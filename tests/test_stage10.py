"""검사 둘의 범위 맞추기 (Y-a) — 찾는 형태는 한 곳에서 나온다.

문서 검사(check_names)와 개발 DB 게이트(check_dev_db)가 다른 변형을 보면
그 틈이 다음 구멍이다. 막는 코드마다 막히는 쪽과 뚫리는 쪽을 함께 잰다.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sqlite3

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _번호하나():
    anon = _load("anonymize")
    try:
        phones = anon.load_map()[1]
    except SystemExit:
        pytest.skip("대응표가 없다 — 새로 받은 사본에서는 잴 것이 없다")
    if not phones:
        pytest.skip("대응표에 번호가 없다")
    return phones[0]


# ════════════════════════════════════════════════════════════════════
# 1-a·1-b. 변형은 한 곳에서 — 하이픈으로 적어도 숫자형이 함께 나온다
# ════════════════════════════════════════════════════════════════════


def test10_v01_변형을_만드는_곳이_하나다():
    """번호변형들 은 anonymize 에만 정의되고, 두 검사가 그것을 부른다."""
    anon = _load("anonymize")
    assert callable(anon.번호변형들)
    cn_src = (ROOT / "scripts" / "check_names.py").read_text(encoding="utf-8")
    dev_src = (ROOT / "scripts" / "check_dev_db.py").read_text(encoding="utf-8")
    # 게이트는 직접 부르고, 문서 검사는 표기들()(변형 포함)로 받는다
    assert "번호변형들" in dev_src
    assert "def 번호변형들" not in dev_src and "def 번호변형들" not in cn_src
    # 3-4-4 를 제 손으로 조립하는 곳이 검사들에 없다
    assert "[:3]" not in dev_src and "[3:7]" not in dev_src


def test10_v02_하이픈으로_적어도_두_형이_다_나온다():
    """검토자 5-a — 대응표에 하이픈 번호를 넣어도 숫자-그대로 형이 빠지지
    않는다. 합성 번호로 규칙 자체를 잰다."""
    anon = _load("anonymize")
    assert anon.번호변형들("010-1234-5678") == [
        "01012345678", "010-1234-5678", "010 1234 5678"]
    assert anon.번호변형들("01012345678") == [
        "01012345678", "010-1234-5678", "010 1234 5678"]
    # 11자리가 아니면 변형을 지어내지 않되, **원표기는 버리지 않는다** —
    # 지역번호를 하이픈으로 적어도 그 모양 그대로는 찾는다 (검토 반영)
    assert anon.번호변형들("021234567") == ["021234567"]
    assert anon.번호변형들("02-123-4567") == ["021234567", "02-123-4567"]


# ════════════════════════════════════════════════════════════════════
# 1-c. 두 검사가 같은 문자열에 같은 판정을 낸다
# ════════════════════════════════════════════════════════════════════


def test10_v03_문서에_3_4_4_실번호를_심으면_걸린다(tmp_path):
    real, fake = _번호하나()
    anon = _load("anonymize")
    cn = _load("check_names")
    실형 = anon.번호변형들(real)
    가형 = anon.번호변형들(fake)
    assert len(실형) >= 2                                 # 3-4-4 형이 있다

    p = tmp_path / "글.md"
    p.write_text(f"연락처는 {실형[1]} 입니다", encoding="utf-8")
    assert cn.찾는다(cn._anon.표기들(), [p])              # 막는 쪽 — 3-4-4 로 걸린다
    p.write_text(f"연락처는 {실형[0]} 입니다", encoding="utf-8")
    assert cn.찾는다(cn._anon.표기들(), [p])              # 숫자 그대로도
    p.write_text(f"연락처는 {가형[1]} 입니다", encoding="utf-8")
    assert not cn.찾는다(cn._anon.표기들(), [p])          # 가명 번호는 통과


def test10_v04_두_검사가_같은_문자열에_같은_판정이다(tmp_path):
    real, fake = _번호하나()
    anon = _load("anonymize")
    cn = _load("check_names")
    dev = _load("check_dev_db")

    def 게이트판정(글: str) -> bool:
        db = tmp_path / "one.db"
        db.unlink(missing_ok=True)
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE meetings (body TEXT)")
        con.execute("INSERT INTO meetings VALUES (?)", (글,))
        con.commit()
        con.close()
        return bool(dev.실명이있나(db))

    def 문서판정(글: str) -> bool:
        p = tmp_path / "글.md"
        p.write_text(글, encoding="utf-8")
        return bool(cn.찾는다(cn._anon.표기들(), [p]))

    실형 = anon.번호변형들(real)
    for 글 in [f"연락처 {실형[0]} 확인", f"연락처 {실형[1]} 확인",
              f"연락처 {실형[2]} 확인"]:
        assert 문서판정(글) and 게이트판정(글), "실번호 변형에 두 검사가 갈렸다"
    for 글 in [f"연락처 {v} 확인" for v in anon.번호변형들(fake)]:
        assert not 문서판정(글) and not 게이트판정(글), "가명 번호에 두 검사가 갈렸다"


# ════════════════════════════════════════════════════════════════════
# 2-c. 제외칸마다 이유와 쓰는 곳이 있다 — 근거 없는 제외를 막는다
# ════════════════════════════════════════════════════════════════════


def test10_e01_제외칸의_근거_자리가_비면_실패한다():
    """자리만 채우고 거짓을 적는 것은 못 막지만, 빈 채로 늘어나는 것은
    막는다 (지시문 2-c). 근거는 「이유 — 근거: 파일:줄」 꼴이다."""
    import re

    dev = _load("check_dev_db")
    나쁜것 = []
    for 칸, 값 in dev.제외칸.items():
        if not re.search(r".+ — 근거: [\w/.]+\.py:\d+", 값):
            나쁜것.append(칸)
    assert 나쁜것 == [], f"근거(파일:줄) 없는 제외칸: {나쁜것}"
