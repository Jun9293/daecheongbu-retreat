"""초대 링크 (CLAUDE.md 4-12).

SMS 인증을 접은 이유는 4-12 와 1장 확정사항에 적었다. 여기서는 그 결정을
안전하게 구현하는 것만 다룬다.

**토큰 원문을 저장하지 않는다.** 해시만 남기고 원문은 발급 화면에서 한 번만
보여준다 — DB 파일이 새면 링크가 그대로 새는 구조를 만들지 않기 위해서다.
비밀번호를 평문으로 두지 않는 것과 같은 이유다.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InviteToken, User

INVITE_TTL_DAYS = 7        # 링크의 유효기간
TOKEN_BYTES = 32           # secrets.token_urlsafe 에 넘길 바이트 수


def invite_url(raw: str, *, base: str | None = None) -> str:
    """붙여넣으면 바로 열리는 초대 주소.

    **자리표시자를 남기지 않습니다.** 전에는 주소 앞부분을 자리표시자로
    찍고 사람이 손으로 갈아 끼웠는데, 그러다 토큰까지 건드려
    링크가 깨졌습니다.

    주소를 만드는 곳은 **여기 하나**입니다 — 스크립트와 화면이 같이 씁니다.
    두 곳에서 만들면 한쪽만 고쳐집니다.
    """
    from app import config

    root = (base or config.BASE_URL or "").rstrip("/")
    return f"{root}/invite/{raw}"


def normalize_phone(raw: str) -> str:
    """연락처를 숫자만 남겨 정규화한다.

    로그인에는 더 이상 쓰지 않는다 (초대 링크로 바꿨다). 사람을 알아보고
    총무팀이 연락할 때 쓰는 값이라 형식만 맞춘다.
    """
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if not digits:
        raise ValueError("연락처를 입력해주세요.")
    if len(digits) < 9 or len(digits) > 11:
        raise ValueError("연락처 형식이 올바르지 않습니다.")
    return digits


def _now() -> dt.datetime:
    return dt.datetime.now()


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue(db: Session, *, user: User, actor: User | None = None) -> str:
    """새 초대 링크를 발급하고 **원문을 돌려준다.**

    같은 사람에게 남아 있던 링크는 함께 취소한다 — 재발급했는데 옛 링크가
    계속 살아 있으면 "한 번 쓰면 만료" 가 뜻을 잃는다.
    """
    revoke_all(db, user=user)

    raw = secrets.token_urlsafe(TOKEN_BYTES)
    db.add(
        InviteToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=_now() + dt.timedelta(days=INVITE_TTL_DAYS),
            created_by_id=actor.id if actor else None,
        )
    )
    db.commit()
    return raw


def revoke_all(db: Session, *, user: User) -> int:
    """그 사람의 살아 있는 링크를 전부 취소한다."""
    count = 0
    for token in db.scalars(
        select(InviteToken).where(
            InviteToken.user_id == user.id,
            InviteToken.used_at.is_(None),
            InviteToken.revoked_at.is_(None),
        )
    ):
        token.revoked_at = _now()
        count += 1
    if count:
        db.commit()
    return count


def problem_with(token: InviteToken | None) -> str | None:
    """쓸 수 없는 링크면 사유를, 괜찮으면 None."""
    if token is None:
        return "링크를 찾을 수 없습니다. 총무팀에 다시 요청해주세요."
    if token.revoked_at is not None:
        return "취소된 링크입니다. 총무팀에 다시 요청해주세요."
    if token.used_at is not None:
        return "이미 사용한 링크입니다. 링크는 한 번만 쓸 수 있습니다."
    if token.expires_at < _now():
        return f"만료된 링크입니다 (유효기간 {INVITE_TTL_DAYS}일). 총무팀에 다시 요청해주세요."
    return None


def redeem(db: Session, raw: str) -> tuple[User | None, str | None]:
    """링크를 쓴다. (사용자, 사유) 중 하나만 채워 돌려준다."""
    token = db.scalars(
        select(InviteToken).where(InviteToken.token_hash == hash_token(raw))
    ).first()

    reason = problem_with(token)
    if reason is not None:
        return None, reason

    user = db.get(User, token.user_id)
    if user is None:
        return None, "계정을 찾을 수 없습니다. 총무팀에 문의해주세요."
    if not user.is_active:
        return None, "비활성화된 계정입니다. 총무팀에 문의해주세요."

    token.used_at = _now()
    db.commit()
    return user, None


def live_token(db: Session, *, user: User) -> InviteToken | None:
    """아직 쓸 수 있는 링크가 있는지 (원문은 알 수 없다 — 해시만 있으므로)."""
    for token in db.scalars(
        select(InviteToken)
        .where(InviteToken.user_id == user.id)
        .order_by(InviteToken.id.desc())
    ):
        if problem_with(token) is None:
            return token
    return None


# ── 발급 직후 한 번만 꺼내지는 자리 ──────────────────────────────────
#
# 원문을 URL 에 실으면 총무팀 브라우저의 **주소창과 방문 기록**, Cloudflare 접속
# 로그에 7일 내내 살아 있는 링크가 남는다. 총무팀은 그 링크를 자기가 쓰는 것이
# 아니라 복사해서 보내므로 링크는 그동안 계속 쓸 수 있는 상태다 — 그 컴퓨터를
# 잠깐 쓰는 사람이 방문 기록에서 꺼내 그 사람으로 로그인할 수 있다.
# 해시로 저장한 이유가 거기서 무너진다.
#
# 그래서 원문은 서버 메모리에만 두고 URL 에는 **한 번 쓰면 사라지는 키**만 싣는다.
# 새로고침하면 이미 없으므로 링크가 다시 나오지 않는다.
_HANDOFF_TTL_SECONDS = 600      # 발급 화면을 띄우는 데 이보다 오래 걸릴 일은 없다
_HANDOFF_MAX = 50               # 무한히 쌓이지 않게
_handoff: dict[str, tuple[str, dt.datetime]] = {}


def _sweep_handoff(now: dt.datetime) -> None:
    for key in [k for k, (_, at) in _handoff.items()
                if (now - at).total_seconds() > _HANDOFF_TTL_SECONDS]:
        _handoff.pop(key, None)
    while len(_handoff) > _HANDOFF_MAX:
        _handoff.pop(next(iter(_handoff)), None)


def stash(raw: str) -> str:
    """원문을 담아 두고 **꺼낼 키**를 돌려준다."""
    now = _now()
    _sweep_handoff(now)
    key = secrets.token_urlsafe(9)
    _handoff[key] = (raw, now)
    return key


def take(key: str | None) -> str | None:
    """한 번만 꺼내진다. 두 번째부터는 None — 새로고침해도 다시 보이지 않는다."""
    if not key:
        return None
    now = _now()
    _sweep_handoff(now)
    found = _handoff.pop(key, None)
    if found is None:
        return None
    raw, at = found
    if (now - at).total_seconds() > _HANDOFF_TTL_SECONDS:
        return None
    return raw
