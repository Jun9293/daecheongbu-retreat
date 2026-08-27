"""일정(ScheduleDay / ScheduleItem) 관리."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.models import Department, Retreat, ScheduleDay, ScheduleItem, Task, User
from app.security import get_current_user, require_editor
from app.templating import redirect, render

router = APIRouter(prefix="/schedule")


def _parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    return dt.date.fromisoformat(raw)


def _owned_day(db: Session, day_id: int, retreat: Retreat) -> ScheduleDay:
    day = db.get(ScheduleDay, day_id)
    if day is None or day.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="일자를 찾을 수 없습니다.")
    return day


def _hour_of(item: ScheduleItem) -> str:
    """정렬·그룹핑용 시각. 시간이 없으면 맨 뒤로 보낸다."""
    if not item.start_time:
        return "--"
    return item.start_time[:2]


@router.get("")
def schedule_page(
    request: Request,
    day_id: int | None = None,
    dept: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    days = list(
        db.scalars(
            select(ScheduleDay)
            .where(ScheduleDay.retreat_id == retreat.id)
            .order_by(ScheduleDay.sort_order, ScheduleDay.id)
        )
    )
    today = dt.date.today()
    current = None
    if days:
        if day_id is not None:
            current = next((d for d in days if d.id == day_id), days[0])
        else:
            current = next((d for d in days if d.date == today), days[0])

    departments = list(
        db.scalars(
            select(Department)
            .where(Department.retreat_id == retreat.id)
            .order_by(Department.sort_order, Department.id)
        )
    )

    items = list(current.items) if current is not None else []

    # 부서 필터 — '내 부서'와 '공통 일정'은 함께 보여야 의미가 있다
    if dept == "mine" and user.department_id:
        items = [i for i in items if i.department_id in (None, user.department_id)]
    elif dept.isdigit():
        picked = int(dept)
        items = [i for i in items if i.department_id in (None, picked)]

    # 시각별로 묶어 타임라인으로 표시
    hours: dict[str, list[ScheduleItem]] = {}
    for item in items:
        hours.setdefault(_hour_of(item), []).append(item)
    for bucket in hours.values():
        # 시각 우선, 같은 시각이면 공통 일정을 부서 업무보다 위에
        bucket.sort(key=lambda i: (i.start_time or "", i.department_id is not None, i.id))
    timeline = sorted(hours.items(), key=lambda kv: (kv[0] == "--", kv[0]))

    tasks_by_item: dict[int, list[Task]] = {}
    if items:
        for task in db.scalars(
            select(Task).where(Task.schedule_item_id.in_([i.id for i in items]))
        ):
            tasks_by_item.setdefault(task.schedule_item_id, []).append(task)

    dept_counts = {d.id: 0 for d in departments}
    common_count = 0
    for item in (current.items if current is not None else []):
        if item.department_id is None:
            common_count += 1
        elif item.department_id in dept_counts:
            dept_counts[item.department_id] += 1

    return render(
        request,
        "schedule.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "days": days,
            "current_day": current,
            "timeline": timeline,
            "shown_count": len(items),
            "total_count": len(current.items) if current is not None else 0,
            "common_count": common_count,
            "dept_counts": dept_counts,
            "tasks_by_item": tasks_by_item,
            "departments": departments,
            "dept_filter": dept,
            "now_hour": dt.datetime.now().strftime("%H"),
            "is_today": current is not None and current.date == today,
        },
    )


@router.post("/days")
def create_day(
    label: str = Form(...),
    date: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    max_order = (
        db.scalar(
            select(func.max(ScheduleDay.sort_order)).where(
                ScheduleDay.retreat_id == retreat.id
            )
        )
        or 0
    )
    day = ScheduleDay(
        retreat_id=retreat.id,
        label=label.strip(),
        date=_parse_date(date),
        sort_order=max_order + 1,
    )
    db.add(day)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="일자_추가",
        target_type="schedule_day",
        target_id=day.id,
        summary=day.label,
    )
    return redirect(
        f"/schedule?retreat_id={retreat.id}&day_id={day.id}", message="일자를 추가했습니다."
    )


@router.post("/days/{day_id}/delete")
def delete_day(
    day_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    day = _owned_day(db, day_id, retreat)
    label = day.label
    db.delete(day)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="일자_삭제",
        target_type="schedule_day",
        target_id=day_id,
        summary=label,
    )
    return redirect(f"/schedule?retreat_id={retreat.id}", message="일자를 삭제했습니다.")


@router.post("/days/{day_id}/items")
def create_item(
    day_id: int,
    title: str = Form(...),
    start_time: str = Form(""),
    end_time: str = Form(""),
    location: str = Form(""),
    department_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    day = _owned_day(db, day_id, retreat)
    item = ScheduleItem(
        schedule_day_id=day.id,
        title=title.strip(),
        start_time=start_time or None,
        end_time=end_time or None,
        location=location.strip() or None,
        department_id=int(department_id) if department_id else None,
    )
    db.add(item)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="일정_추가",
        target_type="schedule_item",
        target_id=item.id,
        summary=f"{day.label} · {item.title}",
    )
    return redirect(
        f"/schedule?retreat_id={retreat.id}&day_id={day.id}", message="일정을 추가했습니다."
    )


@router.post("/items/{item_id}/delete")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    item = db.get(ScheduleItem, item_id)
    if item is None or item.day.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다.")
    day_id = item.schedule_day_id
    title = item.title
    db.delete(item)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="일정_삭제",
        target_type="schedule_item",
        target_id=item_id,
        summary=title,
    )
    return redirect(
        f"/schedule?retreat_id={retreat.id}&day_id={day_id}", message="일정을 삭제했습니다."
    )
