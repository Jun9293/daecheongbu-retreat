# -*- coding: utf-8 -*-
"""아이디·비밀번호로 들어오는 자리 (CLAUDE.md 4-12).

**비밀번호 원문은 어디에도 저장하지 않고 로그에도 안 찍는다.** 남는 것은
아래 `해시한다` 가 만든 한 줄뿐이고, 그 줄에는 원문을 되돌릴 것이 없다.

## 해시 줄에 셈을 함께 적는다

    scrypt$<n>$<r>$<p>$<소금>$<해시>      (소금과 해시는 열여섯 진수로 적는다)

읽을 때는 **그 줄에 적힌 셈**으로 센다. 세기를 올리면 그때부터 만들어지는
줄만 새 셈이고 옛 줄은 옛 셈 그대로인데, 읽는 쪽이 지금 셈으로 세면
**그날 이전에 비밀번호를 정한 사람 전원이 조용히 못 들어온다** — 비밀번호가
틀렸다는 말만 나오고 아무 오류도 안 난다.

## `maxmem` 을 반드시 함께 준다

`hashlib.scrypt` 는 `maxmem` 을 안 주면 OpenSSL 기본값(32MB)을 쓰는데,
그 한도는 **셈을 올리는 순간 넘는다** — n 을 32768 로만 올려도 `ValueError`
가 난다(같은 노트북의 다른 앱에서 실제로 밟았다). 그래서 필요한 크기를
**줄에 적힌 셈에서 계산해** 함께 넘긴다. 값을 글로 적어 두지 않고
`tests/test_stage34.py` 가 잰다 — 기본값으로는 터지는 것까지 함께.

## 틀린 사유를 가르지 않는다

없는 아이디와 틀린 비밀번호가 **같은 말**을 낸다. 갈라 말하면 아이디
목록을 만들 수 있고, 그 목록이 곧 사람 목록이다. 없는 아이디일 때도
**더미 해시를 한 번 세어** 걸리는 시간으로도 안 갈리게 한다.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User

# ── 셈 ────────────────────────────────────────────────────────────────
#
# 지금 만드는 줄에 쓰는 값이다. 올려도 옛 줄은 자기 셈으로 읽히므로
# 여기만 고치면 된다 — 그것이 줄에 셈을 적어 두는 이유다.
N, R, P = 2**15, 8, 1
SALT_BYTES = 16
KEY_BYTES = 32

MIN_LENGTH = 8                  # 규칙은 이 하나뿐이다 (아래 `너무짧나`)
MAX_FAILS = 10                  # 이만큼 틀리면 잠근다
LOCK_MINUTES = 5                # 잠기는 시간

# 발급한 첫 비밀번호의 길이. 사람이 카카오톡으로 옮겨 적는 값이라
# 헷갈리는 글자(0/O·1/l)를 뺀 자리에서 고른다.
FIRST_LENGTH = 10
_FIRST_ALPHABET = "abcdefghijkmnpqrstuvwxyzACDEFGHJKLMNPQRSTUVWXYZ23456789"


def now() -> dt.datetime:
    """저장하는 시각은 이 저장소에서 전부 tz 없는 UTC 다 (`models._now`)."""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _maxmem(n: int, r: int, p: int) -> int:
    """그 셈이 실제로 쓰는 크기에 여유를 붙인 값.

    scrypt 가 쓰는 크기는 대략 `128 * n * r` 이고 병렬도만큼 더 든다.
    **셈에서 계산한다** — 숫자를 박아 두면 셈을 올릴 때 한쪽만 고쳐진다.
    """
    return 128 * n * r * (p + 2)


def 해시한다(raw: str) -> str:
    """새 비밀번호 한 줄. 원문은 돌려주지도 남기지도 않는다."""
    salt = secrets.token_bytes(SALT_BYTES)
    key = hashlib.scrypt(
        raw.encode("utf-8"), salt=salt, n=N, r=R, p=P,
        maxmem=_maxmem(N, R, P), dklen=KEY_BYTES,
    )
    return f"scrypt${N}${R}${P}${salt.hex()}${key.hex()}"


def 맞나(stored: str | None, raw: str) -> bool:
    """줄에 적힌 셈으로 세어 견준다. 모양이 이상하면 거짓이다."""
    if not stored or not raw:
        return False
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt, key = bytes.fromhex(parts[4]), bytes.fromhex(parts[5])
    except ValueError:
        return False
    if n < 2 or n & (n - 1) or r < 1 or p < 1:
        return False
    try:
        got = hashlib.scrypt(
            raw.encode("utf-8"), salt=salt, n=n, r=r, p=p,
            maxmem=_maxmem(n, r, p), dklen=len(key),
        )
    except ValueError:
        return False
    return hmac.compare_digest(got, key)


# 없는 아이디일 때 한 번 세는 줄. **시간으로도 안 갈리게** 하려고 둔다 —
# 아이디가 없으면 바로 돌아가고 있으면 해시를 세면, 걸린 시간만 재도
# 어느 아이디가 있는지 알 수 있다.
_더미: str | None = None


def 더미해시() -> str:
    global _더미
    if _더미 is None:
        _더미 = 해시한다(secrets.token_urlsafe(32))
    return _더미


def 너무짧나(raw: str) -> bool:
    """규칙은 길이 하나뿐이다.

    큰 글자·기호를 섞으라는 규칙은 외우기 어려운 짧은 값을 만들 뿐이고,
    사람은 그것을 적어 둔다. 길이만 본다.
    """
    return len(raw or "") < MIN_LENGTH


def 첫비밀번호() -> str:
    """관리자가 본인에게 전할 값. **저장하지 않고 화면에만 한 번 보인다.**"""
    return "".join(secrets.choice(_FIRST_ALPHABET) for _ in range(FIRST_LENGTH))


def 아이디로찾기(db: Session, login_id: str) -> User | None:
    """대소문자를 가리지 않고 찾는다 — 휴대폰이 첫 글자를 제멋대로 키운다."""
    login_id = (login_id or "").strip()
    if not login_id:
        return None
    return db.scalars(
        select(User).where(func.lower(User.login_id) == login_id.lower())
    ).first()


def 잠겼나(user: User, at: dt.datetime | None = None) -> bool:
    until = getattr(user, "locked_until", None)
    return until is not None and until > (at or now())


# 사유를 가르지 않는 그 한마디. 없는 아이디와 틀린 비밀번호가 같이 쓴다.
TOLD = "아이디 또는 비밀번호가 맞지 않습니다."
TOLD_INACTIVE = "비활성화된 계정입니다. 총무팀에 문의해주세요."
TOLD_LOCKED = (
    f"{MAX_FAILS}번 틀려서 {LOCK_MINUTES}분 동안 잠겼습니다."
    " 잠시 뒤에 다시 해주세요."
)


def 들어온다(db: Session, login_id: str, raw: str,
          at: dt.datetime | None = None) -> tuple[User | None, str | None]:
    """(사용자, 사유) 중 하나만 채워 돌려준다.

    **순서가 규칙이다.**

    1. 아이디가 없으면 — 더미 해시를 한 번 세고 `TOLD`
    2. 잠겨 있으면 — 비밀번호를 보지 않고 `TOLD_LOCKED`
       (맞는 비밀번호로 잠금이 풀리면 잠글 뜻이 없다)
    3. **비활성이면 — 비밀번호를 보기 전에** `TOLD_INACTIVE`
       (뒤에 두면 같은 비활성 계정이 비밀번호가 맞을 때와 틀릴 때 다른 말을
       내서, 그 계정의 비밀번호를 맞혔는지를 화면이 알려 준다)
    4. 틀리면 — 센 수를 올리고, `MAX_FAILS` 에 닿으면 잠근다
    5. 맞으면 — 센 수를 0 으로 되돌린다

    잠금은 **DB 에** 있다. 메모리에 두면 서버를 다시 켜는 것으로 풀린다.
    """
    at = at or now()
    user = 아이디로찾기(db, login_id)
    if user is None:
        맞나(더미해시(), raw or "")
        return None, TOLD
    if 잠겼나(user, at):
        return None, TOLD_LOCKED
    if not user.is_active:
        return None, TOLD_INACTIVE

    if not 맞나(user.password_hash, raw or ""):
        user.failed_count = (user.failed_count or 0) + 1
        if user.failed_count >= MAX_FAILS:
            user.locked_until = at + dt.timedelta(minutes=LOCK_MINUTES)
            user.failed_count = 0
            db.commit()
            return None, TOLD_LOCKED
        db.commit()
        return None, TOLD

    user.failed_count = 0
    user.locked_until = None
    db.commit()
    return user, None


def 비밀번호를정한다(db: Session, user: User, raw: str, *, 첫판: bool = False) -> None:
    """해시만 남기고 원문은 버린다.

    `첫판` 은 관리자가 발급하는 자리다 — 그때는 본인이 바꿔야 하므로
    `must_change_password` 를 참으로 둔다. 본인이 바꾼 자리에서는 거짓이다.
    """
    user.password_hash = 해시한다(raw)
    user.must_change_password = 첫판
    user.failed_count = 0
    user.locked_until = None
    db.commit()


# ── 발급 직후 한 번만 꺼내지는 자리 ──────────────────────────────────
#
# **첫 비밀번호를 주소(URL)에 싣지 않는다.** 실으면 총무팀 브라우저의
# 주소창과 방문 기록, 그리고 Cloudflare 접속 로그에 그 값이 남는다 —
# 그 컴퓨터를 잠깐 쓰는 사람이 방문 기록에서 꺼내 그 사람으로 들어갈 수
# 있고, 해시로만 저장하는 이유가 거기서 무너진다.
#
# 그래서 원문은 **서버 메모리에만** 두고 주소에는 한 번 쓰면 사라지는
# 키만 싣는다. 새로고침하면 이미 없으므로 다시 나오지 않는다.
# (초대 링크 시절에 같은 자리가 `domain/auth` 에 있었다 — 링크가 걷히면서
# 이리로 왔다. 담는 것이 링크에서 비밀번호로 바뀌었을 뿐 이유는 같다.)
_꺼내는_시간 = 600      # 발급 화면을 띄우는 데 이보다 오래 걸릴 일은 없다
_꺼내는_최대 = 50       # 무한히 쌓이지 않게
_한번자리: dict[str, tuple[str, str, dt.datetime]] = {}


def _쓸어낸다(at: dt.datetime) -> None:
    for key in [k for k, (_, _, 찍힌때) in _한번자리.items()
                if (at - 찍힌때).total_seconds() > _꺼내는_시간]:
        _한번자리.pop(key, None)
    while len(_한번자리) > _꺼내는_최대:
        _한번자리.pop(next(iter(_한번자리)), None)


def 담는다(raw: str, name: str = "") -> str:
    """원문과 **누구의 것인지**를 한 키에 묶어 둔다.

    이름을 따로 실으면 주소를 손봤을 때 「B 님의 비밀번호」 아래 A 의 값이
    뜰 자리가 생긴다. 묶어 두면 그 자리가 없다.
    """
    at = now()
    _쓸어낸다(at)
    key = secrets.token_urlsafe(9)
    _한번자리[key] = (raw, name, at)
    return key


def 꺼낸다(key: str | None) -> tuple[str, str] | None:
    """(원문, 이름). **한 번만 꺼내진다** — 새로고침하면 다시 안 보인다."""
    if not key:
        return None
    at = now()
    _쓸어낸다(at)
    found = _한번자리.pop(key, None)
    if found is None:
        return None
    raw, name, 찍힌때 = found
    if (at - 찍힌때).total_seconds() > _꺼내는_시간:
        return None
    return raw, name
