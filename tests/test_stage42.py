"""시험이 운영 DB 를 지우지 못하게 — 2026-09-13 사고 수습 (봐둘것 AZ-a).

`tests/conftest.py` 의 `_시험DB가_아니면_멈춘다` 가 **막혀야 할 것을 막고,
막히면 안 되는 것을 통과시키는지** 같은 판에서 잰다.

**운영 파일에 대고 재지 않는다.** 운영과 같은 꼴의 경로(`…/data/app.db`)를
pytest 의 `tmp_path` 에 만들어 거기에 댄다 — 그 자리는 `%TEMP%` 아래이지만
conftest 의 `_TMP` 밖이라, 「임시 폴더면 된다」 는 넓은 기준이었다면 여기서
통과해 버린다. 그 차이를 잰다.

`-p` 로 app 을 먼저 import 하는 실제 입구를 끝까지 따라가 본 것은 이 파일
밖에서 했다(가짜 운영 파일에 대고 · 보고 2장) — pytest 안에서 pytest 를
다시 띄우면 그 판이 또 운영 옆에서 돈다.
"""

import pytest
from sqlalchemy import create_engine

from tests import conftest


def _파일엔진(path):
    return create_engine(f"sqlite:///{path}")


def test42_a01_운영꼴_경로면_멈춘다(tmp_path):
    운영꼴 = tmp_path / "data" / "app.db"
    운영꼴.parent.mkdir()
    운영꼴.write_bytes(b"")
    엔진 = _파일엔진(운영꼴)
    with pytest.raises(pytest.exit.Exception) as 멈춤:
        conftest._시험DB가_아니면_멈춘다(엔진)
    엔진.dispose()
    말 = str(멈춤.value)
    # 조용히 삼키지 않는다 — 어느 파일을 열었고 왜 안 되는지를 말한다
    assert str(운영꼴) in 말, 말
    assert "임시 폴더 밖" in 말 and "-p" in 말, 말
    assert 멈춤.value.returncode == 3


def test42_a02_시험용_임시폴더면_지나간다():
    엔진 = _파일엔진(conftest._TMP / "test.db")
    conftest._시험DB가_아니면_멈춘다(엔진)  # 멈추면 여기서 Exit 가 난다
    엔진.dispose()


def test42_a03_지금_앱의_엔진은_지나간다():
    """정상 경로 — 이 판이 실제로 쓰는 엔진이 막히면 모든 시험이 멈춘다."""
    from app.db import engine

    import pathlib

    conftest._시험DB가_아니면_멈춘다(engine)
    assert conftest._TMP.resolve() in pathlib.Path(engine.url.database).resolve().parents


def test42_a04_메모리DB는_지나간다():
    엔진 = create_engine("sqlite://")
    conftest._시험DB가_아니면_멈춘다(엔진)
    엔진.dispose()


def test42_a05_파일이_아닌_DB는_멈춘다():
    """sqlite 가 아니면 임시 폴더 안인지 알 길이 없다 — 지나가게 두지 않는다."""
    from types import SimpleNamespace

    from sqlalchemy.engine import make_url

    엔진 = SimpleNamespace(url=make_url("postgresql://h/app"))
    with pytest.raises(pytest.exit.Exception):
        conftest._시험DB가_아니면_멈춘다(엔진)


def test42_a06_지우는_자리마다_검사가_앞에_선다():
    """**conftest 안에서** `drop_all` 을 부르는 문장 바로 앞에 검사가 있는가 —
    검사를 볼 것을 실제로 보는지(③). 보는 것은 `tests/conftest.py` 하나이고
    `x = ….drop_all()` 같은 대입 안의 부름·별칭은 못 본다. 다른 시험 파일은
    `tmp_path` 엔진에 `drop_all` 을 부를 수 있어 그 파일까지 넓히지 않았다."""
    import ast
    import inspect

    나무 = ast.parse(inspect.getsource(conftest))
    지우기 = 0
    for 몸 in ast.walk(나무):
        줄들 = getattr(몸, "body", None)
        if not isinstance(줄들, list):
            continue
        for i, 줄 in enumerate(줄들):
            부름 = getattr(줄, "value", None)
            if isinstance(줄, ast.Expr) and isinstance(부름, ast.Call) \
                    and getattr(부름.func, "attr", "") == "drop_all":
                지우기 += 1
                앞 = ast.unparse(줄들[i - 1]) if i else ""
                assert "_시험DB가_아니면_멈춘다" in 앞, f"검사 없이 지운다: {ast.unparse(줄)}"
    assert 지우기 >= 1, "drop_all 을 하나도 못 찾았다 — 이 시험이 아무것도 안 본다"


def _사본(tmp_path):
    """운영과 같은 꼴의 사본 — 표 하나에 행 하나. 운영 파일에 대고 재지 않는다."""
    import sqlite3

    경로 = tmp_path / "data" / "app.db"
    경로.parent.mkdir()
    이음 = sqlite3.connect(경로)
    이음.execute("CREATE TABLE retreats (id INTEGER PRIMARY KEY, name TEXT)")
    이음.execute("INSERT INTO retreats (name) VALUES ('가')")
    이음.commit()
    이음.close()
    return 경로


def test42_b01_읽기전용엔진은_읽고_쓰기는_막힌다(tmp_path):
    """운영을 직접 여는 표본 시험의 엔진(`읽기전용엔진`) — **읽는 것은 되고
    쓰는 것은 막힌다**를 같은 판에서 본다. 파일의 바이트도 그대로여야 한다."""
    import sqlalchemy as sa

    from tests.test_meetings_import import 읽기전용엔진

    경로 = _사본(tmp_path)
    전 = 경로.read_bytes()
    엔진 = 읽기전용엔진(경로)
    try:
        with 엔진.connect() as c:
            assert c.execute(sa.text("SELECT count(*) FROM retreats")).scalar() == 1
        with pytest.raises(sa.exc.OperationalError, match="readonly"):
            with 엔진.begin() as c:
                c.execute(sa.text("INSERT INTO retreats (name) VALUES ('나')"))
        with pytest.raises(sa.exc.OperationalError, match="readonly"):
            with 엔진.begin() as c:
                c.execute(sa.text("DROP TABLE retreats"))
    finally:
        엔진.dispose()
    assert 경로.read_bytes() == 전


def test42_b02_검사스크립트가_운영을_여는_꼴도_읽기전용이다(tmp_path):
    """시험이 부르는 `check_names` 도 운영 `data/app.db` 를 연다(`표밖담당자`).
    그 꼴(`file:…?mode=ro`)이 실제로 쓰기를 막는지 사본에 대고 재고,
    스크립트가 아직 그 꼴로 여는지 본다."""
    import pathlib
    import sqlite3

    src = (pathlib.Path(__file__).resolve().parent.parent / "scripts" / "check_names.py").read_text(encoding="utf-8")
    assert 'sqlite3.connect(f"file:{db}?mode=ro", uri=True)' in src, "check_names 가 운영을 여는 꼴이 바뀌었다"

    경로 = _사본(tmp_path)
    이음 = sqlite3.connect(f"file:{경로}?mode=ro", uri=True)
    try:
        assert 이음.execute("SELECT count(*) FROM retreats").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            이음.execute("INSERT INTO retreats (name) VALUES ('나')")
    finally:
        이음.close()


def test42_b03_운영을_여는_시험은_읽기전용엔진을_쓴다():
    """`tests/` 에서 운영 `data/app.db` 를 이름하는 파일은 **그 엔진으로만** 연다.
    같은 꼴의 쓰기 가능한 엔진이 새로 생기면 빨개진다. 이 파일은 그 말을 설명하려고
    담으므로 뺀다. 하나라도 봐야 한다(③)."""
    import pathlib

    본 = 0
    for f in sorted(pathlib.Path(__file__).resolve().parent.glob("test_*.py")):
        if f.name == pathlib.Path(__file__).name:
            continue
        src = f.read_text(encoding="utf-8")
        if '"data" / "app.db"' not in src:
            continue
        본 += 1
        assert "읽기전용엔진(" in src, f"{f.name} 이 운영을 읽기 전용 엔진 없이 연다"
        assert 'create_engine(f"sqlite:///{운영}")' not in src, f"{f.name} 에 쓰기 가능한 운영 엔진이 있다"
    assert 본 >= 1, "운영을 여는 시험을 하나도 못 찾았다 — 이 시험이 아무것도 안 본다"


def test42_a07_세션_첫머리에서도_검사가_돈다():
    """사고의 입구(`-p`)를 실제로 막은 것은 `pytest_sessionstart` 다 — 바깥 재현이
    거기서 exit 3 으로 멈췄다. `SessionLocal` 로 운영에 쓰는 시험을 막는 것도
    그 훅뿐이라, 누가 지우면 여기서 빨개진다."""
    import ast
    import inspect

    훅 = getattr(conftest, "pytest_sessionstart", None)
    assert 훅 is not None, "conftest 에 pytest_sessionstart 가 없다"
    부름들 = {
        getattr(n.func, "id", "") for n in ast.walk(ast.parse(inspect.getsource(훅)))
        if isinstance(n, ast.Call)
    }
    assert "_시험DB가_아니면_멈춘다" in 부름들
