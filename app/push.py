"""웹 푸시(PWA) 발송.

카카오톡 연동 전까지의 알림 수단. 별도 계약·승인 절차 없이 무료로 쓸 수 있다.

주의: 웹 푸시는 브라우저 규격상 **HTTPS 또는 localhost**에서만 동작한다.
같은 와이파이의 다른 기기에서 http://192.168.x.x 로 접속하면 구독 자체가 안 된다.
(운영 배포 시 HTTPS를 붙이면 해결된다. 그 전까지 알림은 앱 알림함에서 확인 가능.)
"""

from __future__ import annotations

import base64
import json
import logging

from cryptography.hazmat.primitives import serialization
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DATA_DIR, PUSH_CONTACT
from app.models import Notification, PushSubscription, User

logger = logging.getLogger("dcb.push")

VAPID_KEY_PATH = DATA_DIR / "vapid_private.pem"

_cached_public_key: str | None = None


def _load_vapid():
    """VAPID 키를 읽고, 없으면 새로 만들어 저장한다."""
    from py_vapid import Vapid01

    if VAPID_KEY_PATH.exists():
        return Vapid01.from_file(str(VAPID_KEY_PATH))

    vapid = Vapid01()
    vapid.generate_keys()
    vapid.save_key(str(VAPID_KEY_PATH))
    logger.warning("새 VAPID 키를 만들었습니다: %s", VAPID_KEY_PATH)
    return vapid


def application_server_key() -> str:
    """브라우저 구독에 필요한 공개키 (base64url)."""
    global _cached_public_key
    if _cached_public_key is None:
        vapid = _load_vapid()
        raw = vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        _cached_public_key = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return _cached_public_key


def save_subscription(
    db: Session, *, user: User, subscription: dict, user_agent: str | None = None
) -> PushSubscription:
    endpoint = subscription["endpoint"]
    keys = subscription.get("keys", {})

    existing = db.scalars(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    ).first()
    if existing is not None:
        existing.user_id = user.id
        existing.p256dh = keys.get("p256dh", "")
        existing.auth = keys.get("auth", "")
        existing.user_agent = (user_agent or "")[:300] or None
        existing.last_failed_at = None
        db.commit()
        return existing

    record = PushSubscription(
        user_id=user.id,
        endpoint=endpoint,
        p256dh=keys.get("p256dh", ""),
        auth=keys.get("auth", ""),
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(record)
    db.commit()
    return record


def delete_subscription(db: Session, *, endpoint: str) -> None:
    record = db.scalars(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    ).first()
    if record is not None:
        db.delete(record)
        db.commit()


def _send_one(subscription: PushSubscription, payload: dict) -> bool:
    """실제 발송. 성공하면 True, 구독이 만료됐으면 False."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=str(VAPID_KEY_PATH),
            vapid_claims={"sub": PUSH_CONTACT},
            ttl=60 * 60 * 24,
            timeout=10,
        )
        return True
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            # 구독이 만료됨 — 정리 대상
            return False
        logger.warning("푸시 발송 실패 (status=%s): %s", status, exc)
        return True  # 일시적 실패는 구독을 지우지 않는다


def push_notifications(db: Session, notifications: list[Notification]) -> int:
    """앱 알림함에 저장된 알림들을 웹 푸시로도 보낸다."""
    if not notifications:
        return 0
    if not VAPID_KEY_PATH.exists():
        _load_vapid()

    sent = 0
    stale: list[str] = []
    for notification in notifications:
        subscriptions = list(
            db.scalars(
                select(PushSubscription).where(
                    PushSubscription.user_id == notification.user_id
                )
            )
        )
        if not subscriptions:
            continue

        payload = {
            "title": notification.title,
            "body": notification.body or "",
            "link": notification.link or "/notifications",
            "tag": notification.dedupe_key,
        }
        delivered = False
        for subscription in subscriptions:
            if _send_one(subscription, payload):
                delivered = True
            else:
                stale.append(subscription.endpoint)
        if delivered:
            notification.pushed = True
            sent += 1

    for endpoint in stale:
        delete_subscription(db, endpoint=endpoint)
    if sent:
        db.commit()
    return sent
