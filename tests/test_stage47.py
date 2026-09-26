"""재정 차례 5 — 고치는 길 (2026-09-14).

- 지출: 일자 · 금액 · 예산 항목 · 세부 항목명 · 식사 인원 · 지출자 · 계좌 셋 · 비고를 고친다.
  영수증의 원본 번호를 고친다. 문은 `_my_entry` 하나(부서 403 · 취소 409)
- 예산 항목: 취소된 항목은 못 고친다(409)
- 수입: 고치는 길이 새로 섰다 — 예산 항목과 같은 모양(총무팀 · 취소 409 · 전후 기록)
- 계좌를 가르는 규칙은 `domain/budget.py` 의 `split_account` 하나
- 활동 기록: 바뀐 칸만 · 계좌는 값 없이 「바뀜」

계좌·이름은 지어낸 값이다. 수는 박지 않는다(11-3).
"""

from __future__ import annotations

import ast
import datetime as dt
import pathlib
import re

import pytest
from sqlalchemy import select

from app import models
from app.domain import budget as B
from tests.conftest import app_session, login_as, make_user

TODAY = dt.date.today()
ROOT = pathlib.Path(__file__).resolve().parent.parent
은행, 번호, 예금주 = "지어낸은행", "999-0000-1111", "가명예금주"
새은행, 새번호 = "다른지어낸은행", "888-7777-2222"


@pytest.fixture
def 판(admin_client):
    with app_session() as db:
        r = models.Retreat(name="차례5 회차", meal_subsidy_per_person=8000,
                           start_date=TODAY + dt.timedelta(days=30),
                           end_date=TODAY + dt.timedelta(days=32))
        db.add(r)
        db.flush()
        dept = models.Department(retreat_id=r.id, key="chongmuM", name="1 총무M", sort_order=0)
        other = models.Department(retreat_id=r.id, key="hebron", name="5 헤브론", sort_order=1)
        db.add_all([dept, other])
        db.flush()
        c1 = models.BudgetCategory(retreat_id=r.id, level1="홍보", level2="포스터", planned_amount=100_000, sort_order=1)
        c2 = models.BudgetCategory(retreat_id=r.id, level1="식비", level2="야식", planned_amount=300_000, sort_order=2)
        db.add_all([c1, c2])
        db.add(models.IncomeItem(retreat_id=r.id, name="수련회비", amount=1_000_000, sort_order=1))
        db.commit()
        ids = {"retreat": r.id, "dept": dept.id, "other": other.id, "c1": c1.id, "c2": c2.id,
               "income": db.scalar(select(models.IncomeItem.id))}
    admin_client.get(f"/budget?retreat_id={ids['retreat']}")
    return ids


def _등록(client, ids, amount, **extra):
    data = {"amount": str(amount), "department_id": str(ids["dept"]), "payer_name": "가명지출자",
            "budget_category_id": str(ids["c1"])}
    data.update(extra)
    assert client.post(f"/expenses/create?retreat_id={ids['retreat']}", data=data,
                       follow_redirects=True).status_code == 200
    with app_session() as db:
        return db.scalar(select(models.ExpenseEntry.id).order_by(models.ExpenseEntry.id.desc()))


def _고침(client, ids, eid, **fields):
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        data = {"expense_date": e.expense_date.isoformat(), "amount": str(e.amount),
                "budget_category_id": str(e.budget_category_id or ""), "payer_name": e.payer_name or "",
                "payer_bank": e.payer_bank or "", "payer_account_number": e.payer_account_number or "",
                "payer_account_holder": e.payer_account_holder or "", "note": e.note or "",
                "level3b": e.level3b or "",
                "meal_headcount": "" if e.meal_headcount is None else str(e.meal_headcount)}
    data.update({k: str(v) for k, v in fields.items()})
    return client.post(f"/expenses/{eid}/update?retreat_id={ids['retreat']}", data=data)


def _마지막기록(action):
    with app_session() as db:
        return db.scalars(select(models.ActivityLog).where(models.ActivityLog.action == action)
                          .order_by(models.ActivityLog.id.desc())).first()


# ── 가) 지출 고치기 — 계좌 셋 · 원본 번호도 각각 ──


def test47_a01_지출을_고치고_계좌_셋도_고친다(admin_client, 판):
    eid = _등록(admin_client, 판, 10_000, payer_bank=은행, payer_account_number=번호,
               payer_account_holder=예금주)
    새날 = (TODAY - dt.timedelta(days=3)).isoformat()
    resp = _고침(admin_client, 판, eid, amount=12_000, expense_date=새날, budget_category_id=판["c2"],
               payer_name="다른가명", payer_bank=새은행, payer_account_number=새번호,
               payer_account_holder="", note="고친 비고")
    assert resp.status_code in (200, 303)
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        assert (e.amount, e.subsidy_amount, e.expense_date.isoformat()) == (12_000, 12_000, 새날)
        assert (e.payer_name, e.note) == ("다른가명", "고친 비고")
        assert (e.payer_bank, e.payer_account_number, e.payer_account_holder) == (새은행, 새번호, None)
        assert e.budget_category_id == 판["c2"] and (e.level1, e.level2) == ("식비", "야식")
    log = _마지막기록("지출_수정")
    assert log is not None
    # 바뀐 칸만 · 계좌 셋은 값 대신 「(바뀜)」 — 기록 어디에도 계좌 값이 없다
    assert set(log.after_value) >= {"amount", "payer_bank", "payer_account_number", "payer_account_holder"}
    assert "level3b" not in log.after_value, "안 바뀐 칸이 기록에 남았다"
    assert log.before_value["payer_account_number"] == "(바뀜)" == log.after_value["payer_account_number"]
    글 = f"{log.summary} {log.before_value} {log.after_value}"
    for 값 in (은행, 번호, 예금주, 새은행, 새번호):
        assert 값 not in 글
    assert log.before_value["amount"] == 10_000 and log.after_value["amount"] == 12_000
    # 아무것도 안 바꾸면 기록을 안 남긴다
    with app_session() as db:
        n = len(db.scalars(select(models.ActivityLog).where(models.ActivityLog.action == "지출_수정")).all())
    _고침(admin_client, 판, eid)
    with app_session() as db:
        assert len(db.scalars(select(models.ActivityLog).where(models.ActivityLog.action == "지출_수정")).all()) == n


def test47_a02_영수증_원본_번호를_고친다(admin_client, 판):
    rid = 판["retreat"]
    eid = _등록(admin_client, 판, 1_000, receipt_memo="별첨", receipt_original_no="17")
    with app_session() as db:
        r = db.get(models.ExpenseEntry, eid).receipts[0]
        rcpt_id, no = r.id, r.number
    assert admin_client.post(f"/expenses/{eid}/receipts/{rcpt_id}/original?retreat_id={rid}",
                             data={"original_no": "18-1"}, follow_redirects=True).status_code == 200
    with app_session() as db:
        assert db.get(models.ExpenseReceipt, rcpt_id).original_no == "18-1"
        assert db.get(models.ExpenseReceipt, rcpt_id).number == no, "자동 번호가 흔들렸다"
    log = _마지막기록("영수증_원본번호_수정")
    assert log.before_value == {"original_no": "17"} and log.after_value == {"original_no": "18-1"}
    # **2026-09-26 부터 영수증은 칩이고 원본 번호는 팝업이 말한다** — 목록에
    # 줄줄이 적지 않는다. 칩이 그 값을 들고 있어야 팝업이 보일 수 있다
    page = admin_client.get(f"/expenses?retreat_id={rid}").text
    assert f'data-no="{no}"' in page and 'data-orig="18-1"' in page
    # 비우면 비워진다 — 자리는 안 그려진다
    admin_client.post(f"/expenses/{eid}/receipts/{rcpt_id}/original?retreat_id={rid}", data={"original_no": ""})
    with app_session() as db:
        assert db.get(models.ExpenseReceipt, rcpt_id).original_no is None
    # 이 지출에 안 걸린 영수증 id 는 404
    e2 = _등록(admin_client, 판, 2_000)
    assert admin_client.post(f"/expenses/{e2}/receipts/{rcpt_id}/original?retreat_id={rid}",
                             data={"original_no": "x"}).status_code == 404


def test47_a03_식대_인원을_고치면_지원금액을_다시_센다(admin_client, 판):
    eid = _등록(admin_client, 판, 100_000, is_meal_expense="1", meal_headcount="5")
    with app_session() as db:
        assert db.get(models.ExpenseEntry, eid).subsidy_amount == 40_000
    _고침(admin_client, 판, eid, meal_headcount=20)
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        assert (e.meal_headcount, e.subsidy_amount, e.personal_burden_amount) == (20, 100_000, 0)


def test47_a04_부서_리더는_제_부서만_고치고_남의_계좌를_못_바꾼다(client, admin_client, 판):
    rid = 판["retreat"]
    내것 = _등록(admin_client, 판, 3_000, payer_bank=은행, payer_account_number=번호)
    남것 = _등록(admin_client, 판, 4_000, department_id=판["other"])
    make_user("가명고침리더", "01066660001", "dept_lead", dept=판["dept"])
    login_as(client, "01066660001")
    # 남의 부서 지출은 403
    assert _고침(client, 판, 남것, note="남의 것").status_code == 403
    # 제 부서 지출 — 화면에 계좌 칸이 없어 빈 값으로 와도 계좌는 그대로, 비고는 바뀐다
    page = client.get(f"/expenses?retreat_id={rid}").text
    # 고치는 길은 **「전체 편집」 하나**다 (7-4 · 2026-09-26) — 줄마다 폼을 펴지 않는다.
    # 남의 계좌를 못 보는 사람에게는 계좌를 **화면에 싣지 않는다**(그 판정이 이 줄이다)
    assert 'id="expedit"' in page and 번호 not in page
    assert 'data-acctedit="0"' in page
    assert _고침(client, 판, 내것, note="리더가 고침", payer_bank="", payer_account_number="",
               payer_account_holder="").status_code in (200, 303)
    with app_session() as db:
        e = db.get(models.ExpenseEntry, 내것)
        assert e.note == "리더가 고침"
        assert (e.payer_bank, e.payer_account_number) == (은행, 번호), "리더가 남의 계좌를 지웠다"


def test47_a05_계좌는_이름_팝업에서_보이고_복사한다(admin_client, 판):
    """**2026-09-26 에 자리가 바뀌었다** (7-4) — 목록에 뒤 네 자리를 적던 것이
    **지출자 이름의 팝업**으로 갔다. 목록에는 번호가 한 자리도 안 서고, 팝업이
    전체와 「복사」 를 준다. 볼 수 있는 사람 판정은 그대로 `계좌를_본다` 다.

    `account_tail` 은 엑셀·다른 화면이 쓰므로 그대로 잰다.
    """
    _등록(admin_client, 판, 5_000, payer_bank=은행, payer_account_number=번호)
    page = admin_client.get(f"/expenses?retreat_id={판['retreat']}").text
    assert 'class="payer acct"' in page and f'data-no="{번호}"' in page
    assert 'class="acct-no"' not in page, "목록에 번호가 그대로 섰다"
    assert B.account_tail(번호) == "…1111" and B.account_tail("") == "" and B.account_tail(None) == ""
    # 「복사」 단추는 팝업이 만든다 — 서버 쪽에는 안 보이므로 **그 부품에서** 잰다
    # (2026-09-26 검토 [R] — 옮기면서 재는 자리가 통째로 사라졌던 곳)
    js = (ROOT / "app" / "static" / "js" / "exppop.js").read_text(encoding="utf-8")
    assert "acctcopy" in js and "data-copy=" in js, "계좌 복사 단추가 사라졌다"


# ── 나) 취소된 지출 · 항목 · 수입은 못 고친다 ──


def test47_b01_취소된_지출은_고치기와_원본_번호가_409(admin_client, 판):
    rid = 판["retreat"]
    eid = _등록(admin_client, 판, 7_000, receipt_memo="별첨", receipt_original_no="3")
    with app_session() as db:
        rcpt_id = db.get(models.ExpenseEntry, eid).receipts[0].id
    admin_client.post(f"/expenses/{eid}/cancel?retreat_id={rid}")
    assert _고침(admin_client, 판, eid, amount=9_999).status_code == 409
    assert admin_client.post(f"/expenses/{eid}/receipts/{rcpt_id}/original?retreat_id={rid}",
                             data={"original_no": "99"}).status_code == 409
    with app_session() as db:
        assert db.get(models.ExpenseEntry, eid).amount == 7_000
        assert db.get(models.ExpenseReceipt, rcpt_id).original_no == "3"
    assert f"/expenses/{eid}/update" not in admin_client.get(f"/expenses?retreat_id={rid}").text


def test47_b02_취소된_예산_항목은_고치기가_409(admin_client, 판):
    rid, cid = 판["retreat"], 판["c1"]
    admin_client.post(f"/budget/categories/{cid}/cancel?retreat_id={rid}")
    resp = admin_client.post(f"/budget/categories/{cid}/update?retreat_id={rid}",
                             data={"level1": "바뀐구분", "level2": "바뀐항목", "planned_amount": "1"})
    assert resp.status_code == 409
    with app_session() as db:
        c = db.get(models.BudgetCategory, cid)
        assert (c.level1, c.level2, c.planned_amount) == ("홍보", "포스터", 100_000)
    # 산 항목은 된다 — 막히는 쪽만 재지 않는다
    assert admin_client.post(f"/budget/categories/{판['c2']}/update?retreat_id={rid}",
                             data={"level1": "식비", "level2": "야식", "planned_amount": "250000"},
                             follow_redirects=True).status_code == 200
    with app_session() as db:
        assert db.get(models.BudgetCategory, 판["c2"]).planned_amount == 250_000


def test47_b03_취소된_수입은_고치기가_409(admin_client, 판):
    rid, iid = 판["retreat"], 판["income"]
    admin_client.post(f"/budget/incomes/{iid}/cancel?retreat_id={rid}")
    assert admin_client.post(f"/budget/incomes/{iid}/update?retreat_id={rid}",
                             data={"name": "바뀐이름", "amount": "5"}).status_code == 409
    with app_session() as db:
        i = db.get(models.IncomeItem, iid)
        assert (i.name, i.amount) == ("수련회비", 1_000_000)


# ── 예산 항목 — 걸린 지출이 있어도 예산금액 · 이름을 고친다 ──


def test47_c01_걸린_지출이_있는_항목의_예산금액과_이름(admin_client, 판):
    rid, cid = 판["retreat"], 판["c1"]
    eid = _등록(admin_client, 판, 60_000)
    admin_client.post(f"/budget/categories/{cid}/update?retreat_id={rid}",
                      data={"level1": "홍보", "level2": "현수막", "planned_amount": "80000"})
    with app_session() as db:
        c = db.get(models.BudgetCategory, cid)
        e = db.get(models.ExpenseEntry, eid)
        assert (c.level2, c.planned_amount) == ("현수막", 80_000)
        assert e.budget_category_id == cid and e.amount == 60_000, "지출이 흔들렸다"
        # 지출 쪽에 등록 때 복사한 시트 칸(level2)은 따라가지 않는다 — 봐둘것 BB-g 에 적었다
        assert e.level2 == "포스터"
        s = B.build_budget_summary(db, retreat=db.get(models.Retreat, rid))
        row = next(r for r in s.categories if r.category.id == cid)
        assert (row.planned, row.spent) == (80_000, 60_000)
    # 지출 화면의 묶음 머리는 항목의 지금 이름을 따른다
    assert "홍보 &gt; 현수막" in admin_client.get(f"/expenses?retreat_id={rid}").text


# ── 다) 수입 고치기 ──


def test47_d01_수입을_고친다(client, admin_client, 판):
    rid, iid = 판["retreat"], 판["income"]
    assert admin_client.post(f"/budget/incomes/{iid}/update?retreat_id={rid}",
                             data={"name": "수련회비(조정)", "unit_price": "50000", "headcount": "30",
                                   "amount": "1", "note": "고친 비고"}, follow_redirects=True).status_code == 200
    with app_session() as db:
        i = db.get(models.IncomeItem, iid)
        # 단가 × 명수가 있으면 그것이 금액이다 — 등록과 같은 domain 함수
        assert (i.name, i.amount, i.note) == ("수련회비(조정)", B.income_amount_of(50_000, 30, 1), "고친 비고")
    log = _마지막기록("수입_수정")
    assert log.before_value["amount"] == 1_000_000 and log.after_value["name"] == "수련회비(조정)"
    assert admin_client.post(f"/budget/incomes/{iid}/update?retreat_id={rid}",
                             data={"name": " ", "amount": "1"}).status_code == 400
    # 총무팀만
    make_user("가명수입리더", "01066660002", "dept_lead", dept=판["dept"])
    login_as(client, "01066660002")
    assert client.post(f"/budget/incomes/{iid}/update?retreat_id={rid}",
                       data={"name": "리더", "amount": "1"}).status_code == 403


# ── 라) 계좌를 가르는 규칙은 domain/budget.py 하나 ──


def test47_e01_계좌_가르기_규칙(판):
    assert B.split_account("국민 123-45 ", "가명") == ("국민", "123-45", "가명")
    assert B.split_account("  신한   110-222-333  ", None) == ("신한", "110-222-333", None)
    assert B.split_account("110222333", "가명") == (None, "110222333", "가명")
    assert B.split_account("", "가명") == (None, None, "가명")


def _가르는곳들(tree) -> list[tuple[str, int]]:
    """계좌를 가르는 자리 — **계좌 칸에 값을 넣는 함수 안에서 split/partition 을 부르면서
    `split_account` 는 안 부르는 곳**, 그리고 이름에 account·계좌가 든 함수 안의 split/partition.
    받는 쪽 변수 이름은 안 본다(한글 이름·text 같은 흔한 이름이라 못 가른다)."""
    계좌칸 = {"payer_bank", "payer_account_number", "payer_account_holder",
             "bank_name", "account_number", "account_holder"}
    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        가른다 = [n for n in calls if isinstance(n.func, ast.Attribute)
                 and n.func.attr in ("split", "partition", "rsplit", "rpartition")]
        if not 가른다:
            continue
        이름에계좌 = "account" in fn.name.lower() or "계좌" in fn.name
        넣는다 = any((isinstance(n, ast.keyword) and n.arg in 계좌칸)
                  or (isinstance(n, ast.Attribute) and n.attr in 계좌칸 and isinstance(n.ctx, ast.Store))
                  or (isinstance(n, ast.Constant) and n.value in 계좌칸)
                  for n in ast.walk(fn))
        부른다 = any(isinstance(n.func, (ast.Name, ast.Attribute))
                  and getattr(n.func, "id", getattr(n.func, "attr", None)) == "split_account" for n in calls)
        if 이름에계좌 or (넣는다 and not 부른다):
            found.append((fn.name, 가른다[0].lineno))
    return found


def test47_e02_계좌를_가르는_코드는_한_곳뿐이다():
    """코드에서 끌어낸다 — app · scripts · seed 전부에서 계좌를 가르는 자리를 찾아
    `budget.split_account` 하나만 나오는지 본다."""
    볼것 = list((ROOT / "app").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")) + [ROOT / "seed.py"]
    찾음 = []
    for path in 볼것:
        for name, line in _가르는곳들(ast.parse(path.read_text(encoding="utf-8"))):
            찾음.append((path.name, name))
    # ③ 검사가 볼 것을 실제로 보는가 — 정본이 잡혀야 한다(0 이면 아무것도 안 본 것이다)
    assert ("budget.py", "split_account") in 찾음, 찾음
    assert 찾음 == [("budget.py", "split_account")], f"계좌를 가르는 자리가 둘이다: {찾음}"
    # 막혀야 할 것 — 들여오기 스크립트가 규칙을 다시 적는 모양 둘을 같은 함수로 심는다
    for 심은것 in (
        "def 들여온다(줄):\n    은행, _, 번호 = 줄['계좌'].partition(' ')\n    return Entry(payer_bank=은행, payer_account_number=번호)\n",
        "def load(row, e):\n    parts = row.split(' ', 1)\n    e.payer_bank = parts[0]\n",
    ):
        assert _가르는곳들(ast.parse(심은것)), 심은것
    # 막히면 안 되는 것 — split_account 를 부르며 계좌 칸에 넣는 자리
    assert not _가르는곳들(ast.parse(
        "def 들여온다(줄):\n    이름 = 줄['지출자'].split(',')[0]\n"
        "    b, n, h = split_account(줄['계좌'], 이름)\n    return Entry(payer_bank=b)\n"))


# ── 마) 내 정보의 계좌를 바꾸면 칸 이름만 남는다 ──


def test47_f01_내_정보_계좌를_바꾸면_칸_이름만_기록(admin_client, 판):
    admin_client.post("/me/update", data={"name": "총무 김간사", "bank_name": 은행,
                                           "account_number": 번호, "account_holder": 예금주})
    log = _마지막기록("내정보_수정")
    assert log is not None and "account_number" in log.summary
    글 = f"{log.summary} {log.before_value} {log.after_value}"
    for 값 in (은행, 번호, 예금주):
        assert 값 not in 글
    with app_session() as db:
        n = len(db.scalars(select(models.ActivityLog).where(models.ActivityLog.action == "내정보_수정")).all())
    admin_client.post("/me/update", data={"name": "총무 김간사", "bank_name": 은행,
                                           "account_number": 번호, "account_holder": 예금주})
    with app_session() as db:
        assert len(db.scalars(select(models.ActivityLog).where(models.ActivityLog.action == "내정보_수정")).all()) == n


# ── 커밋 전 검토가 짚은 것 — 돈 셈 · 기록 · 리더의 지출자 · 취소된 예산 항목 ──


def test47_g01_비고만_고치면_지원금액을_다시_세지_않는다(admin_client, 판):
    rid = 판["retreat"]
    eid = _등록(admin_client, 판, 100_000, is_meal_expense="1", meal_headcount="5")
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        assert e.subsidy_amount == 40_000
        # ㄱ 회차 상한이 바뀐 뒤
        db.get(models.Retreat, rid).meal_subsidy_per_person = 5_000
        # ㄴ 인원이 빈 채 손으로 적은 지원금액(들여온 줄의 모양)
        손 = models.ExpenseEntry(retreat_id=rid, department_id=판["dept"], amount=90_000,
                                 subsidy_amount=72_000, personal_burden_amount=18_000,
                                 is_meal_expense=True, meal_headcount=None, expense_date=TODAY)
        db.add(손)
        db.commit()
        손id = 손.id
    _고침(admin_client, 판, eid, note="비고만")
    _고침(admin_client, 판, 손id, note="비고만")
    with app_session() as db:
        assert db.get(models.ExpenseEntry, eid).subsidy_amount == 40_000, "상한이 바뀐 뒤 비고만 고쳤는데 다시 셌다"
        assert (db.get(models.ExpenseEntry, 손id).subsidy_amount,
                db.get(models.ExpenseEntry, 손id).personal_burden_amount) == (72_000, 18_000)
    # 인원을 고치면 그때 다시 센다(지금 상한으로)
    _고침(admin_client, 판, eid, meal_headcount=4)
    with app_session() as db:
        assert db.get(models.ExpenseEntry, eid).subsidy_amount == 20_000
    log = _마지막기록("지출_수정")
    assert log.before_value["subsidy_amount"] == 40_000 and log.after_value["subsidy_amount"] == 20_000
    # 인원이 빈 식대 줄의 금액을 바꾸면 0 으로 떨어뜨리지 않고 400
    assert _고침(admin_client, 판, 손id, amount=95_000).status_code == 400
    with app_session() as db:
        assert db.get(models.ExpenseEntry, 손id).amount == 90_000
    # 숫자가 아닌 인원은 500 이 아니라 400
    assert _고침(admin_client, 판, eid, meal_headcount="x").status_code == 400


def test47_g02_예산_항목과_수입도_바뀐_칸만_기록한다(admin_client, 판):
    rid, cid, iid = 판["retreat"], 판["c2"], 판["income"]
    admin_client.post(f"/budget/categories/{cid}/update?retreat_id={rid}",
                      data={"level1": "식비", "level2": "야식", "unit_price": "4000", "headcount": "50",
                            "times": "2", "planned_amount": "0"})
    log = _마지막기록("예산항목_수정")
    assert set(log.after_value) == {"planned_amount", "unit_price", "headcount", "times"}, log.after_value
    assert log.after_value["planned_amount"] == B.planned_amount_of(4000, 50, 2, 0)
    admin_client.post(f"/budget/incomes/{iid}/update?retreat_id={rid}",
                      data={"name": "수련회비", "amount": "1000000", "note": "비고만"})
    log = _마지막기록("수입_수정")
    assert log.after_value == {"note": "비고만"} and log.before_value == {"note": None}
    # 안 바뀌면 기록을 안 남긴다
    with app_session() as db:
        n = len(db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action.in_(("예산항목_수정", "수입_수정")))).all())
    admin_client.post(f"/budget/incomes/{iid}/update?retreat_id={rid}",
                      data={"name": "수련회비", "amount": "1000000", "note": "비고만"})
    admin_client.post(f"/budget/categories/{cid}/update?retreat_id={rid}",
                      data={"level1": "식비", "level2": "야식", "unit_price": "4000", "headcount": "50",
                            "times": "2", "planned_amount": "0"})
    with app_session() as db:
        assert len(db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action.in_(("예산항목_수정", "수입_수정")))).all()) == n


def test47_g03_계좌를_못_보는_사람은_계좌_적힌_지출의_지출자를_못_바꾼다(client, admin_client, 판):
    rid = 판["retreat"]
    있음 = _등록(admin_client, 판, 3_000, payer_bank=은행, payer_account_number=번호)
    없음 = _등록(admin_client, 판, 3_000)
    make_user("가명지출자리더", "01066660003", "dept_lead", dept=판["dept"])
    login_as(client, "01066660003")
    assert _고침(client, 판, 있음, payer_name="다른사람").status_code == 400
    with app_session() as db:
        assert db.get(models.ExpenseEntry, 있음).payer_name == "가명지출자"
    # 계좌가 빈 지출은 리더가 지출자와 계좌를 함께 적을 수 있다(등록 폼과 같은 결)
    assert _고침(client, 판, 없음, payer_name="다른사람", payer_bank=은행,
               payer_account_number=번호).status_code in (200, 303)
    with app_session() as db:
        e = db.get(models.ExpenseEntry, 없음)
        assert (e.payer_name, e.payer_bank, e.payer_account_number) == ("다른사람", 은행, 번호)


def test47_g04_취소된_예산_항목에_걸린_지출(admin_client, 판):
    rid = 판["retreat"]
    eid = _등록(admin_client, 판, 5_000)                                   # c1 에 걸림
    admin_client.post(f"/budget/categories/{판['c1']}/cancel?retreat_id={rid}")
    # 같은 항목 그대로 두고 다른 칸을 고치는 것은 된다
    assert _고침(admin_client, 판, eid, note="취소된 항목에 머묾").status_code in (200, 303)
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        assert (e.budget_category_id, e.note) == (판["c1"], "취소된 항목에 머묾")
    # 다른 지출을 취소된 항목으로 옮기는 것은 400
    e2 = _등록(admin_client, 판, 6_000, budget_category_id=판["c2"])
    assert _고침(admin_client, 판, e2, budget_category_id=판["c1"]).status_code == 400
    with app_session() as db:
        assert db.get(models.ExpenseEntry, e2).budget_category_id == 판["c2"]
    # 화면 — 그 지출은 취소된 항목 아래에 그대로 서고 머리가 그렇게 말한다.
    # **선택지에서는 빠진다**(7-3) — 편집 상태의 목록은 산 항목뿐이라 그리로
    # 새로 옮길 수 없다. 서버도 400 으로 막는다(위)
    page = admin_client.get(f"/expenses?retreat_id={rid}").text
    assert "취소된 예산 항목" in page
    # **선택지에서 빠졌는지를 실제로 잰다** (2026-09-26 두 번째 검토 [9]) —
    # 전에는 그 말이 주석에만 있어, 화면이 취소된 항목을 다시 실어도 아무것도
    # 안 빨개졌다. 고를 목록은 서버가 한 번 실어 보내는 그 씨앗 하나다
    import json as _json
    씨앗 = re.search(r'<script id="exp-cats"[^>]*>(.*?)</script>', page, re.S)
    ids = [c["id"] for c in _json.loads(씨앗.group(1))]
    assert 판["c1"] not in ids, "취소된 예산 항목이 선택지에 남았다"
    assert 판["c2"] in ids, "산 항목이 선택지에서 빠졌다"
