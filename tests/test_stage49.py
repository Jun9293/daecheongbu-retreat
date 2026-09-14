"""계좌 꼴 게이트 (봐둘것 BB-c · 2026-09-14 · 재정 운영 실행 전 마지막 판).

- 판정은 `domain/budget.py` 의 `account_problem` 하나 — 지출 등록 · 지출 고치기 · 내 정보 · 시트 들여오기가 지난다
- 꼴의 경계는 `app/account_shape.py` 하나 — 게이트와 두 검사(`check_dev_db` · `check_names`)가 같이 본다
- 들여오기 쪽은 `tests/test_stage48.py` 의 c03 이 잰다

계좌·이름은 지어낸 값이다. **실제 계좌 꼴 표본은 「은행 이름 + 숫자와 하이픈 12~14 개」 를 흉내 낸 것이다**
(2026-09-14 시트 64 줄의 모양 · 값은 저장소에 없다).
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import sqlite3

import pytest
from sqlalchemy import select

from app import models
from app.domain import budget as B
from tests.conftest import app_session
from tests.test_stage47 import _고침, _등록, 판  # noqa: F401 — 판 은 fixture

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 시트의 꼴을 흉내 낸 지어낸 계좌 — 하이픈 없는 것 · 둘 · 셋, 숫자 12~14
통과할꼴 = [("지어낸은행", "99912345678901"), ("가명", "999-123-45678901"), ("지어낸새마을", "999-1234-5678-90"),
         ("가명은행", "999-000-000000")]
# (은행, 번호, 예금주) — 막아야 할 꼴
막을꼴 = [
    ("", "999-0000-1111", "가명"),              # 번호만 있고 은행이 빔
    ("지어낸은행", "999-00가-1111", "가명"),       # 글자 섞임
    ("지어낸은행", "999 0000 1111", "가명"),       # 빈칸 섞임
    ("지어낸은행", "-999-0000-1111", "가명"),      # 앞 하이픈
    ("지어낸은행", "999--0000-1111", "가명"),      # 겹친 하이픈
    ("지어낸은행", "999-123", "가명"),             # 숫자가 너무 적음
    ("지어낸은행", "9" * 17, "가명"),              # 숫자가 너무 많음
    ("12345", "999-0000-1111", "가명"),            # 숫자만인 은행
    ("지어낸은행" * 5, "999-0000-1111", "가명"),     # 너무 긴 은행
    ("지어낸은행", "999-0000-1111", "가" * 31),     # 너무 긴 예금주
]


# ── 가) 게이트가 막는 것과 지나는 것 ──


def test49_a01_이상한_꼴은_막고_시트_꼴은_지난다():
    for 은행, 번호, 예금주 in 막을꼴:
        assert B.account_problem(은행, 번호, 예금주), f"막아야 할 꼴이 지났다: {(은행, 번호[:3], len(번호))}"
    for 은행, 번호 in 통과할꼴:
        assert B.account_problem(은행, 번호, "가명예금주") is None
    # 계좌를 안 적은 것은 틀린 것이 아니다
    for 셋 in ((None, None, None), ("", "", ""), ("지어낸은행", "", ""), ("", "", "가명")):
        assert B.account_problem(*셋) is None
    assert B.account_problem(" 지어낸은행 ", " 999-0000-1111 ", " 가명 ") is None, "앞뒤 빈칸은 폼이 뗀다"


def test49_a02_판정은_한_곳이다():
    """계좌 칸에 쓰는 자리가 전부 account_problem 을 부른다 — 규칙을 다시 적은 곳이 없다."""
    for 파일 in ("app/routers/expenses.py", "app/routers/settings.py", "scripts/재정들여오기.py"):
        tree = ast.parse((ROOT / 파일).read_text(encoding="utf-8"))
        assert any(isinstance(n, ast.Call) and getattr(n.func, "id", None) == "account_problem"
                   for n in ast.walk(tree)), f"{파일} 이 게이트를 안 부른다"
        글 = (ROOT / 파일).read_text(encoding="utf-8")
        assert "숫자_최소" not in 글 and "칸꼴" not in 글, f"{파일} 이 꼴을 스스로 적었다"


# ── 다) 폼이 게이트 뒤에도 돈다 ──


def test49_c01_등록은_꼴이_맞으면_저장하고_틀리면_400(admin_client, 판):
    eid = _등록(admin_client, 판, 11_000, payer_bank="지어낸은행", payer_account_number="999-1234-567890",
               payer_account_holder="가명")
    with app_session() as db:
        assert db.get(models.ExpenseEntry, eid).payer_account_number == "999-1234-567890"
    _등록(admin_client, 판, 12_000)                     # 계좌 없이도 된다
    with app_session() as db:
        전 = db.scalar(select(models.ExpenseEntry.id).order_by(models.ExpenseEntry.id.desc()))
    r = admin_client.post(f"/expenses/create?retreat_id={판['retreat']}", data={
        "amount": "17777", "department_id": str(판["dept"]), "payer_name": "가명",
        "payer_bank": "", "payer_account_number": "999-1234-567890"})
    assert r.status_code == 400 and "은행" in r.text
    with app_session() as db:
        assert db.scalar(select(models.ExpenseEntry.id).order_by(models.ExpenseEntry.id.desc())) == 전, "막혔는데 저장됐다"


def test49_c02_고치기는_계좌를_바꿀_때만_꼴을_본다(admin_client, 판):
    eid = _등록(admin_client, 판, 14_000, payer_bank="지어낸은행", payer_account_number="999-1234-567890")
    assert _고침(admin_client, 판, eid, payer_account_number="999-00가-1111").status_code == 400
    assert _고침(admin_client, 판, eid, payer_account_number="999-4321-567890").status_code in (200, 303)
    with app_session() as db:
        assert db.get(models.ExpenseEntry, eid).payer_account_number == "999-4321-567890"
    # 게이트 전에 들어간 옛 값 — 비고 하나 고치는 길은 안 막는다
    with app_session() as db:
        db.get(models.ExpenseEntry, eid).payer_account_number = "옛날에 들어간 값"
        db.commit()
    assert _고침(admin_client, 판, eid, note="비고만 고침").status_code in (200, 303)
    with app_session() as db:
        e = db.get(models.ExpenseEntry, eid)
        assert e.note == "비고만 고침" and e.payer_account_number == "옛날에 들어간 값"


def test49_c03_내_정보도_같은_게이트(admin_client):
    r = admin_client.post("/me/update", data={"name": "총무 김간사", "bank_name": "",
                                               "account_number": "999-1234-567890", "account_holder": ""})
    assert r.status_code == 400
    ok = admin_client.post("/me/update", data={"name": "총무 김간사", "bank_name": "지어낸은행",
                                                "account_number": "999-1234-567890", "account_holder": "가명"})
    assert ok.status_code in (200, 303)
    with app_session() as db:
        assert "999-1234-567890" in {u.account_number for u in db.scalars(select(models.User))}


# ── 라) 두 검사가 계좌 꼴을 본다 ──


def _load(이름):
    spec = importlib.util.spec_from_file_location(f"_{이름}_49", ROOT / "scripts" / f"{이름}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 검사가 잡아야 할 꼴 — 지어낸 표시(999 · 한 숫자 되풀이 · 이어 오름)를 피해 만든 번호.
# 실제 계좌와 같을 수는 있어도 누구의 것인지 이 파일에 적혀 있지 않다
심을번호 = "352-8061-4907-13"


def test49_d01_검사가_보는_꼴과_빼는_꼴():
    꼴 = _load("check_names")._꼴
    for 조각 in (심을번호, "35280614907", "352806-14-907135"):
        assert 꼴.계좌로보이나(조각), 조각
    for 조각 in ("999-0000-1111", "01012345678", "010-1234-5678", "2026-09-12-2027", "0000000000",
                 "12345678901234", "1462", "352-806"):
        assert not 꼴.계좌로보이나(조각), 조각
    # 영숫자에 붙은 조각(해시·백업 파일 이름)은 글에서 안 뽑는다
    assert not [m.group() for m in 꼴.글속꼴.finditer(f"app-{심을번호[:8]}-214809.db · a{심을번호}")
                if 꼴.계좌로보이나(m.group())]


def test49_d02_check_names_가_docs_의_계좌_꼴을_잡는다(tmp_path, monkeypatch, capsys):
    m = _load("check_names")
    가짜 = tmp_path / "docs" / "보고.md"
    가짜.parent.mkdir()
    가짜.write_text(f"첫 줄\n지출자 계좌 지어낸은행 {심을번호} 입니다\n", encoding="utf-8")
    monkeypatch.setattr(m, "ROOT", tmp_path)
    assert m.계좌꼴검사([가짜]) == 1
    out = capsys.readouterr().out
    assert "docs/보고.md:2" in out and 심을번호 not in out, "자리만 찍고 값은 안 찍는다"
    가짜.write_text("지어낸 999-0000-1111 · 2026-09-14 21:55\n", encoding="utf-8")
    assert m.계좌꼴검사([가짜]) == 0
    # docs/ 밖은 안 본다 — 코드·시험·seed 는 지어낸 번호를 담는다
    밖 = tmp_path / "tests" / "x.py"
    밖.parent.mkdir()
    밖.write_text(f"번호 = '{심을번호}'\n", encoding="utf-8")
    assert m.계좌꼴검사([밖, 가짜]) == 0, "docs/ 밖의 번호로 빨개졌다"


def test49_d03_check_dev_db_가_계좌_꼴을_잡는다(tmp_path):
    dev = _load("check_dev_db")
    db_path = tmp_path / "acc.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE expense_entries (payer_account_number TEXT, note TEXT)")
    con.execute("INSERT INTO expense_entries VALUES (?, ?)", (심을번호, "계좌 없음"))
    con.execute("INSERT INTO expense_entries VALUES (?, ?)", ("999-0000-1111", f"메모에 {심을번호} 적음"))
    con.commit()
    con.close()
    걸림 = dev.실명이있나(db_path)
    assert 걸림.get("expense_entries.payer_account_number") == 1
    assert 걸림.get("expense_entries.note") == 1, "글 속에 든 계좌 꼴도 잡는다"


def test49_d04_대응표가_없어도_계좌_꼴은_본다(tmp_path, monkeypatch):
    dev = _load("check_dev_db")
    monkeypatch.setattr(dev._anon, "MAP_PATH", tmp_path / "없는대응표.json")
    db_path = tmp_path / "acc2.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE users (account_number TEXT)")
    con.execute("INSERT INTO users VALUES (?)", (심을번호,))
    con.commit()
    con.close()
    assert dev.실명이있나(db_path).get("users.account_number") == 1


def test49_d05_check_names_는_본_수가_0_이면_실패(tmp_path, capsys):
    m = _load("check_names")
    assert m.계좌꼴검사([]) == 1 and "하나도 못 봤습니다" in capsys.readouterr().out
    # 경로를 주거나 --staged 로 돌 때는 docs/ 가 없을 수 있다 — 막히면 안 되는 쪽
    assert m.계좌꼴검사([], 전체=False) == 0 and "해당 없음" in capsys.readouterr().out


def test49_d06_전각_숫자는_꼴이_아니다():
    전각 = "９９９-１２３４-５６７８９０"
    assert B.account_problem("지어낸은행", 전각, "가명"), "전각 숫자가 게이트를 지났다"


def test49_c04_내_정보는_계좌를_바꿀_때만_꼴을_본다(admin_client):
    with app_session() as db:
        u = db.scalars(select(models.User).where(models.User.role == "admin")).first()
        u.bank_name, u.account_number = None, "옛날에 들어간 값"
        db.commit()
        이름 = u.name
    r = admin_client.post("/me/update", data={"name": "이름만 고침", "bank_name": "",
                                               "account_number": "옛날에 들어간 값", "account_holder": ""})
    assert r.status_code in (200, 303)
    with app_session() as db:
        assert "이름만 고침" in {x.name for x in db.scalars(select(models.User))}, f"{이름[:0]}옛 계좌가 이름 고치기를 막았다"
