"""초대 링크를 화면에서 (+ 다듬기 후속) — 4-17 사용자 탭.

발급·재발급·복사가 화면에서 되고, 만드는 것은 스크립트와 **같은 함수**
(invites.issue)다. 막는 코드마다 막히는 쪽 시험이 함께 있다.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest
from sqlalchemy import select
from starlette.testclient import TestClient

from app import models
from tests.conftest import app_session, login_as, make_user

TODAY = dt.date.today()
ROOT = pathlib.Path(__file__).resolve().parent.parent


def _fresh():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def person(admin_client):
    return make_user("초대받을 사람", "01066660001", "member")


# ════════════════════════════════════════════════════════════════════
# 1. 발급 → 로그인 → 재사용 403 → 재발급 → 옛 링크 403 → 화면에 안 남음 (1-g)
# ════════════════════════════════════════════════════════════════════


def test8_i01_발급부터_만료까지_한_바퀴(admin_client, person):
    # 발급 — 화면의 JS 가 부르는 길(inline=1). 링크가 그 자리(JSON)로 온다
    r = admin_client.post(f"/admin/users/{person}/invite?inline=1")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "초대받을 사람" and "/invite/" in data["url"]
    token = data["url"].rsplit("/", 1)[-1]

    # 그 링크로 로그인 — 200 (홈으로)
    guest = _fresh()
    ok = guest.get(f"/invite/{token}", follow_redirects=True)
    assert ok.status_code == 200

    # 같은 링크 다시 — 한 번 쓰면 만료 (403)
    again = _fresh().get(f"/invite/{token}")
    assert again.status_code == 403

    # 재발급 — 새 링크가 오고, 그것을 쓰기 전이라도 **또 재발급하면** 죽는다
    first = admin_client.post(f"/admin/users/{person}/invite?inline=1").json()
    second = admin_client.post(f"/admin/users/{person}/invite?inline=1").json()
    old_token = first["url"].rsplit("/", 1)[-1]
    new_token = second["url"].rsplit("/", 1)[-1]
    assert _fresh().get(f"/invite/{old_token}").status_code == 403   # 옛 링크는 죽었다
    assert _fresh().get(f"/invite/{new_token}", follow_redirects=True).status_code == 200

    # 목록을 새로 열면 링크가 화면에 안 남는다 — 원문을 저장하지 않는다 (4-12)
    page = admin_client.get("/admin/users")
    assert "/invite/" not in page.text.replace('action="/admin/users', "")


def test8_i02_발급은_총무팀만(client, admin_client, person):
    make_user("리더", "01066660002", "dept_lead")
    login_as(client, "01066660002")
    denied = client.post(f"/admin/users/{person}/invite?inline=1")
    assert denied.status_code == 403                     # 막는 쪽


def test8_i03_화면과_스크립트가_같은_함수를_부른다():
    """만드는 길이 둘이면 하나만 고쳐진다 (1-d). issue 는 auth 한 곳이다."""
    auth = (ROOT / "app" / "domain" / "auth.py").read_text(encoding="utf-8")
    assert auth.count("\ndef issue(") == 1
    screen = (ROOT / "app" / "routers" / "admin_users.py").read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "create_admin.py").read_text(encoding="utf-8")
    assert "invites.issue(" in screen and "invites.issue(" in script
    assert "invites.invite_url(" in screen and "invites.invite_url(" in script
    # 다른 길로 토큰을 만드는 곳이 없다 — InviteToken 을 직접 짓는 자리는 auth 뿐
    for path in pathlib.Path(ROOT, "app").rglob("*.py"):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel == "app/domain/auth.py" or rel == "app/models.py":
            continue
        assert "InviteToken(" not in path.read_text(encoding="utf-8"), rel


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
    # 그리고 **장소가 살던 칸을 실제로 본다** — 목록에만 있고 칸을 안 보면
    # 익명화 이전 프로그램표를 든 dev DB 가 그대로 지나간다 (검토자 지적)
    for 칸 in (("program_items", "text"), ("programs", "place"), ("programs", "name")):
        assert 칸 in dev.이름칸
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


def test8_i04_JS_없는_길의_배너가_이름을_말한다(admin_client, person):
    """리다이렉트 배너(폴백)도 누구의 링크인지 밝힌다 — 이름 없는 링크가
    이 화면이 안 쓰인 이유의 하나였다 (0-a)."""
    r = admin_client.post(f"/admin/users/{person}/invite", follow_redirects=False)
    assert r.status_code == 303
    location = r.headers["location"]
    assert "k=" in location and f"u={person}" in location
    page = admin_client.get(location)
    assert "초대받을 사람 님의 링크입니다" in page.text
    assert 'id="invitelink"' in page.text and 'id="copylink"' in page.text
    # 한 번만 보인다는 문장과, 그 자리(행)에서 여는 JS 훅이 화면에 있다
    assert "한 번만 보입니다" in page.text
    assert "issueform" in page.text and "inline=1" in page.text
