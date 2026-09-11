"""남은 것 닫기 — 초대 토큰·이름 한 자리(X-a) · 볼 목록을 칸으로(0-a) · 문구.

막는 코드마다 막히는 쪽과 뚫리는 쪽을 함께 잰다 (11-3).
"""

from __future__ import annotations


import importlib.util
import pathlib
import sqlite3

import pytest
from sqlalchemy import JSON, String, Text
from starlette.testclient import TestClient

from app import models
from tests.conftest import make_user, app_session

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _map_or_skip(mod):
    try:
        return mod.load_map()
    except SystemExit:
        pytest.skip("대응표가 없다 — 새로 받은 사본에서는 잴 것이 없다")


# ════════════════════════════════════════════════════════════════════
# 1. 초대 토큰과 이름이 한 자리에 (X-a)
# ════════════════════════════════════════════════════════════════════


def _아이디를준다(uid: int, 아이디: str) -> None:
    from app.models import User
    with app_session() as db:
        db.get(User, uid).login_id = 아이디
        db.commit()


def test9_t01_이름과_비밀번호가_한_키에_묶여_어긋날_자리가_없다(admin_client):
    """이름을 주소에 따로 실으면 「B 님의 비밀번호」 아래 A 의 값이 뜰 자리가
    생긴다 (4-12). 값과 이름은 **한 키**에 묶여 온다."""
    person = make_user("묶인 사람", "01066670001", "member")
    other = make_user("딴 사람", "01066670002", "member")
    _아이디를준다(person, "mukin")

    r = admin_client.post(f"/admin/users/{person}/password", follow_redirects=False)
    location = r.headers["location"]
    assert "k=" in location and "u=" not in location      # 이름은 키 안에 있다

    # 주소에 남의 id 를 붙여도 아무것도 안 바뀐다 — u= 를 읽는 곳이 없다 (막는 쪽)
    page = admin_client.get(location + f"&u={other}")
    assert "묶인 사람 님의 첫 비밀번호입니다" in page.text
    assert "딴 사람 님의" not in page.text
    assert 'id="firstpw"' in page.text

    # 같은 키를 다시 열면 값도 이름도 없다 — 한 번만 꺼내진다
    again = admin_client.get(location)
    assert 'id="issued"' not in again.text


def test9_t02_화면의_이름과_그_값으로_로그인한_계정이_같다(admin_client):
    """보여준 이름과 그 값이 여는 계정이 같은가 — 어긋나면 총무팀이 엉뚱한
    사람에게 비밀번호를 보낸다."""
    import re as _re

    person = make_user("일치 확인", "01066670003", "member")
    _아이디를준다(person, "ilchi")
    r = admin_client.post(f"/admin/users/{person}/password", follow_redirects=False)
    page = admin_client.get(r.headers["location"]).text
    assert "일치 확인 님의 첫 비밀번호입니다" in page
    값 = _re.search(r'id="firstpw" readonly value="([^"]+)"', page).group(1)

    from app.main import app

    guest = TestClient(app)
    assert guest.post("/login", data={"login_id": "ilchi", "password": 값},
                      follow_redirects=False).status_code == 303
    # 첫 비밀번호라 바꾸는 화면이 먼저 뜬다 — 거기에 그 사람 이름이 있다
    me = guest.get("/password")
    assert me.status_code == 200 and "일치 확인" in me.text


# ════════════════════════════════════════════════════════════════════
# 2. 볼 목록을 칸으로 잰다 — 게이트는 전부 보고 뺄 것만 이유와 함께 뺀다
# ════════════════════════════════════════════════════════════════════


def _모델_글자칸() -> set[tuple[str, str]]:
    cols = set()
    for mapper in models.Base.registry.mappers:
        table = mapper.local_table
        for col in table.columns:
            if isinstance(col.type, (String, Text, JSON)):
                cols.add((table.name, col.name))
    return cols


def _진짜_스키마_db(path: pathlib.Path) -> None:
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{path}")
    models.Base.metadata.create_all(engine)
    engine.dispose()


def test9_g01_볼칸은_모델_전수에서_제외를_뺀_것이다(tmp_path):
    """목록에 든 것이 아니라 **닿지 않는 칸이 없는지**를 잰다 (11-2).

    제외에만 이유가 붙고, 모델에서 사라진 칸이 제외에 남으면(낡은 목록)
    빨개진다. 볼칸은 진짜 스키마(create_all)에서 실측한다.
    """
    dev = _load("check_dev_db")
    model_cols = _모델_글자칸()
    for 칸 in dev.제외칸:
        assert 칸 in model_cols, f"모델에 없는 제외칸: {칸}"

    db_path = tmp_path / "schema.db"
    _진짜_스키마_db(db_path)
    con = sqlite3.connect(db_path)
    try:
        본것 = set(dev.볼칸들(con))
    finally:
        con.close()
    assert 본것 == model_cols - set(dev.제외칸)


def test9_g02_볼_칸마다_심으면_전부_걸린다(tmp_path):
    """칸 커버리지 — 「목록에 있다」 가 아니라 「그 칸에 심으면 걸린다」.

    사람 이름·장소·연락처를 칸마다 돌아가며 하나씩 심고, 볼 칸 전부가
    걸리는지 잰다. 하나라도 조용하면 그 칸이 「볼 목록 밖」 이다.
    """
    dev = _load("check_dev_db")
    names, phones, places = _map_or_skip(dev._anon)
    비밀들 = [names[0][0]]
    if places:
        비밀들.append(places[0][0])
    if phones:
        비밀들.append(phones[0][0])

    model_cols = _모델_글자칸()
    볼칸 = sorted(model_cols - set(dev.제외칸))
    표별: dict[str, list[str]] = {}
    for 표, 칸 in 볼칸:
        표별.setdefault(표, []).append(칸)

    db_path = tmp_path / "plant.db"
    con = sqlite3.connect(db_path)
    i = 0
    for 표, 칸들 in 표별.items():
        ddl = ", ".join(f'"{c}" TEXT' for c in 칸들)
        con.execute(f'CREATE TABLE "{표}" ({ddl})')
        값들 = []
        for _ in 칸들:
            값들.append(f"심은 값 {비밀들[i % len(비밀들)]} 끝")
            i += 1
        홀더 = ", ".join("?" for _ in 칸들)
        con.execute(f'INSERT INTO "{표}" VALUES ({홀더})', 값들)
    con.commit()
    con.close()

    걸림 = dev.실명이있나(db_path)
    안걸린것 = [f"{표}.{칸}" for 표, 칸 in 볼칸 if 걸림.get(f"{표}.{칸}") != 1]
    assert 안걸린것 == [], f"심었는데 조용한 칸: {안걸린것}"
    assert len(걸림) == len(볼칸)                        # 센 것이 0이면 실패 (11-3)


def test9_g03_모델에_없던_새_칸도_저절로_걸린다(tmp_path):
    """막는 쪽 — 스키마에서 읽으므로 목록을 안 고쳐도 새 칸이 검사된다.
    목록을 고쳐야 잡히는 구조였다면 이 시험이 있을 수 없다."""
    dev = _load("check_dev_db")
    names, _, _ = _map_or_skip(dev._anon)
    real = names[0][0]

    db_path = tmp_path / "new.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE program_items (brand_new_note TEXT)")
    con.execute("INSERT INTO program_items VALUES (?)", (f"메모: {real} 확인",))
    con.commit()
    con.close()
    assert dev.실명이있나(db_path).get("program_items.brand_new_note") == 1


def test9_t03_발급_배너가_사후_고지를_함께_적는다():
    """4-12 문면 — 「이전 비밀번호는 이제 쓸 수 없습니다」 를 발급할 때마다
    함께 적는다. 안 적으면 총무팀이 「아까 보낸 것으로 들어가세요」 라고
    안내하게 된다.

    **띄우는 길은 하나다** — 그 자리에서 띄우던 길은 걷었다(값이 실린
    응답이 둘이 되면 한쪽만 no-store 를 놓쳐도 아무도 모른다).
    """
    html = (ROOT / "app" / "templates" / "admin_users.html").read_text(encoding="utf-8")
    assert "이전 비밀번호는 이제 쓸 수 없습니다" in html
    assert "한 번만 보입니다" in html
    assert "showInline" not in html, "값을 띄우는 길이 둘이다"
    # u= 를 만드는 곳이 없다. **낱말 시험이라 주석의 &u= 에도 걸린다** —
    # 가짜 빨강 쪽이라 안전해서 그대로 둔다(가짜 초록이 문제지 가짜
    # 빨강은 사람을 그 자리로 데려간다). 걸리면 주석을 다르게 적으면 된다
    src = (ROOT / "app" / "routers" / "admin_users.py").read_text(encoding="utf-8")
    assert "&u=" not in src and 'params.get("u"' not in src
