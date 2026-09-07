"""준비 단계 보드 (CLAUDE.md 4장)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity, resolve_retreat
from app.domain import board as board_view
from app.domain import diagnosis
from app.domain import discussion
from app.domain import dweek
from app.domain import library as lib_domain
from app.domain import permissions as perm
from app.domain.departments import department_key_of, short_name
from app.models import DiscussionEntry, Meeting, Retreat, TaskRun, User
from app.routers import attachments
from app.security import get_current_user
from app.templating import render

router = APIRouter()


def _dept_key_of(db: Session, user: User) -> str | None:
    """로그인한 사람의 부서 키. 공용 함수로 옮겼다 — 알림 쪽과 같은 것을 써야 한다."""
    return department_key_of(db, user)


def _can_edit(db: Session, user: User, run: TaskRun) -> bool:
    return perm.can_edit_department_by_key(
        role=user.role,
        user_department_key=_dept_key_of(db, user),
        target_department_key=run.department.key if run.department else None,
    )


@router.get("/board")
def board_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """준비 보드. 홈은 / (4-15) — 이 화면은 /board 다."""
    raw = request.query_params.get("retreat_id")
    retreat = resolve_retreat(db, user, int(raw) if raw and raw.isdigit() else None)
    if retreat is None:
        return render(request, "no_retreat.html", {"user": user})
    if retreat.start_date is None:
        raise HTTPException(status_code=400, detail="회차의 개회일이 지정되지 않았습니다.")

    my_key = _dept_key_of(db, user)
    view = board_view.build(db, retreat, can_edit=lambda run: perm.can_edit_department_by_key(
            role=user.role, user_department_key=my_key,
            target_department_key=run.department.key if run.department else None))
    return render(
        request,
        "board.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "board": view,
            "my_department_key": my_key,
            "active_tab": "board",
            "page_subtitle": "준비 보드",
        },
    )


def _load_run(db: Session, retreat: Retreat, run_id: int) -> TaskRun:
    run = db.get(TaskRun, run_id)
    if run is None or run.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다.")
    return run


def _serialize_discussions(db: Session, run: TaskRun, user: User | None = None) -> list[dict]:
    """논의 목록. 걸린 곳(runs)과 출처(source)를 함께 싣는다 (4-9).

    걸린 곳은 링크 표에서 읽는다(discussion.runs_of) — 한 곳뿐이면 화면이
    아무것도 안 붙이고, 둘 이상이면 「여기」 와 나머지 업무 이름을 붙인다.
    """
    entries = run.discussions
    replaced = {e.supersedes_entry_id for e in entries if e.supersedes_entry_id}
    # 출처가 회의록인 것들의 회의 날짜 — 한 번에 모아 읽는다
    meeting_ids = {e.source_meeting_id for e in entries if e.source_meeting_id}
    meetings = {
        m.id: m
        for m in db.scalars(select(Meeting).where(Meeting.id.in_(meeting_ids)))
    } if meeting_ids else {}

    out = []
    for entry in entries:
        attached = discussion.runs_of(db, entry)
        meeting = meetings.get(entry.source_meeting_id)
        out.append(
            {
                "id": entry.id,
                "date": entry.authored_at.strftime("%m/%d") if entry.authored_at else "",
                "body": entry.body,
                "author": entry.author_name,
                "superseded": entry.id in replaced,
                "replaces": entry.supersedes_entry_id,
                "carried": entry.carried_from_run_id is not None,
                "can_edit": _can_edit_entry(user, entry),
                # 걸린 곳 — 지금 보는 업무는 here 로 표시된다
                "runs": [
                    {
                        "run_id": r.id,
                        "title": r.library.title,
                        "here": r.id == run.id,
                    }
                    for r in attached
                ],
                # 출처 — 회의록에서 온 것이면 그 회의록으로 가는 길을 준다.
                # 없으면 화면이 「직접 적음 · M/D」 로 그린다.
                "source": (
                    {
                        "meeting_id": meeting.id,
                        "label": (
                            f"{meeting.meeting_date.month}/{meeting.meeting_date.day} 회의"
                            if meeting.meeting_date
                            else "회의"
                        ),
                    }
                    if meeting is not None
                    else None
                ),
            }
        )
    return out


def _can_edit_entry(user: User | None, entry: DiscussionEntry) -> bool:
    """자기가 쓴 기록만 고친다. 총무팀은 전부 고칠 수 있다.

    지난 회차에서 따라온 기록은 그 회차의 사실이므로 여기서 손대지 않는다.
    말을 바꾸는 것과 잘못 쓴 것을 고치는 것은 다르다 — 결정이 뒤집힌 것은
    취소선 + 후속 기록으로 남기고, 이 기능은 오타·오기를 위한 것이다.
    """
    if user is None or entry.carried_from_run_id is not None:
        return False
    return perm.can_manage_retreat(user.role) or entry.author_id == user.id


@router.get("/board/task/{run_id}")
def task_detail(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    run = _load_run(db, retreat, run_id)
    lib = run.library

    by_library = {
        r.library_id: r
        for r in db.scalars(
            select(TaskRun).where(TaskRun.retreat_id == retreat.id, TaskRun.included)
        )
    }
    dept_by_key = {d.key: d for d in retreat.departments}

    related = []
    for library_id in lib.related_library_ids or []:
        other = by_library.get(library_id)
        if other is None:
            continue
        related.append(
            {
                "run_id": other.id,
                "title": other.library.title,
                "kind_label": other.library.kind_label,
                "department": short_name(other.department.name) if other.department else "담당 없음",
                "color": other.department.color if other.department else "#69726D",
                "start": other.start_date.isoformat() if other.start_date else None,
                "end": (other.end_date or other.start_date).isoformat()
                if other.start_date
                else None,
            }
        )

    def brief(other: TaskRun) -> dict:
        return {
            "run_id": other.id,
            "library_id": other.library_id,
            "title": other.library.title,
            "kind_label": other.library.kind_label,
            "department": short_name(other.department.name) if other.department else "담당 없음",
            "color": other.department.color if other.department else "#69726D",
            "status": other.status,
            "start": other.start_date.isoformat() if other.start_date else None,
            "end": (other.end_date or other.start_date).isoformat()
            if other.start_date
            else None,
        }

    # 선행은 라이브러리에 단방향으로 저장돼 있고, 후속은 그 역방향을 계산한 것이다.
    # 관련(방향 없음)과 섞지 않는다 — 대응이 완전히 다르기 때문이다.
    prerequisites = [
        brief(by_library[i])
        for i in lib_domain.prerequisites_of(lib)
        if i in by_library
    ]
    dependents = [
        brief(by_library[library_id])
        for library_id in lib_domain.dependents_map(db).get(lib.id, [])
        if library_id in by_library
    ]

    parent = by_library.get(lib.parent_library_id) if lib.parent_library_id else None

    return {
        "run_id": run.id,
        "run_no": run.run_no,   # 회차 안에서 고정되는 번호 (4-14)
        "title": lib.title,
        "kind": lib.kind,
        "kind_label": lib.kind_label,
        "status": run.status,
        # 배지는 한 곳에서 만든다 (board.paint_of · 4-3) — 기한이 지났으면 '지연'
        "badge": board_view.paint_of(run, dt.date.today())["badge"],
        "start": run.start_date.isoformat() if run.start_date else None,
        "end": (run.end_date or run.start_date).isoformat() if run.start_date else None,
        "d_week": run.d_week,
        "department": run.department.name if run.department else "담당 없음",
        "department_color": run.department.color if run.department else "#69726D",
        "assignee_id": run.assignee_id,
        "assignee": run.assignee.name if run.assignee else None,
        "candidates": _assignee_candidates(db, run),
        "department_key": run.department.key if run.department else None,
        "departments": [
            {"key": d.key, "name": d.name, "color": d.color}
            for d in sorted(retreat.departments, key=lambda d: d.sort_order)
        ],
        "parent_run_id": parent.id if parent else None,
        "parent_title": parent.library.title if parent else None,
        "related_departments": [
            dept_by_key[k].name
            for k in (lib.related_department_keys or [])
            if k in dept_by_key
        ],
        # 편집(4-9)은 키로 한다 (2장) — 이름만 주면 화면이 이름으로 키를 찾게 된다
        "related_department_keys": [
            k for k in (lib.related_department_keys or []) if k in dept_by_key
        ],
        "related": related,
        "prerequisites": prerequisites,
        "dependents": dependents,
        # 선후행을 고칠 수 있는 사람은 '선행을 가진 쪽' 업무의 담당 부서와 총무팀이다.
        # A 가 B 를 기다린다고 적는 것은 A 쪽의 판단이므로 A 의 부서가 적는다.
        "link_candidates": [
            {
                "run_id": other.id,
                "library_id": other.library_id,
                "title": other.library.title,
                "d_week": other.d_week,
            }
            for other in sorted(
                by_library.values(), key=lambda r: (r.library.title, r.id)
            )
            if other.id != run.id
        ],
        "discussions": _serialize_discussions(db, run, user),
        # 이 업무의 확인 요청 이력 (4-9) — 보낸 것과 답이 함께 보인다
        "reviews": _serialize_reviews(db, run),
        # 첨부는 회차별이라 run 에 붙는다 (CLAUDE.md 4-9). 상세 패널이
        # 탭을 열기 전에 개수를 보여줘야 해서 여기서 함께 내려보낸다.
        "attachments": attachments.serialize(db, user, run),
        "attachment_limits": attachments.limits(),
        "rules": lib.rules,
        "reclassification_note": lib.reclassification_note,
        "suggestion_rationale": lib.suggestion_rationale
        if lib.origin == "claude_suggestion"
        else None,
        "can_edit": _can_edit(db, user, run),
        # 진단은 저장하지 않고 요청할 때마다 계산한다 (CLAUDE.md 4-10)
        "diagnosis": diagnosis.diagnose(db, retreat, run).as_dict(),
    }


class StatusIn(BaseModel):
    status: str


@router.post("/board/task/{run_id}/status")
def set_status(
    run_id: int,
    payload: StatusIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    from app.models import RUN_STATUSES

    if payload.status not in RUN_STATUSES:
        raise HTTPException(status_code=400, detail="알 수 없는 상태입니다.")

    run = _load_run(db, retreat, run_id)
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 편집할 수 있습니다.")

    before = run.status
    run.status = payload.status
    # 처음 '대기' 를 벗어나면 착수한 날을 찍는다. 되돌려도 지우지 않는다 —
    # 착수했다는 사실은 사라지지 않고, 진단 패널이 이걸로 판정한다.
    if run.started_at is None and payload.status != "대기":
        run.started_at = dt.date.today()
    # 완료는 취소될 수 있으므로 벗어나면 지운다 (착수와 반대다)
    if payload.status == "완료":
        if run.completed_at is None:
            run.completed_at = dt.date.today()
    else:
        run.completed_at = None
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="업무_상태_변경",
        target_type="task_run",
        target_id=run.id,
        summary=f"{run.library.title}: {before} → {payload.status}",
        before_value={"status": before},
        after_value={"status": payload.status},
    )

    # **생김새는 한 곳에서 만든다** (board.paint_of). 바·점·배지는 이제 한
    # 규칙이지만(4-3) 화면(JS)이 받는 이름 쌍(bar_*/dot_*)은 그대로다 —
    # 화면은 받아서 칠하기만 한다.
    return JSONResponse(board_view.paint_of(run, dt.date.today()))


def _assignee_candidates(db: Session, run: TaskRun) -> list[dict]:
    """담당자로 고를 수 있는 사람 — 그 부서 소속 + 총무팀.

    부서가 정해지지 않은 업무는 총무팀 소관이므로 관리자만 보인다.
    """
    from app.models import Department

    people = []
    keys = {run.department.key} if run.department else set()
    for user in db.scalars(select(User).where(User.is_active)):
        if perm.can_manage_retreat(user.role):
            people.append(user)
            continue
        if user.department_id is None:
            continue
        dept = db.get(Department, user.department_id)
        if dept and dept.key in keys:
            people.append(user)
    seen, out = set(), []
    for user in people:
        if user.id in seen:
            continue
        seen.add(user.id)
        out.append({"id": user.id, "name": user.name, "role": perm.ROLE_LABELS.get(user.role, user.role)})
    return sorted(out, key=lambda p: p["name"])


class DepartmentIn(BaseModel):
    key: str | None = None


@router.post("/board/task/{run_id}/department")
def set_department(
    run_id: int,
    payload: DepartmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """담당팀을 옮긴다.

    업무가 다른 부서의 줄로 통째로 옮겨가는 일이라 보드를 다시 그려야 한다.
    넘기고 나면 넘긴 쪽은 더 이상 그 업무를 고칠 수 없다 — 그게 넘긴다는 뜻이다.
    """
    run = _load_run(db, retreat, run_id)
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 옮길 수 있습니다.")

    dept_by_key = {d.key: d for d in retreat.departments}
    if payload.key and payload.key not in dept_by_key:
        raise HTTPException(status_code=400, detail="이번 회차에 없는 부서입니다.")

    before = run.department.name if run.department else "담당 없음"
    target = dept_by_key.get(payload.key) if payload.key else None
    run.department_id = target.id if target else None

    # 넘긴 팀 사람이 담당자로 남아 있으면 뜻이 맞지 않는다
    if run.assignee is not None and not perm.can_manage_retreat(run.assignee.role):
        from app.models import Department

        holder = db.get(Department, run.assignee.department_id) if run.assignee.department_id else None
        if holder is None or holder.key != payload.key:
            run.assignee_id = None
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="담당팀_변경",
        target_type="task_run",
        target_id=run.id,
        summary=f"{run.library.title}: {before} → {target.name if target else '담당 없음'}",
    )
    # `reload` 를 함께 보내던 것을 뺐다 — 읽는 곳이 없다. 다시 그릴지는
    # 화면이 정한다 (drawer.js 의 onDepartment 규약).
    return {"department_key": payload.key}


class AssigneeIn(BaseModel):
    user_id: int | None = None


@router.post("/board/task/{run_id}/assignee")
def set_assignee(
    run_id: int,
    payload: AssigneeIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """담당자를 지정한다. 팀만 적혀 있으면 결국 아무도 안 한다."""
    run = _load_run(db, retreat, run_id)
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 지정할 수 있습니다.")

    before = run.assignee.name if run.assignee else None
    if payload.user_id is None:
        run.assignee_id = None
    else:
        target = db.get(User, payload.user_id)
        if target is None or not target.is_active:
            raise HTTPException(status_code=400, detail="그 사람을 찾을 수 없습니다.")
        run.assignee_id = target.id
    db.commit()
    db.refresh(run)
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="담당자_지정",
        target_type="task_run",
        target_id=run.id,
        summary=f"{run.library.title}: {before or '없음'} → {run.assignee.name if run.assignee else '없음'}",
    )
    # **생김새와 함께 돌려준다** (board.paint_of). 담당자는 점에 적히지 않지만
    # 마우스를 올렸을 때 뜨는 한 줄에는 들어간다 — 그 문장을 화면이 다시
    # 조립하게 두면 옛 이름이 남는다. 실제로 그랬다 (4-13).
    return {
        "assignee_id": run.assignee_id,
        "assignee": run.assignee.name if run.assignee else None,
        **board_view.paint_of(run, dt.date.today()),
    }


class DatesIn(BaseModel):
    start: str
    end: str | None = None


@router.post("/board/task/{run_id}/dates")
def move_dates(
    run_id: int,
    payload: DatesIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """바를 끌어 옮겨 날짜를 바꾼다.

    이번 회차의 실행 기록만 바뀐다. 라이브러리의 기본 D-주차는 그대로다 —
    한 회차에서 일정을 당겼다고 다음 회차의 기준까지 따라 움직이면 안 된다.
    """
    run = _load_run(db, retreat, run_id)
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 옮길 수 있습니다.")

    try:
        start = dt.date.fromisoformat(payload.start)
        end = dt.date.fromisoformat(payload.end) if payload.end else start
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다.") from exc
    if end < start:
        raise HTTPException(status_code=400, detail="마감일이 시작일보다 빠릅니다.")

    before = {
        "start": run.start_date.isoformat() if run.start_date else None,
        "end": run.end_date.isoformat() if run.end_date else None,
    }
    run.start_date, run.end_date = start, end
    run.d_week = dweek.week_of(retreat.start_date, start) if start < retreat.start_date else None
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="업무_날짜_변경",
        target_type="task_run",
        target_id=run.id,
        summary=f"{run.library.title}: {before['start']} → {start.isoformat()}",
        before_value=before,
        after_value={"start": start.isoformat(), "end": end.isoformat()},
    )
    # 날짜를 옮기면 **기한 초과가 바뀌고, 달력의 점 색이 그것을 따라간다** (4-13).
    # 화면에서 다시 계산하지 않도록 상태 변경과 **같은 모양**으로 실어 보낸다.
    return {
        **board_view.paint_of(run, dt.date.today()),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "d_week": run.d_week,
        "label": f"{start.month}/{start.day}"
        + (f"–{end.month}/{end.day}" if end != start else ""),
    }


class DiscussionIn(BaseModel):
    body: str
    supersedes_entry_id: int | None = None


@router.post("/board/task/{run_id}/discussion")
def add_discussion(
    run_id: int,
    payload: DiscussionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    run = _load_run(db, retreat, run_id)
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 편집할 수 있습니다.")

    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="내용을 입력해주세요.")

    supersedes = payload.supersedes_entry_id
    if supersedes is not None:
        target = db.get(DiscussionEntry, supersedes)
        # 걸린 곳은 링크 표에서 본다 (4-9) — run_id 를 읽지 않는다
        if target is None or run.id not in {r.id for r in discussion.runs_of(db, target)}:
            raise HTTPException(status_code=400, detail="대체할 기록을 찾을 수 없습니다.")

    entry = DiscussionEntry(
        _legacy_run_id=run.id,
        authored_at=dt.date.today(),
        body=body,
        author_id=user.id,
        author_name=user.name,
        supersedes_entry_id=supersedes,
    )
    db.add(entry)
    db.flush()
    # 걸린 곳의 유일한 출처는 링크 표다 — 만들 때 함께 건다 (4-9).
    # **번복(후속)은 대체되는 기록이 걸린 곳을 그대로 물려받는다** — 한쪽에서만
    # 번복하면 다른 쪽에는 번복 안 된 결정으로 남는다. 뗀 곳은 물려받지 않는다.
    if supersedes is not None:
        for attached_run in discussion.runs_of(db, target):
            discussion.attach(db, entry, attached_run)
    else:
        discussion.attach(db, entry, run)
    db.commit()
    db.refresh(run)

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="논의_추가",
        target_type="task_run",
        target_id=run.id,
        summary=f"{run.library.title}: {body[:40]}",
    )
    return {"discussions": _serialize_discussions(db, run, user)}


# ---------------------------------------------------------------- 업무 추가


@router.get("/board/add")
def add_task_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """회차를 연 뒤에도 업무는 늘어난다.

    라이브러리에 이미 있는 것을 이번 회차에 넣거나, 아예 새 업무를 만든다.
    새로 만든 것도 라이브러리에 남아 다음 회차의 후보가 된다.
    """
    from app.domain import dweek as dweek_mod
    from app.models import TaskLibrary

    if perm.is_readonly(user.role):
        raise HTTPException(status_code=403, detail="열람 전용 계정은 추가할 수 없습니다.")

    existing = {
        run.library_id
        for run in db.scalars(select(TaskRun).where(TaskRun.retreat_id == retreat.id, TaskRun.included))
    }
    rows = []
    for lib in db.scalars(
        select(TaskLibrary)
        .where(TaskLibrary.archived_at.is_(None), TaskLibrary.parent_library_id.is_(None))
        .order_by(TaskLibrary.title)
    ):
        if lib.id in existing:
            continue
        start, _ = dweek_mod.resolve_dates(
            retreat.start_date,
            anchor=lib.date_anchor,
            d_week=lib.default_d_week,
            offset_days=lib.default_offset_days,
            span_days=lib.default_span_days,
        )
        rows.append(
            {
                "library_id": lib.id,
                "title": lib.title,
                "kind": lib.kind,
                "kind_label": lib.kind_label,
                "department_key": lib.default_department_key,
                "d_week": lib.default_d_week,
                "start_label": f"{start.month}/{start.day}",
            }
        )

    departments = sorted(retreat.departments, key=lambda d: d.sort_order)

    # 기간은 보드와 같은 눈금으로 고른다 — 주 단위 구간은 주로, 일 단위 구간은 날짜로.
    # 보드가 그리는 범위보다 앞쪽까지 열어 둔다 (기획 업무는 D-13주보다 앞에 있다).
    slots = board_view.planning_slots(retreat.start_date, retreat.end_date)

    parents = sorted(
        (
            {"library_id": run.library_id, "title": run.library.title,
             "department_key": run.department.key if run.department else None}
            for run in board_view.load_runs(db, retreat)
            if run.library.kind == "main"
        ),
        key=lambda p: p["title"],       # 가나다순
    )

    return render(
        request,
        "board_add.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "library_rows": rows,
            "departments": departments,
            # 소속 키는 회차를 가리지 않고 찾는다 (2장) — 이 회차 목록에서
            # id 로 찾으면 다른 회차 소속의 키가 안 잡힌다
            "my_department_key": department_key_of(db, user),
            "viewer_is_admin": perm.can_manage_retreat(user.role),
            "slots": slots,
            "parents": parents,
            "active_tab": "board",
            "page_subtitle": "업무 추가",
        },
    )


class AddExistingIn(BaseModel):
    library_ids: list[int] = []


@router.post("/board/add/existing")
def add_existing(
    payload: AddExistingIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """라이브러리에 있는 업무를 이번 회차에 넣는다."""
    from app.domain import dweek as dweek_mod
    from app.models import TaskLibrary

    if perm.is_readonly(user.role):
        raise HTTPException(status_code=403, detail="열람 전용 계정은 추가할 수 없습니다.")

    dept_by_key = {d.key: d for d in retreat.departments}
    added = 0
    for library_id in payload.library_ids:
        lib = db.get(TaskLibrary, library_id)
        if lib is None:
            continue
        dept = dept_by_key.get(lib.default_department_key or "")
        if not perm.can_edit_department_by_key(
            role=user.role,
            user_department_key=_dept_key_of(db, user),
            target_department_key=lib.default_department_key,
        ):
            raise HTTPException(status_code=403, detail="내 부서의 업무만 추가할 수 있습니다.")
        for target in [lib] + list(
            db.scalars(select(TaskLibrary).where(TaskLibrary.parent_library_id == lib.id))
        ):
            start, end = dweek_mod.resolve_dates(
                retreat.start_date,
                anchor=target.date_anchor,
                d_week=target.default_d_week,
                offset_days=target.default_offset_days,
                span_days=target.default_span_days,
            )
            run = db.scalars(
                select(TaskRun).where(
                    TaskRun.retreat_id == retreat.id, TaskRun.library_id == target.id
                )
            ).first()
            target_dept = dept_by_key.get(target.default_department_key or "")
            if run is None:
                db.add(
                    TaskRun(
                        library_id=target.id,
                        retreat_id=retreat.id,
                        included=True,
                        department_id=target_dept.id if target_dept else None,
                        d_week=target.default_d_week,
                        start_date=start,
                        end_date=end,
                        status="대기",
                        # 회차를 연 뒤 더한 업무는 max+1 (4-14)
                        run_no=lib_domain.next_run_no(db, retreat.id),
                    )
                )
                db.flush()
            else:                       # 미실행으로 남아 있던 기록을 되살린다
                run.included = True
                run.start_date, run.end_date = start, end
                run.d_week = target.default_d_week
                run.department_id = target_dept.id if target_dept else None
                if run.run_no is None:  # 번호가 없던 옛 행이면 이때 받는다
                    run.run_no = lib_domain.next_run_no(db, retreat.id)
        added += 1
    db.flush()
    # 회차를 연 뒤에 넣은 업무도 라이브러리의 선행이 이어져야 한다.
    # 여기가 없으면 링크가 비어 그 업무는 조용히 '진행 가능' 이 된다.
    unmet = board_view.relink_prerequisites(db, retreat)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="업무_추가",
        target_type="task_run",
        target_id=None,
        summary=f"라이브러리에서 {added}건 추가",
    )
    return {"added": added, "unmet_prerequisites": unmet, "redirect": "/board"}


class NewTaskIn(BaseModel):
    title: str
    department_key: str | None = None
    kind: str = "main"
    start: str
    end: str | None = None
    parent_library_id: int | None = None


@router.post("/board/add/new")
def add_new(
    payload: NewTaskIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """라이브러리에 없던 업무를 새로 만든다. 다음 회차의 후보로도 남는다.

    **만드는 것은 `domain/tasks.create_run` 하나다** (14장) — 회의록 쪽
    (항목 전환·제안 반영)과 같은 함수를 지난다. 여기 남는 것은 이 경로의
    문(부서 편집 권한)과 입력 파싱뿐이다.
    """
    from app.domain import tasks as tasks_domain

    if perm.is_readonly(user.role):
        raise HTTPException(status_code=403, detail="열람 전용 계정은 추가할 수 없습니다.")
    dept_by_key = {d.key: d for d in retreat.departments}
    dept = dept_by_key.get(payload.department_key or "")
    # **부서가 적혀 있을 때만 키를 검사한다** — 회의록 길(전환·제안 반영)과
    # 같은 규칙이다. 부서 없는 업무는 아직 누구 일인지 안 정해진 것이고,
    # 그것을 만드는 데 관리자를 요구하면 「나중에 정하자」 를 적을 수 없다.
    # 담당 부서는 드로어에서 나중에 고른다 (4-9).
    if payload.department_key and not perm.can_edit_department_by_key(
        role=user.role,
        user_department_key=_dept_key_of(db, user),
        target_department_key=payload.department_key,
    ):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 추가할 수 있습니다.")

    try:
        start = dt.date.fromisoformat(payload.start)
        end = dt.date.fromisoformat(payload.end) if payload.end else start
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="기간을 다시 골라주세요.") from exc

    try:
        lib, _run = tasks_domain.create_run(
            db,
            retreat,
            title=payload.title,
            kind=payload.kind,
            department=dept,
            parent_library_id=payload.parent_library_id,
            start=start,
            end=end,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="업무_신규생성",
        target_type="task_library",
        target_id=lib.id,
        summary=f"{lib.title} ({start.isoformat()} ~ {end.isoformat()})",
    )
    return {"library_id": lib.id, "redirect": "/board"}


def _serialize_reviews(db: Session, run: TaskRun) -> list[dict]:
    """이 업무의 확인 요청 이력 — run_id 로 남은 것만 (옛 요청은 Task 표를
    가리켜 run 으로 잇지 못한다)."""
    from app.models import ReviewRequest

    rows = db.scalars(
        select(ReviewRequest)
        .where(ReviewRequest.run_id == run.id)
        .order_by(ReviewRequest.id.desc())
    )
    return [
        {
            "id": r.id,
            "department": r.department.name if r.department else "",
            "department_color": r.department.color if r.department else "#83827F",
            "status": r.status,
            "requester": r.requester_name,
            "message": r.message,
            "responder": r.responder_name,
            "comment": r.response_comment,
            "at": r.created_at.strftime("%m/%d") if r.created_at else "",
        }
        for r in rows
    ]


class TitleIn(BaseModel):
    title: str


@router.post("/board/task/{run_id}/title")
def set_title(
    run_id: int,
    payload: TitleIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """제목을 그 자리에서 고친다 (4-9).

    제목은 라이브러리에 붙는다 — 회차를 넘어 같은 업무의 이름이다. 지난
    회차의 화면에도 새 이름이 보이지만, 그때의 실행 기록(날짜·상태)은
    그대로다 (6-6 의 「지난 회차의 실행 기록 날짜는 건드리지 않는다」 와 같은 결).
    """
    run = _load_run(db, retreat, run_id)
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 편집할 수 있습니다.")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="제목을 비울 수 없습니다.")

    before = run.library.title
    if before != title:
        run.library.title = title
        db.commit()
        log_activity(
            db,
            retreat_id=retreat.id,
            actor=user,
            action="업무_제목_변경",
            target_type="task_run",
            target_id=run.id,
            summary=f"제목 변경: {before} → {title}",
            before_value={"title": before},
            after_value={"title": title},
        )
    paint = board_view.paint_of(run, dt.date.today())
    # 화면들이 제 라벨을 갈아 끼울 수 있게 문장(툴팁)도 함께 낸다 — 조립 금지 (9장)
    return {"title": title, "tooltip": paint["tooltip"]}


class RelatedDeptsIn(BaseModel):
    keys: list[str]


@router.post("/board/task/{run_id}/related-departments")
def set_related_departments(
    run_id: int,
    payload: RelatedDeptsIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """관련팀을 그 자리에서 고친다 (4-9). 부서는 **키**로 받는다 (2장).

    관련팀은 라이브러리에 붙는다 — 다음 회차에도 그대로 따라간다.
    보드의 고스트 바가 이 값에서 나오므로 보드는 다시 그린다.
    """
    run = _load_run(db, retreat, run_id)
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 편집할 수 있습니다.")
    valid = {d.key for d in retreat.departments if d.key}
    unknown = [k for k in payload.keys if k not in valid]
    if unknown:
        raise HTTPException(status_code=400, detail=f"모르는 부서 키입니다: {', '.join(unknown)}")

    lib = run.library
    before = sorted(lib.related_department_keys or [])
    after = sorted(set(payload.keys))
    if before != after:
        lib.related_department_keys = after
        db.commit()
        log_activity(
            db,
            retreat_id=retreat.id,
            actor=user,
            action="관련팀_변경",
            target_type="task_run",
            target_id=run.id,
            summary=f"{lib.title}: 관련팀 {len(after)}곳",
            before_value={"keys": before},
            after_value={"keys": after},
        )
    dept_by_key = {d.key: d for d in retreat.departments}
    return {
        "related_department_keys": after,
        "related_departments": [dept_by_key[k].name for k in after if k in dept_by_key],
    }


class ReviewRequestIn(BaseModel):
    department_keys: list[str]
    message: str = ""


@router.post("/board/task/{run_id}/review-request")
def request_review(
    run_id: int,
    payload: ReviewRequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """이 업무에 대한 확인 요청 (4-9) — 옛 task_detail 의 폼이 있던 자리다.

    요청은 ReviewRequest 로 남고(run_id 로 업무를 가리킨다), 받는 부서
    사람들의 알림 「받은 것」 과 내 「내가 보낸 요청」 에 뜬다 (4-16).
    """
    from app.routers.reviews import create_review_requests

    run = _load_run(db, retreat, run_id)
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 편집할 수 있습니다.")
    dept_by_key = {d.key: d for d in retreat.departments if d.key}
    # 모르는 키는 걸러서 진행하지 않고 **거절한다** (5-1 · related-departments 와
    # 같은 규칙) — 셋 중 둘만 가면 보낸 사람은 셋 다 갔다고 믿는다
    unknown = [k for k in payload.department_keys if k not in dept_by_key]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"이 회차에 없는 부서입니다: {', '.join(unknown)}",
        )
    ids = [dept_by_key[k].id for k in payload.department_keys]
    if not ids:
        raise HTTPException(status_code=400, detail="확인받을 부서를 하나 이상 골라주세요.")

    created = create_review_requests(
        db,
        retreat=retreat,
        requester=user,
        department_ids=ids,
        message=payload.message,
        run=run,
    )
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="확인요청_보냄",
        target_type="task_run",
        target_id=run.id,
        summary=f"{run.library.title} → {len(created)}개 부서",
    )
    return {"reviews": _serialize_reviews(db, run)}


class RulesIn(BaseModel):
    body: str


@router.post("/board/task/{run_id}/rules")
def set_rules(
    run_id: int,
    payload: RulesIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """업무 규칙은 라이브러리에 붙는다 — 회차가 바뀌어도 그대로 간다.

    논의는 그 회차의 사정이고, 규칙은 매번 같은 방식으로 하기 위한 것이다.
    담당자가 바뀌어도 "이건 이렇게 한다"가 사람이 아니라 기록에 남아야 한다.
    """
    run = _load_run(db, retreat, run_id)
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 고칠 수 있습니다.")

    body = payload.body.strip()
    before = run.library.rules
    run.library.rules = body or None
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="업무규칙_수정",
        target_type="task_library",
        target_id=run.library_id,
        summary=f"{run.library.title} 규칙 {'삭제' if not body else '저장'}",
        before_value={"rules": before},
        after_value={"rules": run.library.rules},
    )
    return {"rules": run.library.rules}


class PrerequisitesIn(BaseModel):
    run_ids: list[int] = []


@router.post("/board/task/{run_id}/prerequisites")
def set_prerequisites(
    run_id: int,
    payload: PrerequisitesIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """선행 업무를 고친다.

    관계는 회차가 아니라 라이브러리에 붙는다 — 업무 규칙과 같은 성격이라 다음
    회차에도 그대로 따라간다. 이번 회차의 blocked_by_run_ids 는 그 결과를 지금
    보드에 비추는 사본이다.

    고칠 수 있는 사람은 선행을 '가진 쪽' 업무의 담당 부서와 총무팀이다.
    """
    run = _load_run(db, retreat, run_id)
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 고칠 수 있습니다.")

    by_run_id = {
        r.id: r
        for r in db.scalars(
            select(TaskRun).where(TaskRun.retreat_id == retreat.id, TaskRun.included)
        )
    }
    library_ids: list[int] = []
    for other_run_id in payload.run_ids:
        other = by_run_id.get(other_run_id)
        if other is None:
            raise HTTPException(status_code=400, detail="이번 회차에 없는 업무입니다.")
        library_ids.append(other.library_id)

    before = lib_domain.prerequisites_of(run.library)
    try:
        lib_domain.set_prerequisites(db, run.library, library_ids)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 이번 회차의 링크도 함께 맞춘다 (included 끼리만)
    library_to_run = {r.library_id: r for r in by_run_id.values()}
    run.blocked_by_run_ids = [
        library_to_run[i].id for i in run.library.prerequisite_library_ids or []
        if i in library_to_run
    ]
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="선행업무_변경",
        target_type="task_library",
        target_id=run.library_id,
        summary=f"{run.library.title} 선행 {len(before)}건 → {len(library_ids)}건",
        before_value={"prerequisite_library_ids": before},
        after_value={"prerequisite_library_ids": list(run.library.prerequisite_library_ids or [])},
    )
    return task_detail(run.id, db=db, user=user, retreat=retreat)


class DiscussionEditIn(BaseModel):
    body: str


@router.post("/board/task/{run_id}/discussion/{entry_id}")
def edit_discussion(
    run_id: int,
    entry_id: int,
    payload: DiscussionEditIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """써 놓은 논의를 고친다 — 오타나 잘못 적은 것을 바로잡는 용도다."""
    run = _load_run(db, retreat, run_id)
    entry = _entry_of(db, run, entry_id)
    if not _can_edit_entry(user, entry):
        raise HTTPException(status_code=403, detail="내가 쓴 기록만 고칠 수 있습니다.")

    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="내용을 입력해주세요.")

    before = entry.body
    if before == body:
        return {"discussions": _serialize_discussions(db, run, user)}

    entry.body = body
    db.commit()
    db.refresh(run)
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="논의_수정",
        target_type="discussion_entry",
        target_id=entry.id,
        summary=f"{run.library.title}: {before[:30]} → {body[:30]}",
        before_value={"body": before},
        after_value={"body": body},
    )
    return {"discussions": _serialize_discussions(db, run, user)}


def _entry_of(db: Session, run: TaskRun, entry_id: int) -> DiscussionEntry:
    """이 업무에 걸려 있는 논의 하나. 걸린 곳은 링크 표에서 본다 (4-9)."""
    entry = db.get(DiscussionEntry, entry_id)
    if entry is None or run.id not in {r.id for r in discussion.runs_of(db, entry)}:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
    return entry


@router.post("/board/task/{run_id}/discussion/{entry_id}/detach")
def detach_discussion(
    run_id: int,
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """논의를 이 업무에서 뗀다 — 지우지 않는다(detachedAt, 4-9).

    마지막 한 곳은 떼지 못한다: 붙을 곳 없는 논의는 어느 화면에도 안 떠서,
    있는데 아무도 못 보는 기록이 된다.
    """
    run = _load_run(db, retreat, run_id)
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무만 편집할 수 있습니다.")
    entry = _entry_of(db, run, entry_id)

    try:
        discussion.detach(db, entry, run)
    except discussion.LastAttachmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(run)
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="논의_떼기",
        target_type="discussion_entry",
        target_id=entry.id,
        summary=f"{run.library.title} 에서 뗌: {entry.body[:30]}",
        before_value={"run_id": run.id},
    )
    return {"discussions": _serialize_discussions(db, run, user)}
