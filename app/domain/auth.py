# -*- coding: utf-8 -*-
"""옛 초대 링크 (CLAUDE.md 4-12).

**2026-09-11 에 걷었습니다.** 로그인은 아이디와 비밀번호로 합니다
(`app/domain/login.py`) — 휴대폰 홈 화면에 붙인 앱은 쿠키가 사파리와 따로라
사파리에서 연 링크로는 그 앱 안에서 로그인되지 않고, 그 안에는 링크를 붙여
넣을 주소창도 없기 때문입니다.

**만드는 길은 남기지 않았습니다** — 발급·사용·주소 만들기를 지웠습니다.
코드를 남겨 두면 그것이 곧 열린 문입니다. 옛 주소(`/invite/<토큰>`)는
토큰을 보지 않고 로그인 화면으로 보냅니다 (`app/routers/login.py`).

**표(`invite_tokens`)와 행은 지우지 않습니다** (0장) — 누가 언제 들어왔는지가
거기 남아 있습니다. 아직 살아 있는 링크를 끊는 것은
`scripts/계정문열기.py` 갈래 ③ 이고, 그때 「살아 있다」 의 뜻은
아래 `problem_with` 하나입니다.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InviteToken, User

INVITE_TTL_DAYS = 7        # 만들던 시절의 유효기간 — 아래 사유 문구가 쓴다


def _now() -> dt.datetime:
    return dt.datetime.now()


def hash_token(raw: str) -> str:
    """옛 행과 견줄 때만 쓴다. 원문은 저장한 적이 없다."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def problem_with(token: InviteToken | None) -> str | None:
    """쓸 수 없는 링크면 사유를, **아직 살아 있으면 None.**

    「살아 있다」 를 이 파일 안에서 두 번 정하지 않는다 — 전에 그러다
    한쪽이 기한을 안 봐서 같은 파일에 두 뜻이 있었다.
    """
    if token is None:
        return "링크를 찾을 수 없습니다."
    if token.revoked_at is not None:
        return "취소된 링크입니다."
    if token.used_at is not None:
        return "이미 사용한 링크입니다."
    if token.expires_at < _now():
        return f"만료된 링크입니다 (유효기간 {INVITE_TTL_DAYS}일)."
    return None


def live_token(db: Session, *, user: User) -> InviteToken | None:
    """그 사람에게 아직 살아 있는 링크가 있는지."""
    for token in db.scalars(
        select(InviteToken)
        .where(InviteToken.user_id == user.id)
        .order_by(InviteToken.id.desc())
    ):
        if problem_with(token) is None:
            return token
    return None


def revoke_all(db: Session, *, user: User) -> int:
    """그 사람의 살아 있는 링크를 전부 끊는다."""
    count = 0
    for token in db.scalars(select(InviteToken).where(InviteToken.user_id == user.id)):
        if problem_with(token) is None:
            token.revoked_at = _now()
            count += 1
    if count:
        db.commit()
    return count


def 살아있는것들(db: Session) -> list[InviteToken]:
    """아직 살아 있는 링크 전부. **먼저 세어 사람에게 보이려고** 따로 둔다."""
    return [t for t in db.scalars(select(InviteToken)) if problem_with(t) is None]


def 전부끊는다(db: Session) -> int:
    """살아 있는 링크를 전부 끊고 몇 개였는지 돌려준다 (계정문열기 갈래 ③)."""
    at = _now()
    tokens = 살아있는것들(db)
    for token in tokens:
        token.revoked_at = at
    if tokens:
        db.commit()
    return len(tokens)
