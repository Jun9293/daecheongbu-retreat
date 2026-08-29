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
from app.domain import dweek
from app.domain import permissions as perm
from app.domain.departments import short_name
from app.models import DiscussionEntry, Retreat, TaskRun, User
from app.security import get_current_user
from app.templating import render

router = APIRouter()


def _dept_key_of(db: Session, user: User) -> str | None:
    """로그인한 사람의 부서 키. 회차가 바뀌어도 이것만은 그대로다."""
    from app.models import Department

    if user.department_id is None:
        return None
    dept = db.get(Department, user.department_id)
    return dept.key if dept else None


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


def _serialize_discussions(run: TaskRun) -> list[dict]:
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
        }
        for entry in run.discussions
    ]


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
        "parent_run_id": parent.id if parent else None,
        "parent_title": parent.library.title if parent else None,
        "related_departments": [
            dept_by_key[k].name
            for k in (lib.related_department_keys or [])
            if k in dept_by_key
        ],
        "related": related,
        "discussions": _serialize_discussions(run),
        "reclassification_note": lib.reclassification_note,
        "suggestion_rationale": lib.suggestion_rationale
        if lib.origin == "claude_suggestion"
        else None,
        "can_edit": _can_edit(db, user, run),
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
    return {"discussions": _serialize_discussions(run)}


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
    return {"added": added, "redirect": "/board"}


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
