"""D-주차 계산과 명절 충돌 (CLAUDE.md 6-4, 6-5)."""

import datetime as dt

from app.domain import dweek


def test_anchor_sunday_is_the_sunday_before_opening():
    # 2026-08-21 은 금요일 → 직전 일요일 8/16 이 D-1주차
    assert dweek.anchor_sunday(dt.date(2026, 8, 21)) == dt.date(2026, 8, 16)


def test_anchor_sunday_skips_a_week_when_opening_on_sunday():
    """개회 당일을 준비 주간으로 셀 수는 없다."""
    assert dweek.anchor_sunday(dt.date(2026, 8, 23)) == dt.date(2026, 8, 16)


def test_week_dates_step_back_seven_days():
    open_date = dt.date(2026, 8, 21)
    assert dweek.week_date(open_date, 1) == dt.date(2026, 8, 16)
    assert dweek.week_date(open_date, 2) == dt.date(2026, 8, 9)
    # 목업 보드의 첫 칸 D-13주 = 5/24
    assert dweek.week_date(open_date, 13) == dt.date(2026, 5, 24)


def test_relative_position_round_trips():
    open_date = dt.date(2026, 8, 21)
    start, end = dt.date(2026, 5, 28), dt.date(2026, 8, 16)  # 시설 협조요청
    rel = dweek.relative_position(open_date, start, end)
    assert rel["default_d_week"] == 13
    assert rel["default_offset_days"] == 4  # 목요일
    again = dweek.resolve_dates(
        open_date,
        anchor=rel["date_anchor"],
        d_week=rel["default_d_week"],
        offset_days=rel["default_offset_days"],
        span_days=rel["default_span_days"],
    )
    assert again == (start, end)


def test_dates_move_but_keep_the_d_week_when_the_opening_moves():
    """개회일이 바뀌어도 D-주차와 요일이 유지된다."""
    summer, winter = dt.date(2026, 8, 21), dt.date(2027, 1, 15)
    start, _ = dweek.resolve_dates(summer, anchor="week", d_week=13, offset_days=0, span_days=7)
    moved, _ = dweek.resolve_dates(winter, anchor="week", d_week=13, offset_days=0, span_days=7)
    assert start == dt.date(2026, 5, 24)
    assert moved == dt.date(2026, 10, 18)
    assert start.weekday() == moved.weekday() == 6  # 둘 다 일요일
    assert dweek.week_of(winter, moved) == 13


def test_tasks_inside_the_retreat_anchor_to_the_opening_day():
    start, end = dweek.resolve_dates(
        dt.date(2027, 1, 15), anchor="open", d_week=None, offset_days=1, span_days=0
    )
    assert start == end == dt.date(2027, 1, 16)


def test_winter_retreat_collides_with_christmas_and_year_end():
    clashes = dweek.holiday_clashes(dt.date(2027, 1, 15))
    weeks = {c["d_week"]: c["name"] for c in clashes}
    assert weeks[4] == "성탄 전야"
    assert weeks[3] == "송구영신"


def test_summer_retreat_has_no_holiday_clash():
    assert dweek.holiday_clashes(dt.date(2026, 8, 21)) == []
