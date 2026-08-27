"""할 일(Task) 관리."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.models import TASK_STATUSES, Department, Retreat, ScheduleItem, Task, User
from app.security import assert_can_edit_department, get_current_user, require_editor
from app.templating import redirect, render

router = APIRouter(prefix="/tasks")


def _parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    return dt.date.fromisoformat(raw)


def _departments(db: Session, retreat: Retreat) -> list[Department]:
    return list(
        db.scalars(
            select(Department)
            .where(Department.retreat_id == retreat.id)
            .order_by(Department.sort_order, Department.id)
        )
    )


def _members(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.is_active).order_by(User.name)))


@router.get("")
def task_list(
    request: Request,
    scope: str = "all",
    status: str = "",
    department_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    query = select(Task).where(Task.retreat_id == retreat.id)
    if status:
        query = query.where(Task.status == status)
    if department_id:
        query = query.where(Task.department_id == department_id)

    tasks = list(
        db.scalars(query.order_by(Task.due_date.is_(None), Task.due_date, Task.id))
    )
    if scope == "mine":
        tasks = [
            t
            for t in tasks
            if t.assignee_id == user.id
            or (user.department_id is not None and t.department_id == user.department_id)
        ]

    return render(
        request,
        "tasks.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "tasks": tasks,
            "departments": _departments(db, retreat),
            "members": _members(db),
            "statuses": TASK_STATUSES,
            "scope": scope,
            "status_filter": status,
            "department_filter": department_id,
            "schedule_items": list(
                db.scalars(
                    select(ScheduleItem)
                    .join(ScheduleItem.day)
                    .where(ScheduleItem.day.has(retreat_id=retreat.id))
                    .order_by(ScheduleItem.id)
                )
            ),
        },
    )


@router.post("/create")
def create_task(
    title: str = Form(...),
    description: str = Form(""),
    department_id: str = Form(""),
    assignee_id: str = Form(""),
    schedule_item_id: str = Form(""),
    due_date: str = Form(""),
    status: str = Form("대기"),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    dept_id = int(department_id) if department_id else None
    assert_can_edit_department(user, dept_id)

    if status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail="알 수 없는 상태값입니다.")

    task = Task(
        retreat_id=retreat.id,
        title=title.strip(),
        description=description.strip() or None,
        department_id=dept_id,
        assignee_id=int(assignee_id) if assignee_id else None,
        schedule_item_id=int(schedule_item_id) if schedule_item_id else None,
        due_date=_parse_date(due_date),
        status=status,
        blocked_by_task_ids=[],
        related_department_ids=[],
    )
    db.add(task)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="할일_생성",
        target_type="task",
        target_id=task.id,
        summary=task.title,
    )
    return redirect(f"/tasks?retreat_id={retreat.id}", message="할 일을 추가했습니다.")


@router.post("/{task_id}/status")
def update_status(
    task_id: int,
    status: str = Form(...),
    redirect_to: str = Form("/tasks"),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    task = db.get(Task, task_id)
    if task is None or task.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")
    if status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail="알 수 없는 상태값입니다.")
    assert_can_edit_department(user, task.department_id)

    before = task.status
    task.status = status
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="할일_상태변경",
        target_type="task",
        target_id=task.id,
        summary=f"{task.title}: {before} → {status}",
        before_value={"status": before},
        after_value={"status": status},
    )
    sep = "&" if "?" in redirect_to else "?"
    return redirect(f"{redirect_to}{sep}retreat_id={retreat.id}", message="상태를 변경했습니다.")


@router.post("/{task_id}/update")
def update_task(
    task_id: int,
    title: str = Form(...),
    description: str = Form(""),
    department_id: str = Form(""),
    assignee_id: str = Form(""),
    due_date: str = Form(""),
    status: str = Form("대기"),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    task = db.get(Task, task_id)
    if task is None or task.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")
    assert_can_edit_department(user, task.department_id)

    new_dept = int(department_id) if department_id else None
    if new_dept != task.department_id:
        # 다른 부서로 넘기려면 그 부서에 대한 권한도 있어야 한다.
        assert_can_edit_department(user, new_dept)

    task.title = title.strip()
    task.description = description.strip() or None
    task.department_id = new_dept
    task.assignee_id = int(assignee_id) if assignee_id else None
    task.due_date = _parse_date(due_date)
    if status in TASK_STATUSES:
        task.status = status
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="할일_수정",
        target_type="task",
        target_id=task.id,
        summary=task.title,
    )
    return redirect(f"/tasks?retreat_id={retreat.id}", message="할 일을 수정했습니다.")


@router.post("/{task_id}/delete")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    task = db.get(Task, task_id)
    if task is None or task.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")
    assert_can_edit_department(user, task.department_id)

    title = task.title
    db.delete(task)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="할일_삭제",
        target_type="task",
        target_id=task_id,
        summary=title,
    )
    return redirect(f"/tasks?retreat_id={retreat.id}", message="할 일을 삭제했습니다.")
