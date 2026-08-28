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

MAX_FIRST_WEEK = 30  # 이보다 이른 업무는 첫 칸에 몰아 넣는다


def tint(hex_color: str, ratio: float) -> str:
    """팀 색을 종이색 쪽으로 흐리게 섞는다. 글자가 검정이므로 연한 톤만 쓴다."""
    raw = hex_color.lstrip("#")
    r, g, b = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    mix = lambda v, paper: round(v * ratio + paper * (1 - ratio))  # noqa: E731
    return f"rgb({mix(r, 250)},{mix(g, 251)},{mix(b, 250)})"


def bar_style(status: str, color: str, *, kind: str, ghost: bool) -> tuple[str, str]:
    """(배경, 테두리색). 완료를 눈에 띄게 하지 않는 것이 핵심이다 —
    목적이 구멍 방지라면 시선은 미완료로 가야 한다."""
    if ghost:
        return "none", "#C7CEC9"
    if status == "완료":
        return "#DFE3E0", "#C4CBC6"
    if status == "지연":
        return "#FBE4DF", "#C8442E"
    if kind == "schedule" or status == "대기":
        return "#FAFBFA", color
    return tint(color, 0.20), color


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


def load_runs(db: Session, retreat: Retreat) -> list[TaskRun]:
    return list(
        db.scalars(
            select(TaskRun)
            .options(joinedload(TaskRun.library), joinedload(TaskRun.department))
            .where(TaskRun.retreat_id == retreat.id, TaskRun.included)
            .order_by(TaskRun.id)
        )
    )


def build(db: Session, retreat: Retreat) -> dict:
    """보드 한 장을 그리는 데 필요한 모든 것."""
    open_date = retreat.start_date
    close_date = retreat.end_date or open_date
    runs = load_runs(db, retreat)
    axis = Axis(open_date, close_date, _first_week(open_date, runs))

    by_library = {run.library_id: run for run in runs}
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
            "related_department_keys": [
                k for k in (lib.related_department_keys or []) if k in dept_by_key
            ],
            "d_week": run.d_week,
            "origin": lib.origin,
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

    done = sum(1 for r in runs if r.status == "완료")
    grid = (
        "var(--label-w) "
        f"repeat({len(axis.week_sundays)},var(--wk)) "
        f"repeat({len(axis.days)},var(--day)) var(--retreat)"
    )
    return {
        "axis": axis,
        "grid": grid,
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


def carried_and_current(run: TaskRun) -> tuple[list, list]:
    """논의 내역을 (이번 회차, 지난 회차에서 따라온 것)으로 나눈다."""
    current = [e for e in run.discussions if e.carried_from_run_id is None]
    carried = [e for e in run.discussions if e.carried_from_run_id is not None]
    return current, carried


def superseded_ids(entries) -> set[int]:
    return {e.supersedes_entry_id for e in entries if e.supersedes_entry_id}


def library_titles(db: Session) -> dict[int, str]:
    return {row.id: row.title for row in db.scalars(select(TaskLibrary))}
