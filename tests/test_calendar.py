"""달력 보기 (CLAUDE.md 4-13). 수용 기준 1~17.

**`today` 를 주입합니다.** 실행 날짜에 따라 갈리는 테스트는 며칠 뒤 아무도
모르게 빨간불이 되고, 그러면 테스트를 안 보게 됩니다 — 진단 패널(4-10)과
수련회 진행(5장)에서 해 온 방식 그대로입니다.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.domain import calendar as cal_domain
from tests.conftest import app_session, login_as

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


def test_08_점을_누르면_보드의_상세_패널이_열린다(admin_client, cal_data):
    """**여기서 새로 만들지 않는다.** `/board?task=` 가 이미 그 일을 한다
    (알림을 누르고 들어올 때 쓰던 길, 4-11)."""
    page = admin_client.get("/calendar?scope=all").text
    run_id = cal_data["runs"]["오늘 업무"]
    assert f'href="/board?task={run_id}"' in page

    # 달력 화면에는 상세 패널을 두지 않는다 — 두 벌이 되면 갈린다
    view = open("app/templates/calendar.html", encoding="utf-8").read()
    assert 'id="drawer"' not in view
    assert "daddlog" not in view

    # 그 길이 실제로 살아 있다
    assert admin_client.get(f"/board?task={run_id}").status_code == 200
    js = open("app/static/js/board.js", encoding="utf-8").read()
    assert "get('task')" in js


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
    fresh = TestClient(admin_client.app if hasattr(admin_client, "app") else None) \
        if False else None
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
