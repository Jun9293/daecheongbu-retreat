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


def can_see_account(role: str) -> bool:
    """**지출자 계좌를 볼 수 있는가.** 화면·엑셀·칩이 이것 하나를 부른다.

    지출을 등록하는 것과 남이 적은 계좌를 읽는 것은 다른 일이라, 편집자
    (부서 리더·부서원)도 못 봅니다. 지금은 총무팀과 같은 줄이지만 **이름이
    다른 물음**이라 따로 둡니다 — `can_manage_retreat` 를 그대로 쓰면
    「회차를 만들 수 있는가」 가 바뀔 때 계좌까지 함께 움직입니다.

    **두 곳에서 정하면 갈립니다.** 실제로 화면은 계좌만 빼고 누구나 보는데
    파일은 통째로 막혀 있어서, 같은 표인데 보는 사람이 달랐습니다 (5-8).
    """
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
