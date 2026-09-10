"""비품 (4-18) — 표 둘 · 옮기기 · 화면 · 체크리스트에서 걷기.

지시의 수용 기준 가~아 를 하나씩 잰다. 각 시험의 독스트링이 **실제로 무엇을 보는지**
적는다 — 막혀야 할 것이 막히는가 · 통과해야 할 것이 통과하는가 · 검사가 볼 것을
보고 있는가(센 것이 0 이면 실패다).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import shutil
import sqlite3

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import models
from app.domain import permissions as perm
from tests.conftest import app_session, login_as, make_user

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = dt.date.today()


def _스크립트(이름: str):
    spec = importlib.util.spec_from_file_location(이름, ROOT / f"scripts/{이름}.py")
    모듈 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(모듈)
    return 모듈


def _사본준비(모듈, tmp_path, monkeypatch):
    """사본은 시험 폴더에 뜬다 — test24 와 같은 손질 (세션이 여는 파일 = 뜰 파일)."""
    from app.db import engine
    monkeypatch.setattr(모듈.config, "DATA_DIR", tmp_path)
    shutil.copy(engine.url.database, tmp_path / "app.db")
    monkeypatch.setattr(모듈.config, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")


def _count(db, model, *where) -> int:
    q = select(func.count()).select_from(model)
    for w in where:
        q = q.where(w)
    return db.execute(q).scalar_one()


def _셈(db) -> dict[str, int]:
    return {
        "checklists": _count(db, models.Checklist),
        "items": _count(db, models.ChecklistItem),
        "eq_items": _count(db, models.EquipmentItem),
        "eq_runs": _count(db, models.EquipmentRun),
        "moved": _count(db, models.Checklist, models.Checklist.moved_at.is_not(None)),
    }


@pytest.fixture
def 세상(admin_client):
    """회차 하나 · 부서 둘(키) · 리더 둘 · 체크리스트 넷 — 부서 있는 둘, 업무에 딸린
    하나(옮기면 안 된다), 부서 없는 하나. 이름은 가명이다."""
    with app_session() as db:
        r = models.Retreat(name="비품 회차", start_date=TODAY + dt.timedelta(days=30),
                           end_date=TODAY + dt.timedelta(days=33))
        db.add(r); db.flush()
        ids = {"retreat": r.id}
        for i, (key, name) in enumerate((("hebron", "5 헤브론"), ("sketch", "4 스케치"))):
            d = models.Department(retreat_id=r.id, key=key, name=name, color_tag="#888", sort_order=i)
            db.add(d); db.flush(); ids[key] = d.id
        db.commit()
    ids["hebron_lead"] = make_user("헤브론 리더", "01077770401", "general",
                                   departments=[(ids["hebron"], perm.LEAD)])
    ids["sketch_lead"] = make_user("스케치 리더", "01077770402", "general",
                                   departments=[(ids["sketch"], perm.LEAD)])
    with app_session() as db:
        r = db.get(models.Retreat, ids["retreat"])
        task = models.Task(retreat_id=r.id, title="준비물 업무", department_id=ids["hebron"],
                           due_date=TODAY + dt.timedelta(days=31), status="대기",
                           blocked_by_task_ids=[], related_department_ids=[])
        db.add(task); db.flush()
        when = dt.datetime(2026, 9, 1, 3, 0)
        a = models.Checklist(retreat_id=r.id, name="집회 비품", department_id=ids["hebron"], sort_order=1)
        b = models.Checklist(retreat_id=r.id, name="새친구 비품", department_id=ids["sketch"], sort_order=2)
        c = models.Checklist(retreat_id=r.id, name="업무 준비물", department_id=ids["hebron"],
                             task_id=task.id, sort_order=3)
        d = models.Checklist(retreat_id=r.id, name="공통 비품", department_id=None, sort_order=4)
        db.add_all([a, b, c, d]); db.flush()
        db.add_all([
            models.ChecklistItem(checklist_id=a.id, label="무선마이크", quantity="4개", checked=True,
                                 checked_by_id=ids["hebron_lead"], checked_by_name="박민준",
                                 checked_at=when, sort_order=0),
            models.ChecklistItem(checklist_id=a.id, label="마이크 배터리", quantity="인당 2개", sort_order=1),
            models.ChecklistItem(checklist_id=b.id, label="이름표", quantity="60장", sort_order=0),
            models.ChecklistItem(checklist_id=b.id, label="릴선", sort_order=1),
            models.ChecklistItem(checklist_id=c.id, label="업무용 물건", sort_order=0),
            models.ChecklistItem(checklist_id=d.id, label="릴선", quantity="2개", sort_order=0),
        ])
        db.commit()
        ids.update({"a": a.id, "b": b.id, "c": c.id, "d": d.id})
    return ids


# ── 가·나. 유니크 둘 — 실제로 넣어서 잰다 ────────────────────────────────

def test28_a01_같은_팀_이름은_거절되고_팀이_다르면_선다(admin_client):
    """가) ① (team_key, name) 을 두 번 넣으면 IntegrityError ② 팀이 다르면 둘 다 선다.
    (묶음이 품목에서 회차로 옮겨 간 뒤의 모양 — 4-18.) 본다: 두 번째 add+commit 이
    예외인가, 셋째 뒤 행 수가 2인가."""
    with app_session() as db:
        db.add(models.EquipmentItem(team_key="hebron", name="릴선")); db.commit()
        db.add(models.EquipmentItem(team_key="hebron", name="릴선"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(models.EquipmentItem(team_key="sketch", name="릴선")); db.commit()
        assert _count(db, models.EquipmentItem, models.EquipmentItem.name == "릴선") == 2


def test28_a02_같은_회차_같은_품목_같은_묶음은_한_번만(admin_client, 세상):
    """나) (retreat_id, item_id, group_name) 을 두 번 넣으면 거절, 묶음만 다르면 둘 다
    선다. 본다: 두 번째 commit 이 예외이고 셋째 뒤 행 수가 2 인가."""
    with app_session() as db:
        item = models.EquipmentItem(team_key="hebron", name="스탠드")
        db.add(item); db.flush()
        db.add(models.EquipmentRun(retreat_id=세상["retreat"], item_id=item.id, group_name="집회")); db.commit()
        db.add(models.EquipmentRun(retreat_id=세상["retreat"], item_id=item.id, group_name="집회"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(models.EquipmentRun(retreat_id=세상["retreat"], item_id=item.id, group_name="야외")); db.commit()
        assert _count(db, models.EquipmentRun, models.EquipmentRun.item_id == item.id) == 2


# ── 부팅 마이그레이션 — 두 번 띄워도 같다 ────────────────────────────────

def test28_b01_두_번_띄워도_표와_칸이_그대로다(client):
    """init_db 를 두 번 불러도 예외가 없고, checklists.moved_at 이 한 번만 있고
    equipment 표 둘이 있다. 본다: PRAGMA table_info 의 칸 이름 목록."""
    from app.db import engine, init_db
    init_db(); init_db()
    con = sqlite3.connect(engine.url.database)
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(checklists)")]
        assert cols.count("moved_at") == 1
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        assert {"equipment_items", "equipment_runs"} <= tables
    finally:
        con.close()


# ── 다·라·마. 옮기기 ───────────────────────────────────────────────────

def test28_c01_미리보기는_아무것도_안_바꾸고_이름을_안_찍는다(세상, tmp_path, monkeypatch, capsys):
    """다) 앞뒤 행 수(체크리스트 · 항목 · equipment 둘 · moved_at 수) 전부 같다.
    본다: 다섯 수의 dict 가 같은가, 출력에 항목 수는 있고 사람 이름은 없는가."""
    모듈 = _스크립트("비품옮기기")
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        전 = _셈(db)
        assert 전["items"] == 6 and 전["eq_runs"] == 0, "③ 옮길 것이 실제로 있어야 한다"
        assert 모듈.옮기기(db, 실행=False) == 0
        후 = _셈(db)
    assert 전 == 후
    out = capsys.readouterr().out
    assert "옮길 체크리스트 3개 · 항목 5개 · 새로 설 라이브러리 행 5개" in out
    assert "박민준" not in out and "집회 비품" in out
    assert not list(tmp_path.glob("backups/*.db")), "미리보기는 사본도 안 뜬다"


def test28_c02_실행하면_항목_체크_수량이_그대로_옮겨진다(세상, tmp_path, monkeypatch):
    """라) --실행 뒤: 항목 5 → EquipmentRun 5, 체크된 수 1 → 1, 수량 글자 그대로,
    업무에 딸린 것은 안 옮기고, 옮긴 셋에 moved_at 이 찍히며, 원래 행은 남는다.
    본다: 수량 문자열 집합 · checked 수 · moved_at 유무 · 사본 파일."""
    모듈 = _스크립트("비품옮기기")
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        전 = _셈(db)
        assert 모듈.옮기기(db, 실행=True) == 0
        후 = _셈(db)
        assert 후["checklists"] == 전["checklists"] and 후["items"] == 전["items"], "지우지 않는다"
        assert 후["eq_runs"] == 5 and 후["eq_items"] == 5 and 후["moved"] == 3
        runs = list(db.scalars(select(models.EquipmentRun)))
        assert sum(1 for r in runs if r.checked) == 1
        assert {r.quantity for r in runs} == {"4개", "인당 2개", "60장", None, "2개"}
        mic = next(r for r in runs if r.item.name == "무선마이크")
        assert mic.checked_by_name == "박민준" and mic.checked_by_id == 세상["hebron_lead"]
        assert mic.checked_at == dt.datetime(2026, 9, 1, 3, 0) and mic.item.team_key == "hebron"
        assert mic.group_name == "집회 비품"                       # 묶음은 run 의 것
        # 부서 없는 체크리스트는 team_key "" 로
        common = next(r for r in runs if r.group_name == "공통 비품")
        assert common.item.team_key == "" and common.item.name == "릴선"
        # 같은 이름이라도 팀이 다르면 딴 품목이다 — 새친구(sketch)의 릴선과 공통("")의 릴선
        assert _count(db, models.EquipmentItem, models.EquipmentItem.name == "릴선") == 2
        assert db.get(models.Checklist, 세상["c"]).moved_at is None, "업무에 딸린 것은 그대로"
        assert db.get(models.Checklist, 세상["a"]).moved_at is not None
    assert len(list(tmp_path.glob("backups/app-*.db"))) == 1, "바꾸기 직전에 사본 하나"


def test28_c03_두_번_돌리면_둘째는_옮길_것이_없다(세상, tmp_path, monkeypatch, capsys):
    """마) 둘째 판은 0건 — 「옮길 것이 없습니다」 를 말하고 equipment_runs 가 안 는다.
    본다: 출력 문구와 행 수."""
    모듈 = _스크립트("비품옮기기")
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        모듈.옮기기(db, 실행=True)
        n = _count(db, models.EquipmentRun)
        capsys.readouterr()
        assert 모듈.옮기기(db, 실행=True) == 0
        assert _count(db, models.EquipmentRun) == n == 5
    out = capsys.readouterr().out
    assert "옮길 것이 없습니다" in out and "성공" not in out


def test28_c04_한_체크리스트에_같은_이름이_둘이면_세고_건너뛴다(세상, tmp_path, monkeypatch, capsys):
    """(검토가 짚음) 세션이 autoflush=False 라 방금 add 한 run 을 select 가 못 봐서
    둘째 항목이 (회차·품목) 유니크에 걸렸었다. 본다: 예외 없이 끝나고 그 품목의 run 이
    1개, 출력에 「건너뛴 항목 1개」, 나머지는 그대로 옮겨졌는가."""
    with app_session() as db:
        db.add(models.ChecklistItem(checklist_id=세상["a"], label="무선마이크", quantity="한 개 더", sort_order=9))
        db.commit()
    모듈 = _스크립트("비품옮기기")
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        assert 모듈.옮기기(db, 실행=True) == 0
        mic = db.scalar(select(models.EquipmentItem).where(models.EquipmentItem.name == "무선마이크"))
        assert _count(db, models.EquipmentRun, models.EquipmentRun.item_id == mic.id) == 1
        assert _count(db, models.EquipmentRun) == 5, "겹친 하나만 빠지고 나머지는 그대로"
        assert db.get(models.Checklist, 세상["a"]).moved_at is not None
    out = capsys.readouterr().out
    assert "건너뛴 항목 1개" in out and "항목 5개" in out


# ── 바. 체크리스트 화면에서 걷는다 ────────────────────────────────────

def test28_d01_옮긴_체크리스트는_안_보이고_안_옮긴_것은_보인다(admin_client, 세상):
    """바) moved_at 이 찍힌 것은 /checklists 응답에 없고, 안 찍힌 것은 있다 — 둘 다 밟는다."""
    with app_session() as db:
        db.get(models.Checklist, 세상["a"]).moved_at = dt.datetime(2026, 9, 10)
        db.commit()
    page = admin_client.get(f"/checklists?retreat_id={세상['retreat']}").text
    # 제목 마크업으로 본다 — 만들기 폼의 예시 글(「예: 1일차 집회 비품」)이 같은 낱말을 품는다
    assert '<h3 style="margin:0">새친구 비품</h3>' in page and '<h3 style="margin:0">업무 준비물</h3>' in page
    assert '<h3 style="margin:0">집회 비품</h3>' not in page
    assert 'href="/equipment"' in page


# ── 사·아. 화면과 권한 ───────────────────────────────────────────────────

@pytest.fixture
def 옮긴세상(세상, tmp_path, monkeypatch):
    모듈 = _스크립트("비품옮기기")
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        모듈.옮기기(db, 실행=True)
        runs = {r.item.name + "/" + r.group_name: r.id for r in db.scalars(select(models.EquipmentRun))}
    세상["run_mic"] = runs["무선마이크/집회 비품"]
    세상["run_tag"] = runs["이름표/새친구 비품"]
    return 세상


def test28_e01_다른_부서_키의_비품은_403_이고_단추가_없다(client, 옮긴세상):
    """사) 스케치 리더가 헤브론 비품을 고치려 하면 403 — 막히는 쪽을 실제로 만든다.
    그 계정의 화면에는 헤브론 줄이 보이되 단추(toggle·include 폼)가 없고, 자기
    부서 줄에는 있다. 본다: 상태 코드 · 두 줄의 form action 유무."""
    ids = 옮긴세상
    login_as(client, "01077770402")
    client.get(f"/board?retreat_id={ids['retreat']}")
    for path in ("toggle", "include", "edit"):
        assert client.post(f"/equipment/{ids['run_mic']}/{path}", data={"quantity": "x"},
                           follow_redirects=False).status_code == 403
    page = client.get(f"/equipment?retreat_id={ids['retreat']}").text
    assert "무선마이크" in page, "③ 남의 부서 줄도 보인다 — 숨기지 않고 흐리게"
    assert f'action="/equipment/{ids["run_mic"]}/toggle"' not in page
    assert f'action="/equipment/{ids["run_mic"]}/include"' not in page
    assert f'action="/equipment/{ids["run_tag"]}/toggle"' in page, "② 자기 부서 줄에는 단추가 있다"
    # 자기 부서는 실제로 바뀐다
    assert client.post(f"/equipment/{ids['run_tag']}/toggle", follow_redirects=False).status_code == 303
    with app_session() as db:
        run = db.get(models.EquipmentRun, ids["run_tag"])
        assert run.checked and run.checked_by_name == "스케치 리더"


def test28_e02_이번_회차_불필요는_행을_남기고_흐리게_보인다(admin_client, 옮긴세상):
    """아) include 를 끄면 행 수가 그대로이고 화면에 「이번 회차 불필요」 로 보이며
    다시 넣기 단추가 있다. 본다: 앞뒤 행 수 · included 값 · 화면 글자."""
    ids = 옮긴세상
    with app_session() as db:
        전 = _count(db, models.EquipmentRun)
    r = admin_client.post(f"/equipment/{ids['run_mic']}/include", follow_redirects=False)
    assert r.status_code == 303
    with app_session() as db:
        assert _count(db, models.EquipmentRun) == 전 == 5
        assert db.get(models.EquipmentRun, ids["run_mic"]).included is False
    page = admin_client.get(f"/equipment?retreat_id={ids['retreat']}").text
    assert "이번 회차 불필요" in page and "다시 넣기" in page
    assert "무선마이크" in page and "지우기" not in page and "삭제" not in page
    # 되살리면 다시 포함
    admin_client.post(f"/equipment/{ids['run_mic']}/include", follow_redirects=False)
    with app_session() as db:
        assert db.get(models.EquipmentRun, ids["run_mic"]).included is True


def test28_e03_사이드바에_비품이_있고_수량_위치를_저장한다(admin_client, 옮긴세상):
    """화면 뼈대 — 사이드바 항목 · 묶음 · 수량/위치 저장."""
    ids = 옮긴세상
    page = admin_client.get(f"/equipment?retreat_id={ids['retreat']}").text
    assert 'href="/equipment"' in page and "집회 비품" in page and "인당 2개" in page
    admin_client.post(f"/equipment/{ids['run_mic']}/edit",
                      data={"quantity": "5개", "location": "본당 창고"}, follow_redirects=False)
    with app_session() as db:
        run = db.get(models.EquipmentRun, ids["run_mic"])
        assert (run.quantity, run.location) == ("5개", "본당 창고")


# ── 새 표의 글자 칸을 개발 DB 게이트가 본다 ──────────────────────────────

def 글자칸(model) -> set[tuple[str, str]]:
    """모델에서 글자 칸을 뽑는다 — 손으로 적어 두면 칸이 늘 때 목록이 갈린다 (도막 2)."""
    from sqlalchemy import String, Text
    t = model.__table__
    return {(t.name, c.name) for c in t.columns if isinstance(c.type, (String, Text))}


def test28_f01_새_표의_글자_칸은_제외하지_않고_기본으로_본다(client):
    """check_dev_db 의 제외칸에 equipment 표가 없고, 볼칸들 이 새 표의 글자 칸을 **전부**
    낸다. 목록은 손으로 적지 않고 모델의 String/Text 칸에서 뽑는다 — 칸이 늘면 이
    시험도 따라 는다. 본다: 제외칸 키 · 모델에서 뽑은 집합 ⊆ 볼칸들 · 뽑은 수가 0 이 아님."""
    from app.db import engine
    모듈 = _스크립트("check_dev_db")
    assert not [k for k in 모듈.제외칸 if k[0].startswith("equipment")]
    con = sqlite3.connect(engine.url.database)
    try:
        본다 = set(모듈.볼칸들(con))
    finally:
        con.close()
    기대 = 글자칸(models.EquipmentItem) | 글자칸(models.EquipmentRun)
    assert len(기대) >= 8, "③ 뽑은 것이 있어야 한다"
    assert ("equipment_items", "unit") in 기대 and ("equipment_runs", "group_name") in 기대
    assert 기대 <= 본다, 기대 - 본다
