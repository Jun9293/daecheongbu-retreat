"""할 일(Task) 관리."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import notifications as notify_service
from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.domain.dependencies import (
    CycleError,
    blocking_tasks,
    build_blocker_map,
    is_blocked,
    newly_unblocked,
    validate_blockers,
)
from app.models import (
    TASK_STATUSES,
    Department,
    Retreat,
    ReviewRequest,
    ScheduleItem,
    Task,
    User,
)
from app.routers.reviews import create_review_requests
from app.security import assert_can_edit_department, get_current_user, require_editor
from app.templating import redirect, render

router = APIRouter(prefix="/tasks")


def _all_tasks(db: Session, retreat: Retreat) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.retreat_id == retreat.id)))


def _parse_ids(raw: list[str] | None) -> list[int]:
    return [int(value) for value in (raw or []) if str(value).strip().isdigit()]


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

    all_tasks = _all_tasks(db, retreat)
    tasks_by_id = {task.id: task for task in all_tasks}
    blockers_by_task = {task.id: blocking_tasks(task, tasks_by_id) for task in tasks}

    reviews_by_task: dict[int, list[ReviewRequest]] = {}
    for review in db.scalars(
        select(ReviewRequest).where(
            ReviewRequest.retreat_id == retreat.id, ReviewRequest.task_id.isnot(None)
        )
    ):
        reviews_by_task.setdefault(review.task_id, []).append(review)

    return render(
        request,
        "tasks.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "tasks": tasks,
            "all_tasks": all_tasks,
            "blockers_by_task": blockers_by_task,
            "reviews_by_task": reviews_by_task,
            "departments": _departments(db, retreat),
            "members": _members(db),
            "statuses": TASK_STATUSES,
            "scope": scope,
            "status_filter": status,
            "department_filter": department_id,
            # 새 할 일 만들기 폼에서 쓰는 목록 (셀렉트 하나뿐이라 부담 없음)
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


@router.get("/{task_id}")
def task_detail(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """할 일 상세.

    선행 작업 선택지는 회차 전체 할 일이라 목록 화면에 매 행마다 그리면
    페이지가 수 MB 로 불어난다. 그래서 상세 화면에서만 그린다.
    """
    task = db.get(Task, task_id)
    if task is None or task.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")

    all_tasks = _all_tasks(db, retreat)
    tasks_by_id = {t.id: t for t in all_tasks}

    return render(
        request,
        "task_detail.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "task": task,
            "all_tasks": [t for t in all_tasks if t.id != task.id],
            "blockers": blocking_tasks(task, tasks_by_id),
            "followers": [
                t for t in all_tasks if task.id in (t.blocked_by_task_ids or [])
            ],
            "reviews": list(
                db.scalars(
                    select(ReviewRequest).where(ReviewRequest.task_id == task.id)
                )
            ),
            "departments": _departments(db, retreat),
            "members": _members(db),
            "statuses": TASK_STATUSES,
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
    _notify_assignee(db, retreat=retreat, task=task, actor=user)
    return redirect(f"/tasks?retreat_id={retreat.id}", message="할 일을 추가했습니다.")


def _notify_assignee(db: Session, *, retreat: Retreat, task: Task, actor: User) -> None:
    """담당자로 지정된 사람에게 알린다 (본인이 스스로 지정한 경우는 제외)."""
    if not task.assignee_id:
        return
    assignee = db.get(User, task.assignee_id)
    if assignee is None:
        return
    due = f" (기한 {task.due_date})" if task.due_date else ""
    notify_service.notify(
        db,
        users=[assignee],
        retreat_id=retreat.id,
        kind="할일배정",
        title=f"📋 담당자로 지정됐습니다 · {task.title}",
        body=f"{actor.name}님이 배정했습니다.{due}",
        link=f"/tasks?retreat_id={retreat.id}",
        target_type="task",
        target_id=task.id,
        dedupe_key=f"task-assigned:{task.id}:{task.assignee_id}",
        exclude_user_id=actor.id,
    )


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

    message = "상태를 변경했습니다."
    if status == "완료" and before != "완료":
        released = _release_followers(db, retreat=retreat, task=task, actor=user)
        if released:
            names = ", ".join(t.title for t in released)
            message = f"완료 처리했습니다. 이어서 시작할 수 있는 작업: {names}"

    sep = "&" if "?" in redirect_to else "?"
    return redirect(f"{redirect_to}{sep}retreat_id={retreat.id}", message=message)


def _release_followers(
    db: Session, *, retreat: Retreat, task: Task, actor: User
) -> list[Task]:
    """선행 작업이 완료되어 '시작 가능'이 된 후행 작업의 담당자에게 알린다."""
    released = newly_unblocked(completed_task_id=task.id, tasks=_all_tasks(db, retreat))
    for follower in released:
        recipients = []
        if follower.assignee_id:
            assignee = db.get(User, follower.assignee_id)
            if assignee is not None:
                recipients.append(assignee)
        if follower.department_id:
            recipients.extend(notify_service.department_members(db, follower.department_id))
        if not recipients:
            recipients = notify_service.admins(db)

        notify_service.notify(
            db,
            users=recipients,
            retreat_id=retreat.id,
            kind="시작가능",
            title=f"▶ 시작할 수 있습니다 · {follower.title}",
            body=f"선행 작업 '{task.title}'이(가) 완료되었습니다.",
            link=f"/tasks?retreat_id={retreat.id}",
            target_type="task",
            target_id=follower.id,
            dedupe_key=f"unblocked:{follower.id}:{task.id}",
        )
        log_activity(
            db,
            retreat_id=retreat.id,
            actor=actor,
            action="선행완료_시작가능",
            target_type="task",
            target_id=follower.id,
            summary=f"{follower.title} ← {task.title} 완료",
        )
    return released


@router.post("/{task_id}/blockers")
def set_blockers(
    task_id: int,
    blocker_ids: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    """선행 작업 지정. 순환 참조는 거부한다."""
    task = db.get(Task, task_id)
    if task is None or task.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")
    assert_can_edit_department(user, task.department_id)

    ids = _parse_ids(blocker_ids)
    all_tasks = _all_tasks(db, retreat)
    valid_ids = {t.id for t in all_tasks}
    ids = [i for i in ids if i in valid_ids]

    try:
        validate_blockers(
            task_id=task.id, blocker_ids=ids, blocker_map=build_blocker_map(all_tasks)
        )
    except CycleError as exc:
        return redirect(f"/tasks?retreat_id={retreat.id}", message=f"⚠️ {exc}")

    task.blocked_by_task_ids = ids
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="선행작업_지정",
        target_type="task",
        target_id=task.id,
        summary=f"{task.title} ← 선행 {len(ids)}건",
    )
    note = "선행 작업을 저장했습니다."
    if ids and not is_blocked(task, {t.id: t for t in all_tasks}):
        note = "선행 작업을 저장했습니다. 선행이 모두 완료되어 바로 시작할 수 있습니다."
    return redirect(f"/tasks?retreat_id={retreat.id}", message=note)


@router.post("/{task_id}/review-request")
def request_review(
    task_id: int,
    department_ids: list[int] = Form(default=[]),
    message: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    """관련 부서에 확인 요청을 보낸다."""
    task = db.get(Task, task_id)
    if task is None or task.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")
    assert_can_edit_department(user, task.department_id)

    if not department_ids:
        return redirect(
            f"/tasks?retreat_id={retreat.id}", message="확인을 요청할 부서를 선택해주세요."
        )

    created = create_review_requests(
        db,
        retreat=retreat,
        requester=user,
        department_ids=department_ids,
        message=message,
        task=task,
    )
    task.related_department_ids = sorted(
        set((task.related_department_ids or []) + [r.department_id for r in created])
    )
    task.status = "피드백요청"
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="할일_확인요청",
        target_type="task",
        target_id=task.id,
        summary=f"{task.title} → {len(created)}개 부서",
    )
    return redirect(
        f"/tasks?retreat_id={retreat.id}", message=f"{len(created)}개 부서에 확인을 요청했습니다."
    )


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

    previous_assignee = task.assignee_id
    previous_status = task.status

    task.title = title.strip()
    task.description = description.strip() or None
    task.department_id = new_dept
    task.assignee_id = int(assignee_id) if assignee_id else None
    task.due_date = _parse_date(due_date)
    if status in TASK_STATUSES:
        task.status = status
    db.commit()

    if task.assignee_id and task.assignee_id != previous_assignee:
        _notify_assignee(db, retreat=retreat, task=task, actor=user)
    if task.status == "완료" and previous_status != "완료":
        _release_followers(db, retreat=retreat, task=task, actor=user)
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
