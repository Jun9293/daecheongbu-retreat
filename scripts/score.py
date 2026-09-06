# -*- coding: utf-8 -*-
"""제안 채점표(`data/제안-N판.real.md`)를 **한 화면에 하나씩** 보여주는 작은 서버.

스무남은 개를 메모장으로 채점하면 회의록 인용과 근거가 표 한 줄에 뭉쳐 있어
읽히지 않고, 어디까지 했는지도 안 보인다. 이 화면은 제안 하나와 **그
회의의 원문을 나란히** 놓고, 근거로 인용된 대목을 원문 안에서 짚어 준다.

    .venv\\Scripts\\python.exe scripts/score.py

**한 번 쓰고 마는 도구다.** 채점이 끝나면 안 쓴다.

## 운영 앱에 붙이지 않는다

별도 포트(기본 8765)·별도 진입점이다. 운영 DB 는 **회의록 본문을 읽기만**
한다 — `init_db()` 도 부르지 않는다(그건 스키마를 고친다).

## 파일이 정본이다

누를 때마다 채점표 파일에 바로 쓴다. 화면은 그 파일을 매번
다시 읽어 보여줄 뿐이고, 메모리에 들고 있다가 마지막에 한 번 쓰지 않는다 —
창을 닫아도 그대로여야 한다.

**표를 새로 파싱하지 않는다.** 어느 줄이 제안인지는
`suggest_sample.py` 의 `제안줄인가()` 가 이미 안다. 두 벌이 되면 한쪽만
고쳐지고, 갈린 쪽이 사람이 채운 판정을 덮는다.

## 덮어쓰기 가드와 부딪히지 않는다

`suggest_sample.py` 의 `막는다()`·`채운곳()` 은 **「사람이 채운 것을
기계가 덮지 않는다」** 이고, 이 화면은 **「사람이 채운다」** 이다.
목적이 반대이므로 이 화면은 그 가드를 우회하는 것이 아니라 **애초에 그
가드가 막으려던 대상이 아니다.** 오히려 이 화면으로 한 칸이라도 채우면
그때부터 `suggest_sample.py` 는 `--replace` 로도 이 파일을 못 덮는다 —
그것이 맞는 동작이다.

기본은 `data/제안-3판.real.md` 이고 `--file` 로 다른 판을 연다.
**앞 판의 판정을 옆에 보여 주지 않는다** — 보여 주면 사람이 그것을
따라간다. 같은 업무가 다시 나와도 다시 판단해야 한다.

그래도 **쓰기 전에 원본을 백업한다** (`data/제안-N판.real.<시각>.bak`).
제안은 Claude 가 낸 것이라 다시 내면 같은 것이 나오지 않는다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import http.server
import importlib.util
import json
import pathlib
import re
import shutil
import sys
import threading
import webbrowser

_뿌리 = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_뿌리))

from sqlalchemy import select                                   # noqa: E402

from app.db import SessionLocal                                 # noqa: E402
from app.models import Meeting, Retreat                         # noqa: E402

채점표 = _뿌리 / "data" / "제안-3판.real.md"
회차이름 = "2026 여름수련회 Belong"

X이유들 = ["다른업무", "할일아님", "중복", "기타"]
판정들 = ["O", "X", "?"]


def _표파서():
    """**표를 읽는 규칙은 `suggest_sample.py` 것을 그대로 쓴다.**

    `공개본()` 이 `anonymize.py` 를 부르는 것과 같은 방식이다 — 스크립트라
    import 로는 못 가져오므로 경로로 읽어 온다.
    """
    스펙 = importlib.util.spec_from_file_location(
        "_ss_for_score", _뿌리 / "scripts" / "suggest_sample.py")
    M = importlib.util.module_from_spec(스펙)
    스펙.loader.exec_module(M)
    return M


SS = _표파서()


# ==========================================================================
# 파일 읽기 — 어느 줄이 무엇인지
# ==========================================================================

_회의머리 = re.compile(r"^## (?P<제목>.+?) \((?P<날짜>\d{4}-\d{2}-\d{2})\)\s*$")
_놓친것줄 = "안 나온 것이 있나요?"
_종류줄 = "종류가 아쉬운 것"
_일판자리 = "중: "


def 칸나눔(줄: str) -> list[str]:
    return 줄.split("|")


def 읽는다(글: str) -> dict:
    """채점표를 자리로 나눈다. **줄 번호를 들고 있는다** — 쓸 때 그 줄만 고친다."""
    줄들 = 글.splitlines()
    회의들: list[dict] = []
    지금 = None
    다채운뒤부터 = None
    놓친표: dict[str, int] = {}    # 짧은제목 -> 줄번호 (「다 채운 뒤」 의 놓친 것 표)
    종류줄: dict[str, int] = {}    # 종류 이름 -> 줄번호 (종류별 표)
    X이유줄: dict[str, int] = {}   # 이유 -> 줄번호
    일판줄 = None
    표머리 = ""

    for i, 줄 in enumerate(줄들):
        머리 = _회의머리.match(줄)
        if 머리 and 다채운뒤부터 is None:
            지금 = {"제목": 머리["제목"], "짧은제목": 머리["제목"].split(" (")[0],
                  "날짜": 머리["날짜"], "제안들": [], "놓친것줄": None,
                  "종류줄": None}
            회의들.append(지금)
            continue
        if 줄.startswith("## 다 채운 뒤"):
            다채운뒤부터 = i
            지금 = None
            continue

        if SS.제안줄인가(줄) and 지금 is not None:
            칸 = 칸나눔(줄)
            지금["제안들"].append({
                "줄": i, "종류": 칸[1].strip(), "무엇": 칸[2].strip(),
                "근거": 칸[3].strip(), "판정": 칸[4].strip(),
                "X이유": 칸[5].strip()})
            continue

        if _놓친것줄 in 줄 and 지금 is not None:
            지금["놓친것줄"] = i
            continue
        if _종류줄 in 줄 and "→" in 줄 and 지금 is not None:
            지금["종류줄"] = i
            continue

        칸 = 칸나눔(줄)
        if len(칸) >= 3 and 칸[1].strip() in ("회의", "종류", "이유"):
            표머리 = 줄
            continue
        if 다채운뒤부터 is None:
            continue
        if len(칸) == 5 and 칸[1].strip().startswith("26.") \
                and "놓친 것이 있나" in 표머리:
            놓친표[칸[1].strip()] = i
        elif len(칸) == 4 and 칸[1].strip().strip("`") in X이유들 \
                and "이유" in 표머리:
            X이유줄[칸[1].strip().strip("`")] = i
        elif len(칸) == 5 and 칸[1].strip() in ("논의", "새 업무", "결정사항", "합계") \
                and "종류" in 표머리:
            종류줄[칸[1].strip()] = i
        elif 줄.lstrip().startswith("→ ") and _일판자리 in 줄:
            일판줄 = i

    return {"줄들": 줄들, "회의들": 회의들, "놓친표": 놓친표,
            "종류줄": 종류줄, "X이유줄": X이유줄, "일판줄": 일판줄}


def 일판값(줄: str) -> str:
    """`→ … 중: ______` 에서 사람이 적은 것. `______` 는 빈 것으로 본다."""
    return 줄.split(_일판자리)[-1].strip().strip("_ ")


def 놓친값(줄: str) -> str:
    return 줄.split("→")[-1].strip()


def 종류값(줄: str) -> set[int]:
    """`… → #4 · #7` 에서 번호만. 모르는 글자는 조용히 버리지 않고 무시한다."""
    return {int(x) for x in re.findall(r"#(\d+)", 줄.split("→")[-1])}


def 종류글(번호들: set[int]) -> str:
    return " · ".join(f"#{n}" for n in sorted(번호들))


# ==========================================================================
# 「놓친 것」 이 이미 낸 제안과 닮았나
# ==========================================================================

# **막지 않는다. 말만 한다.** 「그 논의로는 부족하다」 는 판단일 수 있어서
# 겹쳐 적는 것이 틀린 것이 아니다. 다만 **그렇게 판단한 것인지 모르고 적은
# 것인지**가 갈려야 한다 — 2판에서 그 둘이 구별되지 않아 「놓친 것 4건」 이
# 실제로는 2건일 수도 있는 상태가 됐다.
# **`제작` 은 넣지 않았다.** 이 저장소에서 흔하기는 하지만 뜻을 지고 있어서
# (`큐시트 제작` 과 `현수막 제작` 은 다른 일이다), 빼면 「큐시트 제작 업무가
# 필요」 가 「큐시트 제작」 과 안 닮은 것이 된다.
#
# **조사가 낱말로 세어졌다.** 어절을 통째로 뽑으므로 `헤브론으로` 에서
# `으로` 가 떨어져 나오지 않는데, 그 조각이 `자체적으로` 안에도 있어서
# 두 글이 `으로` 하나로 이미 겹친 것이 된다. 여기에 사람 이름 하나가
# 더해지면 낱말 둘이 되어, 상관없는 제안이 닮은 것으로 잡힌다.
# 조사는 뜻을 지지 않으므로 뺀다.
_조사 = {"으로", "에게", "에서", "이나", "라고", "부터", "까지", "처럼",
       "보다", "한테", "께서", "이랑", "하고", "이고", "인지", "인가",
       "대해", "위한"}
_흔한낱말 = {"업무", "내용", "확인", "진행", "관련", "필요", "전체", "담당",
          "상위", "총무팀", "논의", "수련회", "하기", "한다"} | _조사


def _낱말(글: str) -> list[str]:
    return [w for w in re.findall(r"[가-힣]{2,}|[A-Za-z]{2,}", 글)
            if w not in _흔한낱말]


def _두글자(글: str) -> set[str]:
    민글 = re.sub(r"[^가-힣A-Za-z0-9]", "", 글)
    return {민글[i:i + 2] for i in range(len(민글) - 1)} or {민글}


def 닮았나(가: str, 나: str) -> tuple[bool, float, list[str]]:
    """**두 가지로 본다** — 글자가 거의 같거나(`도착이벤트 안내 필요` ↔
    `도착이벤트 안내 — 총무팀`), 뜻 있는 낱말이 둘 이상 겹치거나
    (`찬양관련 자료는 헤브론으로 전달` ↔ `외부강사 설교·찬양 PPT 전달`).

    한 가지로는 못 잡는다 — 앞엣것은 낱말이 둘밖에 안 겹치고 뒤엣것은
    글자 겹침이 0.15 다. 실제로 2판에서 사람이 겹쳐 적은 둘이 각각
    한쪽씩입니다.
    """
    A, B = _두글자(가), _두글자(나)
    점 = len(A & B) / max(1, min(len(A), len(B)))
    겹친 = set()
    for x in _낱말(가):
        for y in _낱말(나):
            if x == y or x in y or y in x:
                겹친.add(min(x, y, key=len))
    return (점 >= 0.5 or len(겹친) >= 2), round(점, 2), sorted(겹친)


def 토막내기(글: str) -> list[str]:
    """`1. 가, 2. 나` 처럼 여럿을 한 칸에 적는다. 하나씩 견줘야 한다."""
    조각 = re.split(r"\s*\d+\.\s*|[,·]\s*", 글)
    return [x.strip() for x in 조각 if len(x.strip()) >= 4]


def 닮은것(놓친글: str, 제안들: list[dict]) -> list[dict]:
    난것: list[dict] = []
    for 토막 in 토막내기(놓친글):
        for 자리, 제안 in enumerate(제안들, 1):
            맞나, 점, 겹친 = 닮았나(토막, 제안["무엇"])
            if 맞나:
                난것.append({"토막": 토막, "자리": 자리, "제안": 제안["무엇"],
                           "종류": 제안["종류"], "판정": 제안["판정"],
                           "점": 점, "겹친낱말": 겹친})
    return 난것


# ==========================================================================
# 걸음 — 제안 하나 · 회의 끝의 「놓친 것」 · 마지막의 `03.29 #1`
# ==========================================================================

def 걸음들(상태: dict) -> list[dict]:
    """**「놓친 것」 을 회의가 바뀌는 자리에 끼워 넣는다.**

    그 회의의 제안을 다 본 뒤라야 답할 수 있다. 따로 떨어진 화면에 두면
    스무남은 개를 다 본 뒤에 네 회의를 되짚어야 한다.
    """
    걸음: list[dict] = []
    줄들 = 상태["줄들"]
    번호 = 0
    for 회의 in 상태["회의들"]:
        아쉬움 = (종류값(줄들[회의["종류줄"]])
               if 회의["종류줄"] is not None else set())
        for 자리, 제안 in enumerate(회의["제안들"], 1):
            번호 += 1
            걸음.append({"갈래": "제안", "회의": 회의["제목"],
                       "짧은제목": 회의["짧은제목"], "날짜": 회의["날짜"],
                       "자리": 자리, "회의개수": len(회의["제안들"]),
                       "번호": 번호, "종류줄": 회의["종류줄"],
                       "종류아쉬움": 자리 in 아쉬움, **제안})
        if 회의["놓친것줄"] is not None:
            표줄 = 상태["놓친표"].get(회의["짧은제목"])
            칸 = 칸나눔(줄들[표줄]) if 표줄 is not None else []
            걸음.append({
                "갈래": "놓친것", "회의": 회의["제목"],
                "짧은제목": 회의["짧은제목"], "날짜": 회의["날짜"],
                "줄": 회의["놓친것줄"], "표줄": 표줄,
                "값": 놓친값(줄들[회의["놓친것줄"]]),
                "무엇": (칸[3].strip() if len(칸) == 5 else ""),
                # **그 회의에서 낸 것을 함께 들고 간다.** 안 보여 주면
                # 이미 낸 것을 또 적게 된다 — 사람 잘못이 아니라 화면
                # 잘못이다. 2판에서 실제로 그렇게 됐다.
                "제안들": [{"자리": i, "종류": x["종류"], "무엇": x["무엇"],
                         "판정": x["판정"]}
                        for i, x in enumerate(회의["제안들"], 1)],
                "회의개수": len(회의["제안들"])})
    if 상태["일판줄"] is not None:
        걸음.append({"갈래": "일판", "줄": 상태["일판줄"],
                   "값": 일판값(줄들[상태["일판줄"]])})
    return 걸음


def 채워졌나(걸음: dict) -> bool:
    if 걸음["갈래"] == "제안":
        return bool(걸음["판정"])
    return bool(걸음["값"])


# ==========================================================================
# 회의록 원문 — 운영 DB 에서 읽기만 한다
# ==========================================================================

def 회의록들() -> dict[str, dict]:
    """제목 -> 그 회의의 원문.

    **같은 제목의 회의록이 여럿이다.** 같은 날 부서별로 적은 것이 각각
    들어와 있어서, `26.07.05` 는 두 건(`03-예배사역팀리더` 51자 ·
    `04-총무팀` 641자)이다. `suggest_sample.py` 는 `.first()` 로 **첫째만**
    보고 제안을 냈으므로 **채점도 첫째를 봐야 한다** — 나중 것을 보여주면
    제안이 보지도 않은 글로 채점하게 된다.

    그래도 **나머지가 있다는 사실은 숨기지 않는다.** 「이 근거가 회의록에
    없다」 가 제안이 못 읽어서인지 애초에 그 글을 안 봐서인지가 갈린다.
    """
    db = SessionLocal()
    try:
        r = db.scalars(select(Retreat).where(Retreat.name == 회차이름)).first()
        if r is None:
            return {}
        본문: dict[str, dict] = {}
        for m in db.scalars(select(Meeting).where(Meeting.retreat_id == r.id)):
            자리 = 본문.setdefault(m.title, {"본문": "", "출처": "", "다른것": []})
            if not 자리["본문"] and not 자리["출처"]:
                자리["본문"] = m.body or ""
                자리["출처"] = m.source_ref or ""
            else:
                자리["다른것"].append({"출처": m.source_ref or "",
                                   "본문": m.body or ""})
        return 본문
    finally:
        db.close()


# ==========================================================================
# 근거로 인용된 대목을 원문에서 찾기
# ==========================================================================

_인용꼴 = [re.compile(r"`([^`]+)`"), re.compile(r"'([^']+)'"),
        re.compile(r"「([^」]+)」"), re.compile("[\"“]([^\"”]+)[\"”]")]


def 인용조각(근거: str) -> list[str]:
    """근거 안에서 **원문을 옮긴 것으로 보이는 대목**만 뽑는다."""
    나온것: list[str] = []
    for 꼴 in _인용꼴:
        for m in 꼴.finditer(근거):
            조각 = m.group(1).strip()
            if len(조각) >= 4 and 조각 not in 나온것:
                나온것.append(조각)
    return 나온것


def _정규(글: str) -> tuple[str, list[int]]:
    """공백을 하나로 줄인 글과, 그 글자가 원문 몇 번째였는지."""
    낸글: list[str] = []
    자리: list[int] = []
    앞이공백 = False
    for i, 글자 in enumerate(글):
        if 글자.isspace():
            if 앞이공백:
                continue
            낸글.append(" ")
            자리.append(i)
            앞이공백 = True
        else:
            낸글.append(글자)
            자리.append(i)
            앞이공백 = False
    return "".join(낸글), 자리


def 찾는다(본문: str, 조각: str) -> dict:
    """**못 찾으면 못 찾았다고 말한다.** 조용히 넘어가지 않는다 —
    근거가 회의록에 없다는 것 자체가 채점에 쓸 정보다 (1판에서 일곱 중 넷).
    """
    본문정규, 자리 = _정규(본문)
    for 찾을것 in (조각, 조각.replace("｜", "|")):   # `칸글()` 이 바꿔 둔 세로줄
        찾을정규, _ = _정규(찾을것)
        찾을정규 = 찾을정규.strip()
        if not 찾을정규:
            continue
        시작 = 본문정규.find(찾을정규)
        if 시작 >= 0:
            return {"조각": 조각, "상태": "찾음",
                   "처음": 자리[시작], "끝": 자리[시작 + len(찾을정규) - 1] + 1}
    # 모델이 `…` 로 줄여 인용한 것 — 앞부분만이라도 짚는다
    if "…" in 조각 or "..." in 조각:
        토막 = [x.strip() for x in re.split("…|\\.\\.\\.", 조각)]
        for x in sorted([x for x in 토막 if len(x) >= 4], key=len, reverse=True):
            찾을정규, _ = _정규(x)
            찾을정규 = 찾을정규.strip()
            시작 = 본문정규.find(찾을정규)
            if 시작 >= 0:
                return {"조각": 조각, "상태": "부분", "짚은것": x,
                       "처음": 자리[시작],
                       "끝": 자리[시작 + len(찾을정규) - 1] + 1}
    return {"조각": 조각, "상태": "못찾음"}


def 원문칠하기(본문: str, 짚은것: list[dict]) -> str:
    """찾은 대목에 `<mark>` 를 두른 HTML. 겹치면 합친다."""
    구간 = sorted([(x["처음"], x["끝"]) for x in 짚은것 if "처음" in x])
    합친것: list[list[int]] = []
    for 처음, 끝 in 구간:
        if 합친것 and 처음 <= 합친것[-1][1]:
            합친것[-1][1] = max(합친것[-1][1], 끝)
        else:
            합친것.append([처음, 끝])
    낸글: list[str] = []
    앞 = 0
    for 처음, 끝 in 합친것:
        낸글.append(html.escape(본문[앞:처음]))
        낸글.append("<mark>" + html.escape(본문[처음:끝]) + "</mark>")
        앞 = 끝
    낸글.append(html.escape(본문[앞:]))
    return "".join(낸글)


# ==========================================================================
# 세기 — 「다 채운 뒤」
# ==========================================================================

def 센다(상태: dict) -> dict:
    """**1판 수치와 종류 이름은 `suggest_sample.py` 에서 가져온다**
    (`SS.일판` · `SS.일판합계` · `SS.제안종류`). 여기서 다시 적으면 두 벌이 된다.

    다만 **채워진 판정을 세는 코드는 저장소에 없었다** — `다채운뒤()` 는
    빈 표를 만드는 함수라 채점 결과를 세지 않는다. 그래서 세는 것만 여기
    있고, 견줄 1판 값과 표의 모양은 그대로 가져다 쓴다.
    """
    종류순 = list(SS.제안종류.values())
    셈 = {이름: {"O": 0, "X": 0, "?": 0, "총": 0} for 이름 in 종류순}
    X이유셈 = {이유: 0 for 이유 in X이유들}
    for 회의 in 상태["회의들"]:
        for 제안 in 회의["제안들"]:
            칸 = 셈.setdefault(제안["종류"], {"O": 0, "X": 0, "?": 0, "총": 0})
            칸["총"] += 1
            if 제안["판정"] in 판정들:
                칸[제안["판정"]] += 1
            if 제안["X이유"] in X이유셈:
                X이유셈[제안["X이유"]] += 1
    총 = sum(x["총"] for x in 셈.values())
    O = sum(x["O"] for x in 셈.values())
    채운수 = sum(x["O"] + x["X"] + x["?"] for x in 셈.values())
    # **백분율은 여기서 한 번만 만든다.** 화면이 따로 `Math.round` 를 돌리면
    # 파이썬의 `round`(짝수 쪽으로)와 갈린다 — 분모 8에서 `1/8` 이 파일 12% ·
    # 화면 13% 로 실제로 어긋났다. 사람은 화면을 보고 채점을 마치는데 성적표로
    # 옮겨 적히는 것은 파일 쪽이라, **어느 쪽이 틀렸는지 아무도 안 본다.**
    비율 = {이름: 비율글(칸["O"], 칸["총"]) for 이름, 칸 in 셈.items()}
    일판비율 = {이름: 비율글(*값) for 이름, 값 in SS.일판.items()}
    놓친 = []
    for 회의 in 상태["회의들"]:
        표줄 = 상태["놓친표"].get(회의["짧은제목"])
        칸 = 칸나눔(상태["줄들"][표줄]) if 표줄 is not None else []
        놓친.append({"회의": 회의["짧은제목"],
                   "값": (놓친값(상태["줄들"][회의["놓친것줄"]])
                        if 회의["놓친것줄"] is not None else ""),
                   "무엇": (칸[3].strip() if len(칸) == 5 else "")})
    return {"종류": 셈, "종류순": 종류순, "X이유": X이유셈, "놓친": 놓친,
            "총": 총, "O": O, "채운수": 채운수,
            "비율": 비율, "합계비율": 비율글(O, 총),
            "일판": SS.일판, "일판비율": 일판비율,
            "일판합계": list(SS.일판합계), "일판합계비율": 비율글(*SS.일판합계)}


def 비율글(맞: int, 전: int) -> str:
    return f"{맞}/{전} ({round(맞 * 100 / 전)}%)" if 전 else "—"


# ==========================================================================
# 파일 쓰기 — 누를 때마다 바로. 처음 쓰기 전에 백업.
# ==========================================================================

# **읽기부터 쓰기까지가 한 덩어리다.** 줄 번호를 읽어 두고 그 줄에 쓰는데,
# 그 사이에 다른 요청이 끼면 방금 읽은 자리에 대고 쓰게 된다. 재진입
# 자물쇠인 것은 `채운다()` 가 안에서 `마무리표()` → `쓴다()` 를 부르기 때문이다.
_자물쇠 = threading.RLock()
_백업함: list[pathlib.Path] = []


def 백업한다(길: pathlib.Path) -> pathlib.Path:
    """**첫 쓰기 전에 한 번.** 파일을 망가뜨리면 낸 것을 다시 낼 수 없다 —
    Claude 가 낸 것이라 다시 부르면 같은 것이 나오지 않는다.
    """
    if _백업함:
        return _백업함[0]
    갈곳 = 길.with_name(f"{길.stem}.{dt.datetime.now():%Y%m%d-%H%M%S}.bak")
    shutil.copy2(길, 갈곳)
    _백업함.append(갈곳)
    return 갈곳


def 칸바꿈(줄: str, 몇번째: int, 값: str) -> str:
    """표 한 줄에서 그 칸만 갈아 끼운다. 나머지 칸은 글자 하나 안 건드린다."""
    칸 = 칸나눔(줄)
    칸[몇번째] = f" {값} " if 값 else " "
    return "|".join(칸)


def 쓴다(길: pathlib.Path, 고침: list[tuple[int, str]]) -> None:
    with _자물쇠:
        백업한다(길)
        글 = 길.read_text(encoding="utf-8")
        끝맺음 = "\n" if 글.endswith("\n") else ""
        줄들 = 글.splitlines()
        for 줄번호, 새줄 in 고침:
            줄들[줄번호] = 새줄
        임시 = 길.with_suffix(길.suffix + ".tmp")
        임시.write_text("\n".join(줄들) + 끝맺음, encoding="utf-8")
        임시.replace(길)


def 채운다(길: pathlib.Path, 걸음번호: int, 값: dict) -> None:
    with _자물쇠:
        _채운다(길, 걸음번호, 값)


def _채운다(길: pathlib.Path, 걸음번호: int, 값: dict) -> None:
    상태 = 읽는다(길.read_text(encoding="utf-8"))
    걸음 = 걸음들(상태)
    if not (0 <= 걸음번호 < len(걸음)):
        raise ValueError(f"없는 자리입니다: {걸음번호}")
    이것 = 걸음[걸음번호]
    줄들 = 상태["줄들"]
    고침: list[tuple[int, str]] = []

    if 이것["갈래"] == "제안":
        판정 = (값.get("판정") or "").strip()
        이유 = (값.get("X이유") or "").strip()
        if 판정 and 판정 not in 판정들:
            raise ValueError(f"모르는 판정입니다: {판정!r}")
        if 이유 and 이유 not in X이유들:
            raise ValueError(f"모르는 X 이유입니다: {이유!r}")
        if 판정 != "X":
            # **X 가 아니면 이유를 남기지 않는다.** O 로 고쳤는데 이유가
            # 남아 있으면 세는 곳마다 수가 갈린다
            이유 = ""
        줄 = 칸바꿈(줄들[이것["줄"]], 4, 판정)
        고침.append((이것["줄"], 칸바꿈(줄, 5, 이유)))

        # **「종류가 아쉽다」 는 판정과 따로다.** 「맞나」 와 「산출물이
        # 맞나」 는 다른 물음이라 O 를 주면서도 아쉬울 수 있다. 표에 칸을
        # 더하지 않고 회의마다 한 줄에 번호로 모은다 — 제안 줄이 7칸이
        # 아니게 되면 `제안줄인가()` 가 못 알아보고, 그러면 **덮어쓰기
        # 가드가 사람이 채운 판정을 안 지킨다.**
        if "종류아쉬움" in 값 and 이것["종류줄"] is not None:
            번호들 = 종류값(줄들[이것["종류줄"]])
            번호들 = (번호들 | {이것["자리"]}) if 값["종류아쉬움"]                 else (번호들 - {이것["자리"]})
            머리 = 줄들[이것["종류줄"]].split("→")[0]
            고침.append((이것["종류줄"], f"{머리}→ {종류글(번호들)}".rstrip()
                       if 번호들 else f"{머리}→ "))

    elif 이것["갈래"] == "놓친것":
        답 = (값.get("값") or "").strip()
        무엇 = SS.칸글((값.get("무엇") or "").strip())
        if 답 and 답 not in ("O", "X"):
            raise ValueError(f"모르는 답입니다: {답!r}")
        머리 = 줄들[이것["줄"]].split("→")[0]
        # **비우면 원래 모양 그대로 돌아간다.** 끝의 빈칸을 털어 내면
        # 지웠는데도 파일에 diff 가 남아, 무엇을 고친 것인지 흐려진다
        고침.append((이것["줄"], f"{머리}→ {답}"))
        # **같은 사실이 두 자리에 있다** — 회의 끝의 줄과 「다 채운 뒤」 의
        # 표. 서식이 원래 그렇다. 한쪽만 채우면 읽는 사람이 서로 다른
        # 말을 보게 되므로 **한 번 눌러 둘 다 채운다.**
        if 이것["표줄"] is not None:
            줄 = 칸바꿈(줄들[이것["표줄"]], 2, 답)
            고침.append((이것["표줄"], 칸바꿈(줄, 3, 무엇)))

    else:   # 일판
        답 = (값.get("값") or "").strip()
        if 답 and 답 not in X이유들:
            raise ValueError(f"모르는 이유입니다: {답!r}")
        머리 = 줄들[이것["줄"]].split(_일판자리)[0]
        고침.append((이것["줄"], f"{머리}{_일판자리}{답 or '______'}"))

    쓴다(길, 고침)
    마무리표(길)


def 마무리표(길: pathlib.Path) -> bool:
    """**다 채웠을 때만** 「다 채운 뒤」 의 셈한 표를 채운다.

    반쯤 채운 수를 적어 두면 그것이 최종 결과처럼 읽힌다.

    **그리고 다 채웠다가 하나를 비우면 도로 걷어낸다.** 적기만 하고
    되돌리지 않으면 `27/27 (100%)` 이 26개만 채운 파일에 그대로 남는다 —
    화면은 매번 다시 세어 맞고 **파일만 틀리는데, 성적표로 옮겨 적히는
    것은 파일 쪽이다.** 「다 채웠을 때만」 이라는 규칙이 그 '언제' 가 아닌
    때에 조용히 뚫리는 자리다 (11-3).
    """
    with _자물쇠:
        return _마무리표(길)


def _마무리표(길: pathlib.Path) -> bool:
    상태 = 읽는다(길.read_text(encoding="utf-8"))
    셈 = 센다(상태)
    다채움 = 셈["총"] > 0 and 셈["채운수"] >= 셈["총"]
    줄들 = 상태["줄들"]
    고침: list[tuple[int, str]] = []
    for 이름, 줄번호 in 상태["종류줄"].items():
        if 이름 == "합계":
            글, 물음, 전 = 셈["합계비율"], sum(
                x["?"] for x in 셈["종류"].values()), 셈["총"]
        else:
            칸 = 셈["종류"].get(이름)
            if not 칸:
                continue
            글, 물음, 전 = 셈["비율"][이름], 칸["?"], 칸["총"]
        # 다 안 채웠으면 **생성기가 낸 빈 모양**(`/ N`)으로 되돌린다
        값 = (글 + (f" · ?{물음}" if 물음 else "")) if 다채움 else f"/ {전}"
        고침.append((줄번호, 칸바꿈(줄들[줄번호], 3, 값)))
    for 이유, 줄번호 in 상태["X이유줄"].items():
        고침.append((줄번호, 칸바꿈(줄들[줄번호], 2,
                                str(셈["X이유"][이유]) if 다채움 else "")))
    # **안 바뀌는 줄은 건드리지 않는다.** 누를 때마다 같은 글자를 다시
    # 써 넣으면 파일이 바뀐 때를 알 수 없다
    고침 = [(n, s) for n, s in 고침 if s != 줄들[n]]
    if 고침:
        쓴다(길, 고침)
    return 다채움


# ==========================================================================
# 화면에 넘길 것
# ==========================================================================

def 상태전부(길: pathlib.Path, 본문들: dict[str, dict]) -> dict:
    상태 = 읽는다(길.read_text(encoding="utf-8"))
    걸음 = 걸음들(상태)
    낼것 = []
    for 걸 in 걸음:
        하나 = dict(걸)
        if 걸["갈래"] in ("제안", "놓친것"):
            쪽 = 본문들.get(걸["회의"]) or {"본문": "", "출처": "", "다른것": []}
            본문 = 쪽["본문"]
            하나["원문없음"] = not 본문
            하나["출처"] = 쪽["출처"]
            하나["다른것"] = [{"출처": x["출처"], "원문": html.escape(x["본문"])}
                          for x in 쪽["다른것"]]
            if 걸["갈래"] == "제안":
                짚은것 = [찾는다(본문, x) for x in 인용조각(걸["근거"])]
                하나["원문"] = 원문칠하기(본문, 짚은것)
                하나["짚은것"] = 짚은것
            else:
                하나["원문"] = html.escape(본문)
                하나["짚은것"] = []
                하나["닮은것"] = 닮은것(걸["무엇"], 걸["제안들"])
        하나["채움"] = 채워졌나(걸)
        낼것.append(하나)
    첫빈칸 = next((i for i, x in enumerate(낼것) if not x["채움"]),
                max(0, len(낼것) - 1))
    return {"걸음": 낼것, "첫빈칸": 첫빈칸, "셈": 센다(상태),
            "백업": (str(_백업함[0]) if _백업함 else None),
            "파일": str(길)}


# ==========================================================================
# 서버 — 운영 앱과 아무 것도 나누지 않는다
# ==========================================================================

화면 = """<!doctype html>
<meta charset="utf-8">
<title>제안 채점</title>
<style>
:root{--ink:#37352F;--ink2:#6E6D6A;--ink3:#83827F;--line:rgba(55,53,47,.09);
      --sel:#2383E2;--red:#C4554D;--mark:#FAF1D2;--face:#F7F7F5}
*{box-sizing:border-box}
/* **머리와 발은 늘 보인다** — 어디까지 했는지와 누를 단추가 스크롤로
   사라지면, 스무남은 개를 넘기는 동안 매번 아래로 내려가야 한다. 그래서 창을
   꽉 채우고 **가운데 두 칸만** 스크롤한다. */
html,body{height:100%}
body{margin:0;font:15px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Pretendard,
     "Malgun Gothic",sans-serif;color:var(--ink);background:#fff;
     display:flex;flex-direction:column;overflow:hidden}
header{flex:none;background:#fff;border-bottom:1px solid var(--line);
       padding:10px 16px;display:flex;gap:16px;align-items:baseline;flex-wrap:wrap;z-index:2}
h1{font-size:17px;margin:0;font-weight:600}
.meta{color:var(--ink2);font-size:13px}
.bar{flex:1 1 160px;height:6px;background:var(--face);border-radius:3px;overflow:hidden;
     min-width:120px}
.bar i{display:block;height:100%;background:var(--sel)}
main{flex:1;min-height:0;display:grid;
     grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:0}
section{padding:16px;overflow-y:auto;min-height:0}
section+section{border-left:1px solid var(--line);background:var(--face)}
h2{font-size:13px;font-weight:600;color:var(--ink2);margin:0 0 10px;
   letter-spacing:.02em}
.kind{display:inline-block;font-size:12px;color:var(--ink2);border:1px solid var(--line);
      border-radius:3px;padding:1px 7px;margin-bottom:8px}
.what{font-size:17px;font-weight:600;line-height:1.45}
.why{margin-top:12px;color:var(--ink);white-space:pre-wrap}
.why b{color:var(--ink2);font-weight:600;font-size:13px;display:block;margin-bottom:4px}
pre.body{white-space:pre-wrap;font:14px/1.7 ui-monospace,"Malgun Gothic",monospace;
     background:#fff;border:1px solid var(--line);border-radius:4px;padding:12px;margin:0}
mark{background:var(--mark);padding:1px 0}
.quotes{margin-top:12px;font-size:13px}
.q{padding:6px 8px;border-radius:4px;margin-bottom:4px;border:1px solid var(--line)}
.q.ok{color:var(--ink2)}
.q.no{border-color:var(--red);color:var(--red);background:#fff}
.q.part{border-color:#B8860B;color:#8A6A0B;background:#fff}
footer{flex:none;background:#fff;border-top:1px solid var(--line);
       padding:12px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button{font:inherit;padding:7px 14px;border:1px solid var(--line);background:#fff;
       border-radius:4px;cursor:pointer;color:var(--ink)}
button:hover{background:rgba(55,53,47,.06)}
button.big{font-size:17px;font-weight:600;min-width:56px}
button.on{border-color:var(--sel);box-shadow:inset 0 0 0 1px var(--sel);color:var(--sel)}
button.on.x{border-color:var(--red);box-shadow:inset 0 0 0 1px var(--red);color:var(--red)}
input[type=text]{font:inherit;padding:7px 10px;border:1px solid var(--line);
       border-radius:4px;min-width:260px;flex:1 1 260px}
.sp{flex:1}
.note{color:var(--ink2);font-size:13px}
.warn{color:var(--red);font-size:13px}
table{border-collapse:collapse;font-size:14px;margin:8px 0 16px}
th,td{border:1px solid var(--line);padding:5px 10px;text-align:left}
th{color:var(--ink2);font-weight:600;font-size:13px}
@media (max-width:900px){
  body{overflow:auto}
  main{display:block}
  section{overflow:visible}
  section+section{border-left:0;border-top:1px solid var(--line)}
  header{position:sticky;top:0}
  footer{position:sticky;bottom:0}}
</style>
<header>
  <h1 id="hd">…</h1>
  <span class="meta" id="pos"></span>
  <span class="bar"><i id="barfill" style="width:0"></i></span>
  <span class="meta" id="left"></span>
</header>
<main>
  <section id="left-pane"></section>
  <section id="right-pane"></section>
</main>
<footer id="foot"></footer>
<script>
let S=null, i=0, 그린자리=-1;
const E=s=>document.createElement(s);
const esc=s=>String(s??"").replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

async function load(first){
  S=await (await fetch('/api/state')).json();
  if(first) i=S.첫빈칸;
  draw();
}
async function save(값){
  const r=await fetch('/api/save',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({자리:i,값:값})});
  const j=await r.json();
  if(!j.ok){alert('저장하지 못했습니다: '+j.말);return;}
  S=j.상태; draw();
}
function go(d){ i=Math.max(0,Math.min(S.걸음.length-1,i+d)); draw(); }

function draw(){
  const g=S.걸음[i], 셈=S.셈;
  const 채운제안=셈.채운수, 총=셈.총;
  document.getElementById('barfill').style.width=(총?채운제안/총*100:0)+'%';
  document.getElementById('left').textContent=
    총-채운제안>0 ? (총-채운제안)+'개 남음' : '판정 다 채웠습니다';
  const hd=document.getElementById('hd'), pos=document.getElementById('pos');
  if(g.갈래==='제안'){
    hd.textContent=g.회의;
    pos.textContent='이 회의 '+g.자리+'/'+g.회의개수+' · 전체 '+g.번호+'/'+총;
  }else if(g.갈래==='놓친것'){
    hd.textContent=g.회의+' — 놓친 것';
    pos.textContent='이 회의 제안 '+g.회의개수+'개를 다 봤습니다';
  }else{
    hd.textContent='1판의 03.29 #1 — X 이유';
    pos.textContent='마지막 자리';
  }
  drawLeft(g); drawRight(g); drawFoot(g);
  // **자리를 옮길 때만** 두 칸을 맨 위로 올린다. 앞 제안에서 내려 읽던
  // 자리가 그대로 남으면 다음 제안의 첫 줄을 지나치지만, 누를 때마다
  // 올라가면 회의록을 내려 읽다가 O 를 누른 순간 읽던 곳을 잃는다.
  if(그린자리!==i){
    document.getElementById('left-pane').scrollTop=0;
    document.getElementById('right-pane').scrollTop=0;
    그린자리=i;
  }
}

function drawLeft(g){
  const p=document.getElementById('left-pane'); p.innerHTML='';
  if(g.갈래==='제안'){
    p.innerHTML='<h2>제안</h2>'
      +'<div class="kind">'+esc(g.종류)+'</div>'
      +'<div class="what">'+esc(g.무엇)+'</div>'
      +'<div class="why"><b>근거 / 인용</b>'+esc(g.근거)+'</div>';
    const q=E('div'); q.className='quotes';
    if(!g.짚은것.length){
      q.innerHTML='<div class="q no">근거에 <b>인용된 대목이 없습니다</b> — '
        +'문장뿐입니다. 회의록에서 직접 확인하세요.</div>';
    }else{
      g.짚은것.forEach(x=>{
        const d=E('div');
        if(x.상태==='찾음'){d.className='q ok';
          d.textContent='회의록에서 찾았습니다 · 「'+x.조각+'」';}
        else if(x.상태==='부분'){d.className='q part';
          d.textContent='일부만 찾았습니다 (「'+x.짚은것+'」) · 인용: 「'+x.조각+'」';}
        else{d.className='q no';
          d.textContent='회의록에서 못 찾았습니다 · 「'+x.조각+'」';}
        q.appendChild(d);
      });
    }
    p.appendChild(q);
  }else if(g.갈래==='놓친것'){
    let h='<h2>놓친 것</h2>'
      +'<div class="what">마땅히 나왔어야 하는데 안 나온 것이 있나요?</div>'
      +'<div class="why">이 칸이 없으면 <b style="display:inline">적게 내는 '
      +'쪽으로 점수를 올릴 수 있습니다.</b></div>';
    // **이 회의에서 낸 것을 함께 보여 준다.** 안 보여 주면 이미 낸 것을
    // 또 적게 된다 — 2판에서 실제로 그렇게 됐고, 사람 잘못이 아니라
    // 화면 잘못이다.
    h+='<h2 style="margin-top:16px">이 회의에서 낸 것 '+g.제안들.length+'개</h2>';
    if(!g.제안들.length){
      h+='<div class="q no">이 회의는 <b>낸 것이 없습니다.</b> '
        +'그러니 여기 적는 것은 전부 놓친 것입니다.</div>';
    }else{
      h+='<table><tr><th>#</th><th>종류</th><th>무엇을 하자는 것</th>'
        +'<th>판정</th></tr>';
      g.제안들.forEach(x=>{h+='<tr><td>'+x.자리+'</td><td>'+esc(x.종류)+'</td><td>'
        +esc(x.무엇)+'</td><td>'+esc(x.판정||'—')+'</td></tr>';});
      h+='</table>';
    }
    (g.닮은것||[]).forEach(x=>{
      h+='<div class="q part">적으신 「'+esc(x.토막)+'」 이(가) <b>#'+x.자리
        +' '+esc(x.제안)+'</b> 와(과) 닮았습니다'
        +(x.겹친낱말.length?' (겹친 낱말: '+esc(x.겹친낱말.join(', '))+')':'')
        +'. <b>막지 않습니다</b> — 「그 제안으로는 부족하다」 는 판단이면 '
        +'그대로 두세요.</div>';
    });
    p.innerHTML=h;
  }else{
    p.innerHTML='<h2>1판의 03.29 #1</h2>'
      +'<div class="what">넷 중 하나로 정해 주세요.</div>'
      +'<div class="why">1판 성적표가 그것을 「같은 모양」 넷에 넣지 않고 '
      +'이름만 적어 두었습니다 — 사람이 그렇게 분류한 것이 아니어서입니다.</div>';
    p.appendChild(summary());
  }
}

function drawRight(g){
  const p=document.getElementById('right-pane'); p.innerHTML='';
  if(g.갈래==='일판'){ p.innerHTML='<h2>다 채운 뒤</h2>'; p.appendChild(summary(true)); return; }
  p.innerHTML='<h2>회의록 원문 — '+esc(g.짧은제목)+' ('+esc(g.날짜)+')'
    +(g.출처?' · '+esc(g.출처):'')+'</h2>';
  const pre=E('pre'); pre.className='body';
  pre.innerHTML=g.원문없음 ? '<span class="warn">이 회의의 원문을 운영 DB '
    +'에서 찾지 못했습니다.</span>' : g.원문;
  p.appendChild(pre);
  (g.다른것||[]).forEach(x=>{
    const h=E('h2'); h.style.marginTop='16px';
    h.innerHTML='같은 제목의 다른 회의록 — '+esc(x.출처)
      +' <span class="warn">제안은 이것을 보지 않고 냈습니다</span>';
    const q=E('pre'); q.className='body'; q.style.opacity='.75';
    q.textContent=x.원문 ? '' : '(빈 회의록)';
    if(x.원문) q.innerHTML=x.원문;
    p.appendChild(h); p.appendChild(q);
  });
}

function summary(전부){
  // **백분율을 여기서 만들지 않는다.** `Math.round` 와 파이썬 `round` 가
  // 갈려서 같은 값이 화면 13% · 파일 12% 로 나온 적이 있다. 서버가 이미
  // 만든 글자(`셈.비율`·`셈.합계비율`)를 그대로 그린다.
  const 셈=S.셈, box=E('div');
  let h='<table><tr><th>종류</th><th>1판 (낱말)</th><th>이번 판 — O</th>'
    +'<th>X</th><th>?</th><th>안 채움</th></tr>';
  let O=0,X=0,Q=0,T=0;
  셈.종류순.forEach(k=>{
    const c=셈.종류[k]||{O:0,X:0,'?':0,총:0};
    O+=c.O;X+=c.X;Q+=c['?'];T+=c.총;
    h+='<tr><td>'+k+'</td>'
      +'<td>'+(셈.일판비율[k]||'(1판에 없던 종류)')+'</td>'
      +'<td>'+esc(셈.비율[k])+'</td>'
      +'<td>'+c.X+'</td><td>'+c['?']+'</td>'
      +'<td>'+(c.총-c.O-c.X-c['?'])+'</td></tr>';
  });
  h+='<tr><td><b>합계</b></td><td>'+셈.일판합계비율+'</td>'
    +'<td><b>'+esc(셈.합계비율)+'</b></td>'
    +'<td>'+X+'</td><td>'+Q+'</td><td>'+(T-O-X-Q)+'</td></tr></table>';
  if(전부){
    h+='<table><tr><th>X 이유</th><th>이번 판</th></tr>';
    Object.keys(셈.X이유).forEach(k=>{h+='<tr><td>'+k+'</td><td>'+셈.X이유[k]+'</td></tr>';});
    h+='</table><table><tr><th>회의</th><th>놓친 것이 있나</th><th>무엇을 놓쳤나</th></tr>';
    셈.놓친.forEach(x=>{h+='<tr><td>'+x.회의+'</td><td>'+esc(x.값||'—')+'</td><td>'
      +esc(x.무엇||'')+'</td></tr>';});
    h+='</table><div class="note">종류별 표와 X 이유 표는 <b>다 채우면</b> '
      +'채점표 파일에도 적힙니다.</div>';
  }
  box.innerHTML=h; return box;
}

function drawFoot(g){
  const f=document.getElementById('foot'); f.innerHTML='';
  if(g.갈래==='제안'){
    ['O','X','?'].forEach(v=>{
      const b=E('button'); b.className='big'+(g.판정===v?' on'+(v==='X'?' x':''):'');
      b.textContent=v;
      b.onclick=()=>save({판정:g.판정===v?'':v,X이유:g.X이유});
      f.appendChild(b);
    });
    const lab=E('span'); lab.className='note'; lab.textContent='X 이유:'; f.appendChild(lab);
    ['다른업무','할일아님','중복','기타'].forEach(v=>{
      const b=E('button'); b.className=(g.X이유===v?'on':'');
      b.textContent=v; b.disabled=(g.판정!=='X');
      b.onclick=()=>save({판정:g.판정,X이유:g.X이유===v?'':v});
      f.appendChild(b);
    });
    // **판정과 따로 둔다.** 「맞나」 와 「산출물이 맞나」 는 다른 물음이라
    // O 를 주면서도 아쉬울 수 있다. 붙여 두면 판정의 넷째 값처럼 읽힌다.
    const 벽=E('span'); 벽.className='note'; 벽.textContent='│'; f.appendChild(벽);
    const 아쉬=E('button');
    아쉬.className=(g.종류아쉬움?'on':'');
    아쉬.textContent='종류가 아쉽다';
    아쉬.title='맞는 얘긴데 논의로 그쳤거나 업무로 갔어야 하는 것. 판정과 따로입니다.';
    아쉬.disabled=(g.종류줄===null);
    아쉬.onclick=()=>save({판정:g.판정,X이유:g.X이유,종류아쉬움:!g.종류아쉬움});
    f.appendChild(아쉬);
  }else if(g.갈래==='놓친것'){
    ['O','X'].forEach(v=>{
      const b=E('button'); b.className='big'+(g.값===v?' on':'');
      b.textContent=v;
      b.onclick=()=>save({값:g.값===v?'':v,무엇:txt.value});
      f.appendChild(b);
    });
    var txt=E('input'); txt.type='text'; txt.value=g.무엇||'';
    txt.placeholder='무엇을 놓쳤나 (적고 O 나 X 를 누르세요)';
    txt.onblur=()=>{ if((g.무엇||'')!==txt.value) save({값:g.값,무엇:txt.value}); };
    f.appendChild(txt);
  }else{
    ['다른업무','할일아님','중복','기타'].forEach(v=>{
      const b=E('button'); b.className='big'+(g.값===v?' on':'');
      b.textContent=v;
      b.onclick=()=>save({값:g.값===v?'':v});
      f.appendChild(b);
    });
  }
  const sp=E('span'); sp.className='sp'; f.appendChild(sp);
  const back=E('button'); back.textContent='← 앞'; back.disabled=(i===0);
  back.onclick=()=>go(-1); f.appendChild(back);
  const next=E('button'); next.textContent='뒤 →';
  next.disabled=(i===S.걸음.length-1); next.onclick=()=>go(1); f.appendChild(next);
}

document.addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT')return;
  if(e.key==='ArrowLeft')go(-1);
  if(e.key==='ArrowRight')go(1);
});
load(true);
</script>
"""


class 손님(http.server.BaseHTTPRequestHandler):
    본문들: dict[str, str] = {}
    길: pathlib.Path = 채점표

    def log_message(self, *_a):        # 콘솔을 요청 로그로 채우지 않는다
        pass

    def _낸다(self, 몸: bytes, 종류: str, 코드: int = 200) -> None:
        self.send_response(코드)
        self.send_header("Content-Type", f"{종류}; charset=utf-8")
        self.send_header("Content-Length", str(len(몸)))
        self.end_headers()
        self.wfile.write(몸)

    def _json(self, 값: dict, 코드: int = 200) -> None:
        self._낸다(json.dumps(값, ensure_ascii=False).encode("utf-8"),
                 "application/json", 코드)

    def do_GET(self) -> None:
        if self.path.startswith("/api/state"):
            self._json(상태전부(self.길, self.본문들))
        elif self.path in ("/", "/index.html"):
            self._낸다(화면.encode("utf-8"), "text/html")
        else:
            self._낸다(b"not found", "text/plain", 404)

    def do_POST(self) -> None:
        if not self.path.startswith("/api/save"):
            self._낸다(b"not found", "text/plain", 404)
            return
        길이 = int(self.headers.get("Content-Length") or 0)
        몸 = self.rfile.read(길이)
        try:
            # **먼저 읽고 나서 답한다.** 몸을 다 안 읽고 끊으면 브라우저에는
            # 응답이 아니라 연결 끊김으로 보인다 — 저장이 안 된 것을
            # 화면이 「저장했다」 로 지나칠 수 있다
            받은것 = json.loads(몸 or b"{}")
        except (UnicodeDecodeError, ValueError) as e:
            self._json({"ok": False, "말": f"보낸 것을 못 읽었습니다: {e}"}, 400)
            return
        try:
            채운다(self.길, int(받은것["자리"]), 받은것.get("값") or {})
        except Exception as e:      # noqa: BLE001 — 화면에 그대로 말한다
            self._json({"ok": False, "말": str(e)}, 400)
            return
        self._json({"ok": True, "상태": 상태전부(self.길, self.본문들)})


def main() -> None:
    ap = argparse.ArgumentParser(description="제안 채점표를 한 화면에 하나씩 채운다")
    ap.add_argument("--file", default=str(채점표))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--열지않기", action="store_true")
    args = ap.parse_args()

    길 = pathlib.Path(args.file)
    if not 길.exists():
        print(f"채점표가 없습니다: {길}")
        print("scripts/suggest_sample.py 로 먼저 만드세요.")
        raise SystemExit(1)

    상태 = 읽는다(길.read_text(encoding="utf-8"))
    걸음 = 걸음들(상태)
    제안수 = sum(len(x["제안들"]) for x in 상태["회의들"])
    if 제안수 == 0:
        # **아무것도 못 읽은 것을 「다 채웠다」 로 보여주지 않는다** —
        # 0을 세고 초록을 내는 것이 이 저장소가 여러 번 겪은 고장이다
        print(f"{길} 에서 제안 줄을 하나도 못 읽었습니다.")
        print("표 모양이 바뀌었는지 보세요 (suggest_sample.py 의 제안줄인가).")
        raise SystemExit(1)

    본문들 = 회의록들()
    없는것 = [x["제목"] for x in 상태["회의들"]
           if not (본문들.get(x["제목"]) or {}).get("본문")]
    겹친것 = [x["제목"] for x in 상태["회의들"]
           if (본문들.get(x["제목"]) or {}).get("다른것")]
    print(f"채점표: {길}")
    print(f"회의 {len(상태['회의들'])}건 · 제안 {제안수}개 · 걸음 {len(걸음)}개")
    if 없는것:
        print("! 원문을 못 찾은 회의:", ", ".join(없는것))
    if 겹친것:
        print("! 같은 제목의 회의록이 여럿인 회의:", ", ".join(겹친것))
        print("  제안을 낼 때 쓴 첫째 것을 위에 놓고, 나머지는 아래에 함께 보입니다.")

    손님.본문들 = 본문들
    손님.길 = 길
    서버 = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), 손님)
    주소 = f"http://127.0.0.1:{args.port}"
    print(f"\n{주소}  (Ctrl+C 로 끝냅니다)")
    if not args.열지않기:
        threading.Timer(0.5, lambda: webbrowser.open(주소)).start()
    try:
        서버.serve_forever()
    except KeyboardInterrupt:
        print("\n끝냅니다.")
    finally:
        서버.server_close()


if __name__ == "__main__":
    main()
