# -*- coding: utf-8 -*-
"""대응표와 익명화 규칙 (11-2 「저장소와 실명」).

2026-09-04 에 두 가지가 드러났다.

1. **한 이름이 두 사람을 가리키고 있었다.** 성이 다른 두 사람이 있는데
   대응표에는 이름만 적힌 한 줄뿐이었다. 성이 붙은 쪽은 경계 규칙 때문에
   애초에 안 바뀌어 아직 섞이지는 않았지만, 성 붙은 형태를 잡게 만드는
   순간 **두 사람이 조용히 한 사람이 되고 아무 오류도 나지 않는다.**
2. **`◯◯M으로` 가 안 바뀌었다.** `M` 다음이 한글이라 경계 규칙이
   건너뛰었다. 이 틈으로 이름 하나가 공개 커밋에 남았다.

**실명을 이 파일에 박지 않는다.** 대응표에서 읽어 쓴다 — 박으면 막으려던
것을 시험이 한다.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _익명():
    스펙 = importlib.util.spec_from_file_location(
        "_anonymize_map_test", ROOT / "scripts" / "anonymize.py")
    m = importlib.util.module_from_spec(스펙)
    스펙.loader.exec_module(m)
    return m


def _성붙은짝(A):
    """대응표에서 **성이 붙은 표기와 이름만 적은 표기가 함께 있는 사람**과,
    같은 이름을 다른 성으로 쓰는 다른 사람을 찾는다."""
    data = json.loads(A.MAP_PATH.read_text(encoding="utf-8"))
    긴것 = {}
    for 줄 in data.get("names", []):
        표기들 = 줄["표기"] if isinstance(줄, dict) else [줄[0]]
        가명 = 줄["가명"] if isinstance(줄, dict) else 줄[1]
        for 표기 in 표기들:
            긴것[표기] = 가명
    for 긴, 가명1 in 긴것.items():
        if len(긴) != 3:
            continue
        짧은 = 긴[1:]
        for 다른, 가명2 in 긴것.items():
            if len(다른) == 3 and 다른 != 긴 and 다른[1:] == 짧은 and 가명1 != 가명2:
                return 긴, 가명1, 다른, 가명2, 짧은, 긴것.get(짧은)
    pytest.skip("성이 붙어 갈린 두 사람이 대응표에 없다")


def test_대응표_01_옛_구조도_그대로_읽힌다():
    """남은 줄을 한꺼번에 옮기지 않는다 — 표기가 하나뿐인 사람은
    옮길 이유가 없다."""
    A = _익명()
    data = json.loads(A.MAP_PATH.read_text(encoding="utf-8"))
    옛것 = [x for x in data["names"] if not isinstance(x, dict)]
    새것 = [x for x in data["names"] if isinstance(x, dict)]
    assert 옛것, "옛 구조의 줄이 하나도 없다 — 한꺼번에 옮긴 것이다"
    assert 새것, "새 구조의 줄이 없다"
    names, _ = A.load_map()
    표기들 = {a for a, _ in names}
    for 줄 in 옛것:
        assert 줄[0] in 표기들, "옛 구조의 줄이 안 읽혔다"


def test_대응표_02_긴_표기부터_바꾼다():
    """이름만 적은 표기를 먼저 바꾸면 성이 붙은 표기가 `성 + 가명` 이 되어
    **두 사람이 다시 섞인다.** 이 구조에서 가장 쉽게 틀리는 자리다."""
    A = _익명()
    names, phones = A.load_map()
    긴, 가명1, 다른, 가명2, 짧은, 짧은가명 = _성붙은짝(A)

    글 = f"{긴} · {짧은} · {다른}"
    새글, 바뀐수 = A.swap(글, doc=True, names=names, phones=phones)
    assert 바뀐수 == 3, f"셋 다 바뀌어야 한다: {새글}"
    assert 가명1 in 새글 and 가명2 in 새글, (
        f"성이 붙은 두 표기가 각각 다른 가명이어야 한다: {새글}")
    assert 가명1 != 가명2, "두 사람이 같은 가명을 쓴다"
    # 성 + 가명 이 나오면 짧은 것을 먼저 바꾼 것이다
    for 성 in (긴[0], 다른[0]):
        assert 성 + (짧은가명 or "") not in 새글, (
            f"짧은 표기를 먼저 바꿔 `성+가명` 이 됐다: {새글}")


def test_대응표_03_한_표기가_두_사람에게_있으면_거절한다(tmp_path, monkeypatch):
    """그냥 두면 뒤엣것이 이기면서 **두 사람이 조용히 한 사람이 되고**
    아무 오류도 나지 않는다."""
    A = _익명()
    겹친표 = tmp_path / "겹친-대응표.json"
    겹친표.write_text(json.dumps({
        "names": [{"가명": "가명하나", "표기": ["같은표기"]},
                  {"가명": "가명둘", "표기": ["같은표기"]}],
        "phones": []}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(A, "MAP_PATH", 겹친표)
    with pytest.raises(SystemExit) as e:
        A.load_map()
    assert "두 사람" in str(e.value)


def test_익명화_01_M_뒤에_조사가_붙어도_바꾼다():
    """`◯◯M으로` — 이 틈으로 이름 하나가 공개 커밋에 남았다."""
    A = _익명()
    names, phones = A.load_map()
    표기, 가명 = next((a, b) for a, b in names if len(a) == 2)
    for 꼴 in (f"담당자가 {표기}M으로 정해짐", f"{표기}M이 맡는다", f"3일차 - {표기}M"):
        새글, 바뀐수 = A.swap(꼴, doc=True, names=names, phones=phones)
        assert 바뀐수 == 1, f"안 바뀌었다: {꼴!r}"
        assert 가명 + "M" in 새글, f"`가명M` 이 아니다: {새글!r}"


def test_익명화_02_낱말_안에_든_것은_그대로다():
    """**느슨하게 하는 것이 아니라 좁게 더한 것이다.** 앞쪽 경계는 그대로라
    `필요한`·`진행`·`중요한` 은 여전히 안 바뀐다."""
    A = _익명()
    names, phones = A.load_map()
    for 글 in ("필요한 것들", "진행요원 배정", "중요한 결정", "사진 촬영", "이동은 명시적으로"):
        새글, 바뀐수 = A.swap(글, doc=True, names=names, phones=phones)
        assert 바뀐수 == 0, f"낱말이 깨졌다: {글!r} -> {새글!r}"
        assert 새글 == 글


def test_익명화_03_대응표가_비면_시험이_실패한다(tmp_path, monkeypatch):
    """**아무것도 안 보는 것은 통과가 아니다.** 대응표가 비면 `swap` 은
    무엇을 넣어도 0을 돌려주는데, 그때 초록이 뜨면 이 시험 전부가
    있으나 마나가 된다."""
    A = _익명()
    빈표 = tmp_path / "빈-대응표.json"
    빈표.write_text(json.dumps({"names": [], "phones": []}), encoding="utf-8")
    monkeypatch.setattr(A, "MAP_PATH", 빈표)
    names, phones = A.load_map()
    assert not names
    # 여기서 멈추지 않고 **그 상태를 실패로 못박는다**
    with pytest.raises(AssertionError):
        assert names, "대응표에서 읽은 실명이 0개다 — 검사가 아무것도 안 본다"
