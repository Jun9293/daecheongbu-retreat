"""세는 말을 검사가 잡게 (+ 이름 · 점검 계정).

10장의 「자리를 세어 두지 않습니다」 를 **사람이 다섯 판 연속 어겼다.**
매번 커밋 전 검토가 잡았다 — 규칙을 아는 사람이 다섯 번 어겼으면
그것은 사람이 조심할 일이 아니다. 검사로 옮긴다.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _심는다(tmp_path, 글: str) -> list:
    """한 파일에 글을 심고 검사에 물어본다."""
    cc = _load("check_counts")
    p = tmp_path / "심은것.md"
    p.write_text(글, encoding="utf-8")
    # 저장소 밖 파일이라 relative_to 가 터진다 — ROOT 를 잠깐 옮긴다
    옛ROOT = cc.ROOT
    cc.ROOT = tmp_path
    try:
        return cc.찾는다([p])
    finally:
        cc.ROOT = 옛ROOT


# ════════════════════════════════════════════════════════════════════
# 1. 세는 말 — 막는 쪽 · 뚫리는 쪽 · 볼 것을 보나
# ════════════════════════════════════════════════════════════════════


def test17_c01_세는_말을_심으면_걸린다(tmp_path):
    """막는 쪽. 다섯 판이 실제로 남긴 모양들을 그대로 심는다."""
    for 글 in ("이 값을 보는 세 곳(period · deps · notify)",
               "읽는 곳은 아홉인데 전부 거른다",
               "네 곳(CSS 머리 주석 · drawer.js)을 놓쳤다",
               "함께 남아 있던 곳이 여덟 곳이다",
               "켜는 자리가 셋인데 여기만 없다",
               "12px 자리 53곳을 세어 갈랐다",
               "같은 기능이 세 군데 있다"):
        assert _심는다(tmp_path, 글), f"이 모양을 못 본다: {글}"


def test17_c02_세지_않는_말은_통과한다(tmp_path):
    """뚫리는 쪽. 이것이 걸리면 정작 지켜야 할 규칙을 못 적는다.

    **둘은 이 저장소의 원칙 문장이다** — 「같은 것이 두 곳에 있으면
    갈린다」. 자릿수(`8자리`)와 이름 붙은 묶음(`세 벌`)도 자리가 아니다.
    """
    for 글 in ("읽는 곳은 여럿이고 `archived_at` 으로 찾으면 나온다",
               "같은 것이 두 곳에 있으면 반드시 갈린다",
               "패널을 한 벌 더 만들 수는 없다",
               "키의 지문 8자리. 키 자체는 드러내지 않는다",
               "막는 검사의 세 벌(막힘·통과·실제로 봄)",
               "그 자리는 4-15 홈이 맡는다",
               "행 모양을 두 벌로 두면 반드시 갈린다"):
        assert not _심는다(tmp_path, 글), f"세지 않는 말이 걸린다: {글}"


def test17_c03_날짜가_있으면_그때_잰_값이다(tmp_path):
    """이력을 적을 수 있어야 한다 — 「2026-09-03 에 세어 봤더니 107곳」 은
    지금에 대한 주장이 아니다. 날짜가 없으면 같은 문장도 걸린다."""
    assert not _심는다(tmp_path, "2026-09-03 에 세어 봤더니 흐림이 107곳이었다")
    assert not _심는다(tmp_path, "2026-09-03 에 세어 봤더니\n흐림이 107곳이었다")
    assert _심는다(tmp_path, "흐림이 107곳이다")


def test17_c04_주석과_문서만_본다(tmp_path):
    """코드 줄의 수는 값이지 주장이 아니다 (`limit=3`).
    잡을 것은 **사람이 사람에게 적은 말**이다."""
    cc = _load("check_counts")
    p = tmp_path / "심은것.py"
    p.write_text('LIMIT = 3\n'
                 '세곳 = ["가", "나", "다"]\n'
                 'def f():\n'
                 '    """이것을 부르는 곳은 세 곳이다."""\n'
                 '    return 세곳[:3]\n', encoding="utf-8")
    옛ROOT, cc.ROOT = cc.ROOT, tmp_path
    try:
        걸림 = cc.찾는다([p])
    finally:
        cc.ROOT = 옛ROOT
    assert len(걸림) == 1 and 걸림[0][1] == 4, 걸림


def test17_c05_이유_없이_넘기면_실패한다(tmp_path, monkeypatch):
    """넘김 규칙(지난 판)이 그대로 걸린다 — 이유 없는 넘김은 넘김이 아니다."""
    cc = _load("check_counts")
    목록 = tmp_path / "세어둠.txt"
    목록.write_text("docs/어딘가.md\n", encoding="utf-8")
    monkeypatch.setattr(cc, "넘김목록", 목록)
    try:
        cc.볼파일()
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError("이유 없는 줄을 그냥 넘겼다")


def test17_c06_지금_저장소에는_0곳이다():
    """소스를 읽지 않고 **실제로 돌린다.** 0곳인 것은 이 판이 전부
    처리했기 때문이고, c01 이 그 눈이 살아 있음을 따로 잰다."""
    r = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"),
                        str(SCRIPTS / "check_counts.py")],
                       cwd=ROOT, capture_output=True)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-1500:]


def test17_c07_볼_파일이_0이면_실패한다(monkeypatch):
    """센 것이 0이면 성공이 아니라 실패다 (11-3)."""
    cc = _load("check_counts")
    monkeypatch.setattr(cc, "볼파일", lambda: [])
    monkeypatch.setattr("sys.argv", ["check_counts.py"])
    assert cc.main() == 2


def test17_c08_10장이_왜_검사로_옮겼는지_말한다():
    """규칙만 적어 두면 새어 들어간다 — 다섯 판이 그 증거다."""
    글 = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    자리 = 글[글.index("**자리를 세어 두지 않습니다.**"):][:1200]
    assert "다섯 판" in 자리
    assert "check_counts" in 자리


# ════════════════════════════════════════════════════════════════════
# 2. 이름이 경계다 — 글검사.py
# ════════════════════════════════════════════════════════════════════


def test17_n01_이름이_글검사다():
    """문구는 사람이 안 읽고 이름은 부를 때마다 읽는다. 「전부
    통과했습니다」 가 「글이 통과했습니다」 로 읽혀야 한다."""
    assert (SCRIPTS / "글검사.py").exists()
    assert not (SCRIPTS / "검사.py").exists(), "옛 이름이 남아 있다"


def test17_n02_옛_이름이_옛말_목록에_있다():
    """이름을 바꾸면 그 이름을 가리키던 글이 낡는다 — 목록에 적어야
    `check_stale` 이 잡는다 (11-3)."""
    글 = (ROOT / "docs" / "옛말.md").read_text(encoding="utf-8")
    자리 = 글[글.index("## 글 검사는 한 자리에서"):][:900]
    assert "scripts/검사.py" in 자리


def test17_n03_새_검사가_그_한_줄로_들어갔다():
    """「검사가 하나 늘어도 11-3 은 그대로다」 는 주장을 이 판이 실제로
    밟았다 — `check_counts` 가 `검사들` 한 줄로 들어갔다."""
    검사 = _load("글검사")
    assert "check_counts" in 검사.검사들


# ════════════════════════════════════════════════════════════════════
# 3. 점검을 두 계정으로
# ════════════════════════════════════════════════════════════════════


def test17_a01_건너뛴_것이_있으면_어느_계정인지_말한다():
    """한 계정으로만 돌면 못 바꾸는 쪽이 안 재지는데 점수는 만점이다 —
    지난 판이 그것으로 92/92 를 받았다.

    **낱말만 잰다** — 실제로 그 줄이 뜨는지는 브라우저에서 돌려 봤고
    결과는 `docs/review/최근.md` 에 있다."""
    글 = (ROOT / "docs" / "checks" / "drawer.js").read_text(encoding="utf-8")
    자리 = 글[글.index("const 건너뜀"):][:900]
    assert "부서 리더" in 자리 and "관리자" in 자리, "어느 계정인지 말하지 않는다"
    assert "한 계정으로는" in 자리, "왜 다시 돌아야 하는지 말하지 않는다"


def test17_a02_11_3_이_두_계정을_말한다():
    """스크립트만 알고 있으면 다음 사람은 한 계정으로 돌린다."""
    글 = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    자리 = 글[글.index("### 2. 재시작하고"):]
    자리 = 자리[:자리.index("### 3.")]
    assert "두 계정" in 자리 and "부서 리더" in 자리


def test17_a03_글검사_출력에_넘김_수가_있다():
    """새 검사도 같은 규칙을 지킨다 — 넘김이 자라는 것이 보여야 한다."""
    환경 = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"),
                        str(SCRIPTS / "check_counts.py")],
                       cwd=ROOT, capture_output=True, env=환경)
    assert "이유와 함께 넘겨 두었습니다" in r.stdout.decode("utf-8", "replace")
