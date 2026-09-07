"""목록 보기 (CLAUDE.md 4-14) — 같은 TaskRun 을 순서 축으로 본다.

숫자를 화면에서 다시 세지 않는다. 배지는 board.paint_of 한 곳에서 나온다
(4-3) — 기한이 지났으면 '지연' 이고, 그것은 저장값이 아니라 계산값이다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import board
from app.models import Retreat, TaskRun

# 칩과 주소의 상태 값 — 배지의 CSS 클래스와 같은 이름을 쓴다 (4-0 의 --st-*).
# '지연'(late)은 저장값이 아니라 계산값이므로, 여기서도 배지 이름으로 거른다.
STATE_LABELS = {"wait": "대기", "prog": "진행중", "done": "완료", "late": "지연"}
STATE_ORDER = ("wait", "prog", "done", "late")


@dataclass
class ListView:
    rows: list = field(default_factory=list)        # 미완료 — 시작일 순
    done_rows: list = field(default_factory=list)   # 완료 — 기본 접힘 (4-14)
    state_counts: dict = field(default_factory=dict)
    dept_counts: list = field(default_factory=list)
    scope: str = "all"
    state: str = ""
    dept: str = ""
    total: int = 0

    @property
    def state_labels(self):
        """칩 순서대로 (값, 이름). 이름을 화면에 직접 적으면 상태 분기가
        템플릿으로 새어 들어간다 (4-3) — 여기 한 곳에서 나간다."""
        return [(s, STATE_LABELS[s]) for s in STATE_ORDER]


def _sort_key(run: TaskRun):
    """시작일 순 (4-14 · 6-6). 날짜 없는 것은 뒤로 — 조용히 빼지 않는다."""
    start = run.start_date or run.end_date
    return (start is None, start or dt.date.max, run.id)


def _row(run: TaskRun, today: dt.date, *, dim_key: str | None) -> dict:
    paint = board.paint_of(run, today)
    end = run.end_date or run.start_date
    done = run.status == "완료"
    dday = None
    if end and not done:
        # 완료에는 D+N 을 붙이지 않는다 (4-14) — 끝난 일의 경과일은 재촉이다
        diff = (end - today).days
        dday = "D-day" if diff == 0 else (f"D-{diff}" if diff > 0 else f"D+{-diff}")
    dept = run.department
    return {
        "run_id": run.id,
        "no": run.run_no,        # 회차 안에서 고정 (4-14) — 회의에서 번호로 부른다
        "title": run.library.title,
        "kind_label": run.library.kind_label,
        "dept": (
            {"key": dept.key, "name": dept.name, "color": dept.color} if dept else None
        ),
        "assignee": run.assignee.name if run.assignee else None,
        "end": end,
        "dday": dday,
        "badge": paint["badge"],
        # 소속 외는 숨기지 않고 흐리게 (1장) — 부서는 키로 비교한다 (2장).
        # dim_key 가 없으면(총무팀 등) 전부 선명하다 — 홈과 같은 규칙 (4-15)
        "dim": bool(dim_key and (dept.key if dept else None) != dim_key),
    }


def build(
    db: Session,
    retreat: Retreat,
    *,
    today: dt.date,
    my_key: str | None,
    dim: bool = True,
    scope: str = "all",
    state: str = "",
    dept: str = "",
) -> ListView:
    """my_key 는 「내 부서」 칩의 기준, dim 은 소속 외 흐림을 켤지다.

    총무팀(admin)은 dim=False 로 전부 선명하게 본다 — 홈(4-15)·옛 화면과
    같은 규칙이다. 흐림을 끄더라도 「내 부서」 칩은 소속이 있으면 동작한다.
    """
    runs = sorted(
        db.scalars(
            select(TaskRun).where(
                TaskRun.retreat_id == retreat.id, TaskRun.included
            )
        ),
        key=_sort_key,
    )

    # 소속이 없으면 '내 부서' 는 고를 것이 없다 — 전체로 떨어뜨린다
    if scope == "mine" and not my_key:
        scope = "all"
    if state not in STATE_LABELS:
        state = ""

    def key_of(run: TaskRun) -> str | None:
        return run.department.key if run.department else None

    scoped = [r for r in runs if scope != "mine" or key_of(r) == my_key]

    # 칩의 건수는 **거른 뒤가 아니라 거르기 전** 범위에서 센다 — 상태 칩을
    # 누른 채로도 다른 상태의 건수가 보여야 이동할 수 있다.
    badge_of = {r.id: board.paint_of(r, today)["badge"]["cls"] for r in scoped}
    state_counts = {s: sum(1 for r in scoped if badge_of[r.id] == s) for s in STATE_ORDER}

    dept_counts = []
    for d in sorted(retreat.departments, key=lambda d: d.sort_order):
        n = sum(1 for r in scoped if key_of(r) == d.key)
        if n:
            dept_counts.append(
                {"key": d.key, "name": d.name, "color": d.color, "count": n}
            )

    picked = scoped
    if state:
        picked = [r for r in picked if badge_of[r.id] == state]
    if dept:
        picked = [r for r in picked if key_of(r) == dept]

    rows = [_row(r, today, dim_key=my_key if dim else None) for r in picked]
    return ListView(
        rows=[r for r in rows if r["badge"]["cls"] != "done"],
        done_rows=[r for r in rows if r["badge"]["cls"] == "done"],
        state_counts=state_counts,
        dept_counts=dept_counts,
        scope=scope,
        state=state,
        dept=dept,
        total=len(scoped),
    )
