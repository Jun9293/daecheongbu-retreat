# -*- coding: utf-8 -*-
"""기준 문서를 읽는 한 자리 — CLAUDE.md 와 `docs/CLAUDE-부록/` (2026-10-07).

CLAUDE.md 가 한도를 넘어 몇 장의 본문을 부록으로 옮겼다. 그 뒤로
「기준 문서에 이 말이 **없어야** 한다」 를 CLAUDE.md 하나로만 재면
**옮긴 장은 안 본 채로 초록**이다 — 막는 시험이 볼 것을 안 보는 자리다(11-3).

**「없어야 한다」 는 `전체()` 로 잰다. 「있어야 한다」 는 그 말이 있어야 할
문서 하나를 읽는다** — 합친 글에서 찾으면 어디에 있어도 통과해 단언이 약해진다.

읽는 곳을 여기 하나로 둔다. 시험마다 폴더를 저마다 훑으면 한쪽만 고쳐진다.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
본문 = ROOT / "CLAUDE.md"
부록폴더 = ROOT / "docs" / "CLAUDE-부록"


def 부록들() -> list[pathlib.Path]:
    return sorted(부록폴더.glob("*.md"))


def 문서들() -> list[pathlib.Path]:
    """CLAUDE.md 와 부록 전부. **이름을 세어 두지 않는다** (10장)."""
    return [본문] + 부록들()


def 전체() -> str:
    """기준 문서 전부를 이은 글 — 「없어야 한다」 를 잴 때 쓴다."""
    return "\n".join(p.read_text(encoding="utf-8") for p in 문서들())
