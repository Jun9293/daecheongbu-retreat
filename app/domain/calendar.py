"""달력 보기 (CLAUDE.md 4-13).

준비 보드는 D-주차 타임라인이라 "전체가 어떻게 흘러가나" 를 봅니다.
이 화면은 담당자가 **"이번 주에 내가 뭘 해야 하나"** 를 보는 자리입니다.

**마감일에 점 하나만 찍습니다.** 기간 전체를 띠로 그리지 않습니다 —
15일짜리 업무를 띠로 그리면 한 주에 몇 개만 있어도 달력이 꽉 차고,
담당자에게 중요한 것은 **언제까지 끝내야 하는가**입니다.

**점의 생김새는 보드의 규칙을 그대로 씁니다**(`board.bar_style`·`board.overdue_of`).
두 벌이 되면 반드시 어긋나고, 어긋난 쪽을 아무도 눈치채지 못합니다.
"""

from __future__ import annotations

import calendar as _calendar
import datetime as dt

from sqlalchemy.orm import Session

from app.domain import board as board_domain
from app.models import Retreat, TaskRun, User

# 고를 수 있는 범위. **부서 키가 그대로 값이 된다** — 여기 셋만 특별하다.
#
# 전에는 `내 것 / 우리 부서 / 전체` 셋뿐이라 **어느 부서를 고를 수가 없었다.**
# 총무팀장이 스케치팀 것만 보려 해도 방법이 없었다. 보드는 이미 드롭다운으로
# 어느 부서든 골랐으므로 **그것을 그대로 쓴다** (`partials/deptpick.html`).
#
# `dept` 는 옛 값이다. 쿠키에 남아 있을 수 있어 **내 부서 키로 옮겨 준다** —
# 모르는 값이라고 `mine` 으로 떨어뜨리면, 어제까지 우리 부서를 보던 사람이
# 오늘 갑자기 자기 것만 보게 되고 왜인지 알 수 없다.
FIXED_SCOPES = ("mine", "all")
SCOPE_LABELS = {"mine": "내 것", "all": "전체"}
LEGACY_DEPT = "dept"

# 한 칸에 이만큼까지 펼쳐 두고 나머지는 접는다. 다 펼치면 칸이 세로로
# 길어져 주 높이가 들쭉날쭉해지고, 그러면 달력으로 읽히지 않는다.
PER_DAY = 3

WEEKDAYS = ("일", "월", "화", "수", "목", "금", "토")


def month_of(value: str | None, *, today: dt.date, retreat: Retreat) -> dt.date:
    """볼 달의 1일.

    **처음 열면 오늘이 든 달**입니다. 다만 회차 기간 밖이면 회차가 시작하는
    달로 갑니다 — 지난 회차를 열었는데 빈 달이 뜨면 "업무가 없나" 로 읽힙니다.
    """
    if value:
        # `2026-11` 도 `2026-11-01` 도 받는다 — 화면이 내보내는 것은 뒤엣것이라
        # 앞엣것만 받으면 이전/다음 달이 조용히 기본 달로 돌아온다
        try:
            parts = value.split("-")
            return dt.date(int(parts[0]), int(parts[1]), 1)
        except (ValueError, TypeError, IndexError):
            pass

    start, end = retreat.start_date, retreat.end_date or retreat.start_date
    if start and not (start <= today <= (end or start)):
        return start.replace(day=1)
    return today.replace(day=1)


def shift_month(first: dt.date, step: int) -> dt.date:
    """한 달 앞뒤로. **회차 기간을 벗어난 달로도 갑니다** — 막지 않습니다."""
    month = first.month + step
    year = first.year + (month - 1) // 12
    return dt.date(year, (month - 1) % 12 + 1, 1)


def _in_scope(run: TaskRun, *, scope: str, user: User | None) -> bool:
    """`mine` · `all` · **부서 키**.

    **부서는 키로 비교합니다** (2장). `Department` 행은 회차마다 새로
    만들어지므로 id 로 보면 새 회차가 열리는 순간 그 부서 업무가 통째로
    사라집니다 — 값 자체를 키로 두면 그 실수를 할 자리가 없어집니다.
    """
    if scope == "all":
        return True
    if scope == "mine":
        return user is not None and run.assignee_id == user.id
    return (run.department.key if run.department else None) == scope


def dot_of(run: TaskRun, *, today: dt.date) -> dict:
    """점 하나. **보드와 같은 규칙**으로 칠한다.

    색과 기한 초과는 `board.paint_of` 가 만든다 — 날짜를 옮겼을 때 화면에
    돌려주는 값과 **같은 곳에서 나와야** 처음 그린 점과 옮긴 점이 같아진다.
    """
    paint = board_domain.paint_of(run, today)
    return {
        "run_id": run.id,
        "title": run.library.title,
        "kind": run.library.kind,
        "status": paint["status"],
        "overdue": paint["overdue"],
        "overdue_days": paint["overdue_days"],
        "department_key": run.department.key if run.department else None,
        "color": paint["color"],
        "background": paint["dot_background"],
        "border": paint["dot_border"],
        # **마우스를 올렸을 때 뜨는 한 줄도 구조가 준다** — 부서·담당자를
        # 점에 실어 두고 화면이 다시 조립하던 것을 걷어냈다. 담당자를 바꾸면
        # 그 값을 아무도 갱신하지 않아 옛 사람이 남았다 (board.tooltip_of).
        "tooltip": paint["tooltip"],
        # **기간은 구조가 실어 보낸다** — 점에 마우스를 올렸을 때 화면이
        # 계산하거나 서버에 다시 묻지 않는다. 점이 자기 것을 들고 있다 (4-13).
        # 시작일이 없으면 마감일 하루짜리로 본다.
        "start": (run.start_date or run.end_date).isoformat()
        if (run.start_date or run.end_date) else None,
        "end": (run.end_date or run.start_date).isoformat()
        if (run.end_date or run.start_date) else None,
    }


def build(
    db: Session,
    retreat: Retreat,
    *,
    today: dt.date,
    user: User | None = None,
    my_dept_key: str | None = None,
    month: str | None = None,
    scope: str = "mine",
    only_open: bool = False,
) -> dict:
    """달력 한 장. **`today` 를 받습니다** — 실행 날짜에 따라 갈리면 안 됩니다."""
    depts = [{"key": d.key, "name": d.name}
             for d in sorted(retreat.departments, key=lambda d: (d.sort_order, d.id))
             if d.key]
    쓸수있는 = set(FIXED_SCOPES) | {d["key"] for d in depts}
    # 옛 값(`dept`)은 **내 부서 키로 옮긴다** — 쿠키에 남아 있을 수 있다
    if scope == LEGACY_DEPT:
        scope = my_dept_key or "mine"
    if scope not in 쓸수있는:
        scope = "mine"

    first = month_of(month, today=today, retreat=retreat)
    runs = [
        run for run in board_domain.load_runs(db, retreat)
        if run.included
        and _in_scope(run, scope=scope, user=user)
        and not (only_open and run.status == "완료")
    ]

    # ── 마감일에 점 하나 ──
    by_day: dict[str, list[dict]] = {}
    undated: list[dict] = []
    for run in sorted(runs, key=lambda r: (r.library.title or "")):
        end = run.end_date or run.start_date
        dot = dot_of(run, today=today)
        if end is None:
            # **놓을 자리가 없다고 조용히 빼지 않습니다.** 그게 정확히
            # 놓치는 지점입니다 — 달력 아래에 따로 모아 보여줍니다
            undated.append(dot)
        else:
            by_day.setdefault(end.isoformat(), []).append(dot)

    # ── 달 격자 (일요일 시작) ──
    weeks: list[list[dict]] = []
    last = _calendar.monthrange(first.year, first.month)[1]
    lead = (first.weekday() + 1) % 7          # 월=0 → 일=0 으로
    day = first - dt.timedelta(days=lead)
    while True:
        row = []
        for _ in range(7):
            iso = day.isoformat()
            dots = by_day.get(iso, [])
            row.append({
                "date": iso,
                "day": day.day,
                # **1일에는 달을 함께 적는다.** `1` 만 있으면 어느 달의 1일인지
                # 알기 어렵고, 앞뒤 달 칸이 섞여 있어 더 그렇다 — 오히려
                # 옆 달(`.out`) 쪽이 더 헷갈리므로 거기도 같게 적는다.
                "day_label": f"{day.month}/{day.day}" if day.day == 1 else str(day.day),
                "in_month": day.month == first.month,
                "is_today": day == today,
                "weekday": (day.weekday() + 1) % 7,
                "dots": dots[:PER_DAY],
                "more": dots[PER_DAY:],
            })
            day += dt.timedelta(days=1)
        weeks.append(row)
        if day > first.replace(day=last):
            break

    shown = sum(len(cell["dots"]) + len(cell["more"])
                for week in weeks for cell in week if cell["in_month"])
    return {
        "month": first.isoformat(),
        "label": f"{first.year}년 {first.month}월",
        "prev": shift_month(first, -1).isoformat(),
        "next": shift_month(first, 1).isoformat(),
        "today": today.isoformat(),
        "today_month": today.replace(day=1).isoformat(),
        "weekdays": list(WEEKDAYS),
        "weeks": weeks,
        "undated": undated,
        "scope": scope,
        # 고르는 자리는 보드와 같은 것을 쓴다 (`partials/deptpick.html`)
        "departments": depts,
        "only_open": only_open,
        "count": shown,
        "total": len(runs),
        "per_day": PER_DAY,
    }
