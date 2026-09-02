"""회의록 — 안건/결정사항/액션아이템 기록과 Task 전환.

회의 따로, 실행 따로가 되지 않도록 액션아이템은 한 번의 클릭으로 Task가 된다.
"""

from __future__ import annotations

import datetime as dt
import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import notifications as notify_service
from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.models import (
    MEETING_ITEM_KINDS,
    Department,
    Meeting,
    MeetingItem,
    Retreat,
    Task,
    User,
)
from app.domain import permissions as perm
from app.security import get_current_user, require_editor
from app.templating import redirect, render

router = APIRouter(prefix="/meetings")


def _parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    return dt.date.fromisoformat(raw)


def parse_attendees(raw: str) -> list[str]:
    if not raw:
        return []
    return [name for name in re.split(r"[,\n\r\t ]+", raw.strip()) if name]


def _owned(db: Session, meeting_id: int, retreat: Retreat) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    if meeting.retreat_id is not None and meeting.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    return meeting


@router.get("")
def meeting_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    meetings = list(
        db.scalars(
            select(Meeting)
            .where((Meeting.retreat_id == retreat.id) | (Meeting.retreat_id.is_(None)))
            .order_by(Meeting.meeting_date.is_(None), Meeting.meeting_date.desc(), Meeting.id.desc())
        )
    )
    return render(
        request,
        "meetings.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "meetings": meetings,
            "today": dt.date.today().isoformat(),
            "active_tab": "meetings",
            "can_edit": not perm.is_readonly(user.role),
        },
    )


@router.get("/{meeting_id}")
def meeting_detail(
    meeting_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    meeting = _owned(db, meeting_id, retreat)
    return render(
        request,
        "meeting_detail.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "meeting": meeting,
            "active_tab": "meetings",
            "can_edit": not perm.is_readonly(user.role),
            "kinds": MEETING_ITEM_KINDS,
            "departments": list(
                db.scalars(
                    select(Department)
                    .where(Department.retreat_id == retreat.id)
                    .order_by(Department.sort_order, Department.id)
                )
            ),
            "members": list(
                db.scalars(select(User).where(User.is_active).order_by(User.name))
            ),
        },
    )


@router.post("/create")
def create_meeting(
    title: str = Form(...),
    meeting_date: str = Form(""),
    attendees: str = Form(""),
    body: str = Form(""),
    # 빈 문자열은 클라이언트에 따라 아예 전송되지 않을 수 있으므로
    # "연결 안 함"을 명시적인 토큰으로 받는다.
    link_retreat: str = Form("retreat"),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    meeting = Meeting(
        # 수련회와 무관한 일반 회의는 회차에 연결하지 않는다 (검색·필터로 구분)
        retreat_id=None if link_retreat == "none" else retreat.id,
        title=title.strip(),
        meeting_date=_parse_date(meeting_date) or dt.date.today(),
        attendee_names=parse_attendees(attendees),
        body=body.strip() or None,
        created_by_id=user.id,
    )
    db.add(meeting)
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="회의록_생성",
        target_type="meeting",
        target_id=meeting.id,
        summary=meeting.title,
    )
    return redirect(f"/meetings/{meeting.id}?retreat_id={retreat.id}", message="회의록을 만들었습니다.")


@router.post("/{meeting_id}/items")
def add_item(
    meeting_id: int,
    kind: str = Form(...),
    content: str = Form(...),
    department_id: str = Form(""),
    assignee_id: str = Form(""),
    due_date: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    meeting = _owned(db, meeting_id, retreat)
    if kind not in MEETING_ITEM_KINDS:
        raise HTTPException(status_code=400, detail="알 수 없는 항목 종류입니다.")

    max_order = (
        db.scalar(
            select(func.max(MeetingItem.sort_order)).where(MeetingItem.meeting_id == meeting.id)
        )
        or 0
    )
    db.add(
        MeetingItem(
            meeting_id=meeting.id,
            kind=kind,
            content=content.strip(),
            department_id=int(department_id) if department_id else None,
            assignee_id=int(assignee_id) if assignee_id else None,
            due_date=_parse_date(due_date),
            sort_order=max_order + 1,
        )
    )
    db.commit()
    return redirect(f"/meetings/{meeting.id}?retreat_id={retreat.id}", message="항목을 추가했습니다.")


@router.post("/items/{item_id}/to-task")
def convert_to_task(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    item = db.get(MeetingItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    if item.converted_task_id is not None:
        return redirect(
            f"/meetings/{item.meeting_id}?retreat_id={retreat.id}",
            message="이미 할 일로 등록된 항목입니다.",
        )

    task = Task(
        retreat_id=retreat.id,
        title=item.content[:200],
        description=f"[회의록] {item.meeting.title} ({item.meeting.meeting_date})",
        department_id=item.department_id,
        assignee_id=item.assignee_id,
        due_date=item.due_date,
        status="대기",
        blocked_by_task_ids=[],
        related_department_ids=[],
    )
    db.add(task)
    db.flush()
    item.converted_task_id = task.id
    db.commit()

    if task.assignee_id:
        assignee = db.get(User, task.assignee_id)
        if assignee is not None:
            notify_service.notify(
                db,
                users=[assignee],
                retreat_id=retreat.id,
                kind="할일배정",
                title=f"📋 새 할 일 · {task.title}",
                body=f"'{item.meeting.title}' 회의의 액션아이템이 할 일로 등록됐습니다.",
                link=f"/tasks?retreat_id={retreat.id}",
                target_type="task",
                target_id=task.id,
                dedupe_key=f"task-assigned:{task.id}",
                exclude_user_id=user.id,
            )

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="액션아이템_할일전환",
        target_type="task",
        target_id=task.id,
        summary=task.title,
    )
    return redirect(
        f"/meetings/{item.meeting_id}?retreat_id={retreat.id}", message="할 일로 등록했습니다."
    )


@router.post("/items/{item_id}/delete")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    item = db.get(MeetingItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    meeting_id = item.meeting_id
    db.delete(item)
    db.commit()
    return redirect(f"/meetings/{meeting_id}?retreat_id={retreat.id}", message="항목을 삭제했습니다.")


@router.post("/{meeting_id}/update")
def update_meeting(
    meeting_id: int,
    title: str = Form(...),
    meeting_date: str = Form(""),
    attendees: str = Form(""),
    body: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    meeting = _owned(db, meeting_id, retreat)
    meeting.title = title.strip()
    meeting.meeting_date = _parse_date(meeting_date)
    meeting.attendee_names = parse_attendees(attendees)
    meeting.body = body.strip() or None
    db.commit()
    return redirect(f"/meetings/{meeting.id}?retreat_id={retreat.id}", message="회의록을 저장했습니다.")


@router.post("/{meeting_id}/delete")
def delete_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    meeting = _owned(db, meeting_id, retreat)
    title = meeting.title
    db.delete(meeting)
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="회의록_삭제",
        target_type="meeting",
        target_id=meeting_id,
        summary=title,
    )
    return redirect(f"/meetings?retreat_id={retreat.id}", message="회의록을 삭제했습니다.")
