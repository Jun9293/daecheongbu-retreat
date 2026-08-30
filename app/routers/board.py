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
from app.domain import dweek
from app.domain import library as lib_domain
from app.domain import permissions as perm
from app.domain.departments import department_key_of, short_name
from app.models import DiscussionEntry, Retreat, TaskRun, User
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


@router.get("/")
@router.get("/board")
def board_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """준비 단계 보드. 이 화면이 홈이다."""
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


def _serialize_discussions(run: TaskRun, user: User | None = None) -> list[dict]:
    replaced = {e.supersedes_entry_id for e in run.discussions if e.supersedes_entry_id}
    return [
        {
            "id": entry.id,
            "date": entry.authored_at.strftime("%m/%d") if entry.authored_at else "",
            "body": entry.body,
            "author": entry.author_name,
            "superseded": entry.id in replaced,
            "replaces": entry.supersedes_entry_id,
            "carried": entry.carried_from_run_id is not None,
            "can_edit": _can_edit_entry(user, entry),
        }
        for entry in run.discussions
    ]


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
        "title": lib.title,
        "kind": lib.kind,
        "kind_label": lib.kind_label,
        "status": run.status,
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
        "discussions": _serialize_discussions(run, user),
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

    view_row = {
        "status": run.status,
        "background": None,
        "border": None,
    }
    color = run.department.color if run.department else "#69726D"
    background, border = board_view.bar_style(
        run.status, color, kind=run.library.kind, ghost=False
    )
    view_row["background"] = background
    view_row["border"] = border
    return JSONResponse(view_row)


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
    return {"department_key": payload.key, "reload": True}


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
    return {"assignee_id": run.assignee_id, "assignee": run.assignee.name if run.assignee else None}


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
    return {
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
        if target is None or target.run_id != run.id:
            raise HTTPException(status_code=400, detail="대체할 기록을 찾을 수 없습니다.")

    entry = DiscussionEntry(
        run_id=run.id,
        authored_at=dt.date.today(),
        body=body,
        author_id=user.id,
        author_name=user.name,
        supersedes_entry_id=supersedes,
    )
    db.add(entry)
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
    return {"discussions": _serialize_discussions(run, user)}


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
            "my_department_key": next(
                (d.key for d in departments if d.id == user.department_id), None
            ),
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
                    )
                )
            else:                       # 미실행으로 남아 있던 기록을 되살린다
                run.included = True
                run.start_date, run.end_date = start, end
                run.d_week = target.default_d_week
                run.department_id = target_dept.id if target_dept else None
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
    """라이브러리에 없던 업무를 새로 만든다. 다음 회차의 후보로도 남는다."""
    from app.domain import dweek as dweek_mod
    from app.models import TASK_KINDS, TaskLibrary

    if perm.is_readonly(user.role):
        raise HTTPException(status_code=403, detail="열람 전용 계정은 추가할 수 없습니다.")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="업무 이름을 입력해주세요.")
    if payload.kind not in TASK_KINDS:
        raise HTTPException(status_code=400, detail="알 수 없는 분류입니다.")

    dept_by_key = {d.key: d for d in retreat.departments}
    dept = dept_by_key.get(payload.department_key or "")
    if not perm.can_edit_department_by_key(
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
    if end < start:
        raise HTTPException(status_code=400, detail="마감이 시작보다 빠릅니다.")
    if payload.kind == "sub" and payload.parent_library_id is None:
        raise HTTPException(status_code=400, detail="하위 업무는 상위 업무를 골라야 합니다.")

    # 고른 날짜를 라이브러리의 상대 위치로 되돌려 둔다 (다음 회차에서 다시 계산된다)
    rel = dweek_mod.relative_position(retreat.start_date, start, end)
    lib = TaskLibrary(
        title=title,
        kind=payload.kind,
        parent_library_id=payload.parent_library_id,
        default_department_key=payload.department_key,
        related_department_keys=[],
        related_library_ids=[],
        origin="history",
        **rel,
    )
    db.add(lib)
    db.flush()
    db.add(
        TaskRun(
            library_id=lib.id,
            retreat_id=retreat.id,
            included=True,
            department_id=dept.id if dept else None,
            d_week=lib.default_d_week,
            start_date=start,
            end_date=end,
            status="대기",
        )
    )
    db.flush()
    board_view.relink_prerequisites(db, retreat)   # 새로 만든 업무도 선행을 잇는다
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="업무_신규생성",
        target_type="task_library",
        target_id=lib.id,
        summary=f"{title} ({start.isoformat()} ~ {end.isoformat()})",
    )
    return {"library_id": lib.id, "redirect": "/board"}


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
    entry = db.get(DiscussionEntry, entry_id)
    if entry is None or entry.run_id != run.id:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
    if not _can_edit_entry(user, entry):
        raise HTTPException(status_code=403, detail="내가 쓴 기록만 고칠 수 있습니다.")

    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="내용을 입력해주세요.")

    before = entry.body
    if before == body:
        return {"discussions": _serialize_discussions(run, user)}

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
    return {"discussions": _serialize_discussions(run, user)}
