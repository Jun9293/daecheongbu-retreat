# -*- coding: utf-8 -*-
"""노션 업무와 앱 업무의 **짝을 정하고 등급을 매깁니다** (업무 대조 1판 · 2026-09-16 · 사람이 ㄱ2 로 정함).

1판(`data/노션대조.real.py`)은 ① 제목이 같은 것부터 순서대로 ② 남은 것은 닮음이 문턱을 넘는 것부터 1:1 로
이었습니다. 그 방식은 **앞에서 잘못 먹은 짝이 뒤의 더 맞는 짝을 밀어냈고**, 구분이 없는 줄을 통째로 뺐고,
같은 제목이 노션에 여럿이면 앞줄을 먼저 가져갔습니다. 여기는 그 셋을 메웁니다.

- **점수를 다 매긴 뒤 높은 것부터 확정합니다** — 입력 순서가 결과를 바꾸지 않습니다(전역에 가깝게)
- 점수는 제목 닮음에 **구분 · 담당 · 날짜가 맞으면 더해** 정합니다 — 같은 제목이 여럿일 때 날짜 · 담당이
  가까운 줄이 이깁니다
- **구분이 없는 줄도 후보입니다.** 빼는 것은 D-주차 표지뿐입니다(`표지인가`)
- 등급은 **A(자동으로 믿음) · B(사람이 5초 안에 판단) · C(근거가 약함)** 입니다

**이 파일은 값을 안 읽고 안 씁니다** — 셈만 합니다. 값을 읽어 파일로 내는 것은 `data/` 의 실행기입니다
(11-2 의 「운영 DB 를 읽어 만든 것은 `data/*.real.*` 로」).
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
from dataclasses import dataclass

# 제목에서 떼는 글자 — 1판과 같은 목록이다(바꾸면 1판 수와 못 견준다)
_뗄것 = re.compile(r"[\s()\[\]/&·,.\-→’'+:~]")
_표지 = re.compile(r"\(?D-\d+주차\)?$")

구분표 = {"Main": "main", "Sub": "sub", "Sch": "schedule"}
담당표 = {"1 총무M": "chongmuM", "1 총무팀": "chongmu", "2 봉사팀 공통": "(봉사팀공통)", "3 선교사회": "seongyo",
        "4 스케치": "sketch", "5 헤브론": "hebron", "6 코람데오": "koram", "7 재정": "jaejeong",
        "8 개기자": "gaegija", "9 새친구팀": "saechingu"}

닮음문턱 = 0.50      # 이보다 덜 닮으면 후보로 치지 않는다
등급A = 0.93         # 제목이 사실상 같고 나머지도 어긋나지 않는다
등급B = 0.70         # 사람이 보면 곧 판단할 수 있는 자리


def 줄기(제목: str) -> str:
    return _뗄것.sub("", 제목 or "").lower()


def 표지인가(제목: str) -> bool:
    """D-주차 표지 줄인가 — 업무가 아니라 주차를 가르는 머리다."""
    return bool(_표지.fullmatch((제목 or "").strip()))


def 날짜(값) -> dt.date | None:
    if isinstance(값, dt.date):
        return 값
    try:
        return dt.date.fromisoformat(str(값)[:10])
    except (TypeError, ValueError):
        return None


def 제목점수(가: str, 나: str) -> float:
    """제목만 본 닮음 0~1. 한쪽이 다른 쪽을 품으면 짧은 쪽 길이만큼 쳐 준다."""
    x, y = 줄기(가), 줄기(나)
    if not x or not y:
        return 0.0
    r = difflib.SequenceMatcher(None, x, y).ratio()
    if min(len(x), len(y)) >= 3 and (x in y or y in x):
        r = max(r, 0.60 + 0.30 * min(len(x), len(y)) / max(len(x), len(y)))
    return r


def 덤(노션: dict, 앱: dict) -> float:
    """구분 · 담당 · 시작일이 맞으면 더한다 — 같은 제목이 여럿일 때 이것이 가른다."""
    더 = 0.0
    if 노션.get("kind") and 구분표.get(노션["kind"]) == 앱.get("kind"):
        더 += 0.05
    if 노션.get("team") and 담당표.get(노션["team"]) == 앱.get("team"):
        더 += 0.05
    ㄴ, ㅇ = 날짜(노션.get("start")), 날짜(앱.get("start"))
    if ㄴ and ㅇ:
        차 = abs((ㄴ - ㅇ).days)
        더 += 0.06 if 차 == 0 else (0.03 if 차 <= 7 else 0.0)
    return 더


def 점수(노션: dict, 앱: dict) -> tuple[float, float]:
    """(총점, 제목점수). **총점을 1 에서 자르지 않는다** — 제목이 똑같은 줄이 여럿일 때
    자르면 덤이 지워져 날짜 · 담당이 가른 결과가 사라진다(`test55_c01`)."""
    바탕 = 제목점수(노션.get("title", ""), 앱.get("title", ""))
    return (바탕 + 덤(노션, 앱)) if 바탕 else 0.0, 바탕


@dataclass
class 짝:
    노션: int          # 노션 줄 번호(0부터)
    앱: int            # 앱 줄 번호(0부터)
    총점: float
    제목: float
    등급: str


def 등급매김(총점: float, 제목: float) -> str:
    if 제목 >= 등급A and 총점 >= 등급A:
        return "A"
    if 총점 >= 등급B:
        return "B"
    return "C"


def 짝짓는다(노션들: list[dict], 앱들: list[dict], *, 문턱: float = 닮음문턱) -> list[짝]:
    """**점수를 다 매긴 뒤 높은 것부터 확정한다** — 입력 순서가 결과를 안 바꾼다.

    같은 점수면 제목점수 · 줄 번호 순으로 갈라 **같은 자료면 늘 같은 답**이 나온다.
    """
    후보 = []
    for i, n in enumerate(노션들):
        if 표지인가(n.get("title", "")):
            continue
        for j, a in enumerate(앱들):
            총, 바탕 = 점수(n, a)
            if 바탕 >= 문턱:
                후보.append((총, 바탕, -i, -j, i, j))
    후보.sort(reverse=True)
    쓴노션: set[int] = set()
    쓴앱: set[int] = set()
    나온것: list[짝] = []
    for 총, 바탕, _, _, i, j in 후보:
        if i in 쓴노션 or j in 쓴앱:
            continue
        쓴노션.add(i)
        쓴앱.add(j)
        나온것.append(짝(i, j, round(총, 4), round(바탕, 4), 등급매김(총, 바탕)))
    나온것.sort(key=lambda p: (-p.총점, p.노션, p.앱))
    return 나온것


def 네갈래(노션들: list[dict], 앱들: list[dict], 짝들: list[짝]) -> dict[str, int]:
    """짝 밖에 남은 것까지 세어 네 갈래로. 표지는 어느 갈래에도 안 넣는다."""
    쓴노션 = {p.노션 for p in 짝들}
    쓴앱 = {p.앱 for p in 짝들}
    후보노션 = [i for i, n in enumerate(노션들) if not 표지인가(n.get("title", ""))]
    같음 = sum(1 for p in 짝들 if 줄기(노션들[p.노션]["title"]) == 줄기(앱들[p.앱]["title"]))
    return {
        "노션만": sum(1 for i in 후보노션 if i not in 쓴노션),
        "앱만": sum(1 for j in range(len(앱들)) if j not in 쓴앱),
        "둘 다 · 제목 같음": 같음,
        "둘 다 · 제목 다름": len(짝들) - 같음,
        "표지(갈래 밖)": len(노션들) - len(후보노션),
    }


def 등급수(짝들: list[짝]) -> dict[str, int]:
    return {g: sum(1 for p in 짝들 if p.등급 == g) for g in ("A", "B", "C")}
