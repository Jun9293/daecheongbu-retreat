# -*- coding: utf-8 -*-
"""**CLAUDE.md 가 이름한 것이 저장소에 실제로 있는가** (11-3 3단계의 둘째 축).

## 왜 둘째 축인가

옛말 검사(`check_stale`)는 **사람이 목록에 적어 둔 것만** 찾습니다. 그래서
적는 것을 잊으면 도구가 없는 것과 같습니다 — 2026-09-08 에 그 도구를
만든 판이 **자기가 바꾼 말을 목록에 안 적어** 4-0 이 옛 상태로 남았고,
그때 바뀐 시험 예외 목록의 이름은 **문서에만 있는 이름**이 됐습니다
(검토가 잡음).

이 검사는 목록에 기대지 않습니다. **문서가 이름한 것을 저장소에서
찾아보는 것**뿐이라, 이름이 바뀌면 적어 두지 않아도 걸립니다.

## 무엇을 보는가

백틱 안의 **코드 모양**만 봅니다. 셋으로 갈라 각각 다른 곳을 봅니다.

| 축 | 모양 | 어디서 찾나 |
|---|---|---|
| 경로 | `app/domain/tasks.py` · `templates/tasks.html` | git 이 아는 파일 목록(앞에 `app/` 등이 생략됐을 수 있다) |
| 식별자 | `create_run` · `보조급자리` · `paint_of()` | **코드 파일만** (문서는 안 본다 — 아래) |
| 선택자 | `.cell.st.pick` · `#statmenu` | CSS·JS·템플릿 |
| 토큰 | `--fz` · `--ink-2` | CSS·JS·템플릿, 없으면 코드(명령줄 스위치와 생김새가 같다) |

**산문은 안 봅니다.** 백틱은 강조에도 쓰여서(`지연`·`대기`) 전부 보면
넘김 목록만 늘다가 아무도 안 읽습니다 (4-11 · 옛말.md 의 그 판단과 같다).
다만 **한 낱말 한글을 통째로 버리지는 않습니다** — 이 저장소가 실제로
쓰는 이름이 그 모양이라(`안여는곳`·`보조급자리`) 버리면 이 축이 정작
우리가 바꾸는 이름을 못 봅니다. 강조로 쓴 것은 대개 코드에도 있어 그냥
지나갑니다.

넘기는 것은 `docs/이름-넘김.txt` 에 **왜 넘기는지와 함께** 적습니다 —
지운 화면(`app.css`)처럼 **없는 것이 맞는 이름**이 그것입니다.

## 아무것도 안 보는 것은 통과가 아니다

본 이름이 0개면 **실패합니다** (11-3).

    .venv\\Scripts\\python.exe scripts/check_named.py
    .venv\\Scripts\\python.exe scripts/check_named.py --목록
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
문서 = ROOT / "CLAUDE.md"
넘김목록 = ROOT / "docs" / "이름-넘김.txt"

글파일 = {".py", ".js", ".css", ".html", ".txt", ".bat", ".json", ".md",
        ".yml", ".yaml", ".ini", ".cfg", ".toml"}
# **식별자를 찾는 곳은 코드뿐이다** — 아래 `저장소글` 의 이유
코드꼴 = {".py", ".js", ".css", ".html", ".bat", ".json", ".ini",
        ".yml", ".yaml", ".cfg", ".toml"}
경로꼴 = re.compile(r"[\w./가-힣-]+\.(?:py|js|css|html|md|txt|bat|json|ini|yml|yaml)$")
선택자꼴 = re.compile(r"[.#][A-Za-z][\w-]*(?:[.#][\w-]+)*$")
식별자꼴 = re.compile(r"[A-Za-z가-힣_][\w가-힣_]*(?:\.[\w가-힣_]+)*(?:\(\))?$")
# CSS 토큰(`--fz` · `--ink-2`)은 모양 파일에서 찾는다. `--실행` 같은 명령줄
# 스위치와 생김새가 같아서, **모양에 있으면 토큰이고 없으면 스위치다**
토큰꼴 = re.compile(r"--[a-z][\w-]*$")


def 넘긴것() -> tuple[set[str], list[tuple[int, str]]]:
    """**읽는 규칙은 `scripts/넘김.py` 하나다** (그 파일의 이유)."""
    return 넘김.읽는다(넘김목록)


def 이름들() -> dict[str, str]:
    """{이름: 축} — 문서가 이름한 코드 모양.

    **8장의 데이터 모델(캠멜 표기)은 코드블록 안에 있어 이미 빠진다** —
    처음에는 캠멜을 따로 걸렀는데, 그러면 `originOf`·`statMenu`·`putFile`
    처럼 **본문이 이름한 진짜 함수**가 함께 빠졌다(검토가 짚음). 코드는
    스네이크라던 짐작도 이 저장소에는 안 맞는다 — JS 가 절반이다.

    **한 낱말 한글도 본다.** `안여는곳`·`보조급자리`·`쪽지읽기` 처럼 이
    저장소가 실제로 쓰는 이름이 그 모양이라, 빼면 **이 축이 정작 우리가
    바꾸는 이름을 못 본다.** 대신 `지연`·`대기` 같은 강조는 **코드에
    있으면 통과**하므로 실제로 걸리는 것만 넘김에 적으면 된다.
    """
    글 = 문서.read_text(encoding="utf-8")
    # 8장 데이터 모델 코드블록 (``` 로 감싼 것) 은 표기법이 다르다
    글 = re.sub(r"```[\s\S]*?```", "", 글)
    나온것: dict[str, str] = {}
    for t in re.findall(r"`([^`\n]{2,90})`", 글):
        t = t.strip()
        if " " in t:                                  # 산문
            continue
        if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", t):     # 색 값
            continue
        if any(c in t for c in "?&=<>{}*'\"[]:,"):    # 주소·조각·예시
            continue
        if 토큰꼴.fullmatch(t):
            나온것.setdefault(t, "토큰")
        elif t.startswith("-"):                       # 명령줄 스위치
            continue
        elif 경로꼴.fullmatch(t):
            나온것.setdefault(t, "경로")
        elif 선택자꼴.fullmatch(t) and not t[1:].isdigit():
            나온것.setdefault(t, "선택자")
        elif 식별자꼴.fullmatch(t) and not t.isdigit():
            나온것.setdefault(t, "식별자")
    return 나온것


def 코드파일(경로: set[str]) -> list[pathlib.Path]:
    """식별자를 찾을 파일 — **코드뿐이다.**

    문서까지 뒤지면 다른 문서가 그 이름을 한 번이라도 적어 둔 것만으로
    「있다」 가 되어, 이 검사가 잡으려던 바로 그것(문서에만 남은 이름)을
    못 잡는다 — 실제로 지워진 이름 하나가 **옛말 목록에 적혀 있다는
    이유로** 통과했다.

    **자기 자신은 뺀다.** 이 파일은 자기가 무엇을 보는지 설명하려고
    보기로 든 이름들을 담고 있어서, 그 이름이 코드에서 사라져도
    **자기 설명 덕분에 통과한다** — 10장의 「도구는 자기가 금지하는 것을
    설명하려고 담게 된다」 가 방향만 뒤집힌 자리다.
    """
    나온것 = []
    나 = pathlib.Path(__file__).resolve()
    for 이름 in sorted(경로):
        p = ROOT / 이름
        if p.suffix.lower() in 코드꼴 and p.exists() and p.resolve() != 나:
            나온것.append(p)
    return 나온것


def 저장소글() -> tuple[set[str], str, str]:
    """(파일 경로 집합, **코드**의 글, 화면·모양 파일의 글)."""
    출 = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files"],
                       cwd=ROOT, capture_output=True).stdout.decode("utf-8")
    경로 = {x.strip() for x in 출.split("\n") if x.strip()}
    글, 모양 = [], []
    for p in 코드파일(경로):
        try:
            내용 = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        글.append(내용)
        if p.suffix.lower() in {".css", ".js", ".html"}:
            모양.append(내용)
    return 경로, "\n".join(글), "\n".join(모양)


def 없는것(이름: dict[str, str], 경로: set[str], 글: str, 모양: str) -> list[tuple[str, str]]:
    넘길것, _ = 넘긴것()
    나온것 = []
    for t, 축 in sorted(이름.items()):
        if t in 넘길것:
            continue
        if 축 == "경로":
            # **앞머리를 세어 두지 않는다** (10장). 14장 표는 `partials/
            # drawer.html` 처럼 앞을 줄여 적으므로 어딘가 생략된 것을
            # 받아야 하는데, 폴더 목록을 손으로 적어 두면 폴더가 하나
            # 늘 때마다 멀쩡한 파일이 「없다」 로 걸린다 — 실제로
            # `docs/review/` 가 빠져 있어 있는 파일이 넘김에 적혔다.
            # **`/` 경계에서 끝나는 파일이 있으면 있는 것이다**
            if t in 경로 or any(p.endswith("/" + t) for p in 경로):
                continue
        elif 축 == "토큰":
            # `--fz` 는 CSS 토큰이고 `--실행` 은 명령줄 스위치다. 생김새가
            # 같아 나눌 수 없지만 **나눌 필요도 없다** — 둘 중 무엇이든
            # 저장소 어딘가(모양 또는 코드)에 있으면 있는 것이다
            if t in 모양 or t in 글:
                continue
        elif 축 == "선택자":
            if t in 모양:
                continue
        else:
            벗긴것 = t.rstrip("()")
            if 벗긴것 in 글:
                continue
            # `check_dev_db.제외칸` 처럼 **어디의 무엇**으로 적은 것은
            # 마지막 토막이 그 파일에 있으면 된 것이다 — 코드에는 모듈
            # 이름을 붙여 쓰지 않는다
            토막 = 벗긴것.rsplit(".", 1)[-1]
            if "." in 벗긴것 and 토막 in 글:
                continue
            # **8장의 표기는 캠멜이고 코드는 스네이크다** (`assigneeName`
            # ↔ `assignee_name`). 그건 문서가 정한 표기법이지 낡은 이름이
            # 아니므로, 스네이크로 바꿔 한 번 더 본다. 캠멜을 통째로
            # 건너뛰던 때는 `originOf`·`statMenu` 같은 **본문이 이름한
            # 진짜 함수**가 함께 빠져 이 축이 정작 우리가 바꾸는 이름을
            # 못 봤다 (검토가 짚음)
            스네이크 = re.sub(r"(?<!^)(?=[A-Z])", "_", 토막).lower()
            if 스네이크 != 토막 and 스네이크 in 글:
                continue
        나온것.append((t, 축))
    return 나온것


def main() -> int:
    ap = argparse.ArgumentParser(
        description="CLAUDE.md 가 이름한 것이 저장소에 있는지 본다")
    ap.add_argument("--목록", action="store_true", help="무엇을 보는지만")
    args = ap.parse_args()

    이름 = 이름들()
    # **아무것도 안 보는 것은 통과가 아니다** (11-3)
    if not 이름:
        print("!! 문서에서 읽은 이름이 0개입니다 — 검사가 아무것도 안 보고 있습니다.")
        return 2

    # **이유 없는 넘김은 넘김이 아니다.** 조용히 버리면 적은 사람은
    # 넘긴 줄 알고 검사는 안 넘긴 채로 돈다 (scripts/넘김.py)
    넘길것, 이유없음 = 넘긴것()
    if 이유없음:
        넘김.말한다(넘김목록, 이유없음)
        return 2

    if args.목록:
        for 축 in ("경로", "식별자", "선택자", "토큰"):
            것들 = sorted(t for t, a in 이름.items() if a == 축)
            print(f"\n{축} {len(것들)}개")
            for t in 것들:
                print("   ", t)
        return 0

    경로, 글, 모양 = 저장소글()
    빠진것 = 없는것(이름, 경로, 글, 모양)
    print(f"문서가 이름한 {len(이름)}개(경로·식별자·선택자·토큰)를 저장소에서 찾았습니다.")
    # **넘김이 자라는 것 자체가 보여야 한다** — 줄어들 일이 없는 목록은
    # 찍어 두지 않으면 아무도 그 크기를 모른다
    print(f"   그중 {len(넘길것)}개는 {넘김목록.name} 에 이유와 함께 넘겨 두었습니다.")
    if not 빠진것:
        print("문서에만 있는 이름이 없습니다.")
        return 0

    print()
    print(f"!! {len(빠진것)}개가 문서에만 있습니다 — 이름이 바뀌었거나 지워진 것입니다.")
    print("   문서를 지금 이름으로 고치거나, 없는 것이 맞으면")
    print(f"   docs/{넘김목록.name} 에 `이름 | 왜 넘기는가` 로 적으세요.")
    print()
    for t, 축 in 빠진것:
        print(f"   [{축}] {t}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
