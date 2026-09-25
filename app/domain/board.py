"""수련회 준비 — 보드의 뷰 모델 (CLAUDE.md 4장, 시각 스펙 retreat-board-v4.html).

가로축은 D-13주~D-3주까지 주 단위, D-2주부터 개회일까지 하루 단위,
마지막에 수련회 기간 한 칸. 주 단위를 쓰는 이유는 봉사자들이 주말에만
모이기 때문이다 — 편의가 아니라 실제 리듬이다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain import dweek, period
from app.domain.departments import short_name
from app.models import Retreat, TaskLibrary, TaskRun

WEEKDAYS = ("일", "월", "화", "수", "목", "금", "토")

# (옛 STATUS_COLORS 표는 지웠다 — 아무도 안 읽는 채로 옛 팔레트의 붉은 값을
#  들고 있었다. 상태의 생김새는 bar_style·배지 토큰이 쥔다. 4-0 · 4-3)

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
        return "rgb(250,250,252)"            # 못 읽으면 종이색
    try:
        r, g, b = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "rgb(250,250,252)"
    mix = lambda v, paper: round(v * ratio + paper * (1 - ratio))  # noqa: E731
    return f"rgb({mix(r, 250)},{mix(g, 250)},{mix(b, 252)})"


# 차가운 무채색 기조 (CLAUDE.md 4장 UI 방향).
# **부서 색이 면에도 온다 — 다만 아주 옅게** (2026-09-21 에 사람이 정함).
# 전에는 「면을 안 채운다」 였고 팀색이 7~8px 점과 3px 마개에만 갇혀 있어서,
# 색이 아홉 가지나 있는데 화면이 통째로 회색으로 읽혔다. 채우되 **선택
# 테두리와 지연 배지를 묻지 않을 만큼만** 넣는다 — 그래서 알파를 여기 한 곳에
# 두고 값도 8%·14% 로 낮게 잡는다. 왼쪽 3px 마개는 그대로 남는다.
BAR_DONE = ("#F0F1F4", "#E3E4E9")        # 회색 채움 — 눈에 띄지 않게
# 부서가 없는 업무의 색. 여기저기 흩어져 있던 것을 한 곳으로 모은다.
# (`Department.color` 도 색을 안 정한 부서에 같은 값을 넣어 준다)
NO_DEPARTMENT_COLOR = "#71727D"

BAR_LATE = ("#FBF1F0", "#C4554D")        # 옅은 붉은색 + 빨간 테두리
BAR_GHOST_BORDER = "#C7C8CE"
# `bar_style` 은 이제 이 값을 안 돌려준다 — 못 읽는 색은 `tint` 가 종이색으로
# 물러선다. 남긴 것은 **「팀색이 안 온 바탕」 이 무엇인지** 를 시험이 가리킬
# 이름이 필요해서다(`test_calendar` 가 「이 값이 아니다」 를 잰다)
BAR_TODO_BG = "#FFFFFF"

# 면을 채우는 비율. **여기 한 곳에 둔다** — 여러 자리에 흩어 두면 한쪽만
# 진해진다. 값이 낮은 것은 선택 테두리와 지연 배지를 묻지 않기 위해서다.
TINT_TODO = 0.08                         # 대기
TINT_WIP = 0.14                           # 진행중


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
        return tint(color, TINT_TODO), color
    return tint(color, TINT_WIP), color



class Axis:
    """보드 가로축 — **구간이 다섯이다** (목업 D · 2026-09-23 사람이 정함).

        기획(주) · 준비(주) · D-2주(하루) · 수련회 · 후속(주)

    앞의 둘은 `dweek.PLANNING_UNTIL_D_WEEK` 하나로 갈린다 — 같은 주 단위
    칸이고 **머리의 구간 줄만** 다르다. 뒤의 「후속」 은 2026-09-23 에
    새로 붙었다: 결산·환급·정리는 폐회 뒤에 하는 일인데(4-15 의 결산 홈이
    그것을 세고 있다) **축 밖이라 보드에 설 자리가 없었다.**
    """

    def __init__(self, open_date: dt.date, close_date: dt.date, first_week: int,
                 *, after_weeks: int = dweek.MIN_AFTER_WEEKS) -> None:
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
        # **후속은 폐회 다음 날이 든 주부터** 주 단위로 간다. 첫 칸의 일요일은
        # 그 날이 든 주의 일요일이다 — 앞쪽 칸들이 전부 일요일 눈금이라
        # 여기만 폐회 다음 날로 시작하면 한 주가 어긋난 채 이어진다.
        self.after_weeks = max(0, min(after_weeks, dweek.LAST_AFTER_WEEK))
        first_after = close_date + dt.timedelta(days=1)
        first_after -= dt.timedelta(days=(first_after.weekday() + 1) % 7)
        self.after_sundays = [
            first_after + dt.timedelta(days=7 * i) for i in range(self.after_weeks)
        ]
        self.total = (len(self.week_sundays) + len(self.days) + 1
                      + len(self.after_sundays))

    @property
    def shift_index(self) -> int:
        """주 단위 → 일 단위로 바뀌는 열 번호 (여기에 굵은 세로선)."""
        return len(self.week_sundays) + 1

    @property
    def retreat_column(self) -> int:
        return len(self.week_sundays) + len(self.days) + 1

    def section_of_week(self, n: int) -> str:
        """D-n주가 「기획」 인가 「준비」 인가 — 가르는 자리는 여기 하나다."""
        return "plan" if n > dweek.PLANNING_UNTIL_D_WEEK else "prep"

    def column_of(self, day: dt.date) -> int:
        """그 날이 앉는 열. **범위 밖은 가까운 쪽 끝에 붙인다** (9장).

        뒤로 나간 것은 `beyond_of` 가 따로 말한다 — 마지막 칸에 붙이기만 하면
        「마지막 주가 마감인 업무」 와 「반년 뒤가 마감인 업무」 가 같은 모양이다.
        """
        if day > self.close_date and self.after_sundays:
            index = (day - self.after_sundays[0]).days // 7
            if index < 0:
                return self.retreat_column
            return self.retreat_column + 1 + min(index, len(self.after_sundays) - 1)
        if day >= self.open_date:
            return self.retreat_column
        if self.days and day >= self.days[0]:
            return len(self.week_sundays) + 1 + (day - self.days[0]).days
        sunday = day - dt.timedelta(days=(day.weekday() + 1) % 7)
        index = (sunday - self.week_sundays[0]).days // 7
        return max(1, min(len(self.week_sundays), index + 1))

    def beyond_of(self, end: dt.date) -> bool:
        """그 마감이 **축 뒤쪽 상한 밖**인가 (바 끝에 `→` 를 단다 · 4-1)."""
        if not self.after_sundays:
            return end > self.close_date
        return end > self.after_sundays[-1] + dt.timedelta(days=6)

    def sections(self) -> list[dict]:
        """머리 첫 줄 — 구간마다 (이름, 칸 수). **칸에서 세어 만든다** —
        따로 적으면 칸을 하나 늘렸을 때 한쪽만 고쳐진다."""
        out: list[dict] = []
        for cell in self.headers():
            if out and out[-1]["key"] == cell["section"]:
                out[-1]["span"] += 1
            else:
                out.append({"key": cell["section"], "label": SECTION_LABELS[cell["section"]],
                            "span": 1})
        return out

    def headers(self) -> list[dict]:
        cells = []
        for i, sunday in enumerate(self.week_sundays):
            n = self.first_week - i
            cells.append(
                {
                    "kind": "week",
                    "section": self.section_of_week(n),
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
                    "section": "d2",
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
                "section": "retreat",
                "top": "수련회",
                "bottom": f"{self.open_date.month}/{self.open_date.day}"
                f"–{self.close_date.month}/{self.close_date.day}",
                "label": "수련회 기간",
                "start": self.open_date.isoformat(),
                "end": self.close_date.isoformat(),
                "shift": False,
            }
        )
        for i, sunday in enumerate(self.after_sundays):
            cells.append(
                {
                    "kind": "after",
                    "section": "after",
                    "top": f"D+{i + 1}",
                    "bottom": f"{sunday.month}/{sunday.day}",
                    "label": f"D+{i + 1}주 ({sunday.month}/{sunday.day} 주)",
                    "start": sunday.isoformat(),
                    "end": (sunday + dt.timedelta(days=6)).isoformat(),
                    "shift": i == 0,
                }
            )
        return cells


SECTION_LABELS = {
    "plan": "기획 · 주 단위 (D-주)",
    "prep": "준비 · 주 단위 (D-주)",
    "d2": "D-2주 · 하루 단위",
    "retreat": "수련회",
    "after": "후속 · 주 단위",
}


def collapsed_lanes(subs: list[dict]) -> list[list[dict]]:
    """접힌 Main 아래 한 줄에 눕힐 하위 바들 (목업 D · 4-1).

    둘을 한다.

    **합친다** — 시작 칸과 끝 칸이 **둘 다** 같은 하위끼리는 바 하나로 묶고
    이름을 「, 」 로 잇는다. 합친 바는 끌 수 없다(run 이 여럿이라 끌면 어느
    것이 움직이는지 화면이 말해 주지 못한다 · 2026-09-23 사람이 정함).

    **눕힌다** — 일부만 겹치면 앞에서부터 빈 줄에 넣고, 없으면 줄을 하나 더
    둔다. **겹친 채로 그리면 뒤엣것이 앞엣것을 덮어 있는 업무가 화면에서
    사라진다.**

    날짜 없는 하위는 여기 안 눕힌다 — 놓을 칸이 없다(점선 표시가 대신한다).
    """
    묶음: dict[tuple[int, int], list[dict]] = {}
    차례: list[tuple[int, int]] = []
    for sub in subs:
        if sub.get("undated"):
            # **여기서 빼는 것은 「바를 안 놓는다」 뿐이다** — 몇 건인지는
            # `undated_subs` 가 세어 왼쪽 칸이 말한다. 조용히 빼면 접힌
            # 동안 그 업무가 화면 어디에도 없다(4-1 · 커밋 전 검토)
            continue
        키 = (sub["col_start"], sub["col_end"])
        if 키 not in 묶음:
            묶음[키] = []
            차례.append(키)
        묶음[키].append(sub)

    바들 = []
    for 키 in sorted(차례):
        무리 = 묶음[키]
        첫 = 무리[0]
        바들.append({
            "col_start": 키[0],
            "col_end": 키[1],
            "title": ", ".join(x["title"] for x in 무리),
            "run_id": 첫["run_id"] if len(무리) == 1 else None,
            "run_ids": " ".join(str(x["run_id"]) for x in 무리),
            "merged": len(무리) > 1,
            # 합친 바의 생김새는 **첫째 것**을 따른다 — 여럿의 상태를 섞을
            # 규칙이 없고, 섞으면 같은 칸이 상태에 따라 색이 오락가락한다
            "status": 첫["status"],
            "kind": 첫["kind"],
            "background": 첫["background"],
            "border": 첫["border"],
            "owner_color": 첫["owner_color"],
            "beyond": any(x.get("beyond") for x in 무리),
            # **`items` 라고 부르지 않는다** — dict 의 메서드 이름이라 Jinja 가
            # 키가 아니라 그 메서드를 준다(화면이 한 번 터졌다)
            "pop_items": [{"title": x["title"], "run_id": x["run_id"],
                           "meta_line": x["meta_line"]} for x in 무리],
        })

    lanes: list[list[dict]] = []
    for 바 in 바들:
        for lane in lanes:
            if all(바["col_start"] >= 놓인["col_end"] or 바["col_end"] <= 놓인["col_start"]
                   for 놓인 in lane):
                lane.append(바)
                break
        else:
            lanes.append([바])
    return lanes


def _축안에(axis: "Axis", day: dt.date) -> bool:
    """그 날이 축이 실제로 덮는 기간 안인가.

    `column_of` 는 **범위 밖도 가까운 쪽 끝에 붙이므로**(9장) 그것만으로는
    「오늘이 축에 있다」 를 알 수 없다 — 그대로 그리면 회차가 한참 지난 뒤에도
    오늘 선이 마지막 칸에 붙어 **거짓말을 한다.**
    """
    처음 = axis.week_sundays[0] if axis.week_sundays else axis.open_date
    끝 = (axis.after_sundays[-1] + dt.timedelta(days=6)) if axis.after_sundays else axis.close_date
    return 처음 <= day <= 끝


def _after_weeks(close_date: dt.date, runs: list[TaskRun], today: dt.date) -> int:
    """후속 칸을 몇 개 그릴까 — **오늘이 든 주와 가장 늦은 마감 중 늦은 쪽**까지.

    (2026-09-23 사람이 정함). 마감으로만 정하면 폐회가 한참 지난 회차에서
    축이 세 칸에 멈추는데, 그러면 「오늘」 단추가 **옮길 오늘 선이 축에 없다.**
    """
    ends = [due_of(r) for r in runs]
    늦은 = max([d for d in ends if d] + [today], default=today)
    if 늦은 <= close_date:
        return dweek.MIN_AFTER_WEEKS
    first = close_date + dt.timedelta(days=1)
    first -= dt.timedelta(days=(first.weekday() + 1) % 7)
    필요 = (늦은 - first).days // 7 + 1
    return max(dweek.MIN_AFTER_WEEKS, min(dweek.LAST_AFTER_WEEK, 필요))


def _first_week(open_date: dt.date, runs: list[TaskRun]) -> int:
    starts = [r.start_date for r in runs if r.start_date]
    if not starts:
        return dweek.FIRST_D_WEEK
    earliest = dweek.week_of(open_date, min(starts))
    return max(dweek.FIRST_D_WEEK, min(MAX_FIRST_WEEK, earliest))



def due_of(run: TaskRun) -> dt.date | None:
    """이 업무의 마감 — 마감이 비면 시작일을 하루짜리 마감으로 본다.

    기한을 재는 곳(overdue_of · suggestions.late_in_base)이 같은 정의를 쓴다.
    각자 `end or start` 를 다시 적으면 한쪽만 고쳐진다.
    """
    return run.end_date or run.start_date


def overdue_by_date(run: TaskRun, today: dt.date) -> bool:
    """날짜 계산만 — 기한이 지났는데 아직 끝나지 않았는가.

    화면은 이것을 직접 쓰지 않고 `overdue_of` 를 쓴다. 따로 있는 이유는
    **과거의 어느 시점**을 재는 자리(suggestions.late_in_base 가 폐회일
    시점을 잰다) 때문이다 — 그쪽에 `overdue_of` 를 주면 기준 회차가
    보관(is_archived)된 순간 무조건 False 가 되어, 지연 계열 제안이
    조용히 죽는다. 보관은 드롭다운에서 치우는 표시지 그때 지연이
    없었다는 뜻이 아니다.
    """
    end = due_of(run)
    return bool(end and end < today and run.status != "완료")


def overdue_of(run: TaskRun, today: dt.date) -> bool:
    """기한이 지났는데 아직 끝나지 않았는가 — '지연' 은 이 계산 하나에서 나온다.

    저장값이 아니다 (4-3). 저장해 두면 담당자가 손으로 눌러야만 붙어서,
    놓친 사람이 직접 신고해야 시스템이 알아차리는 구조가 된다.

    **끝난 회차에서는 지연이 없다** (4-10 의 '종료된 회차'와 같은 결) —
    지난 회차를 열면 모든 미완료가 기한 초과라, 바·점·배지·홈 지표·목록
    칩이 온통 붉게 소리를 지른다. 끝난 회차의 「지연 N건」 은 재촉이 아니라
    소음이다. 폐회일 당일까지는 그대로 잰다 (period.is_over 와 같은 경계).
    """
    if period.is_over(run.retreat, today):
        return False
    return overdue_by_date(run, today)


# 배지의 CSS 클래스 — 이름은 4-0 의 상태 배지 토큰(--st-*)과 짝이다
BADGE_CLASSES = {"대기": "wait", "진행중": "prog", "완료": "done", "지연": "late"}


def paint_of(run: TaskRun, today: dt.date, *, ghost: bool = False) -> dict:
    """한 업무가 **어떻게 보이는가**. 보드의 바 · 달력의 점 · 배지를 함께 만든다.

    화면마다 따로 계산하게 두면 두 벌이 되고, **두 벌이 되면 반드시 어긋나며
    어긋난 쪽을 아무도 눈치채지 못한다.** 실제로 어긋나 있었다: 달력이
    마감일을 옮길 때 기한 초과를 화면에서 `iso < today` 로 다시 판단했는데,
    색은 손대지 않아 **붉은 점을 미래로 옮겨도 붉게 남았다.**

    그래서 규칙을 여기 한 곳에 두고, 날짜·상태를 바꾸는 API 가 이것을
    그대로 실어 보낸다. 화면은 받아서 칠하기만 한다.

    '지연' 은 저장값이 아니라 계산값이다 (4-3) — 기한이 지났으면 바도 점도
    배지도 '지연' 으로 칠한다. 전에는 바만 저장된 상태 그대로였는데, 저장
    '지연' 이 없어지면서 바의 지연 표현도 이 계산에서 나온다. `bar_*` 와
    `dot_*` 를 둘 다 남긴 것은 화면(JS)이 그 이름으로 받기 때문이다.
    """
    # `color_tag` 가 아니라 `color` 를 쓴다 — 색을 안 정한 부서에서 `color_tag`
    # 는 None 이고, 그대로 내보내면 화면이 `border-color: None` 을 받는다.
    # `color` 는 그 자리에 기본색을 넣어 주는 속성이다.
    color = run.department.color if run.department else NO_DEPARTMENT_COLOR
    overdue = overdue_of(run, today)
    kind = run.library.kind

    # 보이는 상태 — 기한이 지났는데 미완료면 '지연'. 날짜에서 계산한다 (4-10).
    shown = "지연" if overdue else run.status
    bar_bg, bar_border = bar_style(shown, color, kind=kind, ghost=ghost)
    dot_bg, dot_border = bar_bg, bar_border
    # **접두사 없는 쌍을 두지 않는다.** `background`/`border` 로 두면 그쪽이
    # 기본값처럼 보여서, 세 번째 화면이 생겼을 때 사람이 따져 보지 않고 집는다 —
    # 이번에 고친 버그가 정확히 그 모양이었다.
    days = overdue_days_of(run, today)
    return {
        "status": run.status,
        "color": color,
        "overdue": overdue,
        "overdue_days": days,
        # 상태 배지 — **홈·목록·보드가 전부 이것을 쓴다** (4-3). 화면이 상태를
        # 다시 분기하면 두 벌이 된다.
        # **배지에 칸을 늘리지 않는다.** 며칠 늦었는지는 바로 위 `overdue_days`
        # 이고, 그것을 배지 안에도 넣으면 같은 값이 두 자리에 있게 된다 —
        # 배지를 통째로 견주는 시험이 곧바로 빨개졌다(2026-09-23 · 검토가 잡음)
        "badge": {"label": shown, "cls": BADGE_CLASSES[shown]},
        "bar_background": bar_bg,
        "bar_border": bar_border,
        "dot_background": dot_bg,
        "dot_border": dot_border,
        # **문장도 여기서 만든다.** 색과 같은 이유다 — 조립하는 곳이 둘이면
        # 반드시 어긋나고 어긋난 쪽을 아무도 눈치채지 못한다. 실제로 이
        # 구조로 세 번 당했다(색·기간·툴팁). `title` 이라 부르지 않는 것은
        # 달력의 점에서 그 이름이 **업무 이름**을 뜻하기 때문이다.
        "tooltip": tooltip_of(run, status=run.status, overdue=overdue,
                              overdue_days=days),
    }


def popup_meta(run: TaskRun, today: dt.date) -> str:
    """업무 팝업(F)의 둘째 줄 — **「기간 · 상태 · 담당팀」** 한 줄.

    **만드는 곳은 여기 하나다** — 보드와 달력이 같은 부품을 쓰므로(4-1 · 4-13)
    화면마다 조립하면 두 벌이 되고 갈린 쪽을 아무도 눈치채지 못한다.
    `tooltip_of` 와 다른 함수인 것은 **담는 것이 다르기 때문**이다: 툴팁은
    부서를 앞에 놓고 상위·담당자까지 싣고, 팝업은 목업 F 가 정한 셋만 싣는다.

    **축 밖으로 나간 업무가 실제 날짜를 말하는 자리가 여기다**(4-1) — 바는
    마지막 칸에 붙고 `→` 만 달리므로, 이 줄이 없으면 그 날짜가 화면 어디에도
    없다.
    """
    start = run.start_date or run.end_date
    end = run.end_date or run.start_date
    조각 = []
    if start:
        조각.append(start.isoformat() if start == end
                   else f"{start.isoformat()} – {end.isoformat()}")
    else:
        조각.append("날짜 없음")
    늦음 = overdue_days_of(run, today)
    조각.append(f"지연 {늦음}일" if 늦음 else paint_of(run, today)["badge"]["label"])
    조각.append(run.department.name if run.department else "담당 없음")
    return " · ".join(조각)


def tooltip_of(run: TaskRun, *, status: str, overdue: bool,
               overdue_days: int) -> str:
    """점에 마우스를 올렸을 때 뜨는 한 줄.

    **부서 · 상태 · 담당자 · 기간 · 기한 경과** 순이고 없는 것은 빠진다.
    담당자와 부서를 점에 `data-*` 로 실어 두고 화면이 다시 조립하던 것을
    걷어냈다 — 담당자를 바꾸면 아무도 그 값을 갱신하지 않아서 **옛 사람이
    툴팁에 계속 남았다.**

    기간은 `dot_of` 와 같은 규칙이다 — 한쪽이 비면 있는 쪽을 하루짜리로 본다.
    """
    start = run.start_date or run.end_date
    end = run.end_date or run.start_date
    조각 = [run.department.name if run.department else "담당 없음", status]
    # 상위가 있으면 한 줄 (봐둘것 BF-a) — 달력 점에서도 무엇의 하위인지 보인다
    if run.library.parent_library_id and run.library.parent is not None:
        조각.append(f"상위: {run.library.parent.title}")
    if run.assignee:
        조각.append(run.assignee.name)
    if start:
        조각.append(f"기간 {start.isoformat()} → {end.isoformat()}")
    if overdue and overdue_days:
        조각.append(f"마감에서 {overdue_days}일 경과")
    return " · ".join(x for x in 조각 if x)


def is_child(run: TaskRun, depth: int = 0) -> bool:
    """하위 모양으로 그리는가 (봐둘것 BF-a · 사람이 정함 2026-09-17).

    트리 아래 줄 · 분류가 하위인 줄 · **상위가 있는 줄**이다. 부서가 다른 하위는 자기 부서의
    머리 줄에 서는데, 굵은 Main 모양이면 최상위 업무로 읽힌다. 분류만 보면 노션 속성이 빈
    채 앱에 main 으로 들어간 하위가 굵게 남으므로 상위가 있는지도 본다. 보드 넓은 화면과
    좁은 폭 행이 이 하나를 받아 쓴다.
    """
    return bool(depth) or run.library.kind == "sub" or run.library.parent_library_id is not None


def parent_of(run: TaskRun, by_library: dict[int, TaskRun]) -> dict | None:
    """상위 표시 한 벌 (2장 상위-하위 · 봐둘것 BF-a) — **보드 · 목록 · 드로어가 같이 쓴다.**

    `by_library` 는 이번 회차의 산 run 을 라이브러리 id 로 찾는 표다. 상위의 run 이
    이번 회차에 없으면 `run_id` 가 비고(열 수 없음) 제목만 보인다. 부서는 **run 의**
    부서로 견준다 — 화면이 그리는 부서 블록이 run 의 것이다. 상위 run 에 부서가 없으면
    `no_dept` 가 서고 화면은 「담당 없음」 을 쓴다. **상위 run 이 없으면 부서 꼬리를 안
    단다** — 그 회차의 부서를 모르는데 「담당 없음」 이라고 하면 사실이 아니다(커밋 전 검토).
    그때 「다른가」 는 라이브러리의 부서 키로 견준다.
    """
    lib = run.library
    if lib.parent_library_id is None:
        return None
    prun = by_library.get(lib.parent_library_id)
    plib = prun.library if prun else lib.parent
    pdept = prun.department if prun else None
    mine = run.department.key if run.department else None
    if prun:
        pkey = pdept.key if pdept else None
    else:
        pkey = (plib.default_department_key or None) if plib else None
    return {
        "run_id": prun.id if prun else None,
        "title": plib.title if plib else "(라이브러리에 없음)",
        "dept_name": short_name(pdept.name) if pdept else None,
        "dept_color": pdept.color if pdept else None,
        "no_dept": prun is not None and pdept is None,
        "other_dept": pkey != mine,
    }


def overdue_days_of(run: TaskRun, today: dt.date) -> int:
    # overdue_of 와 같은 경계 — 끝난 회차에서는 경과일도 세지 않는다
    if not overdue_of(run, today):
        return 0
    return (today - due_of(run)).days


def has_started(run: TaskRun) -> bool:
    """착수했는가. started_at 이 없던 시절의 기존 행만 상태로 보정한다.

    인정하는 값은 '진행중'·'완료' 뿐이다. 모르는 것은 미착수 쪽에 둔다 —
    문제를 감추는 방향이 아니라 드러내는 방향이 안전하다.
    (저장 '지연' 이 있던 시절에는 그것을 미착수로 두는 판단이 여기 있었다.
    지금은 저장값 자체가 없어 그 갈림이 사라졌다 — 4-3.)
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
    axis = Axis(open_date, close_date, _first_week(open_date, runs),
                after_weeks=_after_weeks(close_date, runs, today))

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
            "department_color": run.department.color if run.department else NO_DEPARTMENT_COLOR,
            "parent_run_id": by_library[lib.parent_library_id].id
            if lib.parent_library_id in by_library
            else None,
            "parent_title": by_library[lib.parent_library_id].library.title
            if lib.parent_library_id in by_library
            else None,
            "parent": parent_of(run, by_library),
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

    def make_row(run: TaskRun, *, depth: int, ghost: bool, owner_color: str,
                 head_parent: bool = False) -> dict:
        lib = run.library
        # **날짜가 없는 것과 개회일에 있는 것은 다르다** (4-1 · 봐둘것 BJ-d).
        # 전에는 둘 다 개회일 자리에 보통 바로 서서, 수련회 칸에 잡힌 진짜
        # 업무와 구별이 안 됐다. 이제 바를 안 그리고 점선 표시를 둔다.
        undated = run.start_date is None and run.end_date is None
        start = run.start_date or run.end_date or open_date
        end = run.end_date or start
        # **첫 렌더도 paint_of 를 지난다.** 여기서 bar_style 을 직접 부르면
        # 처음 그린 바와 API 로 다시 칠한 바가 서로 다른 길에서 나온다 —
        # 그게 달력에서 어긋났던 그 구조다 (4-13).
        paint = paint_of(run, today, ghost=ghost)
        background, border = paint["bar_background"], paint["bar_border"]
        return {
            "run_id": run.id,
            # 회차 안에서 고정되는 번호 (4-14) — 회의에서 번호로 부른다
            "no": run.run_no,
            "title": lib.title,
            "kind": lib.kind,
            # 보이는 상태 — 기한이 지났으면 '지연'. 저장값이 아니라 paint_of 의
            # 계산값이다 (4-3). 화면의 지연 배지가 이 값에서 나온다.
            "status": paint["badge"]["label"],
            "depth": depth,
            "ghost": ghost,
            # 하위 모양(얇은 바 · 한 급 아래 줄)으로 그리는가 — is_child 하나가 정한다
            "child": is_child(run, depth),
            "col_start": axis.column_of(start),
            "col_end": axis.column_of(end) + 1,
            # 축 뒤쪽 상한 밖 — 바 끝에 `→` 를 달고 **제목이 안 끊겨도** 팝업을
            # 연다(4-1). 그러지 않으면 실제 날짜를 말할 자리가 어디에도 없다
            "beyond": axis.beyond_of(end) and not undated,
            "undated": undated,
            # 팝업(F)이 쓰는 한 줄 — 만드는 곳을 화면에 두면 보드와 달력이 갈린다
            "meta_line": popup_meta(run, today),
            "background": background,
            "border": border,
            "owner_name": short_name(run.department.name) if run.department else "담당 없음",
            "assignee": run.assignee.name if run.assignee else None,
            "owner_color": owner_color,
            "start": start.isoformat(),
            "end": end.isoformat(),
            # 머리 줄로 선 하위만 상위를 붙인다 — 트리 아래 줄은 들여쓰기가 이미 말한다
            "parent": parent_of(run, by_library) if head_parent and not ghost else None,
        }

    dept_blocks = []
    for dept in departments:
        own = [r for r in runs if r.department_id == dept.id]
        # **머리 줄 = 상위가 없거나, 상위가 이 부서 블록에 없는 줄** (봐둘것 BF-a).
        # 「상위가 없는 줄」 만 머리로 두면 상위가 다른 부서(또는 이번 회차에 없음)인
        # 하위가 어느 블록에도 안 서서 보드에서 사라진다. 그 줄은 자기 부서의 머리로
        # 그리고 상위를 옆에 붙인다 — 부서를 옮기지 않는다(사람이 정함 · 2026-09-17)
        own_libs = {r.library_id for r in own}
        mains = [r for r in own if r.library.parent_library_id not in own_libs]
        rows: list[dict] = []
        for main in mains:
            head = make_row(main, depth=0, ghost=False, owner_color=dept.color,
                            head_parent=True)
            subs = [make_row(sub, depth=1, ghost=False, owner_color=dept.color)
                    for sub in own
                    if sub.library.parent_library_id == main.library_id]
            # **하위가 있는 Main 은 기본 접힘이다** (4-1 · 목업 D). 접힌 줄에
            # 눕힐 바를 서버가 미리 만들어 둔다 — 화면에는 접힌 것과 펼친 것이
            # 둘 다 그려지고 **보이는 쪽만** 자리를 차지한다(`offsetParent`).
            # 그래야 펼침을 켜고 끌 때 서버를 다시 부르지 않는다.
            head["lanes"] = collapsed_lanes(subs)
            head["sub_count"] = len(subs)
            # 접힌 동안 바를 못 놓는 하위 — 놓을 칸이 없다. 왼쪽 칸이 그 수를
            # 말한다(안 말하면 접힌 채로는 있는 줄도 모른다)
            head["undated_subs"] = sum(1 for x in subs if x.get("undated"))
            # 행 높이 48 + (줄 수 − 1) × 18 (목업 D)
            head["row_height"] = 48 + max(0, len(head["lanes"]) - 1) * 18
            rows.append(head)
            rows.extend(subs)

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
                owner_color=r.department.color if r.department else NO_DEPARTMENT_COLOR,
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
                "count": len(own),
                # 부서 줄은 「완료 n/n건」 과 지연만 적는다 (4-1 · 목업 D).
                # **고스트는 안 센다** — 남의 부서 업무다
                "done": sum(1 for r in own if r.status == "완료"),
                "late": sum(1 for r in own if overdue_of(r, today)),
                "ghost_count": len(ghost_rows),
            }
        )

    unassigned = [r for r in runs if r.department_id is None]
    if unassigned:
        rows = [make_row(r, depth=0, ghost=False, owner_color=NO_DEPARTMENT_COLOR, head_parent=True)
                for r in unassigned]
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
                "count": len(unassigned),
                "done": sum(1 for r in unassigned if r.status == "완료"),
                "late": sum(1 for r in unassigned if overdue_of(r, today)),
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
                        "department_color": r.department.color if r.department else NO_DEPARTMENT_COLOR,
                        "assignee": r.assignee.name if r.assignee else None,
                        # **없으면 없다고 낸다** — 개회일로 채우면 화면이
                        # 「8/21」 이라고 적어 없던 날짜를 얻는다 (4-1)
                        "start": (r.start_date or r.end_date).isoformat()
                        if (r.start_date or r.end_date) else None,
                        "end": (r.end_date or r.start_date).isoformat()
                        if (r.start_date or r.end_date) else None,
                        "border": paint_of(r, today)["bar_border"],
                        "parent": parent_of(r, by_library),
                        "child": is_child(r),
                    }
                    for r in group
                ],
            }
        )

    done = sum(1 for r in runs if r.status == "완료")
    grid = (
        "var(--label-w) "
        f"repeat({len(axis.week_sundays)},var(--wk)) "
        f"repeat({len(axis.days)},var(--day)) var(--retreat) "
        f"repeat({len(axis.after_sundays)},var(--after))"
    )
    return {
        "axis": axis,
        "grid": grid,
        "mobile_groups": mobile_groups,
        "headers": axis.headers(),
        "sections": axis.sections(),
        "columns": axis.total,
        "shift_index": axis.shift_index,
        # 오늘 선을 그릴 열 — 오늘이 축 밖이면 None (그리지 않는다)
        "today_column": axis.column_of(today) if _축안에(axis, today) else None,
        "today": today.isoformat(),
        "departments": dept_blocks,
        "meta": meta,
        "total": len(runs),
        "done": done,
        # 저장된 상태가 아니라 날짜에서 계산한다 (4-10) — 저장 '지연' 은 없다 (4-3)
        "late": sum(1 for r in runs if overdue_of(r, today)),
        "open_date": open_date,
        "close_date": close_date,
    }


# 좁은 폭 목록에서 **날짜 없는 업무만 모으는 묶음** (4-1 · 4-13). 정수 주차와
# 안 섞이게 따로 둔다 — 개회일 자리로 떨어뜨리면 수련회 기간에 실제로 잡힌
# 업무와 구별이 안 된다(봐둘것 BJ-d 가 넓은 폭에서 짚은 그 자리다)
NO_DATE_BUCKET = "__nodate__"


def _by_week(runs: list[TaskRun], open_date: dt.date, axis: Axis):
    """실행 업무를 D-주차로 묶는다. 개회일 이후 업무는 수련회 기간으로 모은다.

    **날짜가 없는 업무는 따로 모은다** — 전에는 `start_date or open_date` 라
    「수련회 기간」 묶음에 개회일 날짜를 달고 섰다. 넓은 폭은 고쳤는데 좁은
    폭만 남아 있던 자리다(2026-09-25 커밋 전 검토).
    """
    buckets: dict[object, list[TaskRun]] = {}
    for run in runs:
        if run.start_date is None and run.end_date is None:
            buckets.setdefault(NO_DATE_BUCKET, []).append(run)
            continue
        start = run.start_date or run.end_date
        week = 0 if start >= open_date else max(1, dweek.week_of(open_date, start))
        buckets.setdefault(min(week, axis.first_week), []).append(run)

    out = []
    # 날짜 없는 묶음은 **맨 뒤**에 — 「이번 주에 뭐가 있나」 가 먼저다
    주차들 = sorted((w for w in buckets if w != NO_DATE_BUCKET),
                  key=lambda w: (w == 0, -w))
    for week in list(주차들) + ([NO_DATE_BUCKET] if NO_DATE_BUCKET in buckets else []):
        if week == NO_DATE_BUCKET:
            out.append(("날짜 없는 업무", "nodate", buckets[week]))
            continue
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
    # **후속 칸은 안 낸다** (`after_weeks=0`). 보드의 축이 뒤로 늘어난 것이
    # (2026-09-25) 여기까지 따라오면 「수련회 기간 · 8/30」 이라는 이름의 칸이
    # 셋 생긴다 — 아래 `else` 가 `after` 를 수련회로 읽기 때문이다.
    # **폐회 뒤 주에 업무를 놓게 할지는 사람이 정할 것**이라 지금은 전과
    # 같은 칸만 낸다(봐둘것 BJ-g · 커밋 전 검토가 잡았다)
    axis = Axis(open_date, close_date or open_date, dweek.PLANNING_FIRST_WEEK,
                after_weeks=0)
    out = []
    for cell in axis.headers():
        if cell["kind"] == "week":
            label = f"{cell['top']}주 · {cell['bottom']} 주"
        elif cell["kind"] == "day":
            label = f"{cell['bottom']} ({cell['top']})"
        elif cell["kind"] == "after":
            # 지금은 `after_weeks=0` 이라 안 오지만, 사람이 열기로 하면 여기다 —
            # **`else` 로 흘려 보내면 「수련회 기간」 이라는 거짓 이름이 붙는다**
            label = f"{cell['top']}주 · {cell['bottom']} 주"
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
