"""역할 기반 권한 규칙 테스트.

CLAUDE.md 3-3 기준:
  admin      = 전체
  dept_lead  = 자기 부서 Task·예산만 편집
  member     = 자기 부서 Task·예산만 편집
  viewer     = 읽기 전용
"""
import pytest

from app.domain.permissions import (
    ADMIN,
    DEPT_LEAD,
    MEMBER,
    VIEWER,
    can_edit_department_content,
    can_manage_retreat,
    can_manage_users,
    is_readonly,
)


def test_admin은_회차_설정을_관리할_수_있다():
    assert can_manage_retreat(ADMIN) is True


@pytest.mark.parametrize("role", [DEPT_LEAD, MEMBER, VIEWER])
def test_admin이_아니면_회차_설정을_관리할_수_없다(role):
    assert can_manage_retreat(role) is False


def test_admin만_사용자_역할을_관리할_수_있다():
    assert can_manage_users(ADMIN) is True
    assert can_manage_users(DEPT_LEAD) is False


def test_viewer는_읽기_전용이다():
    assert is_readonly(VIEWER) is True
    assert is_readonly(MEMBER) is False


def test_부서리더는_자기_부서_내용을_편집할_수_있다():
    assert can_edit_department_content(
        role=DEPT_LEAD, user_department_id=3, target_department_id=3
    ) is True


def test_부서리더는_타_부서_내용을_편집할_수_없다():
    assert can_edit_department_content(
        role=DEPT_LEAD, user_department_id=3, target_department_id=4
    ) is False


def test_부서원은_자기_부서_내용을_편집할_수_있다():
    assert can_edit_department_content(
        role=MEMBER, user_department_id=3, target_department_id=3
    ) is True


def test_viewer는_자기_부서_내용도_편집할_수_없다():
    assert can_edit_department_content(
        role=VIEWER, user_department_id=3, target_department_id=3
    ) is False


def test_admin은_모든_부서_내용을_편집할_수_있다():
    assert can_edit_department_content(
        role=ADMIN, user_department_id=None, target_department_id=99
    ) is True


def test_부서_미지정_내용은_admin만_편집할_수_있다():
    # 부서가 지정되지 않은 독립 Task/예산은 총무팀 소관
    assert can_edit_department_content(
        role=ADMIN, user_department_id=None, target_department_id=None
    ) is True
    assert can_edit_department_content(
        role=DEPT_LEAD, user_department_id=3, target_department_id=None
    ) is False


def test_소속_부서가_없는_사용자는_부서_내용을_편집할_수_없다():
    assert can_edit_department_content(
        role=MEMBER, user_department_id=None, target_department_id=3
    ) is False


def test_알_수_없는_역할은_거부한다():
    assert can_manage_retreat("superuser") is False
    assert can_edit_department_content(
        role="superuser", user_department_id=1, target_department_id=1
    ) is False


def test_부서_소속은_키로_비교해야_한다():
    """Department 행은 회차마다 새로 만들어진다.

    id 로 비교하면 새 회차가 열리는 순간 모든 부서 리더가 자기 부서 업무조차
    손대지 못한다. 회차를 넘어 같은 부서임을 알아보는 것은 key 뿐이다.
    """
    from app.domain import permissions as perm

    assert perm.can_edit_department_by_key(
        role="dept_lead", user_department_key="sketch", target_department_key="sketch") is True
    assert perm.can_edit_department_by_key(
        role="dept_lead", user_department_key="sketch", target_department_key="chongmuM") is False
    assert perm.can_edit_department_by_key(
        role="admin", user_department_key=None, target_department_key="sketch") is True
    assert perm.can_edit_department_by_key(
        role="viewer", user_department_key="sketch", target_department_key="sketch") is False
    # 담당 없는 업무는 총무팀 소관
    assert perm.can_edit_department_by_key(
        role="dept_lead", user_department_key="sketch", target_department_key=None) is False
