# -*- coding: utf-8 -*-
"""CLAUDE.md 를 나눈 뒤의 짝 (2026-10-07).

본문을 `docs/CLAUDE-부록/` 으로 옮기면서 생긴 「두 곳이 같아야 하는 자리」 를 잰다.
"""

from __future__ import annotations

import re

from tests import 기준문서


def test78_a01_0단계의_표와_부록_폴더가_같다():
    """11-3 0단계의 표는 「어느 장의 본문이 어디 있나」 를 말하는 유일한 목록이다.

    표에만 있으면 없는 문서를 읽으라고 하는 것이고, **폴더에만 있으면 그 장을
    고치는 사람이 본문이 따로 있는 줄 모른다** — 뒤엣것이 조용한 쪽이다.
    """
    글 = 기준문서.본문.read_text(encoding="utf-8")
    자리 = 글[글.index("### 0. 고치기 전에 훑는다"):글.index("### 1. 커밋하고 푸시한다")]
    표 = set(re.findall(r"^\|[^|\n]+\|\s*`docs/CLAUDE-부록/([^`\n]+\.md)`\s*\|\s*$", 자리, re.M))
    폴더 = {p.name for p in 기준문서.부록들()}
    # **아무것도 안 보는 것은 통과가 아니다** (11-3) — 둘 다 비면 같다고 나온다
    assert 표, "0단계에서 표를 못 읽었다 — 표의 꼴이 바뀌었나"
    assert 폴더, "부록 폴더에서 문서를 하나도 못 찾았다 — 폴더가 옮겨 갔나"
    assert 표 - 폴더 == set(), f"표에만 있는 문서: {sorted(표 - 폴더)}"
    assert 폴더 - 표 == set(), f"폴더에만 있는 문서(0단계 표에 한 줄을 더한다): {sorted(폴더 - 표)}"


def test78_a02_전체가_부록까지_읽는다():
    """「없어야 한다」 시험들이 기대는 자리 — 이것이 CLAUDE.md 만 읽으면
    그 시험들이 전부 옮긴 장을 안 본 채로 초록이다.

    부록마다 **그 문서에만 있는 줄**(머리말)이 합친 글에 들어 있는지 본다.
    """
    전체 = 기준문서.전체()
    assert 기준문서.본문.read_text(encoding="utf-8") in 전체
    for p in 기준문서.부록들():
        글 = p.read_text(encoding="utf-8")
        assert 글.startswith("# CLAUDE.md 부록 — "), f"{p.name} 의 머리가 다르다"
        assert 글 in 전체, f"{p.name} 을 안 읽는다"
