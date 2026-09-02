"""노션 회의록을 회의 단위로 자른다 (CLAUDE.md 회의록 1단계).

**옮기기는 일회성 이사다.** 앞으로 회의록은 이 프로그램에 적으므로 노션에는
더 쓰지 않는다. 그래서 화면이 아니라 스크립트이고, 자르는 규칙을 여기 도메인에
두어 **시험이 화면 없이 돌 수 있게** 한다.

## 자르는 규칙

원본은 한 페이지 안에 여러 회의가 쌓여 있는 구조다. 회의의 시작은
**빨간 굵은 `YY.MM.DD`** 줄이다 — `<span color="red">**26.07.25 (행정팀)**</span>`
처럼 뒤에 말이 붙기도 하고, `<details><summary>` 안에 들어 있기도 하다.

**빨간 굵은 글씨가 전부 날짜인 것은 아니다.** 같은 모양으로 이런 것들이 있다:

- `**정해야함**` · `**재정부와 논의 할 것 (담당M)**` — 강조일 뿐이다
- `**총무팀 모임 전 수시로 정리한 내용들 (특정일 없음)**` — 날짜 없는 덩어리
- `**사전 OT 필요내용**` — 같은 것
- `**26.04.22 1차 구상안**` — 회의 **안에** 중첩된 것이라 자르면 안 된다
- `**26.05.15 확인 내용**` — 줄 가운데에 있다

그래서 자르는 조건이 셋이다.

1. `YY.MM.DD` 로 **시작**해야 한다 (`26.05.12~15` 같은 기간도 받는다)
2. 그 표시가 **줄의 맨 앞**이어야 한다 (`<details>`/`<summary>` 는 벗겨낸 뒤)
3. 들여쓰기가 **없어야** 한다 — 중첩된 것은 그 회의의 내용이다
4. 그 표시 **뒤에 말이 붙어 있지 않아야** 한다 —
   `<summary>**26.04.22 1차 구상안**</span> ⇒ 외부강사 섭외결정 …</summary>` 는
   26.04.22 회의 **안에** 접어 둔 것이라, 자르면 그 회의가 둘로 쪼개진다.
   실제로 처음에는 그렇게 잘려서 4월 22일 회의가 두 개가 됐다

## 날짜 없는 덩어리

`(특정일 없음)`·`사전 OT 필요내용` 처럼 날짜가 아닌 빨간 굵은 줄도
**버리지 않는다.** 실제 내용이 들어 있다 — 총무팀 역할분담이 통째로 거기 있다.
`meeting_date=None` 으로 두고 제목에 원문을 남긴다.

## 형광펜

`<span color="yellow_bg">` 로 칠해진 대목이 있다. **안 끝난 것을 표시한
것으로 보인다** — `시설에 대걸레 있는지 쓸수 있는지 문의` 가 7/25 와 7/26 에
같은 색으로 두 번 나온다.

**이것은 추측이다.** 노션에 규칙이 적혀 있는 것이 아니라 쓰인 모양에서 읽은
것이므로, 표시는 살려 넣되(`⟨미완료?⟩`) 미리보기에서 **추측이라고 말한다.**
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

# ── 잘라내는 표시 ──────────────────────────────────────────────────────
# 빨간 굵은 글씨 한 덩이. `<span color="red">**…**</span>`
_RED = re.compile(r'<span color="red(?:_bg)?">\s*\*\*(?P<text>.+?)\*\*\s*</span>')
# 그 안에서 날짜로 읽히는 것. `26.07.25` · `26.05.12~15`
_DATE = re.compile(r"^(?P<y>\d{2})\.(?P<m>\d{2})\.(?P<d>\d{2})(?:\s*~\s*\d{1,2})?")
_YELLOW = re.compile(r'<span color="yellow_bg">(?P<text>.*?)</span>', re.S)
_TAG = re.compile(r"</?(?:details|summary)>")
_SPAN = re.compile(r'<span color="[a-z_]+">|</span>')

# 사람 평가로 읽히는 말. **자동으로 빼지 않는다** — 사람이 보고 정한다.
_평가말 = (
    "잘함", "못함", "약함", "익숙", "꼼꼼", "빠릿", "적응", "다 잘",
    "INFP", "ISFJ", "ENFJ", "ISTP", "ESFJ", "INFJ", "ISTFP", "ISTJ",
    "ENFP", "INTP", "INTJ", "ENTJ", "ENTP", "ESTJ", "ESTP", "ISFP", "ESFP",
)


@dataclass
class 회의:
    """잘라낸 회의 하나."""

    source: str                       # 어느 노션 페이지에서 왔는가
    heading: str                      # 원문 제목 줄
    date: dt.date | None              # 날짜 없는 덩어리는 None
    body: str
    highlights: list[str] = field(default_factory=list)
    people_notes: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return f"{self.source} · {self.heading}"


def _strip(line: str) -> str:
    """`<details>`·`<summary>` 껍데기만 벗긴다. 들여쓰기는 **그대로 둔다** —
    중첩 여부를 그것으로 판단하기 때문이다."""
    return _TAG.sub("", line)


def _plain(text: str) -> str:
    """색 태그를 걷어낸 사람이 읽는 글."""
    return _SPAN.sub("", text).strip()


def cut(text: str, *, source: str) -> tuple[list[회의], list[str]]:
    """한 페이지를 회의들로 자른다. `(회의들, 자르지 못한 것)`.

    **자르지 못한 것을 조용히 버리지 않는다** — 어느 대목인지 돌려주고
    미리보기가 그것을 보여 준다 (4-10 의 '빠진 선행' 과 같은 자리).
    """
    lines = text.splitlines()
    # 앞머리(`---` 사이의 메타)는 건너뛴다
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
        lines = lines[end + 1 :]

    자른것: list[tuple[str, dt.date | None, list[str]]] = []
    못자른것: list[str] = []
    현재: list[str] | None = None

    for raw in lines:
        벗긴 = _strip(raw)
        m = _RED.search(벗긴)
        머리 = False
        if m:
            앞 = 벗긴[: m.start()]
            # 조건 2·3 — 줄 맨 앞이고 들여쓰기가 없어야 한다
            뒤 = 벗긴[m.end() :].strip()
            # 표시 **뒤에 말이 붙어 있으면** 회의 제목이 아니다 — 조건 4
            if 앞.strip() == "" and 뒤 == "" and not raw.startswith((" ", "\t")):
                속 = m.group("text").strip()
                d = _DATE.match(속)
                if d:
                    year = 2000 + int(d.group("y"))
                    try:
                        날 = dt.date(year, int(d.group("m")), int(d.group("d")))
                    except ValueError:
                        # `26.00.00` — 템플릿의 빈 자리다. 날짜가 아니다
                        날 = None
                    자른것.append((속, 날, []))
                    현재 = 자른것[-1][2]
                    머리 = True
                elif _평가아님(속):
                    # 날짜 없는 덩어리. **버리지 않는다**
                    자른것.append((속, None, []))
                    현재 = 자른것[-1][2]
                    머리 = True
                else:
                    못자른것.append(속)
        if not 머리:
            if 현재 is None:
                # 첫 회의 앞의 머리말(행사 개요 등)은 회의가 아니다
                continue
            현재.append(raw)

    회의들 = []
    for 제목, 날, 줄들 in 자른것:
        본문 = "\n".join(줄들).strip("\n")
        회의들.append(
            회의(
                source=source,
                heading=_plain(제목),
                date=날,
                body=본문,
                highlights=[_plain(x) for x in _YELLOW.findall(본문) if _plain(x)],
                people_notes=people_notes(본문),
            )
        )
    return 회의들, 못자른것


def _평가아님(text: str) -> bool:
    """날짜가 아닌 빨간 굵은 줄 중 **회의 제목으로 볼 것**인가.

    `정해야함` 처럼 문장 속 강조는 회의가 아니다. 회의 제목으로 보는 것은
    `(특정일 없음)` 처럼 **덩어리를 여는 말**뿐이라, 길이와 꼬리말로 가른다.
    애매하면 **자르지 않고** 못 자른 것으로 넘긴다 — 잘못 자르면 남의 회의
    내용이 엉뚱한 회의에 붙는데, 그건 눈에 안 띈다.
    """
    if len(text) < 6:
        return False
    return any(x in text for x in ("특정일 없음", "필요내용", "정리한 내용"))


def people_notes(body: str) -> list[str]:
    """**사람 평가로 읽히는 대목**을 짚는다. 자동으로 빼지 않는다.

    `26.06.21` 이 여덟 명의 MBTI 와 개인 평가다(`체력 약함`, `추진력 약함`,
    `사람 쪼는거 못함`). 역할 분담을 위해 그 자리에서 적은 것이지만
    **업무 지식이 아니라 사람 품평이다** — 0장의 "지식은 사람이 아니라 기록에
    남긴다" 는 업무 지식을 말한 것이지 사람 품평이 아니다 (CLAUDE.md 9장).

    사람이 보고 정하도록 **어느 줄인지만** 돌려준다.
    """
    짚은것 = []
    for line in body.splitlines():
        말 = _plain(line).lstrip("-\t ").strip()
        if not 말:
            continue
        if any(x in 말 for x in _평가말):
            짚은것.append(말)
    return 짚은것
