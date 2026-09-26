"""4단계 — 지출 화면 (CLAUDE.md 7-4 · 2026-09-26 사람이 정한 확정본).

- 예산 화면과 **같은 편집 방식**(전체 편집 하나) · 저장은 `POST /expenses/bulk`
- 「금액」 → **영수증 금액** · 인원수 칩 없음
- 예산 항목 칸 + 세부항목-2(병합) + 세부항목-3(그 묶음에 없으면 가로로 합침)
- 긴 내용(명단 · 비고)은 `…` 로 줄이고 **팝업에서 고쳐 저장**한다
- 인원은 **명단 이름 수**다 (7-2)

**막는 쪽을 실제로 만들어 잰다**(11-3) — 걸리는 줄을 섞어 보내고 아무것도 안
바뀌었는지, 안 보낸 칸(비고 · 인원)이 **안 덮이는지**, 남의 부서 줄이 막히는지.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from sqlalchemy import select

from app import models
from tests.conftest import app_session, login_as, make_user

TODAY = dt.date.today()
ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def 지출(admin_client):
    """예산 항목 둘 · 같은 세부항목-2 가 이어진 줄 둘(병합이 실제로 서야 한다) · 식대 하나."""
    with app_session() as db:
        retreat = models.Retreat(
            name="지출 시험 회차", meal_subsidy_per_person=8000,
            start_date=TODAY + dt.timedelta(days=30), end_date=TODAY + dt.timedelta(days=32))
        db.add(retreat)
        db.flush()
        a = models.BudgetCategory(retreat_id=retreat.id, level1="홍보", level2="인쇄물",
                                  level3="포스터", planned_amount=300_000, sort_order=1)
        c = models.BudgetCategory(retreat_id=retreat.id, level1="식비", level2="본행사",
                                  planned_amount=500_000, sort_order=2)
        db.add_all([a, c])
        db.commit()
        rid, aid, cid = retreat.id, a.id, c.id

    def 등록(**kw):
        data = {"expense_date": TODAY.isoformat(), "amount": "10000",
                "payer_name": "수련회계좌"}
        data.update(kw)
        r = admin_client.post(f"/expenses/create?retreat_id={rid}", data=data,
                              follow_redirects=True)
        assert r.status_code == 200

    등록(budget_category_id=str(aid), level3b="포스터 인쇄", amount="30000")
    등록(budget_category_id=str(aid), level3b="포스터 인쇄", amount="20000")
    등록(budget_category_id=str(cid), level3b="식사", amount="60000",
        is_meal_expense="1", meal_attendees="가 나 다 라")
    with app_session() as db:
        ids = [e.id for e in db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == rid).order_by(models.ExpenseEntry.id))]
    return {"retreat": rid, "a": aid, "c": cid, "ids": ids}


def _줄(e, **kw):
    줄 = {"id": e.id,
          "expense_date": e.expense_date.isoformat() if e.expense_date else "",
          "amount": e.amount,
          "budget_category_id": str(e.budget_category_id or ""),
          "level3b": e.level3b or "",
          "payer_name": e.payer_name or "",
          "payer_bank": "", "payer_account_number": "", "payer_account_holder": "",
          "paid": bool(e.paid)}
    줄.update(kw)
    return 줄


def _줄들(rid, **kw):
    with app_session() as db:
        return [_줄(e, **kw) for e in db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == rid).order_by(models.ExpenseEntry.id))]


# ── ㄱ. 표 모양 ────────────────────────────────────────────────────


def test74_a01_머리는_영수증_금액이고_인원수_칩이_없다(admin_client, 지출):
    page = admin_client.get(f"/expenses?retreat_id={지출['retreat']}").text
    assert "영수증 금액" in page
    assert "mealchip" not in page, "인원수 칩이 남았다"


def test74_a02_세부항목_2_는_이어진_같은_값끼리_병합된다(admin_client, 지출):
    page = admin_client.get(f"/expenses?retreat_id={지출['retreat']}").text
    assert 'class="l3b" rowspan="2"' in page
    # 세부항목-3 이 하나도 없는 묶음은 가로로 합친다
    assert 'colspan="2"' in page


def test74_a03_세부묶음은_도메인_한_곳에서_묶는다():
    from app.domain.budget import 세부묶음

    class 가짜:
        note = None
        is_meal_expense = False
        meal_attendee_names = None

        def __init__(self, b, c=None):
            self.level3b, self.level3c = b, c

    묶음 = 세부묶음([가짜("가"), 가짜("가"), 가짜("나", "n"), 가짜("가")])
    assert [len(b["entries"]) for b in 묶음] == [2, 1, 1], "떨어진 같은 이름을 붙였다"
    assert [b["has_l3c"] for b in 묶음] == [False, True, False]
    # 병합에 쓰는 것은 **그려질 줄 수**다 — 긴 내용이 없으면 지출 수와 같다
    assert [b["rows"] for b in 묶음] == [2, 1, 1]


def test74_a04_긴_내용은_줄여_놓고_팝업이_전체를_든다(admin_client, 지출):
    page = admin_client.get(f"/expenses?retreat_id={지출['retreat']}").text
    assert 'class="longcell"' in page and 'data-full="가 나 다 라"' in page


# ── ㄴ. 팝업에서 고치는 것 ─────────────────────────────────────────


def test74_b01_명단을_고치면_인원과_지원금액이_따라_움직인다(admin_client, 지출):
    rid = 지출["retreat"]
    with app_session() as db:
        식대 = db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == rid,
            models.ExpenseEntry.is_meal_expense.is_(True))).one()
        eid, 전지원 = 식대.id, 식대.subsidy_amount
    r = admin_client.post(f"/expenses/{eid}/long?retreat_id={rid}",
                          data={"kind": "attendees", "value": "가 나"})
    assert r.status_code == 200
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        assert e.meal_headcount == 2, "인원은 이름 수다"
        assert e.subsidy_amount == min(e.amount, 2 * 8000)
        assert e.subsidy_amount != 전지원


def test74_b02_비고는_팝업에서_고친다(admin_client, 지출):
    rid, eid = 지출["retreat"], 지출["ids"][0]
    assert admin_client.post(f"/expenses/{eid}/long?retreat_id={rid}",
                             data={"kind": "note", "value": "견적 두 곳"}).status_code == 200
    with app_session() as db:
        assert db.get(models.ExpenseEntry, eid).note == "견적 두 곳"


def test74_b03_고칠_수_없는_칸은_거절한다(admin_client, 지출):
    rid, eid = 지출["retreat"], 지출["ids"][0]
    assert admin_client.post(f"/expenses/{eid}/long?retreat_id={rid}",
                             data={"kind": "amount", "value": "1"}).status_code == 400
    # 식대가 아닌 지출에는 명단이 없다
    assert admin_client.post(f"/expenses/{eid}/long?retreat_id={rid}",
                             data={"kind": "attendees", "value": "가"}).status_code == 400


def test74_b04_계좌는_이름_팝업이_들고_목록에는_안_선다(admin_client, 지출):
    rid, eid = 지출["retreat"], 지출["ids"][0]
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        e.payer_name = "박민준"
        e.payer_bank = "국민"
        e.payer_account_number = "123-4567-8901"
        db.commit()
    page = admin_client.get(f"/expenses?retreat_id={rid}").text
    assert 'class="payer acct"' in page and 'data-no="123-4567-8901"' in page
    assert 'class="acct-no"' not in page


# ── ㄷ. 전체 편집 — 한 번에 저장되고, 걸리면 아무것도 안 바뀐다 ──────


def test74_c01_표_전체를_한_번에_저장한다(admin_client, 지출):
    rid = 지출["retreat"]
    줄들 = _줄들(rid)
    for 줄 in 줄들:
        줄["amount"] += 1000
        줄["level3b"] = (줄["level3b"] or "") + " 고침"
        줄["paid"] = True
    r = admin_client.post(f"/expenses/bulk?retreat_id={rid}", json={"rows": 줄들, "removed": []})
    assert r.status_code == 200, r.text
    with app_session() as db:
        for 줄 in 줄들:
            e = db.get(models.ExpenseEntry, 줄["id"])
            assert e.amount == 줄["amount"] and e.paid is True
            assert e.level3b.endswith("고침")
            assert e.paid_date == TODAY


def test74_c02_안_보낸_칸은_안_고친다(admin_client, 지출):
    """비고와 인원은 이 표에서 안 고치는 칸이다 — 보내면 빈 글자로 덮인다."""
    rid, eid = 지출["retreat"], 지출["ids"][0]
    admin_client.post(f"/expenses/{eid}/long?retreat_id={rid}",
                      data={"kind": "note", "value": "남아 있어야 한다"})
    with app_session() as db:
        식대 = db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == rid,
            models.ExpenseEntry.is_meal_expense.is_(True))).one()
        전 = (식대.id, 식대.meal_headcount, 식대.subsidy_amount)
    assert admin_client.post(f"/expenses/bulk?retreat_id={rid}",
                             json={"rows": _줄들(rid), "removed": []}).status_code == 200
    with app_session() as db:
        assert db.get(models.ExpenseEntry, eid).note == "남아 있어야 한다"
        e = db.get(models.ExpenseEntry, 전[0])
        assert (e.meal_headcount, e.subsidy_amount) == 전[1:], "식대 인원이 흔들렸다"


def test74_c03_걸리는_줄이_있으면_아무것도_안_바뀐다(admin_client, 지출):
    rid = 지출["retreat"]
    줄들 = _줄들(rid)
    with app_session() as db:
        전 = {e.id: e.amount for e in db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == rid))}
    for 줄 in 줄들:
        줄["amount"] += 500
    줄들[-1]["amount"] = -1                      # 마지막 줄이 걸린다
    r = admin_client.post(f"/expenses/bulk?retreat_id={rid}", json={"rows": 줄들, "removed": []})
    assert r.status_code == 400
    with app_session() as db:
        for eid, 금액 in 전.items():
            assert db.get(models.ExpenseEntry, eid).amount == 금액, "절반만 저장됐다"


def test74_c04_취소는_행을_안_지운다(admin_client, 지출):
    rid, eid = 지출["retreat"], 지출["ids"][0]
    assert admin_client.post(f"/expenses/bulk?retreat_id={rid}",
                             json={"rows": [], "removed": [eid]}).status_code == 200
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        assert e is not None and e.canceled_at is not None


def test74_c05_이미_취소된_줄은_묶음_저장으로도_못_고친다(admin_client, 지출):
    rid, eid = 지출["retreat"], 지출["ids"][0]
    admin_client.post(f"/expenses/bulk?retreat_id={rid}", json={"rows": [], "removed": [eid]})
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        줄 = _줄(e, amount=e.amount + 1)
    r = admin_client.post(f"/expenses/bulk?retreat_id={rid}", json={"rows": [줄], "removed": []})
    assert r.status_code == 409


def test74_c06_두_번_보내도_같은_모양이다(admin_client, 지출):
    rid = 지출["retreat"]
    줄들 = _줄들(rid)
    admin_client.post(f"/expenses/bulk?retreat_id={rid}", json={"rows": 줄들, "removed": []})
    with app_session() as db:
        n1 = len(list(db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == rid))))
    admin_client.post(f"/expenses/bulk?retreat_id={rid}", json={"rows": 줄들, "removed": []})
    with app_session() as db:
        assert len(list(db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == rid)))) == n1


def test74_c07_남의_부서_줄은_묶음_저장으로도_못_고친다(client, 지출):
    rid = 지출["retreat"]
    with app_session() as db:
        dept = models.Department(retreat_id=rid, key="sketch", name="4 스케치",
                                 color_tag="#B95A83", sort_order=9)
        남 = models.Department(retreat_id=rid, key="hebron", name="5 헤브론",
                              color_tag="#4A8A5C", sort_order=8)
        db.add_all([dept, 남])
        db.flush()
        did, 남id = dept.id, 남.id
        e = db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == rid)).first()
        e.department_id = 남id
        eid, 금액 = e.id, e.amount
        db.commit()
    사람 = make_user("스케치 리더", "010-7777-0003", "dept_lead", dept=did)
    login_as(client, 사람)
    with app_session() as db:
        줄 = _줄(db.get(models.ExpenseEntry, eid), amount=금액 + 1)
    r = client.post(f"/expenses/bulk?retreat_id={rid}", json={"rows": [줄], "removed": []})
    assert r.status_code in (400, 403)
    with app_session() as db:
        assert db.get(models.ExpenseEntry, eid).amount == 금액


def test74_c08_저장은_기록에_남는다(admin_client, 지출):
    rid = 지출["retreat"]
    줄들 = _줄들(rid)
    줄들[0]["amount"] += 100
    admin_client.post(f"/expenses/bulk?retreat_id={rid}", json={"rows": 줄들, "removed": []})
    with app_session() as db:
        표 = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "지출표_저장")).all()
        줄 = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "지출_수정")).all()
        assert 표 and 줄, "활동 기록이 없다"


# ── ㄹ. 한 벌인지 (규칙이 두 벌이 되면 갈린다) ───────────────────────


def test74_d01_줄마다_고치기와_묶음_저장이_같은_함수를_지난다():
    src = (ROOT / "app" / "routers" / "expenses.py").read_text(encoding="utf-8")
    assert src.count("def 한줄을_고친다(") == 1
    # 부르는 곳은 둘뿐이다 — 줄마다 고치기와 묶음 저장
    assert src.count("한줄을_고친다(") == 3   # 정의 하나 + 부르는 곳 둘


def test74_d02_전체_편집_단추와_저장_길이_하나다(admin_client, 지출):
    page = admin_client.get(f"/expenses?retreat_id={지출['retreat']}").text
    assert 'id="expedit"' in page and 'id="expsave"' in page
    본문 = page.split("<tbody>")[1]
    assert 'class="rowedit"' not in 본문, "줄마다 펴는 폼이 남았다"
    js = (ROOT / "app" / "static" / "js" / "expedit.js").read_text(encoding="utf-8")
    # 보내는 자리는 하나다 — 머리 주석이 그 길을 적어 두므로 두 번 나온다
    assert js.count("fetch('/expenses/bulk'") == 1


def test74_d03_열람_전용에게는_편집도_첨부도_없다(client, 지출):
    사람 = make_user("열람 사람", "010-7777-0004", "viewer")
    login_as(client, 사람)
    page = client.get(f"/expenses?retreat_id={지출['retreat']}").text
    assert 'id="expedit"' not in page and 'exp-cats' not in page
    assert 'class="rcptadd"' not in page


def test74_d04_인원_칸은_등록_폼에도_없다(admin_client, 지출):
    page = admin_client.get(f"/expenses?retreat_id={지출['retreat']}").text
    assert 'name="meal_headcount"' not in page, "인원 칸이 남았다 (7-2)"
    assert 'name="meal_attendees"' in page


# ── ㅅ. 커밋 전 검토가 잡은 자리 (2026-09-26) ─────────────────────


def _칸격자(page: str) -> list[int]:
    """표의 줄마다 **오른쪽 끝이 몇 번째 칸인지** 를 센다 (rowspan · colspan 반영).

    병합 수가 실제 줄 수와 어긋나면 그 아래가 통째로 밀리는데, 화면에는
    「칸이 왼쪽으로 붙었다」 로만 보이고 아무 오류도 안 난다 — pytest 가 볼 수
    있는 자리라 여기서 잰다.
    """
    import re

    body = re.search(r"<tbody>(.*?)</tbody>", page, re.S).group(1)
    찬칸: dict[int, int] = {}          # 열 → 몇 줄 더 차 있나
    끝 = []
    for 줄 in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        열 = 0
        for m in re.finditer(r"<t[dh]([^>]*)>", 줄):
            while 찬칸.get(열, 0) > 0:
                열 += 1
            cs = re.search(r'colspan="(\d+)"', m.group(1))
            rs = re.search(r'rowspan="(\d+)"', m.group(1))
            폭, 높 = int(cs.group(1)) if cs else 1, int(rs.group(1)) if rs else 1
            for i in range(폭):
                찬칸[열 + i] = 높
            열 += 폭
        while 찬칸.get(열, 0) > 0:
            열 += 1
        끝.append(열)
        for k in list(찬칸):
            찬칸[k] -= 1
    return 끝


def test74_g01_긴_내용_줄이_사이에_껴도_칸이_안_밀린다(admin_client, 지출):
    """병합은 **그려질 줄 수**를 세야 한다 (검토 [C] · `budget.긴줄인가`)."""
    with app_session() as db:
        e = db.get(models.ExpenseEntry, 지출["ids"][0])   # 묶음의 **첫 줄**에 비고
        e.note = "영수증 뒷면 참조"
        db.commit()
    page = admin_client.get(f"/expenses?retreat_id={지출['retreat']}").text
    끝 = _칸격자(page)
    assert 끝, "표가 안 그려졌다"
    assert len(set(끝)) == 1, f"줄마다 칸 수가 다르다: {끝}"


def test74_g02_안_보낸_세부항목2는_안_지워진다(admin_client, 지출):
    """병합 때문에 입력칸이 없는 줄이 있다 — 그 줄이 값을 지우면 안 된다 (검토 [B])."""
    줄들 = _줄들(지출["retreat"])
    for 줄 in 줄들:
        줄.pop("level3b")                     # 화면의 둘째 줄부터가 이 모양이다
    r = admin_client.post(f"/expenses/bulk?retreat_id={지출['retreat']}",
                          json={"rows": 줄들, "removed": []})
    assert r.status_code == 200
    with app_session() as db:
        남은 = [e.level3b for e in db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == 지출["retreat"]).order_by(models.ExpenseEntry.id))]
    assert 남은 == ["포스터 인쇄", "포스터 인쇄", "식사"], f"세부항목-2 가 지워졌다: {남은}"


def test74_g03_비고만_고쳐도_식대_지원금액이_안_움직인다(admin_client, 지출):
    """인원과 명단이 어긋난 옛 줄이 있다 — 여기서 이름 수로 덮으면 **돈이 바뀐다** (검토 [G])."""
    식대 = 지출["ids"][2]
    with app_session() as db:
        e = db.get(models.ExpenseEntry, 식대)
        e.meal_headcount = 12                 # 이름은 넷인데 인원은 열둘 (옛 폼이 따로 받던 시절)
        e.subsidy_amount, e.personal_burden_amount = 60_000, 0
        db.commit()
        전 = (e.meal_headcount, e.subsidy_amount)
    줄들 = _줄들(지출["retreat"])
    r = admin_client.post(f"/expenses/bulk?retreat_id={지출['retreat']}",
                          json={"rows": 줄들, "removed": []})
    assert r.status_code == 200
    with app_session() as db:
        e = db.get(models.ExpenseEntry, 식대)
        assert (e.meal_headcount, e.subsidy_amount) == 전, "지원금액이 조용히 바뀌었다"


def test74_g04_묶음_저장의_취소도_줄마다_기록에_남는다(admin_client, 지출):
    """같은 일을 하는 `/cancel` 과 **같은 이름으로** 남는다 (검토 [J] · 0장)."""
    눌린 = 지출["ids"][1]
    줄들 = [줄 for 줄 in _줄들(지출["retreat"]) if 줄["id"] != 눌린]
    r = admin_client.post(f"/expenses/bulk?retreat_id={지출['retreat']}",
                          json={"rows": 줄들, "removed": [눌린]})
    assert r.status_code == 200
    with app_session() as db:
        logs = list(db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "지출_취소")))
    assert [x.target_id for x in logs] == [눌린], "취소가 줄마다 안 남았다"


# ── ㅇ. 두 번째 검토가 잡은 자리 (2026-09-26) ────────────────────


def test74_h01_식대는_명단이_비어도_넣을_자리가_선다(admin_client, 지출):
    """인원을 넣는 길이 그 팝업뿐이다 (검토 [1] · 7-2).

    이름이 있을 때만 그리면 **인원이 빈 식대 줄은 금액도 못 고친다**
    (`한줄을_고친다` 가 400 으로 막는다). 비면 「명단 없음」 으로 선다.
    """
    with app_session() as db:
        e = db.get(models.ExpenseEntry, 지출["ids"][2])
        assert e.is_meal_expense
        e.meal_attendee_names = None
        e.meal_headcount = None
        db.commit()
    page = admin_client.get(f"/expenses?retreat_id={지출['retreat']}").text
    assert 'data-long="attendees"' in page and "명단 없음" in page, "명단 자리가 안 섰다"
    # 그 자리로 이름을 넣으면 인원과 지원금액이 따라온다
    r = admin_client.post(f"/expenses/{지출['ids'][2]}/long?retreat_id={지출['retreat']}",
                          data={"kind": "attendees", "value": "가 나 다"})
    assert r.status_code in (200, 303)
    with app_session() as db:
        e = db.get(models.ExpenseEntry, 지출["ids"][2])
        assert e.meal_headcount == 3 and e.subsidy_amount > 0


def test74_h02_빈_글자는_여전히_지우라는_뜻이다(admin_client, 지출):
    """「안 보냄」 과 「비웠다」 를 가르는 자리다 (검토 [3] · 막는 쪽의 반대편).

    `test74_g02` 가 「안 보내면 안 고친다」 를 재고, 이것이 그 짝이다 —
    둘 중 하나만 있으면 누가 「빈 글자도 그대로로 본다」 로 바꿔도 안 빨개진다.
    """
    줄들 = _줄들(지출["retreat"])
    for 줄 in 줄들:
        줄["level3b"] = ""
    r = admin_client.post(f"/expenses/bulk?retreat_id={지출['retreat']}",
                          json={"rows": 줄들, "removed": []})
    assert r.status_code == 200
    with app_session() as db:
        남은 = [e.level3b for e in db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == 지출["retreat"]))]
    assert 남은 == [None, None, None], f"빈 글자가 「그대로」 로 읽혔다: {남은}"


def test74_h03_병합된_세부항목2는_묶음_전체가_따라온다(admin_client, 지출):
    """화면이 실제로 보내는 몸으로 잰다 (검토 [2]).

    병합된 칸은 **묶음의 첫 줄에만** 입력칸이 있다. 그 줄만 고쳐 보내면
    나머지가 옛 이름으로 남아 **묶음이 쪼개진다** — 예산 화면이 같은 자리에서
    이미 막고 있는 것이다.
    """
    줄들 = _줄들(지출["retreat"])
    포스터 = [줄 for 줄 in 줄들 if 줄["level3b"] == "포스터 인쇄"]
    assert len(포스터) == 2, "병합된 묶음이 안 섰다"
    for 줄 in 포스터:                       # 화면의 JS 가 묶음값을 함께 싣는다
        줄["level3b"] = "포스터 재인쇄"
    r = admin_client.post(f"/expenses/bulk?retreat_id={지출['retreat']}",
                          json={"rows": 줄들, "removed": []})
    assert r.status_code == 200
    with app_session() as db:
        이름 = [e.level3b for e in db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == 지출["retreat"]).order_by(models.ExpenseEntry.id))]
    assert 이름[:2] == ["포스터 재인쇄", "포스터 재인쇄"], f"묶음이 쪼개졌다: {이름}"
    # 화면 쪽 — 묶음의 값을 나머지 줄에도 싣는 코드가 있는가
    js = (ROOT / "app" / "static" / "js" / "expedit.js").read_text(encoding="utf-8")
    assert "묶음값" in js and "dataset.blk" in js, "첫 줄만 보내는 옛 모양이다"


def test74_h04_긴_내용_칸의_권한은_그_지출_줄에서_본다():
    """긴 내용 칸은 **지출 줄 안에 없다** — 아래에 따로 서는 줄에 있다.

    `closest('tr[data-exp]')` 로만 찾으면 그 자리는 늘 `null` 이라 권한
    판정이 통째로 새고, 편집 중 막기(검토 [I])가 **안 걸린다** —
    2026-09-26 화면 점검이 실제로 그것을 잡았다(봐둘것 BJ-i).

    **낱말만 잰다** — 동작은 `docs/checks/fin.js` 의 갈래 ⑭ 가 잰다(브라우저에서만
    일어나는 일이다 · 10장). 여기서 보는 것은 **그 판정이 한 자리에 있는가** 다.
    """
    js = (ROOT / "app" / "static" / "js" / "exppop.js").read_text(encoding="utf-8")
    assert "function 그줄(" in js, "어느 지출 줄인지 찾는 자리가 없다"
    assert "tr.longrow" in js and "dataset.of" in js, "긴 내용 줄을 안 거친다"
    # 옛 모양(그 줄에서 바로 closest)이 판정에 남아 있지 않다
    판정 = [줄 for 줄 in js.splitlines() if "고칠수있는줄" in 줄 and "=" in 줄]
    assert 판정 and all("closest('tr[data-exp]')" not in 줄 for 줄 in 판정),         f"권한 판정이 아직 지출 줄만 본다: {판정}"


def test74_h05_긴_내용_칸이_그_지출_줄을_가리킨다(admin_client, 지출):
    """화면 쪽 — 긴 내용 줄이 어느 지출의 것인지 표시가 있어야 찾아간다."""
    with app_session() as db:
        e = db.get(models.ExpenseEntry, 지출["ids"][0])
        e.note = "영수증 뒷면 참조"
        db.commit()
    page = admin_client.get(f"/expenses?retreat_id={지출['retreat']}").text
    assert f'class="longrow" data-of="{지출["ids"][0]}"' in page, "긴 내용 줄에 주인 표시가 없다"
