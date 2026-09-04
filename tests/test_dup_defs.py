# -*- coding: utf-8 -*-
"""같은 이름의 시험이 둘이면 뒤엣것이 이기고 앞엣것은 한 번도 안 돈다.

2026-09-04 에 `tests/test_suggest_llm.py` 에 같은 블록이 두 번 들어가
최상위 `def` 셋이 중복 정의됐다. 그중 `test_가드_07` 은 **새로 쓴 것이
앞, 지우려던 옛 것이 뒤**여서 실제로 도는 것은 소스를 읽는 옛 판이었다.
그 판의 주제가 정확히 「소스를 읽는 단언을 실제로 돌리는 시험으로」
였는데 그 한 자리에서 성립하지 않았다.

**개수로는 안 잡힌다.** 가려진 `def` 는 애초에 수집되지 않으므로
`--collect-only` 가 중복 전후로 똑같은 수를 낸다. 이름을 봐야 한다.
"""

from __future__ import annotations

import ast
import collections
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def 겹친이름(글: str) -> dict:
    """한 모듈 안에서 두 번 이상 정의된 최상위 이름 → 줄 번호들.

    **클래스와 대입도 본다** — `def` 만 보면 `이름 = ...` 이 뒤에서
    같은 이름을 덮는 것을 놓친다.
    """
    자리 = collections.defaultdict(list)
    for n in ast.parse(글).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            자리[n.name].append(n.lineno)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    자리[t.id].append(n.lineno)
    return {k: v for k, v in 자리.items() if len(v) > 1}


def test_중복_01_검사가_실제로_잡는다():
    """**아무것도 안 보는 검사는 통과가 아니다** (11-3).

    아래 시험은 저장소가 깨끗하면 늘 초록이라, 검사가 망가져도
    초록이다. 그래서 일부러 두 번 적은 것을 여기서 먼저 잡는다.
    """
    가짜 = (chr(10)).join([
        "def test_하나():",
        "    pass",
        "",
        "",
        "def test_하나():",
        "    pass",
    ])
    겹침 = 겹친이름(가짜)
    assert 겹침 == {"test_하나": [1, 5]}, 겹침


def test_중복_02_대입이_def_를_덮는_것도_잡는다():
    """`def 표본()` 뒤에 `표본 = [...]` 가 오면 함수가 사라진다."""
    가짜 = (chr(10)).join(["def 표본():", "    pass", "", "", "표본 = [1, 2]"])
    assert "표본" in 겹친이름(가짜)


def test_중복_03_한_이름이_한_번씩이면_안_잡는다():
    """과하게 걸려도 고장이다 — 다른 파일의 같은 이름은 상관없다."""
    가짜 = (chr(10)).join(["def test_하나():", "    pass", "", "",
                           "def test_둘():", "    pass"])
    assert 겹친이름(가짜) == {}


def test_중복_04_tests_전체에_같은_이름이_없다():
    """**여기가 본 검사다.** `tests/` 의 모든 파일을 본다."""
    파일들 = sorted((ROOT / "tests").glob("test_*.py"))
    assert len(파일들) >= 10, f"볼 파일이 너무 적다: {len(파일들)}개"

    걸린것 = {}
    for p in 파일들:
        겹침 = 겹친이름(p.read_text(encoding="utf-8"))
        if 겹침:
            걸린것[p.name] = 겹침
    assert not 걸린것, (
        f"같은 이름이 두 번 정의됐다 — 뒤엣것만 돈다: {걸린것}")

