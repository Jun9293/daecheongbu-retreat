"""알림함 + 웹 푸시 구독."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import notifications as notify_service
from app import push as push_service
from app.db import get_db
from app.domain import permissions as perm
from app.deps import all_retreats, get_current_retreat, log_activity
from app.models import Retreat, User
from app.security import get_current_user, require_admin
from app.templating import redirect, render

router = APIRouter()


# 사람 발신 = 확인 요청과 그 답 (4-16). 정의는 배지와 한 곳(notifications 서비스)이다.
HUMAN_KINDS = notify_service.HUMAN_KINDS


@router.get("/notifications")
def notification_box(
    request: Request,
    tab: str = "received",
    chip: str = "all",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """알림 — 한 페이지, 탭 둘: 받은 것 / 내가 보낸 요청 (4-16).

    저장 구조는 합치지 않는다 — Review 와 Notification 은 그대로 두고
    화면에서 한 목록으로 만든다. 시각 역순이다.
    """
    from app.models import ReviewRequest
    from app.routers.reviews import can_respond_to

    retreats = all_retreats(db)
    retreat = get_current_retreat(request, db, user) if retreats else None
    if retreat is None:
        return render(request, "no_retreat.html", {"user": user})

    rows = []
    for n in notify_service.recent_notifications(
        db, user, limit=100, retreat_id=retreat.id
    ):
        human = n.kind in HUMAN_KINDS
        review = None
        sender_dept = None
        can_respond = False
        if human and n.target_type == "review" and n.target_id:
            review = db.get(ReviewRequest, n.target_id)
            if review is not None and review.requester_id:
                sender = db.get(User, review.requester_id)
                sender_dept = perm.first_department(sender) if sender else None
            # 요청받은 부서(또는 총무팀)만 답한다 — respond 엔드포인트와
            # **같은 함수**를 쓴다. 부서는 키로 (2장) — id 로 견주면 새 회차가
            # 열리는 순간 버튼이 조용히 사라진다
            can_respond = (
                review is not None
                and n.kind == "확인요청"
                and review.status == "대기"
                and can_respond_to(db, user, review)
            )
        rows.append(
            {
                "n": n,
                "human": human,
                "review": review,
                "sender_dept": sender_dept,
                "can_respond": can_respond,
            }
        )

    if chip == "human":
        rows = [r for r in rows if r["human"]]
    elif chip == "system":
        rows = [r for r in rows if not r["human"]]

    # 답을 기다리는 것 — 배지의 뒷항과 **같은 함수**(pending_for_user)로 센다.
    # 알림 행을 거르는 방식이면 부서 없는 admin 이 배지에는 잡히는데 화면에는
    # 아무것도 안 떠서, 배지와 화면이 서로 다른 말을 한다 (봐둘것 T-c 였던 것).
    from app.routers.reviews import pending_for_user

    pending_reviews = pending_for_user(db, user, retreat)
    if chip == "pending":
        rows = []

    sent = list(
        db.scalars(
            select(ReviewRequest)
            .where(
                ReviewRequest.retreat_id == retreat.id,
                ReviewRequest.requester_id == user.id,
            )
            .order_by(ReviewRequest.id.desc())
        )
    )

    return render(
        request,
        "notifications.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": retreats,
            "tab": "sent" if tab == "sent" else "received",
            "chip": chip,
            "rows": rows,
            "pending_reviews": pending_reviews,
            "sent": sent,
            # 목록 위 줄의 N — read_all 이 실제로 처리하는 범위(이 회차
            # + 회차 없는 것)와 같은 수다. 사이드바 배지의 전 회차 수를 그대로
            # 쓰면 버튼이 (5) 라 말하고 3건만 지운다
            "retreat_unread": notify_service.unread_count(
                db, user, retreat_id=retreat.id
            ),
            # 「많다」 의 경계는 여기 하나다 — 화면에 숫자를 박으면 갈린다
            "many_unread": notify_service.MANY_UNREAD,
            "push_public_key": push_service.application_server_key(),
            "active_tab": "notifications",
            "page_subtitle": "알림",
        },
    )


@router.post("/notifications/{notification_id}/read")
def read_one(
    notification_id: int,
    redirect_to: str = Form("/notifications"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notify_service.mark_read(db, user, notification_id)
    return redirect(redirect_to)


@router.post("/notifications/read-all")
def read_all(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 「모두 읽음」 은 **이 회차의** 내 안 읽은 알림 전부다 (4-16)
    retreat = get_current_retreat(request, db, user) if all_retreats(db) else None
    count = notify_service.mark_all_read(
        db, user, retreat_id=retreat.id if retreat else None
    )
    return redirect("/notifications", message=f"{count}건을 읽음 처리했습니다.")


# ------------------------------------------------------------------ 웹 푸시


@router.get("/push/public-key")
def public_key(_user: User = Depends(get_current_user)):
    return {"key": push_service.application_server_key()}


@router.post("/push/subscribe")
async def subscribe(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = await request.json()
    subscription = payload.get("subscription") or payload
    if not subscription.get("endpoint"):
        return {"ok": False, "error": "구독 정보가 올바르지 않습니다."}

    push_service.save_subscription(
        db,
        user=user,
        subscription=subscription,
        user_agent=request.headers.get("user-agent"),
    )
    return {"ok": True}


@router.post("/push/unsubscribe")
async def unsubscribe(
    request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    payload = await request.json()
    endpoint = payload.get("endpoint")
    if endpoint:
        push_service.delete_subscription(db, endpoint=endpoint)
    return {"ok": True}


@router.post("/push/test")
def send_test_push(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """구독이 실제로 동작하는지 본인에게 보내보는 버튼."""
    import datetime as dt

    stamp = dt.datetime.now().strftime("%H:%M:%S")
    notify_service.notify(
        db,
        users=[user],
        retreat_id=retreat.id,
        kind="테스트",
        title="🔔 알림 테스트",
        body=f"이 알림이 보이면 정상입니다. ({stamp})",
        link="/notifications",
        dedupe_key=f"test:{user.id}:{stamp}",
    )
    return redirect("/notifications", message="테스트 알림을 보냈습니다.")


# ------------------------------------------------------------------ 수동 점검


@router.post("/risk-scan")
def manual_scan(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    created = notify_service.run_risk_scan(db, retreat=retreat)
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="위험_점검",
        target_type="retreat",
        target_id=retreat.id,
        summary=f"알림 {created}건 생성",
    )
    message = (
        f"점검 완료 — 새 알림 {created}건" if created else "점검 완료 — 새로 발견된 위험 없음"
    )
    return redirect(f"/notifications?retreat_id={retreat.id}", message=message)
