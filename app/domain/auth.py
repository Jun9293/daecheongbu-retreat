"""전화번호 SMS 인증코드 발급/검증."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import AUTH_CODE_MAX_ATTEMPTS, AUTH_CODE_TTL_SECONDS, SECRET_KEY
from app.models import AuthCode

_MOBILE_RE = re.compile(r"^01[016789]\d{7,8}$")


class AuthError(Exception):
    """인증 실패 (코드 불일치·만료·시도 초과)."""


def normalize_phone(raw: str) -> str:
    """입력된 전화번호를 '01012345678' 형태로 정규화한다."""
    if not raw:
        raise ValueError("전화번호를 입력해주세요.")

    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("+82"):
        digits = "0" + digits[3:]
    elif digits.startswith("82") and not digits.startswith("820"):
        digits = "0" + digits[2:]
    digits = digits.lstrip("+")

    if not _MOBILE_RE.match(digits):
        raise ValueError("휴대폰 번호 형식이 올바르지 않습니다. (예: 010-1234-5678)")
    return digits


def _hash_code(phone_number: str, code: str) -> str:
    msg = f"{phone_number}:{code}".encode()
    return hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def issue_auth_code(db: Session, *, phone_number: str) -> str:
    """새 인증코드를 발급하고, 같은 번호의 이전 코드는 무효화한다."""
    now = _now()
    for old in db.scalars(
        select(AuthCode).where(
            AuthCode.phone_number == phone_number, AuthCode.consumed_at.is_(None)
        )
    ):
        old.consumed_at = now

    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        AuthCode(
            phone_number=phone_number,
            code_hash=_hash_code(phone_number, code),
            expires_at=now + dt.timedelta(seconds=AUTH_CODE_TTL_SECONDS),
        )
    )
    db.commit()
    return code


def verify_auth_code(
    db: Session, *, phone_number: str, code: str, now: dt.datetime | None = None
) -> bool:
    now = now or _now()
    record = db.scalars(
        select(AuthCode)
        .where(AuthCode.phone_number == phone_number, AuthCode.consumed_at.is_(None))
        .order_by(AuthCode.id.desc())
    ).first()

    if record is None:
        raise AuthError("인증코드를 먼저 요청해주세요.")
    if record.expires_at < now:
        raise AuthError("인증코드가 만료되었습니다. 다시 요청해주세요.")
    if record.attempts >= AUTH_CODE_MAX_ATTEMPTS:
        raise AuthError("시도 횟수를 초과했습니다. 인증코드를 다시 요청해주세요.")

    if not hmac.compare_digest(record.code_hash, _hash_code(phone_number, code)):
        record.attempts += 1
        db.commit()
        raise AuthError("인증코드가 올바르지 않습니다.")

    record.consumed_at = now
    db.commit()
    return True
