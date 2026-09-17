"""노션 관련업무로 업무 상위를 채운다 (2026-09-17 · `scripts/업무계층채우기.py`).

값은 전부 지어낸 것이다 — 실제 노션 줄(data/노션업무전체.real.tsv)은 열지 않는다.
**Main 은 노션 업무속성으로 가른다** — 앱 kind 로 가르면 속성 빈 줄이 빠지는 것을 따로 잰다.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest
from sqlalchemy import func, select

from app import models

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _채우기():
    이름 = "업무계층채우기_시험"
    spec = importlib.util.spec_from_file_location(이름, ROOT / "scripts" / "업무계층채우기.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[이름] = mod
    spec.loader.exec_module(mod)
    return mod


# (노션 id, 제목, 업무속성, 담당팀, 앱 kind, 앱 부서 키, 관련업무 노션 id 들)
줄들 = [
    ("m1", "포스터 제작", "Main", "4 스케치", "main", "sketch", ["m2", "s1", "s2", "b1", "x1"]),
    ("m2", "주제 방향성", "Main", "1 총무M", "main", "chongmuM", ["m1", "s2", "s3"]),
    ("m3", "명찰 디자인", "Main", "4 스케치", "main", "sketch", ["s3", "x1"]),
    ("s1", "포스터 확정", "Sub", "4 스케치", "sub", "sketch", ["m1"]),                 # Main 하나
    ("s2", "포스터 의뢰", "Sub", "1 총무M", "sub", "chongmuM", ["m1", "m2"]),          # 같은 담당팀 → m2
    ("s3", "명찰 의뢰", "Sub", "4 스케치", "sub", "sketch", ["m2", "m3"]),             # 같은 담당팀 → m3
    ("x1", "갈리는 줄", "Sub", "4 스케치", "sub", "sketch", ["m1", "m3"]),             # 같은 담당팀이 둘 → 비움
    ("c1", "홀로 선 일정", "Sch", "2 봉사팀 공통", "schedule", None, ["s1"]),           # Main 을 안 가리킴
    ("b1", "속성 빈 줄", "", "1 총무M", "main", "chongmuM", ["m1"]),                    # 앱 kind 는 main · 부서 다름
    ("(D-3주차)", "(D-3주차)", "", "0", "main", None, []),                              # 표지 — 읽을 때 빠진다
]


def _파일(tmp_path, 값=줄들) -> pathlib.Path:
    p = tmp_path / "노션업무전체.real.tsv"
    p.write_text("\n".join("\t".join([r[0], r[1], r[2], r[3]]) for r in 값) + "\n", encoding="utf-8")
    return p


def _앱(db, 값=줄들) -> dict[str, models.TaskLibrary]:
    libs = {}
    for nid, 제목, _, _, kind, 키, _ in 값:
        if 제목.startswith("(D-"):
            continue
        libs[nid] = models.TaskLibrary(title=제목, kind=kind, default_department_key=키,
                                       notion_page_id=nid, related_library_ids=[])
        db.add(libs[nid])
    db.flush()
    for nid, *_, 관련 in 값:
        if nid in libs:
            libs[nid].related_library_ids = [libs[x].id for x in 관련]
    db.commit()
    return libs


def test61_a01_Main_하나면_그것_여럿이면_같은_담당팀_하나(db, tmp_path):
    m = _채우기()
    libs = _앱(db)
    판 = m.고른다(db, m.읽는다(_파일(tmp_path))[0])
    id = {k: v.id for k, v in libs.items()}
    assert 판.채울 == {id["s1"]: id["m1"], id["s2"]: id["m2"], id["s3"]: id["m3"], id["b1"]: id["m1"]}
    assert sorted(판.하나만) == sorted([id["s1"], id["b1"]])
    assert sorted(판.같은팀) == sorted([id["s2"], id["s3"]])
    assert list(판.가를수없음) == [id["x1"]] and 판.가를수없음[id["x1"]] == sorted([id["m1"], id["m3"]])
    assert 판.안가리킴 == [id["c1"]]
    # Main 끼리의 관련(m1↔m2)은 상위가 아니다
    assert not {id["m1"], id["m2"], id["m3"]} & set(판.채울)
    assert 판.수["고리"] == 0 and 판.수["부모가 Main 이 아닌 것"] == 0


def test61_a02_Main_은_업무속성으로_가른다_kind_가_아니다(db, tmp_path):
    """속성 빈 줄은 앱에 kind=main 이지만 자식이다 — kind 로 가르면 빠진다."""
    m = _채우기()
    libs = _앱(db)
    판 = m.고른다(db, m.읽는다(_파일(tmp_path))[0])
    assert libs["b1"].kind == "main" and libs["b1"].id in 판.채울
    assert 판.수["노션 Main(업무속성)"] == 3


def test61_a03_담당_부서가_다른_부모도_채우고_따로_센다(db, tmp_path):
    m = _채우기()
    libs = _앱(db)
    판 = m.고른다(db, m.읽는다(_파일(tmp_path))[0])
    assert 판.부서다름 == [libs["b1"].id]
    assert 판.수["  · 채울 것 중 담당 부서가 다른 부모"] == 1


def test61_b01_이미_상위가_있으면_멈춘다(db, tmp_path):
    m = _채우기()
    libs = _앱(db)
    libs["s1"].parent_library_id = libs["m3"].id
    db.commit()
    with pytest.raises(m.멈춤, match="상위가 이미 적힌"):
        m.고른다(db, m.읽는다(_파일(tmp_path))[0])


def test61_b02_노션_줄과_앱이_안_맞으면_멈춘다(db, tmp_path):
    m = _채우기()
    _앱(db)
    with pytest.raises(m.멈춤, match="1:1 로 맞지 않습니다"):
        m.고른다(db, m.읽는다(_파일(tmp_path, 줄들[:-2]))[0])


def test61_b03_고리가_생기면_멈춘다(db, tmp_path):
    """노션 Main 은 상위를 안 받아 지금 모양에서는 고리가 못 생긴다 — 그래도 감시가 도는지 심어 잰다.

    「이미 상위가 있으면 멈춤」 을 지나야 고리 감시에 닿으므로, m1 의 상위를 **DB 에만** 두고
    세션 객체에서는 비운다(flush 안 함). 고리 감시는 DB 를 따로 읽는다.
    """
    m = _채우기()
    libs = _앱(db)
    바깥 = models.TaskLibrary(title="노션 밖 업무", kind="main", parent_library_id=libs["s1"].id)
    db.add(바깥)
    db.commit()
    db.execute(models.TaskLibrary.__table__.update()
               .where(models.TaskLibrary.id == libs["m1"].id).values(parent_library_id=바깥.id))
    db.commit()                                         # s1 → m1 → 바깥 → s1 · b1 도 m1 을 거쳐 그 고리에 빠진다
    with db.no_autoflush:
        libs["m1"].parent_library_id = None
        with pytest.raises(m.멈춤, match="고리에 빠지는 줄이 2 개"):
            m.고른다(db, m.읽는다(_파일(tmp_path))[0])
    db.rollback()


def test61_c01_미리보기는_아무것도_안_바꾼다(db, tmp_path, capsys):
    m = _채우기()
    _앱(db)
    전 = m.센다(db), m.관련지문(db)
    m.돌린다(db, 실행=False, 파일=_파일(tmp_path), 사본=False, 짝표=tmp_path / "짝.md")
    assert (m.센다(db), m.관련지문(db)) == 전
    out = capsys.readouterr().out
    assert "채울 것: 4" in out and "바꾸지 않았습니다" in out
    assert "포스터" not in out, "미리보기가 제목을 찍었다 — 값은 안 찍는다"
    assert "포스터" in (tmp_path / "짝.md").read_text(encoding="utf-8")


def test61_c02_실행은_상위만_채우고_관련은_그대로_두고_기록을_남긴다(db, tmp_path):
    m = _채우기()
    libs = _앱(db)
    전지문 = m.관련지문(db)
    m.돌린다(db, 실행=True, 파일=_파일(tmp_path), 사본=False, 짝표=tmp_path / "짝.md")
    db.expire_all()
    assert db.get(models.TaskLibrary, libs["s2"].id).parent_library_id == libs["m2"].id
    assert db.get(models.TaskLibrary, libs["x1"].id).parent_library_id is None
    assert db.get(models.TaskLibrary, libs["m1"].id).parent_library_id is None
    assert m.관련지문(db) == 전지문
    assert m.센다(db)["채움 기록"] == 1
    # 두 번째는 이미 채워져 멈춘다 — 덮지 않는다
    with pytest.raises(m.멈춤, match="상위가 이미 적힌"):
        m.돌린다(db, 실행=True, 파일=_파일(tmp_path), 사본=False, 짝표=tmp_path / "짝.md")


def test61_c03_다시_세기가_어긋나면_되돌린다(db, tmp_path, monkeypatch):
    m = _채우기()
    libs = _앱(db)
    원래 = m.넣는다

    def 관련까지_건드림(db_, 판):
        원래(db_, 판)
        db_.get(models.TaskLibrary, libs["m3"].id).related_library_ids = []
        db_.flush()
    monkeypatch.setattr(m, "넣는다", 관련까지_건드림)
    with pytest.raises(m.멈춤, match="related_library_ids 가 바뀌었습니다"):
        m.돌린다(db, 실행=True, 파일=_파일(tmp_path), 사본=False, 짝표=tmp_path / "짝.md")
    db.expire_all()
    assert db.scalar(select(func.count(models.TaskLibrary.id))
                     .where(models.TaskLibrary.parent_library_id.is_not(None))) == 0
    assert m.센다(db)["채움 기록"] == 0


def test61_c04_실행은_사본을_먼저_뜬다(db, tmp_path, monkeypatch):
    m = _채우기()
    _앱(db)
    불림 = []
    monkeypatch.setattr(m, "사본을_뜬다", lambda: 불림.append(m.센다(db)["상위가 있는 노션 라이브러리"]))
    m.돌린다(db, 실행=True, 파일=_파일(tmp_path), 짝표=tmp_path / "짝.md")
    assert 불림 == [0], "사본이 안 떠졌거나 채운 뒤에 떠졌다"
