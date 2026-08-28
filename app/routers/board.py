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
from app.domain import permissions as perm
from app.domain.departments import short_name
from app.models import DiscussionEntry, Retreat, TaskRun, User
from app.security import get_current_user
from app.templating import render

router = APIRouter()


def _can_edit(user: User, run: TaskRun) -> bool:
    return perm.can_edit_department_content(
        role=user.role,
        user_department_id=user.department_id,
        target_department_id=run.department_id,
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

    view = board_view.build(db, retreat)
    my_key = None
    if user.department_id is not None:
        dept = next((d for d in retreat.departments if d.id == user.department_id), None)
        my_key = dept.key if dept else None

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
        "can_edit": _can_edit(user, run),
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
    if not _can_edit(user, run):
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
    if not _can_edit(user, run):
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
