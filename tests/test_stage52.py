"""문서가 되돌리는 자리로 가리키는 사본은 지키는판에 있다 (CLAUDE.md 11-2 백업 절 · 2026-09-15 사람이 정함).

문서(CLAUDE.md · `docs/` 아래 글 — 얼린 보고가 있는 `docs/review/` 는 뺀다)에 나오는 백업 사본 이름마다
`scripts/backup.py` 의 `지키는판` 에 있거나 `docs/사본-넘김.txt` 에 이유와 함께 넘겨져 있어야 한다.
되돌리는 자리인지 기록인지는 기계가 못 가르므로 넘김의 이유 칸이 사람이 한 번 보는 자리다.
운영 백업 폴더는 안 본다 — 파일이 있는지가 아니라 **지울 수 있는지**를 본다.
"""

from __future__ import annotations

import pathlib
import re

from scripts import backup, 넘김

ROOT = pathlib.Path(__file__).resolve().parent.parent
사본꼴 = re.compile(r"app-(\d{8}-\d{6})\.db")


def 볼글() -> dict[pathlib.Path, str]:
    파일 = [ROOT / "CLAUDE.md"] + [p for p in sorted((ROOT / "docs").rglob("*.md"))
                                   if "review" not in p.relative_to(ROOT / "docs").parts]
    return {p: p.read_text(encoding="utf-8") for p in 파일}


def 빠진사본(글들: dict, 지키는: set[str], 넘길: set[str]) -> dict[str, list[str]]:
    """사본 이름 → 그 이름이 나온 파일들. 지키는판에도 넘김에도 없는 것만."""
    빠진: dict[str, list[str]] = {}
    for p, 글 in 글들.items():
        for m in 사본꼴.finditer(글):
            if m.group(1) not in 지키는 and m.group(0) not in 넘길:
                빠진.setdefault(m.group(0), [])
                if p.name not in 빠진[m.group(0)]:
                    빠진[m.group(0)].append(p.name)
    return 빠진


def _넘김():
    넘길, 안되는줄 = 넘김.읽는다(ROOT / "docs" / "사본-넘김.txt")
    assert not 안되는줄, f"사본-넘김.txt 에 이유가 없거나 이름을 되풀이한 줄: {안되는줄}"
    return 넘길


def test52_a01_문서가_가리키는_사본은_전부_지키는판이나_넘김에():
    글들 = 볼글()
    본수 = sum(len(사본꼴.findall(글)) for 글 in 글들.values())
    assert 본수 > 0, "문서에서 사본 이름을 하나도 못 찾았다 — 아무것도 안 보는 검사다"
    빠진 = 빠진사본(글들, set(backup.지키는판), _넘김())
    assert not 빠진, ("문서가 이름을 적었는데 지키는판에도 docs/사본-넘김.txt 에도 없는 사본 — "
                      f"되돌리는 자리면 지키는판에, 기록이면 넘김에 이유와 함께(CLAUDE.md 11-2): {빠진}")


def test52_a02_2026_09_15_의_두_사고를_심으면_잡는다():
    """들여오기 직전 사본과 짝잇기 직전 사본을 지키는판에서 빼면 둘 다 걸린다."""
    지키는 = set(backup.지키는판) - {"20260915-002352", "20260915-144929"}
    빠진 = 빠진사본(볼글(), 지키는, _넘김())
    assert set(빠진) == {"app-20260915-002352.db", "app-20260915-144929.db"}


def test52_a03_넘김에만_적어도_통과하고_얼린_보고는_안_본다():
    지키는 = set(backup.지키는판) - {"20260915-002352", "20260915-144929"}
    넘길 = _넘김() | {"app-20260915-002352.db", "app-20260915-144929.db"}
    assert 빠진사본(볼글(), 지키는, 넘길) == {}, "넘김에 적은 이름이 걸렸다"
    assert all("review" not in p.parts for p in 볼글()), "얼린 보고까지 보고 있다"


def test52_a04_넘김에_이유가_없으면_넘기지_않는다(tmp_path):
    목록 = tmp_path / "사본-넘김.txt"
    목록.write_text("app-20990101-000000.db |\n", encoding="utf-8")
    넘길, 안되는줄 = 넘김.읽는다(목록)
    assert "app-20990101-000000.db" not in 넘길 and 안되는줄
