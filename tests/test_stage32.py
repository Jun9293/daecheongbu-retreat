"""비품 도막 4 — 총무 시트를 넣기 전에 걸리는 넷 (2026-09-11).

| 잰 것 | 어디 |
|---|---|
| 가·나 | 약 묶음이 의약품 하나로 모이고, 그래서 겹치는 run 을 따로 센다 |
| 다·라 | 멈출 때 묶음과 그 안 차례를 말한다 · 미리보기가 두 수를 다 찍는다 |
| 마 | 보관된 회차를 고르면 경고하고 **그대로 넣는다** |
| 바·사·아 | 비고가 품목이 아니라 회차(run)의 것이다 · 옮기기 |

**합성 TSV 만 쓴다** — 실제 시트(`data/*.real.tsv`)는 외부인 실명과 전화가 들어
있어 시험이 열지 않는다. 합성 자료의 사람 이름은 가명이다.

각 독스트링에 **그 줄이 실제로 무엇을 보는지** 적는다 — 막혀야 할 것이 막히는가 ·
막히면 안 되는 것이 통과하는가 · 검사가 볼 것을 보고 있는가(11-3).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import shutil

import pytest
from sqlalchemy import func, inspect, select, text

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
def 들여오기():
    return _스크립트("비품들여오기")


@pytest.fixture
def 비고옮기기():
    return _스크립트("비품비고옮기기")


def _사본준비(모듈, tmp_path, monkeypatch):
    """사본은 시험 폴더에 뜬다 — 세션이 여는 파일 = 사본을 뜰 파일 (test30 과 같다)."""
    from app.db import engine
    monkeypatch.setattr(모듈.config, "DATA_DIR", tmp_path)
    shutil.copy(engine.url.database, tmp_path / "app.db")
    monkeypatch.setattr(모듈.config, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")


def _수(db) -> dict[str, int]:
    셈 = lambda m: db.execute(select(func.count()).select_from(m)).scalar_one()  # noqa: E731
    return {"품목": 셈(models.EquipmentItem), "run": 셈(models.EquipmentRun)}


@pytest.fixture
def 회차(admin_client):
    """회차 하나 + 부서(총무) — 팀 키가 있어야 들여온다."""
    with app_session() as db:
        r = models.Retreat(name="도막4 회차", start_date=TODAY + dt.timedelta(days=30),
                           end_date=TODAY + dt.timedelta(days=33))
        db.add(r); db.flush()
        db.add(models.Department(retreat_id=r.id, key="chongmu", name="1 총무팀",
                                 color_tag="#888", sort_order=0))
        db.commit()
        return r.id


머리글 = ["구분", "챙길 물품", "현재 수량", "필요한 수량", "최종", "위치", "비고"]


def _tsv(tmp_path: pathlib.Path, 이름: str, 줄들: list[list[str]]) -> pathlib.Path:
    p = tmp_path / 이름
    p.write_text("\n".join("\t".join(칸 for 칸 in 줄) for 줄 in 줄들), encoding="utf-8")
    return p


def 총무자료(tmp_path, 줄들, 이름="총무.tsv"):
    return _tsv(tmp_path, 이름, [머리글] + 줄들)


# ── 가. 약 묶음이 하나로 모인다 ─────────────────────────────────────────

def test32_a01_약_묶음_셋이_의약품_하나로_모인다(들여오기, tmp_path):
    """가) 약 묶음 **셋을 실제로 심고** 잰다.

    본다 — ① 자료의 구분 값이 정말 셋이고 서로 다른가(아니면 이 시험은 「모았다」 를
    아무것도 안 재고 통과한다) ② 뽑은 뒤 `묶음이름` 이 셋 다 의약품인가
    ③ **약이 아닌 묶음은 안 딸려 오는가**(전부를 의약품으로 보내면 이 시험은
    통과하지만 화면이 망가진다)."""
    약구분 = ["소화제", "감기약", "연고"]
    assert len(set(약구분)) == 3, "심은 구분 값이 셋이 아니다"

    p = 총무자료(tmp_path, [[구분, f"약{i}", "", "1", "", "", ""]
                          for i, 구분 in enumerate(약구분)]
                          + [["사무용품", "볼펜", "", "10", "", "모빌랙", ""]])
    뽑은, _ = 들여오기.줄뽑기("총무", p)
    assert [줄["구분"] for 줄 in 뽑은] == 약구분 + ["사무용품"], "자료가 뜻대로 안 놓였다"

    묶음 = [들여오기.묶음이름(줄["구분"]) for 줄 in 뽑은]
    assert 묶음[:3] == ["의약품"] * 3, f"약 묶음이 안 모였다: {묶음[:3]}"
    assert 묶음[3] == "사무용품", "약이 아닌 묶음까지 딸려 왔다"


def test32_a02_진통제가_통제로_가지_않는다(들여오기):
    """가) **표는 「들어 있으면」 으로 보므로 순서가 뜻을 바꾼다.**
    「통제」 가 「진통제」 안에 들어 있어서, 진통제 줄이 조용히 통제 묶음으로 가고
    있었다.

    본다 — ① 진통제가 의약품인가 ② **통제는 그대로 통제인가**(둘을 같이 봐야
    「통제를 지워서 고친 것」 이 아님이 보인다)."""
    assert 들여오기.묶음이름("진통제") == "의약품"
    assert 들여오기.묶음이름("통제") == "통제"


# ── 나. 합쳐져 겹치는 run 을 따로 센다 ──────────────────────────────────

def _고른다(들여오기, retreat_id: int, p: pathlib.Path):
    with app_session() as db:
        뽑은, 셈 = 들여오기.줄뽑기("총무", p)
        만들것, 수 = 들여오기.고른다(db, db.get(models.Retreat, retreat_id), "총무", 뽑은)
    return 만들것, 수, 셈


def test32_a03_같은_약이_두_묶음에_있으면_합쳐진_수를_따로_센다(들여오기, tmp_path, 회차):
    """나) 같은 물품을 **두 약 구분에 겹치게 심어** 잰다.

    본다 — ① 두 줄을 읽었는데 만들 run 이 하나인가 ② 그 하나가 「합쳐진run」 으로
    세어지는가(「이미있는run」 이 아니다 — DB 에는 아무것도 없다)
    ③ **안 겹치는 자료에서는 그 수가 0 인가**(늘 세면 아무것도 안 재는 수다)."""
    겹침 = 총무자료(tmp_path, [
        ["소화제", "상비약 상자", "", "1", "", "", ""],
        ["감기약", "상비약 상자", "", "1", "", "", ""],     # 같은 물품 · 다른 약 구분
    ], "겹침.tsv")
    만들것, 수, 셈 = _고른다(들여오기, 회차, 겹침)
    assert 셈["넣을줄"] == 2, "두 줄을 읽어야 한다"
    assert len(만들것) == 1, "한 자리로 모여야 한다"
    assert 수["합쳐진run"] == 1, f"합쳐진 수를 안 셌다: {dict(수)}"
    assert 수.get("이미있는run", 0) == 0, "DB 에는 아무것도 없으므로 이쪽은 0 이다"

    # ③ 안 겹치면 0 — 같은 판에서 본다
    안겹침 = 총무자료(tmp_path, [
        ["소화제", "상비약 상자", "", "1", "", "", ""],
        ["감기약", "해열 패치", "", "1", "", "", ""],
    ], "안겹침.tsv")
    만들것2, 수2, _ = _고른다(들여오기, 회차, 안겹침)
    assert len(만들것2) == 2 and 수2.get("합쳐진run", 0) == 0


def test32_a04_합쳐진_수가_미리보기에_찍힌다(들여오기, tmp_path, monkeypatch, 회차, capsys):
    """나) 세는 것과 **찍는 것**은 다른 일이다 — 세어 놓고 안 찍으면 조용히 넘긴 것과
    같다. 본다: 미리보기 글에 그 수가 실제로 있는가."""
    p = 총무자료(tmp_path, [
        ["소화제", "상비약 상자", "", "1", "", "", ""],
        ["감기약", "상비약 상자", "", "1", "", "", ""],
    ])
    _사본준비(들여오기, tmp_path, monkeypatch)
    capsys.readouterr()
    with app_session() as db:
        assert 들여오기.들여오기(db, "총무", p, 회차, 실행=False) == 0
    out = capsys.readouterr().out
    assert "한 자리로 모인 것 1개" in out, f"합쳐진 수를 안 찍었다: {out}"


# ── 다. 멈출 때 묶음과 그 안 차례를 말한다 ──────────────────────────────

def test32_b01_멈출_때_묶음과_그_안_차례를_말하고_이름은_안_찍는다(들여오기, tmp_path):
    """다) 자국 있는 물품을 **묶음의 세 번째 자리에** 놓고 잰다.

    본다 — ① 묶음 이름이 말에 있는가 ② 그 안 차례가 맞는가(자료에서 세어 만든다)
    ③ **물품 이름과 사람 이름이 말에 없는가** — 찍으면 그 출력이 새는 자리다
    ④ 파일의 줄 번호도 여전히 있는가(둘 다 있어야 어느 쪽으로든 찾는다)."""
    앞줄 = [["사무용품", "볼펜", "", "1", "", "", ""],
           ["", "가위", "", "1", "", "", ""]]
    자국 = ["", "지민M 자", "", "1", "", "", ""]          # 가명
    p = 총무자료(tmp_path, 앞줄 + [자국])

    차례 = len(앞줄) + 1                                  # 자료에서 센다 — 박지 않는다
    줄번호 = 1 + len(앞줄) + 1                            # 머리글 1줄 + 앞줄 + 그 줄
    with pytest.raises(들여오기.멈춤) as e:
        들여오기.줄뽑기("총무", p)
    말 = str(e.value)
    assert "묶음 「사무용품」" in 말, f"묶음 이름이 없다: {말}"
    assert f"{차례}번째 물품" in 말, f"그 안 차례가 틀렸다: {말}"
    assert f"파일의 {줄번호}번째 줄" in 말
    assert "지민M 자" not in 말 and "지민" not in 말, "물품·사람 이름을 찍었다"


def test32_b02_표에_없는_구분에서_멈춰도_원래_값을_안_찍는다(들여오기, tmp_path):
    """다) **표에 없는 구분**과 자국이 겹친 줄 — `묶음이름` 이 거기서 또 멈추면
    사람이 엉뚱한 안내를 본다.

    본다 — ① 사람 자국 쪽 안내가 나오는가(묶음표 안내가 아니라) ② 원래 구분 값이
    말에 안 실리는가(거기에 성함이 섞여 있다) ③ 자국이 없으면 **묶음표 안내가
    제대로 나오는가**(② 쪽 — 안 그러면 표 안내를 죽인 것이다)."""
    구분 = "빌려준 분 지민M 쪽"                            # 가명
    with pytest.raises(들여오기.멈춤) as e:
        들여오기.줄뽑기("총무", 총무자료(tmp_path, [[구분, "하준M 자", "", "1", "", "", ""]], "a.tsv"))
    말 = str(e.value)
    assert "사람 자국" in 말 and "표에 없는 구분" in 말
    assert "지민" not in 말 and "하준" not in 말, "원래 값이나 물품 이름이 실렸다"

    # ③ 자국이 없으면 묶음표 쪽이 제대로 멈춘다
    뽑은, _ = 들여오기.줄뽑기("총무", 총무자료(tmp_path, [["듣보 구분", "자", "", "1", "", "", ""]], "b.tsv"))
    with pytest.raises(들여오기.멈춤) as e2:
        들여오기.묶음이름(뽑은[0]["구분"])
    assert "묶음표에 없는 구분" in str(e2.value)


# ── 라. 미리보기가 두 수를 다 찍는다 ────────────────────────────────────

def test32_b03_미리보기에_레코드_수와_물품_줄_수가_둘_다_있다(들여오기, tmp_path, monkeypatch, 회차, capsys):
    """라) 머리글 **위에 메모 두 줄**을 두고, 물품 줄과 빈 줄을 섞어 잰다.

    본다 — ① 파일의 레코드 수 ② 머리글 아래 줄 수 ③ 물품 이름이 있는 줄 수.
    **기대값은 자료를 실제로 세어 만든다** — 수를 시험에 박지 않는다(11-3)."""
    줄들 = [["메모", "", "", "", "", "", ""], ["메모2", "", "", "", "", "", ""],
           list(머리글),
           ["사무용품", "볼펜", "", "1", "", "", ""],
           ["", "", "", "", "", "", ""],                  # 물품 이름이 없는 줄
           ["", "가위", "", "1", "", "", ""]]
    p = _tsv(tmp_path, "메모.tsv", 줄들)
    레코드 = len(줄들)
    머리아래 = len(줄들) - 3
    물품줄 = sum(1 for 줄 in 줄들[3:] if 줄[1])

    _사본준비(들여오기, tmp_path, monkeypatch)
    capsys.readouterr()
    with app_session() as db:
        assert 들여오기.들여오기(db, "총무", p, 회차, 실행=False) == 0
    out = capsys.readouterr().out
    assert f"파일의 레코드 {레코드}개" in out, out
    assert f"머리글 아래 {머리아래}개" in out, out
    assert f"물품 이름이 있는 줄 {물품줄}개" in out, out


# ── 마. 보관된 회차 — 경고하고 그대로 넣는다 ────────────────────────────

def test32_c01_보관된_회차를_고르면_경고하고_그대로_넣는다(들여오기, tmp_path, monkeypatch, admin_client, capsys):
    """마) 보관된 회차와 안 보관된 회차를 **둘 다 세워 같은 판에서** 본다.

    본다 — ① 보관 쪽에 경고가 찍히는가 ② **그래도 들어가는가**(막는 것이 아니다)
    ③ 보관이 아닌 쪽에는 그 말이 **없는가** — 둘을 같이 봐야 늘 찍는 것이 아님이
    보인다 ④ `--실행` 에서도 찍는가(미리보기에서만 찍으면 사람이 지나친다)."""
    with app_session() as db:
        옛 = models.Retreat(name="보관된 회차", start_date=TODAY - dt.timedelta(days=400),
                           end_date=TODAY - dt.timedelta(days=398), is_archived=True)
        새 = models.Retreat(name="사는 회차", start_date=TODAY + dt.timedelta(days=30),
                           end_date=TODAY + dt.timedelta(days=33))
        db.add_all([옛, 새]); db.flush()
        for r in (옛, 새):
            db.add(models.Department(retreat_id=r.id, key="chongmu", name="1 총무팀",
                                     color_tag="#888", sort_order=0))
        db.commit()
        옛id, 새id = 옛.id, 새.id

    p = 총무자료(tmp_path, [["사무용품", "볼펜", "", "1", "", "", ""]])
    _사본준비(들여오기, tmp_path, monkeypatch)

    capsys.readouterr()
    with app_session() as db:
        assert 들여오기.들여오기(db, "총무", p, 옛id, 실행=False) == 0
    보관미리 = capsys.readouterr().out
    assert 들여오기.보관경고 in 보관미리 and "보관된 회차" in 보관미리, 보관미리

    with app_session() as db:
        전 = _수(db)
        assert 들여오기.들여오기(db, "총무", p, 옛id, 실행=True) == 0
    보관실행 = capsys.readouterr().out
    assert 들여오기.보관경고 in 보관실행, "--실행 에서는 안 찍었다"
    with app_session() as db:
        후 = _수(db)
        assert 후["run"] == 전["run"] + 1, "경고만 하고 막지 않는다 — 그대로 들어가야 한다"

    # ③ 보관이 아닌 회차에는 그 말이 없다
    with app_session() as db:
        assert 들여오기.들여오기(db, "총무", p, 새id, 실행=False) == 0
    assert 들여오기.보관경고 not in capsys.readouterr().out, "보관이 아닌데 경고가 떴다"


# ── 바·사. 비고는 회차(run)의 것이다 ────────────────────────────────────

def test32_d01_품목에는_비고_칸이_없다():
    """바) **모델에서 칸 목록을 직접 뽑아** 견준다 — 손으로 적은 목록과 안 견준다.

    본다 — ① `equipment_items` 에 note 가 없는가 ② `equipment_runs` 에는 있는가
    (둘을 같이 봐야 「지우기만 했다」 가 아님이 보인다)."""
    품목칸 = {c.name for c in inspect(models.EquipmentItem).local_table.columns}
    run칸 = {c.name for c in inspect(models.EquipmentRun).local_table.columns}
    assert "note" not in 품목칸, f"품목에 비고가 아직 있다: {sorted(품목칸)}"
    assert "note" in run칸, f"회차에 비고가 없다: {sorted(run칸)}"


def test32_d02_같은_품목이_두_묶음에_있으면_비고가_따로_붙는다(들여오기, tmp_path, monkeypatch, 회차):
    """사) 같은 물품을 **다른 두 묶음에** 놓고 비고를 다르게 적어 잰다.

    본다 — ① 품목은 하나인가(회차를 넘는 것이라 하나여야 한다) ② run 이 둘인가
    ③ **두 run 의 비고가 서로 다른가** — 품목에 있었다면 하나가 다른 하나를
    덮거나 「비어 있을 때만」 규칙에 걸려 한쪽이 사라졌다."""
    p = 총무자료(tmp_path, [
        ["사무용품", "가위", "", "1", "", "", "본부에 두는 것"],
        ["포토존", "가위", "", "1", "", "", "포토존에 두는 것"],
    ])
    _사본준비(들여오기, tmp_path, monkeypatch)
    with app_session() as db:
        assert 들여오기.들여오기(db, "총무", p, 회차, 실행=True) == 0
    with app_session() as db:
        assert _수(db) == {"품목": 1, "run": 2}
        붙은 = {r.group_name: r.note for r in db.scalars(select(models.EquipmentRun))}
        assert 붙은 == {"사무용품": "본부에 두는 것", "포토존": "포토존에 두는 것"}


# ── 아. 비고옮기기 ──────────────────────────────────────────────────────

def _옛칸을_세운다(db) -> None:
    """도막 4 이전 모양 — 품목에 비고 칸이 있던 때. 시험이 그 상태를 직접 만든다."""
    db.execute(text("ALTER TABLE equipment_items ADD COLUMN note TEXT"))
    db.commit()


def _옛비고(db, item_id: int) -> str | None:
    return db.execute(text("SELECT note FROM equipment_items WHERE id = :i"),
                      {"i": item_id}).scalar_one()


def test32_e01_비고옮기기는_미리보기_실행_그리고_두_번째에_0건이다(비고옮기기, tmp_path, monkeypatch, 회차):
    """아) 옛 모양을 **실제로 만들어** 세 판을 돌린다.

    본다 — ① 미리보기가 수만 찍고 **아무것도 안 바꾸는가**(사본도 안 뜬다)
    ② 실행 뒤 run 둘에 같은 값이 들어갔는가 ③ **칸이 걷혔는가**
    ④ 두 번째 판이 「옮길 것이 없습니다」 인가 ⑤ 이미 제 비고가 있는 run 은
    안 덮는가."""
    with app_session() as db:
        _옛칸을_세운다(db)
        item = models.EquipmentItem(team_key="chongmu", name="릴선")
        db.add(item); db.flush()
        for i, (묶음, 제비고) in enumerate((("사무용품", None), ("포토존", "사람이 적은 것"))):
            db.add(models.EquipmentRun(retreat_id=회차, item_id=item.id, group_name=묶음,
                                       note=제비고, sort_order=i))
        db.execute(text("UPDATE equipment_items SET note = '품목에 있던 말' WHERE id = :i"),
                   {"i": item.id})
        db.commit()
        item_id = item.id

    _사본준비(비고옮기기, tmp_path, monkeypatch)

    with app_session() as db:                       # ① 미리보기
        assert 비고옮기기.옮기기(db, 실행=False) == 0
        assert _옛비고(db, item_id) == "품목에 있던 말", "미리보기가 값을 건드렸다"
    assert not list(tmp_path.glob("backups/*.db")), "미리보기는 사본도 안 뜬다"

    with app_session() as db:                       # ② 실행
        assert 비고옮기기.옮기기(db, 실행=True) == 0
    assert list(tmp_path.glob("backups/*.db")), "실행은 사본을 먼저 뜬다"

    with app_session() as db:
        붙은 = {r.group_name: r.note for r in db.scalars(select(models.EquipmentRun))}
        assert 붙은 == {"사무용품": "품목에 있던 말", "포토존": "사람이 적은 것"}
        assert "note" not in {r[1] for r in db.execute(text(
            "PRAGMA table_info(equipment_items)"))}, "③ 칸이 안 걷혔다"

    with app_session() as db:                       # ④ 두 번째 판
        assert 비고옮기기.옮기기(db, 실행=True) == 0


def test32_e02_run_이_없는_품목의_비고는_따로_세고_걷지_않는다(비고옮기기, tmp_path, monkeypatch, 회차, capsys):
    """아) **run 이 하나도 없는 품목을 실제로 만들어** 잰다 — 그 비고는 갈 곳이 없다.

    본다 — ① 미리보기가 그 수를 따로 세는가 ② `--실행` 이 **아무것도 안 하고
    멈추는가**(걷으면 그 값이 사라진다) ③ 칸과 값이 그대로 남는가
    ④ run 을 만들어 주면 **그때는 지나가는가**(막기만 하면 영영 못 옮긴다)."""
    with app_session() as db:
        _옛칸을_세운다(db)
        외톨이 = models.EquipmentItem(team_key="chongmu", name="갈 곳 없는 품목")
        멀쩡 = models.EquipmentItem(team_key="chongmu", name="멀쩡한 품목")
        db.add_all([외톨이, 멀쩡]); db.flush()
        db.add(models.EquipmentRun(retreat_id=회차, item_id=멀쩡.id, group_name="사무용품"))
        db.execute(text("UPDATE equipment_items SET note = '어딘가에서 빌림'"))
        db.commit()
        외톨이id, 멀쩡id = 외톨이.id, 멀쩡.id

    _사본준비(비고옮기기, tmp_path, monkeypatch)

    capsys.readouterr()
    with app_session() as db:
        assert 비고옮기기.옮기기(db, 실행=False) == 0
        assert 비고옮기기.센다(db)["갈곳없는비고"] == 1
    assert "갈 곳이 없는 비고 1개" in capsys.readouterr().out

    with app_session() as db:                       # ② 실행은 멈춘다
        with pytest.raises(비고옮기기.멈춤) as e:
            비고옮기기.옮기기(db, 실행=True)
        assert "1개" in str(e.value)
        assert _옛비고(db, 외톨이id) == "어딘가에서 빌림", "③ 값이 사라졌다"
        assert "note" in {r[1] for r in db.execute(text(
            "PRAGMA table_info(equipment_items)"))}, "③ 칸을 걷어 버렸다"
        assert db.scalars(select(models.EquipmentRun)).one().note is None, "멈췄는데 옮겼다"

    with app_session() as db:                       # ④ run 을 만들어 주면 지나간다
        db.add(models.EquipmentRun(retreat_id=회차, item_id=외톨이id, group_name="포토존"))
        db.commit()
        assert 비고옮기기.옮기기(db, 실행=True) == 0
    with app_session() as db:
        assert {r.item_id: r.note for r in db.scalars(select(models.EquipmentRun))} == {
            멀쩡id: "어딘가에서 빌림", 외톨이id: "어딘가에서 빌림"}


# ── 검토가 잡은 자리 ────────────────────────────────────────────────────

def test32_e03_run_이_전부_제_비고를_가져도_값을_안_잃는다(비고옮기기, tmp_path, monkeypatch, 회차, capsys):
    """**검토가 재현한 값 손실 경로.** 품목의 run 이 **전부 제 비고를 갖고 있으면**
    UPDATE 가 한 줄도 안 걸리는데, 옛 판정은 「run 이 있나」 만 물어서 0 을 내고
    칸을 걷어 그 값을 가져갔다. 바깥 문과 안쪽 문이 서로 다른 것을 보던 자리다.

    본다 — ① 미리보기가 그 경우를 **갈 곳 없는 것으로 세는가**
    ② `--실행` 이 멈추는가 ③ **품목의 비고가 그대로 남는가**(핵심)
    ④ 그 run 의 비고를 비워 주면 **그때는 지나가고 값이 거기로 가는가**."""
    with app_session() as db:
        _옛칸을_세운다(db)
        item = models.EquipmentItem(team_key="chongmu", name="릴선")
        db.add(item); db.flush()
        db.add(models.EquipmentRun(retreat_id=회차, item_id=item.id,
                                   group_name="사무용품", note="사람이 적은 것"))
        db.execute(text("UPDATE equipment_items SET note = '품목에 있던 말'"))
        db.commit()
        item_id, run_id = item.id, db.scalars(select(models.EquipmentRun)).one().id

    _사본준비(비고옮기기, tmp_path, monkeypatch)
    capsys.readouterr()
    with app_session() as db:
        assert 비고옮기기.센다(db)["갈곳없는비고"] == 1, "① 이 경우를 안 셌다"
        assert 비고옮기기.센다(db)["run없는품목"] == 0, "run 은 있다 — 갈린 수를 따로 센다"
        assert 비고옮기기.옮기기(db, 실행=False) == 0
    assert "갈 곳이 없는 비고 1개" in capsys.readouterr().out

    with app_session() as db:
        with pytest.raises(비고옮기기.멈춤):
            비고옮기기.옮기기(db, 실행=True)
        assert _옛비고(db, item_id) == "품목에 있던 말", "③ 값이 사라졌다"
        assert db.get(models.EquipmentRun, run_id).note == "사람이 적은 것", "남의 말을 덮었다"

    # ④ 그 run 을 비워 주면 지나간다 — 막기만 하면 영영 못 옮긴다
    with app_session() as db:
        db.get(models.EquipmentRun, run_id).note = None
        db.commit()
        assert 비고옮기기.옮기기(db, 실행=True) == 0
    with app_session() as db:
        assert db.get(models.EquipmentRun, run_id).note == "품목에 있던 말"


def test32_e04_회차_쪽_칸이_없으면_무엇을_하라고_말한다(비고옮기기, tmp_path, monkeypatch, 회차):
    """**검토가 재현한 자리.** `equipment_runs.note` 는 부팅이 붙이는데, 서버를 한
    번도 안 켠 DB 에 이것부터 돌리면 질의가 터지고 `OperationalError` 갈래가
    **「표가 없다」** 는 엉뚱한 안내를 냈다 — 그 안내를 따라가면 빈 DB 를 새로
    만드는 길이다.

    본다 — ① 그 상태를 실제로 만들고(칸을 걷어) 부르면 **멈춤**인가
    ② 말이 서버를 켜라고 가리키는가 ③ 칸이 있으면 **그 문을 안 막는가**."""
    with app_session() as db:
        _옛칸을_세운다(db)
        db.execute(text("ALTER TABLE equipment_runs DROP COLUMN note"))
        db.commit()
    _사본준비(비고옮기기, tmp_path, monkeypatch)
    with app_session() as db:
        with pytest.raises(비고옮기기.멈춤) as e:
            비고옮기기.옮기기(db, 실행=False)
        assert "서버를 한 번 켠 뒤" in str(e.value), f"무엇을 하라고 안 말했다: {e.value}"

    # ③ 칸을 도로 붙이면 그 문은 안 막는다
    with app_session() as db:
        db.execute(text("ALTER TABLE equipment_runs ADD COLUMN note TEXT"))
        db.commit()
        assert 비고옮기기.옮기기(db, 실행=False) == 0


def test32_a05_묶음표에_짧은_말이_긴_말_위에_있지_않다(들여오기):
    """**검토가 봐 둘 것으로 짚은 자리.** `test32_a02` 는 진통제/통제 **그 짝만**
    잰다 — 다음에 짧은 말이 위에 들어오면 아무것도 안 걸리고, 걸리는 모양이
    「조용히 다른 묶음으로 간다」 라 화면에도 자국이 안 남는다.

    본다 — ① 표 전체에서 **짧은 말이 긴 말보다 위에 있는 짝**이 하나도 없는가
    ② 표가 비어 있지 않은가(비면 ①이 아무것도 안 보고 통과한다)
    ③ 같은 찾을 말이 두 줄에 있지 않은가."""
    표 = 들여오기.묶음표
    assert len(표) > 20, f"표가 너무 짧다 — 이 시험이 아무것도 안 보고 있다: {len(표)}"
    말들 = [찾 for 찾, _ in 표]
    assert len(set(말들)) == len(말들), "같은 찾을 말이 두 줄에 있다"

    거꾸로 = [(짧, 긴) for i, 짧 in enumerate(말들)
             for 긴 in 말들[i + 1:] if 짧 in 긴]
    assert not 거꾸로, f"짧은 말이 긴 말 위에 있다 — 긴 쪽이 조용히 짧은 쪽으로 간다: {거꾸로}"


def test32_a06_묶음표의_찾을_말에_사람_자국이_없다(들여오기):
    """가) 찾을 말은 **깨끗한 낱말뿐**이어야 한다(4-18) — 값 전체를 열쇠로 두면
    빌려주신 분의 성함이 이 공개 저장소에 들어온다.

    본다 — ① 표의 모든 찾을 말이 `사람자국` 을 안 지나는가 ② 그 그물이 실제로
    무언가를 잡기는 하는가(가명으로 한 번 재 본다 — 늘 False 를 내는 그물이면
    ①은 아무것도 안 보고 통과한다)."""
    assert 들여오기.사람자국("지민M"), "② 그물이 아무것도 안 잡는다"
    걸린 = [찾 for 찾, _ in 들여오기.묶음표 if 들여오기.사람자국(찾)]
    assert not 걸린, f"찾을 말에 사람 자국이 있다: {걸린}"
