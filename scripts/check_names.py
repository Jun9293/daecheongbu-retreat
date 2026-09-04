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

## 이 검사를 손댈 때

**주석만 적힌 상태에서 한 번 돌리세요.** 금지하는 것을 설명하려면
그것을 적게 됩니다 — 다 만들고 돌리면 여러 번 빨개진 뒤에 압니다
(10장).
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
남은목록 = ROOT / "docs" / "이름-남은곳.txt"

# 글자만 있는 파일을 본다. 이미지·zip 안의 실명은 이 검사의 몫이 아니다.
글파일 = {".py", ".md", ".txt", ".html", ".js", ".css", ".json", ".bat",
        ".yml", ".yaml", ".ini", ".cfg", ".toml"}


def 가린다(이름: str) -> str:
    """**실명을 화면에 그대로 찍지 않는다.** 검사 결과가 로그·CI·채팅으로
    돌아다니는데, 거기 실명이 찍히면 막으려던 것을 검사가 하고 있는 셈이다."""
    if len(이름) <= 1:
        return "◯"
    return 이름[0] + "◯" * (len(이름) - 1)


def 넘긴것() -> set:
    """**넘기는 것은 이름이 아니라 낱말이다.**

    전에는 **이름을 통째로** 넘겼다. 그러면 회의록에서 홀로 선 그 이름도
    안 걸린다 — 지키려던 바로 그것이 빠진다. 넘겨야 할 것은 이름이
    아니라 **그 이름을 품은 낱말**(`진행`·`사진`·`필요한` 같은)이다.

    4-0 의 `흐려도_되는곳` 과 같은 방식이다 — 규칙을 끄는 것이 아니라
    넘길 자리를 이름으로 적어 두는 것이다.
    """
    if not 넘긴목록.exists():
        return set()
    나온것 = set()
    for 줄 in 넘긴목록.read_text(encoding="utf-8").splitlines():
        줄 = 줄.strip()
        if not 줄 or 줄.startswith("#"):
            continue
        칸 = [x.strip() for x in 줄.split("|")]
        if len(칸) >= 2 and 칸[0] and 칸[1]:
            나온것.add(칸[0])
    return 나온것


def 남은곳() -> set:
    """**아직 안 고친 자리** (파일, 줄번호).

    이미 있던 것이라 이번 diff 와 섞으면 무엇 때문에 빨개졌는지
    안 읽힌다. 그래서 넘기되 **몇 곳인지 끝에 말한다** — 조용히
    넘기면 이 목록이 있다는 것조차 잊힌다.
    """
    if not 남은목록.exists():
        return set()
    나온것 = set()
    for 줄 in 남은목록.read_text(encoding="utf-8").splitlines():
        줄 = 줄.strip()
        if not 줄 or 줄.startswith("#"):
            continue
        칸 = [x.strip() for x in 줄.split("|")]
        if len(칸) >= 2 and 칸[1].isdigit():
            나온것.add((칸[0], int(칸[1])))
    return 나온것


# 담당자 칸에 들어오는, **사람 이름이 아닌 말.**
#
# ── 어디에 적는가 (여기가 정본이다) ────────────────────────────
#
#   부서·파트·팀 이름   `anonymize.KEEP`
#       2장의 부서표 · 5-3 의 총무팀 파트 · 성가대 같은 팀.
#       **익명화에서도 영영 제외된다** — 바꿔서는 안 되는 말이다
#
#   그 밖에 이름이 아닌 말   여기 (`_이름아님`)
#       역할·호칭(`목사님`), 자리를 가리키는 말(`담당`·`미정`).
#       **이 검사에서만 안 본다** — 익명화는 그대로 지나간다.
#       바꿀 이름이 아니라 이름이 아닌 말이므로 그것으로 충분하다
#
#   낱말 안에 든 이름   `docs/이름-확인됨.txt`
#       `필요한`·`진행` 처럼 실명 검사의 오탐. **글 전체**를 보는
#       쪽이 쓰고, 담당자 칸을 보는 이 검사는 쓰지 않는다
#
# **KEEP 에 잘못 넣는 것이 가장 조용하다** — 영영 안 바뀌고 검사도
# 안 본다. 그래서 KEEP 은 좁게 두고, 애매하면 `_이름아님` 이다.
_이름아님 = {"담당", "미정", "없음", "공통",
           # 역할·호칭 — 바꿀 이름이 아니라 이름이 아닌 말이다
           "목사", "목사님", "사진스탭", "총무스탭"}

# **담당을 적는 칸. 늘어나면 여기 더한다** — 이 목록이 곧 "무엇을 보는가"
# 이고, 빠뜨리면 그 칸의 이름은 영영 안 보인다.
#
# **칸 이름이 아니라 「어디의 무엇」 으로 적는다.** 전에는 이름만 셋을
# 두고 JSON 갈래만 그것을 썼는데, DB 갈래는 자기 목록을 따로 들고
# 있었다 — **여기 넷째를 더해도 DB 는 안 따라왔다.** 위의 주석이
# 보증한다고 적은 것이 절반만 사실이었다. 이 검사가 고친 고장이
# 「보는 목록이 불완전했다」 인데 같은 모양이 한 칸 옆에 있었다.
담당칸 = (
    ("json", "assignee"),       # 5-3 이 정한 자리
    ("json", "assignee_name"),  # 〃
    ("json", "host"),           # 8장 Program.host — 「누가 진행하나」
    ("db", "program_items", "assignee_name"),
    ("db", "programs", "host"),
)

# **두 갈래가 이 한 목록에서 자기 몫을 뽑아 쓴다.** 따로 들면 갈린다.
JSON칸 = frozenset(x[1] for x in 담당칸 if x[0] == "json")
DB칸 = tuple((x[1], x[2]) for x in 담당칸 if x[0] == "db")


def 표밖담당자(자료폴더: pathlib.Path | None = None) -> dict:
    """**운영 자료의 담당자 칸에 있는데 대응표에 없는 이름.**

    `check_names` 는 **대응표에 있는 표기만** 찾는다. 그래서 표에
    없는 이름은 영영 안 보인다 — 2026-09-04 에 이름 하나가 정확히
    그 틈으로 공개 커밋에 남았고, 사람이 원본과 공개본을 손으로
    대조해서야 찾았다(셋 중 둘은 바뀌었는데 하나만 남았다).

    "아무것도 안 보는 것은 통과가 아니다" 는 막았지만 **"볼 목록이
    불완전하다" 는 안 막혀 있었다.**

    **막지 않고 말만 한다.** 사람 이름인지 아닌지는 사람만 안다.
    정한 것은 `docs/이름-확인됨.txt` 에 `[사람]` 표시로 쌓는다.
    """
    import json
    import re
    있는표기 = set(_anon.표기들())
    # **실명 검사의 넘김 목록을 같이 쓰지 않는다.** 그 목록은 「낱말
    # 안에 든 이름」 을 넘기는 자리라, 여기서 함께 쓰면 담당자 칸에
    # 홀로 선 그 이름까지 잠재운다 — `이름-확인됨.txt` 머리말이
    # 경고한 바로 그 입구다.
    아는말 = set(_anon.KEEP) | _이름아님
    본칸 = 0
    나온것: dict = {}
    걸린아는말: set = set()

    def 훑기(o):
        nonlocal 본칸
        if isinstance(o, dict):
            for k, v in o.items():
                # **담당을 적는 칸 전부** — 위 `담당칸` 에서 뽑았다.
                # `assignee`·`assignee_name` 은
                # 5-3 이 정한 자리이고, `host` 는 8장 `Program.host` —
                # 「누가 진행하나」 를 적는 칸이라 사람 이름이 지나간다.
                # 전에는 앞의 둘만 봤는데, 익명화는 `host` 도 실제로
                # 바꾸고 있었다 — **보는 목록이 불완전했다.**
                if k in JSON칸 and isinstance(v, str):
                    본칸 += 1
                    for 조각 in re.split(r"[·,/\s]+", v):
                        조각 = 조각.strip().rstrip("M")
                        # **창을 좁히지 않는다.** 전에는 2~3글자만
                        # 봤는데, 5-3 이 한 글자 담당자 표기를
                        # 적어 두었다 — 그때 0개였던 것은 걸러서가
                        # 아니라 **안 봐서** 0 이었다.
                        # 위는 다섯 글자까지 본다. 그보다 긴 것은
                        # 사람 이름이 아니라 묶음 이름이다.
                        if not (1 <= len(조각) <= 5) or 조각 in 있는표기:
                            continue
                        if 조각 in 아는말:
                            걸린아는말.add(조각)
                        else:
                            나온것[조각] = 나온것.get(조각, 0) + 1
                else:
                    훑기(v)
        elif isinstance(o, list):
            for x in o:
                훑기(x)

    폴더 = 자료폴더 if 자료폴더 is not None else ROOT / "data"
    for p2 in sorted(폴더.glob("*.real.*")):
        if p2.suffix != ".json":
            continue
        try:
            훑기(json.loads(p2.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue

    # **DB 도 본다.** 2026-09-04 에 실제로 이름이 샌 제안 문서는
    # `app.db` 에서 나왔다 — 파일만 보면 그쪽이 안 보인다.
    # 「볼 목록이 불완전하다」 를 막으려고 만든 검사가 스스로
    # 한 갈래만 보고 있었다.
    db = 폴더 / "app.db"
    if db.exists():
        import sqlite3
        try:
            이음 = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        except sqlite3.Error:
            return {"본칸": 본칸, "표밖": 나온것, "안본말": sorted(걸린아는말)}
        try:
            표들 = {r[0] for r in 이음.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for 표, 칸 in DB칸:
                if 표 not in 표들:
                    continue
                for (값,) in 이음.execute(
                        f"SELECT {칸} FROM {표} WHERE {칸} IS NOT NULL"):
                    훑기({칸: 값})
        except sqlite3.Error:
            pass
        finally:
            이음.close()
    # **KEEP 때문에 안 보는 것을 말한다.** KEEP 은 「절대 바꾸지
    # 않는다」 라서 잘못 들어간 것이 가장 조용하다 — 실명이 하나
    # 섞이면 영영 익명화되지 않고 이 검사도 안 본다.
    return {"본칸": 본칸, "표밖": 나온것, "안본말": sorted(걸린아는말)}


def 예외파일() -> set:
    """이 셋만 스스로를 담아도 된다 — 자기 코드 · 자기 시험 · 넘길 목록."""
    return {
        (ROOT / "scripts" / "check_names.py").resolve(),
        (ROOT / "tests" / "test_check_names.py").resolve(),
        넘긴목록.resolve(),
        남은목록.resolve(),
    }


def 낱말(줄: str, 자리: int, 길이: int) -> str:
    """걸린 자리를 품은 **한글 덩어리**를 잘라 낸다.

    `필요한 것들` 에서 두 글자가 걸리면 `필요한` 을 돌려준다.
    성이 붙은 이름에서 걸리면 **성까지 붙은 세 글자**를 돌려준다 —
    그래서 **낱말이 오탐인지 실명인지 사람이 보고 가를 수 있다.**
    (여기에 실명을 예로 적지 않는다. 적으면 이 검사에 스스로 걸린다.)
    """
    ㄱ, ㄴ = 자리, 자리 + 길이
    while ㄱ > 0 and "가" <= 줄[ㄱ - 1] <= "힣":
        ㄱ -= 1
    while ㄴ < len(줄) and "가" <= 줄[ㄴ] <= "힣":
        ㄴ += 1
    return 줄[ㄱ:ㄴ]


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
    # **기본은 저장소 전체다.** 스테이징된 것만 보면, 이미 커밋된
    # 자리에 남아 있는 것을 영영 못 본다 — 새는 구멍을 막은 뒤에는
    # 보는 범위를 넓혀야 한다.
    명령 = (["git", "-c", "core.quotepath=false", "diff", "--cached",
           "--name-only"] if args.staged else
          ["git", "-c", "core.quotepath=false", "ls-files"])
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


def 찾는다(실명: list[str], 파일들: list[pathlib.Path],
        남은것: list | None = None) -> list[tuple]:
    """**경계를 보지 않는다.** 글자가 들어 있으면 전부 짚는다.

    `남은것` 을 주면 «아직 안 고친 자리»(`이름-남은곳.txt`)에 든 것을
    그쪽으로 옮겨 담는다 — 결과에서는 빠지되 **세어서 말하기 위해서**다.
    """
    넘김 = 넘긴것()
    남은자리 = 남은곳() if 남은것 is not None else set()
    나온것 = []
    for p in 파일들:
        if p.suffix.lower() not in 글파일:
            continue
        # **예외는 셋뿐이다.** 어떤 것을 금지하는 도구는 그것을
        # 설명하려고 스스로 담게 된다 (10장). 자기 코드·자기 시험·
        # 넘길 목록이 그것이다.
        #
        # **검토 보고(`docs/review/최근.md`)는 예외가 아니다.** 운영
        # 자료에서 온 것을 계속 담을 파일이라, 빼면 정확히 새는 자리를
        # 안 보게 된다. 거기서는 가려서 적는다(`홍성◯`).
        if p.resolve() in 예외파일():
            continue
        try:
            글 = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        상대 = 상대경로(p)
        for 번호, 줄 in enumerate(글.split("\n"), 1):
            for 이름 in 실명:
                자리 = 줄.find(이름)
                while 자리 >= 0:
                    덩어리 = 낱말(줄, 자리, len(이름))
                    # **한 글자 이름은 홀로 섰을 때만 본다.**
                    # 낱말 안에 들면 `진행`·`사진`·`추진력` 처럼
                    # 끝없이 나와, 넘김 목록이 낱말 수만큼 늘어난다.
                    # **늘어난 목록은 아무도 읽지 않는다** (4-11).
                    # 그 자리는 `anonymize.py` 의 경계 규칙에 맡긴다.
                    #
                    # **이름의 위치로 가르지 않는다.** 이 자료에서
                    # 이름은 낱말 한가운데 오는 것이 정상이다
                    # (`◯◯M으로` · `9명 ◯◯◯ ◯◯◯`). 위치로 가르면
                    # 잡던 것을 놓친다. 가르는 축은 **길이**다.
                    짧은데붙었나 = len(이름) == 1 and 덩어리 != 이름
                    if not 짧은데붙었나 and 덩어리 not in 넘김:
                        한줄 = (상대, 번호, 이름, 줄.strip(), 덩어리)
                        if (상대, 번호) in 남은자리:
                            남은것.append(한줄)
                        else:
                            나온것.append(한줄)
                        break
                    자리 = 줄.find(이름, 자리 + 1)
    return 나온것


def main() -> int:
    ap = argparse.ArgumentParser(
        description="커밋될 파일에 실명이 들어 있는지 찾는다 (바꾸지는 않는다)")
    ap.add_argument("경로", nargs="*", help="볼 파일이나 폴더 (없으면 커밋될 것)")
    ap.add_argument("--staged", action="store_true",
                    help="커밋될 것만 (기본은 저장소 전체)")
    ap.add_argument("--all", action="store_true",
                    help="기본과 같다 (옛 이름)")
    args = ap.parse_args()

    # **구조를 묻지 않는다.** 물음 단위로만 부른다 — 대응표 모양이
    # 바뀌어도 여기가 안 깨진다
    실명 = _anon.표기들()

    # **아무것도 안 보는 것은 통과가 아니다.** 대응표 구조가 바뀌거나
    # 파일이 비면 조용히 0개를 보게 되는데, 그때 초록이 뜨면 검사가
    # 있으나 마나다 — 2026-09-04 에 정확히 그 상태로 두 번 푸시했다.
    if not 실명:
        print("!! 대응표에서 읽은 실명이 0개입니다.")
        print("   검사가 아무것도 안 보고 있습니다 — 통과로 치지 않습니다.")
        print(f"   {_anon.MAP_PATH} 의 모양을 확인해 주세요.")
        return 2

    파일들 = 볼파일(args)
    남은것: list = []
    나온것 = 찾는다(실명, 파일들, 남은것)

    def 남은말():
        # **0곳이면 0곳이라고 말한다.** 조용하면 이 목록이 있다는
        # 것조차 잊힌다 — 「걸린 것 없음」 을 0건으로 읽게 된다
        print(f"아직 안 고친 곳 {len(남은것)}곳"
              f" (docs/{남은목록.name})")

    def 표밖말():
        본 = 표밖담당자()
        if not 본["본칸"]:
            print("담당자 칸을 하나도 못 읽었습니다 —"
                  " 운영 자료가 없거나 파싱이 어긋났습니다.")
            return
        표밖 = 본["표밖"]
        # **0개면 0개라고 말한다.** 조용하면 이 자리가 있다는 것조차
        # 잊힌다 — 「아직 안 고친 곳 N곳」 과 같은 자리다
        말 = (" · ".join(f"{가린다(k)}({v})" for k, v in sorted(표밖.items()))
             if 표밖 else "")
        print(f"대응표에 없는 담당자 표기 {len(표밖)}개"
              f"{(': ' + 말) if 말 else ''}"
              f"  (담당자 칸 {본['본칸']}개를 봤습니다)")
        # **안 보는 것도 말한다.** KEEP 에 잘못 들어간 것이 가장
        # 조용하다 — 영영 안 바뀌고 이 검사도 안 본다
        if 본["안본말"]:
            print(f"   그중 이름이 아니라고 미리 정해 둔 것 "
                  f"{len(본['안본말'])}개: {' · '.join(본['안본말'])}")

    print(f"실명 {len(실명)}개로 파일 {len(파일들)}개를 봤습니다.")
    if not 나온것:
        print("걸린 것이 없습니다.")
        남은말()
        표밖말()
        return 0

    print()
    print(f"!! {len(나온것)}곳에서 실명이 보입니다 (이름은 가려 찍습니다).")
    print("   오탐이면 docs/이름-확인됨.txt 에 `낱말 | 왜 넘기는가` 로 적으세요.")
    print()
    앞선파일 = None
    for 상대, 번호, 이름, 줄, 덩어리 in 나온것:
        if 상대 != 앞선파일:
            print(f"  {상대}")
            앞선파일 = 상대
        미리 = 줄.replace(이름, 가린다(이름))
        print(f"    {번호:>5}줄  {가린다(덩어리)}  {미리[:74]}")
    print()
    남은말()
    표밖말()
    return 1


if __name__ == "__main__":
    sys.exit(main())
