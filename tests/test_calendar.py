"""달력 보기 (CLAUDE.md 4-13). 수용 기준 1~17.

**`today` 를 주입합니다.** 실행 날짜에 따라 갈리는 테스트는 며칠 뒤 아무도
모르게 빨간불이 되고, 그러면 테스트를 안 보게 됩니다 — 진단 패널(4-10)과
수련회 진행(5장)에서 해 온 방식 그대로입니다.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app import models
from app.domain import calendar as cal_domain
from tests.conftest import app_session, login_as

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

OPEN = dt.date(2026, 8, 21)
CLOSE = dt.date(2026, 8, 23)
TODAY = dt.date(2026, 8, 10)      # 회차 기간 안쪽 달(8월)의 어느 날


@pytest.fixture
def cal_data(admin_client):
    """부서 2개 · 업무 여럿. 마감이 지난 것, 날짜가 없는 것, 한 날에 몰린 것."""
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회 Belong", start_date=OPEN, end_date=CLOSE)
        db.add(retreat)
        db.flush()
        depts = {}
        for order, (key, name, color) in enumerate([
            ("chongmuM", "1 총무M", "#2F4858"),
            ("hebron", "5 헤브론", "#4A8A5C"),
        ]):
            dept = models.Department(
                retreat_id=retreat.id, key=key, name=name,
                color_tag=color, sort_order=order)
            db.add(dept)
            depts[key] = dept
        db.flush()

        lead = models.User(
            name="헤브론 리더", phone_number="01055556666", role="dept_lead",
            department_id=depts["hebron"].id)
        db.add(lead)
        admin = db.scalars(
            select(models.User).where(models.User.role == "admin")).first()
        db.flush()

        runs = {}

        def task(title, *, end, dept="chongmuM", status="대기", kind="main",
                 assignee=None, included=True, start=None):
            lib = models.TaskLibrary(title=title, kind=kind, default_d_week=5)
            db.add(lib)
            db.flush()
            run = models.TaskRun(
                library_id=lib.id, retreat_id=retreat.id, included=included,
                department_id=depts[dept].id, assignee_id=assignee,
                d_week=5, start_date=start or end, end_date=end, status=status)
            db.add(run)
            db.flush()
            runs[title] = run.id
            return run

        # 한 날(8/12)에 다섯 — PER_DAY(3) 를 넘겨 접힌다
        for i in range(5):
            task(f"몰린 업무 {i + 1}", end=dt.date(2026, 8, 12),
                 assignee=admin.id if i < 2 else None)
        # 마감이 지났는데 미완료 — 날짜에서 계산해 붉게 (저장된 상태는 '진행중')
        task("지각한 업무", end=dt.date(2026, 8, 5), status="진행중",
             assignee=admin.id)
        # 마감이 지났지만 완료 — 붉지 않다
        task("끝낸 업무", end=dt.date(2026, 8, 6), status="완료",
             assignee=admin.id)
        # 오늘 마감
        task("오늘 업무", end=TODAY, assignee=admin.id)
        # 다른 부서
        task("헤브론 업무", end=dt.date(2026, 8, 18), dept="hebron",
             assignee=lead.id)
        # 일정 분류도 놓는다 — 날짜만 지키면 되지만 날짜는 있다
        task("총 리허설", end=dt.date(2026, 8, 20), kind="schedule")
        # 다음 달
        task("다음 달 업무", end=dt.date(2026, 9, 3), assignee=admin.id)
        # **마감일이 없다** — 달력 아래에 따로 모인다
        task("날짜 없는 업무", end=None, start=None, assignee=admin.id)
        # 이번 회차에 빼기로 한 것 — 놓지 않는다
        task("빼놓은 업무", end=dt.date(2026, 8, 12), included=False)

        db.commit()
        return {"retreat_id": retreat.id, "runs": runs,
                "admin_id": admin.id, "lead_id": lead.id}


def build(db, cal_data, **kw):
    kw.setdefault("today", TODAY)
    return cal_domain.build(
        db, db.get(models.Retreat, cal_data["retreat_id"]), **kw)


def me(db, cal_data):
    return db.get(models.User, cal_data["admin_id"])


def cell_on(view, iso):
    for week in view["weeks"]:
        for cell in week:
            if cell["date"] == iso:
                return cell
    return None


def titles_on(view, iso):
    cell = cell_on(view, iso)
    return [d["title"] for d in cell["dots"] + cell["more"]]


def all_titles(view):
    return [d["title"] for week in view["weeks"] for cell in week
            for d in cell["dots"] + cell["more"]]


# ---------------------------------------------------------------- 1. 화면


def test_01_사이드바에_달력이_있고_열린다(admin_client, cal_data):
    page = admin_client.get("/calendar")
    assert page.status_code == 200
    assert "</html>" in page.text

    shell = open("app/templates/retreat_base.html", encoding="utf-8").read()
    assert "'/calendar'" in shell and "'달력'" in shell
    # 준비 단계 바로 아래
    assert shell.index("'/board'") < shell.index("'/calendar'") < shell.index("'/live'")
    assert 'href="/calendar"' in page.text


# ---------------------------------------------------------------- 2. 마감일 점


def test_02_마감일에_점이_찍히고_기간_띠가_아니다(cal_data):
    """15일짜리 업무를 띠로 그리면 한 주에 몇 개만 있어도 달력이 꽉 찬다."""
    with app_session() as db:
        view = build(db, cal_data, scope="all")

    # 8/1~8/20 이 기간인 업무를 넣어도 마감일 하루에만 선다
    with app_session() as db:
        run = db.get(models.TaskRun, cal_data["runs"]["총 리허설"])
        run.start_date = dt.date(2026, 8, 1)
        db.commit()
        view = build(db, cal_data, scope="all")

    days = [cell["date"] for week in view["weeks"] for cell in week
            if any(d["title"] == "총 리허설" for d in cell["dots"] + cell["more"])]
    assert days == ["2026-08-20"], f"하루가 아니라 {len(days)}일에 걸쳐 그렸다"

    # 일정 분류도 놓는다 — 날짜만 지키면 되지만 날짜는 있다
    assert "총 리허설" in all_titles(view)
    # 이번 회차에 빼기로 한 것은 놓지 않는다
    assert "빼놓은 업무" not in all_titles(view)


# ---------------------------------------------------------------- 3. 날짜 없는 업무


def test_03_마감일이_없는_업무가_따로_모인다(admin_client, cal_data):
    """**놓을 자리가 없다고 조용히 빼면 그게 정확히 놓치는 지점이다.**"""
    with app_session() as db:
        view = build(db, cal_data, scope="all")

    assert [d["title"] for d in view["undated"]] == ["날짜 없는 업무"]
    assert "날짜 없는 업무" not in all_titles(view)

    page = admin_client.get("/calendar?scope=all").text
    assert "날짜가 없는 업무 1건" in page


# ---------------------------------------------------------------- 4. 쌓기·접기


def test_04_한_날에_여럿이면_쌓이고_넘치면_접힌다(admin_client, cal_data):
    with app_session() as db:
        view = build(db, cal_data, scope="all")

    cell = cell_on(view, "2026-08-12")
    assert len(cell["dots"]) == cal_domain.PER_DAY == 3
    assert len(cell["more"]) == 2, "넘친 것이 접히지 않았다"
    assert len(titles_on(view, "2026-08-12")) == 5

    page = admin_client.get("/calendar?scope=all").text
    assert "외 2건" in page
    assert "<details" in page          # 눌러서 편다


# ---------------------------------------------------------------- 5·6·7. 생김새


def test_05_부서_색과_상태가_보드와_같게_나온다(cal_data):
    """**보드와 같은 규칙을 쓴다. 두 벌이 되면 어긋난다.**"""
    from app.domain import board as board_domain

    with app_session() as db:
        view = build(db, cal_data, scope="all")
        by_title = {d["title"]: d
                    for week in view["weeks"] for cell in week
                    for d in cell["dots"] + cell["more"]}

    assert by_title["헤브론 업무"]["color"] == "#4A8A5C"
    assert by_title["오늘 업무"]["color"] == "#2F4858"

    # 상태 4종이 보드의 bar_style 에서 그대로 나온다
    assert by_title["끝낸 업무"]["background"] == board_domain.BAR_DONE[0]
    assert by_title["지각한 업무"]["border"] == board_domain.BAR_LATE[1]
    assert by_title["오늘 업무"]["background"] == board_domain.BAR_TODO_BG
    with app_session() as db:
        run = db.get(models.TaskRun, cal_data["runs"]["오늘 업무"])
        run.status = "진행중"
        db.commit()
        wip = build(db, cal_data, scope="all")
    assert next(d for week in wip["weeks"] for cell in week
                for d in cell["dots"] + cell["more"]
                if d["title"] == "오늘 업무")["background"] \
        == board_domain.BAR_WIP_BG


def test_06_기한_초과가_날짜에서_계산된다(cal_data):
    """저장된 '지연' 이 아니다 — 놓친 사람이 직접 눌러야 알아차리는 구조를
    만들지 않는다 (4-10)."""
    from app.domain import board as board_domain

    with app_session() as db:
        view = build(db, cal_data, scope="all")
        by_title = {d["title"]: d
                    for week in view["weeks"] for cell in week
                    for d in cell["dots"] + cell["more"]}

    late = by_title["지각한 업무"]
    assert late["status"] == "진행중", "저장된 상태는 '지연' 이 아니다"
    assert late["overdue"] is True
    assert late["overdue_days"] == 5            # 8/5 → 8/10
    assert late["background"] == board_domain.BAR_LATE[0]

    # 마감이 지났어도 완료면 붉지 않다
    assert by_title["끝낸 업무"]["overdue"] is False
    # 아직 안 지난 것도 붉지 않다
    assert by_title["헤브론 업무"]["overdue"] is False

    # **오늘 마감은 아직 지나지 않은 것이다**
    assert by_title["오늘 업무"]["overdue"] is False


def test_07_오늘_칸이_표시된다(admin_client, cal_data):
    with app_session() as db:
        view = build(db, cal_data, scope="all")

    marked = [cell["date"] for week in view["weeks"] for cell in week
              if cell["is_today"]]
    assert marked == [TODAY.isoformat()]

    page = admin_client.get("/calendar?scope=all").text
    assert "cal-cell" in page and "today" in page


# ---------------------------------------------------------------- 8. 상세 패널


def test_08_점을_누르면_그_자리에서_패널이_열린다(admin_client, cal_data):
    """수용기준 6 · 9 — 보드로 넘어가지 않는다.

    전에는 `/board?task=` 로 넘겨 보냈다. 그러면 **보던 달과 범위 칩을
    잃고**, 돌아오려면 뒤로 가야 했다.
    """
    page = admin_client.get("/calendar?scope=all").text
    run_id = cal_data["runs"]["오늘 업무"]

    # 점이 자기가 어느 업무인지 들고 있다 — 눌러서 그 자리에서 연다
    assert f'data-run="{run_id}"' in page
    assert 'id="drawer"' in page, "달력에 상세 패널이 없다"
    assert "calendar.js" in page and "drawer.js" in page

    # 자바스크립트가 죽었을 때를 위한 길은 남겨 둔다 (가운데 버튼 · 새 탭)
    assert f'href="/board?task={run_id}"' in page
    assert admin_client.get(f"/board?task={run_id}").status_code == 200

    # `/calendar?task=123` 으로 열린 채 시작한다 (수용기준 9)
    assert admin_client.get(f"/calendar?task={run_id}&scope=all").status_code == 200
    js = admin_client.get("/static/js/drawer.js").text
    assert "get('task')" in js


def test_08b_패널이_한_벌이다(admin_client, cal_data):
    """수용기준 11 — 보드와 달력이 **같은 조각·같은 스크립트**를 쓴다.

    두 벌이 되면 논의·상태·첨부·선후행이 두 곳에서 갈리고, **갈린 쪽을
    아무도 눈치채지 못한다.** 그래서 "둘 다 되더라" 가 아니라 **경로가
    하나인지**를 본다 — 되는 것은 베껴 놓아도 된다.
    """
    board_view = open("app/templates/board.html", encoding="utf-8").read()
    cal_view = open("app/templates/calendar.html", encoding="utf-8").read()

    include = 'include "partials/drawer.html"'
    assert include in board_view, "보드가 패널 조각을 include 하지 않는다"
    assert include in cal_view, "달력이 패널 조각을 include 하지 않는다"

    # 어느 쪽도 패널을 자기 안에 다시 그려 두지 않았다
    for name, view in (("board.html", board_view), ("calendar.html", cal_view)):
        assert 'id="drawer"' not in view, f"{name} 이 패널을 따로 갖고 있다"
        assert 'id="dtabs"' not in view, f"{name} 이 탭을 따로 갖고 있다"

    # 움직이는 코드도 한 벌 — board.js 에 패널 코드가 남아 있으면 안 된다
    board_js = open("app/static/js/board.js", encoding="utf-8").read()
    for moved in ("function renderDrawer", "function renderLog",
                  "function renderFiles", "function statMenu"):
        assert moved not in board_js, f"board.js 에 {moved} 가 남아 있다"

    drawer_js = open("app/static/js/drawer.js", encoding="utf-8").read()
    for kept in ("function renderDrawer", "function renderLog",
                 "function renderFiles", "function statMenu"):
        assert kept in drawer_js

    # 두 화면이 같은 파일을 싣는다
    assert "drawer.js" in admin_client.get("/board").text
    assert "drawer.js" in admin_client.get("/calendar?scope=all").text


def test_08c_상태를_바꾸면_점이_따라_바뀐다(admin_client, cal_data):
    """수용기준 8 — **다시 불러오지 않는다.** 보던 달을 잃으면 안 된다."""
    run_id = cal_data["runs"]["오늘 업무"]
    res = admin_client.post(f"/board/task/{run_id}/status", json={"status": "완료"})
    assert res.status_code == 200
    view = res.json()
    # 점을 다시 칠할 재료를 그 응답이 들고 있다 — 보드의 바와 같은 값이다
    # **접두사 없는 쌍을 두지 않는다** — 보드의 바인지 달력의 점인지가
    # 이름에 있어야, 세 번째 화면이 생겼을 때 아무거나 집지 않는다
    assert "bar_background" in view and "bar_border" in view
    assert "dot_background" in view and "dot_border" in view
    assert "background" not in view and "border" not in view

    js = open("app/static/js/calendar.js", encoding="utf-8").read()
    assert "onStatus" in js
    assert "cal-dot" in js
    assert "location.reload" not in js, "달력을 다시 불러오면 보던 달을 잃는다"


def test_08d_닫으면_보던_달과_칩이_그대로다(admin_client, cal_data):
    """수용기준 7 — 패널은 겹쳐 뜰 뿐 화면을 갈아치우지 않는다."""
    page = admin_client.get("/calendar?month=2026-08&scope=all&only_open=1").text
    # 칩 상태를 구조가 실어 보낸다 — 화면 코드가 클래스를 뒤져 알아내지 않는다
    assert 'data-only-open="1"' in page
    assert 'data-scope="all"' in page
    # 달 값은 화면이 내보내는 그대로다 (`2026-08-01`) — 4-13 의 그 함정
    assert 'data-month="2026-08-01"' in page
    # 패널을 여닫는 것은 주소를 바꾸지 않는다
    js = open("app/static/js/calendar.js", encoding="utf-8").read()
    assert "location.href" not in js and "location.search =" not in js


# ---------------------------------------------------------------- 9~13. 칩


def test_09_범위_칩_셋이_동작하고_기본이_내_것이다(admin_client, cal_data):
    with app_session() as db:
        person = me(db, cal_data)
        mine = build(db, cal_data, user=person, my_dept_key="chongmuM")
        assert mine["scope"] == "mine", "기본이 '내 것' 이 아니다"
        # 담당자가 나인 것만
        assert "헤브론 업무" not in all_titles(mine)
        assert "오늘 업무" in all_titles(mine)

        dept = build(db, cal_data, user=person, my_dept_key="hebron",
                     scope="dept")
        assert [t for t in all_titles(dept)] == ["헤브론 업무"]

        every = build(db, cal_data, user=person, my_dept_key="chongmuM",
                      scope="all")
        assert "헤브론 업무" in all_titles(every)
        assert len(all_titles(every)) > len(all_titles(mine))

    # 주소를 안 주면 기본이 '내 것'
    page = admin_client.get("/calendar?scope=mine").text
    assert 'aria-pressed="true"' in page


def test_10_부서를_키로_비교한다(admin_client, cal_data):
    """**회차를 두 번 열어도 맞아야 한다.** Department 행은 회차마다 새로
    만들어지므로 id 로 보면 새 회차가 열리는 순간 자기 부서 업무가 사라진다."""
    with app_session() as db:
        # 같은 키로 두 번째 회차의 부서를 만든다 (회차를 새로 연 상황)
        second = models.Retreat(
            name="2027 겨울수련회", start_date=dt.date(2027, 1, 8),
            end_date=dt.date(2027, 1, 10))
        db.add(second)
        db.flush()
        fresh_dept = models.Department(
            retreat_id=second.id, key="hebron", name="5 헤브론",
            color_tag="#4A8A5C", sort_order=0)
        db.add(fresh_dept)
        db.flush()
        # 리더의 계정이 **새 회차의 부서 행**을 가리키게 한다
        lead = db.get(models.User, cal_data["lead_id"])
        lead.department_id = fresh_dept.id
        db.commit()

        from app.domain.departments import department_key_of

        key = department_key_of(db, lead)
        assert key == "hebron"

        # 옛 회차의 달력에서도 자기 부서 업무가 그대로 보인다
        view = build(db, cal_data, user=lead, my_dept_key=key, scope="dept")
        assert all_titles(view) == ["헤브론 업무"], \
            "새 회차가 열리자 자기 부서 업무가 사라졌다 — id 로 비교하고 있다"


def test_11_부서가_없으면_우리_부서_칩이_안_나온다(admin_client, cal_data):
    with app_session() as db:
        person = me(db, cal_data)
        without = build(db, cal_data, user=person, my_dept_key=None)
        assert [s["value"] for s in without["scopes"]] == ["mine", "all"]

        # 굳이 dept 로 불러도 '내 것' 으로 떨어진다 — 빈 화면을 만나지 않게
        fallen = build(db, cal_data, user=person, my_dept_key=None, scope="dept")
        assert fallen["scope"] == "mine"

        withdept = build(db, cal_data, user=person, my_dept_key="hebron")
        assert [s["value"] for s in withdept["scopes"]] == ["mine", "dept", "all"]


def test_12_고른_범위가_다음에_열_때_유지된다(admin_client, cal_data):
    picked = admin_client.get("/calendar?scope=all&only_open=1")
    assert picked.status_code == 200

    from app.routers.calendar import OPEN_COOKIE, SCOPE_COOKIE

    assert admin_client.cookies.get(SCOPE_COOKIE) == "all"
    assert admin_client.cookies.get(OPEN_COOKIE) == "1"

    # 주소에 아무것도 안 줘도 지난번 것으로 열린다
    again = admin_client.get("/calendar").text
    assert "헤브론 업무" in again          # scope=all 이 유지됐다
    assert "끝낸 업무" not in again        # only_open 이 유지됐다


def test_13_미완료만이_동작한다(cal_data):
    with app_session() as db:
        every = build(db, cal_data, scope="all")
        assert "끝낸 업무" in all_titles(every)

        open_only = build(db, cal_data, scope="all", only_open=True)
        assert "끝낸 업무" not in all_titles(open_only)
        assert "지각한 업무" in all_titles(open_only)


# ---------------------------------------------------------------- 14·15. 달


def test_14_처음_열면_오늘이_든_달_회차_밖이면_회차_시작_달(cal_data):
    with app_session() as db:
        retreat = db.get(models.Retreat, cal_data["retreat_id"])

        # 오늘이 회차 기간 안 → 오늘이 든 달
        inside = cal_domain.month_of(None, today=OPEN, retreat=retreat)
        assert inside == dt.date(2026, 8, 1)

        # 오늘이 회차 기간 밖 → 회차가 시작하는 달
        outside = cal_domain.month_of(
            None, today=dt.date(2027, 3, 15), retreat=retreat)
        assert outside == dt.date(2026, 8, 1)

        # 명시하면 그 달
        asked = cal_domain.month_of(
            "2026-11-01", today=OPEN, retreat=retreat)
        assert asked == dt.date(2026, 11, 1)
        # 이상한 값은 조용히 기본으로
        assert cal_domain.month_of("엉망", today=OPEN, retreat=retreat) \
            == dt.date(2026, 8, 1)


def test_15_이전_다음_달과_오늘이_동작하고_칩이_유지된다(admin_client, cal_data):
    # 해를 넘겨도 맞는다
    assert cal_domain.shift_month(dt.date(2026, 12, 1), 1) == dt.date(2027, 1, 1)
    assert cal_domain.shift_month(dt.date(2026, 1, 1), -1) == dt.date(2025, 12, 1)

    with app_session() as db:
        view = build(db, cal_data, scope="all")
        assert view["prev"] == "2026-07-01"
        assert view["next"] == "2026-09-01"
        assert view["today_month"] == "2026-08-01"

        # **회차 기간을 벗어난 달로도 간다. 막지 않는다**
        far = build(db, cal_data, scope="all", month="2027-05-01")
        assert far["label"] == "2027년 5월"
        assert all_titles(far) == []

    # 달을 넘기는 링크가 지금 칩을 달고 다닌다
    page = admin_client.get("/calendar?scope=all&only_open=1").text
    assert "month=2026-09-01&amp;scope=all" in page or \
        "month=2026-09-01&scope=all" in page
    next_month = admin_client.get("/calendar?month=2026-09-01").text
    assert "다음 달 업무" in next_month


# ---------------------------------------------------------------- 16. 휴대폰


def test_16_좁은_화면에서_주_단위_목록으로_바뀐다(admin_client, cal_data):
    """7칸 달력은 글자가 안 들어간다. 억지로 우겨넣지 않는다."""
    page = admin_client.get("/calendar?scope=all").text
    # 두 모양이 함께 그려지고 CSS 가 하나만 보여준다
    assert 'class="calwrap"' in page and 'class="calweeks"' in page
    assert 'class="calweek"' in page

    css = open("app/static/css/retreat.css", encoding="utf-8").read()
    narrow = css[css.index(".calweeks{"):]
    assert ".calweeks{display:none}" in css        # 넓은 화면에서는 안 쓴다
    block = css[css.rindex("@media (max-width:820px){"):]
    assert ".calwrap{display:none}" in block
    assert ".calweeks{display:block" in block


# ---------------------------------------------------------------- 17. 빈 달


def test_17_업무가_하나도_없는_달에서도_죽지_않는다(admin_client, cal_data):
    with app_session() as db:
        empty = build(db, cal_data, scope="all", month="2027-05-01")
        assert empty["count"] == 0
        assert empty["weeks"], "격자가 아예 안 그려졌다"
        assert all(cell["dots"] == [] and cell["more"] == []
                   for week in empty["weeks"] for cell in week)

    page = admin_client.get("/calendar?month=2027-05-01&scope=all")
    assert page.status_code == 200
    assert "이 달에는 마감인 업무가 없습니다" in page.text \
        or "날짜가 없는 업무" in page.text

    # 업무가 하나도 없는 회차여도 죽지 않는다
    with app_session() as db:
        bare = models.Retreat(
            name="빈 회차", start_date=dt.date(2027, 6, 4),
            end_date=dt.date(2027, 6, 6))
        db.add(bare)
        db.commit()
        bare_id = bare.id
        view = cal_domain.build(db, bare, today=TODAY, scope="all")
        assert view["count"] == 0 and view["undated"] == []
    assert admin_client.get(
        f"/calendar?retreat_id={bare_id}").status_code == 200

    # 개회일이 없는 회차도
    with app_session() as db:
        blank = models.Retreat(name="개회일 미정")
        db.add(blank)
        db.commit()
        assert cal_domain.build(db, blank, today=TODAY, scope="all")["weeks"]


# ════════════════════════════════════════════════════════════════════
#  리뷰에서 나온 것 — 수용기준 1~5 · 12
# ════════════════════════════════════════════════════════════════════
#
# 달력의 `onDates` 를 **넘기는 걸 빠뜨려서** 패널은 새 마감일을 말하는데
# 점은 옛 칸에 남아 있었다. 베껴 놓아서 갈린 것이 아니라 **안 넘겨서** 갈렸다.


import re

JS_DIR = ROOT / "app" / "static" / "js"


def read_js(name: str) -> str:
    return (JS_DIR / name).read_text(encoding="utf-8")


def code_only(js: str) -> str:
    """주석을 걷어낸 코드.

    **설명하는 글에 적힌 낱말을 코드로 착각하지 않기 위해서다.** 이 저장소는
    "왜 그렇게 했는가" 를 주석에 길게 적으므로, 고친 내용을 설명한 문장이
    그대로 시험에 걸린다 — 실제로 `iso < today` 를 지웠다고 적은 주석 때문에
    "날짜를 아직 견주고 있다" 로 잘못 읽혔다.

    **문자열·정규식 안의 `//` 를 자르지 않는다.** 줄에서 `//` 만 찾아 뒤를
    버리면 `'https://x'` 가 든 줄이 통째로 잘려 나가고, **없음을 확인하는
    시험이 그때 조용히 통과한다** — 코드가 사라졌으니 당연히 없다.

    정규식까지 따라가는 이유는 `/[&<>"]/g` 처럼 **정규식 안에 따옴표가 든**
    자리가 실제로 있기 때문이다. 그것을 문자열 시작으로 잘못 읽으면 그 뒤가
    통째로 문자열이 되어 파일의 절반이 사라진다.

    정규식인지 나눗셈인지는 앞의 글자로 가른다 — 자바스크립트를 제대로
    해석하는 것이 아니라, **이 저장소의 코드에서 틀리지 않을 만큼**이다.
    """
    # `/` 앞에 이런 글자가 오면 정규식의 시작이다 (값이 올 자리가 아니므로)
    before_regex = set("(,=:[!&|?{};+-*%~^<>") | {"\n", "\r"}
    out, i, n = [], 0, len(js)
    prev = ""                       # 바로 앞의 뜻있는 글자
    while i < n:
        ch = js[i]

        if ch in "\"'`":           # ── 문자열
            quote, j = ch, i + 1
            out.append(ch)
            while j < n:
                out.append(js[j])
                if js[j] == "\\" and j + 1 < n:
                    out.append(js[j + 1])
                    j += 2
                    continue
                if js[j] == quote:
                    j += 1
                    break
                j += 1
            i, prev = j, quote
            continue

        if js.startswith("//", i):                # ── 줄 주석
            j = js.find("\n", i)
            i = n if j < 0 else j
            continue

        if js.startswith("/*", i):                # ── 블록 주석
            j = js.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue

        if ch == "/" and (prev == "" or prev in before_regex):   # ── 정규식
            out.append(ch)
            j = i + 1
            while j < n and js[j] != "\n":
                out.append(js[j])
                if js[j] == "\\" and j + 1 < n:
                    out.append(js[j + 1])
                    j += 2
                    continue
                if js[j] == "/":
                    j += 1
                    break
                j += 1
            i, prev = j, "/"
            continue

        out.append(ch)
        if not ch.isspace():
            prev = ch
        i += 1
    return "".join(out)


def handler_names() -> set[str]:
    """`drawer.js` 가 화면에게 물어보는 이름 전부.

    `call('이름')` 과 `host.이름` 둘 다 본다 — 뒤엣것으로 읽는 것도
    화면이 넘겨야 하는 값이기는 마찬가지다.
    """
    js = read_js("drawer.js")
    # **두 따옴표를 다 받는다.** 홑따옴표만 보면 `call("onFoo")` 로 쓴 이름이
    # 안 잡히고, 그러면 그것을 빠뜨려도 이 시험이 통과한다 — 시험이 헛돈다.
    called = set(re.findall(r'''call\(\s*['"]([A-Za-z_]\w*)['"]''', js))
    direct = set(re.findall(r"\bhost\.([A-Za-z_]\w*)", js))
    return called | direct


def registered(name: str) -> tuple[set[str], dict[str, str]]:
    """(등록한 이름, 일부러 안 쓴다고 적어 둔 이름→이유)."""
    js = read_js(name)
    block = js[js.index("Drawer.init({"):]
    unused_at = block.find("__unused:")
    body = block[:unused_at] if unused_at >= 0 else block
    keys = set(re.findall(r"^  ([A-Za-z_]\w*):", body, re.M))
    keys |= set(re.findall(r"^  ([A-Za-z_]\w*),", body, re.M))   # 줄임 표기

    excuses: dict[str, str] = {}
    if unused_at >= 0:
        tail = block[unused_at:]
        tail = tail[: tail.index("},")]
        for key, why in re.findall(r"^    ([A-Za-z_]\w*):\s*(.+)$", tail, re.M):
            excuses[key] = why.strip().strip("',+ ")
    return keys - {"__unused"}, excuses


# ── 4 ─────────────────────────────────────────────────────────────────


def test_r04_모든_핸들러가_등록됐거나_이유와_함께_적혀_있다():
    """**빠뜨린 것과 일부러 안 쓴 것을 가른다.**

    `call()` 은 없는 핸들러를 조용히 건너뛴다. 그래서 화면만 봐서는 둘이
    똑같이 생겼고, 실제로 `onDates` 를 빠뜨려 달력이 옛 날짜를 말했다.
    """
    names = handler_names()
    assert names, "drawer.js 에서 핸들러 이름을 하나도 못 찾았다 — 시험이 헛돈다"
    # 빠뜨리기 쉬운 것들이 실제로 목록에 들어 있는지 (시험이 헛돌지 않는지)
    for must in ("onDates", "onStatus", "onDepartment", "link", "meta"):
        assert must in names, f"{must} 를 못 찾았다"

    gaps = []
    for screen in ("board.js", "calendar.js"):
        keys, excuses = registered(screen)
        for name in sorted(names):
            if name in keys:
                continue
            if name in excuses and len(excuses[name]) > 10:
                continue                      # 이유와 함께 적혀 있으면 됐다
            gaps.append(f"{screen}: {name}"
                        + (" (이유가 너무 짧다)" if name in excuses else ""))
    assert gaps == [], (
        "등록도 안 했고 '일부러 안 씀' 목록에도 없다 — "
        f"빠뜨린 것인지 알 수 없다: {gaps}")


def test_r04b_안_쓰는_이유가_저마다_다르다():
    """복사해 붙인 이유는 이유가 아니다. 같은 문장이 여러 번이면 생각을
    안 한 것이므로, 그 목록은 다음 사람에게 아무 도움이 안 된다."""
    for screen in ("board.js", "calendar.js"):
        _, excuses = registered(screen)
        whys = list(excuses.values())
        assert len(set(whys)) == len(whys), f"{screen} 의 이유가 겹친다: {whys}"


# ── 5 ─────────────────────────────────────────────────────────────────


def test_r05_onDepartment_는_true_규약이다():
    """`undefined` 로 갈랐더니, 핸들러가 있어도 반환값을 빠뜨리면 핸들러가
    돈 **뒤에** 페이지가 통째로 새로고침됐다 — 두 번 일하고 화면도 잃는다."""
    js = read_js("drawer.js")
    assert "call('onDepartment', d.run_id) !== true" in js
    assert "=== undefined) location.reload()" not in js


# ── 1 ~ 3 ─────────────────────────────────────────────────────────────


def test_r01_달력이_마감일_변경을_받는다(admin_client, cal_data):
    """수용기준 1 — 점의 자리를 정하는 것은 마감일이다 (4-13).

    패널에서 기간을 고쳤는데 점이 옛 칸에 그대로 있으면, 한 화면이 서로
    다른 날짜를 말한다.
    """
    js = read_js("calendar.js")
    keys, _ = registered("calendar.js")
    assert "onDates" in keys, "달력이 onDates 를 등록하지 않았다"
    assert "applyDates" in js

    # 칸이 자기 날짜를 말해야 점을 옮길 수 있다
    page = admin_client.get("/calendar?scope=all").text
    assert 'class="cal-cell' in page and "data-date=" in page
    assert 'data-per-day="' in page
    # `data-today` 는 뺐다 — 화면이 날짜를 견주지 않으므로 필요 없다
    assert 'data-today="' not in page

    # 서버가 새 날짜를 돌려준다 — 화면은 그걸 받아 점을 옮긴다
    run_id = cal_data["runs"]["오늘 업무"]
    res = admin_client.post(f"/board/task/{run_id}/dates",
                            json={"start": "2026-08-03", "end": "2026-08-07"})
    assert res.status_code == 200
    assert res.json()["end"] == "2026-08-07"


def test_r02_이_달_밖으로_나가면_화면이_말한다(admin_client, cal_data):
    """수용기준 2 — **조용히 사라지면 "지워진 건가" 로 읽힌다.**

    4-13 에서 날짜 없는 업무를 조용히 빼지 않기로 한 것과 같은 자리다.
    """
    page = admin_client.get("/calendar?scope=all").text
    assert 'id="calnote"' in page, "말할 자리가 없다"

    js = read_js("calendar.js")
    assert "이 달에는 보이지 않습니다" in js
    assert "그 달로 넘겨서 보세요" in js
    # 이 달 안이면 옮기고, 밖이면 말한다 — 두 갈래가 다 있어야 한다
    assert '.cal-cell[data-date=' in js
    assert "placeInGrid" in js and "placeInWeekList" in js


def test_r03_기간을_바꿔도_다시_불러오지_않는다():
    """수용기준 3 — 보던 달·범위 칩·`미완료만` 을 잃으면 안 된다 (4-13)."""
    js = read_js("calendar.js")
    assert "location.reload" not in js
    assert "location.href" not in js
    # 숫자도 함께 맞춘다 — 외 N건 · 날짜 없는 업무 N건 · 위쪽 건수
    assert "recount" in js
    assert "cal-more" in js and "calundated" in js and "calcount" in js


def test_r03b_숫자를_더하지_않고_세어서_다시_적는다():
    """더하고 빼면 한 번 어긋난 뒤로 영영 어긋난다."""
    js = read_js("calendar.js")
    block = js[js.index("function recount()"):]
    block = block[: block.index("\n}")]
    assert "querySelectorAll" in block
    assert "++" not in block and "--" not in block, "세지 않고 더하고 있다"


# ── 12 ────────────────────────────────────────────────────────────────


def test_r12_calbar_가_없어도_죽지_않는다():
    """이 파일은 패널이 있는 화면이면 어디서든 실릴 수 있다. 그때 `.calbar`
    가 없다고 상태 변경이 통째로 멈추면 안 된다."""
    js = read_js("calendar.js")
    for guarded in ("bar?.dataset.onlyOpen", "bar?.dataset.perDay"):
        assert guarded in js, f"{guarded} 가 ?. 로 막혀 있지 않다"
    # 옛 방식(막지 않은 접근)이 남아 있지 않은지
    assert "document.querySelector('.calbar').dataset" not in js


# ════════════════════════════════════════════════════════════════════
#  점이 날짜를 따라갈 때 생긴 두 가지 (수용기준 1~3 · 5~8)
# ════════════════════════════════════════════════════════════════════
#
# **기한 초과를 화면에서 다시 계산하고 있었다.** 4-13 은 점의 색·상태·기한
# 초과가 보드의 `bar_style`·`overdue_of` 를 그대로 쓴다고 못박았는데 두 벌이
# 됐고, 이미 어긋나 있었다 — `applyStatus` 는 인라인 배경을 다시 칠하는데
# `applyDates` 는 클래스만 건드려서 **붉은 점을 미래로 옮겨도 붉게 남았다.**


def _paint_run(admin_client, run_id, start, end):
    res = admin_client.post(f"/board/task/{run_id}/dates",
                            json={"start": start, "end": end})
    assert res.status_code == 200, res.text
    return res.json()


# ── 1 · 2. 서버가 색을 함께 돌려준다 ─────────────────────────────────
#
# **브라우저로만 보면 착각한다.** 과거끼리 옮겨 보고 "안 붉어졌다" 며
# 통과로 읽을 수 있다. 응답에 든 색으로 본다.


def test_r2_01_과거에서_미래로_옮기면_더_이상_붉지_않다(admin_client, cal_data):
    run_id = cal_data["runs"]["오늘 업무"]
    past = dt.date.today() - dt.timedelta(days=10)
    future = dt.date.today() + dt.timedelta(days=10)

    late = _paint_run(admin_client, run_id, past.isoformat(), past.isoformat())
    assert late["overdue"] is True
    assert late["overdue_days"] == 10

    fresh = _paint_run(admin_client, run_id, future.isoformat(), future.isoformat())
    assert fresh["overdue"] is False
    assert fresh["overdue_days"] == 0
    # **색까지 바뀐다.** 클래스만 바꾸면 인라인 스타일이 CSS 를 이겨 붉게 남는다.
    assert fresh["dot_background"] != late["dot_background"], "점 배경이 그대로다"
    assert fresh["dot_border"] != late["dot_border"], "점 테두리가 그대로다"


def test_r2_02_미래에서_과거로_옮기면_붉어진다(admin_client, cal_data):
    from app.domain import board as board_domain

    run_id = cal_data["runs"]["오늘 업무"]
    future = dt.date.today() + dt.timedelta(days=10)
    past = dt.date.today() - dt.timedelta(days=3)

    _paint_run(admin_client, run_id, future.isoformat(), future.isoformat())
    late = _paint_run(admin_client, run_id, past.isoformat(), past.isoformat())

    assert late["overdue"] is True
    # 붉은 것은 '지연' 의 색이다 — 저장된 상태가 아니라 날짜에서 나온다 (4-10)
    late_bg, late_border = board_domain.BAR_LATE
    assert late["dot_background"] == late_bg
    assert late["dot_border"] == late_border
    # 저장된 상태는 그대로다. 손으로 '지연' 을 누른 적이 없다.
    assert late["status"] != "지연"


def test_r2_02b_보드의_바와_달력의_점을_함께_준다(admin_client, cal_data):
    """둘은 규칙이 다르다 — 바는 저장된 상태대로, 점은 기한이 지나면 '지연'.
    그래서 한 값으로 합칠 수 없고, 그렇다고 화면마다 계산하게 두면 두 벌이 된다."""
    run_id = cal_data["runs"]["오늘 업무"]
    past = (dt.date.today() - dt.timedelta(days=5)).isoformat()
    paint = _paint_run(admin_client, run_id, past, past)

    for key in ("bar_background", "bar_border", "dot_background", "dot_border",
                "status", "overdue", "overdue_days", "color"):
        assert key in paint, f"{key} 가 없다"
    # **접두사 없는 쌍을 남기지 않는다.** 그쪽이 기본값처럼 보여서, 세 번째
    # 화면이 생겼을 때 사람이 따져 보지 않고 집는다 — 이번에 고친 버그가 그 모양이었다.
    assert "background" not in paint and "border" not in paint

    # 기한이 지난 '대기' 업무: 바는 대기 색, 점은 지연 색
    assert paint["status"] == "대기"
    assert paint["bar_background"] != paint["dot_background"], \
        "바와 점의 배경이 같으면 둘을 나눈 뜻이 없다"
    assert paint["bar_border"] != paint["dot_border"], \
        "바와 점의 테두리가 같으면 둘을 나눈 뜻이 없다"


def test_r2_02c_상태_변경도_같은_모양으로_돌려준다(admin_client, cal_data):
    """`/status` 와 `/dates` 가 같아야 화면이 한 가지 방법으로 칠한다."""
    run_id = cal_data["runs"]["오늘 업무"]
    dates = _paint_run(admin_client, run_id, "2026-08-03", "2026-08-07")
    status = admin_client.post(f"/board/task/{run_id}/status",
                               json={"status": "진행중"}).json()
    shared = {"status", "color", "overdue", "overdue_days",
              "bar_background", "bar_border", "dot_background", "dot_border"}
    assert shared <= set(dates), f"/dates 에 없는 것: {shared - set(dates)}"
    assert shared <= set(status), f"/status 에 없는 것: {shared - set(status)}"


def test_r2_02d_생김새를_만드는_곳이_하나다():
    """`board.paint_of` 하나가 만들고, 달력의 `dot_of` 도 그것을 부른다."""
    board_src = (ROOT / "app" / "domain" / "board.py").read_text(encoding="utf-8")
    cal_src = (ROOT / "app" / "domain" / "calendar.py").read_text(encoding="utf-8")
    router_src = (ROOT / "app" / "routers" / "board.py").read_text(encoding="utf-8")

    assert "def paint_of(" in board_src
    assert "board_domain.paint_of(" in cal_src, "달력이 따로 칠하고 있다"
    assert "board_domain.bar_style(" not in cal_src, "달력에 두 번째 계산이 남아 있다"
    assert router_src.count("paint_of(") == 2, "/status 와 /dates 둘 다 써야 한다"
    assert "board_view.bar_style(" not in router_src

    # **보드 첫 렌더도 지나야 한다.** 여기서 bar_style 을 직접 부르면
    # paint_of 는 API 경로만 쓰는 껍데기가 되고 첫 렌더가 세 번째 길로 남는다.
    body = board_src[board_src.index("def build("):]
    assert "bar_style(" not in body, "보드 첫 렌더가 아직 bar_style 을 직접 부른다"
    assert "paint_of(run, today, ghost=ghost)" in body
    # 정의 자체를 빼면 남는 것은 paint_of 안의 두 번뿐이다
    assert board_src.count("bar_style(") == 3, "bar_style 을 부르는 곳이 늘었다"


# ── 3. 화면이 날짜를 견주지 않는다 ────────────────────────────────────


def test_r2_03_달력_코드에_날짜_비교가_없다():
    js = code_only(read_js("calendar.js"))
    assert "todayIso" not in js, "오늘 날짜를 들고 있다"
    assert "< today" not in js and "dataset.today" not in js, "날짜를 견주고 있다"
    # 서버가 준 것을 그대로 쓴다
    assert "p.overdue" in js and "p.dot_background" in js
    # 칠하는 곳이 하나다. 그리고 그것을 감싼 `reload()` 가 **점이 들고 있는
    # 것 전부**(색·기간·title)를 한 자리에서 갈아 끼운다 — 옮길 때 하나라도
    # 빠뜨리면 옛 값이 따라온다. 실제로 세 번 그랬다.
    assert js.count("function paint(") == 1
    assert js.count("function reload(") == 1
    for caller in ("applyStatus", "applyDates"):
        block = js[js.index(f"function {caller}("):]
        block = block[: block.index("\n}")]
        assert "reload(" in block, f"{caller} 가 reload 를 안 쓴다"

    page_src = (ROOT / "app" / "templates" / "calendar.html").read_text(encoding="utf-8")
    assert "data-today" not in page_src, "안 쓰는 값을 아직 실어 보낸다"


# ── 5 · 6 · 7. 내보냈다가 되돌리기 ───────────────────────────────────


def test_r2_05_이_달_밖으로_내보낸_점을_지우지_않는다():
    """지워 버리면 `if (!existing.length) return;` 에서 그냥 나가 **점이
    안 돌아오고 낡은 안내문이 그대로 남는다** — 패널과 안내문이 서로 다른
    날짜를 말한다."""
    js = read_js("calendar.js")
    assert "function stash(" in js
    assert "calstash" in js

    block = js[js.index("function applyDates("):]
    block = block[: block.index("\n}")]
    assert "stash(model)" in block, "이 달 밖일 때 치워 두지 않는다"

    # 치워 두는 자리는 화면에 그리지 않는다
    stash = js[js.index("function stash("):]
    stash = stash[: stash.index("\n}")]
    assert "hidden = true" in stash


def test_r2_06_되돌아오면_그_업무의_안내만_지운다():
    """다른 업무의 안내가 떠 있었다면 건드리지 않는다 — 남의 말을 대신
    지우면 그쪽이 조용해진다."""
    js = read_js("calendar.js")
    block = js[js.index("function applyDates("):]
    block = block[: block.index("\n}")]
    assert "note.dataset.run === String(runId)" in block

    say = js[js.index("function say("):]
    say = say[: say.index("\n}")]
    assert "note.dataset.run" in say, "누구에 대한 말인지 기억하지 않는다"


def test_r2_07_치워_둔_것은_숫자에_들어가지_않는다():
    """화면에 없는 것이 숫자에 들어가면 `외 N건` 과 위쪽 건수가 눈에 보이는
    것과 어긋난다."""
    js = code_only(read_js("calendar.js"))
    block = js[js.index("function recount()"):]
    block = block[: block.index("\n}\n")]
    # 위쪽 건수는 격자에 실제로 놓인 점만 센다 (치워 둔 자리는 body 아래에 있다)
    assert ".cal-cell:not(.out) .cal-dot" in block
    assert "calstash" not in block, "치워 둔 자리를 세고 있다"
    # 여전히 세어서 다시 적는다
    assert "++" not in block and "--" not in block


# ── 8. 시험이 헛돌지 않는다 ──────────────────────────────────────────


def test_r2_08_두_따옴표로_쓴_핸들러도_잡는다():
    """`call("onFoo")` 로 쓰면 이름이 안 잡히고, 그러면 빠뜨려도 통과한다."""
    import re

    js = '''call("onDouble") call('onSingle') call( "onSpaced" )'''
    found = set(re.findall(r"""call\(\s*['"]([A-Za-z_]\w*)['"]""", js))
    assert found == {"onDouble", "onSingle", "onSpaced"}

    # 실제 시험이 그 정규식을 쓰는지
    src = (ROOT / "tests" / "test_calendar.py").read_text(encoding="utf-8")
    block = src[src.index("def handler_names("):]
    block = block[: block.index("\n\n\n")]
    assert "['\"]" in block, "홑따옴표만 보고 있다"
    assert len(handler_names()) >= 13


# ── 9. README ────────────────────────────────────────────────────────


def test_r2_09_README_가_지금_상태와_맞는다():
    """저장소가 공개라 처음 여는 사람이 만나는 문서다."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    # 없어진 것을 아직 말하고 있지 않은가
    for stale in ("Phase 1 완료", "pytest 163", "DCB_SMS_PROVIDER", "DCB_DEV_MODE",
                  "인증번호", "SMS 벤더", "Solapi"):
        assert stale not in text, f"낡은 내용이 남아 있다: {stale}"

    # 지금 있는 화면을 말하는가
    for path in ("/board", "/calendar", "/live", "/library", "/admin/users"):
        assert path in text, f"{path} 가 없다"

    # 로그인은 초대 링크다
    assert "초대 링크" in text and "create_admin.py" in text

    # 설계는 CLAUDE.md 를 가리키는가 (두 곳에 같은 것을 적지 않는다)
    assert "CLAUDE.md" in text
    assert "app/config.py" in text, "환경변수는 config.py 를 가리켜야 한다"

    # 환경변수 표를 남겼다면 실제로 있는 것만 적혀 있는가
    import re

    from app import config

    real = {"DCB_" + n for n in dir(config)} | {
        "DCB_BASE_URL", "DCB_DATABASE_URL", "DCB_DATA_DIR", "DCB_SECRET_KEY",
        "DCB_PUSH_CONTACT", "DCB_RISK_SCAN_INTERVAL", "DCB_MAX_ASSET_MB",
        "DCB_MAX_ATTACHMENT_MB", "DCB_DISK_FLOOR_MB", "DCB_DISK_WARN_MB",
        "DCB_TUNNEL_MAX_MB", "DCB_DEV",
    }
    for name in set(re.findall(r"DCB_[A-Z_]+", text)):
        assert name in real, f"README 가 없는 환경변수를 적고 있다: {name}"


# ── 6. code_only 가 문자열 안의 `//` 를 자르지 않는다 ────────────────


def test_s_06_code_only_가_문자열_속_주소를_살린다():
    """줄에서 `//` 만 찾아 뒤를 버리면 `'https://x'` 가 든 줄이 통째로 잘려
    나가고, **없음을 확인하는 시험이 그때 조용히 통과한다** — 코드가
    사라졌으니 당연히 없다.

    고치기 전에는 실제로 잘랐다:
        "const u = 'https://x'; // 설명"  →  "const u = 'https:"
    """
    assert code_only("const u = 'https://x'; // 설명").strip() \
        == "const u = 'https://x';"
    assert "https://" in code_only('const M = "주소는 https:// 로 시작"; // 문구')
    # 정규식 리터럴도 살아야 한다 (drawer.js 의 URL_RE)
    kept = code_only(r"const RE = /^https?:\/\/[^\s]+$/i;  // 주소인가")
    assert r"https?:\/\/" in kept
    # 템플릿 문자열 안도 마찬가지
    assert "//y" in code_only("const t = `${x}//y`; // 진짜 주석")
    # 그러면서 진짜 주석은 여전히 걷어낸다
    assert "진짜 주석" not in code_only("const t = `${x}//y`; // 진짜 주석")
    assert "속" not in code_only("a(); /* 여러\n줄 속 */ b();")


def test_s_06b_실제_파일의_주소가_살아남는다():
    """`drawer.js` 에 정말로 그런 줄이 있다 — 시험이 헛돌지 않는지 본다."""
    src = read_js("drawer.js")
    assert "https://" in src, "전제가 바뀌었다 — 이 시험을 다시 보라"
    kept = code_only(src)
    assert "https:// 로 시작하는 주소를 넣어주세요" in kept, \
        "안내 문구가 통째로 잘렸다"
    assert "URL_RE" in kept


# ── 6(a). 세 번 옮겨도 점이 늘어나지 않는다 ─────────────────────────


def test_s_09_옮겨도_점이_늘어나지_않는다():
    """`stash` 가 안 쌓이는 이유는 **옮길 때 그 업무의 복사본을 먼저 전부
    걷어낸다** 한 줄에 걸려 있다. 그 줄이 사라지면 밖으로 내보낼 때마다
    복사본이 하나씩 쌓인다.
    """
    js = code_only(read_js("calendar.js"))
    block = js[js.index("function applyDates("):]
    block = block[: block.index("\n}")]

    # 먼저 전부 걷어내고, 그 다음에 다시 놓는다
    assert "existing.forEach(el => el.remove());" in block
    assert block.index("existing.forEach(el => el.remove());") \
        < block.index("placeInGrid("), "걷어내기가 다시 놓기보다 뒤에 있다"
    assert block.index("existing.forEach(el => el.remove());") \
        < block.index("stash(model)"), "걷어내기가 치워 두기보다 뒤에 있다"

    # 격자와 주 목록에 각각 하나씩만 놓는다 (그래서 최대 2)
    assert block.count("placeInGrid(") == 1
    assert block.count("placeInWeekList(") == 1
    assert block.count("stash(") == 1


def test_s_09b_치워_둘_때는_하나만_남긴다():
    """밖 → 안 → 밖 으로 세 번 옮겨도 `dots(runId)` 가 2를 넘지 않아야 한다.
    격자 1 + 주 목록 1 이 최대이고, 치워 둘 때는 1 이다."""
    js = code_only(read_js("calendar.js"))
    block = js[js.index("function applyDates("):]
    block = block[: block.index("\n}")]
    # 치워 두는 것은 model 하나뿐 — 주 목록 복사본까지 치우지 않는다
    assert "stash(model)" in block
    assert "stash(model.cloneNode" not in block
    # 다시 놓을 때만 복사본을 만든다
    assert "placeInWeekList(iso, model.cloneNode(true))" in block


# ── 6(c). 상태를 두 번 넘기지 않는다 ────────────────────────────────


def test_s_06c_onStatus_는_view_하나만_받는다():
    """`view.status` 가 상태를 들고 온다. 인자로 또 받으면 같은 값이 두 자리에
    있게 되고, 둘이 어긋났을 때 어느 쪽이 맞는지 알 수 없다."""
    drawer = code_only(read_js("drawer.js"))
    assert "call('onStatus', runId, view)" in drawer
    assert "call('onStatus', runId, status, view)" not in drawer

    for name in ("board.js", "calendar.js"):
        js = code_only(read_js(name))
        assert "function applyStatus(runId, view)" in js, f"{name} 의 서명이 다르다"


# ── 6(b). 아무도 안 읽는 값을 보내지 않는다 ─────────────────────────


def test_s_06b2_담당팀_응답에_reload_가_없다(admin_client, cal_data):
    body = (ROOT / "app" / "routers" / "board.py").read_text(encoding="utf-8")
    assert '"reload": True' not in body
    for name in ("board.js", "calendar.js", "drawer.js"):
        assert ".reload" not in code_only(read_js(name)).replace("location.reload", "")


# ── 7. 413 을 사람 말로 옮긴다 ───────────────────────────────────────


def test_s_07_413_이면_사람이_읽을_수_있는_이유가_뜬다():
    """**413 은 우리 응답이 아니다.** 파일이 서버에 닿기 전에 Cloudflare 가
    앞에서 끊은 것이라 `detail` 이 없다 — 그대로 두면 몇 분을 기다린 끝에
    "올리지 못했습니다." 만 보고 이유를 모른 채 끝난다."""
    js = code_only(read_js("drawer.js"))
    body = js[js.index("function putFile("):]
    body = body[: body.index("\n}")]

    assert "xhr.status === 413" in body, "413 을 따로 알아보지 않는다"
    # 우리 detail 이 없으므로 문구를 직접 만든다
    assert "올릴 수 없습니다" in body
    assert "링크로 붙이시거나" in body
    # 숫자를 코드에 박지 않고 상한에서 끌어온다
    assert "tunnel_max_label" in body
    # 413 갈래가 일반 갈래보다 먼저다 — 뒤에 있으면 절대 닿지 않는다
    assert body.index("413") < body.index("올리지 못했습니다")


def test_s_07b_내려받기에는_제한이_없다고_적는다():
    """올리기와 내려받기는 제한이 다르다. 이 한 줄이 없으면 "큰 파일은 아예
    못 쓴다" 로 읽혀서, 집 안에서 올려 두면 되는 길을 아무도 안 쓴다."""
    js = read_js("drawer.js")
    assert "내려받기에는" in js and "제한이 없" in js


# ── 8. 문서의 근거가 크기로 바뀌었다 ────────────────────────────────


def test_s_08_문서가_터널_한계를_크기로_적는다():
    """"30초 · 2MB/s · 60MB 언저리" 로 두면 다음 사람이 상한을 60 으로 내린다.
    그 측정은 로그인하지 않은 요청이라 서버가 먼저 답했을 수 있었다."""
    for path in ("CLAUDE.md", "app/config.py"):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "100MB" in text, f"{path} 에 크기 근거가 없다"
        assert "413" in text, f"{path} 에 413 이 없다"

    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "60MB 언저리가" not in claude and "60MB 언저리**가" not in claude, \
        "낡은 근거가 아직 결론처럼 적혀 있다"
    assert "내려받기에는 이 제한이 없습니다" in claude


def retreat_of_cal(db):
    """이 파일의 시험이 쓰는 회차 하나."""
    return db.scalars(select(models.Retreat)).first()


# ════════════════════════════════════════════════════════════════════
#  사이드바 묶음 · 기간 비추기 (수용기준 1~10)
# ════════════════════════════════════════════════════════════════════


# ── 1 · 2 · 3. 사이드바 ──────────────────────────────────────────────


def test_t_01_준비_단계_묶음에_보드와_달력이_있다(admin_client, cal_data):
    """보드와 달력은 **같은 데이터를 다른 축으로 보는 화면**이라 한 묶음이다
    (4-13). 나란히 놓으면 별개 기능으로 읽힌다."""
    page = admin_client.get("/calendar?scope=all").text

    label = '<div class="navgroup">준비 단계</div>'
    assert label in page, "묶음이 없다"
    after = page[page.index(label):]
    # 바로 아래에 둘이 **한 단계 들어가** 붙어 있다
    upto = after[: after.index('class="navlabel"')]
    assert 'class="sub" href="/board"' in upto
    assert 'class="sub" href="/calendar"' in upto
    assert ">보드" in upto and ">달력" in upto


def test_t_02_준비_단계가_회색_묶음_제목과_구별된다(admin_client, cal_data):
    """`준비 단계` 는 `수련회 진행` 과 **같은 수준의 항목**이다.
    `실무`·`회차 준비` 의 회색 묶음 제목과 달라야 한다."""
    page = admin_client.get("/calendar?scope=all").text

    # 회색 묶음 제목은 그대로 둘이다
    for name in ("실무", "회차 준비"):
        assert f'<div class="navlabel">{name}</div>' in page
    assert '<div class="navlabel">준비 단계</div>' not in page, "아직 회색 묶음 제목이다"

    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    import re as _r

    def decl(sel):
        body = _r.sub(r"/\*.*?\*/", "", css, flags=_r.S)
        at = body.index(sel + "{")
        return body[at + len(sel) + 1 : body.index("}", at)]

    item = decl(".sidenav nav a")
    group = decl(".sidenav .navgroup")
    label = decl(".sidenav .navlabel")

    # 항목과 같은 글자 크기·색
    assert "font-size:13.5px" in item and "font-size:13.5px" in group
    assert "var(--ink-2)" in item and "var(--ink-2)" in group
    # 회색 묶음 제목은 더 작고 더 흐리다 — 구별된다
    assert "font-size:11px" in label and "var(--ink-3)" in label
    # 하위는 한 단계 들어간다
    assert "padding-left" in decl(".sidenav nav a.sub")


def test_t_03_보고_있는_화면에_표시가_붙는다(admin_client, cal_data):
    import re

    def current(page):
        return set(re.findall(r'href="([^"]+)"[^>]*aria-current="page"', page))

    assert current(admin_client.get("/calendar?scope=all").text) == {"/calendar"}
    assert current(admin_client.get("/board").text) == {"/board"}
    # 묶음 자체에는 붙지 않는다 — 링크가 아니다
    page = admin_client.get("/calendar?scope=all").text
    assert '<div class="navgroup">준비 단계</div>' in page
    assert "navgroup\" aria-current" not in page
    # 표시는 **하위 항목**에 붙는다
    assert 'class="sub" href="/calendar" aria-current="page"' in page


# ── 4 · 8. 점이 기간을 들고 간다 ────────────────────────────────────


def test_t_04_점이_자기_기간을_들고_간다(admin_client, cal_data):
    """**구조가 실어 보낸다.** 화면이 계산하거나 서버에 다시 묻지 않는다."""
    page = admin_client.get("/calendar?scope=all").text
    assert "data-start=" in page and "data-end=" in page

    with app_session() as db:
        view = cal_domain.build(db, retreat_of_cal(db), today=dt.date(2026, 8, 10),
                                scope="all")
    seen = [d for week in view["weeks"] for cell in week
            for d in (cell["dots"] + cell["more"])]
    assert seen, "점이 하나도 없다 — 시험이 헛돈다"
    for dot in seen:
        assert dot["start"] and dot["end"], "점이 기간을 안 들고 있다"
        assert dot["start"] <= dot["end"]

    js = code_only(read_js("calendar.js"))
    assert "dataset.start" in js and "dataset.end" in js
    assert "fetch(" not in js.split("function showSpan(")[1].split("\n}")[0], \
        "비출 때 서버에 다시 묻고 있다"


def test_t_08_시작일이_없거나_하루짜리여도_죽지_않는다(admin_client, cal_data):
    """마감일만 있는 업무는 그 날 하루로 본다."""
    with app_session() as db:
        run = db.scalars(select(models.TaskRun)).first()
        run.start_date = None
        run.end_date = dt.date(2026, 8, 12)
        db.commit()
        one = cal_domain.dot_of(run, today=dt.date(2026, 8, 10))
        assert one["start"] == one["end"] == "2026-08-12"

        run.start_date = run.end_date = dt.date(2026, 8, 12)
        db.commit()
        same = cal_domain.dot_of(run, today=dt.date(2026, 8, 10))
        assert same["start"] == same["end"] == "2026-08-12"

    assert admin_client.get("/calendar?scope=all").status_code == 200


def test_t_04b_기간을_말로도_적어_둔다(admin_client, cal_data):
    """달을 걸쳐 잘렸을 때 **정확한 날짜는 툴팁에 있다.**"""
    page = admin_client.get("/calendar?scope=all").text
    assert "· 기간 " in page and " → " in page


# ── 5 · 6 · 7 · 9 · 10. 비추기 ──────────────────────────────────────


def test_t_05_손을_떼면_사라진다():
    js = code_only(read_js("calendar.js"))
    assert "function clearSpan(" in js
    assert "mouseout" in js
    # 점 안에서 자식끼리 옮겨 다니는 것은 떠난 것이 아니다
    assert "dot.contains(e.relatedTarget)" in js


def test_t_06_오늘_테두리와_지연_점이_덮이지_않는다():
    """오늘 칸은 `inset box-shadow` 라 배경 위에 그려지고, 지연 점은 자기
    배경을 갖고 있다. 비침이 그 위를 덮으면 안 된다."""
    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    assert ".cal-cell.today{box-shadow:inset 0 0 0 2px var(--link)}" in css
    # 비침은 배경만 건드린다 — box-shadow 나 border 를 손대지 않는다.
    # **주석을 걷어내고 본다** — 이 저장소는 이유를 주석에 적으므로
    # "box-shadow 라 그대로 남는다" 는 설명이 그대로 걸린다.
    span = css[css.index(".cal-cell.inspan{"):]
    span = span[: span.index("/* 기간이 이 달을 넘어가면")]
    span = re.sub(r"/\*.*?\*/", "", span, flags=re.S)
    assert "box-shadow" not in span and "border-color" not in span


def test_t_07_달을_걸치면_이_달_안쪽만_칠한다():
    js = code_only(read_js("calendar.js"))
    body = js[js.index("function showSpan("):]
    body = body[: body.index("\n}")]
    # 격자에 실제로 있는 칸만 고른다 — 없는 칸을 만들어 낼 수 없다
    assert ".cal-grid .cal-cell[data-date]" in body
    assert "from <= td.dataset.date && td.dataset.date <= to" in body
    # 잘린 끝은 각지게, 안에서 끝나면 둥글게
    assert "span-head" in body and "span-tail" in body
    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    assert ".cal-cell.inspan.span-head{border-top-left-radius" in css
    assert ".cal-cell.inspan{border-radius:0}" in css


def test_t_09_외_N건_안의_점에서도_동작한다():
    """문서에 한 번만 걸어 두면 나중에 펼쳐지는 점도 그대로 잡힌다."""
    js = code_only(read_js("calendar.js"))
    assert "document.addEventListener('mouseover'" in js
    assert ".cal-dot[data-start]" in js
    # 점마다 따로 걸면 `외 N건` 안에서 나중에 옮겨 놓은 점이 빠진다
    assert "querySelectorAll('.cal-dot').forEach(d => d.addEventListener" not in js


def test_t_10_좁은_화면에서는_비추지_않는다():
    """주 목록에는 날짜 격자가 없고 마우스도 없다 — 탭으로 흉내 내면
    점을 누르려다 띠가 뜬다 (4-13)."""
    js = code_only(read_js("calendar.js"))
    assert "matchMedia('(min-width: 821px)')" in js
    body = js[js.index("function showSpan("):]
    body = body[: body.index("\n}")]
    assert "넓은화면()" in body

    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    narrow = css[css.index("@media (max-width:820px){", css.index(".calweeks")):]
    assert ".cal-cell.inspan{background:none}" in narrow[:2000]


def test_t_04c_비침은_무채색이다():
    """**부서 색으로 면을 채우지 않는다** (4-0). 화면이 색으로 덮이면 정작
    눈에 띄어야 할 선택 테두리와 지연 배지가 묻힌다."""
    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    span = css[css.index(".cal-cell.inspan{"):]
    span = span[: span.index("/* 오늘 칸의")]
    assert "var(--hover)" in span, "4-0 의 호버 색을 쓰지 않는다"
    # 부서 색이 끼어들지 않았는지
    assert "--team" not in span and "owner" not in span
    for bad in ("#", "rgb("):
        assert bad not in span, f"새 색을 만들었다: {bad}"


# ════════════════════════════════════════════════════════════════════
#  캐시 번호 · 전환 · 1일 표시 · 옮긴 뒤의 값 (수용기준 1~2 · 7~8 · 9~16 · 18)
# ════════════════════════════════════════════════════════════════════
#
# **기간 비침이 배포됐는데 화면에 안 나타났다.** 원점은 Cache-Control 을
# 보내지 않지만 Cloudflare 가 `/static` 에 `max-age=14400` 을 붙인다. 그동안
# 브라우저는 서버에 물어보지도 않고 갖고 있던 파일을 쓴다. HTML 은 캐시되지
# 않으므로(`cf-cache-status: DYNAMIC`) **새 화면 + 옛 코드**가 된다.
# `calendar.js?v=1` 이 여러 라운드 동안 1 이었던 것이 그 위에 겹쳤다.


# ── 1 · 2. 정적 파일 주소가 저절로 바뀐다 ───────────────────────────


def test_u_01_정적_주소가_내용에서_나온다():
    """번호를 손으로 올리면 **또 빠뜨린다.** 실제로 달력 쪽만 계속 1 이었다."""
    from app.templating import static

    css = ROOT / "app" / "static" / "css" / "retreat.css"
    first = static("css/retreat.css")
    assert first.startswith("/static/css/retreat.css?v=")
    stamp = first.split("=", 1)[1]
    assert len(stamp) >= 8 and stamp != "1", "번호가 내용에서 나오지 않는다"

    # 같은 내용이면 같은 주소 — 안 바뀐 파일을 쓸데없이 다시 받지 않는다
    assert static("css/retreat.css") == first

    # 내용이 바뀌면 주소가 바뀐다
    import app.templating as t

    keep = css.read_bytes()
    try:
        css.write_bytes(keep + b"\n/* temp */\n")
        t._static_stamps.clear()          # 운영은 켤 때 한 번 잰다 (11-2)
        assert static("css/retreat.css") != first, "내용이 바뀌었는데 주소가 그대로다"
    finally:
        css.write_bytes(keep)
        t._static_stamps.clear()

    # 없는 파일이라도 화면을 죽이지 않는다
    assert static("js/없는파일.js").endswith("?v=0")


def test_u_02_화면_어디에도_손으로_박은_번호가_없다(admin_client, cal_data):
    """한 곳이라도 남으면 그 파일이 또 낡는다."""
    import re

    for tpl in sorted((ROOT / "app" / "templates").rglob("*.html")):
        text = tpl.read_text(encoding="utf-8")
        stuck = re.findall(r'/static/[^"\']*\?v=\d', text)
        assert stuck == [], f"{tpl.name} 에 손으로 박은 번호가 남았다: {stuck}"

    # 달력 화면의 스크립트에도 걸려 있다 — 이번에 문제가 된 자리다
    page = admin_client.get("/calendar?scope=all").text
    for asset in ("js/calendar.js", "js/drawer.js", "css/retreat.css"):
        found = re.search(r'/static/' + re.escape(asset) + r'\?v=([0-9a-f]{8})', page)
        assert found, f"{asset} 에 내용 번호가 안 붙었다"


# ── 7 · 8. 전환 ─────────────────────────────────────────────────────


def test_u_07_화면을_옮길_때_밀려_들어오지_않는다(admin_client, cal_data):
    """sidenav.js 가 **그린 뒤에** sidepin 을 붙여서, 화면을 옮길 때마다
    사이드바와 본문이 260px 밀려 들어왔다. 매일 여러 번 오가는 자리다."""
    page = admin_client.get("/calendar?scope=all").text
    # 첫 그림 전에 정한다
    assert 'class="booting' in page
    assert "localStorage.getItem('dcb.sidepin')" in page
    assert page.index("localStorage.getItem('dcb.sidepin')") < page.index("</body>")

    js = (ROOT / "app" / "static" / "js" / "sidenav.js").read_text(encoding="utf-8")
    assert "if (saved === \"1\") setPinned(true);" not in js, "아직 그린 뒤에 붙인다"

    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    assert "body.booting" in css and "transition:none!important" in css
    # 대신 아주 짧은 불투명도만 — 밀거나 키우지 않는다
    assert "@keyframes dcb-in{from{opacity:0}to{opacity:1}}" in css
    assert "animation:dcb-in .12s" in css
    for moving in ("translate", "scale"):
        assert moving not in css[css.index("@keyframes dcb-in"):css.index("@keyframes dcb-in") + 200]


def test_u_08_움직임을_줄이라고_하면_전환이_없다():
    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    at = css.index("@media (prefers-reduced-motion:reduce)")
    block = css[at : css.index("}", css.index("}", at) + 1) + 1]
    assert "transition:none!important" in block
    assert "animation:none!important" in block, "애니메이션은 안 꺼진다"


# ── 9 · 10. 1일에 달을 함께 ─────────────────────────────────────────


def test_u_09_격자의_1일에_달이_함께_나온다(admin_client, cal_data):
    """`1` 만 있으면 어느 달의 1일인지 알기 어렵다. 앞뒤 달 칸이 섞여 있어
    더 그렇다 — **옆 달 칸이 오히려 더 헷갈리는 자리다.**"""
    with app_session() as db:
        view = cal_domain.build(db, retreat_of_cal(db), today=dt.date(2026, 8, 10),
                                scope="all", month="2026-08-01")
    cells = [c for week in view["weeks"] for c in week]
    firsts = [c for c in cells if c["day"] == 1]
    assert firsts, "1일이 없다 — 시험이 헛돈다"
    for c in firsts:
        assert "/" in c["day_label"], f"{c['date']} 의 1일에 달이 없다"
    # 옆 달 칸의 1일도 같다
    outs = [c for c in firsts if not c["in_month"]]
    assert outs, "이 달 격자에 옆 달 1일이 없다"
    for c in outs:
        assert c["day_label"] == f"{int(c['date'][5:7])}/1"
    # 나머지 날은 숫자만
    for c in cells:
        if c["day"] != 1:
            assert c["day_label"] == str(c["day"])

    page = admin_client.get("/calendar?scope=all&month=2026-08-01").text
    assert ">9/1<" in page or ">8/1<" in page


def test_u_10_주_목록의_1일도_같다(admin_client, cal_data):
    page = admin_client.get("/calendar?scope=all&month=2026-08-01").text
    view = (ROOT / "app" / "templates" / "calendar.html").read_text(encoding="utf-8")
    assert "{{ cell.day_label }}<i>" in view, "주 목록이 아직 숫자만 쓴다"
    assert "{{ cell.day_label }}</span>" in view, "격자가 아직 숫자만 쓴다"


# ── 11~14. 옮긴 뒤의 값 ─────────────────────────────────────────────


def test_u_13_점이_들고_있는_것을_한_자리에서_갈아_끼운다():
    """**같은 모양으로 세 번 당했다** — 점은 옮겼는데 onDates 를 안 걸었고,
    걸었더니 색이 안 따라왔고, 그 다음엔 기간이 안 따라왔다."""
    js = code_only(read_js("calendar.js"))
    assert js.count("function reload(") == 1
    body = js[js.index("function reload("):]
    body = body[: body.index("\n}")]
    # 색·기간·title 이 한 자리에 있다
    assert "paint(dot, p)" in body
    assert "dataset.start" in body and "dataset.end" in body
    assert "retitle(dot, p)" in body


def test_u_11_옮기면_기간도_함께_바뀐다(admin_client, cal_data):
    """옮긴 뒤 마우스를 올리면 **새 기간**이 비쳐야 한다. 복제한 점이 옛
    data-start 를 물고 오면 옛 기간이 비친다."""
    run_id = cal_data["runs"]["오늘 업무"]
    saved = admin_client.post(f"/board/task/{run_id}/dates",
                              json={"start": "2026-08-03", "end": "2026-08-07"}).json()
    # 서버가 새 기간을 함께 돌려준다 — 화면이 그걸로 갈아 끼운다
    assert saved["start"] == "2026-08-03" and saved["end"] == "2026-08-07"

    js = code_only(read_js("calendar.js"))
    body = js[js.index("function applyDates("):]
    body = body[: body.index("\n}")]
    assert "reload(model, saved)" in body, "옮길 때 값을 갈아 끼우지 않는다"
    assert "paint(model, saved)" not in body, "색만 갈아 끼운다 — 기간이 남는다"


def test_u_12_옮기면_title_의_기간도_새_값이다():
    """`title` 은 이제 판단에 쓰인다 — 최근.md 가 "정확한 날짜는 툴팁에
    있다" 고 적은 그 툴팁이다. 옛 값이 남으면 그 문장이 거짓이 된다."""
    js = code_only(read_js("calendar.js"))
    assert "function retitle(" in js
    body = js[js.index("function retitle("):]
    body = body[: body.index("\n}")]
    assert "기간 ${p.start}" in body
    assert "dot.title =" in body

    # title 을 다시 만들 재료가 점에 실려 있다
    view = (ROOT / "app" / "templates" / "calendar.html").read_text(encoding="utf-8")
    assert "data-department=" in view and "data-assignee=" in view


def test_u_14_시험이_옮긴_뒤의_값을_본다():
    """옮기기 전만 보면 이 버그가 다시 지나간다."""
    src = (ROOT / "tests" / "test_calendar.py").read_text(encoding="utf-8")
    assert "def test_u_11_옮기면_기간도_함께_바뀐다" in src
    assert "reload(model, saved)" in src


# ── 15 · 16. 패널이 열리면 비침을 지운다 ────────────────────────────


def test_u_15_패널이_열리면_비침이_사라진다():
    """점을 클릭하면 마우스가 움직이지 않아 `mouseout` 이 뜨지 않는다."""
    js = code_only(read_js("calendar.js"))
    init = js[js.index("Drawer.init({"):]
    init = init[: init.index("});")]
    assert "onOpen: clearSpan" in init, "열릴 때 지우지 않는다"


def test_u_16_안_쓰는_목록과_주석이_지금_코드와_맞는다():
    """`__unused.onOpen` 의 이유가 지난 커밋에서 거짓이 됐다 —
    "패널이 열릴 때 달력이 따로 할 일이 없다"."""
    js = read_js("calendar.js")
    keys, excuses = registered("calendar.js")
    assert "onOpen" in keys, "등록했는데 목록에 남아 있으면 안 된다"
    assert "onOpen" not in excuses, "안 쓴다고 적어 두고 쓰고 있다"

    # 주석과 코드가 맞는가 — 실제로 걸린 것은 resize 뿐이었다
    assert "패널이 열리거나 화면이 바뀌면 남아 있던 비침을 지운다" not in js
    assert "화면 폭이 바뀌면 남아 있던 비침을 지운다" in js


# ── 18. .out 규칙이 기준 문서에 적혔다 ──────────────────────────────


def test_u_18_CLAUDE_md_에_비침과_out_이_적혔다():
    """점은 이 달만, 비침은 격자에 보이는 칸까지 — 두 곳이 다르다."""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    at = text.index("#### 점의 생김새는 보드의 규칙을 그대로 씁니다")
    section = text[at : text.index("#### 범위 칩")]
    assert "비칩니다" in section
    assert ":not(.out)" in section, "점을 놓는 범위가 안 적혔다"
    assert "격자에 보이는 칸까지" in section, "비추는 범위가 안 적혔다"
    assert "무채색" in section


def test_u_08b_화면_폭이_두_곳에_있다는_것을_적었다():
    """CSS 는 max-width:820px, JS 는 min-width:821px. 한 곳에서 읽을 수
    없으므로 **같이 움직여야 한다**고 양쪽에 적는다."""
    js = read_js("calendar.js")
    assert "820px" in js and "같이 바꿔야" in js
    # **양쪽에** 적어야 한다. 한쪽에만 적으면 다른 쪽을 고치는 사람은 못 본다
    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    assert "821px" in css and "같이 바꿔야" in css
