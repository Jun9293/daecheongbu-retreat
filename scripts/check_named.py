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
| 식별자 | `create_run` · `보조급자리` · `paint_of()` | 추적 중인 글 파일의 내용 |
| 선택자 | `.cell.st.pick` · `#statmenu` | CSS·JS·템플릿 |

**산문은 안 봅니다.** 백틱은 강조에도 쓰여서(`지연`·`대기`) 전부 보면
넘김 목록만 늘다가 아무도 안 읽습니다 (4-11 · 옛말.md 의 그 판단과 같다).

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
# 경로가 이 앞머리들 중 하나를 생략하고 적혀 있을 수 있다 (14장 표가 그렇다)
앞머리 = ("", "app/", "app/static/", "app/templates/", "docs/", "docs/mockups/",
        "scripts/", "tests/", "app/static/js/", "app/static/css/")

경로꼴 = re.compile(r"[\w./가-힣-]+\.(?:py|js|css|html|md|txt|bat|json|ini|yml|yaml)$")
선택자꼴 = re.compile(r"[.#][A-Za-z][\w-]*(?:[.#][\w-]+)*$")
식별자꼴 = re.compile(r"[A-Za-z가-힣_][\w가-힣_]*(?:\.[\w가-힣_]+)*(?:\(\))?$")
# **캠멜은 8장의 데이터 모델 표기다** (`assigneeName` · `TaskRun.startedAt`).
# 코드는 스네이크라 글자 그대로는 없고, 그건 문서가 정한 표기법이지 낡은
# 이름이 아니다 — 그 표기를 검사에 넣으면 넘김 목록이 모델 필드로 찬다.
캠멜꼴 = re.compile(r"[a-z][A-Za-z0-9]*[A-Z]")


def 넘긴것() -> set[str]:
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


def 이름들() -> dict[str, str]:
    """{이름: 축} — 문서가 이름한 코드 모양.

    **8장의 데이터 모델은 캠멜 표기다**(`assigneeName`). 코드는 스네이크라
    글자 그대로는 없고, 그건 문서가 정한 표기법이지 낡은 이름이 아니다 —
    그 블록은 통째로 건너뛴다.
    """
    글 = 문서.read_text(encoding="utf-8")
    # 8장 데이터 모델 코드블록 (``` 로 감싼 것) 은 표기법이 다르다
    글 = re.sub(r"```[\s\S]*?```", "", 글)
    나온것: dict[str, str] = {}
    for t in re.findall(r"`([^`\n]{2,90})`", 글):
        t = t.strip()
        if " " in t or t.startswith("-"):        # 산문·명령줄 스위치
            continue
        if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", t):     # 색 값
            continue
        if any(c in t for c in "?&=<>{}*'\"[]:,"):    # 주소·조각·예시
            continue
        if 경로꼴.fullmatch(t):
            나온것.setdefault(t, "경로")
        elif 선택자꼴.fullmatch(t) and not t[1:].isdigit():
            나온것.setdefault(t, "선택자")
        elif 식별자꼴.fullmatch(t) and not t.isdigit():
            # **한 낱말 한글은 대개 산문이다** — `지연`·`대기` 처럼 강조로
            # 쓴다. 밑줄·점·괄호가 있거나 영문이 섞였을 때만 이름으로 본다
            if re.fullmatch(r"[가-힣]+", t):
                continue
            if 캠멜꼴.search(t.split(".")[-1].rstrip("()")):
                continue                       # 8장의 모델 표기
            나온것.setdefault(t, "식별자")
    return 나온것


def 코드파일(경로: set[str]) -> list[pathlib.Path]:
    """식별자를 찾을 파일 — **코드뿐이다.**

    문서까지 뒤지면 다른 문서가 그 이름을 한 번이라도 적어 둔 것만으로
    「있다」 가 되어, 이 검사가 잡으려던 바로 그것(문서에만 남은 이름)을
    못 잡는다 — 실제로 지워진 이름 하나가 **옛말 목록에 적혀 있다는
    이유로** 통과했다.
    """
    나온것 = []
    for 이름 in sorted(경로):
        p = ROOT / 이름
        if p.suffix.lower() in 코드꼴 and p.exists():
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
    넘김 = 넘긴것()
    나온것 = []
    for t, 축 in sorted(이름.items()):
        if t in 넘김:
            continue
        if 축 == "경로":
            if any((앞 + t) in 경로 for 앞 in 앞머리):
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
            if "." in 벗긴것 and 벗긴것.rsplit(".", 1)[-1] in 글:
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

    if args.목록:
        for 축 in ("경로", "식별자", "선택자"):
            것들 = sorted(t for t, a in 이름.items() if a == 축)
            print(f"\n{축} {len(것들)}개")
            for t in 것들:
                print("   ", t)
        return 0

    경로, 글, 모양 = 저장소글()
    빠진것 = 없는것(이름, 경로, 글, 모양)
    print(f"문서가 이름한 {len(이름)}개(경로·식별자·선택자)를 저장소에서 찾았습니다.")
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
