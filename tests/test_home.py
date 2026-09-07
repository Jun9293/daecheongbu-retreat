"""홈 (CLAUDE.md 4-15) + 종료 판정 한 곳(period) — UI 개편 단계 2.

숫자는 화면이 아니라 도메인 함수에서 나와야 한다 — 여기서는 **같은 DB 로
홈이 낸 값과 도메인 함수 값을 견준다.** 값을 시험에 박지 않는다 (11-3).
"""

from __future__ import annotations

import datetime as dt
import re

import pytest
from sqlalchemy import select

from app import models
from app.domain import escalation, home as home_domain, period
from app.domain.board import overdue_of
from app.domain.budget import build_budget_summary
from tests.conftest import app_session, login_as, make_user

TODAY = dt.date.today()


# ---------------------------------------------------------------- period (1-b · 2)


def test_p01_속성이_없는_객체는_삼키지_않고_터진다():
    """getattr 로 삼키면 모든 회차가 조용히 '진행 중' 이 된다 (1-b)."""

    class 엉뚱한것:
        pass

    with pytest.raises(AttributeError):
        period.is_over(엉뚱한것(), TODAY)


def _retreat(open_date, close_date, archived=False):
    class R:
        start_date = open_date
        end_date = close_date
        is_archived = archived

    return R()


def test_p02_결산_전환_넷():
    """개회일+1 보통 · 폐회일 당일 보통 · 폐회일+1 결산 · is_archived 결산."""
    open_d, close_d = dt.date(2026, 8, 21), dt.date(2026, 8, 23)
    r = _retreat(open_d, close_d)
    assert period.is_over(r, open_d + dt.timedelta(days=1)) is False
    assert period.is_over(r, close_d) is False
    assert period.is_over(r, close_d + dt.timedelta(days=1)) is True
    assert period.is_over(_retreat(open_d, close_d, archived=True), open_d) is True


def test_p03_종료_판정이_한_곳이다():
    """diagnosis(4-10)·live(5-6)가 period.is_over 를 부르고, `end_date <` 꼴
    판정이 period.py 밖에 없다 (grep 을 시험으로)."""
    import pathlib
    import subprocess

    root = pathlib.Path(__file__).resolve().parent.parent
    out = subprocess.run(
        ["git", "grep", "-n", "end_date <", "--", "app/", "scripts/"],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    hits = [l for l in out.splitlines() if "domain/period.py" not in l]
    assert hits == [], f"period 밖의 종료 판정: {hits}"

    for name in ("diagnosis", "live"):
        text = (root / "app" / "domain" / f"{name}.py").read_text(encoding="utf-8")
        assert "period.is_over(" in text, f"{name} 가 period 를 안 쓴다"


# ---------------------------------------------------------------- 홈 데이터


@pytest.fixture
def home_data(admin_client):
    """실제 오늘을 기준으로 만든 회차 — HTTP 로 여는 시험이 날짜에 흔들리지 않게."""
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회 Belong",
            start_date=TODAY + dt.timedelta(days=30),
            end_date=TODAY + dt.timedelta(days=33),
        )
        db.add(retreat)
        db.flush()
        dept = models.Department(
            retreat_id=retreat.id, key="chongmuM", name="1 총무M",
            color_tag="#2F4858", sort_order=0)
        other = models.Department(
            retreat_id=retreat.id, key="hebron", name="5 헤브론",
            color_tag="#4A8A5C", sort_order=1)
        db.add_all([dept, other])
        db.flush()
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()

        def run(title, *, end, status="대기", assignee=None, d=dept, included=True):
            lib = models.TaskLibrary(title=title, kind="main", default_d_week=5)
            db.add(lib)
            db.flush()
            row = models.TaskRun(
                library_id=lib.id, retreat_id=retreat.id, included=included,
                department_id=d.id, assignee_id=assignee, d_week=5,
                start_date=end, end_date=end, status=status)
            db.add(row)
            return row

        run("어제 마감 내 일", end=TODAY - dt.timedelta(days=2), assignee=admin.id)
        run("오늘 마감 내 일", end=TODAY, assignee=admin.id, status="진행중")
        # 완료된 것은 「내 할 일」 에 안 나온다 — D+N 이 붙을 자리가 없다
        run("끝낸 내 일", end=TODAY - dt.timedelta(days=5), assignee=admin.id, status="완료")
        # 담당자 없이 마감 7일 이내 — 경고 띠 둘째 줄
        run("담당 없는 임박", end=TODAY + dt.timedelta(days=3))
        # 타 부서 · 이번 주
        run("헤브론 이번 주", end=TODAY + dt.timedelta(days=5), d=other)
        # 이번 주 밖
        run("먼 미래", end=TODAY + dt.timedelta(days=20))
        run("빼놓은 것", end=TODAY, included=False)

        cat = models.BudgetCategory(
            retreat_id=retreat.id, level1="홍보", level2="포스터",
            level3="인쇄비", planned_amount=300_000, sort_order=0)
        db.add(cat)
        db.flush()
        db.add(models.ExpenseEntry(
            retreat_id=retreat.id, budget_category_id=cat.id,
            receipt_number="1", expense_date=TODAY, amount=120_000,
            payer_name="박민준", payer_account="", paid=False,
            subsidy_amount=120_000, personal_burden_amount=0))
        db.commit()
        return {"retreat_id": retreat.id, "admin_id": admin.id}


def _kpi(page: str, label: str) -> str:
    m = re.search(
        rf'<div class="l">{label}</div>\s*<div class="v"[^>]*>\s*([0-9.,]+)', page
    )
    assert m, f"지표 '{label}' 이 화면에 없다"
    return m.group(1).replace(",", "")


# ---------------------------------------------------------------- 3 · 4. / 가 홈, 지표 = 도메인


def test_h01_루트가_홈이고_보드는_그대로다(admin_client, home_data):
    page = admin_client.get("/")
    assert page.status_code == 200
    assert '<div class="l">남은 할 일</div>' in page.text
    board = admin_client.get("/board")
    assert board.status_code == 200 and 'id="board"' in board.text


def test_h02_지표_4칸이_도메인_함수_값과_같다(admin_client, home_data):
    page = admin_client.get("/").text

    with app_session() as db:
        retreat = db.get(models.Retreat, home_data["retreat_id"])
        runs = list(db.scalars(select(models.TaskRun).where(
            models.TaskRun.retreat_id == retreat.id,
            models.TaskRun.included.is_(True))))
        open_runs = [r for r in runs if r.status != "완료"]
        overdue = sum(1 for r in open_runs if overdue_of(r, TODAY))
        budget = build_budget_summary(db, retreat=retreat)
        unassigned = len(escalation.unassigned_runs_due_soon(runs, today=TODAY))

    assert int(_kpi(page, "남은 할 일")) == len(open_runs)
    assert int(_kpi(page, "완료")) == len(runs) - len(open_runs)
    assert float(_kpi(page, "예산 집행률")) == budget.progress_pct
    assert int(_kpi(page, "지연")) == overdue
    # 경고 띠 둘째 줄의 수도 escalation 그대로
    assert f"이내인 할 일이 <b>&nbsp;{unassigned}건" in page


def test_h03_홈_라우터와_템플릿은_세지_않는다():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    router = (root / "app" / "routers" / "home.py").read_text(encoding="utf-8")
    template = (root / "app" / "templates" / "home.html").read_text(encoding="utf-8")
    for word in ("overdue_of", "sum(", "len("):
        assert word not in router, f"라우터가 센다: {word}"
    for word in ("|length", "|count", "overdue_of"):
        assert word not in template, f"템플릿이 센다: {word}"


# ---------------------------------------------------------------- 5. 경고 띠


def test_h04_경고_띠는_0건이면_없다(admin_client, home_data):
    page = admin_client.get("/").text
    assert "기한이 지난 할 일이" in page          # 1건 이상 → 있다
    assert "총무팀 확인이 필요합니다" in page

    # 전부 해소하면 띠가 사라진다
    with app_session() as db:
        for r in db.scalars(select(models.TaskRun)):
            r.status = "완료"
        db.commit()
    page = admin_client.get("/").text
    assert "기한이 지난 할 일이" not in page
    assert "총무팀 확인이 필요합니다" not in page


# ---------------------------------------------------------------- 6. 내 할 일


def test_h05_내_할_일은_내_담당_미완료만_마감_오름차순(admin_client, home_data):
    with app_session() as db:
        retreat = db.get(models.Retreat, home_data["retreat_id"])
        me = db.get(models.User, home_data["admin_id"])
        view = home_domain.build(db, retreat, me, today=TODAY)
        titles = [r.title for r in view.my_today]

    assert titles == ["어제 마감 내 일", "오늘 마감 내 일"]  # 오름차순 · 완료 제외


def test_h06_완료된_업무에는_D플러스N_이_없다(admin_client, home_data):
    """끝낸 내 일(D+5 자리)은 아예 목록에 없다 — 완료에 D+N 을 붙일 자리가 없다."""
    page = admin_client.get("/").text
    assert "끝낸 내 일" not in page
    # 미완료 지연에는 D+ 가 붙는다 (붙는 쪽도 본다 — 막는 쪽만 보면 검사가 빈다)
    assert re.search(r"어제 마감 내 일.*?D\+2", page, re.S)


# ---------------------------------------------------------------- 7. 결산 홈


def test_h07_폐회_다음_날부터_결산_홈(admin_client, home_data):
    with app_session() as db:
        retreat = db.get(models.Retreat, home_data["retreat_id"])
        me = db.get(models.User, home_data["admin_id"])
        open_d = retreat.start_date

        # now 주입 — 개회일+1(보통) · 폐회일(보통) · 폐회일+1(결산) · 보관(결산)
        assert home_domain.build(db, retreat, me, today=open_d + dt.timedelta(days=1)).over is False
        assert home_domain.build(db, retreat, me, today=retreat.end_date).over is False
        after = home_domain.build(db, retreat, me, today=retreat.end_date + dt.timedelta(days=1))
        assert after.over is True

        retreat.is_archived = True
        db.flush()
        assert home_domain.build(db, retreat, me, today=open_d).over is True
        retreat.is_archived = False
        db.commit()

    # 결산 홈 렌더링 — 폐회일을 어제로 옮기면 실제 화면이 바뀐다
    with app_session() as db:
        retreat = db.get(models.Retreat, home_data["retreat_id"])
        retreat.start_date = TODAY - dt.timedelta(days=4)
        retreat.end_date = TODAY - dt.timedelta(days=1)
        db.commit()
    page = admin_client.get("/").text
    assert "미지급 환급" in page and "영수증 없는 지출" in page and "미완료 업무" in page
    assert "기한이 지난 할 일이" not in page       # 경고 띠 없음
    assert '<div class="l">지연</div>' not in page  # 지연 지표 없음

    with app_session() as db:
        me = db.get(models.User, home_data["admin_id"])
        retreat = db.get(models.Retreat, home_data["retreat_id"])
        view = home_domain.build(db, retreat, me, today=TODAY)
    assert view.unpaid_refund_count == 1   # 지원금 12만원 · 미지급
    assert view.no_receipt_count == 1      # 영수증 파일 없음
    assert view.open_task_count == 5       # 미완료 (included 만)


# ---------------------------------------------------------------- 8. 옛 /dashboard


def test_h08_dashboard_는_301_로_홈에_간다(admin_client, home_data):
    r = admin_client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/"


def test_h08b_구설계_사용자_POST_가_지워졌다(admin_client, home_data):
    """지운 것이 실제로 지워졌는가 (막히는 쪽 시험 — 11-3). pytest 초록은
    「아무도 안 부른다」 이지 「지워졌다」 가 아니다."""
    assert admin_client.post(
        "/users/create", data={"name": "몰래", "phone_number": "01099998888"}
    ).status_code == 404
    assert admin_client.post(
        "/users/1/update", data={"role": "admin"}
    ).status_code == 404


def test_h10_소속_외_흐림은_부서_키로_가른다(admin_client, home_data):
    """id 로 비교하면 새 회차가 열리는 순간 자기 부서까지 흐려진다 (2장).
    같은 키의 다른 회차 부서 행에 묶인 계정도 자기 부서는 선명해야 한다."""
    with app_session() as db:
        retreat = db.get(models.Retreat, home_data["retreat_id"])
        # 지난 회차 — 같은 키(hebron)의 **다른 Department 행**
        old = models.Retreat(name="지난 회차", start_date=TODAY - dt.timedelta(days=400))
        db.add(old)
        db.flush()
        old_hebron = models.Department(
            retreat_id=old.id, key="hebron", name="5 헤브론", sort_order=0)
        db.add(old_hebron)
        db.flush()
        lead = models.User(
            name="헤브론 리더", phone_number="01077770000", role="dept_lead",
            department_id=old_hebron.id)
        db.add(lead)
        db.flush()

        view = home_domain.build(db, retreat, lead, today=TODAY)
        by_id = {r.id: r.title for r in view.week}
        dim_titles = {by_id[i] for i in view.dim_ids if i in by_id}

    # 이번 주 목록에서 타 부서(총무M)만 흐리고, 내 부서(헤브론)는 선명하다
    assert "헤브론 이번 주" not in dim_titles
    assert any(t != "헤브론 이번 주" for t in dim_titles)


# ---------------------------------------------------------------- 1-d. 확인 요청과 알림 페이지


def test_h09_확인_요청은_받은_것_목록에_서고_0건이면_조용하다(
        admin_client, client, home_data):
    """옛 알림함의 상단 「답 기다리는 확인 요청 N건」 줄은 화면과 함께
    사라졌다 (4-16) — 요청은 받은 것 목록의 **사람 발신** 항목이고, 답하는
    폼이 그 자리에 있다. 0건이면 아무 흔적이 없다."""
    page = admin_client.get("/notifications").text
    assert "답 기다리는 확인 요청" not in page
    assert 'class="sender human"' not in page
    assert 'href="/reviews"' not in page          # 옛 화면으로 가는 길도 없다

    from app.routers.reviews import create_review_requests

    with app_session() as db:
        retreat = db.get(models.Retreat, home_data["retreat_id"])
        dept = db.scalars(select(models.Department).where(
            models.Department.retreat_id == retreat.id)).first()
        admin = db.scalars(select(models.User).where(
            models.User.role == "admin")).first()
        dept_id = dept.id
        # 요청자는 자기 알림을 받지 않으므로(exclude_user_id) 받는 사람을 만든다
        member = models.User(name="총무 팀원", phone_number="01088880001",
                             role="member", department_id=dept_id)
        db.add(member)
        db.flush()
        reviews = create_review_requests(
            db, retreat=retreat, requester=admin,
            department_ids=[dept_id], message="확인 부탁")
        db.commit()
        review_id = reviews[0].id

    login_as(client, "01088880001")
    client.get(f"/board?retreat_id={home_data['retreat_id']}")
    page = client.get("/notifications").text
    assert 'class="sender human"' in page          # 사람 발신 배지
    assert f'action="/reviews/{review_id}/respond"' in page   # 그 자리에서 답한다
    # 「답을 기다리는 것」 칩으로도 걸린다
    pending = client.get("/notifications?chip=pending").text
    assert f'action="/reviews/{review_id}/respond"' in pending
