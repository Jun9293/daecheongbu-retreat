"""첫 비밀번호를 화면에서 (+ 다듬기 후속) — 4-17 사용자 탭.

**2026-09-11 에 초대 링크가 걷혔다.** 그 자리의 한 바퀴(발급 → 로그인 →
바꾸기)는 `tests/test_stage34.py` 가 잰다 — 여기 남은 것은 그때 함께
정한 **권한**과 **만드는 자리가 하나인가**다. 막는 코드마다 막히는 쪽
시험이 함께 있다.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest
from sqlalchemy import select

from app import models
from tests.conftest import app_session, login_as, make_user

TODAY = dt.date.today()
ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def person(admin_client):
    return make_user("초대받을 사람", "01066660001", "member")


# ════════════════════════════════════════════════════════════════════
# 1. 권한과 「만드는 자리가 하나인가」
#
# 한 바퀴(발급 → 로그인 → 바꾸기)는 tests/test_stage34.py 가 잰다.
# ════════════════════════════════════════════════════════════════════
def test8_i02_발급은_총무팀만(client, admin_client, person):
    """부서 리더는 남의 비밀번호를 만들 수 없다 — 만들 수 있으면 그 계정으로
    들어갈 수 있다. **막는 쪽과 안 막히는 쪽을 함께 본다.**"""
    make_user("리더", "01066660002", "dept_lead")
    login_as(client, "01066660002")
    denied = client.post(f"/admin/users/{person}/password")
    assert denied.status_code == 403                     # 막는 쪽
    # 안 막히는 쪽 — 총무팀은 된다 (아이디가 있어야 하므로 먼저 준다)
    admin_client.post(f"/admin/users/{person}/update",
                      data={"role": "general", "login_id": "chodae"})
    ok = admin_client.post(f"/admin/users/{person}/password", follow_redirects=False)
    assert ok.status_code == 303 and "k=" in ok.headers["location"]


def test8_i03_화면과_스크립트가_같은_함수를_부른다():
    """만드는 길이 둘이면 하나만 고쳐진다 (1-d).

    본다 — ① 해시를 만드는 함수가 `domain/login` 한 곳인가 ② 화면과
    스크립트가 **그것을** 부르는가 ③ 다른 곳에서 `hashlib.scrypt` 를 직접
    부르지 않는가(셈이 두 벌이 되는 첫걸음이다) ④ 훑은 파일이 비지 않았나.
    """
    로그인 = (ROOT / "app" / "domain" / "login.py").read_text(encoding="utf-8")
    assert 로그인.count("\ndef 해시한다(") == 1
    screen = (ROOT / "app" / "routers" / "admin_users.py").read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "계정문열기.py").read_text(encoding="utf-8")
    assert "로그인.비밀번호를정한다(" in screen and "로그인.비밀번호를정한다(" in script
    assert "로그인.첫비밀번호()" in screen and "로그인.첫비밀번호()" in script

    본파일 = 0
    for path in list(pathlib.Path(ROOT, "app").rglob("*.py")) + \
            list(pathlib.Path(ROOT, "scripts").glob("*.py")):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        본파일 += 1
        글 = path.read_text(encoding="utf-8")
        if rel != "app/domain/login.py":
            assert "hashlib.scrypt" not in 글, rel
        if rel not in ("app/domain/auth.py", "app/models.py"):
            assert "InviteToken(" not in 글, rel
    assert 본파일 > 20, "훑은 파일이 너무 적다 — 아무것도 안 본 검사다"


# ════════════════════════════════════════════════════════════════════
# 2-a. 장소도 본다 — 사람 이름만 보는 검사는 장소에 아무 말도 안 한다 (11-2)
# ════════════════════════════════════════════════════════════════════


def _load_script(name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _장소하나():
    # 대응표는 anonymize 의 창구로만 읽는다 — 읽는 곳이 둘이면 구조가 바뀔 때
    # 한쪽만 고쳐진다 (test_검사_08 이 그것을 지킨다)
    anon = _load_script("anonymize")
    try:
        places = anon.장소들()
    except SystemExit:
        pytest.skip("대응표가 없다 — 새로 받은 사본에서는 잴 장소가 없다")
    if not places:
        pytest.skip("대응표에 장소가 없다")
    return places[0]


def test8_p01_장소_실명을_심으면_걸린다(tmp_path):
    real, fake = _장소하나()
    cn = _load_script("check_names")
    # 장소가 찾을 목록(표기들)에 이름과 함께 실려 온다 — 한 목록이다
    assert real in cn._anon.표기들()
    p = tmp_path / "글.md"
    p.write_text(f"신선식품은 {real} 냉장고에 보관", encoding="utf-8")
    assert cn.찾는다([real], [p])                        # 막는 쪽
    p.write_text(f"신선식품은 {fake} 냉장고에 보관", encoding="utf-8")
    assert not cn.찾는다([real], [p])                    # 가명은 통과
    # 개발 DB 게이트도 같은 목록을 본다 (load_map 의 names 에 합쳐진다)
    dev = _load_script("check_dev_db")
    assert real in [a for a, _ in dev._anon.load_map()[0]]
    # 그리고 **장소가 살던 칸을 실제로 본다** — 게이트는 글자 칸 전부를
    # 기본으로 훑고 제외 목록만 뺀다. 그 칸들이 제외에 없어야 한다
    for 칸 in (("program_items", "text"), ("programs", "place"), ("programs", "name")):
        assert 칸 not in dev.제외칸
    import sqlite3
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        db_path = pathlib.Path(td) / "app.db"
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE program_items (text TEXT)")
        con.execute("INSERT INTO program_items VALUES (?)", (f"{real} 냉장고에 보관",))
        con.commit()
        con.close()
        걸림 = dev.실명이있나(db_path)
        assert 걸림.get("program_items.text") == 1       # 막는 쪽


def test8_p02_프로그램표에_실제_장소가_없다():
    real, fake = _장소하나()
    text = (ROOT / "data" / "2026여름_프로그램표.json").read_text(encoding="utf-8")
    assert real not in text
    assert fake in text                                  # 지워진 게 아니라 바뀐 것


# ════════════════════════════════════════════════════════════════════
# 2-b·2-c. W-b · W-c · W-a
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def meal_retreat(admin_client):
    with app_session() as db:
        retreat = models.Retreat(name="식대 회차", meal_subsidy_per_person=8000,
                                 start_date=TODAY + dt.timedelta(days=40),
                                 end_date=TODAY + dt.timedelta(days=43))
        db.add(retreat)
        db.flush()
        canceled = models.ExpenseEntry(
            retreat_id=retreat.id, is_meal_expense=True, amount=10_000,
            level3b="모임 식사비-9", canceled_at=dt.datetime.now())
        live = models.ExpenseEntry(
            retreat_id=retreat.id, is_meal_expense=True, amount=5_000,
            level3b="모임 식사비-2")
        db.add_all([canceled, live])
        db.commit()
        return {"retreat": retreat.id, "canceled": canceled.id, "live": live.id}


def test8_w01_취소된_식대는_직전_입력값_제안에_안_잡힌다(meal_retreat):
    from app.routers.expenses import _last_meal_defaults

    with app_session() as db:
        retreat = db.get(models.Retreat, meal_retreat["retreat"])
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()
        got = _last_meal_defaults(db, retreat, admin)
        # 취소된 -9 가 아니라 산 -2 에서 잇는다 (W-b)
        assert got["level3b"] == "모임 식사비-3"


def test8_w02_취소_행에는_지급_토글이_없다(admin_client, meal_retreat):
    rid, cid, lid = (meal_retreat[k] for k in ("retreat", "canceled", "live"))
    admin_client.get(f"/board?retreat_id={rid}")
    page = admin_client.get("/expenses").text
    assert f'action="/expenses/{lid}/paid"' in page      # 산 행에는 있다
    assert f'action="/expenses/{cid}/paid"' not in page  # 취소 행에는 없다 (W-c)
    assert "취소됨" in page                              # 행 자체는 남아 있다


def test8_w03_해시를_맞바꾸면_걸린다(tmp_path):
    """경로·해시가 같은 **줄**에 짝지어 있어야 통과다 (W-a)."""
    cn = _load_script("check_names")
    목록 = [("docs/review/a.png", "aaaaaaaaaaaa"), ("docs/review/b.png", "bbbbbbbbbbbb")]
    짝맞음 = "docs/review/a.png | aaaaaaaaaaaa | 봤음\ndocs/review/b.png | bbbbbbbbbbbb | 봤음"
    assert cn.미확인이미지(목록, 짝맞음) == []
    맞바꿈 = "docs/review/a.png | bbbbbbbbbbbb | 봤음\ndocs/review/b.png | aaaaaaaaaaaa | 봤음"
    assert len(cn.미확인이미지(목록, 맞바꿈)) == 2       # 막는 쪽 — 둘 다 걸린다
