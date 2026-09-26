"""4단계 — 달력 화면 (CLAUDE.md 4-13 · 목업 E).

- 머리에 **범례** · 칸에 **수련회 음영**과 **꼬리표** · 일요일·공휴일은 붉은 글자
- **한 칸의 업무는 전부 보인다**(접기 없음) · 차례는 지연 → 진행중·대기 → 완료
- 지연 칩은 글자 앞에 **`!`** · 끊긴 칩은 **보드와 같은 팝업**(달력만 「상세 열기」)
- 날짜 없는 업무는 줄마다 **제목 · 담당팀**
- **공휴일 표에 없는 해는 조용히 비우지 않는다** — 「공휴일 표 없음」 을 한 줄 낸다

공휴일 값 자체는 박지 않는다(11-3) — **표가 말하는 것과 화면이 말하는 것이 같은지**를
잰다. 음력에서 오는 날은 사람이 확인할 몫이라 그 사실만 시험이 붙든다.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest

from app.domain import calendar as cal_domain
from app.domain import holidays
from tests.conftest import app_session
from tests.test_calendar import build, cell_on, cal_data  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "js" / "calendar.js").read_text(encoding="utf-8")


# ── ㄱ. 공휴일 표 ──────────────────────────────────────────────────


def test75_a01_표에_있는_해와_없는_해를_가른다():
    assert holidays.있나(holidays.아는해[0]) and holidays.있나(holidays.아는해[-1])
    assert not holidays.있나(holidays.아는해[-1] + 1)


def test75_a02_고정된_날은_해마다_같다():
    for year in holidays.아는해:
        assert holidays.이름(dt.date(year, 1, 1)) == "신정"
        assert holidays.이름(dt.date(year, 12, 25)) == "성탄절"
        assert holidays.이름(dt.date(year, 8, 15)) == "광복절"


# 사람이 달력과 대조해 정한 값 (2026-09-26 · 봐둘것 BJ-j). **이 표에만 적는다** —
# 코드가 같은 수를 또 들고 있으면 한쪽만 고쳐진다. 여기 있는 것은 「사람이 확인한
# 날」 이고, 그 날에 실제로 꼬리표와 붉은 글자가 뜨는지를 화면까지 내려가 잰다.
사람이_확인한_설날 = {2026: (2, 17), 2027: (2, 6), 2028: (1, 26)}


def test75_a03b_사람이_확인한_설날이_그대로다():
    """**2027 · 2028 은 2026-09-26 에 하루씩 당겼다** (봐둘것 BJ-j).

    그전 값(2/7 · 1/27)은 이 창이 적어 넣은 것이라 틀렸다. 앞뒤 하루씩의
    연휴도 함께 움직인다 — 설날만 옮기면 연휴가 설날을 건너뛴다.
    """
    for 해, (달, 날) in 사람이_확인한_설날.items():
        그날 = dt.date(해, 달, 날)
        assert holidays.이름(그날) == "설날", f"{그날} 이 설날이 아니다"
        assert holidays.이름(그날 - dt.timedelta(days=1)) == "설 연휴"
        assert holidays.이름(그날 + dt.timedelta(days=1)) == "설 연휴"
        # 옛 값에는 아무것도 안 남는다 — 남으면 나흘짜리 연휴가 된다
        if 해 != 2026:
            assert holidays.이름(그날 + dt.timedelta(days=2)) is None, f"{해} 옛 설날이 남았다"


# **안 건드리기로 한 것도 재어 둔다** (2026-09-26 커밋 전 검토 [E]) — 보고가
# 「다른 해·다른 명절 그대로」 를 `a03b` 로 가리켰는데 그것은 **설날만** 잰다.
안_건드린_명절 = {
    "추석": {2026: (9, 25), 2027: (9, 15), 2028: (10, 3)},
    "부처님오신날": {2026: (5, 24), 2027: (5, 13), 2028: (5, 2)},
}


def test75_a03d_설날_말고는_아무것도_안_움직였다():
    """설날 넷만 고쳤다 — 추석과 부처님오신날은 그대로여야 한다.

    **낱말만 잰다** 가 아니다: 표를 실제로 불러 이름을 견준다. 2028 추석은
    개천절과 같은 날이라 이름이 그쪽으로 갈릴 수 있어 **둘 중 하나면** 된다.
    """
    for 이름, 해별 in 안_건드린_명절.items():
        for 해, (달, 날) in 해별.items():
            그날 = dt.date(해, 달, 날)
            난것 = holidays.이름(그날)
            assert 난것 in (이름, "개천절"), f"{그날} 이 {난것} 이다 — {이름} 이어야 한다"


def test75_a03c_화면이_그_날을_붉게_칠하고_이름을_단다(cal_data):
    """표만 고치고 화면이 안 따라오면 고친 뜻이 없다 — **칸까지 내려가 잰다.**"""
    for 해, (달, 날) in 사람이_확인한_설날.items():
        with app_session() as db:
            view = build(db, cal_data, scope="all", month=f"{해}-{달:02d}")
        칸 = cell_on(view, f"{해}-{달:02d}-{날:02d}")
        assert 칸["holiday"] == "설날", f"{해} 설날 칸에 이름이 없다"
        assert 칸["red"] is True, f"{해} 설날이 안 붉다"
        assert 칸["tag"] == {"글": "설날", "결": "holiday"}


def test75_a03_표에_없는_해는_이름을_안_낸다():
    없는해 = holidays.아는해[-1] + 1
    assert holidays.이름(dt.date(없는해, 1, 1)) is None, "모르는 해에 이름을 지어냈다"


def test75_a04_표가_없으면_화면이_그렇게_말한다(admin_client, cal_data):
    없는해 = holidays.아는해[-1] + 1
    page = admin_client.get(f"/calendar?month={없는해}-03&scope=all").text
    assert "공휴일 표 없음" in page
    # 표가 있는 달에는 그 줄이 안 뜬다 — 「이상 없음」 이 쌓이면 진짜 경고가 묻힌다
    page2 = admin_client.get("/calendar?month=2026-08&scope=all").text
    assert "공휴일 표 없음" not in page2


# ── ㄴ. 칸 — 수련회 음영 · 꼬리표 · 붉은 날짜 ─────────────────────


def test75_b01_수련회_날에_음영이_깔리고_개회일에_꼬리표가_붙는다(cal_data):
    with app_session() as db:
        view = build(db, cal_data, scope="all", month="2026-08")
    칸 = cell_on(view, "2026-08-21")          # cal_data 의 개회일(OPEN)
    assert 칸["retreat"] is True
    assert 칸["tag"] == {"글": "수련회 개회", "결": "open"}
    안쪽 = cell_on(view, "2026-08-22")
    assert 안쪽["retreat"] is True and 안쪽["tag"]["글"] == "수련회"


def test75_b02_일요일과_공휴일은_붉은_글자다(cal_data):
    with app_session() as db:
        view = build(db, cal_data, scope="all", month="2026-08")
    일요일 = cell_on(view, "2026-08-16")       # 2026-08-16 은 일요일
    assert 일요일["red"] is True
    광복절 = cell_on(view, "2026-08-15")
    assert 광복절["red"] is True and 광복절["holiday"] == "광복절"
    평일 = cell_on(view, "2026-08-18")
    assert 평일["red"] is False


def test75_b03_꼬리표는_한_줄뿐이다(cal_data):
    """수련회 개회 > 수련회 > 공휴일 > 오늘 차례로 **하나만** 고른다."""
    with app_session() as db:
        view = build(db, cal_data, scope="all", month="2026-08")
    for week in view["weeks"]:
        for 칸 in week:
            assert 칸["tag"] is None or set(칸["tag"]) == {"글", "결"}


def test75_b04_화면이_그_값을_그대로_그린다(admin_client, cal_data):
    page = admin_client.get("/calendar?month=2026-08&scope=all").text
    assert 'class="cal-cell' in page and " span\"" in page.replace("'", '"')
    assert 'class="cal-tag open"' in page
    assert 'class="cal-d red"' in page
    # 색은 4-0 의 값만 쓴다 — 여기서 새로 짓지 않는다
    assert ".cal-cell.span{background:var(--span-retreat)}" in CSS
    assert ".cal-d.red{color:var(--red-ink)}" in CSS


# ── ㄷ. 칸 안의 차례와 칩 ─────────────────────────────────────────


def _급수(dot: dict) -> int:
    """칸 안의 차례 — **지연 0 · 진행중·대기 1 · 완료 2** (목업 E)."""
    if dot["overdue"]:
        return 0
    return 2 if dot["status"] == "완료" else 1


def test75_c01_차례는_지연_진행중대기_완료다(cal_data):
    """급한 것이 위로 온다 (목업 E).

    **한 칸 안에서 지연과 미지연은 섞일 수 없다** — 늦음은 그 칸의 날짜 하나로
    정해지기 때문이다. 그래서 지난 날 칸(지연 + 완료)과 앞으로 올 날 칸
    (진행중·대기 + 완료)을 **둘 다** 보고, 급수가 오름차순인지 잰다.
    """
    from app import models
    from sqlalchemy import select

    with app_session() as db:
        앞날 = list(db.scalars(select(models.TaskRun).where(
            models.TaskRun.retreat_id == cal_data["retreat_id"],
            models.TaskRun.end_date == dt.date(2026, 8, 12))))
        assert len(앞날) >= 3, "한 칸에 셋이 안 선다"
        앞날[0].status, 앞날[1].status, 앞날[2].status = "완료", "진행중", "대기"
        # 지난 날 칸(8/5)에는 이미 지연이 서 있다 — 거기에 완료를 하나 보낸다
        앞날[2].end_date, 앞날[2].status = dt.date(2026, 8, 5), "완료"
        db.commit()
        view = build(db, cal_data, scope="all", month="2026-08")

    for 날 in ("2026-08-12", "2026-08-05"):
        점들 = cell_on(view, 날)["dots"]
        assert len(점들) >= 2, f"{날} 칸에 잴 것이 없다"
        급수들 = [_급수(d) for d in 점들]
        assert 급수들 == sorted(급수들), f"{날} 칸의 차례가 어긋났다: {급수들}"
        assert len(set(급수들)) > 1, f"{날} 칸에 한 급만 있어 차례를 못 쟀다"


def test75_c02_지연_칩은_글자_앞에_느낌표다(cal_data):
    """지연은 **글자 앞의 `!` 하나**다 (목업 E · 보드의 바와 같은 규칙 · 4-1).

    **회차가 끝난 뒤에는 지연이 없다**(4-10 의 그 경계 · `overdue_of`) — 그래서
    화면으로 재려면 아직 안 끝난 회차여야 한다. 여기서는 구조가 내는 값과
    매크로가 그 값을 쓰는지를 본다.
    """
    from app import models
    from sqlalchemy import select

    with app_session() as db:
        run = db.scalars(select(models.TaskRun).where(
            models.TaskRun.retreat_id == cal_data["retreat_id"])).first()
        run.end_date = dt.date(2026, 8, 3)
        run.status = "대기"
        db.commit()
        view = build(db, cal_data, scope="all", month="2026-08")   # today=2026-08-10

    칸 = cell_on(view, "2026-08-03")
    assert 칸["dots"] and 칸["dots"][0]["overdue"] is True
    매크로 = (ROOT / "app" / "templates" / "partials" / "caldot.html").read_text(encoding="utf-8")
    assert 'class="cal-bang"' in 매크로 and "dot.overdue" in 매크로
    assert ".cal-dot .cal-bang{color:var(--red-ink)" in CSS


def test75_c03_칩은_보드와_같은_팝업을_연다():
    """**부품은 `taskpop.js` 하나다** (4-1 · 4-13) — 달력에서만 「상세 열기」 를 켠다."""
    assert "TaskPop.open" in JS and "상세열기: true" in JS
    t = (ROOT / "app" / "templates" / "calendar.html").read_text(encoding="utf-8")
    assert "js/taskpop.js" in t
    # 끊긴 칩에만 연다 — 안 끊긴 칩은 제목이 다 보인다 (보드와 같은 조건)
    assert "function 끊겼나(" in JS


def test75_c04_손가락_기기는_첫_탭이_칠함이고_두_번째가_드로어다():
    assert "matchMedia('(hover: none)')" in JS
    assert "탭한점" in JS and "Drawer.open" in JS


def test75_c05_한_줄_메타는_보드와_같은_함수에서_나온다(cal_data):
    with app_session() as db:
        view = build(db, cal_data, scope="all", month="2026-08")
    점 = next(d for week in view["weeks"] for c in week for d in c["dots"])
    assert 점["meta"], "팝업 줄이 비어 있다"
    src = (ROOT / "app" / "domain" / "calendar.py").read_text(encoding="utf-8")
    assert "board_domain.popup_meta(" in src


# ── ㄹ. 날짜 없는 업무 ────────────────────────────────────────────


def test75_d01_줄마다_제목과_담당팀이_선다(cal_data):
    from app import models

    with app_session() as db:
        run = db.scalars(__import__("sqlalchemy").select(models.TaskRun).where(
            models.TaskRun.retreat_id == cal_data["retreat_id"])).first()
        run.start_date = None
        run.end_date = None
        db.commit()
        view = build(db, cal_data, scope="all", month="2026-08")
    assert view["undated"], "날짜 없는 업무가 안 모였다"
    assert view["undated"][0]["dept_name"]
    # 달력 칸의 점에는 안 붙인다 — 거기는 자리가 없다
    점 = next((d for week in view["weeks"] for c in week for d in c["dots"]), None)
    assert 점 is None or "dept_name" not in 점


def test75_d02_안내는_상세에서_날짜를_정하라고_말한다(admin_client, cal_data):
    from app import models

    with app_session() as db:
        run = db.scalars(__import__("sqlalchemy").select(models.TaskRun).where(
            models.TaskRun.retreat_id == cal_data["retreat_id"])).first()
        run.start_date = None
        run.end_date = None
        db.commit()
    page = admin_client.get("/calendar?month=2026-08&scope=all").text
    assert "날짜를 정하면 달력에 나타납니다" in page
    assert "보드에서 기간을 정해 주세요" not in page, "옛 문구가 남았다"


# ── ㅁ. 범례 ──────────────────────────────────────────────────────


def test75_e01_범례가_넷을_말한다(admin_client, cal_data):
    page = admin_client.get("/calendar?month=2026-08&scope=all").text
    for 말 in ("업무 기간", "수련회", "지연", "완료"):
        assert 말 in page
    assert 'class="callegend"' in page
    assert ".callegend .lg.retreat{background:var(--span-retreat)}" in CSS
    assert ".callegend .lg.span{background:var(--span)}" in CSS
