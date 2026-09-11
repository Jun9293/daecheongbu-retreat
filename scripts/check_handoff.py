# -*- coding: utf-8 -*-
"""검토용 보고 맨 위에 **사람칸**이 있는지 본다 (11-3 · 2026-09-11 도막 5).

## 왜 검사인가

사람이 움직여야 하는 것 — 노트북에서 직접 돌릴 명령, 관리자 권한이 필요한 것,
사람이 정해야 할 것, 막혀서 못 한 것 — 이 보고 곳곳에 흩어져 있으면 **사람이
그것을 찾아 읽어야** 합니다. 한 칸에 모으면 그 자리만 보면 됩니다.

그런데 **모으기로 정하는 것만으로는 안 됩니다.** 이 저장소가 여러 번 겪은
모양입니다 — 규칙을 글로만 적어 두면 새어 나갑니다(4-0 의 흐림 자리, 10장의
자리 세기). 그래서 검사로 둡니다.

## 무엇을 보나

`docs/review/최근.md` 의 **맨 위**에 다섯 줄이 **그 순서로** 있는가, 그리고
**네 줄의 값이 비어 있지 않은가**.

- 「없음」 은 **값입니다.** 빈 칸은 값이 아닙니다 — 빈 칸은 「그 일이 없다」 와
  「묻지 않았다」 를 구별해 주지 않습니다
- 이유는 보지 않습니다. 이 칸은 **어디에 적혀 있는지만 가리키는 자리**이고
  이유는 본문에 있습니다 — 같은 말이 두 곳에 있으면 갈립니다

**모양만 봅니다.** 내용이 맞는지는 사람과 검토자가 봅니다(검토-원칙 9).

    .venv\\Scripts\\python.exe scripts/check_handoff.py
"""

from __future__ import annotations

import pathlib
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
보고 = ROOT / "docs" / "review" / "최근.md"

# **머리 한 줄 + 값이 붙는 네 줄.** 순서가 뜻을 가진다 — 먼저 할 것이 위다.
# 이 글자가 정본이고 11-3 과 덩어리가 그대로 받아 씁니다
머리 = "사람이 할 것"
칸들 = ("노트북에서 직접:", "관리자 권한:", "정할 것:", "막혀서 못 한 것:")


def 읽는다(글: str) -> list[str]:
    """맨 위의 빈 줄만 건너뛴다 — 그 아래 첫 다섯 줄이 사람칸이어야 한다."""
    줄들 = 글.splitlines()
    while 줄들 and not 줄들[0].strip():
        줄들.pop(0)
    return [줄.strip() for 줄 in 줄들[:len(칸들) + 1]]


def 본다(글: str) -> list[str]:
    """탈이 있으면 그 말들을 돌려준다 — **빈 목록이 통과다.**

    부르는 곳이 둘이다(이 파일의 `main` 과 시험) — 파일을 만들지 않고 글로
    재려고 갈라 두었다. 두 곳에서 따로 판정하면 시험이 검사와 다른 것을 본다.
    """
    앞 = 읽는다(글)
    if not 앞 or 앞[0] != 머리:
        return [f"맨 위에 「{머리}」 줄이 없습니다 — 지금 첫 줄: {(앞[0] if 앞 else '')!r}"]
    탈 = []
    for i, 이름 in enumerate(칸들, start=1):
        줄 = 앞[i] if i < len(앞) else ""
        if not 줄.startswith(이름):
            탈.append(f"{i}번째 칸이 「{이름}」 이 아닙니다 — 지금: {줄!r}")
            continue
        값 = 줄[len(이름):].strip()
        if not 값:
            탈.append(f"「{이름}」 의 값이 비어 있습니다 — 없으면 「없음」 이라고 적습니다")
    return 탈


def main() -> int:
    if not 보고.exists():
        print(f"!! {보고.relative_to(ROOT)} 가 없습니다 — 11-3 이 매번 덮어쓰라고 한 파일입니다.")
        return 1
    탈 = 본다(보고.read_text(encoding="utf-8"))
    # **맞힌 줄 수로 말한다.** 전에는 보기도 전에 「찾았습니다」 를 찍어서,
    # 바로 아래 어긋난 수를 세는 줄과 서로를 부정했다 (검토 g)
    맞은수 = len(칸들) + 1 - len(탈)
    print(f"{보고.relative_to(ROOT).as_posix()} 맨 위에서 사람칸 "
          f"{len(칸들) + 1}줄 중 {맞은수}줄이 제자리입니다.")
    if 탈:
        print(f"!! {len(탈)}곳이 어긋납니다.")
        for 말 in 탈:
            print(f"  {말}")
        print("   모양은 CLAUDE.md 11-3 에 있습니다. 네 이름은 늘 그 자리 그 순서입니다.")
        return 1
    print("사람칸이 제자리에 있고 네 칸이 다 채워져 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
