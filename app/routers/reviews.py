"""부서 간 확인 요청 — 요청 보내기 / 승인·반려."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import notifications as notify_service
from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.models import (
    REVIEW_STATUSES,
    Department,
    FileAsset,
    Retreat,
    ReviewRequest,
    Task,
    User,
)
from app.security import assert_can_edit_department, get_current_user, require_editor
from app.templating import redirect, render

router = APIRouter()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def pending_for_user(db: Session, user: User, retreat: Retreat) -> list[ReviewRequest]:
    """나에게(= 내 부서에) 온 대기 중인 확인 요청."""
    if user.department_id is None:
        if user.role != "admin":
            return []
        query = select(ReviewRequest).where(
            ReviewRequest.retreat_id == retreat.id, ReviewRequest.status == "대기"
        )
    else:
        query = select(ReviewRequest).where(
            ReviewRequest.retreat_id == retreat.id,
            ReviewRequest.status == "대기",
            ReviewRequest.department_id == user.department_id,
        )
    return list(db.scalars(query.order_by(ReviewRequest.id.desc())))


@router.get("/reviews")
def review_box(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    incoming = pending_for_user(db, user, retreat)
    outgoing = list(
        db.scalars(
            select(ReviewRequest)
            .where(
                ReviewRequest.retreat_id == retreat.id,
                ReviewRequest.requester_id == user.id,
            )
            .order_by(ReviewRequest.id.desc())
        )
    )
    answered = list(
        db.scalars(
            select(ReviewRequest)
            .where(
                ReviewRequest.retreat_id == retreat.id,
                ReviewRequest.status != "대기",
            )
            .order_by(ReviewRequest.id.desc())
            .limit(30)
        )
    )
    return render(
        request,
        "reviews.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "incoming": incoming,
            "outgoing": outgoing,
            "answered": answered,
        },
    )


def create_review_requests(
    db: Session,
    *,
    retreat: Retreat,
    requester: User,
    department_ids: list[int],
    message: str,
    task: Task | None = None,
    file_asset: FileAsset | None = None,
) -> list[ReviewRequest]:
    """관련 부서들에 확인 요청을 만들고 해당 부서원에게 알린다."""
    subject = task.title if task is not None else (file_asset.title if file_asset else "")
    link = f"/reviews?retreat_id={retreat.id}"
    created: list[ReviewRequest] = []

    for department_id in department_ids:
        department = db.get(Department, department_id)
        if department is None or department.retreat_id != retreat.id:
            continue

        review = ReviewRequest(
            retreat_id=retreat.id,
            task_id=task.id if task is not None else None,
            file_asset_id=file_asset.id if file_asset is not None else None,
            department_id=department_id,
            requester_id=requester.id,
            requester_name=requester.name,
            message=message.strip() or None,
        )
        db.add(review)
        db.commit()
        created.append(review)

        recipients = notify_service.department_members(db, department_id)
        notify_service.notify(
            db,
            users=recipients,
            retreat_id=retreat.id,
            kind="확인요청",
            title=f"📩 확인 요청 · {subject}",
            body=f"{requester.name}님이 {department.name}에 확인을 요청했습니다."
            + (f" — {message.strip()}" if message.strip() else ""),
            link=link,
            target_type="review",
            target_id=review.id,
            dedupe_key=f"review:{review.id}",
            exclude_user_id=requester.id,
        )
    return created


@router.post("/reviews/{review_id}/respond")
def respond(
    review_id: int,
    decision: str = Form(...),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    review = db.get(ReviewRequest, review_id)
    if review is None or review.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="확인 요청을 찾을 수 없습니다.")
    if decision not in ("승인", "반려"):
        raise HTTPException(status_code=400, detail="승인 또는 반려만 가능합니다.")
    if review.status != "대기":
        return redirect(
            f"/reviews?retreat_id={retreat.id}", message="이미 처리된 요청입니다."
        )

    # 요청받은 부서만 응답할 수 있다 (총무팀은 전체 가능)
    assert_can_edit_department(user, review.department_id)

    subject = review.subject
    review.status = decision
    review.responder_id = user.id
    review.responder_name = user.name
    review.response_comment = comment.strip() or None
    review.responded_at = _now()

    # 파일에 대한 요청이면 파일 상태도 함께 반영한다
    if review.file_asset is not None:
        review.file_asset.status = "승인" if decision == "승인" else "반려"
        review.file_asset.updated_at = _now()
    db.commit()

    requester = db.get(User, review.requester_id) if review.requester_id else None
    if requester is not None:
        icon = "✅" if decision == "승인" else "↩️"
        notify_service.notify(
            db,
            users=[requester],
            retreat_id=retreat.id,
            kind="확인결과",
            title=f"{icon} {decision} · {subject}",
            body=f"{user.name}님이 {decision}했습니다."
            + (f" — {comment.strip()}" if comment.strip() else ""),
            link=f"/reviews?retreat_id={retreat.id}",
            target_type="review",
            target_id=review.id,
            dedupe_key=f"review-result:{review.id}",
        )

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="확인요청_응답",
        target_type="review",
        target_id=review.id,
        summary=f"{subject}: {decision}",
    )
    return redirect(f"/reviews?retreat_id={retreat.id}", message=f"{decision} 처리했습니다.")


@router.post("/reviews/{review_id}/cancel")
def cancel(
    review_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    review = db.get(ReviewRequest, review_id)
    if review is None or review.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="확인 요청을 찾을 수 없습니다.")
    if review.requester_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="요청한 본인만 취소할 수 있습니다.")

    db.delete(review)
    db.commit()
    return redirect(f"/reviews?retreat_id={retreat.id}", message="확인 요청을 취소했습니다.")


ALL_REVIEW_STATUSES = REVIEW_STATUSES
