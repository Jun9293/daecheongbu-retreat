"""4단계 — 예산 화면 (CLAUDE.md 7-3 · 2026-09-26 사람이 정한 확정본).

바뀐 것 —

- 구분은 **왼쪽 열로 빠져 병합**되고, 세부항목이 여럿인 항목은 **항목 셀이 병합**된다
- 구분마다 **소계 줄**. 제목은 예산금액 바로 왼쪽, 음영은 구분 칸까지
- 「비율」 → **예산비율**, 옛 「집행률」 칸 자리 → **결산비율**(항목 결산 ÷ 총 결산).
  **다른 수다** — 그래서 줄마다의 집행률은 화면에서 없어졌다
- 고치는 것은 **「전체 편집」 하나**이고 저장도 `POST /budget/bulk` **한 번**이다.
  전부 되거나 전부 안 된다
- 줄 끝에 **비고**(`BudgetCategory.note`)

**막는 쪽을 실제로 만들어 잰다**(11-3) — 걸리는 줄을 섞어 보내고 **아무것도 안
바뀌었는지**, 편집이 꺼진 화면에 이동 핸들이 **안 그려지는지**를 본다.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest
from sqlalchemy import select

from app import models
from app.domain import budget as B
from tests.conftest import app_session

TODAY = dt.date.today()
ROOT = pathlib.Path(__file__).resolve().parent.parent
JS = (ROOT / "app" / "static" / "js" / "budget.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")


@pytest.fixture
def 예산(admin_client):
    """구분 둘 · 한 항목은 세부항목 둘(병합이 실제로 서야 한다) · 지출 하나."""
    with app_session() as db:
        retreat = models.Retreat(
            name="예산 시험 회차", meal_subsidy_per_person=8000,
            start_date=TODAY + dt.timedelta(days=30), end_date=TODAY + dt.timedelta(days=32))
        db.add(retreat)
        db.flush()

        def cat(l1, l2, l3, planned, order):
            row = models.BudgetCategory(
                retreat_id=retreat.id, level1=l1, level2=l2, level3=l3,
                planned_amount=planned, sort_order=order)
            db.add(row)
            db.flush()
            return row

        a = cat("홍보", "인쇄물", "포스터", 300_000, 1)
        b = cat("홍보", "인쇄물", "현수막", 200_000, 2)
        c = cat("식비", "본행사", None, 500_000, 3)
        db.add(models.ExpenseEntry(
            retreat_id=retreat.id, budget_category_id=a.id, expense_date=TODAY,
            amount=100_000, subsidy_amount=100_000, personal_burden_amount=0,
            payer_name="수련회계좌", paid=True))
        db.commit()
        return {"retreat": retreat.id, "a": a.id, "b": b.id, "c": c.id}


def _summary(rid):
    with app_session() as db:
        return B.build_budget_summary(db, retreat=db.get(models.Retreat, rid))


def _본문(page: str) -> str:
    return page.split("<tbody>")[1].split("</tbody>")[0]


# ── ㄱ. 표 모양 — 병합과 소계 ─────────────────────────────────────


def test73_a01_구분과_항목이_병합된_칸으로_선다(admin_client, 예산):
    page = admin_client.get(f"/budget?retreat_id={예산['retreat']}").text
    본문 = _본문(page)
    # 홍보(2줄) · 식비(1줄) — rowspan 은 그 구분의 **세부항목 줄 수**다(소계는 뺀다)
    assert 'class="l1" rowspan="2"' in 본문
    assert 'class="l1" rowspan="1"' in 본문
    # 인쇄물은 세부항목이 둘이라 항목 셀이 병합된다
    assert 'class="l2" rowspan="2"' in 본문


def test73_a02_소계는_구분마다_따로_줄로_선다(admin_client, 예산):
    본문 = _본문(admin_client.get(f"/budget?retreat_id={예산['retreat']}").text)
    assert 본문.count('class="subtot"') == 2, "구분마다 하나여야 한다"
    # 제목은 예산금액 **바로 왼쪽** — 구분부터 횟수까지 여섯 칸을 먹는다
    assert '<td colspan="6" class="r">소계</td>' in 본문


def test73_a03_소계_값은_summary_의_것이다(admin_client, 예산):
    s = _summary(예산["retreat"])
    홍보 = next(g for g in s.groups if g.name == "홍보")
    assert 홍보.planned == 500_000 and 홍보.spent == 100_000
    본문 = _본문(admin_client.get(f"/budget?retreat_id={예산['retreat']}").text)
    assert "500,000" in 본문


def test73_a04_접기_토글과_세부항목_개수는_없다(admin_client, 예산):
    """병합된 셀과 접는 자리가 한 칸에서 부딪힌다 — 둘 다 걷었다."""
    본문 = _본문(admin_client.get(f"/budget?retreat_id={예산['retreat']}").text)
    assert 'data-fold' not in 본문 and 'class="fold"' not in 본문
    assert "세부항목 " not in 본문


def test73_a05_비고_칸이_있다(admin_client, 예산):
    with app_session() as db:
        db.get(models.BudgetCategory, 예산["a"]).note = "견적 두 곳"
        db.commit()
    page = admin_client.get(f"/budget?retreat_id={예산['retreat']}").text
    assert "<th class=\"c-note\">비고" in page
    assert "견적 두 곳" in _본문(page)


# ── ㄴ. 두 비율 — 다른 수다 ───────────────────────────────────────


def test73_b01_예산비율과_결산비율은_분모가_다르다(예산):
    s = _summary(예산["retreat"])
    a = next(r for r in s.categories if r.category.id == 예산["a"])
    assert a.ratio_pct == round(300_000 / s.total_planned * 100, 1)
    # 쓴 돈이 이 한 건뿐이라 결산비율은 100 이다 — 「집행률」(100,000/300,000)과 다르다
    assert a.settle_ratio_pct == 100.0
    assert a.progress_pct == round(100_000 / 300_000 * 100, 1)


def test73_b02_결산비율의_분모는_총_결산이다(예산):
    """미지정·취소된 항목에 걸린 지출까지 든 값이라야 화면의 총계와 맞는다."""
    with app_session() as db:
        db.add(models.ExpenseEntry(
            retreat_id=예산["retreat"], budget_category_id=None, expense_date=TODAY,
            amount=100_000, subsidy_amount=100_000, personal_burden_amount=0,
            payer_name="수련회계좌", paid=True))
        db.commit()
    s = _summary(예산["retreat"])
    a = next(r for r in s.categories if r.category.id == 예산["a"])
    assert s.total_spent == 200_000
    assert a.settle_ratio_pct == 50.0


def test73_b03_줄마다의_집행률_칸은_화면에_없다(admin_client, 예산):
    page = admin_client.get(f"/budget?retreat_id={예산['retreat']}").text
    assert "예산비율" in page and "결산비율" in page
    assert "집행률" not in _본문(page)


# ── ㄷ. 전체 편집 — 한 번에 저장되고, 걸리면 아무것도 안 바뀐다 ──────


def _몸(rows, removed=None):
    return {"rows": rows, "removed": removed or []}


def _줄(cat, **kw):
    줄 = {
        "id": cat.id, "level1": cat.level1, "level2": cat.level2,
        "level3": cat.level3 or "", "unit_price": cat.unit_price,
        "headcount": cat.headcount, "times": cat.times,
        "planned_amount": cat.planned_amount, "note": cat.note or "",
    }
    줄.update(kw)
    return 줄


def _줄들(rid):
    with app_session() as db:
        cats = db.scalars(
            select(models.BudgetCategory)
            .where(models.BudgetCategory.retreat_id == rid,
                   models.BudgetCategory.canceled_at.is_(None))
            .order_by(models.BudgetCategory.sort_order, models.BudgetCategory.id)).all()
        return [_줄(c) for c in cats]


def test73_c01_한_번에_고치고_순서를_정한다(admin_client, 예산):
    rid = 예산["retreat"]
    줄들 = _줄들(rid)
    줄들.reverse()                       # 끌어 옮긴 것과 같은 모양
    줄들[0]["note"] = "옮겼다"
    r = admin_client.post(f"/budget/bulk?retreat_id={rid}", json=_몸(줄들))
    assert r.status_code == 200, r.text
    with app_session() as db:
        cats = db.scalars(
            select(models.BudgetCategory)
            .where(models.BudgetCategory.retreat_id == rid)
            .order_by(models.BudgetCategory.sort_order)).all()
        assert [c.id for c in cats][:3] == [줄["id"] for 줄 in 줄들]
        assert cats[0].note == "옮겼다"


def test73_c02_새_줄은_id_가_없다(admin_client, 예산):
    rid = 예산["retreat"]
    줄들 = _줄들(rid)
    줄들.append({"id": None, "level1": "식비", "level2": "간식", "level3": "야식",
                 "unit_price": 3000, "headcount": 40, "times": 2,
                 "planned_amount": 0, "note": ""})
    assert admin_client.post(f"/budget/bulk?retreat_id={rid}", json=_몸(줄들)).status_code == 200
    s = _summary(rid)
    새것 = next(r for r in s.categories if r.category.level3 == "야식")
    # 단가 × 명수 × 횟수가 이긴다 — 셈은 서버의 같은 함수다 (7-3)
    assert 새것.planned == 3000 * 40 * 2


def test73_c03_빼면_취소_표시일_뿐_행은_남는다(admin_client, 예산):
    rid, cid = 예산["retreat"], 예산["b"]
    줄들 = [줄 for 줄 in _줄들(rid) if 줄["id"] != cid]
    assert admin_client.post(f"/budget/bulk?retreat_id={rid}",
                             json=_몸(줄들, [cid])).status_code == 200
    with app_session() as db:
        cat = db.get(models.BudgetCategory, cid)
        assert cat is not None, "행이 지워졌다 (0장)"
        assert cat.canceled_at is not None
    s = _summary(rid)
    assert cid in {r.category.id for r in s.canceled_categories}


def test73_c04_걸리는_줄이_있으면_아무것도_안_바뀐다(admin_client, 예산):
    """**막는 쪽을 실제로 만들어 잰다** — 절반만 들어간 표가 생기면 안 된다."""
    rid = 예산["retreat"]
    전 = _summary(rid).total_planned
    줄들 = _줄들(rid)
    줄들[0]["note"] = "이건 저장되면 안 된다"
    줄들[0]["planned_amount"] = 999_000
    줄들[-1]["level2"] = "   "                     # 마지막 줄이 걸린다
    r = admin_client.post(f"/budget/bulk?retreat_id={rid}", json=_몸(줄들))
    assert r.status_code == 400
    assert "비울 수 없습니다" in r.json()["detail"]
    with app_session() as db:
        assert db.get(models.BudgetCategory, 줄들[0]["id"]).note in (None, "")
    assert _summary(rid).total_planned == 전


def test73_c05_음수는_거절한다(admin_client, 예산):
    rid = 예산["retreat"]
    줄들 = _줄들(rid)
    줄들[0]["unit_price"] = -1
    r = admin_client.post(f"/budget/bulk?retreat_id={rid}", json=_몸(줄들))
    assert r.status_code == 400 and "0보다" in r.json()["detail"]


def test73_c06_남의_회차_항목은_안_받는다(admin_client, 예산):
    rid = 예산["retreat"]
    with app_session() as db:
        다른 = models.Retreat(name="남의 회차", start_date=TODAY, end_date=TODAY)
        db.add(다른)
        db.flush()
        밖 = models.BudgetCategory(retreat_id=다른.id, level1="x", level2="y",
                                   planned_amount=1000, sort_order=1)
        db.add(밖)
        db.commit()
        밖id = 밖.id
    줄들 = _줄들(rid)
    줄들[0]["id"] = 밖id
    r = admin_client.post(f"/budget/bulk?retreat_id={rid}", json=_몸(줄들))
    assert r.status_code == 400
    r2 = admin_client.post(f"/budget/bulk?retreat_id={rid}", json=_몸(_줄들(rid), [밖id]))
    assert r2.status_code == 400


def test73_c07_두_번_보내도_같은_모양이다(admin_client, 예산):
    """재실행 안전 — 같은 몸을 두 번 보내면 줄이 늘지 않는다."""
    rid = 예산["retreat"]
    줄들 = _줄들(rid)
    admin_client.post(f"/budget/bulk?retreat_id={rid}", json=_몸(줄들))
    n1 = len(_summary(rid).categories)
    admin_client.post(f"/budget/bulk?retreat_id={rid}", json=_몸(줄들))
    assert len(_summary(rid).categories) == n1


def test73_c08_관리자가_아니면_못_고친다(client, 예산):
    from tests.conftest import login_as, make_user
    사람 = make_user("일반 사람", "010-7777-0001", "general")
    login_as(client, 사람)
    r = client.post(f"/budget/bulk?retreat_id={예산['retreat']}", json=_몸(_줄들(예산["retreat"])))
    assert r.status_code in (302, 303, 403)


def test73_c09_저장은_기록에_남는다(admin_client, 예산):
    rid = 예산["retreat"]
    # 뺀 줄은 `rows` 에서도 빠진다 — 화면이 그렇게 보내고, 같은 줄이 양쪽에
    # 오면 서버가 거절한다(같은 몸이 「고쳐라」 와 「취소하라」 를 함께 말한다)
    겹친 = admin_client.post(f"/budget/bulk?retreat_id={rid}", json=_몸(_줄들(rid), [예산["c"]]))
    assert 겹친.status_code == 400, "고치면서 동시에 취소하는 몸이 지나갔다"
    남는줄 = [줄 for 줄 in _줄들(rid) if 줄["id"] != 예산["c"]]
    r = admin_client.post(f"/budget/bulk?retreat_id={rid}", json=_몸(남는줄, [예산["c"]]))
    assert r.status_code == 200
    with app_session() as db:
        줄 = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "예산표_저장")).all()
        assert 줄, "활동 기록이 없다"
        assert "취소 1" in 줄[-1].summary


# ── ㄹ. 편집이 꺼진 화면에는 이동 핸들이 없다 (막는 쪽) ─────────────


def test73_d01_핸들은_편집_상태에서만_보인다(admin_client, 예산):
    page = admin_client.get(f"/budget?retreat_id={예산['retreat']}").text
    assert 'data-grip' not in _본문(page), "보는 판에 핸들이 그려졌다"
    # CSS 도 같은 말을 한다 — 켜지기 전에는 display:none
    assert re.search(r"\.budtbl \.grip\{display:none\}", CSS)
    assert re.search(r"\.budtbl\.editing \.grip\{display:inline-block", CSS)


def test73_d02_핸들은_다시_그릴_때만_만들어진다():
    """보는 판(서버)과 편집 판(JS)이 **같은 모델**에서 나온다 — 핸들은 JS 쪽에만 있다."""
    t = (ROOT / "app" / "templates" / "partials" / "budtable.html").read_text(encoding="utf-8")
    assert "data-grip" not in t
    assert JS.count('data-grip="item"') == 1 and JS.count('data-grip="row"') == 1


def test73_d03_머리줄은_스크롤해도_붙어_있다():
    assert re.search(r"\.budwrap \.fintbl thead th\{position:sticky", CSS)


def test73_d04_열람_전용에게는_전체_편집이_없다(client, 예산):
    from tests.conftest import login_as, make_user
    사람 = make_user("열람 사람", "010-7777-0002", "viewer")
    login_as(client, 사람)
    page = client.get(f"/budget?retreat_id={예산['retreat']}").text
    assert "budedit" not in page and "bud-rows" not in page
