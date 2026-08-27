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
