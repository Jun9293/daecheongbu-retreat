"""알림함 + 웹 푸시 구독."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app import notifications as notify_service
from app import push as push_service
from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.models import Retreat, User
from app.security import get_current_user, require_admin
from app.templating import redirect, render

router = APIRouter()


@router.get("/notifications")
def notification_box(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    retreats = all_retreats(db)
    retreat = get_current_retreat(request, db, user) if retreats else None
    return render(
        request,
        "notifications.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": retreats,
            "notifications": notify_service.recent_notifications(db, user),
            "push_public_key": push_service.application_server_key(),
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count = notify_service.mark_all_read(db, user)
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
