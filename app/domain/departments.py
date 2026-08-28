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
