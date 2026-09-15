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


def 볼글(root: pathlib.Path = ROOT) -> dict[pathlib.Path, str]:
    파일 = [root / "CLAUDE.md"] + [p for p in sorted((root / "docs").rglob("*.md"))
                                   if "review" not in p.relative_to(root / "docs").parts]
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


_지어낸글 = {
    pathlib.Path("가.md"): "되돌리는 자리는 `app-20990101-000001.db` 다",
    pathlib.Path("나.md"): "직전 사본 app-20990101-000002.db 로 돌았다 · 사본 app-20990101-000001.db",
}


def test52_a02_지키는판에서_빼면_잡는다():
    """2026-09-15 의 두 사고 모양 — 문서가 이름을 적었는데 지키는판에 없다. 실제 문서와 떨어져 잰다."""
    빠진 = 빠진사본(_지어낸글, {"20990101-000001"}, set())
    assert 빠진 == {"app-20990101-000002.db": ["나.md"]}
    assert set(빠진사본(_지어낸글, set(), set())) == {"app-20990101-000001.db", "app-20990101-000002.db"}


def test52_a03_지키는판이나_넘김에_있으면_통과하고_얼린_보고는_안_본다(tmp_path):
    assert 빠진사본(_지어낸글, {"20990101-000001"}, {"app-20990101-000002.db"}) == {}
    (tmp_path / "docs" / "review").mkdir(parents=True)
    (tmp_path / "CLAUDE.md").write_text("없음", encoding="utf-8")
    (tmp_path / "docs" / "review" / "얼린판.md").write_text("app-20990101-000003.db", encoding="utf-8")
    (tmp_path / "docs" / "인계.md").write_text("app-20990101-000004.db", encoding="utf-8")
    assert set(빠진사본(볼글(tmp_path), set(), set())) == {"app-20990101-000004.db"}, "얼린 보고를 보거나 살아 있는 글을 놓쳤다"


def test52_a04_넘김에_이유가_없으면_넘기지_않는다(tmp_path):
    목록 = tmp_path / "사본-넘김.txt"
    목록.write_text("app-20990101-000000.db |\n", encoding="utf-8")
    넘길, 안되는줄 = 넘김.읽는다(목록)
    assert "app-20990101-000000.db" not in 넘길 and 안되는줄
