"""비품 시트 들여오기 (4-18 · 2026-09-11).

수용 기준 가~하 를 하나씩 잰다. **합성 TSV 만 쓴다** — 실제 시트(`data/*.real.tsv`)는
외부인 실명과 전화가 들어 있어 시험이 건드리지 않는다. 합성 자료의 사람 이름은 가명이다.

각 시험의 독스트링이 실제로 무엇을 보는지 적는다 — 막혀야 할 것이 막히는가 ·
통과해야 할 것이 통과하는가 · 검사가 볼 것을 보고 있는가(센 것이 0 이면 실패다).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import shutil

import pytest
from sqlalchemy import func, select

from app import models
from tests.conftest import app_session

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = dt.date.today()


def _스크립트(이름: str):
    spec = importlib.util.spec_from_file_location(이름, ROOT / f"scripts/{이름}.py")
    모듈 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(모듈)
    return 모듈


@pytest.fixture
def 모듈():
    return _스크립트("비품들여오기")


def _사본준비(모듈, tmp_path, monkeypatch):
    """사본은 시험 폴더에 뜬다 — test24 와 같은 손질(세션이 여는 파일 = 뜰 파일)."""
    from app.db import engine
    monkeypatch.setattr(모듈.config, "DATA_DIR", tmp_path)
    shutil.copy(engine.url.database, tmp_path / "app.db")
    monkeypatch.setattr(모듈.config, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")


def _count(db, model, *where) -> int:
    q = select(func.count()).select_from(model)
    for w in where:
        q = q.where(w)
    return db.execute(q).scalar_one()


def _수(db) -> dict[str, int]:
    return {"품목": _count(db, models.EquipmentItem), "run": _count(db, models.EquipmentRun)}


@pytest.fixture
def 회차(admin_client):
    """회차 하나 + 부서 셋(총무·코람데오·헤브론) — 팀 키가 있어야 들여온다."""
    with app_session() as db:
        r = models.Retreat(name="들여오기 회차", start_date=TODAY + dt.timedelta(days=30),
                           end_date=TODAY + dt.timedelta(days=33))
        db.add(r); db.flush()
        ids = {"retreat": r.id}
        for i, (key, name) in enumerate((("chongmu", "1 총무팀"), ("koram", "6 코람데오"),
                                         ("hebron", "5 헤브론"))):
            d = models.Department(retreat_id=r.id, key=key, name=name, color_tag="#888", sort_order=i)
            db.add(d); db.flush(); ids[key] = d.id
        db.commit()
    return ids


def _tsv(tmp_path: pathlib.Path, 이름: str, 줄들: list[list[str]]) -> pathlib.Path:
    p = tmp_path / 이름
    p.write_text("\n".join("\t".join(c for c in 줄) for 줄 in 줄들), encoding="utf-8")
    return p


# 총무 시트를 흉내 낸 머리글 — 실제 시트처럼 첫 칸은 구분이 아니라 메모이고,
# 「최종」 에는 날짜가 붙어 있다(이름으로 찾되 포함으로 맞는지 함께 잰다)
총무머리 = ["예산 : 50만원", "챙길 물품", "현재 수량", "필요한 수량", "최종(08.16)", "위치", "비고"]


def 총무자료(tmp_path, 줄들, 이름="총무.tsv"):
    return _tsv(tmp_path, 이름, [총무머리] + 줄들)


# ── 가. 머리글이 빠지면 멈춘다 ──────────────────────────────────────────

def test30_a01_머리글이_하나_빠지면_무엇이_없는지_말하고_멈춘다(모듈, tmp_path):
    """가) 「위치」 를 실제로 빼고 돌린다. 본다: 멈춤 예외인가 · 빠진 이름을 말하는가 ·
    있는 머리글로 돌리면 안 멈추는가(② 쪽)."""
    빠진 = [c for c in 총무머리 if c != "위치"]
    p = _tsv(tmp_path, "빠짐.tsv", [빠진, ["사무용품", "볼펜", "", "10", "", ""]])
    with pytest.raises(모듈.멈춤) as e:
        모듈.줄뽑기("총무", p)
    assert "위치" in str(e.value)
    # ② 머리글이 다 있으면 통과한다
    ok = 총무자료(tmp_path, [["사무용품", "볼펜", "", "10", "", "모빌랙", ""]])
    뽑은, 셈 = 모듈.줄뽑기("총무", ok)
    assert len(뽑은) == 1 and 셈["넣을줄"] == 1


# ── 나. 합친 칸을 물려받는다 ────────────────────────────────────────────

def test30_a02_구분_칸이_비면_바로_위의_값을_물려받는다(모듈, tmp_path):
    """나) 합친 칸을 흉내 낸 자료(첫 줄에만 구분, 다음 둘은 빈칸)로 잰다.
    본다: 세 줄의 구분이 모두 첫 줄 값인가 · 새 구분이 나오면 거기서 바뀌는가."""
    p = 총무자료(tmp_path, [
        ["사무용품", "볼펜", "", "10", "", "모빌랙", ""],
        ["", "매직", "", "2", "", "모빌랙", ""],
        ["", "가위", "", "4", "", "모빌랙", ""],
        ["포토존", "폴라로이드", "", "1", "", "", ""],
    ])
    뽑은, _ = 모듈.줄뽑기("총무", p)
    assert [줄["구분"] for 줄 in 뽑은] == ["사무용품", "사무용품", "사무용품", "포토존"]


# ── 다. 묶음표에 없으면 멈춘다 ──────────────────────────────────────────

def test30_a03_묶음표에_없는_구분이면_멈추고_그_값을_말한다(모듈, tmp_path, monkeypatch, 회차):
    """다) 표에 없는 구분 값을 **자료에 실제로 넣어** 돌린다. 본다: 멈춤이고 그 값이
    말에 있는가 · 그 줄 앞의 멀쩡한 줄도 함께 막히는가(하나라도 못 넣으면 전부 안 넣는다) ·
    표에 있는 값만 있으면 통과하는가(② 쪽)."""
    assert 모듈.묶음이름("사무용품") == "사무용품", "③ 표가 실제로 무엇을 돌려준다"
    p = 총무자료(tmp_path, [
        ["사무용품", "볼펜", "", "10", "", "모빌랙", ""],
        ["듣도보도 못한 구분", "무엇", "", "1", "", "", ""],
    ])
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        뽑은, _ = 모듈.줄뽑기("총무", p)          # 뽑기는 통과한다 — 표는 그다음이다
        with pytest.raises(모듈.멈춤) as e:
            모듈.고른다(db, db.get(models.Retreat, 회차["retreat"]), "총무", 뽑은)
        assert "듣도보도 못한 구분" in str(e.value)
        assert _수(db) == {"품목": 0, "run": 0}, "① 앞의 멀쩡한 줄도 안 들어간다"
        # ② 표에 있는 값만 있으면 통과한다
        ok = 총무자료(tmp_path, [["사무용품", "볼펜", "", "10", "", "모빌랙", ""]], "ok.tsv")
        뽑은2, _ = 모듈.줄뽑기("총무", ok)
        만들것, _ = 모듈.고른다(db, db.get(models.Retreat, 회차["retreat"]), "총무", 뽑은2)
        assert [줄["묶음"] for 줄 in 만들것] == ["사무용품"]


# ── 라. 위치는 허용 목록으로 ────────────────────────────────────────────

def test30_a04_위치는_허용_목록에_있는_것만_들어간다(모듈, tmp_path, monkeypatch, 회차):
    """라) 목록에 있는 값(모빌랙)과 없는 값(가명 사람 이름)을 한 자료에 둘 다 넣는다.
    본다: 저장된 location 이 하나는 값이고 하나는 None 인가 · 「위치버림」 이 1 인가."""
    p = 총무자료(tmp_path, [
        ["사무용품", "볼펜", "", "10", "", "모빌랙", ""],
        ["사무용품", "매직", "", "2", "", "박민준M", ""],
    ])
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        뽑은, _ = 모듈.줄뽑기("총무", p)
        만들것, 수 = 모듈.고른다(db, db.get(models.Retreat, 회차["retreat"]), "총무", 뽑은)
        assert 수["위치버림"] == 1
        assert {줄["이름"]: 줄["위치"] for 줄 in 만들것} == {"볼펜": "모빌랙", "매직": None}


# ── 마. 비고의 사람 자국 ────────────────────────────────────────────────

def test30_a05_비고는_전화나_이름_자국이_있으면_통째로_버린다(모듈, tmp_path, monkeypatch, 회차):
    """마) 셋 다 밟는다 — 전화꼴 · 이름 뒤 M · 깨끗한 비고. 본다: 저장될 note 셋 ·
    「비고버림」 이 2 인가 · 깨끗한 것은 글자가 그대로인가."""
    p = 총무자료(tmp_path, [
        ["사무용품", "볼펜", "", "10", "", "", "010-1234-5678 로 연락"],
        ["사무용품", "매직", "", "2", "", "", "박민준M 이 가져옴"],
        ["사무용품", "가위", "", "4", "", "", "큰 가위로 사야 함"],
    ])
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        뽑은, _ = 모듈.줄뽑기("총무", p)
        만들것, 수 = 모듈.고른다(db, db.get(models.Retreat, 회차["retreat"]), "총무", 뽑은)
        assert 수["비고버림"] == 2
        assert {줄["이름"]: 줄["비고"] for 줄 in 만들것} == {
            "볼펜": None, "매직": None, "가위": "큰 가위로 사야 함"}


# ── 바. 품목 이름의 사람 자국 ───────────────────────────────────────────

def test30_a06_품목_이름에_사람_자국이_있으면_멈춘다(모듈, tmp_path):
    """바) 이름은 버릴 수 없는 칸이라 멈춘다. 실제로 넣어서 잰다.
    본다: 멈춤이고 「품목 이름」 을 말하는가 · 깨끗한 이름은 통과하는가(② 쪽)."""
    p = 총무자료(tmp_path, [["사무용품", "박민준M : 새벽기도 악보", "", "20", "", "", ""]])
    with pytest.raises(모듈.멈춤) as e:
        모듈.줄뽑기("총무", p)
    assert "품목 이름" in str(e.value)
    ok = 총무자료(tmp_path, [["사무용품", "새벽기도 악보", "", "20", "", "", ""]], "ok.tsv")
    뽑은, _ = 모듈.줄뽑기("총무", ok)
    assert 뽑은[0]["이름"] == "새벽기도 악보"


# ── 사. 미리보기는 아무것도 안 바꾼다 ──────────────────────────────────

def test30_b01_미리보기는_아무것도_안_바꾸고_수만_찍는다(모듈, tmp_path, monkeypatch, 회차, capsys):
    """사) 앞뒤로 품목 수·run 수가 같고 사본이 안 뜬다. 본다: 두 수의 dict · 출력의
    줄 수와 묶음별 수 · 품목 이름이 안 찍히는가 · backups/ 가 비어 있는가."""
    p = 총무자료(tmp_path, [
        ["사무용품", "볼펜", "", "10", "", "모빌랙", ""],
        ["", "매직", "", "2", "", "모빌랙", ""],
        ["포토존", "폴라로이드", "", "1", "", "", ""],
    ])
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        전 = _수(db)
        assert 모듈.들여오기(db, "총무", p, 회차["retreat"], 실행=False) == 0
        후 = _수(db)
    assert 전 == 후 == {"품목": 0, "run": 0}
    out = capsys.readouterr().out
    assert "읽은 줄 3개 · 물품 이름이 있는 줄 3개 · 건너뛴 빈 줄 0개" in out
    assert "사무용품 2" in out and "포토존 1" in out
    assert "새로 설 품목 3개" in out and "새로 설 run 3개" in out
    assert "볼펜" not in out and "폴라로이드" not in out, "품목 이름은 안 찍는다"
    assert not list(tmp_path.glob("backups/*.db")), "미리보기는 사본도 안 뜬다"


# ── 아. 이미 있는 품목은 다시 쓴다 ─────────────────────────────────────

def test30_b02_같은_팀_이름의_품목이_있으면_품목은_안_늘고_run_만_는다(모듈, tmp_path, monkeypatch, 회차):
    """아) 이미 있는 품목을 먼저 심어서 잰다. 본다: 실행 뒤 품목 1 그대로 · run 1 늘어남 ·
    새 run 의 item_id 가 심어 둔 그 품목인가 · 「다시쓸품목」 이 1 인가."""
    with app_session() as db:
        item = models.EquipmentItem(team_key="chongmu", name="볼펜")
        db.add(item); db.commit(); 품목id = item.id
    p = 총무자료(tmp_path, [["사무용품", "볼펜", "", "10", "", "모빌랙", ""]])
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        전 = _수(db)
        assert 모듈.들여오기(db, "총무", p, 회차["retreat"], 실행=True) == 0
    with app_session() as db:
        assert _수(db) == {"품목": 전["품목"], "run": 전["run"] + 1}
        run = db.scalars(select(models.EquipmentRun)).one()
        assert run.item_id == 품목id and run.group_name == "사무용품" and run.quantity == "10"
    # 「다시쓸품목」 이 실제로 세어지는가 — 독스트링이 말한 그 수다
    with app_session() as db:
        뽑은, _ = 모듈.줄뽑기("총무", p)
        _, 수 = 모듈.고른다(db, db.get(models.Retreat, 회차["retreat"]), "총무", 뽑은)
        assert 수["다시쓸품목"] == 1 and 수.get("새품목", 0) == 0


# ── 자. 이미 있는 run 은 안 덮는다 ─────────────────────────────────────

def test30_b03_같은_회차_품목_묶음의_run_은_덮지_않고_건너뛴다(모듈, tmp_path, monkeypatch, 회차):
    """자) 사람이 앱에서 체크한 run 을 먼저 심는다. 본다: 그 run 의 수량·체크·누가·언제가
    하나도 안 바뀌는가 · run 수가 안 느는가 · 「건너뛸run」 이 1 인가 · 묶음이 다른 줄은
    새로 서는가(② 쪽)."""
    when = dt.datetime(2026, 9, 1, 3, 0)
    with app_session() as db:
        item = models.EquipmentItem(team_key="chongmu", name="볼펜")
        db.add(item); db.flush()
        db.add(models.EquipmentRun(retreat_id=회차["retreat"], item_id=item.id, group_name="사무용품",
                                   quantity="사람이 적은 수량", checked=True, checked_by_name="박민준",
                                   checked_at=when, sort_order=0))
        db.commit()
    p = 총무자료(tmp_path, [
        ["사무용품", "볼펜", "", "10", "", "모빌랙", "시트가 적은 비고"],
        ["포토존", "볼펜", "", "3", "", "", ""],          # 묶음이 다르면 새로 선다
        # **한 판에서 새 품목이 두 묶음에 나오는 갈래** — 세션이 autoflush=False 라
        # 방금 만든 품목을 둘째 줄이 못 찾으면 품목이 둘 선다 (도막 1 에서 검토가 잡은 자리)
        ["사무용품", "새 자", "", "1", "", "", ""],
        ["포토존", "새 자", "", "2", "", "", ""],
    ])
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        뽑은, _ = 모듈.줄뽑기("총무", p)
        _, 수 = 모듈.고른다(db, db.get(models.Retreat, 회차["retreat"]), "총무", 뽑은)
        assert 수["건너뛸run"] == 1, "이미 있는 (회차·품목·묶음) 하나를 건너뛴다"
        assert 수["새품목"] == 1, "새 자 는 두 줄에 나와도 품목 하나다"
        assert 모듈.들여오기(db, "총무", p, 회차["retreat"], 실행=True) == 0
    with app_session() as db:
        assert _수(db) == {"품목": 2, "run": 4}
        새자 = db.scalars(select(models.EquipmentItem)
                         .where(models.EquipmentItem.name == "새 자")).all()
        assert len(새자) == 1, "한 판에서 두 묶음에 나와도 품목은 하나다"
        볼펜 = db.scalars(select(models.EquipmentItem)
                        .where(models.EquipmentItem.name == "볼펜")).one()
        옛 = db.scalars(select(models.EquipmentRun).where(
            models.EquipmentRun.group_name == "사무용품",
            models.EquipmentRun.item_id == 볼펜.id)).one()
        assert (옛.quantity, 옛.checked, 옛.checked_by_name, 옛.checked_at) == (
            "사람이 적은 수량", True, "박민준", when), "사람이 적은 것을 시트가 못 민다"
        새 = db.scalars(select(models.EquipmentRun).where(
            models.EquipmentRun.group_name == "포토존",
            models.EquipmentRun.item_id == 옛.item_id)).one()
        assert 새.quantity == "3" and 새.checked is False


def test30_b02b_비고는_빈_note_만_채우고_적힌_것은_안_민다(모듈, tmp_path, monkeypatch, 회차):
    """(검토가 짚음) 이미 있는 품목의 note 가 **비었으면** 시트의 비고가 채우고,
    **적혀 있으면** 그대로 둔다. 운영에서 이 갈래를 밟는 줄이 있다.
    본다: 두 품목의 note · 품목 수가 안 느는가."""
    with app_session() as db:
        db.add(models.EquipmentItem(team_key="chongmu", name="볼펜"))                 # note 없음
        db.add(models.EquipmentItem(team_key="chongmu", name="매직", note="사람이 적은 메모"))
        db.commit()
    p = 총무자료(tmp_path, [
        ["사무용품", "볼펜", "", "10", "", "", "시트가 적은 비고"],
        ["사무용품", "매직", "", "2", "", "", "시트가 밀면 안 되는 비고"],
    ])
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        assert 모듈.들여오기(db, "총무", p, 회차["retreat"], 실행=True) == 0
    with app_session() as db:
        note = {i.name: i.note for i in db.scalars(select(models.EquipmentItem))}
        assert note == {"볼펜": "시트가 적은 비고", "매직": "사람이 적은 메모"}
        assert _수(db)["품목"] == 2


# ── 차. 최종 x 는 included 를 끈다 ─────────────────────────────────────

def test30_b04_최종이_x_면_included_가_꺼지고_행은_남는다(모듈, tmp_path, monkeypatch, 회차):
    """차) x · X · 그 밖의 값 셋을 한 자료에 둔다. 본다: included 셋 · 행이 셋 다 남는가 ·
    x 가 아닌 값(사람 이름)이 어디에도 안 들어가는가."""
    p = 총무자료(tmp_path, [
        ["사무용품", "볼펜", "", "10", "x", "모빌랙", ""],
        ["사무용품", "매직", "", "2", "X", "모빌랙", ""],
        ["사무용품", "가위", "", "4", "박민준", "모빌랙", ""],
    ])
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        assert 모듈.들여오기(db, "총무", p, 회차["retreat"], 실행=True) == 0
    with app_session() as db:
        runs = {r.item.name: r for r in db.scalars(select(models.EquipmentRun))}
        assert len(runs) == 3, "행은 셋 다 남는다"
        assert (runs["볼펜"].included, runs["매직"].included, runs["가위"].included) == (False, False, True)
        담긴글 = " ".join(f"{r.group_name}{r.quantity or ''}{r.location or ''}"
                        f"{r.item.note or ''}{n}" for n, r in runs.items())
        assert "박민준" not in 담긴글, "최종 칸의 그 밖의 값은 안 들여온다"


# ── 카. 코람데오 — 담당자로 팀을 가른다 ────────────────────────────────

def test30_b05_코람데오는_헤브론_담당만_헤브론이고_개인_이름은_안_들어간다(모듈, tmp_path, monkeypatch, 회차):
    """카) 담당자가 헤브론인 줄과 가명 개인 이름인 줄을 둔다. 본다: 저장된 team_key 둘 ·
    담당자의 개인 이름이 품목·묶음·위치·비고 어디에도 없는가(저장된 값을 실제로 읽는다)."""
    p = _tsv(tmp_path, "코람.tsv", [
        ["구역", "물품", "필요 수량", "부족한 수량", "체크", "담당자", "비고"],
        ["4층 창고", "스탠드 마이크", "2", "", "", "헤브론", ""],
        ["4층 창고", "기타 케이블", "3", "", "", "박민준", ""],
        ["워십룸", "인이어", "1", "", "", "", ""],
    ])
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        assert 모듈.들여오기(db, "코람데오", p, 회차["retreat"], 실행=True) == 0
    with app_session() as db:
        팀 = {r.item.name: r.item.team_key for r in db.scalars(select(models.EquipmentRun))}
        assert 팀 == {"스탠드 마이크": "hebron", "기타 케이블": "koram", "인이어": "koram"}
        모든글 = " ".join(
            f"{i.name}{i.note or ''}{i.unit or ''}" for i in db.scalars(select(models.EquipmentItem))
        ) + " ".join(
            f"{r.group_name}{r.quantity or ''}{r.location or ''}{r.checked_by_name or ''}"
            for r in db.scalars(select(models.EquipmentRun)))
        assert "박민준" not in 모든글, "담당자의 개인 이름은 아무 칸에도 안 들어간다"
        assert all(r.checked is False for r in db.scalars(select(models.EquipmentRun)))


# ── 타. 두 번 돌리면 ───────────────────────────────────────────────────

def test30_b06_두_번_돌리면_둘째는_들여올_것이_없다(모듈, tmp_path, monkeypatch, 회차, capsys):
    """타) 둘째 판은 「들여올 것이 없습니다」 이고 수가 안 는다. 본다: 반환 0 · 문구 ·
    앞뒤 수 · 사본이 첫 판의 하나뿐인가."""
    p = 총무자료(tmp_path, [
        ["사무용품", "볼펜", "", "10", "", "모빌랙", ""],
        ["포토존", "폴라로이드", "", "1", "", "", ""],
    ])
    _사본준비(모듈, tmp_path, monkeypatch)
    with app_session() as db:
        모듈.들여오기(db, "총무", p, 회차["retreat"], 실행=True)
    with app_session() as db:
        n = _수(db)
        capsys.readouterr()
        assert 모듈.들여오기(db, "총무", p, 회차["retreat"], 실행=True) == 0
        assert _수(db) == n == {"품목": 2, "run": 2}
    out = capsys.readouterr().out
    assert "들여올 것이 없습니다" in out and "넣었습니다" not in out
    assert len(list(tmp_path.glob("backups/app-*.db"))) == 1, "둘째 판은 사본도 안 뜬다"


# ── 파. 부서 키가 없으면 멈춘다 ────────────────────────────────────────

def test30_b07_부서_키가_없으면_무엇이_없는지_말하고_멈춘다(모듈, tmp_path, admin_client):
    """파) 코람데오·헤브론 부서가 없는 회차에 코람데오 시트를 돌린다. 본다: 멈춤이고
    없는 키를 말하는가 · 아무것도 안 들어갔는가 · 키가 있으면 통과하는가(② 쪽은 b05)."""
    with app_session() as db:
        r = models.Retreat(name="부서 없는 회차", start_date=TODAY, end_date=TODAY + dt.timedelta(days=2))
        db.add(r); db.flush()
        db.add(models.Department(retreat_id=r.id, key="chongmu", name="1 총무팀",
                                 color_tag="#888", sort_order=0))
        db.commit(); rid = r.id
    p = _tsv(tmp_path, "코람.tsv", [
        ["구역", "물품", "필요 수량", "부족한 수량", "체크", "담당자", "비고"],
        ["4층 창고", "스탠드 마이크", "2", "", "", "헤브론", ""],
    ])
    with app_session() as db:
        with pytest.raises(모듈.멈춤) as e:
            모듈.들여오기(db, "코람데오", p, rid, 실행=True)
        말 = str(e.value)
        assert "koram" in 말 and "hebron" in 말
        assert _수(db) == {"품목": 0, "run": 0}


# ── 실제 시트 파일은 저장소 밖이다 ─────────────────────────────────────

def test30_c01_재료_파일은_저장소에_안_들어간다(모듈):
    """0) `data/*.real.*` 이 .gitignore 에 있고, 시험이 실제 시트를 안 쓴다.
    본다: .gitignore 의 그 줄 · 이 시험 파일이 real 파일 이름을 안 담는가(③)."""
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/*.real.*" in ignore, "확장자마다 적으면 새 확장자가 뚫린다"
    # **파일 전체를 훑는다** — 아래에 새 시험이 붙어도 재진다. 찾는 것은 「여는 자리」 가
    # 아니라 **재료 파일의 이름꼴**이다: 이 스크립트는 경로를 모듈 함수에 넘겨서 읽으므로
    # 시험 쪽에 read_·open( 이 안 나온다(검토가 짚음). 이 단언문 자신이 걸리지 않게
    # 찾는 말은 조각을 이어 만든다 (10장 「글자를 찾는 시험은 코드와 설명을 못 가린다」).
    나 = pathlib.Path(__file__).read_text(encoding="utf-8")
    자국들 = ("비품-" + "총무", "비품-" + "코람데오")     # 재료 파일의 이름 (조각을 이어 만든다)
    걸린곳 = [줄 for 줄 in 나.splitlines() if any(자 in 줄 for 자 in 자국들)]
    assert not 걸린곳, f"시험은 합성 자료만 쓴다 — 실제 시트를 가리키는 줄: {걸린곳}"
    # ③ 이 그물이 실제로 무엇을 잡는지 — 잡힐 줄을 하나 만들어 본다
    보기 = f"모듈.줄뽑기('총무', ROOT / 'data/{자국들[0]}.real.tsv')"
    assert any(자 in 보기 for 자 in 자국들), "③ 그물이 실제 시트 표기를 잡는다"
