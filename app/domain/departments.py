"""부서 기본 목록 (CLAUDE.md 2장 — 확정된 결정사항).

봉사팀 공통은 해체했다. 실제로는 특정 팀이 주관하는데 '공통'으로 묶여 있어
담당이 모호했기 때문이다. 부서는 회차마다 새로 만들어지지만 `key` 는 회차를
넘어 같은 값을 쓴다 — 라이브러리 업무가 이 키로 담당 부서를 가리킨다.
"""

from __future__ import annotations

# (key, 이름, 색)
DEPARTMENT_MASTER: tuple[tuple[str, str, str], ...] = (
    ("chongmuM", "1 총무M", "#2F4858"),
    ("chongmu", "1 총무팀", "#77848F"),
    ("seongyo", "3 선교사회", "#3B6EA5"),
    ("sketch", "4 스케치", "#B95A83"),
    ("hebron", "5 헤브론", "#4A8A5C"),
    ("koram", "6 코람데오", "#B44B42"),
    ("jaejeong", "7 재정", "#8A6A4F"),
    ("gaegija", "8 개기자", "#7A5BA6"),
    ("saechingu", "9 새친구팀", "#A98A1E"),
)

DEPARTMENT_NAMES = {key: name for key, name, _ in DEPARTMENT_MASTER}
DEPARTMENT_COLORS = {key: color for key, _, color in DEPARTMENT_MASTER}


def short_name(name: str) -> str:
    """'4 스케치' → '스케치'. 좁은 자리에 담당팀을 표시할 때 쓴다."""
    head, _, rest = name.partition(" ")
    return rest or head


# ── 소속은 키로 본다 (CLAUDE.md 2장) ─────────────────────────────────
#
# Department 행은 회차마다 새로 만들어진다. id 로 비교하면 새 회차가 열리는
# 순간 어긋나는데, 그 실패가 **조용하다** — 아무 오류도 나지 않고 그냥 못 찾는다.
# 회차를 넘어 같은 부서임을 알아보는 것은 key 뿐이다.


def department_key_of(db, user) -> str | None:
    """그 사람의 부서 키. 회차가 바뀌어도 이것만은 그대로다."""
    from app.models import Department

    if user is None or user.department_id is None:
        return None
    dept = db.get(Department, user.department_id)
    return dept.key if dept else None


def users_in_department(db, key: str | None, *, role: str | None = None) -> list:
    """그 부서 키에 속한 사람들.

    User.department_id 는 계정을 만들 때의 회차 행을 가리키므로, 같은 키를 가진
    **모든 회차의** Department 행 id 를 모아서 찾아야 한다.
    """
    from sqlalchemy import select

    from app.models import Department, User

    if not key:
        return []
    dept_ids = list(db.scalars(select(Department.id).where(Department.key == key)))
    if not dept_ids:
        return []
    query = select(User).where(User.department_id.in_(dept_ids))
    if role is not None:
        query = query.where(User.role == role)
    return list(db.scalars(query.order_by(User.id)))
