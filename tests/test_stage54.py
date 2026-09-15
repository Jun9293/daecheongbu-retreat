"""회의록에 노션 페이지 id 를 단다 (노션 대조 2판 · 2026-09-15 · `scripts/회의록id달기.py`).

페이지 id 와 제목은 지어낸 것이다 — 실제 페이지 목록(data/노션회의록.real.json)은 열지 않는다.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

import pytest
from sqlalchemy import select

from app import db as app_db
from app import models

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _달기():
    이름 = "회의록id달기_시험"
    spec = importlib.util.spec_from_file_location(이름, ROOT / "scripts" / "회의록id달기.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[이름] = mod
    spec.loader.exec_module(mod)
    return mod


페이지 = [
    {"id": "p-aaa", "title": "가람팀 나눔 회의록"},
    {"id": "p-bbb", "title": "가람팀 회의록"},
    {"id": "p-ccc", "title": "무엇무엇 모임에 부탁/살필 것 (메모) 회의록"},
]


def _목록(tmp_path, 페이지들=페이지) -> pathlib.Path:
    p = tmp_path / "노션회의록.real.json"
    p.write_text(json.dumps({"페이지": 페이지들}, ensure_ascii=False), encoding="utf-8")
    return p


def _회의(db, title, origin="노션", source=None, pid=None):
    m = models.Meeting(title=title, origin=origin, source_ref=source, notion_page_id=pid)
    db.add(m)
    db.flush()
    return m


def _심는다(db):
    a1 = _회의(db, "26.05.01", source="01-가람팀나눔")
    a2 = _회의(db, "26.05.08", source="01-가람팀나눔")          # 한 파일이 둘로 잘림
    b = _회의(db, "가람팀 회의록", source="02-가람팀")               # 제목이 페이지와 글자 같음
    c = _회의(db, "26.06.01", source="03-부탁살필")
    사람 = _회의(db, "사람이 적은 회의", origin="사람")
    db.commit()
    return a1, a2, b, c, 사람


def test54_a01_칸은_NULL_로_붙고_부팅은_값을_안_채운다():
    붙는 = [(t, c, d) for t, c, d in app_db._ADDED_COLUMNS if c == "notion_page_id"]
    assert 붙는 == [("meetings", "notion_page_id", "VARCHAR(36)")]
    assert "NOT NULL" not in 붙는[0][2] and "DEFAULT" not in 붙는[0][2]
    # 값을 쓰는 곳이 app/ 에 없다 — 모델 선언과 칸 목록만
    본것 = [p for p in (ROOT / "app").rglob("*.py") if p.name not in ("models.py", "db.py")]
    assert len(본것) > 10, "app/ 에서 훑은 파일이 없다 — 아무것도 안 보는 검사다"
    쓰는곳 = [p for p in 본것 if "notion_page_id" in p.read_text(encoding="utf-8")]
    assert 쓰는곳 == []
    assert (ROOT / "app" / "models.py").read_text(encoding="utf-8").count("notion_page_id") == 1, "models.py 가 선언 말고 그 칸을 만진다"
    db글 = (ROOT / "app" / "db.py").read_text(encoding="utf-8")
    assert len(re.findall(r"notion_page_id", db글)) == 1, "db.py 가 칸 목록 말고 그 칸을 만진다"
    assert models.Meeting.__table__.c.notion_page_id.nullable


def test54_b01_짝은_같은_글자_먼저_남은_것은_순서대로_든_것_하나():
    m = _달기()
    짝 = m.짝짓는다(["01-가람팀나눔", "02-가람팀", "03-부탁살필"], 페이지)
    assert {k: v["id"] for k, v in 짝.items()} == {"01-가람팀나눔": "p-aaa", "02-가람팀": "p-bbb", "03-부탁살필": "p-ccc"}


def test54_b02_하나로_못_정하면_멈춘다():
    m = _달기()
    with pytest.raises(m.멈춤):                       # 없음
        m.짝짓는다(["01-없는팀"], 페이지)
    둘 = [{"id": "x", "title": "가나다 회의록"}, {"id": "y", "title": "가X나X다 회의록"}]
    with pytest.raises(m.멈춤):                       # 순서대로 든 것이 둘
        m.짝짓는다(["01-가다"], 둘)
    with pytest.raises(m.멈춤):                       # 번호를 떼면 이름이 같은 출처 둘
        m.짝짓는다(["01-가람팀", "02-가람팀"], 페이지)
    with pytest.raises(m.멈춤):                       # 이미 글자로 짝지은 페이지까지 세면 후보가 둘
        m.짝짓는다(["01-가나다", "02-가다"], 둘)
    with pytest.raises(m.멈춤, match="출처 파일 둘 이상과"):   # 한 페이지가 출처 둘과 짝
        m.짝짓는다(["01-가나다", "02-가다"], 둘[:1])


def test54_b03_막히면_안_되는_것은_통과한다():
    m = _달기()
    # 순서대로 든 페이지가 전체에서 하나면 짝 — 글자 같은 짝과 섞여도
    짝 = m.짝짓는다(["01-가람팀", "02-부탁살필"], 페이지[1:])
    assert {k: v["id"] for k, v in 짝.items()} == {"01-가람팀": "p-bbb", "02-부탁살필": "p-ccc"}


def test54_c01_미리보기는_안_바꾸고_실행은_파일의_회의_전부에_단다(db, tmp_path, capsys):
    m = _달기()
    a1, a2, b, c, 사람 = _심는다(db)
    판 = m.돌린다(db, _목록(tmp_path), 실행=False, 사본=False)
    assert 판.수["채울 회의"] == 4 and 판.수["짝지은 파일"] == 3
    assert 판.수["회의 제목 = 페이지 제목(글자 그대로)"] == 1
    assert 판.수["파일 이름 = 페이지 제목(글자 그대로)"] == 0
    assert 판.수["노션이 아닌 회의(안 건드림)"] == 1
    db.expire_all()
    assert db.scalars(select(models.Meeting.notion_page_id)).all().count(None) == 5

    m.돌린다(db, _목록(tmp_path), 실행=True, 사본=False)
    db.expire_all()
    assert (a1.notion_page_id, a2.notion_page_id, b.notion_page_id, c.notion_page_id) == ("p-aaa", "p-aaa", "p-bbb", "p-ccc")
    assert 사람.notion_page_id is None
    capsys.readouterr()

    판2 = m.돌린다(db, _목록(tmp_path), 실행=True, 사본=False)
    assert 판2.채울 == [] and "채울 것이 없습니다" in capsys.readouterr().out


def test54_c02_다른_id_가_이미_있으면_덮지_않고_멈춘다(db, tmp_path):
    m = _달기()
    _회의(db, "26.05.01", source="01-가람팀나눔", pid="p-다른것")
    _회의(db, "26.05.08", source="02-가람팀")
    db.commit()
    with pytest.raises(m.멈춤):
        m.돌린다(db, _목록(tmp_path), 실행=True, 사본=False)
    db.expire_all()
    assert db.scalars(select(models.Meeting.notion_page_id)).all() == ["p-다른것", None]


def test54_c04_다시_센_수가_어긋나면_되돌린다(db, tmp_path, monkeypatch):
    m = _달기()
    _심는다(db)
    진짜 = m.단수
    불림 = []

    def 어긋난(세션):
        불림.append(1)
        return 진짜(세션) + (1 if len(불림) > 1 else 0)   # 채운 뒤에 센 것만 하나 틀리게
    monkeypatch.setattr(m, "단수", 어긋난)
    with pytest.raises(m.멈춤):
        m.돌린다(db, _목록(tmp_path), 실행=True, 사본=False)
    assert len(불림) == 2
    db.expire_all()
    assert db.scalars(select(models.Meeting.notion_page_id)).all().count(None) == 5


def test54_c05_사본을_뜰_수_없으면_쓰기_전에_멈춘다(db, tmp_path, monkeypatch):
    m = _달기()
    _심는다(db)
    진짜 = m.사본을_뜬다
    본수 = []

    def 지켜본다():
        본수.append(db.execute(select(models.Meeting.id).where(models.Meeting.notion_page_id.is_not(None))).all())
        return 진짜()
    monkeypatch.setattr(m, "사본을_뜬다", 지켜본다)
    with pytest.raises(m.멈춤, match="사본을 뜰 파일이 다릅니다"):   # 시험 DB 는 data/app.db 가 아니다
        m.돌린다(db, _목록(tmp_path), 실행=True, 사본=True)
    assert 본수 == [[]], "사본을 뜨기 전에 이미 값을 썼다"
    db.expire_all()
    assert db.scalars(select(models.Meeting.notion_page_id)).all().count(None) == 5


def test54_c03_목록_파일이_없거나_비면_멈춘다(db, tmp_path):
    m = _달기()
    with pytest.raises(m.멈춤):
        m.돌린다(db, tmp_path / "없음.json", 실행=False, 사본=False)
    with pytest.raises(m.멈춤):
        m.돌린다(db, _목록(tmp_path, []), 실행=False, 사본=False)
