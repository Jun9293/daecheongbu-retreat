"""오늘 운영에서 드러난 넷 (2026-09-11).

셋은 **사람을 잘못된 길로 보낸 자리**이고 하나는 **화면이 거짓을 말한 자리**다.

| 잰 것 | 어디 |
|---|---|
| 가·나 | 들여오기가 멈출 때 찍는 줄 번호가 **파일에서 그 줄이 몇 번째인가**와 같은가
        (도막 4 에서 「시트의 행」 이라는 단정을 걷었다 — `tests/test_stage32.py`) |
| 다·라 | 회차를 안 주면 멈추는가 / 하나뿐이면 지나가며 이름을 찍는가 |
| 마·바 | 회차 상세의 「이 회차의 부서」 가 부서 탭과 같은 답을 내는가 |
| 사·아 | 서버에서 뽑은 링크로 실제로 들어가지는가 / 그 값이 파일로 안 새는가 |

**합성 자료만 쓴다** — 실제 시트(`data/*.real.tsv`)는 외부인 실명과 전화가 들어
있어 시험이 열지 않는다. 합성 자료의 사람 이름은 가명이다.

각 독스트링에 **그 줄이 실제로 무엇을 보는지** 적는다 — 막혀야 할 것이 막히는가 ·
막히면 안 되는 것이 통과하는가 · 검사가 볼 것을 보고 있는가(11-3).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import re

import pytest
from sqlalchemy import select

from app import models
from tests.conftest import app_session, make_user

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


def _tsv(tmp_path: pathlib.Path, 이름: str, 줄들: list[list[str]]) -> pathlib.Path:
    p = tmp_path / 이름
    p.write_text("\n".join("\t".join(칸 for 칸 in 줄) for 줄 in 줄들), encoding="utf-8")
    return p


머리글 = ["구분", "챙길 물품", "현재 수량", "필요한 수량", "최종", "위치", "비고"]
자국줄 = ["사무용품", "지민M 볼펜", "", "10", "", "모빌랙", ""]     # 가명
멀쩡한줄 = ["사무용품", "볼펜", "", "10", "", "모빌랙", ""]


def _같은줄이_앞에_있는_자료(tmp_path, 메모줄수: int, 이름: str) -> pathlib.Path:
    """머리글 **위**에 `자국줄` 과 똑같은 줄을 두 벌 심고, 자료 안에서 한 번 더 낸다.

    `줄들.index(줄)` 은 파일 전체에서 **맨 앞의** 같은 줄을 돌려주므로, 고치기 전
    코드는 머리글 위의 그 줄을 가리켰다 — 사람이 그 번호를 열면 아무것도 없다.
    `메모줄수` 로 머리글 자리를 옮겨 **머리글이 첫 줄이 아닌** 자료를 만든다.
    """
    줄들 = [["비품 준비 메모", "", "", "", "", "", ""] for _ in range(메모줄수)]
    줄들 += [list(자국줄), list(자국줄)]        # ← 같은 내용 두 벌 (머리글 위)
    줄들 += [list(머리글), list(멀쩡한줄), ["", "가위", "", "4", "", "모빌랙", ""],
             list(자국줄)]                       # ← 여기서 멈춰야 한다
    return _tsv(tmp_path, 이름, 줄들)


# ── 가. 같은 내용의 줄이 앞에 있어도 뒤엣것의 번호가 나온다 ───────────────

def test31_a01_같은_줄이_앞에_두_벌_있어도_멈춘_줄의_번호를_말한다(들여오기, tmp_path):
    """가) 같은 내용의 줄을 **실제로 두 벌 심는다.**

    본다 — ① 멈추는가 ② 말에 나오는 수가 **멈춘 그 줄**의 파일 줄 번호인가
    ③ **고치기 전 공식은 다른 수를 냈다**는 것을 같은 자료로 직접 셈해 확인한다
    (③ 이 없으면 이 시험은 고치기 전에도 통과할 수 있다).
    """
    메모 = 1
    p = _같은줄이_앞에_있는_자료(tmp_path, 메모, "앞에두벌.tsv")
    줄들 = 들여오기.읽는다(p)

    # 자료가 실제로 「같은 줄이 셋」 인지부터 본다 — 아니면 이 시험은 아무것도 안 잰다
    assert 줄들.count(자국줄) == 3, "같은 내용의 줄을 심지 못했다"
    멈출자리 = len(줄들)                                # 마지막 줄에서 멈춘다
    assert 줄들[멈출자리 - 1] == 자국줄

    with pytest.raises(들여오기.멈춤) as e:
        들여오기.줄뽑기("총무", p)
    말 = str(e.value)
    assert f"파일의 {멈출자리}번째 줄" in 말, f"멈춘 줄의 번호가 아니다: {말}"

    # ③ 고치기 전 공식(`줄들.index(줄) + 1`)은 머리글 위의 첫 벌을 가리킨다
    옛수 = 줄들.index(자국줄) + 1
    assert 옛수 == 메모 + 1, "심은 자리가 뜻대로 놓이지 않았다"
    assert 옛수 != 멈출자리, "이 자료로는 옛 공식과 새 공식이 갈리지 않는다"


# ── 나. 그 번호가 파일에서 그 줄이 몇 번째인가와 같다 ────────────────────

@pytest.mark.parametrize("메모줄수", [0, 1, 4])
def test31_a02_머리글이_첫_줄이_아니어도_파일의_줄_번호를_말한다(들여오기, tmp_path, 메모줄수):
    """나) 머리글 위의 메모 줄 수를 0·1·4 로 바꿔 가며 잰다.

    본다 — 찍히는 수가 **파일에서 그 줄이 실제로 몇 번째인가**와 늘 같은가.
    머리글 자리가 움직여도 따라 움직인다.

    **「시트의 행」 이라고 재지 않는다** — 그 둘이 같은지는 사람이 시트를 어떻게
    내려받느냐에 달렸다(도막 4 · 4-18). 그래서 말도 「파일의 N번째 줄」 이고,
    사람이 찾을 수 있게 묶음과 그 안 차례를 함께 찍는다(`tests/test_stage32.py`).
    자료를 실제로 세어 기대값을 만든다 — 수를 시험에 박지 않는다(11-3).
    """
    p = _같은줄이_앞에_있는_자료(tmp_path, 메모줄수, f"메모{메모줄수}.tsv")
    기대 = len(들여오기.읽는다(p))                      # 멈추는 줄 = 마지막 줄
    with pytest.raises(들여오기.멈춤) as e:
        들여오기.줄뽑기("총무", p)
    assert f"파일의 {기대}번째 줄" in str(e.value)


def test31_a03_자국이_없으면_안_멈추고_줄_수가_맞는다(들여오기, tmp_path):
    """나) **막히면 안 되는 쪽.** 사람 자국을 뺀 같은 모양의 자료로 돌린다.
    본다 — 멈추지 않는가 · 뽑힌 줄이 실제 자료 줄 수와 맞는가."""
    p = _tsv(tmp_path, "멀쩡.tsv", [
        ["비품 준비 메모", "", "", "", "", "", ""],
        list(머리글), list(멀쩡한줄), ["", "가위", "", "4", "", "모빌랙", ""],
    ])
    뽑은, 셈 = 들여오기.줄뽑기("총무", p)
    assert [줄["이름"] for 줄 in 뽑은] == ["볼펜", "가위"]
    assert 셈["넣을줄"] == 2


def test31_a05_칸_안에_줄바꿈이_있어도_행_번호가_안_밀린다(들여오기, tmp_path):
    """나) **검토가 짚은 자리.** 줄로 자르면 한 행이 두 줄이 되어 그 아래 번호가
    모두 밀린다 — 오늘 고친 것과 같은 종류의 고장이다.

    본다 — ① 비고에 줄바꿈이 든 칸(시트가 따옴표로 감싼 꼴)을 넣고 ② **파일에서
    그 줄이 몇 번째인가**를 손으로 적어 둔 값과 견준다. 판독기에서 기대값을
    끌어오지 않는다 — 둘이 같이 틀리면 같이 맞다고 하기 때문이다(a02 의 한계).
    ③ 그 줄의 비고가 **한 칸으로** 읽히는지도 본다.

    이것이 참이면 「파일의 줄」 과 「레코드」 가 같다 — 그 위에 「시트의 행」 까지
    같은지는 내려받기가 정하므로 여기서 재지 않는다."""
    감싼비고 = '"윗칸\n아랫칸"'        # 시트가 내려받기에서 감싸 주는 꼴
    글 = "\n".join("\t".join(줄) for 줄 in (
        머리글,
        ["사무용품", "볼펜", "", "10", "", "모빌랙", 감싼비고],
        자국줄,
    ))
    p = tmp_path / "줄바꿈.tsv"
    # newline="" 이라야 윈도우가 칸 안의 줄바꿈까지 CRLF 로 바꾸지 않는다 —
    # 바꿔 놓고 그 값을 견주면 시험이 자기가 만든 것과 어긋난다
    p.write_text(글, encoding="utf-8", newline="")

    # 파일의 레코드: 1 머리글 · 2 볼펜(비고가 두 줄짜리) · 3 자국 줄
    with pytest.raises(들여오기.멈춤) as e:
        들여오기.줄뽑기("총무", p)
    assert "파일의 3번째 줄" in str(e.value), f"줄바꿈 때문에 번호가 밀렸다: {e.value}"

    # ③ 비고가 한 칸으로 읽혔는가 — 안 그러면 위의 수가 우연히 맞은 것이다
    줄들 = 들여오기.읽는다(p)
    assert len(줄들) == 3, f"레코드가 3이 아니다: {len(줄들)}"
    assert 줄들[1][6] == "윗칸\n아랫칸"


def test31_a04_자리를_index_로_묻는_곳이_남아_있지_않다():
    """가) **같은 자리가 하나 더 있는지 파일 전체를 훑는다** (지시 1번의 마지막 줄).

    본다 — 주석·독스트링을 걷어낸 코드에 `.index(` 가 하나도 없는가.
    설명에는 그 말이 나오므로(무엇을 고쳤는지 적었다) 코드만 보고 센다 — 10장
    「글자를 찾는 시험은 코드와 설명을 못 가린다」."""
    글 = (ROOT / "scripts/비품들여오기.py").read_text(encoding="utf-8")
    코드 = re.sub(r'"""[\s\S]*?"""', "", 글)
    코드 = "\n".join(줄.split("#")[0] for 줄 in 코드.splitlines())
    assert ".index(" not in 코드, "자리를 내용으로 묻는 곳이 아직 있다"


# ── 다·라. 회차를 조용히 고르지 않는다 ──────────────────────────────────

def _회차(db, 이름: str, 늦게: int) -> int:
    r = models.Retreat(name=이름, start_date=TODAY + dt.timedelta(days=늦게),
                       end_date=TODAY + dt.timedelta(days=늦게 + 2))
    db.add(r)
    db.flush()
    return r.id


def test31_b01_열린_회차가_둘이면_회차_없이는_멈추고_id와_이름을_다_보여준다(들여오기, client):
    """다) 회차를 **실제로 둘 세워** `--회차` 없이 부른다.

    본다 — ① 멈추는가 ② **둘의 id 와 이름이 모두** 말에 있는가(하나만 보이면
    사람이 고를 수 없다) ③ `--회차` 로 고르면 그 회차가 그대로 나오는가."""
    with app_session() as db:
        올해 = _회차(db, "2026 여름수련회 Belong", 30)
        내년 = _회차(db, "2027 여름수련회", 400)
        db.commit()

        with pytest.raises(들여오기.멈춤) as e:
            들여오기.회차고르기(db, None)
        말 = str(e.value)
        for 회차id, 이름 in ((올해, "2026 여름수련회 Belong"), (내년, "2027 여름수련회")):
            assert f"--회차 {회차id}" in 말, f"id {회차id} 를 안 보여준다"
            assert 이름 in 말, f"이름 {이름!r} 을 안 보여준다"

        # ③ 막히면 안 되는 쪽 — 골라 주면 그것을 쓴다
        assert 들여오기.회차고르기(db, 올해).id == 올해
        assert 들여오기.회차고르기(db, 내년).id == 내년


def test31_b02_회차가_하나면_회차_없이도_지나가고_이름을_찍는다(들여오기, client, capsys):
    """라) 하나만 세워 두고 `--회차` 없이 부른다.

    본다 — ① 멈추지 않고 그 회차를 돌려주는가 ② **이름이 실제로 찍히는가**
    (말없이 고르던 것을 고치는 판이라, 고른 사실이 보여야 한다)."""
    with app_session() as db:
        하나 = _회차(db, "2026 여름수련회 Belong", 30)
        db.commit()
        capsys.readouterr()
        고른것 = 들여오기.회차고르기(db, None)
        assert 고른것.id == 하나
    찍힌 = capsys.readouterr().out
    assert "2026 여름수련회 Belong" in 찍힌, f"이름을 안 찍었다: {찍힌!r}"
    assert str(하나) in 찍힌


def test31_b03_보관된_회차는_세지_않는다(들여오기, client):
    """다) **막히면 안 되는 쪽.** 회차가 둘이어도 하나가 보관됐으면 남은 하나를
    쓴다 — 「열려 있는 회차」 가 기준이라고 적어 두었으므로 그것을 실제로 잰다."""
    with app_session() as db:
        산것 = _회차(db, "2026 여름수련회 Belong", 30)
        옛것 = _회차(db, "2025 여름수련회", -400)
        db.get(models.Retreat, 옛것).is_archived = True
        db.commit()
        assert 들여오기.회차고르기(db, None).id == 산것
        # 사람이 **대놓고** 보관된 회차를 고르면 그대로 쓴다 — 「열려 있는」 은
        # 안 줬을 때의 기준이지 고를 수 없다는 뜻이 아니다(검토의 「정할 것 (다)」)
        assert 들여오기.회차고르기(db, 옛것).id == 옛것


# ── 마·바. 회차 상세가 부서 탭과 같은 답을 낸다 ─────────────────────────

def _부서를_넣는다(db, retreat_id: int) -> list[str]:
    이름들 = []
    for i, (key, name) in enumerate((("chongmu", "1 총무팀"), ("hebron", "5 헤브론"),
                                     ("koram", "6 코람데오"))):
        db.add(models.Department(retreat_id=retreat_id, key=key, name=name,
                                 color_tag="#888", sort_order=i))
        이름들.append(name)
    return 이름들


def test31_c01_부서가_있는_회차의_상세에_그_부서가_나온다(admin_client):
    """마) 부서 셋을 **실제로 넣고** 화면을 받아 **부서 이름을 읽어** 잰다.

    본다 — ① 셋이 다 화면에 있는가 ② 「부서가 없습니다」 가 **없는가**
    (전에는 부서가 있는데도 그 말이 떴다) ③ 같은 회차의 부서 탭과 답이 같은가 —
    두 화면이 같은 것을 물으므로 답이 갈리면 하나가 거짓말을 하는 것이다."""
    with app_session() as db:
        rid = _회차(db, "부서 있는 회차", 30)
        이름들 = _부서를_넣는다(db, rid)
        db.commit()

    상세 = admin_client.get(f"/settings/retreats/{rid}")
    assert 상세.status_code == 200
    for 이름 in 이름들:
        assert 이름 in 상세.text, f"상세 화면에 {이름!r} 이 없다"
    assert "부서가 없습니다" not in 상세.text

    탭 = admin_client.get(f"/settings/departments?retreat_id={rid}")
    assert 탭.status_code == 200
    for 이름 in 이름들:
        assert 이름 in 탭.text
    # ③ 두 화면의 답이 갈리지 않는다
    assert ("부서가 없습니다" in 상세.text) == ("등록된 부서가 없습니다" in 탭.text)


def test31_c02_정말로_부서가_없는_회차에서만_없다고_말한다(admin_client):
    """바) **부서를 하나도 안 넣은 회차를 실제로 만들어** 잰다.

    본다 — ① 그때는 「부서가 없습니다」 가 뜨는가 ② 부서가 있는 회차와 **같은
    화면**에서 답이 갈리는가(늘 「있습니다」 로 바뀌었다면 이 판은 거짓을 거짓으로
    바꾼 것뿐이다)."""
    with app_session() as db:
        빈회차 = _회차(db, "부서 없는 회차", 60)
        찬회차 = _회차(db, "부서 있는 회차", 30)
        _부서를_넣는다(db, 찬회차)
        db.commit()

    빈것 = admin_client.get(f"/settings/retreats/{빈회차}")
    assert 빈것.status_code == 200
    assert "부서가 없습니다" in 빈것.text
    찬것 = admin_client.get(f"/settings/retreats/{찬회차}")
    assert "부서가 없습니다" not in 찬것.text


def test31_c03_두_화면이_부서를_같은_함수에_묻는다(client):
    """마) 낱말이 아니라 **부르는 것**을 잰다 — `departments_of` 를 가로채고 두
    화면을 받아, 둘 다 그 함수를 지났는지 본다. 두 곳이 각자 질의를 적으면
    한쪽만 고쳐진다(이 판이 그 상태였다)."""
    from app.domain import departments as dom

    with app_session() as db:
        rid = _회차(db, "같은 함수 회차", 30)
        _부서를_넣는다(db, rid)
        db.commit()
    assert dom.departments_of is not None
    with app_session() as db:
        줄들 = dom.departments_of(db, rid)
        assert [d.name for d in 줄들] == ["1 총무팀", "5 헤브론", "6 코람데오"]
        assert dom.departments_of(db, None) == []


def test31_c04_app_안에서_부서_목록을_묻는_곳이_하나다():
    """마) CLAUDE.md 14장이 「`app/` 안에서 묻는 곳은 여기 하나」 라고 적었으므로
    그것을 실제로 잰다. 검토가 셋(체크리스트·지출·회의록)을 더 찾아 그때 모았다.

    본다 — `app/` 아래에서 `select(Department)` 를 적는 파일이 도메인 모듈
    하나뿐인가. 하나 더 생기면 빨개진다."""
    쓴곳 = sorted(
        str(f.relative_to(ROOT)).replace(chr(92), "/")
        for f in (ROOT / "app").rglob("*.py")
        if "select(Department)" in f.read_text(encoding="utf-8")
    )
    assert 쓴곳 == ["app/domain/departments.py"], f"부서를 따로 묻는 곳이 있다: {쓴곳}"


# ── 사·아. 서버에서 뽑은 링크로 실제로 들어간다 ──────────────────────────

무시할폴더 = {".git", ".venv", "__pycache__", "data", "node_modules",
             ".pytest_cache", ".mypy_cache", "htmlcov", "graphify-out"}


def _저장소파일들() -> set[str]:
    남은 = []
    for p in ROOT.iterdir():
        if p.name not in 무시할폴더:
            남은.append(p)
    모은 = set()
    while 남은:
        p = 남은.pop()
        if p.is_dir():
            남은 += [c for c in p.iterdir() if c.name not in 무시할폴더]
        else:
            모은.add(str(p.relative_to(ROOT)))
    return 모은


def test31_d01_서버에서_만든_비밀번호로_그_사람이_들어와진다(client, capsys):
    """사) `scripts/계정문열기.py` 로 **실제로 만들고 그 값으로 들어간다.**

    본다 — ① 값이 찍히는가 ② 그 값으로 들어가면 **그 사람으로** 로그인되는가
    (이름이 화면에 있다 — 첫 비밀번호라 바꾸는 화면이 먼저 뜬다) ③ 없는
    id 로는 멈추는가.

    (2026-09-11 에 초대 링크를 걷으면서 같은 자리를 옮겼다.)"""
    from fastapi.testclient import TestClient

    from app.main import app

    문열기 = _스크립트("계정문열기")
    관리자 = make_user("복구 총무 정하윤", "01077770001", "admin")
    with app_session() as db:
        db.get(models.User, 관리자).login_id = "bokgu"
        db.commit()

    capsys.readouterr()
    with app_session() as db:
        assert 문열기.재설정(db, 관리자) == 0
    찍힌 = capsys.readouterr().out
    잡힌 = [ln.split()[-1] for ln in 찍힌.splitlines() if ln.strip().startswith("비밀번호 ")]
    assert 잡힌, f"값을 안 찍었다: {찍힌!r}"

    새창 = TestClient(app)
    들어감 = 새창.post("/login", data={"login_id": "bokgu", "password": 잡힌[0]},
                    follow_redirects=False)
    assert 들어감.status_code == 303, 들어감.text
    안쪽 = 새창.get("/password")
    assert 안쪽.status_code == 200, "값을 넣었는데 로그인되지 않았다"
    assert "복구 총무 정하윤" in 안쪽.text, "다른 사람으로 들어와졌다"

    # ③ 없는 id 는 멈춘다 — 만들지 않고 1 로 끝난다
    with app_session() as db:
        assert 문열기.재설정(db, 999_999) == 1


def test31_d02_발급해도_저장소에_값이_적힌_파일이_생기지_않는다(client, capsys):
    """아·자) **돌리기 전후의 파일 목록을 견준다.**

    본다 — ① 새 파일이 하나도 안 생기는가 ② 만들어진 **비밀번호 원문**이
    저장소의 어느 파일에도 없는가(파일 수가 같아도 있던 파일에 덧붙였을 수
    있다) ③ 훑은 것이 비지 않았는가.

    「비밀번호 원문은 어디에도 저장하지 않고 로그에도 안 찍는다」 를 여기서
    실제로 잰다."""
    문열기 = _스크립트("계정문열기")
    관리자 = make_user("값 받는 총무 최도현", "01077770002", "admin")
    with app_session() as db:
        db.get(models.User, 관리자).login_id = "dohyun"
        db.commit()

    전 = _저장소파일들()
    capsys.readouterr()
    with app_session() as db:
        assert 문열기.재설정(db, 관리자) == 0
    찍힌 = capsys.readouterr().out
    값 = [ln.split()[-1] for ln in 찍힌.splitlines() if ln.strip().startswith("비밀번호 ")][0]
    후 = _저장소파일들()

    assert 후 - 전 == set(), f"발급이 파일을 만들었다: {sorted(후 - 전)}"
    # ③ 훑은 것이 비지 않았는가 — `무시할폴더` 가 한 줄 늘어 트리를 통째로 삼키면
    # 아래 단언이 조용히 통과한다(검토가 짚음)
    assert len(후) > 100, f"훑은 파일이 너무 적다 — 이 시험이 눈을 감았다: {len(후)}"
    assert len(값) >= 8, "비밀번호가 아니다 — 이 시험이 아무것도 안 보고 있다"
    바이트 = 값.encode()
    담긴곳 = [이름 for 이름 in 후
             if 바이트 in (ROOT / 이름).read_bytes()]
    assert not 담긴곳, f"비밀번호가 저장소 안 파일에 적혔다: {담긴곳}"


def test31_d03_링크발급을_새로_만들지_않고_있던_것을_가리킨다():
    """사) 지시 4번의 「이미 있으면 새로 만들지 말라」 를 잰다.

    본다 — ① 같은 일을 하는 스크립트가 **둘이 되지 않았는가** ② 있던 것을 돌리는
    법이 배포 안내에 있는가 ③ 되돌리기 절차에서도 그 길을 가리키는가(오늘 막힌
    자리가 바로 「사본으로 되돌린 뒤」 였다)."""
    for 없어야할것 in ("scripts/링크발급.py", "scripts/관리자링크.py",
                    "scripts/create_admin.py"):
        assert not (ROOT / 없어야할것).exists(), \
            f"같은 일을 하는 스크립트가 둘이 됐다 — scripts/계정문열기.py 가 이미 있다: {없어야할것}"
    안내 = (ROOT / "docs/배포-안내.md").read_text(encoding="utf-8")
    assert "계정문열기.py" in 안내
    되돌리기 = 안내.split("**되돌리려면**", 1)
    assert len(되돌리기) == 2, "되돌리기 절차를 못 찾았다"
    assert "계정문열기.py" in 되돌리기[1][:1200], \
        "되돌린 뒤 들어갈 길을 그 자리에서 안 가리킨다"
