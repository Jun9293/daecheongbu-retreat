# -*- coding: utf-8 -*-
"""실명 검사가 **실제로 무언가를 보고 있는지** 시험한다 (11-2).

2026-09-04 에 커밋 전 실명 검사가 `list(m.keys())` 로 대응표를 읽고 있었다.
대응표는 `{"names": [...], "phones": [...]}` 라서 그것이 읽은 것은
**키 두 개**였고, 실명 29개 중 **0개**를 보면서 초록을 냈다.

같은 모양이 이날 셋이었다 — 이 검사, `'더있음'` 을 제안으로 센 것,
덮어쓰기 가드. **셋 다 통과하는 쪽만 시험돼 있었다.**

**실명을 이 파일에 박지 않는다.** 박으면 막으려던 것을 시험이 한다.
대응표에서 읽어 쓰고, 실패 문구에도 가려서 낸다.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _검사():
    스펙 = importlib.util.spec_from_file_location(
        "_check_names", ROOT / "scripts" / "check_names.py")
    m = importlib.util.module_from_spec(스펙)
    스펙.loader.exec_module(m)
    return m


def _실명하나() -> str:
    """대응표에서 **두 글자 이상**인 실명 하나. 한 글자짜리는 낱말 안에
    늘 들어가 넘긴 목록에 있으므로 시험에 쓰지 않는다."""
    C = _검사()
    names, _ = C._anon.load_map()
    넘김 = C.넘긴것()
    for 실명, _가명 in names:
        if len(실명) >= 2 and ("*", 실명) not in 넘김:
            return 실명
    pytest.skip("두 글자 이상인 실명이 대응표에 없다")


def test_검사_01_대응표에서_읽은_실명이_0개면_실패한다(tmp_path, monkeypatch):
    """**아무것도 안 보는 것은 통과가 아니다.**

    이 시험이 이번 사고를 직접 겨눈다 — 검사가 조용히 빈 목록을 들고
    초록을 내면, 있으나 마나가 아니라 **있다고 믿게 만들어 더 나쁘다.**
    """
    빈표 = tmp_path / "빈-대응표.json"
    빈표.write_text(json.dumps({"names": [], "phones": []}), encoding="utf-8")
    r = subprocess.run(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"),
         str(ROOT / "scripts" / "check_names.py"), "docs"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT, env={**dict(__import__("os").environ),
                       "PYTHONIOENCODING": "utf-8"})
    # 진짜 대응표로는 0이 아니어야 한다 (0개면 아래 경로로 빠진다)
    assert "실명 0개" not in (r.stdout or ""), "진짜 대응표에서 0개를 읽었다"

    # 빈 대응표를 물리면 **2번(검사 불능)** 으로 끝나야 한다
    C = _검사()
    monkeypatch.setattr(C._anon, "MAP_PATH", 빈표)
    monkeypatch.setattr("sys.argv", ["check_names.py", "docs"])
    assert C.main() == 2, "빈 대응표인데 통과했다"


def test_검사_02_홀로_선_실명을_잡는다(tmp_path):
    C = _검사()
    실명 = _실명하나()
    p = tmp_path / "글.md"
    p.write_text(f"담당은 {실명} 입니다", encoding="utf-8")
    assert C.찾는다([실명], [p]), "홀로 선 실명을 못 잡았다"


def test_검사_03_성이_붙어도_잡는다(tmp_path):
    """**`anonymize.py` 가 못 바꾸는 자리를 이쪽이 잡아야 한다.**

    바꾸는 쪽은 앞뒤가 한글이면 건너뛴다 — `필요한`·`진행` 을 지키려고
    그렇게 뒀다. 그래서 성이 붙은 `최◯◯` 는 안 바뀐다.
    찾는 쪽까지 같은 규칙을 쓰면 **아무도 그것을 못 본다.**
    """
    C = _검사()
    실명 = _실명하나()
    p = tmp_path / "글.md"
    p.write_text(f"전달: 최{실명} → 방송팀", encoding="utf-8")
    나온것 = C.찾는다([실명], [p])
    assert 나온것, f"성이 붙은 형태를 못 잡았다: 최{C.가린다(실명)}"


def test_검사_04_M_뒤에_조사가_붙어도_잡는다(tmp_path):
    """`◯◯M으로` — 바꾸는 쪽은 뒤가 한글이라 건너뛴다. 실제로 이 모양이
    공개 커밋에 남았다."""
    C = _검사()
    실명 = _실명하나()
    p = tmp_path / "글.md"
    p.write_text(f"담당자가 {실명}M으로 정해짐", encoding="utf-8")
    assert C.찾는다([실명], [p]), "M 뒤에 조사가 붙은 형태를 못 잡았다"


def test_검사_05_넘긴_것은_안_걸린다(tmp_path):
    """**과하게 걸려도 고장이다.** 매번 빨개지면 사람이 무시하기 시작하고,
    한 번 무시하면 돌아오지 않는다 (4-11)."""
    C = _검사()
    넘김 = C.넘긴것()
    별표 = [낱말 for 파일, 낱말 in 넘김 if 파일 == "*"]
    assert 별표, "넘긴 목록에 `*` 항목이 없다 — 이 시험이 무의미하다"
    for 낱말 in 별표:
        assert C.넘기나(넘김, "docs/아무거나.md", 낱말), f"{낱말} 이 안 넘어간다"


def test_검사_06_넘긴_목록에_이유가_적혀_있다():
    """왜 넘겼는지가 없으면 다음 사람이 지울지 둘지 판단할 수 없다."""
    글 = (ROOT / "docs" / "이름-확인됨.txt").read_text(encoding="utf-8")
    줄들 = [x for x in 글.splitlines()
           if x.strip() and not x.strip().startswith("#")]
    assert 줄들, "넘긴 목록이 비어 있다"
    for 줄 in 줄들:
        칸 = [x.strip() for x in 줄.split("|")]
        assert len(칸) >= 3 and 칸[2], f"이유가 없다: {줄[:40]}"


def test_검사_07_gitignore_된_것은_안_본다():
    """`data/*.real.md` 는 실명을 담는 것이 규칙이다 (11-2). 저장소에
    안 올라가므로 이 검사의 몫이 아니다."""
    C = _검사()
    r = subprocess.run(["git", "check-ignore", "-q", "data/제안-1판.real.md"],
                       capture_output=True, cwd=ROOT)
    assert r.returncode == 0, "data/*.real.md 가 gitignore 되지 않았다"
    assert C.무시되나(ROOT / "data" / "제안-1판.real.md")


def test_검사_08_대응표를_anonymize_와_같은_코드로_읽는다():
    """두 곳에서 읽으면 한쪽만 구조를 잘못 읽는다 — 이번에 정확히 그랬다."""
    글 = (ROOT / "scripts" / "check_names.py").read_text(encoding="utf-8")
    assert "_anon.load_map()" in 글, "대응표를 따로 읽고 있다"
    assert "json.loads" not in 글, "대응표를 직접 파싱하고 있다"
