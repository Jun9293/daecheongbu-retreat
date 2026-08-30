"""하루 한 번 도는 알림 (CLAUDE.md 4-11).

스케줄러를 앱 안에 넣지 않는다 — 집 서버의 작업 스케줄러가 이 엔드포인트를
부르면 된다. 앱이 시간을 재기 시작하면 껐다 켤 때마다 동작이 달라진다.

미리보기를 따로 둔 이유: 첫 회차에는 실제로 보내지 않고 "오늘 누구에게 무엇이
갈지"만 보면서 문구와 기준을 다듬을 수 있어야 한다.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import log_activity
from app.domain import notify
from app.models import User
from app.push import push_enabled
from app.security import require_admin

router = APIRouter()


def _today(value: str | None) -> dt.date:
    if not value:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return dt.date.today()


@router.get("/admin/notify/preview")
def preview(
    today: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """보내지 않고 보여준다."""
    when = _today(today)
    digests = notify.build_digests(db, today=when)
    return {
        "date": when.isoformat(),
        "push_enabled": push_enabled(),
        "recipients": len(digests),
        "items": sum(len(d.items) for d in digests),
        "digests": [d.as_dict() for d in digests],
    }


@router.post("/admin/notify/run")
def run(
    today: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """실제 발송. 같은 날 두 번 불러도 중복되지 않는다 (4-11의 재발송 간격)."""
    when = _today(today)
    result = notify.run_digests(db, today=when)
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="알림_발송",
        target_type="notification",
        target_id=None,
        summary=f"{result['recipients']}명에게 {result['items']}건 (실제 발송 {result['sent']}명)",
    )
    return result
