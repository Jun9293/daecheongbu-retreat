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

# 「안 읽은 것이 많다」 의 경계 (4-16). 이만큼 넘으면 알림 화면 맨 위의
# 「모두 읽음」 줄을 크게 낸다 — 첫 화면이 밀린 목록으로 보이면 사람은 그
# 화면을 다시 안 열기 때문이다. 값은 여기 하나이고 화면이 받아 쓴다.
MANY_UNREAD = 50

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
        if perm.is_readonly(user):  # 열람 전용에게는 보내지 않는다
            return
        users[user.id] = user

    if task.assignee_id is not None:
        add(db.get(User, task.assignee_id))

    if task.department_id is not None:
        # 부서는 키로 넓혀 찾는다 (2장) — department_members 가 그 일을 한다
        for user in department_members(db, task.department_id):
            add(user)

    if risk.escalate_to_admin or task.department_id is None:
        for user in perm.admins(db):
            add(user)

    return list(users.values())


def department_members(db: Session, department_id: int) -> list[User]:
    """그 부서의 (알림 받을) 사람들 — **키로 넓혀서** 찾는다 (2장).

    User.department_id 는 계정을 만들 때의 회차 행을 가리킨다. 요청의
    department_id 는 이번 회차 행이라, id 로만 찾으면 새 회차가 열리는 순간
    옛 회차 소속 사람들이 조용히 빠진다 — 아무 오류도 나지 않고 알림이 안 간다.
    """
    from app.models import Department

    dept = db.get(Department, department_id)
    if dept is None or not dept.key:
        # 키 없는 부서(구설계 데이터)는 넓힐 근거가 없다 — 소속 줄도 키로만 본다
        return []
    return [
        user
        for user in perm.members_of(db, dept.key)
        if not perm.is_readonly(user)
    ]


def admins(db: Session) -> list[User]:
    return perm.admins(db)


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


# 사람 발신 = 확인 요청과 그 답 (4-16). 나머지는 시스템 발신이다.
# 배지(4-0)와 알림 페이지가 같은 목록을 봐야 하므로 여기 한 곳에 둔다.
HUMAN_KINDS = ("확인요청", "확인결과")


def badge_unread_count(db: Session, user: User, retreat_id: int | None = None) -> int:
    """**배지의 앞항과 알림 화면의 「안 읽은 알림 N건」 이 같이 쓰는 하나의 수**
    (UI 정리 판 2 · 4-c) — 안 읽은 시스템 알림 중 내가 들어온 뒤(`first_seen_at`)
    온 것. `retreat_id` 를 주면 그 회차 것(+회차 없는 것)만. 사람 발신은 배지의
    뒷항(답 대기 요청)이 따로 센다.

    두 정의를 배지 쪽으로 합쳤다 — 「내가 들어온 뒤로 온 것」 이 사람이 놓친
    것의 수이고(4-16), 그 전 것은 「모두 읽음」 이 지우되 몇 건인지 줄에 적는다.
    """
    since = getattr(user, "first_seen_at", None)
    if since is None:
        return 0
    query = select(Notification).where(
        Notification.user_id == user.id,
        Notification.read_at.is_(None),
        Notification.kind.not_in(HUMAN_KINDS),
        Notification.created_at >= since,
    )
    if retreat_id is not None:
        query = query.where(
            (Notification.retreat_id == retreat_id) | (Notification.retreat_id.is_(None))
        )
    return len(db.scalars(query).all())


def after_close_unread_count(db: Session, user: User, retreat: Retreat) -> int:
    """수련회가 끝난 뒤(폐회일 다음 날부터) 쌓인 안 읽은 알림 수 (4-b) — 지우지
    않고 몇 건인지 말한다. 끝나지 않았으면 0.

    종류·경계를 안 거르므로 「모두 읽음」 이 지우는 수(unread_count)의 부분집합이다 —
    줄에서는 그 수 뒤에 「그중 …」 으로 붙는다(검토가 짚음: 배지 수의 부분집합은
    아니다). 경계는 폐회 다음 날 0시(UTC naive — 봐둘것 AN-b)."""
    from app.domain import period

    today = dt.date.today()
    if not period.is_over(retreat, today):
        return 0
    edge = dt.datetime.combine((retreat.end_date or retreat.start_date) + dt.timedelta(days=1), dt.time())
    return len(db.scalars(select(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None),
        Notification.retreat_id == retreat.id, Notification.created_at >= edge,
    )).all())


def unread_count(db: Session, user: User, retreat_id: int | None = None) -> int:
    """안 읽은 내 알림 수. retreat_id 를 주면 그 회차 것(+회차 없는 것)만 —
    목록 위 줄이 말하는 N 은 **모두 읽음이 실제로 지우는 범위와 같은 수**
    여야 한다 (4-16). 5건이라 말하고 3건만 지우면 숫자가 거짓말이 된다."""
    query = select(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)
    )
    if retreat_id is not None:
        query = query.where(
            (Notification.retreat_id == retreat_id)
            | (Notification.retreat_id.is_(None))
        )
    return len(db.scalars(query).all())


def recent_notifications(
    db: Session, user: User, limit: int = 50, retreat_id: int | None = None
) -> list[Notification]:
    """내 알림 — retreat_id 를 주면 그 회차 것(+회차 없는 일반 알림)만 (4-16)."""
    query = select(Notification).where(Notification.user_id == user.id)
    if retreat_id is not None:
        query = query.where(
            (Notification.retreat_id == retreat_id) | (Notification.retreat_id.is_(None))
        )
    return list(db.scalars(query.order_by(Notification.id.desc()).limit(limit)))


def mark_read(db: Session, user: User, notification_id: int) -> None:
    notification = db.get(Notification, notification_id)
    if notification is not None and notification.user_id == user.id:
        notification.read_at = _now()
        db.commit()


def mark_all_read(db: Session, user: User, retreat_id: int | None = None) -> int:
    """모두 읽음 — retreat_id 를 주면 **이 회차의** 내 안 읽은 알림 전부 (4-16).

    회차 없는 일반 알림도 함께 읽는다 — 화면의 한 목록에 같이 떠 있다.
    """
    query = select(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)
    )
    if retreat_id is not None:
        query = query.where(
            (Notification.retreat_id == retreat_id) | (Notification.retreat_id.is_(None))
        )
    rows = db.scalars(query).all()
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
    # **끝난 회차에는 아무것도 만들지 않는다** (UI 정리 판 2 · 4-a). 판정은 저장된
    # 상태가 아니라 폐회일에서(period.is_over) — 폐회 뒤 열하루 동안 날마다 서른 몇
    # 건이 쌓여 있었다. 진행 중인 회차는 그대로다
    from app.domain import period

    if period.is_over(retreat, today):
        return 0
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
