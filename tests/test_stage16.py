"""보이는 탭으로 다시 재기 (+ 넘김에 이유 · 안 뜨는 UI).

지난 판이 세 화면 점검을 못 돌리고 △ 로 남겼다. 이번 판이 그것부터
닫았고, 그 과정에서 배운 것을 도구로 남긴다 — 넘김에 이유를 강제하고,
검사 셋을 한 자리에서 부른다.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ════════════════════════════════════════════════════════════════════
# 1. 넘김에 이유 — 없으면 넘김이 아니다
# ════════════════════════════════════════════════════════════════════


def test16_s01_이유_없는_줄을_심으면_걸린다(tmp_path):
    """막는 쪽. 셋 다 이유 칸이 빈 줄을 **조용히 버리고** 있었다 —
    적은 사람은 넘긴 줄 알고 검사는 안 넘긴 채로 돈다."""
    넘김 = _load("넘김")
    목록 = tmp_path / "넘김.txt"
    목록.write_text(
        "# 머리말\n"
        "있는것.py | 왜 넘기는지 적었다\n"
        "이유없는것.py\n"
        "빈이유.py | \n"
        "이어적기.py | 〃\n",
        encoding="utf-8")
    넘길것, 이유없음 = 넘김.읽는다(목록)
    assert 넘길것 == {"있는것.py", "이어적기.py"}
    assert [t for _n, t in 이유없음] == ["이유없는것.py", "빈이유.py |"]


def test16_s02_이유가_다_있으면_안_걸린다(tmp_path):
    """뚫리는 쪽. 지금 목록이 걸리면 아무도 안 쓴다."""
    넘김 = _load("넘김")
    for 이름 in ("옛말-넘김.txt", "이름-넘김.txt", "이름-확인됨.txt"):
        _넘길것, 이유없음 = 넘김.읽는다(ROOT / "docs" / 이름)
        assert 이유없음 == [], f"{이름} 에 이유 없는 줄: {이유없음}"


def test16_s03_읽는_곳이_하나다():
    """③ 검사가 볼 것을 보고 있나 — 세 검사가 **같은 함수**를 부른다.
    저마다 읽으면 한쪽만 고쳐지고, 실제로 셋이 같은 결함을 갖고 있었다.

    **낱말만 잰다** — 실제로 같은 결과를 내는지는 s01·s02 가 잰다."""
    for 이름 in ("check_stale", "check_named", "check_names"):
        글 = (SCRIPTS / f"{이름}.py").read_text(encoding="utf-8")
        코드 = re.sub(r'"""[\s\S]*?"""', "", 글)
        코드 = re.sub(r"#[^\n]*", "", 코드)
        assert "넘김.읽는다(" in 코드, f"{이름} 이 제 손으로 읽는다"


def test16_s04_넘김_수가_출력에_찍힌다():
    """줄어들 일이 없는 목록은 크기가 안 보이면 아무도 안 읽게 되고,
    그러면 「거기 적으면 통과」 가 된다 (4-11 의 그 자리)."""
    import os

    # **콘솔 인코딩을 못 박는다.** 윈도우 콘솔은 cp949 라 그대로 받으면
    # 글자가 깨져, 있는 말을 없다고 말한다 (있는 것을 없다고 하는 그 모양)
    환경 = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for 이름 in ("check_stale", "check_named", "check_names"):
        r = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"),
                            str(SCRIPTS / f"{이름}.py")],
                           cwd=ROOT, capture_output=True, env=환경)
        출력 = r.stdout.decode("utf-8", "replace")
        assert "이유와 함께 넘겨 두었습니다" in 출력, f"{이름} 이 넘김 수를 안 찍는다"


# ════════════════════════════════════════════════════════════════════
# 2. 검사 셋을 한 자리에서
# ════════════════════════════════════════════════════════════════════


def test16_g01_한_자리가_셋을_다_부른다():
    """11-3 이 셋을 이름으로 적어 두면 넷째가 생길 때 그 검사만 조용히
    안 돈다. 더할 곳은 `검사들` 한 줄이다."""
    검사 = _load("검사")
    assert set(검사.검사들) == {"check_names", "check_stale", "check_named"}
    for 이름 in 검사.검사들:
        assert (SCRIPTS / f"{이름}.py").exists(), f"{이름} 이 없다"


def test16_g02_하나라도_빨가면_전체가_빨갛다(monkeypatch, capsys):
    """막는 쪽. 모아서 내는 값이 「마지막 것」 이면 앞의 실패가 묻힌다."""
    검사 = _load("검사")
    monkeypatch.setattr(검사, "검사들", ("가", "나", "다"))
    monkeypatch.setattr(검사, "돌린다", lambda 이름: 1 if 이름 == "나" else 0)
    assert 검사.main() == 1
    나온말 = capsys.readouterr().out
    assert "1개가 빨갛습니다" in 나온말 and "나" in 나온말


def test16_g03_끝까지_돈다(monkeypatch):
    """첫 실패에서 멈추면 한 번에 하나씩만 알게 되어 고치고 다시 돌리기를
    되풀이한다."""
    검사 = _load("검사")
    돈것 = []
    monkeypatch.setattr(검사, "검사들", ("가", "나", "다"))
    monkeypatch.setattr(검사, "돌린다", lambda 이름: (돈것.append(이름), 1)[1])
    assert 검사.main() == 1
    assert 돈것 == ["가", "나", "다"], "첫 실패에서 멈췄다"


def test16_g04_전부_통과하면_0이다(monkeypatch):
    """뚫리는 쪽."""
    검사 = _load("검사")
    monkeypatch.setattr(검사, "검사들", ("가", "나"))
    monkeypatch.setattr(검사, "돌린다", lambda 이름: 0)
    assert 검사.main() == 0


def test16_g05_11_3_이_그_한_자리를_부른다():
    """문서가 셋을 이름으로 세어 두면 넷째가 생길 때 갈린다 (10장)."""
    글 = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    자리 = 글[글.index("### 1. 커밋하고 푸시한다"):][:2000]
    assert "scripts/검사.py" in 자리


# ════════════════════════════════════════════════════════════════════
# 3. 안 뜨는 UI — 아는 채로 두는 것과 모르는 것은 다르다
# ════════════════════════════════════════════════════════════════════


def test16_u01_되살리기가_안_뜨는_이유가_적혀_있다():
    """지금 코드로는 `made_excluded` 가 늘 거짓이다. 적어 두지 않으면
    다음 사람이 「왜 안 뜨지」 로 시간을 쓴다.

    **낱말만 잰다** — 뜨고 안 뜨는 것은 시험 r01~r03 이 상태를 직접
    만들어 잰다."""
    for f in ("app/routers/meetings.py", "app/static/js/meeting.js"):
        글 = (ROOT / f).read_text(encoding="utf-8")
        자리 = 글[글.index("made_excluded") - 900: 글.index("made_excluded") + 900]
        assert "빼는 길이 아직 없다" in 자리 or "빼는 길이" in 자리, f"{f} 에 이유가 없다"
    문서 = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "그 단추는 지금 코드로는 안 뜹니다" in 문서


def test16_u02_빼기를_만들_때_볼_것이_12장에_있다():
    """봐둘것이 아니라 **만들 때 읽는 자리**에 둔다 — 되살리기는
    `relink_prerequisites` 를 안 부른다."""
    문서 = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    자리 = 문서[문서.index("「이번 회차에서 빼기」 를 만들 때 함께 볼 것"):][:700]
    assert "relink_prerequisites" in 자리
    assert "조용히 진행" in 자리


def test16_u03_채우는_길이_없는_칸에_그렇다고_적혀_있다():
    """`Retreat.is_archived` 와 `TaskLibrary.archived_at` 은 읽는 곳만
    있고 쓰는 곳이 없다. 그것을 모르면 「보관된 회차」 가 동작한다고 믿는다."""
    글 = (ROOT / "app" / "models.py").read_text(encoding="utf-8")
    for 칸, 말 in (("is_archived: Mapped[bool]", "참으로 만드는 길이 아직 없다"),
                  ("archived_at: Mapped[dt.datetime | None]", "채우는 길이 아직 없다")):
        at = 글.index(칸)
        assert 말 in 글[at - 700:at], f"{칸} 에 이유가 없다"

    # 그리고 실제로 쓰는 곳이 없다 — 생기면 이 시험이 빨개져 주석을 고치게 된다
    코드 = "\n".join(
        p.read_text(encoding="utf-8")
        for p in list((ROOT / "app").rglob("*.py")) + list((ROOT / "scripts").glob("*.py"))
        if "models.py" not in p.name)
    assert not re.search(r"\.is_archived\s*=\s*True", 코드)
    assert not re.search(r"\.archived_at\s*=\s*(?!None)", 코드)


# ════════════════════════════════════════════════════════════════════
# 4. 점검 스크립트 — 대체가 틀리면 검사가 흔들린다
# ════════════════════════════════════════════════════════════════════


def test16_c01_타이머를_대체하지_말라고_적혀_있다():
    """2026-09-08 에 `setTimeout` 을 마이크로태스크로 바꿔 돌렸다가
    콜백을 덮어써 점검이 멈추고 엉뚱한 곳에서 ✗ 를 냈다 — 화면이 아니라
    검사가 흔들린 것이다. 그 ✗ 둘은 보이는 창에서 그대로 통과했다."""
    글 = (ROOT / "docs" / "checks" / "drawer.js").read_text(encoding="utf-8")
    머리 = 글[: 글.index("(async () => {")]
    assert "타이머를 대체하지 마세요" in 머리
    assert "탭을 보이게" in 머리
