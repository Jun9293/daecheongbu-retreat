"""웹 푸시 — 시스템이 먼저 말을 거는 유일한 자리 (CLAUDE.md 4-11).

지금까지 만든 것은 전부 사람이 화면을 열었을 때 답하는 것이었다. 푸시는 반대라
잘못 만들면 되돌리기 어렵다 — 틀린 알림을 세 번 받은 사람은 그 뒤 알림을 보지
않는다. **보내지 않는 쪽으로 기울여 만든다.** 놓치는 것보다 신뢰를 잃는 쪽이 비싸다.

판정은 diagnosis 를 그대로 재료로 쓴다. 푸시 전용 판정 규칙을 새로 쓰면 두 벌이
되어 화면과 알림이 어긋난다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import diagnosis as diag
from app.domain.board import has_started, load_runs, overdue_days_of, overdue_of
from app.domain.departments import users_in_department
from app.models import Department, NotificationLog, Retreat, TaskRun, User

# ── 임계값. 이름을 붙여 둔다 ──────────────────────────────────────────
STALE_DAYS = 7        # 시작하기로 한 날에서 이만큼 지나도록 손대지 않으면 '방치'
DUE_SOON_DAYS = 3     # 마감까지 이 안쪽이면 '임박'
RENOTIFY_DAYS = 7     # 같은 말을 이 안에 다시 하지 않는다
DIGEST_MAX = 5        # 한 통에 담는 최대 건수. 스무 줄짜리 알림은 아무도 안 읽는다

# 항목 종류
STALE = "방치"
DUE_SOON = "기한 임박"
OVERDUE = "기한 초과"
UNBLOCK = "선행 재촉"

KIND_ORDER = (OVERDUE, DUE_SOON, UNBLOCK, STALE)


@dataclass
class Item:
    kind: str
    run_id: int
    title: str
    line: str
    verdict: str
    status: str

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "run_id": self.run_id,
            "title": self.title,
            "line": self.line,
            "verdict": self.verdict,
            "status": self.status,
        }


@dataclass
class Digest:
    user_id: int
    user_name: str
    items: list[Item] = field(default_factory=list)
    overflow: int = 0

    def as_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "overflow": self.overflow,
            "items": [i.as_dict() for i in self.items],
            "title": self.title(),
            "body": self.body(),
        }

    def title(self) -> str:
        return f"수련회 준비 — 오늘 볼 것 {len(self.items) + self.overflow}건"

    def body(self) -> str:
        """kind 별로 묶는다. 재촉하지 않는다 — 판정 단어는 화면과 같은 말을 쓴다."""
        lines: list[str] = []
        for kind in KIND_ORDER:
            rows = [i for i in self.items if i.kind == kind]
            if not rows:
                continue
            lines.append(f"[{kind}]")
            lines.extend(f"· {row.line}" for row in rows)
        if self.overflow:
            lines.append(f"외 {self.overflow}건")
        return "\n".join(lines)


# ── 받는 사람 고르기 ──────────────────────────────────────────────────


def recipient_for(db: Session, run: TaskRun) -> User | None:
    """담당자. 없으면 그 부서의 리더, 그마저 없으면 총무팀으로 올린다.

    셋 다에게 보내지 않는다 — 다 받으면 아무도 자기 일로 받지 않는다.
    """
    if run.assignee_id is not None:
        return db.get(User, run.assignee_id)

    if run.department_id is not None:
        dept = db.get(Department, run.department_id)
        # **키로 찾는다.** id 로 비교하면 새 회차가 열리는 순간 리더를 못 찾고
        # 조용히 총무팀으로 떨어져, 담당자 미지정 업무가 한 사람에게 몰린다.
        leads = users_in_department(db, dept.key if dept else None, role="dept_lead")
        if leads:
            return leads[0]

    return db.scalars(
        select(User).where(User.role == "admin").order_by(User.id)
    ).first()


# ── 항목 고르기 ───────────────────────────────────────────────────────


def _skip(run: TaskRun) -> bool:
    """아예 알림 대상이 아닌 업무."""
    if run.status == "완료":
        return True
    # '일정' 은 산출물 없이 날짜만 지키면 되는 것이라 재촉할 것이 없다 (4-2)
    return run.library.kind == "schedule"


def items_for_run(
    run: TaskRun, verdict: str, today: dt.date
) -> list[Item]:
    """그 업무의 담당자가 받을 항목들. '진행 불가' 는 여기서 나오지 않는다."""
    out: list[Item] = []
    title = run.library.title
    end = run.end_date or run.start_date

    # 기한 초과 — 날짜에서 계산한다. 저장된 '지연' 은 보지 않는다.
    if overdue_of(run, today):
        days = overdue_days_of(run, today)
        out.append(Item(OVERDUE, run.id, title, f"{title} — 마감에서 {days}일 지났습니다",
                        verdict, run.status))
    elif end and 0 <= (end - today).days <= DUE_SOON_DAYS:
        left = (end - today).days
        when = "오늘까지입니다" if left == 0 else f"{left}일 남았습니다"
        out.append(Item(DUE_SOON, run.id, title, f"{title} — 마감이 {when}",
                        verdict, run.status))

    # 방치 — 막는 요인이 없다는 것이 확인된 상태라 가장 정확한 신호다.
    # 재촉하지 않는다: "아직 안 하셨습니다" 가 아니라 "시작할 수 있습니다".
    if verdict == diag.GO and not has_started(run) and run.start_date:
        idle = (today - run.start_date).days
        if idle >= STALE_DAYS:
            out.append(
                Item(STALE, run.id, title,
                     f"{title} — 막는 요인이 없습니다. {idle}일째 시작하지 않았습니다",
                     verdict, run.status)
            )
    return out


def build_digests(db: Session, *, today: dt.date | None = None) -> list[Digest]:
    """오늘 누구에게 무엇이 갈지. 전송과 분리한다 — 그래야 테스트가 된다."""
    today = today or dt.date.today()

    per_user: dict[int, list[Item]] = {}
    names: dict[int, str] = {}

    def add(user: User | None, item: Item) -> None:
        if user is None:
            return
        per_user.setdefault(user.id, []).append(item)
        names[user.id] = user.name

    for retreat in db.scalars(select(Retreat)):
        # 종료·보관된 회차는 보내지 않는다
        closing = retreat.end_date or retreat.start_date
        if retreat.is_archived or (closing and closing < today):
            continue

        runs = load_runs(db, retreat)
        by_id = {r.id: r for r in runs}
        blocks: dict[int, list[int]] = {}
        for other in runs:
            for blocker_id in other.blocked_by_run_ids or []:
                if blocker_id in by_id:
                    blocks.setdefault(blocker_id, []).append(other.id)

        verdicts = {r.id: diag.verdict_of(r, by_id, today) for r in runs}

        for run in runs:
            if _skip(run):
                continue
            verdict = verdicts[run.id]

            # '진행 불가' 는 담당자 본인에게 보내지 않는다 — 기다리는 중인데
            # 재촉받는 것이 된다. 대신 선행을 쥔 쪽이 아래에서 받는다.
            if verdict != diag.BLOCKED:
                for item in items_for_run(run, verdict, today):
                    add(recipient_for(db, run), item)

            # 선행 재촉 — 내 업무가 남을 막고 있을 때 내가 받는다
            waiting = [
                by_id[i]
                for i in blocks.get(run.id, [])
                if i in by_id and verdicts[i] == diag.BLOCKED
            ]
            if waiting:
                who = ", ".join(
                    f"'{w.library.title}'"
                    + (f"({w.department.name})" if w.department else "")
                    for w in waiting[:2]
                )
                more = f" 외 {len(waiting) - 2}건" if len(waiting) > 2 else ""

                # 기다리는 쪽의 기한을 함께 알린다. '진행 불가' 는 그 담당자에게
                # 보내지 않으므로, 이 문장이 없으면 선행을 쥔 쪽도 급한 줄 모른다.
                late = [w for w in waiting if overdue_of(w, today)]
                tail = ""
                if late:
                    worst = max(overdue_days_of(w, today) for w in late)
                    tail = f" — 그쪽 마감이 {worst}일 지났습니다"

                item = Item(
                    UNBLOCK, run.id, run.library.title,
                    f"{run.library.title} — {who}{more}이(가) 이 업무를 기다리고 있습니다{tail}",
                    verdict, run.status,
                )
                add(recipient_for(db, run), item)

                # 기다리는 쪽이 기한을 넘겼을 때만 총무팀에도 올린다.
                # **이때만 예외다** — 나머지는 담당자 한 사람 원칙을 그대로 지킨다.
                if late:
                    owner = recipient_for(db, run)
                    for boss in db.scalars(
                        select(User).where(User.role == "admin").order_by(User.id)
                    ):
                        if owner is not None and boss.id == owner.id:
                            continue      # 담당자가 총무팀이면 두 번 받지 않는다
                        add(boss, item)

    digests: list[Digest] = []
    for user_id, items in per_user.items():
        keep = [i for i in items if not _muted(db, user_id, i, today)]
        if not keep:
            continue                      # 보낼 것이 없으면 보내지 않는다
        keep.sort(key=lambda i: (KIND_ORDER.index(i.kind), i.title))
        digests.append(
            Digest(
                user_id=user_id,
                user_name=names[user_id],
                items=keep[:DIGEST_MAX],
                overflow=max(0, len(keep) - DIGEST_MAX),
            )
        )
    digests.sort(key=lambda d: d.user_id)
    return digests


def _muted(db: Session, user_id: int, item: Item, today: dt.date) -> bool:
    """같은 말을 RENOTIFY_DAYS 안에 다시 하지 않는다.

    다만 그 업무의 상태나 판정이 바뀌었으면 다시 보낸다 — 사정이 달라진 것이므로
    같은 말이 아니다.
    """
    last = db.scalars(
        select(NotificationLog)
        .where(
            NotificationLog.user_id == user_id,
            NotificationLog.run_id == item.run_id,
            NotificationLog.kind == item.kind,
        )
        .order_by(NotificationLog.sent_on.desc(), NotificationLog.id.desc())
    ).first()
    if last is None or last.sent_on is None:
        return False
    if (today - last.sent_on).days >= RENOTIFY_DAYS:
        return False
    before = last.payload or {}
    return (
        before.get("status") == item.status
        and before.get("verdict") == item.verdict
    )


def record(db: Session, digest: Digest, today: dt.date) -> None:
    """보낸 것을 남긴다. 같은 날 두 번 실행해도 이 기록 때문에 중복되지 않는다."""
    for item in digest.items:
        db.add(
            NotificationLog(
                user_id=digest.user_id,
                run_id=item.run_id,
                kind=item.kind,
                sent_on=today,
                payload={"status": item.status, "verdict": item.verdict,
                         "line": item.line},
            )
        )
    db.commit()


def run_digests(db: Session, *, today: dt.date | None = None, sender=None) -> dict:
    """묶음을 만들고 보낸 뒤 기록한다. sender 를 주입하면 실제 전송을 갈아끼울 수 있다."""
    today = today or dt.date.today()
    if sender is None:
        from app.push import send_digest

        sender = send_digest

    digests = build_digests(db, today=today)
    sent, skipped = 0, 0
    for digest in digests:
        if sender(db, digest):
            record(db, digest, today)
            sent += 1
        else:
            # **보내지 못한 것을 보낸 것으로 기록하지 않는다.** 기록하면 그 항목들이
            # 7일간 침묵한다 — 구독자가 0명일 때 한 번 잘못 부르면 그 주의 알림이
            # 통째로 소진된다. 다음 날 다시 후보가 되어야 한다.
            skipped += 1
    return {
        "date": today.isoformat(),
        "recipients": len(digests),
        "sent": sent,
        "skipped": skipped,
        "items": sum(len(d.items) for d in digests),
    }
