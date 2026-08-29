"""역할 기반 권한 규칙 (순수 함수 — DB/요청 객체에 의존하지 않음)."""

ADMIN = "admin"
DEPT_LEAD = "dept_lead"
MEMBER = "member"
VIEWER = "viewer"

ALL_ROLES = (ADMIN, DEPT_LEAD, MEMBER, VIEWER)

ROLE_LABELS = {
    ADMIN: "총무팀(관리자)",
    DEPT_LEAD: "부서 리더",
    MEMBER: "부서원",
    VIEWER: "열람 전용",
}

_EDITOR_ROLES = (DEPT_LEAD, MEMBER)


def can_manage_retreat(role: str) -> bool:
    """회차 생성/복제, 부서·예산 카테고리 관리 권한."""
    return role == ADMIN


def can_manage_users(role: str) -> bool:
    """사용자 초대 및 역할 변경 권한."""
    return role == ADMIN


def is_readonly(role: str) -> bool:
    return role not in (ADMIN, DEPT_LEAD, MEMBER)


def can_edit_department_content(
    *, role: str, user_department_id: int | None, target_department_id: int | None
) -> bool:
    """Task·지출 등 부서에 귀속되는 내용의 편집 권한.

    부서가 지정되지 않은 항목(target_department_id=None)은 총무팀 소관으로 본다.
    """
    if role == ADMIN:
        return True
    if role not in _EDITOR_ROLES:
        return False
    if user_department_id is None or target_department_id is None:
        return False
    return user_department_id == target_department_id


def can_edit_department_by_key(
    *, role: str, user_department_key: str | None, target_department_key: str | None
) -> bool:
    """부서 소속은 **키**로 비교한다.

    Department 행은 회차마다 새로 만들어지므로 id 로 비교하면 새 회차가 열리는
    순간 모든 부서 리더가 자기 부서 업무조차 손대지 못하게 된다.
    회차를 넘어 같은 부서임을 알아보는 것은 key 뿐이다.
    """
    if role == ADMIN:
        return True
    if role not in _EDITOR_ROLES:
        return False
    if not user_department_key or not target_department_key:
        return False
    return user_department_key == target_department_key
