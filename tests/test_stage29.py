"""비품 도막 2 — 묶음을 품목에서 회차로 (4-18).

수용 기준 다~아 를 잰다(가·나 는 test_stage28 의 a01·a02 가 새 모양으로 잰다, 자 는
test28_f01). 옛 모양의 DB 는 여기서 **실제로 세워서** 스크립트를 돌린다 — 막히는
쪽·통과하는 쪽·검사가 볼 것을 보는가 셋을 갖춘다.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import shutil
import sqlite3

import pytest
from sqlalchemy import func, select, text

from app import models
from app.domain import permissions as perm
from tests.conftest import app_session, make_user

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = dt.date.today()


def _스크립트(이름: str):
    spec = importlib.util.spec_from_file_location(이름, ROOT / f"scripts/{이름}.py")
    모듈 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(모듈)
    return 모듈


def _사본준비(모듈, tmp_path, monkeypatch):
    from app.db import engine
    monkeypatch.setattr(모듈.config, "DATA_DIR", tmp_path)
    shutil.copy(engine.url.database, tmp_path / "app.db")
    monkeypatch.setattr(모듈.config, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")


# 도막 1 이 만든 옛 모양 그대로 — 운영 DB 의 sqlite_master 에서 읽은 DDL
옛_품목 = """CREATE TABLE equipment_items (
    id INTEGER NOT NULL, team_key VARCHAR(30) NOT NULL, group_name VARCHAR(100) NOT NULL,
    name VARCHAR(200) NOT NULL, unit VARCHAR(20), note TEXT, created_at DATETIME NOT NULL,
    PRIMARY KEY (id), CONSTRAINT uq_equipment_item UNIQUE (team_key, group_name, name))"""
옛_run = """CREATE TABLE equipment_runs (
    id INTEGER NOT NULL, retreat_id INTEGER NOT NULL, item_id INTEGER NOT NULL,
    included BOOLEAN NOT NULL, quantity VARCHAR(50), location VARCHAR(100), checked BOOLEAN NOT NULL,
    checked_by_id INTEGER, checked_by_name VARCHAR(50), checked_at DATETIME, sort_order INTEGER NOT NULL,
    PRIMARY KEY (id), CONSTRAINT uq_equipment_run UNIQUE (retreat_id, item_id),
    FOREIGN KEY(retreat_id) REFERENCES retreats (id) ON DELETE CASCADE,
    FOREIGN KEY(item_id) REFERENCES equipment_items (id) ON DELETE CASCADE,
    FOREIGN KEY(checked_by_id) REFERENCES users (id) ON DELETE SET NULL)"""


def _수(db) -> dict[str, int]:
    """옛·새 모양 어느 쪽에서도 읽히는 셈 — SQL 로."""
    n = lambda q: db.execute(text(q)).scalar_one()  # noqa: E731
    cols = {r[1] for r in db.execute(text("PRAGMA table_info(equipment_runs)"))}
    return {"items": n("SELECT COUNT(*) FROM equipment_items"),
            "runs": n("SELECT COUNT(*) FROM equipment_runs"),
            "채워진run": n("SELECT COUNT(*) FROM equipment_runs WHERE group_name <> ''") if "group_name" in cols else 0}


@pytest.fixture
def 옛세상(admin_client):
    """옛 모양의 표 둘을 실제로 세우고 자료를 넣는다 — 같은 팀·같은 이름의 릴선이 묶음만
    다르게 둘(합쳐질 것), 같은 이름이 팀만 다른 릴선 하나(따로), 마이크 하나."""
    with app_session() as db:
        r = models.Retreat(name="묶음 회차", start_date=TODAY + dt.timedelta(days=30),
                           end_date=TODAY + dt.timedelta(days=33))
        db.add(r); db.flush()
        ids = {"retreat": r.id}
        # 스케치를 0 · 헤브론을 1 로 — 키의 알파벳순(h < s)과 반대라, 화면 순서가 부서
        # sort_order 를 따르는지 가를 수 있다 (검토가 짚음)
        for i, (key, name) in enumerate((("sketch", "4 스케치"), ("hebron", "5 헤브론"))):
            d = models.Department(retreat_id=r.id, key=key, name=name, color_tag="#888", sort_order=i)
            db.add(d); db.flush(); ids[key] = d.id
        db.commit()
    ids["lead"] = make_user("헤브론 리더", "01077770501", "general", departments=[(ids["hebron"], perm.LEAD)])
    with app_session() as db:
        db.execute(text("DROP TABLE equipment_runs"))
        db.execute(text("DROP TABLE equipment_items"))
        db.execute(text(옛_품목)); db.execute(text(옛_run))
        db.execute(text("CREATE INDEX ix_equipment_items_team_key ON equipment_items (team_key)"))
        db.execute(text("CREATE INDEX ix_equipment_runs_retreat_id ON equipment_runs (retreat_id)"))
        db.execute(text("CREATE INDEX ix_equipment_runs_item_id ON equipment_runs (item_id)"))
        now = "2026-09-10 00:00:00"
        for i, (team, group, name) in enumerate((("hebron", "집회 비품", "릴선"), ("hebron", "야외 세팅", "릴선"),
                                                  ("hebron", "집회 비품", "마이크"), ("sketch", "새친구 비품", "릴선")), start=1):
            unit, note = ("m", "야외용 30m") if i == 2 else (None, None)      # 사라질 쪽(2)에만 unit·note
            db.execute(text("INSERT INTO equipment_items (id, team_key, group_name, name, unit, note, created_at) "
                            "VALUES (:i, :t, :g, :n, :u, :o, :c)"),
                       {"i": i, "t": team, "g": group, "n": name, "u": unit, "o": note, "c": now})
        rid = ids["retreat"]
        db.execute(text("INSERT INTO equipment_runs (id, retreat_id, item_id, included, quantity, location, checked, "
                        "checked_by_id, checked_by_name, checked_at, sort_order) VALUES "
                        "(1, :r, 1, 1, '2개', '본당', 1, :u, '박민준', '2026-09-01 03:00:00', 0), "
                        "(2, :r, 2, 1, '인당 1개', NULL, 0, NULL, NULL, NULL, 1), "
                        "(3, :r, 3, 0, '4개', NULL, 0, NULL, NULL, NULL, 2), "
                        "(4, :r, 4, 1, NULL, '창고', 1, :u, '박민준', '2026-09-02 03:00:00', 0)"),
                   {"r": rid, "u": ids["lead"]})
        db.commit()
    return ids


def _묶음들(page: str) -> list[str]:
    import re
    return re.findall(r'<h3 style="margin:0;font-size:var\(--fz-lg\)">([^<]+)</h3>', page)


# ── 다. 미리보기 ───────────────────────────────────────────────────────

def test29_c01_미리보기는_아무것도_안_바꾸고_수만_찍는다(옛세상, tmp_path, monkeypatch, capsys):
    """다) 앞뒤로 품목 수 · run 수 · 묶음이 채워진 run 수가 같고 사본이 안 뜬다.
    본다: 세 수의 dict · 출력의 다섯 수 · 사람 이름 없음 · backups/ 비어 있음."""
    모듈 = _스크립트("비품묶음옮기기")
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        assert 모듈.옛모양인가(db), "③ 실제로 옛 모양이어야 한다"
        전 = _수(db)
        assert 전 == {"items": 4, "runs": 4, "채워진run": 0}
        assert 모듈.옮기기(db, 실행=False) == 0
        후 = _수(db)
        assert 모듈.옛모양인가(db)
    assert 전 == 후
    out = capsys.readouterr().out
    assert "품목 4개 (합쳐질 품목 1개 · 그중 unit·note 를 남는 쪽에 합칠 것 1개) · run 4개 (묶음이 채워질 run 4개) · 겹침 0건" in out
    assert "박민준" not in out and "릴선" not in out
    assert not list(tmp_path.glob("backups/*.db"))


# ── 라. 합치기 ─────────────────────────────────────────────────────────

def test29_c02_실행하면_품목이_합쳐지고_run_은_둘_다_남는다(옛세상, tmp_path, monkeypatch):
    """라) 같은 팀·같은 이름이 묶음만 다르게 둘 → 품목 하나(id 작은 쪽), run 은 둘 다
    남고 각 run 의 묶음·수량·체크·누가·언제가 그대로. 본다: 품목 4→3 · run 4 · item_id
    가 남긴 쪽 · run 칸 값 전부 · 새 유니크 둘 · 옛 칸 없음 · 사본 하나."""
    모듈 = _스크립트("비품묶음옮기기")
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        assert 모듈.옮기기(db, 실행=True) == 0
    with app_session() as db:
        assert not 모듈.옛모양인가(db)
        assert _수(db) == {"items": 3, "runs": 4, "채워진run": 4}
        runs = {r.id: r for r in db.scalars(select(models.EquipmentRun))}
        assert runs[1].item_id == 1 and runs[2].item_id == 1, "사라지는 품목(2)을 가리키던 run 이 남긴 쪽(1)으로"
        assert (runs[1].group_name, runs[1].quantity, runs[1].location, runs[1].checked,
                runs[1].checked_by_id, runs[1].checked_by_name, runs[1].checked_at) == (
            "집회 비품", "2개", "본당", True, 옛세상["lead"], "박민준", dt.datetime(2026, 9, 1, 3, 0))
        assert (runs[2].group_name, runs[2].quantity, runs[2].checked, runs[2].sort_order) == ("야외 세팅", "인당 1개", False, 1)
        assert (runs[3].group_name, runs[3].included, runs[3].item_id) == ("집회 비품", False, 3)
        assert (runs[4].group_name, runs[4].item_id, runs[4].location) == ("새친구 비품", 4, "창고")
        items = {i.id: i for i in db.scalars(select(models.EquipmentItem))}
        assert set(items) == {1, 3, 4} and items[1].name == "릴선" and items[4].team_key == "sketch"
        assert (items[1].unit, items[1].note) == ("m", "야외용 30m"), "사라지는 쪽의 unit·note 가 남는 쪽에"
        ddl = {r[0]: r[1] for r in db.execute(text(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name LIKE 'equipment%'"))}
        assert set(ddl) == {"equipment_items", "equipment_runs"}, "옛 표(_old)가 안 남는다"
        assert "UNIQUE (team_key, name)" in ddl["equipment_items"] and "group_name" not in ddl["equipment_items"]
        assert "UNIQUE (retreat_id, item_id, group_name)" in ddl["equipment_runs"]
        idx = {r[0] for r in db.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name LIKE 'equipment%'"))}
        assert {"ix_equipment_items_team_key", "ix_equipment_runs_retreat_id", "ix_equipment_runs_item_id"} <= idx
        assert db.execute(text("PRAGMA foreign_key_check(equipment_runs)")).all() == []
    assert len(list(tmp_path.glob("backups/app-*.db"))) == 1


# ── 마. 겹침 ───────────────────────────────────────────────────────────

def test29_c03_겹치는_run_이_있으면_예외_없이_세어서_말하고_안_바꾼다(옛세상, tmp_path, monkeypatch, capsys):
    """마) 합치면 (회차·품목·묶음)이 겹치는 run 을 실제로 만든다 — run 2 의 묶음을 run 1
    과 같게 미리 채워 둔다(부분 옮김 상태). **순수 옛 모양에서는 겹침이 생길 수 없다** —
    옛 유니크가 (팀·묶음·이름)이라 같은 (팀·이름) 품목은 묶음이 반드시 다르고 run 의
    묶음은 그 품목 것으로 채워지기 때문이다. 그래서 칸을 먼저 붙이고 값을 다르게 둔다.
    본다: 예외 없이 1 로 끝남 · 「겹침 1건」 · 표가 옛 모양 그대로 · 수 그대로."""
    모듈 = _스크립트("비품묶음옮기기")
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        # 풀에서 받은 연결이 앱이 쓰던 것이면 SQLite 스키마 캐시가 표를 다시 세우기 전
        # 것일 수 있다 — 읽기 한 번이 캐시를 새로 읽게 한다(안 하면 첫 ALTER 가 옛
        # 스키마를 보고 「duplicate column」 을 낸다 · 스크립트는 늘 읽기가 먼저라 안 걸린다)
        db.execute(text("PRAGMA table_info(equipment_runs)")).all()
        db.execute(text("ALTER TABLE equipment_runs ADD COLUMN group_name VARCHAR(100) NOT NULL DEFAULT ''"))
        db.execute(text("UPDATE equipment_runs SET group_name = '집회 비품' WHERE id = 2"))
        db.commit()
        전 = _수(db)
        assert 모듈.셈(db)["겹침"] == 1, "③ 미리보기의 셈이 겹침을 본다"
        assert 모듈.옮기기(db, 실행=True) == 1
    with app_session() as db:
        assert 모듈.옛모양인가(db) and _수(db) == 전
    out = capsys.readouterr().out
    assert "겹치는 run 이 1건" in out and "옮기지 않았습니다" in out


def test29_c05_중간에_죽으면_첫_ALTER_까지_되돌아간다(옛세상, tmp_path, monkeypatch):
    """「한 트랜잭션」 이 말이 아니라 사실인가 — pysqlite 는 DML 앞에서만 BEGIN 을 내므로
    스크립트가 BEGIN 을 직접 낸다. 표를 다시 세우는 자리(create_all)에서 죽게 만들어,
    그 앞의 ALTER(칸 붙임)·UPDATE 까지 되돌아가는지 본다. 본다: 예외가 나고 · run 표에
    group_name 칸이 없고 · 수가 그대로."""
    모듈 = _스크립트("비품묶음옮기기")
    _사본준비(모듈, tmp_path, monkeypatch)

    def 죽는다(*a, **k):
        raise RuntimeError("시험 — 표를 세우다 죽음")
    monkeypatch.setattr(모듈.Base.metadata, "create_all", 죽는다)
    with app_session() as db:
        전 = _수(db)
        with pytest.raises(RuntimeError):
            모듈.옮기기(db, 실행=True)
        db.rollback()
    with app_session() as db:
        assert "group_name" not in {r[1] for r in db.execute(text("PRAGMA table_info(equipment_runs)"))}, "ALTER 도 되돌아간다"
        assert 모듈.옛모양인가(db) and _수(db) == 전


# ── 바. 두 번 ──────────────────────────────────────────────────────────

def test29_c04_두_번_돌리면_둘째는_옮길_것이_없다(옛세상, tmp_path, monkeypatch, capsys):
    """바) 둘째 판은 「옮길 것이 없습니다」 이고 수가 안 는다. 본다: 반환 0 · 문구 · 수."""
    모듈 = _스크립트("비품묶음옮기기")
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        모듈.옮기기(db, 실행=True)
    with app_session() as db:
        n = _수(db)
        capsys.readouterr()
        assert 모듈.옮기기(db, 실행=True) == 0
        assert _수(db) == n
    out = capsys.readouterr().out
    assert "옮길 것이 없습니다" in out and "옮겼습니다" not in out
    assert len(list(tmp_path.glob("backups/app-*.db"))) == 1, "둘째 판은 사본도 안 뜬다"


# ── 사. 앱을 띄워 화면이 같다 ─────────────────────────────────────────

def test29_d01_옮긴_뒤_화면이_200_이고_묶음과_줄이_전과_같다(옛세상, admin_client, tmp_path, monkeypatch):
    """사) 옛 모양에서 기대되는 묶음(집회 비품: 릴선·마이크 · 야외 세팅: 릴선 · 새친구 비품:
    릴선)을 먼저 적어 두고, 스크립트 뒤 /equipment 가 200 이며 같은 묶음·같은 줄인지
    본다. 본다: 상태 코드 · <h3> 묶음 이름 순서 · data-run 의 수."""
    기대_묶음 = ["새친구 비품", "야외 세팅", "집회 비품"]      # 부서 순서(스케치 0 · 헤브론 1) → 묶음 이름 가나다 — 키 알파벳순(h<s)이면 헤브론이 먼저 왔을 것
    모듈 = _스크립트("비품묶음옮기기")
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        assert 모듈.옮기기(db, 실행=True) == 0
    r = admin_client.get(f"/equipment?retreat_id={옛세상['retreat']}")
    assert r.status_code == 200
    page = r.text
    assert _묶음들(page) == 기대_묶음
    assert page.count('class="tickrow') == 4
    assert page.count('data-run="') == 4 and "릴선" in page and "마이크" in page
    # 남의 부서 칩은 품목의 team_key 로 — 새친구 비품은 스케치
    assert "4 스케치" in page and "5 헤브론" in page


# ── 아. 새 DB 는 처음부터 새 모양 ──────────────────────────────────────

def test29_e01_새로_만든_빈_DB_는_처음부터_새_유니크_둘을_갖는다(client, capsys):
    """아) create_all 로 선 표의 DDL 을 sqlite_master 에서 읽어 유니크 둘을 본다 — 그리고
    init_db 가 새 모양에서는 아무 경고도 안 찍고, 옛 모양(품목에 group_name)에서는 경고를
    찍되 표는 안 고친다. 본다: DDL 문자열 · 출력 · 옛 모양 유지."""
    from app.db import engine, init_db
    con = sqlite3.connect(engine.url.database)
    try:
        ddl = {r[0]: r[1] for r in con.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name LIKE 'equipment%'")}
        assert "UNIQUE (team_key, name)" in ddl["equipment_items"] and "group_name" not in ddl["equipment_items"]
        assert "UNIQUE (retreat_id, item_id, group_name)" in ddl["equipment_runs"]
        uniq = [r[0] for r in con.execute("PRAGMA index_list(equipment_runs)") if r[2] == 1]
        assert uniq, "③ 유니크 인덱스가 실제로 있어야 한다"
    finally:
        con.close()
    capsys.readouterr()
    init_db()
    assert "옛 모양" not in capsys.readouterr().out
    with app_session() as db:
        db.execute(text("DROP TABLE equipment_runs")); db.execute(text("DROP TABLE equipment_items"))
        db.execute(text(옛_품목)); db.execute(text(옛_run)); db.commit()
    init_db()
    out = capsys.readouterr().out
    assert "비품 표가 옛 모양입니다" in out and "비품묶음옮기기" in out
    with app_session() as db:
        assert "group_name" in {r[1] for r in db.execute(text("PRAGMA table_info(equipment_items)"))}, "부팅은 표를 안 고친다"


def test29_e02_옛_모양인_채로_띄우면_비품_화면은_500_이_아니라_말한다(옛세상, admin_client):
    """옛 모양의 표 위에서 새 코드의 /equipment 는 200 이고 「아직 못 읽습니다」 와
    스크립트 이름을 말한다 — 고치지는 않는다. 도막 1 의 비품옮기기.py 도 옛 모양이면 멈춘다.
    본다: 상태 코드 · 문구 · 표 그대로 · 도막 1 스크립트의 반환 1."""
    r = admin_client.get(f"/equipment?retreat_id={옛세상['retreat']}")
    assert r.status_code == 200 and "아직 못 읽습니다" in r.text and "비품묶음옮기기" in r.text
    assert 'class="tickrow' not in r.text
    도막1 = _스크립트("비품옮기기")
    with app_session() as db:
        assert 도막1.옮기기(db, 실행=True) == 1
        assert "group_name" in {r[1] for r in db.execute(text("PRAGMA table_info(equipment_items)"))}
