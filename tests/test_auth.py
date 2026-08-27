"""전화번호 인증 로직 테스트."""

import datetime as dt

import pytest
from sqlalchemy.orm import Session

from app.domain.auth import (
    AuthError,
    issue_auth_code,
    normalize_phone,
    verify_auth_code,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("010-1234-5678", "01012345678"),
        ("010 1234 5678", "01012345678"),
        ("01012345678", "01012345678"),
        ("+82 10-1234-5678", "01012345678"),
        ("+821012345678", "01012345678"),
    ],
)
def test_전화번호를_정규화한다(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "010", "abcdefg", "02-123-4567", "0101234567890"])
def test_잘못된_전화번호는_거부한다(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_인증코드는_6자리_숫자다(db: Session):
    code = issue_auth_code(db, phone_number="01012345678")

    assert len(code) == 6
    assert code.isdigit()


def test_발급된_코드로_인증에_성공한다(db: Session):
    code = issue_auth_code(db, phone_number="01012345678")

    assert verify_auth_code(db, phone_number="01012345678", code=code) is True


def test_틀린_코드는_인증에_실패한다(db: Session):
    code = issue_auth_code(db, phone_number="01012345678")
    wrong = "000000" if code != "000000" else "111111"

    with pytest.raises(AuthError):
        verify_auth_code(db, phone_number="01012345678", code=wrong)


def test_이미_사용한_코드는_재사용할_수_없다(db: Session):
    code = issue_auth_code(db, phone_number="01012345678")
    verify_auth_code(db, phone_number="01012345678", code=code)

    with pytest.raises(AuthError):
        verify_auth_code(db, phone_number="01012345678", code=code)


def test_만료된_코드는_인증에_실패한다(db: Session):
    code = issue_auth_code(db, phone_number="01012345678")
    later = dt.datetime.now(dt.UTC).replace(tzinfo=None) + dt.timedelta(minutes=10)

    with pytest.raises(AuthError):
        verify_auth_code(db, phone_number="01012345678", code=code, now=later)


def test_시도_횟수를_초과하면_코드가_잠긴다(db: Session):
    code = issue_auth_code(db, phone_number="01012345678")
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(5):
        with pytest.raises(AuthError):
            verify_auth_code(db, phone_number="01012345678", code=wrong)

    # 올바른 코드를 넣어도 더 이상 통과하지 않는다
    with pytest.raises(AuthError):
        verify_auth_code(db, phone_number="01012345678", code=code)


def test_다른_번호로_발급된_코드는_통하지_않는다(db: Session):
    code = issue_auth_code(db, phone_number="01012345678")

    with pytest.raises(AuthError):
        verify_auth_code(db, phone_number="01099999999", code=code)


def test_코드를_재발급하면_직전_코드는_무효가_된다(db: Session):
    old_code = issue_auth_code(db, phone_number="01012345678")
    new_code = issue_auth_code(db, phone_number="01012345678")

    with pytest.raises(AuthError):
        verify_auth_code(db, phone_number="01012345678", code=old_code)
    assert verify_auth_code(db, phone_number="01012345678", code=new_code) is True
