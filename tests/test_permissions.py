"""권한 규칙 — 전체 역할과 부서 역할 (도막 4).

`permissions` 는 이제 사람(`User`)을 받는다 — 부서 역할이 소속 줄에서
파생되기 때문이다. 순수 함수 시험은 DB 없이 가짜 소속을 붙여 잰다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domain.permissions import (
    ADMIN, GENERAL, LEAD, MEMBER, VIEWER,
    can_edit_department_key, can_manage_retreat, can_manage_users, can_see_account,
    is_lead_of, is_readonly, lead_keys, my_dept_keys,
)


def _user(role, *memberships):
    """가짜 사람 — memberships 는 (부서 키, 부서 역할)."""
    return SimpleNamespace(
        role=role,
        departments=[SimpleNamespace(dept_role=r, department=SimpleNamespace(key=k), department_id=i)
                     for i, (k, r) in enumerate(memberships, 1)],
    )


def test_admin은_회차_설정을_관리할_수_있다():
    assert can_manage_retreat(ADMIN) is True
    assert can_manage_retreat(_user(ADMIN)) is True


@pytest.mark.parametrize("role", [GENERAL, VIEWER])
def test_admin이_아니면_회차_설정을_관리할_수_없다(role):
    assert can_manage_retreat(role) is False


def test_admin만_사용자_역할을_관리할_수_있다():
    assert can_manage_users(ADMIN) is True
    assert can_manage_users(GENERAL) is False


def test_계좌는_admin만_본다():
    assert can_see_account(_user(ADMIN)) is True
    assert can_see_account(_user(GENERAL, ("hebron", LEAD))) is False


def test_viewer는_읽기_전용이다():
    assert is_readonly(_user(VIEWER)) is True
    assert is_readonly(_user(VIEWER, ("hebron", LEAD))) is True, "viewer 는 소속이 있어도 열람 전용"


def test_소속_없는_일반은_읽기_전용이다():
    """② — 부서 없는 업무는 총무팀 소관이라, 아무 데도 안 붙은 사람이 편집자면 넓어진다."""
    assert is_readonly(_user(GENERAL)) is True
    assert is_readonly(_user(GENERAL, ("hebron", MEMBER))) is False


def test_admin은_소속이_있어도_없어도_읽기_전용이_아니다():
    assert is_readonly(_user(ADMIN)) is False
    assert is_readonly(_user(ADMIN, ("hebron", LEAD))) is False


def test_두_부서_사람은_두_부서를_고치고_셋째는_못_고친다():
    u = _user(GENERAL, ("hebron", LEAD), ("sketch", MEMBER))
    assert my_dept_keys(u) == {"hebron", "sketch"}
    assert lead_keys(u) == {"hebron"}
    assert is_lead_of(u, "hebron") is True
    assert is_lead_of(u, "sketch") is False
    assert can_edit_department_key(u, "hebron") is True
    assert can_edit_department_key(u, "sketch") is True
    assert can_edit_department_key(u, "koram") is False


def test_부서_미지정_내용은_admin만_편집할_수_있다():
    assert can_edit_department_key(_user(ADMIN), None) is True
    assert can_edit_department_key(_user(GENERAL, ("hebron", LEAD)), None) is False


def test_키_없는_부서는_admin만():
    """구설계 데이터 — None == None 으로 남의 부서까지 통과시키면 안 된다."""
    assert can_edit_department_key(_user(GENERAL, ("hebron", LEAD)), "") is False


def test_admin은_모든_부서_내용을_편집할_수_있다():
    assert can_edit_department_key(_user(ADMIN), "koram") is True
    assert can_edit_department_key(_user(ADMIN, ("hebron", MEMBER)), "koram") is True
