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


def _본문자리(본문) -> set:
    """`파일 | 줄번호 | 낱말` 에서 (파일, 줄번호) 만 뽑는다.

    **식이 두 곳에 있으면** 한쪽을 고쳐도 다른 쪽은 안 고쳐지고,
    그때 대신 돌던 시험이 더는 대신하지 못하는데 이름은 그대로다.
    """
    return {(칸[0].strip(), int(칸[1].strip()))
            for 칸 in (x.split("|") for x in 본문)
            if len(칸) >= 2 and 칸[1].strip().isdigit()}


def _실명하나() -> str:
    """대응표에서 **두 글자 이상**인 실명 하나. 한 글자짜리는 낱말 안에
    늘 들어가 넘긴 목록에 있으므로 시험에 쓰지 않는다."""
    C = _검사()
    for 실명 in C._anon.표기들():
        if len(실명) >= 2:
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
    실명집합 = set(C._anon.표기들())

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
    실명집합 = set(C._anon.표기들())
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


def test_검사_08_대응표를_읽는_곳이_하나다():
    """**글자로 찾지 않고 센다.**

    전에는 `json.loads` 가 없는지를 봤는데, 그건 10장이 네 번 당했다고
    적은 그 함정이다 — 코드와 설명을 못 가린다. 대신 **대응표 파일 이름이
    코드에 몇 번 나오는지** 센다. 주석에 나와도 세면 되므로 오탐이 없고,
    새로 읽는 곳을 만들면 반드시 걸린다.

    이 작업에서만 "같은 것을 두 곳에서 읽는" 문제가 **네 번** 나왔다.
    """
    셈 = {}
    for p in ROOT.rglob("*.py"):
        if ".venv" in p.parts or "__pycache__" in p.parts:
            continue
        n = p.read_text(encoding="utf-8", errors="ignore").count(
            "anonymize-map" + ".json")
        if n:
            셈[str(p.relative_to(ROOT)).replace(chr(92), "/")] = n
    assert 셈, "대응표 파일 이름이 코드 어디에도 없다 — 읽는 곳이 사라졌다"
    assert sum(셈.values()) == 1, (
        f"대응표를 읽는 곳이 하나가 아니다: {셈}. "
        "scripts/anonymize.py 의 표기들()·가명()·가명수() 를 부르세요.")


def test_검사_09_한_글자_이름은_홀로_섰을_때만_본다(tmp_path):
    """**가르는 축은 위치가 아니라 길이다.**

    이 자료에서 이름은 낱말 한가운데 오는 것이 정상이다(`◯◯M으로`,
    `9명 ◯◯◯ ◯◯◯`). 위치로 가르면 잡던 것을 놓친다. 대신 한 글자
    이름만 홀로 섰을 때로 좁혀, 넘김 목록이 낱말 수만큼 늘어나는 것을
    막는다 — 목록이 133줄에서 10줄로 줄었다.
    """
    C = _검사()
    한글자 = [a for a in C._anon.표기들() if len(a) == 1]
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


def test_검사_10_남은_곳_목록이_본문과_맞는다():
    """**값을 박지 않고 값끼리 맞는지 본다.**

    전에는 `assert 남은` 으로 **비어 있지 않을 것**을 박아 두었다.
    그런데 다 고쳐서 비는 것이 정상인 경우를 안 넣어서, 남은 다섯을
    고치자 **구조는 멀쩡한데 시험이 빨개졌다.** 오늘 성적표에서 겪은
    것과 같은 자리다 (11-3 「마치기 전에 되짚는 것」).
    """
    C = _검사()
    남은 = C.남은곳()
    머리 = (ROOT / "docs" / "이름-남은곳.txt").read_text(encoding="utf-8")
    글 = (ROOT / "scripts" / "check_names.py").read_text(encoding="utf-8")
    assert "아직 안 고친 곳" in 글, "몇 곳 남았는지 말하지 않는다"

    본문 = [x.strip() for x in 머리.splitlines()
          if x.strip() and not x.strip().startswith("#")]
    if not 남은:
        # **비어 있는 것은 정상이다.** 다만 그렇다고 말해야 한다
        assert 본문 == ["지금은 없습니다."], (
            f"목록이 비었는데 본문이 그렇다고 말하지 않는다: {본문[:3]}")
    else:
        # **같은 단위로 견준다.** `남은곳()` 은 (파일, 줄번호) 의
        # set 이라, 한 줄에 이름이 둘이면 본문 2줄 · set 1자리다.
        # 줄 수와 자리 수를 견주면 **목록이 다시 채워지는 순간**
        # (그때가 이 시험이 필요한 때다) 구조는 멀쩡한데 빨개진다.
        본문자리 = _본문자리(본문)
        assert 본문자리 == 남은, (
            f"본문에서 읽은 자리와 센 것이 다르다: "
            f"본문 {sorted(본문자리)[:3]} · 센 것 {sorted(남은)[:3]}")
        assert not any("지금은 없습니다" in x for x in 본문), (
            "남은 것이 있는데 본문에 「지금은 없습니다」 가 적혀 있다")


def test_검사_11_사람이_뒤집은_줄에_표시가_있다():
    """자동 분류가 어디서 틀리는지의 기록이라 규칙보다 값지다."""
    글 = (ROOT / "docs" / "이름-확인됨.txt").read_text(encoding="utf-8")
    assert "자동 분류가 틀린 자리" in 글, "머리에 그 뜻이 없다"
    assert "홀로 섰을 때만" in 글, "한 글자 이름 맞바꿈이 안 적혀 있다"

    # **줄 단위로 센다.** 전에는 `"[사람]" in 글` 이라 **머리말 산문의
    # 글자**로 통과했다 — 붙은 줄이 0개인데 초록이었다 (10장).
    본문 = [x for x in 글.splitlines()
          if x.strip() and not x.strip().startswith("#")]
    사람줄 = [x for x in 본문 if "[사람]" in x]
    assert 사람줄, (
        "[사람] 이 붙은 줄이 하나도 없다 — 머리말에 그 글자가 있어도 "
        "통과하지 않는다. 자동 분류가 틀린 자리는 규칙이 낸 것보다 "
        "값지므로 지우지 말고 쌓는다")
    for 줄 in 사람줄:
        칸 = [x.strip() for x in 줄.split("|")]
        assert len(칸) >= 2 and 칸[1], f"[사람] 줄에 이유가 없다: {줄[:40]}"


# ── 표에 없는 담당자를 세어 말하는가 (2026-09-04) ────────────────────
#
# `check_names` 는 **대응표에 있는 표기만** 찾는다. 그래서 표에 없는 이름은
# 영영 안 보인다 — 이름 하나가 정확히 그 틈으로 공개 커밋에 남았고, 사람이
# 원본과 공개본을 손으로 대조해서야 찾았다.
#
# "아무것도 안 보는 것은 통과가 아니다" 는 막았지만
# **"볼 목록이 불완전하다" 는 안 막혀 있었다.**

def test_표밖_01_대응표에_없는_담당자를_잡는다(tmp_path):
    """①"""
    C = _검사()
    자료 = tmp_path / "가짜.real.json"
    # 두세 글자만 본다 — 사람 이름의 길이다
    자료.write_text('[{"assignee": "없는가"}]', encoding="utf-8")
    본 = C.표밖담당자(tmp_path)
    assert 본["본칸"] >= 1, "담당자 칸을 못 읽었다"
    assert "없는가" in 본["표밖"], f"대응표에 없는 담당자를 못 잡았다: {본}"


def test_표밖_02_대응표에_있는_사람은_안_걸린다(tmp_path):
    """② **과하게 걸려도 고장이다.**"""
    C = _검사()
    있는것 = next(x for x in C._anon.표기들() if 2 <= len(x) <= 3)
    자료 = tmp_path / "가짜.real.json"
    자료.write_text('[{"assignee": "%s"}, {"assignee": "%sM"}]'
                    % (있는것, 있는것), encoding="utf-8")
    본 = C.표밖담당자(tmp_path)
    assert 본["표밖"] == {}, f"대응표에 있는 사람이 걸렸다: {본['표밖']}"


def test_표밖_03_담당자_칸을_하나도_못_읽으면_그렇다고_말한다(tmp_path, monkeypatch, capsys):
    """③ **파싱이 어긋나 아무것도 안 보면서 「0개」 를 내는 것**이
    이번에 겪은 그것이다. 0개와 못 읽음은 다른 말이어야 한다."""
    C = _검사()
    빈곳 = tmp_path / "빈곳"
    빈곳.mkdir()
    본 = C.표밖담당자(빈곳)
    assert 본["본칸"] == 0, "빈 폴더인데 담당자 칸을 읽었다고 한다"

    # **소스를 읽지 않고 실제 출력을 본다.** 전에는 소스에 문구가
    # 있나만 봐서, 문구를 주석에 남긴 채 `print` 를 바꿔도 초록이었다
    monkeypatch.setattr(C, "표밖담당자", lambda *a, **k: 본)
    monkeypatch.setattr(C, "_anon", C._anon)
    monkeypatch.setattr("sys.argv", ["check_names.py", "docs"])
    C.main()
    말 = capsys.readouterr().out
    assert "담당자 칸을 하나도 못 읽었습니다" in 말, (
        f"못 읽은 것과 0개를 같은 말로 낸다: {말[-200:]}")
    assert "대응표에 없는 담당자 표기 0개" not in 말, (
        f"못 읽었는데 0개라고 말한다: {말[-200:]}")


def _가짜DB(폴더, 표, 칸, 값):
    """`app.db` 흉내 — 표와 칸 하나에 값 하나."""
    import sqlite3
    이음 = sqlite3.connect(폴더 / "app.db")
    이음.execute(f"CREATE TABLE {표} ({칸} TEXT)")
    이음.execute(f"INSERT INTO {표} VALUES (?)", (값,))
    이음.commit()
    이음.close()


def test_표밖_05_DB_갈래도_담당칸에서_뽑아_쓴다(tmp_path, monkeypatch):
    """**「어디의 무엇」 한 목록에서 두 갈래가 파생한다.**

    전에는 `담당칸` 을 JSON 갈래만 쓰고 DB 갈래는 자기 목록을 따로
    들었다 — **넷째를 더해도 DB 는 안 따라왔다.** 「늘어나면 여기
    더한다」 는 주석이 절반만 사실이었고, 이 검사가 고친 고장이
    바로 「보는 목록이 불완전했다」 인데 같은 모양이 한 칸 옆에
    있었다.

    **목록을 줄이면 그 칸이 실제로 안 보이는 것**으로 잰다 —
    박아 두었다면 줄여도 그대로 보인다.
    """
    C = _검사()
    없는이름 = "쟈븧"          # 대응표에도 아는말에도 없는 두 글자
    assert 없는이름 not in C._anon.표기들()
    _가짜DB(tmp_path, "programs", "host", 없는이름)

    본 = C.표밖담당자(tmp_path)
    assert 없는이름 in 본["표밖"], f"DB 의 host 칸을 안 봤다: {본}"

    # 목록에서 그 칸을 빼면 **안 보여야** 한다
    monkeypatch.setattr(C, "DB칸", tuple(x for x in C.DB칸 if x[0] != "programs"))
    본2 = C.표밖담당자(tmp_path)
    assert 없는이름 not in 본2["표밖"], (
        "목록에서 뺐는데도 봤다 — DB 갈래가 자기 목록을 따로 든다")
    assert 본2["본칸"] == 0, 본2


def test_표밖_06_두_갈래가_같은_목록에서_나온다():
    """`JSON칸`·`DB칸` 이 `담당칸` 그대로인가. 위 시험이 「DB칸 을
    쓴다」 까지만 재므로, 그 `DB칸` 이 어디서 왔는지를 여기서 잇는다.

    **소스를 읽지 않는다** — 값끼리 견준다.
    """
    C = _검사()
    assert C.JSON칸 == frozenset(x[1] for x in C.담당칸 if x[0] == "json")
    assert C.DB칸 == tuple((x[1], x[2]) for x in C.담당칸 if x[0] == "db")
    갈래 = {x[0] for x in C.담당칸}
    assert 갈래 == {"json", "db"}, (
        f"모르는 갈래가 있다 — 아무 갈래도 안 보고 지나간다: {갈래}")
    assert C.JSON칸 and C.DB칸, "한 갈래가 비었다"


def test_표밖_04_지금_저장소는_0개다():
    """정한 것은 `anonymize.KEEP`(부서·역할)과 `_이름아님`(흔한 말)에
    쌓인다.

    **이 시험은 `data/*.real.json` 에 기댄다.** 그 파일은 gitignore
    라 새로 받은 사본에서는 "담당자 칸을 하나도 못 읽었다" 로
    빨개진다 — 대응표에 기대는 시험들과 같은 상태이고, 새 규칙은
    아니지만 기대는 파일이 하나 늘었다.
    """
    C = _검사()
    본 = C.표밖담당자()
    assert 본["본칸"] > 0, "담당자 칸을 하나도 못 읽었다"
    가려서 = {C.가린다(k): v for k, v in 본["표밖"].items()}
    assert 본["표밖"] == {}, f"대응표에 없는 담당자가 남아 있다: {가려서}"


def test_검사_10b_목록이_채워진_모양도_본다(tmp_path, monkeypatch):
    """**「안 비었을 때」 갈래가 한 번도 안 돌고 있었다.**

    저장소의 목록이 비어 있어서 `else` 쪽이 실행되지 않았다. 그 갈래가
    처음 도는 때는 **목록이 다시 채워지는 때** — 이 시험이 필요한 바로
    그때다. 손으로 한 번 본 것은 자동으로 지켜지지 않는다.

    한 파일 한 줄에 이름이 둘이면 **본문 2줄 · 자리 1개**다. 단위를
    맞춰 견주는지가 이 갈래의 전부다.
    """
    C = _검사()
    목록 = tmp_path / "이름-남은곳.txt"
    머리 = "# 아직 안 고친 자리" + chr(10) + "#" + chr(10) + chr(10)
    다섯 = [
        "CLAUDE.md | 1475 | 홍◯◯", "CLAUDE.md | 1475 | 민◯◯",
        "CLAUDE.md | 1672 | 이◯◯",
        "app/templates/expenses.html | 74 | 홍◯◯",
        "app/templates/expenses.html | 74 | 민◯◯",
    ]
    목록.write_text(머리 + chr(10).join(다섯) + chr(10), encoding="utf-8")
    monkeypatch.setattr(C, "남은목록", 목록)

    남은 = C.남은곳()
    assert len(남은) == 3, f"다섯 줄에서 자리 셋이 나와야 한다: {남은}"

    # `test_검사_10` 의 else 갈래와 같은 셈
    본문 = [x.strip() for x in 목록.read_text(encoding="utf-8").splitlines()
          if x.strip() and not x.strip().startswith("#")]
    assert _본문자리(본문) == 남은, "줄 수가 아니라 자리로 견뎌야 한다"
    assert len(본문) == 5 and len(남은) == 3, (
        "줄 수와 자리 수가 다른 모양이어야 이 갈래가 뜻이 있다")
