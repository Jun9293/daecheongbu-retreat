"""D-주차 계산과 명절 충돌 감지 (CLAUDE.md 6-4, 6-5).

교회 일정이 주일 중심으로 돌아가기 때문에 시간 축의 기준은 '주'다.
    D-1주차 = 개회일 직전 일요일
    D-N주차 = D-1주차 - (N-1) × 7일

라이브러리 업무는 절대 날짜가 아니라 이 상대 위치만 갖는다. 회차가 바뀌면
개회일만 새로 넣고 여기서 날짜를 다시 계산한다.
"""

from __future__ import annotations

import datetime as dt

# 보드 가로축에서 주 단위로 그리는 구간의 기본 범위
FIRST_D_WEEK = 13  # 업무가 없을 때 보드가 잡는 기본 시작 (D-13주)
LAST_WEEKLY_D_WEEK = 3  # 여기까지 주 단위, D-2주부터는 하루 단위

# 업무를 놓을 수 있는 가장 이른 주. 기획은 개회 반년 전부터 돈다 —
# 장소 탐방·견적, 주제 논의 같은 것들이 D-13주보다 훨씬 앞에 있다.
PLANNING_FIRST_WEEK = 26

# (월-일, 이름) — 이 날이 낀 주는 논의·검토가 막힌다
HOLIDAYS: tuple[tuple[str, str], ...] = (
    ("12-24", "성탄 전야"),
    ("12-25", "성탄"),
    ("12-31", "송구영신"),
    ("01-01", "신정"),
)


def anchor_sunday(open_date: dt.date) -> dt.date:
    """개회일 직전 일요일 = D-1주차.

    개회일이 일요일이면 그날이 아니라 일주일 전 일요일이다.
    (개회 당일을 준비 주간으로 셀 수는 없다)
    """
    # 일요일=0 으로 세는 요일값
    weekday = (open_date.weekday() + 1) % 7
    back = 7 if weekday == 0 else weekday
    return open_date - dt.timedelta(days=back)


def week_date(open_date: dt.date, d_week: int) -> dt.date:
    """D-{d_week}주차 일요일."""
    return anchor_sunday(open_date) - dt.timedelta(days=(d_week - 1) * 7)


def week_of(open_date: dt.date, day: dt.date) -> int:
    """어떤 날짜가 D-몇 주차에 들어가는지. 개회일 이후면 0 이하."""
    sunday = day - dt.timedelta(days=(day.weekday() + 1) % 7)
    return 1 + (anchor_sunday(open_date) - sunday).days // 7


def day_offset_in_week(day: dt.date) -> int:
    """그 주 일요일로부터 며칠째인지 (0~6)."""
    return (day.weekday() + 1) % 7


def resolve_dates(
    open_date: dt.date,
    *,
    anchor: str,
    d_week: int | None,
    offset_days: int,
    span_days: int,
) -> tuple[dt.date, dt.date]:
    """라이브러리의 상대 위치를 이번 회차의 실제 날짜로 바꾼다."""
    if anchor == "open":
        start = open_date + dt.timedelta(days=offset_days)
    else:
        start = week_date(open_date, d_week or FIRST_D_WEEK) + dt.timedelta(days=offset_days)
    return start, start + dt.timedelta(days=max(0, span_days))


def relative_position(open_date: dt.date, start: dt.date, end: dt.date | None = None) -> dict:
    """실제 날짜 → 라이브러리에 저장할 상대 위치. resolve_dates 의 역방향."""
    end = end or start
    if start >= open_date:
        return {
            "date_anchor": "open",
            "default_d_week": None,
            "default_offset_days": (start - open_date).days,
            "default_span_days": (end - start).days,
        }
    return {
        "date_anchor": "week",
        "default_d_week": week_of(open_date, start),
        "default_offset_days": day_offset_in_week(start),
        "default_span_days": (end - start).days,
    }


def holiday_in_week(sunday: dt.date) -> str | None:
    """그 주(일요일부터 7일) 안에 낀 명절 이름."""
    for i in range(7):
        day = sunday + dt.timedelta(days=i)
        key = day.strftime("%m-%d")
        for holiday_key, name in HOLIDAYS:
            if key == holiday_key:
                return name
    return None


def holiday_clashes(open_date: dt.date, first_week: int = FIRST_D_WEEK) -> list[dict]:
    """D-주차 중 명절 주간과 겹치는 것들.

    겨울 회차는 D-4주가 성탄, D-3주가 연말에 걸린다. 그 주말이 막히면
    논의와 검토가 통째로 밀리므로 회차를 만들기 전에 알려줘야 한다.
    """
    found = []
    for n in range(first_week, 0, -1):
        sunday = week_date(open_date, n)
        name = holiday_in_week(sunday)
        if name:
            found.append({"d_week": n, "sunday": sunday, "name": name})
    return found
