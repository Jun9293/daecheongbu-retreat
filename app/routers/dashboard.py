"""로그인 후 첫 화면 — 내 부서 오늘 할 일 중심."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat
from app.domain.budget import build_budget_summary
from app.models import Retreat, ScheduleDay, Task, User
from app.security import get_current_user
from app.templating import render

router = APIRouter()


@router.get("/")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    retreats = all_retreats(db)
    if not retreats:
        return render(request, "no_retreat.html", {"user": user})

    retreat: Retreat = get_current_retreat(request, db, user)
    today = dt.date.today()

    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.retreat_id == retreat.id)
            .order_by(Task.due_date.is_(None), Task.due_date, Task.id)
        )
    )

    def is_mine(task: Task) -> bool:
        return task.assignee_id == user.id or (
            user.department_id is not None and task.department_id == user.department_id
        )

    open_statuses = ("대기", "진행중", "피드백요청", "지연")
    my_open = [t for t in tasks if is_mine(t) and t.status in open_statuses]

    my_today = [t for t in my_open if t.due_date is not None and t.due_date <= today]
    my_week = [
        t
        for t in my_open
        if t.due_date is not None and today < t.due_date <= today + dt.timedelta(days=7)
    ]
    my_undated = [t for t in my_open if t.due_date is None]

    # 구멍 방지: 담당자 없이 기한이 임박한 할 일은 전체에 드러낸다.
    unassigned_soon = [
        t
        for t in tasks
        if t.assignee_id is None
        and t.status in open_statuses
        and t.due_date is not None
        and t.due_date <= today + dt.timedelta(days=7)
    ]
    overdue_all = [
        t
        for t in tasks
        if t.status in open_statuses and t.due_date is not None and t.due_date < today
    ]

    summary = build_budget_summary(db, retreat=retreat)

    days = list(
        db.scalars(
            select(ScheduleDay)
            .where(ScheduleDay.retreat_id == retreat.id)
            .order_by(ScheduleDay.sort_order, ScheduleDay.id)
        )
    )
    today_day = next((d for d in days if d.date == today), None)

    return render(
        request,
        "dashboard.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": retreats,
            "my_today": my_today,
            "my_week": my_week,
            "my_undated": my_undated,
            "unassigned_soon": unassigned_soon,
            "overdue_all": overdue_all,
            "summary": summary,
            "today_day": today_day,
            "stats": {
                "total": len(tasks),
                "done": len([t for t in tasks if t.status == "완료"]),
                "open": len([t for t in tasks if t.status in open_statuses]),
            },
        },
    )
