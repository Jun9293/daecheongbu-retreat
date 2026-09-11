"""비품 도막 5 — 갈린 약 묶음 합치기 · 비고 보이기 · 사람칸 (2026-09-11).

| 잰 것 | 어디 |
|---|---|
| 가~마 | `scripts/비품묶음합치기.py` — 무엇이 옮겨지고 무엇이 안 옮겨지나 |
| 바 | `/equipment` 가 비고를 보이나 · **없으면 그 줄을 안 그리나** |
| 사 | `scripts/check_handoff.py` — 사람칸이 없거나 빠지거나 비면 빨간가 |

**합성 자료만 쓴다** — 실제 시트와 운영 DB 는 시험이 열지 않는다. 사람 이름은 가명이다.

각 독스트링에 **그 줄이 실제로 무엇을 보는지** 적는다 — 막혀야 할 것이 막히는가 ·
막히면 안 되는 것이 통과하는가 · 검사가 볼 것을 보고 있는가(11-3).
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
def 합치기():
    return _스크립트("비품묶음합치기")


@pytest.fixture
def 손넘김():
    return _스크립트("check_handoff")


def _사본준비(모듈, tmp_path, monkeypatch):
    """사본은 시험 폴더에 뜬다 — 세션이 여는 파일 = 사본을 뜰 파일 (test32 와 같다)."""
    from app.db import engine
    monkeypatch.setattr(모듈.config, "DATA_DIR", tmp_path)
    shutil.copy(engine.url.database, tmp_path / "app.db")
    monkeypatch.setattr(모듈.config, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")


@pytest.fixture
def 회차(admin_client):
    with app_session() as db:
        r = models.Retreat(name="도막5 회차", start_date=TODAY + dt.timedelta(days=30),
                           end_date=TODAY + dt.timedelta(days=33))
        db.add(r); db.flush()
        db.add(models.Department(retreat_id=r.id, key="chongmu", name="1 총무팀",
                                 color_tag="#888", sort_order=0))
        db.commit()
        return r.id


def _심는다(회차id: int, 줄들: list[tuple[str, str]], **칸) -> None:
    """(묶음, 물품이름) 목록을 그대로 심는다 — 물품 하나에 run 하나."""
    with app_session() as db:
        for i, (묶음, 이름) in enumerate(줄들):
            item = db.scalars(select(models.EquipmentItem)
                              .where(models.EquipmentItem.name == 이름)).first()
            if item is None:
                item = models.EquipmentItem(team_key="chongmu", name=이름)
                db.add(item); db.flush()
            db.add(models.EquipmentRun(retreat_id=회차id, item_id=item.id,
                                       group_name=묶음, sort_order=i, **칸))
        db.commit()


def _묶음별(회차id: int) -> dict[str, int]:
    with app_session() as db:
        rows = db.execute(
            select(models.EquipmentRun.group_name, func.count())
            .where(models.EquipmentRun.retreat_id == 회차id)
            .group_by(models.EquipmentRun.group_name)).all()
    return {g: n for g, n in rows}


# ── 가. 약 이름 묶음이 의약품 하나로 ────────────────────────────────────

def test33_a01_약_묶음_셋이_의약품_하나로_모인다(합치기, tmp_path, monkeypatch, 회차):
    """가) 약 이름 묶음 **셋을 실제로 심고** 잰다.

    본다 — ① 심은 뒤 그 셋이 정말 따로 서 있는가(아니면 「모았다」 를 아무것도
    안 재고 통과한다) ② 실행 뒤 셋이 의약품 하나가 되는가 ③ **약이 아닌 묶음은
    안 딸려 오는가**(전부를 옮겨도 ②는 통과한다)."""
    _심는다(회차, [("소화제", "소화제 상자"), ("감기약", "감기약 통"),
                 ("연고", "연고"), ("사무용품", "볼펜"), ("포토존", "폴라로이드")])
    전 = _묶음별(회차)
    assert {"소화제", "감기약", "연고"} <= set(전), f"약 묶음 셋이 안 심겼다: {전}"
    assert sum(전[g] for g in ("소화제", "감기약", "연고")) == 3

    _사본준비(합치기, tmp_path, monkeypatch)
    with app_session() as db:
        assert 합치기.합치기(db, 회차, [], 실행=True) == 0

    후 = _묶음별(회차)
    assert 후 == {"의약품": 3, "사무용품": 1, "포토존": 1}, f"모이지 않았다: {후}"


def test33_a02_두_번째_판은_합칠_것이_없다(합치기, tmp_path, monkeypatch, 회차, capsys):
    """라) 같은 판을 한 번 더 돌린다.

    본다 — ① 「합칠 것이 없습니다」 가 나오는가 ② 묶음이 그대로인가(한 번 더
    돌려도 아무 일이 없어야 두 번 돌린 사람이 안 다친다)."""
    _심는다(회차, [("소화제", "소화제 상자")])
    _사본준비(합치기, tmp_path, monkeypatch)
    with app_session() as db:
        assert 합치기.합치기(db, 회차, [], 실행=True) == 0
    앞 = _묶음별(회차)
    capsys.readouterr()
    with app_session() as db:
        assert 합치기.합치기(db, 회차, [], 실행=True) == 0
    assert "합칠 것이 없습니다" in capsys.readouterr().out
    assert _묶음별(회차) == 앞


# ── 나. --더 로 짚은 물품만 ─────────────────────────────────────────────

def test33_b01_더로_짚은_물품의_run_만_옮겨진다(합치기, tmp_path, monkeypatch, 회차):
    """나) 같은 「통제」 묶음에 **약 하나와 약 아닌 하나**를 나란히 심는다.

    본다 — ① 짚은 물품의 run 만 의약품으로 가는가 ② **같은 묶음의 다른 run 은
    그대로인가**(묶음째 옮기면 ①은 통과하지만 엉뚱한 것이 약이 된다)."""
    _심는다(회차, [("통제", "진통제"), ("통제", "통제선 테이프")])
    _사본준비(합치기, tmp_path, monkeypatch)
    with app_session() as db:
        assert 합치기.합치기(db, 회차, ["진통제"], 실행=True) == 0

    with app_session() as db:
        간곳 = {r.item.name: r.group_name for r in db.scalars(select(models.EquipmentRun))}
    assert 간곳 == {"진통제": "의약품", "통제선 테이프": "통제"}


def test33_b02_없는_이름을_주면_멈추고_아무것도_안_바꾼다(합치기, tmp_path, monkeypatch, 회차):
    """나) **막아야 하는 쪽.** 오타 하나를 조용히 흘리면 사람은 짚었다고 믿는데
    그 run 은 갈린 채 남는다 — 화면에서야 알아차린다.

    본다 — ① 멈추는가 ② 그 이름이 말에 있는가 ③ **DB 가 하나도 안 바뀌었는가**
    (같은 판에 옮길 것이 있어도 멈춰야 한다) ④ 있는 이름이면 지나가는가."""
    _심는다(회차, [("통제", "진통제"), ("소화제", "소화제 상자")])
    전 = _묶음별(회차)
    _사본준비(합치기, tmp_path, monkeypatch)
    with app_session() as db:
        with pytest.raises(합치기.멈춤) as e:
            합치기.합치기(db, 회차, ["없는 물품"], 실행=True)
        assert "없는 물품" in str(e.value)
    assert _묶음별(회차) == 전, "③ 멈췄는데 바뀌었다"
    assert not list(tmp_path.glob("backups/*.db")), "③ 멈췄는데 사본을 떴다"

    # ④ 있는 이름이면 지나간다 — 막기만 하면 영영 못 짚는다
    with app_session() as db:
        assert 합치기.합치기(db, 회차, ["진통제"], 실행=True) == 0
    assert _묶음별(회차) == {"의약품": 2}


# ── 다. 겹치면 아무것도 안 한다 ─────────────────────────────────────────

def test33_c01_겹치면_건수를_말하고_아무것도_안_한다(합치기, tmp_path, monkeypatch, 회차, capsys):
    """다) **같은 품목**이 의약품과 소화제에 하나씩 선 자료를 만든다 — 합치면
    (회차·품목·묶음)이 같아진다.

    본다 — ① 멈추는가 ② 건수가 말에 있는가 ③ **DB 가 하나도 안 바뀌었는가**
    (유니크에 걸려 터지기 전에 세어 말해야 한다) ④ **안 겹치는 자료에서는
    지나가는가** — 둘을 같은 판에서 봐야 늘 멈추는 것이 아님이 보인다."""
    _심는다(회차, [("의약품", "상비약 상자"), ("소화제", "상비약 상자")])
    전 = _묶음별(회차)
    _사본준비(합치기, tmp_path, monkeypatch)
    with app_session() as db:
        with pytest.raises(합치기.멈춤) as e:
            합치기.합치기(db, 회차, [], 실행=True)
    말 = str(e.value)
    assert "1건" in 말, f"건수를 안 말했다: {말}"
    assert _묶음별(회차) == 전, "③ 멈췄는데 바뀌었다"
    assert not list(tmp_path.glob("backups/*.db")), "멈췄는데 사본을 떴다"

    # ④ 겹치지 않는 품목을 하나 더 심으면 그것만으로는 여전히 겹치므로,
    #    겹치는 쪽을 치우고 다시 본다 — 같은 판에서 지나가는 것을 잰다
    with app_session() as db:
        겹친run = db.scalars(select(models.EquipmentRun)
                           .where(models.EquipmentRun.group_name == "의약품")).one()
        db.delete(겹친run); db.commit()
    with app_session() as db:
        assert 합치기.합치기(db, 회차, [], 실행=True) == 0
    assert _묶음별(회차) == {"의약품": 1}


# ── 마. 미리보기가 사람이 고를 수 있게 보인다 ───────────────────────────

def test33_d01_미리보기에_통제_묶음의_물품_이름이_나온다(합치기, tmp_path, monkeypatch, 회차, capsys):
    """마) 「통제」 묶음에 **자국 없는 이름과 자국 있는 이름**을 함께 심는다.

    본다 — ① 자국 없는 이름은 **그대로** 나오는가(사람이 `--더` 에 옮겨 적어야 한다)
    ② 자국 있는 이름은 **이름 대신** 「자국 있음」 인가 ③ 가린 수를 세는가
    ④ 미리보기가 아무것도 안 바꾸는가."""
    _심는다(회차, [("통제", "진통제"), ("통제", "지민M 약통"), ("소화제", "소화제 상자")])
    전 = _묶음별(회차)
    _사본준비(합치기, tmp_path, monkeypatch)
    capsys.readouterr()
    with app_session() as db:
        assert 합치기.합치기(db, 회차, [], 실행=False) == 0
    out = capsys.readouterr().out

    assert "진통제" in out, f"자국 없는 이름이 안 나왔다: {out}"
    assert "(자국 있음)" in out, "자국 있는 이름을 안 가렸다"
    assert "지민M 약통" not in out and "지민" not in out, "가린다고 해 놓고 찍었다"
    assert "1개는 이름에 사람 자국이 있어" in out, "③ 가린 수를 안 셌다"
    assert _묶음별(회차) == 전, "④ 미리보기가 바꿨다"
    assert not list(tmp_path.glob("backups/*.db")), "미리보기는 사본도 안 뜬다"


def test33_d02_미리보기가_묶음마다의_수와_갈_묶음을_찍는다(합치기, tmp_path, monkeypatch, 회차, capsys):
    """마) 사람이 고르려면 지금 무엇이 서 있는지가 먼저다.

    본다 — ① 묶음마다 run 수 ② 의약품으로 갈 묶음과 그 수 ③ 옮길 run 수.
    **기대값은 심은 자료에서 세어 만든다** — 수를 시험에 박지 않는다(11-3)."""
    줄들 = [("소화제", "소화제 상자"), ("감기약", "감기약 통"),
           ("감기약", "목캔디"), ("사무용품", "볼펜")]
    _심는다(회차, 줄들)
    갈것 = [g for g, _ in 줄들 if g in ("소화제", "감기약")]
    _사본준비(합치기, tmp_path, monkeypatch)
    capsys.readouterr()
    with app_session() as db:
        assert 합치기.합치기(db, 회차, [], 실행=False) == 0
    out = capsys.readouterr().out
    assert f"감기약 {갈것.count('감기약')}" in out
    assert f"소화제 {갈것.count('소화제')}" in out
    assert f"옮길 run {len(갈것)}개" in out, out


# ── 바. 화면이 비고를 보인다 ────────────────────────────────────────────

def test33_e01_비고가_있는_run_만_그_줄이_선다(admin_client, 회차):
    """바) 비고가 **있는 run 과 없는 run** 을 같은 묶음에 심고 화면 글을 읽는다.

    본다 — ① 있는 쪽의 비고 글이 화면에 있는가 ② **없는 쪽 때문에 빈 줄이
    서지 않는가** — 「비고가 있는 줄 수」 와 「그 줄이 그려진 수」 가 같은지로
    센다(빈 칸이 늘어서면 목록이 안 읽힌다)."""
    _심는다(회차, [("사무용품", "볼펜")], note="빌린 것 — 끝나고 돌려준다")
    _심는다(회차, [("사무용품", "가위")])
    # 회차는 **쿼리 파라미터로만** 바꾼다 (`app/deps.py` 의 `get_current_retreat`).
    # 전에는 없는 라우트에 POST 하고 있었다 — 맞는 회차를 본 것은 기본 고르기에
    # 우연히 걸려서였다(검토 4). 그 줄은 「바꿨다」 고 적힌 죽은 줄이었다
    글 = admin_client.get(f"/equipment?retreat_id={회차}").text
    assert "빌린 것 — 끝나고 돌려준다" in 글, "① 비고가 화면에 없다"
    assert "볼펜" in 글 and "가위" in 글, "두 줄 다 그려져야 한다"

    # ② 비고 줄은 비고가 있는 run 수만큼만 — 빈 줄을 안 그린다
    그린수 = 글.count('class="sub ticknote"')
    with app_session() as db:
        있는수 = sum(1 for r in db.scalars(select(models.EquipmentRun)) if r.note)
    assert 그린수 == 있는수 == 1, f"비고 줄 {그린수}개 · 비고 있는 run {있는수}개"


# ── 사. check_handoff ───────────────────────────────────────────────────

온전한판 = """사람이 할 것
노트북에서 직접: 비품묶음합치기.py 를 돌린다 (6장)
관리자 권한: 없음
정할 것: 없음
막혀서 못 한 것: 없음

작성 시각: 2026-09-11 (KST)
"""


def test33_f01_사람칸이_없거나_빠지거나_비면_빨갛다(손넘김):
    """사) **넷을 같은 판에서 본다** — 칸 없는 판 · 줄 빠진 판 · 값 빈 판 ·
    온전한 판. 온전한 판이 없으면 「늘 빨간 검사」 이고, 나머지 셋이 없으면
    「늘 초록인 검사」 다. 둘 다 아무것도 안 보는 검사다(11-3 ③).

    본다 — ① 온전한 판에서 탈이 0인가 ② 칸이 통째로 없으면 잡는가
    ③ 가운데 한 줄을 지우면 잡는가(뒤 줄이 당겨져 순서가 어긋난다)
    ④ 값만 비우면 잡는가 — **「없음」 은 값이고 빈 칸은 값이 아니다**."""
    assert 손넘김.본다(온전한판) == [], "① 온전한 판이 빨갛다"

    칸없는판 = 온전한판.split("\n\n", 1)[1]
    assert 손넘김.본다(칸없는판), "② 칸이 통째로 없는데 초록이다"

    줄들 = 온전한판.splitlines()
    줄뺀판 = "\n".join(줄들[:2] + 줄들[3:])          # 「관리자 권한」 줄을 지운다
    assert "관리자 권한" not in 줄뺀판
    assert 손넘김.본다(줄뺀판), "③ 줄이 빠졌는데 초록이다"

    값빈판 = 온전한판.replace("관리자 권한: 없음", "관리자 권한:")
    탈 = 손넘김.본다(값빈판)
    assert 탈 and "관리자 권한" in 탈[0], f"④ 값이 비었는데 초록이다: {탈}"


def test33_f02_글검사가_다섯째를_실제로_부른다(손넘김):
    """사) 검사를 **만들어 놓고 안 부르면** 없는 것과 같다.

    본다 — ① `글검사.py` 의 `검사들` 에 이름이 있는가 ② 그 이름의 파일이
    실재하는가 ③ **그 파일의 표와 `검사들` 이 같은 것을 말하는가** — 무엇이 도는지는
    그 파일이 말한다고 11-3 이 정해 두었는데, 표만 늘고 튜플이 그대로면
    그 말이 거짓이 된다.

    **CLAUDE.md 의 문장을 박지 않는다** — 박으면 그 줄을 고쳐 쓰는 판이
    시험 때문에 막힌다(11-3 「문서의 값을 시험에 박지 않습니다」 · 검토 i)."""
    글 = (ROOT / "scripts/글검사.py").read_text(encoding="utf-8")
    검사들 = _스크립트("글검사").검사들
    assert "check_handoff" in 검사들, "① 글검사가 안 부른다"
    for 이름 in 검사들:
        assert (ROOT / f"scripts/{이름}.py").exists(), f"② {이름}.py 가 없다"
    # ③ 독스트링 표의 `check_*` 줄과 튜플이 같은 집합인가
    표에든것 = {줄.split("`")[1] for 줄 in 글.splitlines() if 줄.startswith("| `check_")}
    assert 표에든것 == set(검사들), f"③ 표와 검사들이 갈렸다: {표에든것} · {set(검사들)}"


def test33_b03_더를_준_채_두_번째로_돌려도_0건이다(합치기, tmp_path, monkeypatch, 회차, capsys):
    """라) 사람이 실제로 칠 명령은 `--더` 를 붙인 판이라, **그 판의 두 번째**가
    0건이어야 한다(검토 d). `b01` 은 한 번만 돌린다.

    본다 — ① 둘째 판이 「합칠 것이 없습니다」 인가 ② 묶음이 그대로인가
    ③ **`--더` 이름이 여전히 있는 이름으로 세어지는가** — 옮기고 나면 그 run 이
    의약품으로 가는데, 짚을 수 있는 범위를 그 묶음 안으로 좁혔으므로 둘째 판에는
    없는 이름이 된다. 없는 이름은 멈춤이라 **0건이 아니라 빨개질 수 있다.**"""
    _심는다(회차, [("통제", "진통제")])
    _사본준비(합치기, tmp_path, monkeypatch)
    with app_session() as db:
        assert 합치기.합치기(db, 회차, ["진통제"], 실행=True) == 0
    앞 = _묶음별(회차)
    assert 앞 == {"의약품": 1}

    capsys.readouterr()
    with app_session() as db:
        답 = 합치기.합치기(db, 회차, ["진통제"], 실행=True)
    out = capsys.readouterr().out
    assert 답 == 0, f"둘째 판이 빨갛다: {out}"
    assert "합칠 것이 없습니다" in out, out
    assert _묶음별(회차) == 앞
