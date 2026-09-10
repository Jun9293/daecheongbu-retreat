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


def next_team_key(db) -> str:
    """새 부서에 회차를 넘어 쓸 키(`team1`, `team2` …)를 발급한다 (6-6).

    한글 이름으로는 안전한 키를 만들 수 없으므로 번호를 붙인다. **키 없는 부서를
    만드는 길을 두지 않는다** — 소속·알림·권한이 전부 키로 도는데(2장) 키가 비면
    그 부서 사람은 아무것도 못 받고 아무 오류도 안 난다. 마법사와 설정 › 부서가
    같이 쓴다."""
    from sqlalchemy import select

    from app.models import Department

    used = {d.key for d in db.scalars(select(Department)) if d.key}
    used |= {k for k, _, _ in DEPARTMENT_MASTER}
    n = 1
    while f"team{n}" in used:
        n += 1
    return f"team{n}"


def department_keys_of(user) -> set[str]:
    """그 사람의 부서 **키 집합** — 회차가 바뀌어도 이것만은 그대로다.

    한 사람에 여러 부서가 붙는다(도막 4). 「키 하나」 를 돌려주던
    옛 「한 사람 → 키 하나」 함수는 없앴다 — 같은 이름으로 집합을 돌려주면
    `== my_key` 로 견주던 자리가 **조용히 항상 거짓**이 된다.
    표를 읽는 것은 `permissions` 가 한다 — 여기는 이름만 빌려준다.
    """
    from app.domain import permissions as perm

    return perm.my_dept_keys(user)


def users_in_department(db, key: str | None, *, dept_role: str | None = None) -> list:
    """그 부서 키에 속한 사람들 (활성) — `permissions.members_of` 그대로."""
    from app.domain import permissions as perm

    return perm.members_of(db, key, dept_role=dept_role)
