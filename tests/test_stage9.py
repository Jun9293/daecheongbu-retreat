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
from tests.conftest import make_user

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


def test9_t01_이름과_링크가_한_키에_묶여_어긋날_자리가_없다(admin_client):
    person = make_user("묶인 사람", "01066670001", "member")
    other = make_user("딴 사람", "01066670002", "member")

    r = admin_client.post(f"/admin/users/{person}/invite", follow_redirects=False)
    location = r.headers["location"]
    assert "k=" in location and "u=" not in location      # 이름은 키 안에 있다

    # 주소에 남의 id 를 붙여도 아무것도 안 바뀐다 — u= 를 읽는 곳이 없다 (막는 쪽)
    page = admin_client.get(location + f"&u={other}")
    assert "묶인 사람 님의 링크입니다" in page.text
    assert "딴 사람 님의" not in page.text
    assert "/invite/" in page.text

    # 같은 키를 다시 열면 링크도 이름도 없다 — 한 번만 꺼내진다
    again = admin_client.get(location)
    assert 'id="issued"' not in again.text


def test9_t02_화면의_이름과_그_링크로_로그인한_계정이_같다(admin_client):
    person = make_user("일치 확인", "01066670003", "member")
    data = admin_client.post(f"/admin/users/{person}/invite?inline=1").json()
    assert data["name"] == "일치 확인"
    token = data["url"].rsplit("/", 1)[-1]

    from app.main import app

    guest = TestClient(app)
    guest.get(f"/invite/{token}", follow_redirects=True)
    me = guest.get("/settings")                           # 내 정보 — 로그인한 이름
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


def test9_t03_인라인_결과_상자에도_사후_고지가_있다():
    """4-12 문면 — 「이전에 발급한 링크는 이제 쓸 수 없습니다」 를 발급할
    때마다 함께 적는다. 사전 confirm 과 별개로 상자에도 남는다."""
    html = (ROOT / "app" / "templates" / "admin_users.html").read_text(encoding="utf-8")
    inline_js = html[html.index("function showInline"):]
    assert "이전에 발급한 링크는 이제 쓸 수 없습니다" in inline_js
    assert "지금 링크는 못 쓰게 됩니다" in html            # 사전 confirm 도 그대로
    # u= 를 만드는 곳이 없다
    src = (ROOT / "app" / "routers" / "admin_users.py").read_text(encoding="utf-8")
    assert "&u=" not in src and 'params.get("u"' not in src
