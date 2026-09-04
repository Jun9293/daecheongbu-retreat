# -*- coding: utf-8 -*-
"""커밋될 파일에 **실명이 들어 있는지** 찾는다 (11-2 「저장소와 실명」).

## 바꾸는 것과 찾는 것은 다른 일이다

`anonymize.py` 는 **바꾼다.** 그래서 경계를 엄격하게 본다 — 앞뒤가
한글·영문·숫자면 건너뛴다. 그러지 않으면 `필요한`·`중요한`·`진행` 같은
낱말이 함께 깨진다. 실제로 겪은 일이라 그 규칙이 생겼다.

**이 스크립트는 바꾸지 않는다. 찾기만 한다.** 그래서 경계를 보지 않는다.
성이 붙은 `최○○` 도 걸리고 `중요한` 같은 오탐도 걸린다 —

    오탐은 사람이 한 번 보고 넘기면 되지만,
    못 찾은 실명은 공개 저장소로 나간다.

2026-09-04 에 성이 붙은 이름이 정확히 그 틈으로 나갔다. 이름은
대응표에 있는데 앞에 성이 붙어 `anonymize.py` 가 건너뛰었고, 커밋 전
검사는 대응표 구조를 잘못 읽어 **29개 중 0개를 보고 있었다.**

**이 파일에도 실명을 적지 않는다.** 처음에 예로 실명을 적었다가 이
검사에 스스로 걸렸다 — 막으려던 것을 검사 자신이 하고 있었다.

## 아무것도 안 보는 것은 통과가 아니다

대응표에서 읽은 실명이 0개면 **실패한다.** 검사가 조용히 아무것도 안 보고
초록을 내는 것이 이 사고의 절반이었다.

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/check_names.py            # 커밋될 것
    .venv\\Scripts\\python.exe scripts/check_names.py docs        # 경로를 줘서
    .venv\\Scripts\\python.exe scripts/check_names.py --all       # 추적 중인 전부

넘겨도 되는 것은 `docs/이름-확인됨.txt` 에 적는다 — **왜 넘기는지**를
함께 적는다. 4-0 의 `흐려도_되는곳` 과 같은 방식이다.
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# **대응표를 읽는 코드는 `anonymize.py` 와 같은 것을 쓴다.** 두 곳에서
# 읽으면 한쪽만 구조를 잘못 읽는다 — 이번에 정확히 그랬다.
_스펙 = importlib.util.spec_from_file_location(
    "_anonymize_for_check", ROOT / "scripts" / "anonymize.py")
_anon = importlib.util.module_from_spec(_스펙)
_스펙.loader.exec_module(_anon)

넘긴목록 = ROOT / "docs" / "이름-확인됨.txt"

# 글자만 있는 파일을 본다. 이미지·zip 안의 실명은 이 검사의 몫이 아니다.
글파일 = {".py", ".md", ".txt", ".html", ".js", ".css", ".json", ".bat",
        ".yml", ".yaml", ".ini", ".cfg", ".toml"}


def 가린다(이름: str) -> str:
    """**실명을 화면에 그대로 찍지 않는다.** 검사 결과가 로그·CI·채팅으로
    돌아다니는데, 거기 실명이 찍히면 막으려던 것을 검사가 하고 있는 셈이다."""
    if len(이름) <= 1:
        return "◯"
    return 이름[0] + "◯" * (len(이름) - 1)


def 넘긴것() -> set[tuple[str, str]]:
    """(파일, 낱말) 짝. 이 짝은 걸려도 넘긴다."""
    if not 넘긴목록.exists():
        return set()
    나온것 = set()
    for 줄 in 넘긴목록.read_text(encoding="utf-8").splitlines():
        줄 = 줄.strip()
        if not 줄 or 줄.startswith("#"):
            continue
        칸 = [x.strip() for x in 줄.split("|")]
        if len(칸) >= 2:
            나온것.add((칸[0], 칸[1]))
    return 나온것


def 넘기나(넘김: set, 상대: str, 이름: str) -> bool:
    """`*` 는 **어느 파일에서든** 넘긴다.

    한두 글자 이름은 낱말 안에 늘 들어간다 — `진` 은 진행·사진·추진에,
    `요한` 은 필요한·중요한에. 파일마다 적으면 목록이 끝없이 길어지고,
    특히 `docs/review/최근.md` 는 매 작업마다 새로 써서 **매번 빨개진다.**
    그러면 사람이 이 검사를 무시하기 시작하고, 한 번 무시하면 돌아오지
    않는다 (4-11 과 같은 자리).

    **그 이름들은 이 검사가 못 지킨다.** `anonymize.py` 의 경계 규칙에
    맡긴다 — 그쪽은 낱말 안에 든 것을 건너뛰므로 홀로 선 `진` 만 바꾼다.
    넘긴 목록에 **왜 넘기는지**를 적어 그 사실이 보이게 한다.
    """
    return (상대, 이름) in 넘김 or ("*", 이름) in 넘김


def 볼파일(args) -> list[pathlib.Path]:
    """**커밋될 것만 본다.** gitignore 된 것은 저장소에 안 올라가므로 보지
    않는다 — `data/*.real.md` 가 실명을 담는 것은 규칙대로다."""
    if args.경로:
        나온것 = []
        for 경로 in args.경로:
            p = ROOT / 경로
            if p.is_dir():
                나온것 += [x for x in p.rglob("*") if x.is_file()]
            elif p.is_file():
                나온것.append(p)
        # 경로를 줘도 gitignore 된 것은 뺀다
        return [x for x in 나온것 if not 무시되나(x)]
    명령 = (["git", "-c", "core.quotepath=false", "ls-files"] if args.all else
          ["git", "-c", "core.quotepath=false", "diff", "--cached", "--name-only"])
    줄들 = subprocess.run(명령, capture_output=True, cwd=ROOT).stdout.decode("utf-8")
    return [ROOT / x for x in (y.strip() for y in 줄들.split("\n")) if x
            and (ROOT / x).exists()]


def 무시되나(p: pathlib.Path) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", str(p)],
                       capture_output=True, cwd=ROOT)
    return r.returncode == 0


def 상대경로(p: pathlib.Path) -> str:
    """저장소 밖의 파일도 받는다 — 인자로 아무 경로나 줄 수 있다."""
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def 찾는다(실명: list[str], 파일들: list[pathlib.Path]) -> list[tuple]:
    """**경계를 보지 않는다.** 글자가 들어 있으면 전부 짚는다."""
    넘김 = 넘긴것()
    나온것 = []
    for p in 파일들:
        if p.suffix.lower() not in 글파일:
            continue
        # **넘긴 목록 자신은 보지 않는다.** 넘길 낱말을 적어 두는
        # 파일이라 거기 그 낱말이 있는 것이 당연하다
        if p.resolve() == 넘긴목록.resolve():
            continue
        try:
            글 = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        상대 = 상대경로(p)
        for 번호, 줄 in enumerate(글.split("\n"), 1):
            for 이름 in 실명:
                if 이름 in 줄 and not 넘기나(넘김, 상대, 이름):
                    나온것.append((상대, 번호, 이름, 줄.strip()))
    return 나온것


def main() -> int:
    ap = argparse.ArgumentParser(
        description="커밋될 파일에 실명이 들어 있는지 찾는다 (바꾸지는 않는다)")
    ap.add_argument("경로", nargs="*", help="볼 파일이나 폴더 (없으면 커밋될 것)")
    ap.add_argument("--all", action="store_true", help="추적 중인 파일 전부")
    args = ap.parse_args()

    names, phones = _anon.load_map()
    실명 = [a for a, _ in names] + [a for a, _ in phones]

    # **아무것도 안 보는 것은 통과가 아니다.** 대응표 구조가 바뀌거나
    # 파일이 비면 조용히 0개를 보게 되는데, 그때 초록이 뜨면 검사가
    # 있으나 마나다 — 2026-09-04 에 정확히 그 상태로 두 번 푸시했다.
    if not 실명:
        print("!! 대응표에서 읽은 실명이 0개입니다.")
        print("   검사가 아무것도 안 보고 있습니다 — 통과로 치지 않습니다.")
        print(f"   {_anon.MAP_PATH} 의 모양을 확인해 주세요.")
        return 2

    파일들 = 볼파일(args)
    나온것 = 찾는다(실명, 파일들)

    print(f"실명 {len(실명)}개로 파일 {len(파일들)}개를 봤습니다.")
    if not 나온것:
        print("걸린 것이 없습니다.")
        return 0

    print()
    print(f"!! {len(나온것)}곳에서 실명이 보입니다 (이름은 가려 찍습니다).")
    print("   오탐이면 docs/이름-확인됨.txt 에 `파일 | 낱말 | 왜 넘기는가` 로 적으세요.")
    print()
    앞선파일 = None
    for 상대, 번호, 이름, 줄 in 나온것:
        if 상대 != 앞선파일:
            print(f"  {상대}")
            앞선파일 = 상대
        미리 = 줄.replace(이름, 가린다(이름))
        print(f"    {번호:>5}줄  {가린다(이름)}  {미리[:78]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
