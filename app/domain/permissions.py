"""권한 규칙 — **전체 역할**과 **부서 역할**을 가른다 (4-12 · 도막 4).

## 두 축

| 축 | 어디 | 값 |
|---|---|---|
| 전체 역할 | `users.role` | `admin` · `general`(일반) · `viewer` |
| 부서 역할 | `user_departments.dept_role` — 한 사람에 여러 줄 | `lead` · `member` |

전에는 `users.role` 하나에 넷(`admin·dept_lead·member·viewer`)이 섞여 있어
「총무팀이면서 헤브론 리더」 를 적을 칸이 없었다. 이제 부서 역할은 소속
줄에서 **파생**한다 — `users.role` 에는 안 적는다(같은 것이 두 곳에 있으면
갈린다).

## 이 파일이 유일한 창구다

**`user_departments` 를 읽고 쓰는 곳은 여기뿐이다.** 다른 파일은
`my_dept_keys(user)` · `is_lead_of(user, key)` · `leads_of(db, key)` 처럼
여기 함수를 부른다. 표를 직접 읽는 자리가 둘이 되면 「소속」 의 뜻이
갈린다(도막 3 설계표 1-1). `tests/test_stage25.py` 가 그것을 잰다.

부서는 **키**로 비교한다 (2장) — `Department` 행은 회차마다 새로 만들어져
id 로 견주면 새 회차가 열리는 순간 전부 남의 부서가 된다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

    from app.models import Department, User

# ── 전체 역할 (users.role) ────────────────────────────────────────
ADMIN = "admin"
GENERAL = "general"
VIEWER = "viewer"
ALL_ROLES = (ADMIN, GENERAL, VIEWER)

ROLE_LABELS = {
    ADMIN: "총무팀(관리자)",
    GENERAL: "일반",
    VIEWER: "열람 전용",
}

# ── 부서 역할 (user_departments.dept_role) ───────────────────────
LEAD = "lead"
MEMBER = "member"
DEPT_ROLES = (LEAD, MEMBER)
DEPT_ROLE_LABELS = {LEAD: "리더", MEMBER: "팀원"}

# 옛 `users.role` 값 → (전체 역할, 부서 역할). 옮기는 스크립트와 시험
# 도우미가 쓴다 — 옛 시험이 `role="dept_lead"` 로 부르면 그대로 통과해야 한다.
LEGACY_ROLE_MAP = {
    "dept_lead": (GENERAL, LEAD),
    "member": (GENERAL, MEMBER),
}


# ── 전체 역할 판정 ────────────────────────────────────────────────

def _role_of(user_or_role) -> str:
    """`User` 든 역할 문자열이든 받는다 — 부르는 쪽이 둘 다 있다."""
    return user_or_role if isinstance(user_or_role, str) else user_or_role.role


def is_admin(user_or_role) -> bool:
    """총무팀인가. **문자열 `"admin"` 을 밖에서 견주지 않는다** — 여기 하나다."""
    return _role_of(user_or_role) == ADMIN


def is_viewer(user_or_role) -> bool:
    return _role_of(user_or_role) == VIEWER


def can_manage_retreat(user_or_role) -> bool:
    """회차 생성/복제, 부서·예산 카테고리 관리 권한."""
    return is_admin(user_or_role)


def can_see_account(user_or_role) -> bool:
    """**지출자 계좌를 볼 수 있는가.** 화면·엑셀·칩·등록 폼이 이것 하나를 부른다.

    지출을 등록하는 것과 남이 적은 계좌를 읽는 것은 다른 일이라, 편집자
    (부서 리더·팀원)도 못 본다. 지금은 총무팀과 같은 줄이지만 **이름이 다른
    물음**이라 따로 둔다 — `can_manage_retreat` 를 그대로 쓰면 「회차를 만들
    수 있는가」 가 바뀔 때 계좌까지 함께 움직인다.
    """
    return is_admin(user_or_role)


def can_manage_users(user_or_role) -> bool:
    """사용자 초대 및 역할 변경 권한."""
    return is_admin(user_or_role)


# ── 소속 (user_departments) — 읽는 곳은 여기뿐 ──────────────────

def memberships(user: User) -> list:
    """그 사람의 소속 줄 전부 (`UserDepartment`). 다른 파일은 이것도 직접
    안 만진다 — 아래 함수들이 답을 낸다."""
    return list(user.departments or [])


def my_dept_keys(user: User | None) -> set[str]:
    """내 부서 **키 집합**. 소속이 없으면 빈 집합.

    「내 부서인가」 를 묻던 자리는 전부 「내 부서 **중 하나**인가」 가 된다
    (도막 3 설계표 1-1).
    """
    if user is None:
        return set()
    return {m.department.key for m in memberships(user)
            if m.department is not None and m.department.key}


def lead_keys(user: User | None) -> set[str]:
    """내가 **리더**인 부서 키 집합."""
    if user is None:
        return set()
    return {m.department.key for m in memberships(user)
            if m.dept_role == LEAD and m.department is not None and m.department.key}


def _rows_of_key(user: User | None, key: str | None) -> list:
    """같은 키의 소속 줄 전부 — **회차를 가리지 않는다.** 같은 키의 다른 회차
    부서 행도 같은 소속이다(모델의 그 말). 쓰기(`assign`·`unassign`)가 키로
    맞추므로 보통 한 줄이지만, 옛 자료에 둘이 있어도 답이 갈리지 않게 한다."""
    if user is None or not key:
        return []
    return [m for m in memberships(user) if m.department is not None and m.department.key == key]


def dept_role_of(user: User | None, key: str | None) -> str | None:
    """그 부서에서의 내 역할 (`lead`·`member`) — 소속이 아니면 None.
    줄이 둘이면 리더가 이긴다 — `lead_keys` 와 같은 답이어야 한다."""
    rows = _rows_of_key(user, key)
    if not rows:
        return None
    return LEAD if any(m.dept_role == LEAD for m in rows) else MEMBER


def primary_key(user: User | None) -> str | None:
    """대표 부서 키 하나 — 리더인 부서가 먼저, 없으면 첫 소속(가나다). 칸 하나를
    미리 골라 둘 자리(업무 추가의 담당 부서)가 쓴다. 소속이 없으면 None."""
    return (sorted(lead_keys(user)) or sorted(my_dept_keys(user)) or [None])[0]


def is_lead_of(user: User | None, key: str | None) -> bool:
    return dept_role_of(user, key) == LEAD


def is_member_of(user: User | None, key: str | None) -> bool:
    """리더든 팀원이든 그 부서 소속인가."""
    return dept_role_of(user, key) is not None


def roles_by_key(user: User | None) -> dict[str, str]:
    """내 소속 전부를 「부서 키 → 부서 역할」 로. 설정 › 사용자 폼이 선택 값을 채운다."""
    if user is None:
        return {}
    return {m.department.key: m.dept_role for m in memberships(user)
            if m.department is not None and m.department.key}


def membership_names(user: User | None, *, dept_names: dict[str, str] | None = None
                     ) -> list[tuple[str, str, str]]:
    """소속 줄마다 (키, 부서 이름, 역할 라벨). 화면이 표시만 할 때 쓴다 —
    `describe` 는 한 줄로 붙인 것이고 이것은 낱개다."""
    out = []
    for m in memberships(user) if user is not None else []:
        if m.department is None:
            continue
        name = (dept_names or {}).get(m.department.key) or m.department.name
        out.append((m.department.key, name, DEPT_ROLE_LABELS.get(m.dept_role, m.dept_role)))
    return out


def first_department(user: User | None):
    """대표 부서 행 하나 — 리더인 부서가 먼저, 없으면 첫 소속. 색 점처럼 **하나만**
    그릴 자리가 쓴다. 소속이 없으면 None."""
    rows = [m for m in (memberships(user) if user is not None else []) if m.department is not None]
    if not rows:
        return None
    rows.sort(key=lambda m: (0 if m.dept_role == LEAD else 1, m.department_id))
    return rows[0].department


def is_readonly(user: User | None) -> bool:
    """열람 전용인가 — **admin 이 아니고, viewer 이거나 소속이 없으면** 참 (②).

    소속 없는 일반은 편집자가 아니다. 부서 없는 업무(「나중에 정하자」)는
    총무팀 소관이라, 아무 데도 안 붙은 사람이 그것을 만들 수 있게 두면
    권한이 넓어진다.
    """
    if user is None:
        return True
    if is_admin(user):
        return False
    if is_viewer(user):
        return True
    return not my_dept_keys(user)


def can_edit_department_key(user: User | None, target_key: str | None) -> bool:
    """부서에 귀속되는 내용(업무·지출·체크리스트·첨부)을 고칠 수 있는가.

    admin 은 전부. 나머지는 열람 전용이 아니고 **대상 부서가 내 부서 중
    하나**일 때. 부서가 없는 항목(`target_key` 없음)은 총무팀 소관이다.
    키 없는 부서(구설계 데이터)는 견줄 근거가 없으므로 admin 만 —
    None == None 으로 남의 부서까지 통과시키면 안 된다.
    """
    if user is None:
        return False
    if is_admin(user):
        return True
    if is_readonly(user) or not target_key:
        return False
    return target_key in my_dept_keys(user)


def eager_load():
    """세션이 닫힌 뒤 화면이 소속을 읽는 자리(오류 화면)에서 미리 같이 로드할 옵션.
    표 이름을 밖에서 적지 않으려고 여기 둔다."""
    from sqlalchemy.orm import joinedload

    from app.models import User

    return joinedload(User.departments)


# ── 부서 쪽에서 사람 찾기 ────────────────────────────────────────

def _rows_for_key(db: Session, key: str | None, *, active_only: bool = True) -> list:
    from sqlalchemy import select

    from app.models import Department, User, UserDepartment

    if not key:
        return []
    q = (
        select(UserDepartment)
        .join(Department, Department.id == UserDepartment.department_id)
        .join(User, User.id == UserDepartment.user_id)
        .where(Department.key == key)
        .order_by(User.id)
    )
    if active_only:
        q = q.where(User.is_active)
    return list(db.scalars(q))


def members_of(db: Session, key: str | None, *, dept_role: str | None = None,
               active_only: bool = True) -> list[User]:
    """그 부서 키에 속한 사람들 — **모든 회차의** 같은 키 부서 행을 다 본다.
    같은 사람이 회차 둘의 같은 부서에 붙어 있어도 한 번만 낸다."""
    seen, out = set(), []
    for m in _rows_for_key(db, key, active_only=active_only):
        if dept_role is not None and m.dept_role != dept_role:
            continue
        if m.user_id in seen:
            continue
        seen.add(m.user_id)
        out.append(m.user)
    return out


def leads_of(db: Session, key: str | None) -> list[User]:
    """그 부서의 리더 **전부** (⑤ — 리더가 둘이면 둘 다). 활성 계정만."""
    return members_of(db, key, dept_role=LEAD)


def admins(db: Session, *, active_only: bool = True) -> list[User]:
    """총무팀 전원 — `users.role == admin` 을 밖에서 견주지 않는다."""
    from sqlalchemy import select

    from app.models import User

    q = select(User).where(User.role == ADMIN).order_by(User.id)
    if active_only:
        q = q.where(User.is_active)
    return list(db.scalars(q))


# ── 소속 쓰기 — 쓰는 곳도 여기뿐 ─────────────────────────────────

def assign(db: Session, user: User, department: Department, dept_role: str = MEMBER):
    """소속 줄 하나를 놓는다. **같은 키의 줄이 있으면 그 줄의 역할만 맞춘다** —
    회차가 달라도 같은 키면 같은 소속이라 줄을 하나 더 만들지 않는다. 키 없는
    부서(구설계)만 행 id 로 본다."""
    from app.models import UserDepartment

    if dept_role not in DEPT_ROLES:
        raise ValueError(f"모르는 부서 역할: {dept_role}")
    have = _rows_of_key(user, department.key) if department.key else \
        [m for m in memberships(user) if m.department_id == department.id]
    if have:
        for m in have:
            m.dept_role = dept_role
        return have[0]
    m = UserDepartment(user_id=user.id, department_id=department.id, dept_role=dept_role)
    db.add(m)
    user.departments.append(m)
    return m


def unassign(db: Session, user: User, department: Department) -> bool:
    """같은 키의 소속 줄을 **전부** 뗀다 (키 없는 부서는 행 id 로)."""
    rows = _rows_of_key(user, department.key) if department.key else \
        [m for m in memberships(user) if m.department_id == department.id]
    for m in list(rows):
        user.departments.remove(m)
        db.delete(m)
    return bool(rows)


def unassign_keys(db: Session, user: User, keys: set[str]) -> list[str]:
    """부서 키로 소속을 뗀다 — 이번 회차에 없는(지난 회차) 소속을 사람이 **골라서**
    뗄 때 쓴다. `set_memberships` 는 이번 회차 부서만 만지므로 이 길이 따로 있다."""
    뗌 = []
    for m in list(memberships(user)):
        if m.department is not None and m.department.key in keys:
            user.departments.remove(m)
            db.delete(m)
            뗌.append(m.department.key)
    return 뗌


def set_memberships(db: Session, user: User, wanted: dict[str, str],
                    *, among: list[Department]) -> tuple[list[str], list[str]]:
    """`among`(이번 회차의 부서 행들) 안에서 소속을 `wanted`(키 → 부서 역할)에
    맞춘다. **`among` 밖의 소속(지난 회차 부서)은 건드리지 않는다** — 권한만
    고치려고 저장했을 때 지난 회차 소속이 조용히 지워지면 안 된다.

    돌려주는 것: (붙인 키들, 뗀 키들) — 활동 기록에 **바뀐 것만** 적기 위해서.
    """
    붙임, 뗌 = [], []
    by_key = {d.key: d for d in among if d.key}
    for key, dept in by_key.items():
        want = wanted.get(key)
        have = dept_role_of(user, key)          # 같은 키의 줄 — 어느 회차 행이든
        if want and want not in DEPT_ROLES:
            raise ValueError(f"모르는 부서 역할: {want}")
        if want and have != want:
            assign(db, user, dept, want)          # 있으면 그 줄의 역할만 바뀐다
            붙임.append(f"{key}:{want}")
        elif not want and have is not None:
            unassign(db, user, dept)              # 같은 키의 줄을 전부 뗀다
            뗌.append(key)
    return 붙임, 뗌


def describe(user: User, *, dept_names: dict[str, str] | None = None) -> str:
    """사이드바 카드·표에 낼 한 줄 — 「헤브론 리더 · 총무팀」. 소속이 없으면 빈 문자열."""
    parts = []
    for m in memberships(user):
        if m.department is None:
            continue
        name = (dept_names or {}).get(m.department.key) or m.department.name
        parts.append(f"{name} {DEPT_ROLE_LABELS[LEAD]}" if m.dept_role == LEAD else name)
    return " · ".join(parts)
