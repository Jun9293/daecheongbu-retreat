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
    rows: list = field(default_factory=list)        # 미완료 — 정렬 순
    done_rows: list = field(default_factory=list)   # 완료 — 기본 접힘 (4-14)
    state_counts: dict = field(default_factory=dict)
    dept_counts: list = field(default_factory=list)
    state: str = ""
    dept: str = ""
    sort: str = "date"                              # 'date' | 'name' (4-14)
    dir: str = "asc"                                # 'asc' | 'desc'
    total: int = 0

    @property
    def default_sort(self) -> bool:
        """기본 정렬(시작일 오름)이면 주소에 sort 를 싣지 않는다 — 알림의
        바로가기 주소가 정렬 파라미터로 길어질 이유가 없다."""
        return self.sort == "date" and self.dir == "asc"

    @property
    def state_labels(self):
        """칩 순서대로 (값, 이름). 이름을 화면에 직접 적으면 상태 분기가
        템플릿으로 새어 들어간다 (4-3) — 여기 한 곳에서 나간다."""
        return [(s, STATE_LABELS[s]) for s in STATE_ORDER]


def _sort_key(run: TaskRun):
    """시작일 순 (4-14 · 6-6). 날짜 없는 것은 뒤로 — 조용히 빼지 않는다."""
    start = run.start_date or run.end_date
    return (start is None, start or dt.date.max, run.id)


def _row(run: TaskRun, today: dt.date, *, dim_key: str | None,
         can_edit=None) -> dict:
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
        # 행 배지에서 상태를 바로 바꿀 수 있는가 (4-14) — **보드·드로어와
        # 같은 문**이다. 못 바꾸는 사람에게는 누를 것처럼 보이지 않는다
        "can_edit": True if can_edit is None else bool(can_edit(run)),
    }


def build(
    db: Session,
    retreat: Retreat,
    *,
    today: dt.date,
    my_key: str | None,
    dim: bool = True,
    state: str = "",
    dept: str = "",
    sort: str = "date",
    dir: str = "asc",
    can_edit=None,
) -> ListView:
    """my_key 는 소속 외 흐림의 기준, dim 은 그 흐림을 켤지다.

    총무팀(admin)은 dim=False 로 전부 선명하게 본다 — 홈(4-15)·옛 화면과
    같은 규칙이다. 정렬은 날짜(기본 · 시작일)·이름 두 축, 오름/내림 (4-14) —
    모르는 값은 기본으로 떨어뜨린다.

    **부서를 고르는 자리는 드롭다운 하나다** (4-14). 전에는 「내 부서 /
    전체」 칩과 부서 드롭다운이 같은 일을 나눠 가졌는데, 같은 것을 두
    곳에서 고르면 둘이 어긋날 때 어느 쪽이 이겼는지 화면이 말해 주지
    않는다. 드롭다운이 곧 범위다 — 내 부서를 고르면 옛 「내 부서」 다.
    """
    if sort not in ("date", "name"):
        sort = "date"
    if dir not in ("asc", "desc"):
        dir = "asc"
    key = _sort_key if sort == "date" else (lambda r: (r.library.title, r.id))
    runs = sorted(
        db.scalars(
            select(TaskRun).where(
                TaskRun.retreat_id == retreat.id, TaskRun.included
            )
        ),
        key=key,
        reverse=(dir == "desc"),
    )

    if state not in STATE_LABELS:
        state = ""

    def key_of(run: TaskRun) -> str | None:
        return run.department.key if run.department else None

    badge_of = {r.id: board.paint_of(r, today)["badge"]["cls"] for r in runs}

    # **부서 건수는 부서를 고르기 전 전체에서 센다** — 한 부서를 보는
    # 중에도 다른 부서로 옮겨 갈 수 있어야 한다 (상태 칩과 같은 이유)
    dept_counts = []
    for d in sorted(retreat.departments, key=lambda d: d.sort_order):
        n = sum(1 for r in runs if key_of(r) == d.key)
        if n:
            dept_counts.append(
                {"key": d.key, "name": d.name, "color": d.color, "count": n}
            )

    # 부서가 곧 범위다. **상태 건수는 그 안에서 센다** — 「홍보팀 · 대기 3」
    # 처럼 지금 보고 있는 것을 말해야 한다
    scoped = [r for r in runs if not dept or key_of(r) == dept]
    state_counts = {s: sum(1 for r in scoped if badge_of[r.id] == s) for s in STATE_ORDER}

    picked = scoped
    if state:
        picked = [r for r in picked if badge_of[r.id] == state]

    rows = [_row(r, today, dim_key=my_key if dim else None, can_edit=can_edit)
            for r in picked]
    return ListView(
        rows=[r for r in rows if r["badge"]["cls"] != "done"],
        done_rows=[r for r in rows if r["badge"]["cls"] == "done"],
        state_counts=state_counts,
        dept_counts=dept_counts,
        state=state,
        dept=dept,
        sort=sort,
        dir=dir,
        total=len(scoped),
    )
