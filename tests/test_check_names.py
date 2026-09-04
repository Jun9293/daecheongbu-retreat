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


def test_검사_05_넘긴_낱말은_안_걸리고_홀로_선_이름은_걸린다(tmp_path):
    """**넘기는 것은 이름이 아니라 낱말이다.**

    전에는 이름을 통째로 넘겨서 **회의록에서 홀로 선 그 이름도** 안
    걸렸다 — 지키려던 바로 그것이 빠져 있었다. 과하게 걸려도 고장이지만
    (매번 빨개지면 사람이 무시한다 · 4-11), 못 걸리는 쪽이 더 나쁘다.
    """
    C = _검사()
    넘김 = C.넘긴것()
    assert 넘김, "넘긴 목록이 비어 있다"
    names, _ = C._anon.load_map()
    실명집합 = {a for a, _ in names}

    # 넘긴 낱말 하나를 골라, 그 낱말 안에 든 이름이 안 걸리는지
    골랐다 = None
    for 낱말 in sorted(넘김):
        든이름 = [r for r in 실명집합 if r in 낱말 and r != 낱말]
        if 든이름:
            골랐다 = (낱말, 든이름[0]); break
    assert 골랐다, "이름을 품은 넘김 낱말이 없다 — 이 시험이 무의미하다"
    낱말, 이름 = 골랐다
    p = tmp_path / "글.md"
    p.write_text(f"이 문서는 {낱말} 을 다룹니다", encoding="utf-8")
    assert C.찾는다([이름], [p]) == [], f"넘긴 낱말이 걸렸다: {낱말!r}"

    # **그런데 그 이름이 홀로 서면 걸려야 한다** — 여기가 옛 방식의 구멍이었다
    p.write_text(f"담당은 {이름} 입니다", encoding="utf-8")
    assert C.찾는다([이름], [p]), (
        f"홀로 선 {C.가린다(이름)} 이 안 걸린다 — 이름을 통째로 넘기고 있다")


def test_검사_06_넘긴_목록이_낱말이고_이유가_있다():
    """이름만 적힌 줄이 있으면 그 이름은 어디서든 안 걸린다."""
    C = _검사()
    names, _ = C._anon.load_map()
    실명집합 = {a for a, _ in names}
    글 = (ROOT / "docs" / "이름-확인됨.txt").read_text(encoding="utf-8")
    줄들 = [x for x in 글.splitlines()
           if x.strip() and not x.strip().startswith("#")]
    assert 줄들, "넘긴 목록이 비어 있다"
    for 줄 in 줄들:
        칸 = [x.strip() for x in 줄.split("|")]
        assert len(칸) >= 2 and 칸[1], f"이유가 없다: {줄[:30]}"
        assert 칸[0] not in 실명집합, (
            f"이름만 적힌 줄이 있다 — 그 이름은 어디서든 안 걸린다: "
            f"{C.가린다(칸[0])}")


def test_검사_06b_예외는_셋뿐이고_검토_보고는_예외가_아니다():
    """어떤 것을 금지하는 도구는 그것을 설명하려고 스스로 담게 된다
    (10장). 자기 코드 · 자기 시험 · 넘길 목록이 그것이다.

    **검토 보고는 예외가 아니다.** 운영 자료에서 온 것을 계속 담을
    파일이라, 빼면 정확히 새는 자리를 안 보게 된다.
    """
    C = _검사()
    예외 = C.예외파일()
    assert {x.name for x in 예외} == {"check_names.py", "test_check_names.py",
                                    "이름-확인됨.txt", "이름-남은곳.txt"}, (
        f"예외가 달라졌다: {sorted(x.name for x in 예외)}")
    보고 = (ROOT / "docs" / "review" / "최근.md").resolve()
    assert 보고 not in 예외, "검토 보고가 예외로 빠져 있다"


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


def test_검사_09_한_글자_이름은_홀로_섰을_때만_본다(tmp_path):
    """**가르는 축은 위치가 아니라 길이다.**

    이 자료에서 이름은 낱말 한가운데 오는 것이 정상이다(`◯◯M으로`,
    `9명 ◯◯◯ ◯◯◯`). 위치로 가르면 잡던 것을 놓친다. 대신 한 글자
    이름만 홀로 섰을 때로 좁혀, 넘김 목록이 낱말 수만큼 늘어나는 것을
    막는다 — 목록이 133줄에서 10줄로 줄었다.
    """
    C = _검사()
    names, _ = C._anon.load_map()
    한글자 = [a for a, _ in names if len(a) == 1]
    if not 한글자:
        pytest.skip("한 글자 이름이 대응표에 없다")
    이름 = 한글자[0]
    p = tmp_path / "글.md"

    # 낱말 안에 들면 안 본다
    p.write_text(f"{이름}행 중입니다", encoding="utf-8")
    assert C.찾는다([이름], [p]) == [], "낱말 안에 든 한 글자가 걸렸다"

    # **홀로 서면 여전히 걸린다** — 여기가 지키려던 자리다
    p.write_text(f"담당은 {이름} 입니다", encoding="utf-8")
    assert C.찾는다([이름], [p]), (
        f"홀로 선 {C.가린다(이름)} 이 안 걸린다")


def test_검사_10_남은_곳은_넘기되_세어서_말한다():
    """조용히 넘기면 그 목록이 있다는 것조차 잊힌다."""
    C = _검사()
    남은 = C.남은곳()
    assert 남은, "이름-남은곳.txt 가 비어 있다"
    글 = (ROOT / "scripts" / "check_names.py").read_text(encoding="utf-8")
    assert "아직 안 고친 곳" in 글, "몇 곳 남았는지 말하지 않는다"
    머리 = (ROOT / "docs" / "이름-남은곳.txt").read_text(encoding="utf-8")
    assert "아직 안 고친 것" in 머리, "왜 안 고쳤는지가 없다"
    assert "main 에 합친 뒤" in 머리, "언제 고칠지가 없다"


def test_검사_11_사람이_뒤집은_줄에_표시가_있다():
    """자동 분류가 어디서 틀리는지의 기록이라 규칙보다 값지다."""
    글 = (ROOT / "docs" / "이름-확인됨.txt").read_text(encoding="utf-8")
    assert "[사람]" in 글, "사람이 뒤집은 줄에 표시가 없다"
    assert "자동 분류가 틀린 자리" in 글, "머리에 그 뜻이 없다"
    assert "홀로 섰을 때만" in 글, "한 글자 이름 맞바꿈이 안 적혀 있다"
