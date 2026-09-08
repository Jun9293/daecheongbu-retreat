# -*- coding: utf-8 -*-
"""바꾼 말의 **낡은 표기**가 저장소에 남아 있는지 찾는다 (11-3 3단계).

## 왜 도구인가

11-3 은 「이번에 바꾼 동작의 옛 표현을 그대로 찾아본다」 고만 정해 두었고,
**어떤 낱말로 찾을지는 사람이 그때 골랐다.** 그 자리가 새는 곳이었다 —
2026-09-08 에 「업무 이름을 누르면」 하나로 찾아 **네 곳**(CSS 머리 주석 ·
drawer.js · 점검 스크립트 · 시험 이름)을 놓쳤고 보고에는 「0곳」 이
적혔다. **검사를 했다는 기록이 있는데 검사가 못 본 것이라 안 한 것보다
나쁘다.**

그래서 낱말을 사람이 고르지 않는다. 낡은 말마다 표기를 **여럿** 적어 둔
`docs/옛말.md` 를 읽어 그 전부를 찾는다.

## 무엇을 보는가

`git ls-files` 로 추적 중인 글 파일 전부. 넘기는 자리는
`docs/옛말-넘김.txt` 에 **왜 넘기는지와 함께** 적는다 — 그 말을
설명하려고 스스로 담는 자리(이 파일 · 옛말.md · 그 시험)가 그것이다.
10장의 「어떤 것을 금지하는 도구는 그것을 설명하려고 스스로 담게 된다」.

## 아무것도 안 보는 것은 통과가 아니다

`옛말.md` 에서 읽은 표기가 0개면 **실패한다**(11-3 — 센 것이 0이면
성공이 아니라 실패다). check_names 가 「29개 중 0개를 보며 초록」 을
냈던 그 모양을 여기서 되풀이하지 않는다.

    .venv\\Scripts\\python.exe scripts/check_stale.py
    .venv\\Scripts\\python.exe scripts/check_stale.py --목록   # 무엇을 찾는지만
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
옛말목록 = ROOT / "docs" / "옛말.md"
넘김목록 = ROOT / "docs" / "옛말-넘김.txt"

글파일 = {".py", ".md", ".txt", ".html", ".js", ".css", ".json", ".bat",
        ".yml", ".yaml", ".ini", ".cfg", ".toml"}


def 읽는다() -> list[tuple[str, str]]:
    """(지금 말, 낡은 표기) 쌍 전부.

    표기는 백틱 안에 적고 `·` 로 잇는다 — 한 줄에 여럿이다.
    """
    if not 옛말목록.exists():
        raise SystemExit(f"옛말 목록이 없습니다: {옛말목록}")
    쌍 = []
    지금말 = ""
    표기줄 = False        # 지금 「낡은 표기」 를 읽는 중인가
    항목시작 = False      # `---` 아래가 진짜 항목이다
    for 줄 in 옛말목록.read_text(encoding="utf-8").splitlines():
        # **머리말의 안내는 항목이 아니다.** 「적는 법」 의 예시
        # (`표기1` · `표기2`)를 진짜 표기로 읽으면, **막는 쪽 시험이
        # 자리표시자로 통과하고** 보고에 적는 수도 그만큼 부풀려진다
        # (검토가 잡았다 — 10장의 「도구는 자기가 금지하는 것을
        # 설명하려고 담게 된다」 가 파일 안 구획에서 다시 나온 자리).
        if 줄.strip() == "---":
            항목시작 = True
            continue
        if not 항목시작:
            continue
        if 줄.startswith("## "):
            지금말, 표기줄 = 줄[3:].strip(), False
            continue
        if not 지금말:
            continue
        if "낡은 표기:" in 줄:
            표기줄 = True
        elif 표기줄 and not 줄.startswith("  "):
            # **이어지는 줄도 읽는다.** 표기를 넉넉히 적으라고 해 놓고
            # 한 줄만 읽으면, 줄을 바꾼 표기가 조용히 빠진다 — 검사가
            # 못 보는 자리를 검사 자신이 만드는 셈이다(실제로 그랬다)
            표기줄 = False
        if not 표기줄:
            continue
        for 표기 in re.findall(r"`([^`]+)`", 줄):
            표기 = 표기.strip()
            if 표기:
                쌍.append((지금말, 표기))
    return 쌍


def 넘긴것() -> set[str]:
    """그 말을 **설명하려고** 담는 자리 — 파일 단위로 넘긴다."""
    if not 넘김목록.exists():
        return set()
    나온것 = set()
    for 줄 in 넘김목록.read_text(encoding="utf-8").splitlines():
        줄 = 줄.strip()
        if not 줄 or 줄.startswith("#"):
            continue
        칸 = [x.strip() for x in 줄.split("|")]
        if len(칸) >= 2 and 칸[0] and 칸[1]:
            나온것.add(칸[0])
    return 나온것


def 볼파일() -> list[pathlib.Path]:
    출 = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        cwd=ROOT, capture_output=True,
    ).stdout.decode("utf-8")
    넘김 = 넘긴것()
    나온것 = []
    for 이름 in (x.strip() for x in 출.split("\n")):
        if not 이름 or 이름 in 넘김:
            continue
        p = ROOT / 이름
        if p.suffix.lower() in 글파일 and p.exists():
            나온것.append(p)
    return 나온것


def 상대경로(p: pathlib.Path) -> str:
    """저장소 밖의 파일도 받는다 — 시험이 합성 파일을 넘긴다
    (check_names 의 같은 함수와 같은 이유)."""
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def 찾는다(쌍: list[tuple[str, str]], 파일들: list[pathlib.Path]) -> list[tuple]:
    """(파일, 줄번호, 지금 말, 낡은 표기, 줄) — 걸린 것 전부."""
    나온것 = []
    for p in 파일들:
        try:
            글 = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        상대 = 상대경로(p)
        for 번호, 줄 in enumerate(글.split("\n"), 1):
            for 지금말, 표기 in 쌍:
                if 표기 in 줄:
                    나온것.append((상대, 번호, 지금말, 표기, 줄.strip()))
    return 나온것


def main() -> int:
    ap = argparse.ArgumentParser(
        description="바꾼 말의 낡은 표기가 남아 있는지 찾는다")
    ap.add_argument("--목록", action="store_true", help="무엇을 찾는지만 보여준다")
    args = ap.parse_args()

    쌍 = 읽는다()
    # **아무것도 안 보는 것은 통과가 아니다** (11-3)
    if not 쌍:
        print("!! 옛말 목록에서 읽은 표기가 0개입니다.")
        print(f"   검사가 아무것도 안 보고 있습니다 — {옛말목록.name} 의 모양을 확인해 주세요.")
        return 2

    if args.목록:
        지금까지 = ""
        for 지금말, 표기 in 쌍:
            if 지금말 != 지금까지:
                print(f"\n{지금말}")
                지금까지 = 지금말
            print(f"    {표기}")
        print(f"\n낡은 말 {len({a for a, _ in 쌍})}가지 · 표기 {len(쌍)}개")
        return 0

    파일들 = 볼파일()
    걸린것 = 찾는다(쌍, 파일들)
    print(f"낡은 표기 {len(쌍)}개로 파일 {len(파일들)}개를 봤습니다.")
    if not 걸린것:
        print("옛말이 없습니다.")
        return 0

    print()
    print(f"!! {len(걸린것)}곳에 낡은 표기가 남아 있습니다.")
    print("   지금 말로 고치거나, 그 말을 설명하는 자리면")
    print(f"   docs/{넘김목록.name} 에 `파일 | 왜 넘기는가` 로 적으세요.")
    print()
    앞선파일 = None
    for 상대, 번호, 지금말, 표기, 줄 in 걸린것:
        if 상대 != 앞선파일:
            print(f"  {상대}")
            앞선파일 = 상대
        print(f"    {번호:>5}줄  「{표기}」 → {지금말}")
        print(f"           {줄[:78]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
