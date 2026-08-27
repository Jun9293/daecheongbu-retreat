"""비품·준비물 체크리스트."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.models import Checklist, ChecklistItem, Department, Retreat, Task, User
from app.security import assert_can_edit_department, get_current_user, require_editor
from app.templating import redirect, render

router = APIRouter(prefix="/checklists")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _owned(db: Session, checklist_id: int, retreat: Retreat) -> Checklist:
    checklist = db.get(Checklist, checklist_id)
    if checklist is None or checklist.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="체크리스트를 찾을 수 없습니다.")
    return checklist


@router.get("")
def checklist_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    checklists = list(
        db.scalars(
            select(Checklist)
            .where(Checklist.retreat_id == retreat.id)
            .order_by(Checklist.sort_order, Checklist.id)
        )
    )
    return render(
        request,
        "checklists.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "checklists": checklists,
            "departments": list(
                db.scalars(
                    select(Department)
                    .where(Department.retreat_id == retreat.id)
                    .order_by(Department.sort_order, Department.id)
                )
            ),
            "tasks": list(
                db.scalars(
                    select(Task).where(Task.retreat_id == retreat.id).order_by(Task.id.desc())
                )
            ),
        },
    )


@router.post("/create")
def create_checklist(
    name: str = Form(...),
    department_id: str = Form(""),
    task_id: str = Form(""),
    items: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    dept_id = int(department_id) if department_id else None
    assert_can_edit_department(user, dept_id)

    max_order = (
        db.scalar(
            select(func.max(Checklist.sort_order)).where(Checklist.retreat_id == retreat.id)
        )
        or 0
    )
    checklist = Checklist(
        retreat_id=retreat.id,
        name=name.strip(),
        department_id=dept_id,
        task_id=int(task_id) if task_id else None,
        sort_order=max_order + 1,
    )
    db.add(checklist)
    db.flush()

    # 줄바꿈으로 여러 항목을 한 번에 입력할 수 있게 한다
    for order, line in enumerate(items.splitlines()):
        label = line.strip()
        if label:
            db.add(ChecklistItem(checklist_id=checklist.id, label=label, sort_order=order))
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="체크리스트_생성",
        target_type="checklist",
        target_id=checklist.id,
        summary=checklist.name,
    )
    return redirect(f"/checklists?retreat_id={retreat.id}", message="체크리스트를 만들었습니다.")


@router.post("/{checklist_id}/items")
def add_item(
    checklist_id: int,
    label: str = Form(...),
    quantity: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    checklist = _owned(db, checklist_id, retreat)
    assert_can_edit_department(user, checklist.department_id)

    max_order = (
        db.scalar(
            select(func.max(ChecklistItem.sort_order)).where(
                ChecklistItem.checklist_id == checklist.id
            )
        )
        or 0
    )
    db.add(
        ChecklistItem(
            checklist_id=checklist.id,
            label=label.strip(),
            quantity=quantity.strip() or None,
            sort_order=max_order + 1,
        )
    )
    db.commit()
    return redirect(f"/checklists?retreat_id={retreat.id}", message="항목을 추가했습니다.")


@router.post("/items/{item_id}/toggle")
def toggle_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    item = db.get(ChecklistItem, item_id)
    if item is None or item.checklist.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    assert_can_edit_department(user, item.checklist.department_id)

    item.checked = not item.checked
    if item.checked:
        item.checked_by_id = user.id
        item.checked_by_name = user.name
        item.checked_at = _now()
    else:
        item.checked_by_id = None
        item.checked_by_name = None
        item.checked_at = None
    db.commit()
    return redirect(f"/checklists?retreat_id={retreat.id}")


@router.post("/items/{item_id}/delete")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    item = db.get(ChecklistItem, item_id)
    if item is None or item.checklist.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    assert_can_edit_department(user, item.checklist.department_id)

    db.delete(item)
    db.commit()
    return redirect(f"/checklists?retreat_id={retreat.id}", message="항목을 삭제했습니다.")


@router.post("/{checklist_id}/delete")
def delete_checklist(
    checklist_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    checklist = _owned(db, checklist_id, retreat)
    assert_can_edit_department(user, checklist.department_id)

    name = checklist.name
    db.delete(checklist)
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="체크리스트_삭제",
        target_type="checklist",
        target_id=checklist_id,
        summary=name,
    )
    return redirect(f"/checklists?retreat_id={retreat.id}", message="체크리스트를 삭제했습니다.")
