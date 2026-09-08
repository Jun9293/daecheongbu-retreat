# -*- coding: utf-8 -*-
"""**자리를 세어 둔 말이 남아 있는가** (10장 · 11-3 3단계의 셋째 축).

## 왜 검사인가

10장이 「자리를 세어 두지 않습니다」 라고 못박아 둔 것을 **사람이 다섯 판
연속 어겼습니다.** 매번 커밋 전 검토가 잡았습니다 —

    「거의 늘 넷」 이라 적고 같은 작업 안에서 다섯이 됨
    「셋 다」·「세 곳」 을 놓침
    「여덟 곳」 이라 적고 아홉을 나열
    「넘김 15개(6·3·6)」 이라 적고 7·3·5
    「보는 세 곳」 이 넷이고 「읽는 곳 아홉」 이 열

전부 **적자마자 이미 틀렸거나 다음 판에서 틀렸습니다.** 규칙을 알고
있는 사람이 다섯 번 어겼으면 그것은 사람이 조심할 일이 아닙니다.

## 무엇을 잡는가

**셋 이상의 수 + 자리를 세는 말**입니다.

| 잡는 모양 | 보기 |
|---|---|
| 수 + `곳`·`군데` | `세 곳` · `네 곳` · `33곳` |
| `곳`·`자리`·`군데` + 조사 + 수 | `자리가 셋` · `읽는 곳은 아홉` |

**둘은 안 잡습니다.** 이 저장소에서 「두 곳」·「두 벌」 은 개수를 주장하는
말이 아니라 **원칙**입니다 — 「같은 것이 두 곳에 있으면 갈린다」. 그 말을
막으면 정작 지켜야 할 규칙을 못 적습니다.

**`벌`·`개`·`자리`(수가 바로 뒤에 붙는 것)는 안 잡습니다** — `8자리`는
자릿수이고 `세 벌`은 시험의 세 축(막힘·뚫림·봄)처럼 이름이 붙은 묶음입니다.
넓히면 넘김 목록이 낱말 수만큼 늘고, 늘어난 목록은 아무도 안 읽습니다
(4-11 의 그 자리).

## 날짜가 있으면 지나갑니다

**그때 잰 값은 낡지 않습니다.** 「2026-09-03 에 세어 봤더니 107곳」 은
지금에 대한 주장이 아니라 그날의 사실이라, 앞뒤 한 줄에 날짜가 있으면
그냥 지나갑니다. 이 규칙이 없으면 이력을 적을 수가 없습니다.

넘기는 것은 `docs/세어둠.txt` 에 **왜 세어도 되는지와 함께** 적습니다 —
읽는 규칙은 `scripts/넘김.py` 하나입니다(이유 없는 줄은 넘김이 아닙니다).

    .venv\\Scripts\\python.exe scripts/check_counts.py
    .venv\\Scripts\\python.exe scripts/check_counts.py --목록
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import 넘김  # noqa: E402

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
넘김목록 = ROOT / "docs" / "세어둠.txt"

글파일 = {".py", ".js", ".md", ".txt", ".css", ".html"}

# **셋 이상만.** 둘은 이 저장소의 원칙 문장이다 (위 독스트링)
한글수 = r"(?:세|네|다섯|여섯|일곱|여덟|아홉|열|셋|넷)"
숫자 = r"(?:[3-9]|\d\d+)"
수 = rf"(?:{한글수}|{숫자})"
# **한글 수 뒤에는 공백을 요구한다.** 안 그러면 `세곳` 같은 **변수 이름**이
# 걸린다 — 산문은 「세 곳」 이라 띄어 쓴다. 숫자는 「53곳」 처럼 붙여 쓴다.
# 뒤에 오는 조사(을·이·은)까지 막지 않는다 — `(?![\w])` 로 두었더니
# 한글이 전부 `\w` 라 **「53곳을」 이 안 걸렸다**
센말 = re.compile(rf"(?:{한글수}\s+|{숫자}\s*)(?:곳|군데)")
# `자리가 셋` · `읽는 곳은 아홉` — 수가 뒤에 오는 모양.
# 뒤에 `-` 가 붙으면 절 번호다(`그 자리는 4-15 홈이 맡는다`)
센말뒤 = re.compile(rf"(?:곳|자리|군데)(?:은|는|이|가)\s*({수})(?![\d-])")
날짜 = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}월 ?\d{1,2}일|\d{2}\.\d{2}\.\d{2}")


def 볼파일() -> list[pathlib.Path]:
    넘길것, 이유없음 = 넘김.읽는다(넘김목록)
    if 이유없음:
        넘김.말한다(넘김목록, 이유없음)
        raise SystemExit(2)
    출 = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files"],
                       cwd=ROOT, capture_output=True).stdout.decode("utf-8")
    나온것 = []
    for 이름 in sorted(x.strip() for x in 출.splitlines() if x.strip()):
        if 이름 in 넘길것 or any(이름.startswith(x) for x in 넘길것 if x.endswith("/")):
            continue
        p = ROOT / 이름
        if p.suffix.lower() in 글파일 and p.exists():
            나온것.append(p)
    return 나온것


def 글줄(p: pathlib.Path) -> list[tuple[int, str]]:
    """**주석·독스트링·문서 본문만 본다.**

    코드 줄에도 수는 나오는데(`limit=3` · `[:5]`) 그건 값이지 주장이
    아니다. 잡을 것은 **사람이 사람에게 적은 말**이다.
    """
    글 = p.read_text(encoding="utf-8", errors="replace")
    줄들 = 글.splitlines()
    if p.suffix in (".md", ".txt"):
        return list(enumerate(줄들, 1))
    나온것, 안쪽 = [], False
    for i, 줄 in enumerate(줄들, 1):
        t = 줄.strip()
        if p.suffix == ".py":
            # **한 줄짜리 독스트링을 빠뜨리지 않는다.** `"""` 이 한 줄에
            # 둘이면 열고 닫은 것이라 안쪽 상태가 안 바뀐다 — 처음에는
            # `== 1` 만 봐서 그 줄이 통째로 안 보였다
            if t.count('"""') >= 2:
                나온것.append((i, 줄))
                continue
            if t.count('"""') == 1:
                안쪽 = not 안쪽
                나온것.append((i, 줄))
                continue
            if 안쪽 or t.startswith("#") or "  #" in 줄:
                나온것.append((i, 줄))
        else:                                   # js · css · html
            if (t.startswith(("//", "*", "/*", "{#")) or "//" in 줄 or "/*" in 줄):
                나온것.append((i, 줄))
    return 나온것


def 문단(본문: list[str], 번호: int) -> str:
    """그 줄이 든 문단 — 빈 줄과 빈 줄 사이.

    날짜는 문단 머리에 한 번 적고 수는 그 아래에 나온다. 문단 단위로
    봐야 「그때 잰 값」 이 문단 전체에 걸린다.
    """
    i = 번호 - 1
    앞 = i
    while 앞 > 0 and 본문[앞 - 1].strip():
        앞 -= 1
    뒤 = i
    while 뒤 + 1 < len(본문) and 본문[뒤 + 1].strip():
        뒤 += 1
    return "\n".join(본문[앞:뒤 + 1])


def 찾는다(파일들: list[pathlib.Path]) -> list[tuple[str, int, str, str]]:
    나온것 = []
    for p in 파일들:
        줄들 = 글줄(p)
        본문 = p.read_text(encoding="utf-8", errors="replace").splitlines()
        for 번호, 줄 in 줄들:
            # **앞뒤 한 줄에 날짜가 있으면 그때 잰 값이다** (독스트링)
            if 날짜.search(문단(본문, 번호)):
                continue
            # **한 줄에 한 번만 낸다.** 「곳은 세 곳」 은 두 모양에 다
            # 걸리는데, 고칠 곳은 그 줄 하나다 — 두 번 내면 수가 부풀고
            # 사람이 같은 줄을 두 번 찾는다
            m = 센말.search(줄) or 센말뒤.search(줄)
            if m:
                나온것.append((p.relative_to(ROOT).as_posix(), 번호,
                             m.group(0), 줄.strip()[:76]))
    return 나온것


def main() -> int:
    ap = argparse.ArgumentParser(
        description="자리를 세어 둔 말이 남아 있는지 찾는다 (10장)")
    ap.add_argument("--목록", action="store_true", help="무엇을 찾는지만")
    args = ap.parse_args()

    if args.목록:
        print("잡는 모양")
        print(f"    수 + 곳·군데        {센말.pattern}")
        print(f"    곳·자리·군데 + 수    {센말뒤.pattern}")
        print("\n둘은 안 잡습니다 — 이 저장소에서 「두 곳」 은 원칙 문장입니다.")
        print("앞뒤 한 줄에 날짜가 있으면 그때 잰 값이라 지나갑니다.")
        return 0

    파일들 = 볼파일()
    # **아무것도 안 보는 것은 통과가 아니다** (11-3)
    if not 파일들:
        print("!! 볼 파일이 0개입니다 — 검사가 아무것도 안 보고 있습니다.")
        return 2

    넘길것, _ = 넘김.읽는다(넘김목록)
    걸린것 = 찾는다(파일들)
    print(f"파일 {len(파일들)}개에서 자리를 세는 말을 찾았습니다.")
    print(f"   {len(넘길것)}개는 {넘김목록.name} 에 이유와 함께 넘겨 두었습니다.")
    if not 걸린것:
        print("세어 둔 자리가 없습니다.")
        return 0

    print()
    print(f"!! {len(걸린것)}곳에서 자리를 세고 있습니다.")     # noqa: 이 줄은 세는 말이 아니라 결과다
    print("   세지 않는 말로 바꾸세요 — 「여럿이다」 · 「…로 찾으면 나온다」.")
    print("   세는 것이 맞는 자리면 docs/세어둠.txt 에 `파일 | 왜` 로 적으세요.")
    print()
    앞선파일 = None
    for 상대, 번호, 말, 줄 in 걸린것:
        if 상대 != 앞선파일:
            print(f"  {상대}")
            앞선파일 = 상대
        print(f"    {번호:>5}줄  「{말}」")
        print(f"           {줄}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
