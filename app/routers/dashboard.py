"""로그인 후 첫 화면 — 내 부서 오늘 할 일 중심."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat
from app.domain.budget import build_budget_summary
from app.domain.dependencies import blocking_tasks
from app.models import (
    Checklist,
    FileAsset,
    Meeting,
    Retreat,
    ScheduleDay,
    Task,
    User,
)
from app.security import get_current_user
from app.templating import render

router = APIRouter()


@router.get("/more")
def more_menu(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """모바일 하단바에 다 넣을 수 없는 화면들을 모은 허브."""
    retreats = all_retreats(db)
    if not retreats:
        return render(request, "no_retreat.html", {"user": user})

    retreat = get_current_retreat(request, db, user)
    counts = {
        "files": len(
            db.scalars(select(FileAsset).where(FileAsset.retreat_id == retreat.id)).all()
        ),
        "checklists": len(
            db.scalars(select(Checklist).where(Checklist.retreat_id == retreat.id)).all()
        ),
        "meetings": len(
            db.scalars(
                select(Meeting).where(
                    (Meeting.retreat_id == retreat.id) | (Meeting.retreat_id.is_(None))
                )
            ).all()
        ),
    }
    return render(
        request,
        "more.html",
        {"user": user, "retreat": retreat, "retreats": retreats, "counts": counts},
    )


# 새 준비 단계 보드가 홈이 됐다. 기존 대시보드는 /dashboard 로 옮겼다.
@router.get("/dashboard")
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

    # Phase 2: 선행 작업에 막힌 할 일 / 나에게 온 확인 요청
    tasks_by_id = {t.id: t for t in tasks}
    blocked_mine = [
        (task, blocking_tasks(task, tasks_by_id))
        for task in my_open
        if blocking_tasks(task, tasks_by_id)
    ]
    startable_mine = [
        task
        for task in my_open
        if task.blocked_by_task_ids and not blocking_tasks(task, tasks_by_id)
    ]

    from app.routers.reviews import pending_for_user

    pending_reviews = pending_for_user(db, user, retreat)

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
            "blocked_mine": blocked_mine,
            "startable_mine": startable_mine,
            "pending_reviews": pending_reviews,
            "summary": summary,
            "today_day": today_day,
            "stats": {
                "total": len(tasks),
                "done": len([t for t in tasks if t.status == "완료"]),
                "open": len([t for t in tasks if t.status in open_statuses]),
            },
        },
    )
