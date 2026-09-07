"""부서 간 확인 요청 — 요청 보내기 / 승인·반려."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import notifications as notify_service
from app.db import get_db
from app.deps import get_current_retreat, log_activity
from app.models import (
    REVIEW_STATUSES,
    Department,
    FileAsset,
    Retreat,
    ReviewRequest,
    Task,
    User,
)
from app.security import require_editor
from app.templating import redirect

router = APIRouter()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def pending_for_user(db: Session, user: User, retreat: Retreat) -> list[ReviewRequest]:
    """나에게(= 내 부서에) 온 대기 중인 확인 요청.

    **부서는 키로 비교한다** (2장). 요청의 department_id 는 이번 회차 행이고
    User.department_id 는 계정을 만들 때의 회차 행이라, id 로 견주면 새 회차가
    열리는 순간 배지·답 버튼이 조용히 사라진다.
    """
    from app.domain.departments import department_key_of

    if user.department_id is None:
        if user.role != "admin":
            return []
        query = select(ReviewRequest).where(
            ReviewRequest.retreat_id == retreat.id, ReviewRequest.status == "대기"
        )
    else:
        my_key = department_key_of(db, user)
        base = select(ReviewRequest).where(
            ReviewRequest.retreat_id == retreat.id,
            ReviewRequest.status == "대기",
        )
        if my_key:
            query = base.join(
                Department, Department.id == ReviewRequest.department_id
            ).where(Department.key == my_key)
        else:
            # 키 없는 부서(구설계 데이터)는 행으로만 — can_respond_to 와 같은 결
            query = base.where(ReviewRequest.department_id == user.department_id)
    return list(db.scalars(query.order_by(ReviewRequest.id.desc())))


def can_respond_to(db: Session, user: User, review: ReviewRequest) -> bool:
    """요청받은 부서(키로 — 2장)와 총무팀만 답한다. 화면의 답 버튼과
    respond 엔드포인트가 **같은 판정**을 쓴다 — 갈리면 버튼은 뜨는데 403 이 난다.

    키 없는 부서(구설계 데이터)는 키를 넓힐 근거가 없으므로 행(id)으로만
    본다 — None == None 으로 남의 부서까지 통과시키면 안 된다.
    """
    from app.domain.departments import department_key_of

    if user.role == "admin":
        return True
    target = review.department
    if target is None:
        return False
    if target.key:
        return department_key_of(db, user) == target.key
    return user.department_id == target.id


@router.get("/reviews")
def old_review_box():
    """옛 확인 요청함 — 알림으로 합쳤다 (4-16). 보낸 것 탭으로 잇는다."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/notifications?tab=sent", status_code=301)


def create_review_requests(
    db: Session,
    *,
    retreat: Retreat,
    requester: User,
    department_ids: list[int],
    message: str,
    task: Task | None = None,
    run=None,
    file_asset: FileAsset | None = None,
) -> list[ReviewRequest]:
    """관련 부서들에 확인 요청을 만들고 해당 부서원에게 알린다.

    새 요청은 업무(run)를 가리킨다 (4-9) — task_id 는 옛 Task 표 FK 라
    새로 쓰지 않는다. 답하는 자리는 알림함이다 (4-16).
    """
    if run is not None:
        subject = run.library.title
    elif task is not None:
        subject = task.title
    else:
        subject = file_asset.title if file_asset else ""
    link = f"/notifications?retreat_id={retreat.id}"
    created: list[ReviewRequest] = []

    for department_id in department_ids:
        department = db.get(Department, department_id)
        if department is None or department.retreat_id != retreat.id:
            continue

        review = ReviewRequest(
            retreat_id=retreat.id,
            task_id=task.id if task is not None else None,
            run_id=run.id if run is not None else None,
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
            f"/notifications?retreat_id={retreat.id}", message="이미 처리된 요청입니다."
        )

    # 요청받은 부서만 응답할 수 있다 (총무팀은 전체 가능) — 키로 (2장)
    if not can_respond_to(db, user, review):
        raise HTTPException(status_code=403, detail="요청받은 부서만 답할 수 있습니다.")

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
            link=f"/notifications?retreat_id={retreat.id}",
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
    return redirect(f"/notifications?retreat_id={retreat.id}", message=f"{decision} 처리했습니다.")


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
    return redirect(f"/notifications?tab=sent&retreat_id={retreat.id}", message="확인 요청을 취소했습니다.")


ALL_REVIEW_STATUSES = REVIEW_STATUSES
