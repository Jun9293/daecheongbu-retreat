"""하루 한 번 도는 알림 (CLAUDE.md 4-11).

스케줄러를 앱 안에 넣지 않는다 — 집 서버의 작업 스케줄러가 이 엔드포인트를
부르면 된다. 앱이 시간을 재기 시작하면 껐다 켤 때마다 동작이 달라진다.

미리보기를 따로 둔 이유: 첫 회차에는 실제로 보내지 않고 "오늘 누구에게 무엇이
갈지"만 보면서 문구와 기준을 다듬을 수 있어야 한다.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, log_activity, resolve_retreat
from app.domain import notify
from app.models import PushSubscription, User
from app.push import push_enabled
from app.security import require_admin
from app.templating import redirect, render

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
    request: Request,
    today: str | None = None,
    format: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """보내지 않고 보여준다.

    몇 주 동안 매일 볼 화면이라 사람이 읽을 수 있어야 한다.
    기계가 읽을 것은 ?format=json 으로 남긴다.
    """
    when = _today(today)
    digests = notify.build_digests(db, today=when)
    subscribers = db.scalar(
        select(func.count(func.distinct(PushSubscription.user_id)))
    ) or 0
    payload = {
        "date": when.isoformat(),
        "push_enabled": push_enabled(),
        "subscribers": subscribers,
        "recipients": len(digests),
        "items": sum(len(d.items) for d in digests),
        "digests": [d.as_dict() for d in digests],
    }
    if (format or "").lower() == "json":
        return payload
    return render(
        request,
        "notify_preview.html",
        {
            "user": user,
            "retreat": resolve_retreat(db, user, None),
            "retreats": all_retreats(db),
            "active_tab": "notify",
            "page_subtitle": "알림 미리보기",
            **payload,
        },
    )


@router.post("/admin/notify/run")
def run(
    request: Request,
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
        summary=f"{result['recipients']}명에게 {result['items']}건 "
                f"(실제 발송 {result['sent']}명 · 못 보냄 {result['skipped']}명)",
    )
    if "text/html" in (request.headers.get("accept") or ""):
        note = f"{result['sent']}명에게 보냈습니다."
        if result["skipped"]:
            note += f" {result['skipped']}명은 보낼 곳이 없어 기록하지 않았습니다 — 내일 다시 후보가 됩니다."
        return redirect(f"/admin/notify/preview?today={result['date']}", message=note)
    return result
