"""알림 서비스 — 누구에게 알릴지 정하고, 앱 알림함에 남기고, 웹 푸시로 보낸다.

푸시는 실패할 수 있으므로(구독 안 함, 브라우저 종료, 만료된 구독) 알림은 항상
DB에 먼저 남긴다. 사용자는 앱을 열면 알림함에서 다시 확인할 수 있다.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import permissions as perm
from app.domain.escalation import Risk, scan_risks, tasks_to_mark_delayed
from app.models import Notification, Retreat, Task, User

logger = logging.getLogger("dcb.notify")

RISK_TITLES = {
    "지연": "⚠️ 기한이 지났습니다",
    "기한임박": "🔔 마감이 다가옵니다",
    "담당자미지정": "❗ 담당자가 없습니다",
    "선행지연": "⛔ 선행 작업이 지연됐습니다",
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


# ---------------------------------------------------------------- 수신자 결정


def recipients_for_risk(db: Session, risk: Risk) -> list[User]:
    """위험 하나에 대해 알림을 받아야 할 사람들.

    - 담당자 (지정되어 있으면)
    - 같은 부서의 편집 권한자 전원 (담당자가 자리를 비워도 부서가 알도록)
    - 에스컬레이션 대상이거나 부서가 없으면 총무팀 전원
    """
    task = risk.task
    users: dict[int, User] = {}

    def add(user: User | None) -> None:
        if user is None or not user.is_active:
            return
        if perm.is_readonly(user.role):  # 열람 전용에게는 보내지 않는다
            return
        users[user.id] = user

    if task.assignee_id is not None:
        add(db.get(User, task.assignee_id))

    if task.department_id is not None:
        for user in db.scalars(select(User).where(User.department_id == task.department_id)):
            add(user)

    if risk.escalate_to_admin or task.department_id is None:
        for user in db.scalars(select(User).where(User.role == perm.ADMIN)):
            add(user)

    return list(users.values())


def department_members(db: Session, department_id: int) -> list[User]:
    return [
        user
        for user in db.scalars(
            select(User).where(User.department_id == department_id, User.is_active)
        )
        if not perm.is_readonly(user.role)
    ]


def admins(db: Session) -> list[User]:
    return list(
        db.scalars(select(User).where(User.role == perm.ADMIN, User.is_active))
    )


# ---------------------------------------------------------------- 알림 생성


def notify(
    db: Session,
    *,
    users: list[User],
    retreat_id: int | None,
    kind: str,
    title: str,
    dedupe_key: str,
    body: str | None = None,
    link: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    exclude_user_id: int | None = None,
) -> list[Notification]:
    """알림을 만든다. 같은 사용자에게 같은 dedupe_key면 다시 만들지 않는다."""
    created: list[Notification] = []
    # 담당자와 부서원 목록이 겹칠 수 있으므로 먼저 중복을 제거한다
    # (안 하면 같은 (user_id, dedupe_key) 가 두 번 들어가 UNIQUE 제약을 위반한다)
    unique_users = list({user.id: user for user in users}.values())

    for user in unique_users:
        if exclude_user_id is not None and user.id == exclude_user_id:
            continue  # 본인이 한 행동을 본인에게 알리지 않는다
        exists = db.scalars(
            select(Notification).where(
                Notification.user_id == user.id, Notification.dedupe_key == dedupe_key
            )
        ).first()
        if exists is not None:
            continue
        notification = Notification(
            user_id=user.id,
            retreat_id=retreat_id,
            kind=kind,
            title=title,
            body=body,
            link=link,
            target_type=target_type,
            target_id=target_id,
            dedupe_key=dedupe_key,
        )
        db.add(notification)
        created.append(notification)

    if created:
        db.commit()
        _try_push(db, created)
    return created


def _try_push(db: Session, notifications: list[Notification]) -> None:
    """웹 푸시 발송 시도. 실패해도 앱 알림함에는 이미 남아 있으므로 무시한다."""
    try:
        from app.push import push_notifications

        push_notifications(db, notifications)
    except Exception:  # pragma: no cover - 푸시 실패가 본 기능을 막으면 안 된다
        logger.exception("웹 푸시 발송 실패 (앱 알림함에는 정상 저장됨)")


def unread_count(db: Session, user: User) -> int:
    return len(
        db.scalars(
            select(Notification).where(
                Notification.user_id == user.id, Notification.read_at.is_(None)
            )
        ).all()
    )


def recent_notifications(db: Session, user: User, limit: int = 50) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.id.desc())
            .limit(limit)
        )
    )


def mark_read(db: Session, user: User, notification_id: int) -> None:
    notification = db.get(Notification, notification_id)
    if notification is not None and notification.user_id == user.id:
        notification.read_at = _now()
        db.commit()


def mark_all_read(db: Session, user: User) -> int:
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id, Notification.read_at.is_(None)
        )
    ).all()
    for row in rows:
        row.read_at = _now()
    db.commit()
    return len(rows)


# ---------------------------------------------------------------- 전체 스캔


def run_risk_scan(
    db: Session, *, retreat: Retreat, today: dt.date | None = None
) -> int:
    """회차 전체를 훑어 위험을 찾아 알림을 만든다.

    - 기한이 지난 할 일은 상태를 '지연'으로 자동 전환
    - 감지된 위험마다 담당자·부서·(필요 시) 총무팀에게 알림
    반환값: 새로 만들어진 알림 수
    """
    today = today or dt.date.today()
    tasks = list(db.scalars(select(Task).where(Task.retreat_id == retreat.id)))

    for task in tasks_to_mark_delayed(tasks, today=today):
        task.status = "지연"
    db.commit()

    created = 0
    for risk in scan_risks(tasks, today=today):
        users = recipients_for_risk(db, risk)
        if not users:
            continue
        title = RISK_TITLES.get(risk.kind, "알림")
        created += len(
            notify(
                db,
                users=users,
                retreat_id=retreat.id,
                kind=risk.kind,
                title=f"{title} · {risk.task.title}",
                body=risk.message,
                link=f"/tasks?retreat_id={retreat.id}",
                target_type="task",
                target_id=risk.task.id,
                dedupe_key=risk.dedupe_key,
            )
        )
    return created
