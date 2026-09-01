"""준비 단계 보드의 뷰 모델 (CLAUDE.md 4장, 시각 스펙 retreat-board-v4.html).

가로축은 D-13주~D-3주까지 주 단위, D-2주부터 개회일까지 하루 단위,
마지막에 수련회 기간 한 칸. 주 단위를 쓰는 이유는 봉사자들이 주말에만
모이기 때문이다 — 편의가 아니라 실제 리듬이다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain import dweek
from app.domain.departments import short_name
from app.models import Retreat, TaskLibrary, TaskRun

WEEKDAYS = ("일", "월", "화", "수", "목", "금", "토")

STATUS_COLORS = {
    "대기": "#4A544F",
    "진행중": "#1668E3",
    "완료": "#8B948F",
    "지연": "#C8442E",
}

MAX_FIRST_WEEK = 40  # 이보다 이른 업무는 첫 칸에 몰아 넣는다


def tint(hex_color: str, ratio: float) -> str:
    """팀 색을 종이색 쪽으로 흐리게 섞는다. 글자가 검정이므로 연한 톤만 쓴다.

    **읽을 수 없는 색이 와도 보드를 죽이지 않는다.** `#888` 같은 3자리도 CSS 에서는
    멀쩡한 색이고, 부서 색은 사람이 넣는 값이다. 여기서 터지면 그 회차의 보드가
    통째로 500 이 되는데, 원인이 "부서 색이 세 글자" 라는 것을 아무도 짐작하지 못한다.
    """
    raw = (hex_color or "").lstrip("#").strip()
    if len(raw) == 3:                        # #888 → #888888
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        return "rgb(250,251,250)"            # 못 읽으면 종이색
    try:
        r, g, b = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "rgb(250,251,250)"
    mix = lambda v, paper: round(v * ratio + paper * (1 - ratio))  # noqa: E731
    return f"rgb({mix(r, 250)},{mix(g, 251)},{mix(b, 250)})"


# 무채색 기조 (CLAUDE.md 4장 UI 방향).
# **부서 색으로 면을 채우지 않는다** — 왼쪽 점과 바 테두리에만 쓴다.
# 진행중을 팀 색 20% 로 채우던 것을 없앴으므로, 진행중은 화면 쪽에서
# 왼쪽 3px 팀색 마개(.bar.진행중::after)로 구분한다. 상태 4종은 그대로다.
BAR_DONE = ("#F1F0EE", "#E6E5E2")        # 회색 채움 — 눈에 띄지 않게
BAR_LATE = ("#FBF1F0", "#C4554D")        # 옅은 붉은색 + 빨간 테두리
BAR_GHOST_BORDER = "#C9C8C5"
BAR_WIP_BG = "#FAFAF9"                   # 아주 옅은 중립 — 팀 색이 아니다
BAR_TODO_BG = "#FFFFFF"


def bar_style(status: str, color: str, *, kind: str, ghost: bool) -> tuple[str, str]:
    """(배경, 테두리색). 완료를 눈에 띄게 하지 않는 것이 핵심이다 —
    목적이 구멍 방지라면 시선은 미완료로 가야 한다."""
    if ghost:
        return "none", BAR_GHOST_BORDER
    if status == "완료":
        return BAR_DONE
    if status == "지연":
        return BAR_LATE
    if kind == "schedule" or status == "대기":
        return BAR_TODO_BG, color
    return BAR_WIP_BG, color


class Axis:
    """보드 가로축."""

    def __init__(self, open_date: dt.date, close_date: dt.date, first_week: int) -> None:
        self.open_date = open_date
        self.close_date = close_date
        self.first_week = first_week
        self.week_sundays = [
            dweek.week_date(open_date, n)
            for n in range(first_week, dweek.LAST_WEEKLY_D_WEEK - 1, -1)
        ]
        day0 = dweek.week_date(open_date, 2)
        self.days = []
        cursor = day0
        while cursor < open_date:
            self.days.append(cursor)
            cursor += dt.timedelta(days=1)
        self.total = len(self.week_sundays) + len(self.days) + 1

    @property
    def shift_index(self) -> int:
        """주 단위 → 일 단위로 바뀌는 열 번호 (여기에 굵은 세로선)."""
        return len(self.week_sundays) + 1

    def column_of(self, day: dt.date) -> int:
        if day >= self.open_date:
            return self.total
        if self.days and day >= self.days[0]:
            return len(self.week_sundays) + 1 + (day - self.days[0]).days
        sunday = day - dt.timedelta(days=(day.weekday() + 1) % 7)
        index = (sunday - self.week_sundays[0]).days // 7
        return max(1, min(len(self.week_sundays), index + 1))

    def headers(self) -> list[dict]:
        cells = []
        for i, sunday in enumerate(self.week_sundays):
            n = self.first_week - i
            cells.append(
                {
                    "kind": "week",
                    "top": f"D-{n}",
                    "bottom": f"{sunday.month}/{sunday.day}",
                    "label": f"D-{n}주 ({sunday.month}/{sunday.day} 주)",
                    "start": sunday.isoformat(),
                    "end": (sunday + dt.timedelta(days=6)).isoformat(),
                    "shift": False,
                }
            )
        for i, day in enumerate(self.days):
            cells.append(
                {
                    "kind": "day",
                    "top": WEEKDAYS[(day.weekday() + 1) % 7],
                    "bottom": f"{day.month}/{day.day}",
                    "label": f"{day.month}/{day.day}",
                    "start": day.isoformat(),
                    "end": day.isoformat(),
                    "shift": i == 0,
                }
            )
        cells.append(
            {
                "kind": "retreat",
                "top": "수련회",
                "bottom": f"{self.open_date.month}/{self.open_date.day}"
                f"–{self.close_date.month}/{self.close_date.day}",
                "label": "수련회 기간",
                "start": self.open_date.isoformat(),
                "end": self.close_date.isoformat(),
                "shift": False,
            }
        )
        return cells


def _first_week(open_date: dt.date, runs: list[TaskRun]) -> int:
    starts = [r.start_date for r in runs if r.start_date]
    if not starts:
        return dweek.FIRST_D_WEEK
    earliest = dweek.week_of(open_date, min(starts))
    return max(dweek.FIRST_D_WEEK, min(MAX_FIRST_WEEK, earliest))



def overdue_of(run: TaskRun, today: dt.date) -> bool:
    """기한이 지났는데 아직 끝나지 않았는가.

    저장된 status='지연' 을 보지 않는다. 그건 담당자가 손으로 눌러야만 붙는
    표시라, 놓친 사람이 직접 신고해야 시스템이 알아차리는 구조가 된다.
    """
    end = run.end_date or run.start_date
    return bool(end and end < today and run.status != "완료")


def paint_of(run: TaskRun, today: dt.date) -> dict:
    """한 업무가 **어떻게 보이는가**. 보드의 바와 달력의 점을 함께 만든다.

    둘은 규칙이 다르다 — 보드의 바는 저장된 상태 그대로 칠하고, 달력의 점은
    **기한이 지났으면 '지연' 으로 바꿔** 칠한다 (4-13). 그래서 한 값으로
    합칠 수 없다. 그렇다고 화면마다 따로 계산하게 두면 두 벌이 되고,
    **두 벌이 되면 반드시 어긋나며 어긋난 쪽을 아무도 눈치채지 못한다.**

    실제로 어긋나 있었다: 달력이 마감일을 옮길 때 기한 초과를 화면에서
    `iso < today` 로 다시 판단했는데, 색은 손대지 않아 **붉은 점을 미래로
    옮겨도 붉게 남았다.**

    그래서 규칙을 여기 한 곳에 두고, 날짜·상태를 바꾸는 API 가 이것을
    그대로 실어 보낸다. 화면은 받아서 칠하기만 한다.
    """
    # `color_tag` 가 아니라 `color` 를 쓴다 — 색을 안 정한 부서에서 `color_tag`
    # 는 None 이고, 그대로 내보내면 화면이 `border-color: None` 을 받는다.
    # `color` 는 그 자리에 기본색을 넣어 주는 속성이다.
    color = run.department.color if run.department else "#787774"
    overdue = overdue_of(run, today)
    kind = run.library.kind

    bar_bg, bar_border = bar_style(run.status, color, kind=kind, ghost=False)
    # 기한이 지났는데 미완료면 붉게. 저장된 '지연' 이 아니라 날짜에서 계산한다 —
    # 놓친 사람이 직접 눌러야 시스템이 알아차리는 구조를 만들지 않는다 (4-10)
    dot_bg, dot_border = bar_style(
        "지연" if overdue else run.status, color, kind=kind, ghost=False
    )
    return {
        "status": run.status,
        "color": color,
        "overdue": overdue,
        "overdue_days": overdue_days_of(run, today),
        # 보드의 바
        "background": bar_bg,
        "border": bar_border,
        # 달력의 점
        "dot_background": dot_bg,
        "dot_border": dot_border,
    }


def overdue_days_of(run: TaskRun, today: dt.date) -> int:
    end = run.end_date or run.start_date
    if not end or run.status == "완료" or end >= today:
        return 0
    return (today - end).days


def has_started(run: TaskRun) -> bool:
    """착수했는가. started_at 이 없던 시절의 기존 행만 상태로 보정한다.

    '지연' 은 착수 여부를 알려주지 않는다 — 그게 started_at 을 만든 이유다.
    `!= "대기"` 로 보면 기한을 넘겼고 선행도 안 끝났고 손도 안 댄 업무,
    즉 가장 위험한 조합이 '일부 진행 가능' 으로 읽힌다. 모르는 것은
    미착수 쪽에 둔다 — 문제를 감추는 방향이 아니라 드러내는 방향이 안전하다.
    """
    if run.started_at is not None:
        return True
    return run.status in ("진행중", "완료")



def lost_prerequisites(run: TaskRun, runs: list[TaskRun]) -> list[str]:
    """라이브러리에 적힌 선행 중 이번 회차에 대응하는 run 이 없는 것의 제목.

    관문을 "끊긴 run id 가 있는가" 로 두면 안 된다. 링크가 **애초에 만들어지지
    않은** 경우(회차를 연 뒤 추가한 업무 등)가 통과해 버려, 그 업무가 조용히
    '진행 가능' 이 된다 — 빠진 경우와 같은 실패인데 입구만 다르다.
    그래서 라이브러리 쪽을 기준으로 묻는다.

    board 와 diagnosis 가 이 하나를 같이 쓴다. 두 곳에 두면 어긋난다.
    """
    present = {r.library_id for r in runs}
    session = Session.object_session(run)
    out: list[str] = []
    for library_id in run.library.prerequisite_library_ids or []:
        if library_id in present:
            continue
        target = session.get(TaskLibrary, library_id) if session else None
        out.append(target.title if target else "(이름을 찾을 수 없는 선행 업무)")
    return out


def relink_prerequisites(db: Session, retreat: Retreat) -> list[dict]:
    """라이브러리의 선행 관계를 이번 회차의 run 링크로 다시 맞춘다.

    create_retreat 의 2패스와 같은 일을 회차를 연 뒤에도 한다. included 끼리만
    잇는다 — 보드는 included 인 run 만 실으므로 미포함 run 을 가리키면
    화면에서 끊긴 참조가 된다. 잇지 못한 건은 링크를 만들지 않고 돌려준다.
    """
    runs = list(
        db.scalars(
            select(TaskRun)
            .options(joinedload(TaskRun.library))
            .where(TaskRun.retreat_id == retreat.id, TaskRun.included)
        )
    )
    by_library = {r.library_id: r for r in runs}
    unmet: list[dict] = []
    for run in runs:
        links: list[int] = []
        for library_id in run.library.prerequisite_library_ids or []:
            target = by_library.get(library_id)
            if target is None:
                lib = db.get(TaskLibrary, library_id)
                unmet.append(
                    {
                        "library_id": run.library_id,
                        "title": run.library.title,
                        "prerequisite_id": library_id,
                        "prerequisite_title": lib.title if lib else "(라이브러리에 없음)",
                    }
                )
                continue
            links.append(target.id)
        if list(run.blocked_by_run_ids or []) != links:
            run.blocked_by_run_ids = links
    return unmet

def load_runs(db: Session, retreat: Retreat) -> list[TaskRun]:
    return list(
        db.scalars(
            select(TaskRun)
            .options(
                joinedload(TaskRun.library),
                joinedload(TaskRun.department),
                joinedload(TaskRun.assignee),
            )
            .where(TaskRun.retreat_id == retreat.id, TaskRun.included)
            .order_by(TaskRun.id)
        )
    )


def build(db: Session, retreat: Retreat, *, can_edit=None, today: dt.date | None = None) -> dict:
    """보드 한 장을 그리는 데 필요한 모든 것."""
    today = today or dt.date.today()
    open_date = retreat.start_date
    close_date = retreat.end_date or open_date
    runs = load_runs(db, retreat)
    axis = Axis(open_date, close_date, _first_week(open_date, runs))

    by_library = {run.library_id: run for run in runs}
    # 후속("나를 기다리는 업무")은 저장하지 않는다 — 선행의 역방향으로 계산한다
    run_ids = {run.id for run in runs}
    blocks: dict[int, list[int]] = {}
    for run in runs:
        for blocker_id in run.blocked_by_run_ids or []:
            if blocker_id in run_ids:
                blocks.setdefault(blocker_id, []).append(run.id)

    # 선행이 이번 회차에 없으면 조용히 삼키지 않는다 (lost_prerequisites 참고)
    lost = {run.id: names for run in runs if (names := lost_prerequisites(run, runs))}
    departments = sorted(retreat.departments, key=lambda d: d.sort_order)
    dept_by_key = {d.key: d for d in departments}

    # 업무 메타 (드로어와 연결 표시가 함께 쓴다)
    meta: dict[int, dict] = {}
    for run in runs:
        lib = run.library
        related_ids = [i for i in (lib.related_library_ids or []) if i in by_library]
        meta[run.id] = {
            "run_id": run.id,
            "library_id": lib.id,
            "title": lib.title,
            "kind": lib.kind,
            "kind_label": lib.kind_label,
            "status": run.status,
            "start": run.start_date.isoformat() if run.start_date else None,
            "end": (run.end_date or run.start_date).isoformat() if run.start_date else None,
            "department_key": run.department.key if run.department else None,
            "department_name": run.department.name if run.department else "담당 없음",
            "department_color": run.department.color if run.department else "#69726D",
            "parent_run_id": by_library[lib.parent_library_id].id
            if lib.parent_library_id in by_library
            else None,
            "parent_title": by_library[lib.parent_library_id].library.title
            if lib.parent_library_id in by_library
            else None,
            "related_run_ids": [by_library[i].id for i in related_ids],
            # 선후행은 관련(방향 없음)과 별개 키로 둔다 — 섞으면 판정이 흐려진다
            "blocked_by_run_ids": [i for i in (run.blocked_by_run_ids or []) if i in run_ids],
            "blocks_run_ids": blocks.get(run.id, []),
            # 이번 회차에서 빠져 링크가 끊긴 선행 — 막는 것으로 치지는 않지만
            # 근거에는 반드시 남긴다 (조용히 사라지면 안 된다)
            "lost_prerequisites": lost.get(run.id, []),
            # 기한 초과는 저장된 '지연' 이 아니라 날짜에서 계산한다.
            # 사람이 눌러야만 알아차리는 구조를 없애기 위해서다.
            "overdue": overdue_of(run, today),
            "overdue_days": overdue_days_of(run, today),
            # 사람이 손으로 남긴 '지연' 표시. 판정에는 넣지 않고 근거로만 쓴다.
            "marked_late": run.status == "지연",
            "started": has_started(run),
            "related_department_keys": [
                k for k in (lib.related_department_keys or []) if k in dept_by_key
            ],
            "d_week": run.d_week,
            "assignee": run.assignee.name if run.assignee else None,
            "origin": lib.origin,
            # 끌어서 날짜를 옮길 수 있는지 — 내 부서의 업무만
            "can_edit": True if can_edit is None else bool(can_edit(run)),
        }

    def make_row(run: TaskRun, *, depth: int, ghost: bool, owner_color: str) -> dict:
        lib = run.library
        start = run.start_date or open_date
        end = run.end_date or start
        background, border = bar_style(run.status, owner_color, kind=lib.kind, ghost=ghost)
        return {
            "run_id": run.id,
            "title": lib.title,
            "kind": lib.kind,
            "status": run.status,
            "depth": depth,
            "ghost": ghost,
            "col_start": axis.column_of(start),
            "col_end": axis.column_of(end) + 1,
            "background": background,
            "border": border,
            "owner_name": short_name(run.department.name) if run.department else "담당 없음",
            "assignee": run.assignee.name if run.assignee else None,
            "owner_color": owner_color,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

    dept_blocks = []
    for dept in departments:
        own = [r for r in runs if r.department_id == dept.id]
        mains = [r for r in own if r.library.parent_library_id is None]
        rows: list[dict] = []
        for main in mains:
            rows.append(make_row(main, depth=0, ghost=False, owner_color=dept.color))
            for sub in own:
                if sub.library.parent_library_id == main.library_id:
                    rows.append(make_row(sub, depth=1, ghost=False, owner_color=dept.color))

        # 관련팀으로 지정된 업무는 점선 고스트 바로 이 부서 행에도 나타난다
        ghosts = [
            r
            for r in runs
            if r.department_id != dept.id
            and dept.key in (r.library.related_department_keys or [])
        ]
        ghost_rows = [
            make_row(
                r,
                depth=1,
                ghost=True,
                owner_color=r.department.color if r.department else "#69726D",
            )
            for r in ghosts
        ]

        dept_blocks.append(
            {
                "key": dept.key,
                "name": dept.name,
                "color": dept.color,
                "team_tint": tint(dept.color, 0.20),
                "row_tint": tint(dept.color, 0.055),
                "label_tint": tint(dept.color, 0.03),
                "rows": rows,
                "ghost_rows": ghost_rows,
                "count": len(rows),
                "ghost_count": len(ghost_rows),
            }
        )

    unassigned = [r for r in runs if r.department_id is None]
    if unassigned:
        rows = [make_row(r, depth=0, ghost=False, owner_color="#69726D") for r in unassigned]
        dept_blocks.append(
            {
                "key": "__none__",
                "name": "담당 없음",
                "color": "#69726D",
                "team_tint": "#EDEEED",
                "row_tint": "#F7F8F7",
                "label_tint": "#FAFBFA",
                "rows": rows,
                "ghost_rows": [],
                "count": len(rows),
                "ghost_count": 0,
            }
        )

    # ── 모바일: 24칸 간트는 폰에서 쓸 수 없다. D-주차 → 부서 순 목록으로 바꾼다.
    #    "이번 주에 뭐가 있나"가 먼저 보여야 하므로 주차가 바깥 묶음이다.
    order = {d.id: d.sort_order for d in departments}
    mobile_groups = []
    for label, key, group in _by_week(runs, open_date, axis):
        group.sort(key=lambda r: (order.get(r.department_id, 99), r.library.title))
        mobile_groups.append(
            {
                "key": key,
                "label": label,
                "rows": [
                    {
                        "run_id": r.id,
                        "title": r.library.title,
                        "kind": r.library.kind,
                        "status": r.status,
                        "department_key": r.department.key if r.department else "__none__",
                        "department_name": short_name(r.department.name)
                        if r.department
                        else "담당 없음",
                        "department_color": r.department.color if r.department else "#69726D",
                        "assignee": r.assignee.name if r.assignee else None,
                        "start": (r.start_date or open_date).isoformat(),
                        "end": (r.end_date or r.start_date or open_date).isoformat(),
                        "border": bar_style(
                            r.status,
                            r.department.color if r.department else "#69726D",
                            kind=r.library.kind,
                            ghost=False,
                        )[1],
                    }
                    for r in group
                ],
            }
        )

    done = sum(1 for r in runs if r.status == "완료")
    grid = (
        "var(--label-w) "
        f"repeat({len(axis.week_sundays)},var(--wk)) "
        f"repeat({len(axis.days)},var(--day)) var(--retreat)"
    )
    return {
        "axis": axis,
        "grid": grid,
        "mobile_groups": mobile_groups,
        "headers": axis.headers(),
        "columns": axis.total,
        "shift_index": axis.shift_index,
        "departments": dept_blocks,
        "meta": meta,
        "total": len(runs),
        "done": done,
        "late": sum(1 for r in runs if r.status == "지연"),
        "open_date": open_date,
        "close_date": close_date,
    }


def _by_week(runs: list[TaskRun], open_date: dt.date, axis: Axis):
    """실행 업무를 D-주차로 묶는다. 개회일 이후 업무는 수련회 기간으로 모은다."""
    buckets: dict[int, list[TaskRun]] = {}
    for run in runs:
        start = run.start_date or open_date
        week = 0 if start >= open_date else max(1, dweek.week_of(open_date, start))
        buckets.setdefault(min(week, axis.first_week), []).append(run)

    out = []
    for week in sorted(buckets, key=lambda w: (w == 0, -w)):
        if week == 0:
            out.append(("수련회 기간", "retreat", buckets[week]))
            continue
        sunday = dweek.week_date(open_date, week)
        out.append((f"D-{week}주 · {sunday.month}/{sunday.day} 주", f"w{week}", buckets[week]))
    return out


def planning_slots(open_date: dt.date, close_date: dt.date | None = None) -> list[dict]:
    """업무를 놓을 수 있는 칸 목록 — 보드 축과 같은 눈금.

    보드는 업무가 있는 데까지만 그리지만, 고를 때는 그보다 앞도 열어 둔다.
    기획 단계 업무는 D-13주보다 훨씬 앞에 있기 때문이다.
    """
    axis = Axis(open_date, close_date or open_date, dweek.PLANNING_FIRST_WEEK)
    out = []
    for cell in axis.headers():
        if cell["kind"] == "week":
            label = f"{cell['top']}주 · {cell['bottom']} 주"
        elif cell["kind"] == "day":
            label = f"{cell['bottom']} ({cell['top']})"
        else:
            label = f"수련회 기간 · {cell['bottom']}"
        out.append(
            {"start": cell["start"], "end": cell["end"], "label": label, "kind": cell["kind"]}
        )
    return out


def carried_and_current(run: TaskRun) -> tuple[list, list]:
    """논의 내역을 (이번 회차, 지난 회차에서 따라온 것)으로 나눈다."""
    current = [e for e in run.discussions if e.carried_from_run_id is None]
    carried = [e for e in run.discussions if e.carried_from_run_id is not None]
    return current, carried


def superseded_ids(entries) -> set[int]:
    return {e.supersedes_entry_id for e in entries if e.supersedes_entry_id}


def library_titles(db: Session) -> dict[int, str]:
    return {row.id: row.title for row in db.scalars(select(TaskLibrary))}
