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

**이것은 추측이고, 세어 보니 근거가 약하다.** 회의 50건에서 형광펜은 22개고
서로 다른 문장은 20개인데, **두 번 이상 나온 것은 2개뿐**이다
(`시설에 대걸레…` 7/25·7/26, `홍보영상 썸네일은 헤브론 자체제작` 5/22·5/24).
"안 끝나서 다음 회의로 넘어온 것" 이라는 읽기는 그 둘에 기대고 있고,
나머지 18개는 한 번씩만 나온다 — **그냥 눈에 띄게 칠한 것일 수도 있다.**

그래서 표시는 살려 넣되 **물음표를 뗄 수 없다**(`⟨미완료?⟩`). 미리보기가
개수와 반복 수를 함께 보여 주고, 뜻을 정하는 것은 사람이 한다.
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
#
# **두 칸으로 나눈다.** 한 목록에 다 나오면 200줄이 되고, 200줄이면 사람이
# 안 읽는다. 안 읽으면 짚어 준 것이 없는 것과 같다.
#
#   거의 확실 — MBTI 열여섯. 업무 메모에 이 글자가 나올 이유가 없다
#   볼 만함   — `잘함`·`못함`·`약함` 류. `사용못함` 처럼 **업무 메모도 걸린다**
_MBTI = (
    "INFP", "ISFJ", "ENFJ", "ISTP", "ESFJ", "INFJ", "ISTJ", "INTP",
    "ENFP", "INTJ", "ENTJ", "ENTP", "ESTJ", "ESTP", "ISFP", "ESFP",
    "ISTFP",                       # 원본의 오타. 그대로 잡는다
)
_평가꼬리 = ("잘함", "못함", "약함", "익숙", "꼼꼼", "빠릿", "적응", "다 잘")
_평가말 = _MBTI + _평가꼬리


@dataclass
class 걸림:
    """**조용히 지나갈 뻔한 것.** 미리보기가 이것을 사람에게 보여 준다."""

    kind: str          # '안본제목' | '머리말' | '날짜같은줄' | '빈자리'
    text: str
    붙은곳: str = ""    # 그 내용이 어느 회의로 들어갔는가


@dataclass
class 회의:
    """잘라낸 회의 하나."""

    source: str                       # 어느 노션 페이지에서 왔는가
    heading: str                      # 원문 제목 줄
    date: dt.date | None              # 날짜 없는 덩어리는 None
    body: str
    highlights: list[str] = field(default_factory=list)
    # **두 칸이다** (6단계). 한 목록이면 200줄이 되고, 200줄이면 안 읽는다
    people_sure: list[str] = field(default_factory=list)    # MBTI — 거의 확실
    people_maybe: list[str] = field(default_factory=list)   # 잘함·못함 류
    # `26.00.00` — 템플릿의 빈 칸. **날짜 없는 덩어리와 다르다** (4단계)
    empty_slot: bool = False

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


def cut(text: str, *, source: str) -> tuple[list[회의], list[걸림]]:
    """한 페이지를 회의들로 자른다. `(회의들, 걸린 것들)`.

    **조용히 지나가는 것을 만들지 않는다** (4-10 의 '빠진 선행' 과 같은 자리).
    걸리는 것이 네 가지다.

    | 걸림 | 무엇 |
    |---|---|
    | `안본제목` | 빨간 굵은 줄인데 회의 제목으로 안 본 것. **그 내용이 어느 회의에 붙었는지** 함께 말한다 |
    | `머리말` | 첫 회의 앞의 글. 버리지 않고 무엇을 버렸는지 말한다 |
    | `날짜같은줄` | 회의 **본문 안**에 줄 맨 앞 날짜처럼 보이는 것. 자르지는 않고 말만 한다 |
    | `빈자리` | `26.00.00` — 템플릿의 빈 칸이지 회의가 아니다 |

    **네 번째 갈래가 특히 중요하다.** 지금 조건들은 "빨간 굵은데 회의가 아닌
    것" 을 가린다 — 걸리면 목록에 남아 눈에 띈다. 위험한 것은 **반대쪽**이다.
    날짜인데 `_RED` 가 못 찾는 경우(색이 빨강이 아님 · 색 없이 `**26.07.26**` ·
    `26.7.5`)에는 **아무 경고 없이 앞 회의에 흡수된다.** 그래서 잘라낸 본문을
    다시 훑어 날짜처럼 보이는 줄을 말한다. 자르지는 않는다 — 잘못 자르면
    남의 회의 내용이 엉뚱한 곳에 붙는데 그건 눈에 안 띈다.
    """
    lines = text.splitlines()
    # 앞머리(`---` 사이의 메타)는 건너뛴다
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
        lines = lines[end + 1 :]

    자른것: list[list] = []          # [제목, 날짜, 줄들, 빈자리인가]
    걸린것: list[걸림] = []
    머리말: list[str] = []
    현재: list[str] | None = None

    for raw in lines:
        벗긴 = _strip(raw)
        m = _RED.search(벗긴)
        시작 = False
        if m:
            앞 = 벗긴[: m.start()]
            뒤 = 벗긴[m.end() :].strip()
            # 조건 2·3·4 — 줄 맨 앞 · 들여쓰기 없음 · 뒤에 말이 안 붙음
            if 앞.strip() == "" and 뒤 == "" and not raw.startswith((" ", "\t")):
                속 = m.group("text").strip()
                d = _DATE.match(속)
                if d:
                    year = 2000 + int(d.group("y"))
                    빈자리 = False
                    try:
                        날 = dt.date(year, int(d.group("m")), int(d.group("d")))
                    except ValueError:
                        # `26.00.00` — **템플릿의 빈 칸이지 회의가 아니다.**
                        # 날짜 없는 덩어리와 같은 칸에 두면 사람이 구별할 수 없다
                        날, 빈자리 = None, True
                        걸린것.append(걸림("빈자리", 속))
                    자른것.append([속, 날, [], 빈자리])
                    현재 = 자른것[-1][2]
                    시작 = True
                elif _덩어리제목(속):
                    # 날짜 없는 덩어리. **버리지 않는다**
                    자른것.append([속, None, [], False])
                    현재 = 자른것[-1][2]
                    시작 = True
                else:
                    # **회의 제목으로 안 본 빨간 줄.** 그 내용이 어디로 갔는지
                    # 함께 말한다 — 제목만 알려주면 내용이 어디 갔는지 모른다
                    붙은곳 = _plain(자른것[-1][0]) if 자른것 else "(첫 회의 앞 머리말)"
                    걸린것.append(걸림("안본제목", 속, 붙은곳))
        if not 시작:
            if 현재 is None:
                # **첫 회의 앞의 글을 조용히 버리지 않는다.** 행사 개요처럼
                # 회의가 아닌 것이 대부분이지만, 버린다면 무엇을 버렸는지
                # 말해야 한다 — 머리말에 그렇게 적어 놓고 버리면 안 된다
                if _plain(_strip(raw)).strip():
                    머리말.append(raw)
                continue
            현재.append(raw)

    if 머리말:
        걸린것.append(걸림(
            "머리말",
            f"첫 회의 앞의 {len(머리말)}줄을 회의로 넣지 않았습니다"
            f" — {_plain(_strip(머리말[0])).strip()[:44]} …"))

    회의들 = []
    for 제목, 날, 줄들, 빈자리 in 자른것:
        본문 = "\n".join(줄들).strip("\n")
        for 줄 in date_like_lines(본문):
            # **자르지 않는다. 말만 한다.** 잘못 자르면 남의 회의 내용이
            # 엉뚱한 곳에 붙는데 그건 눈에 안 띈다
            걸린것.append(걸림("날짜같은줄", 줄, _plain(제목)))
        회의들.append(
            회의(
                source=source,
                heading=_plain(제목),
                date=날,
                body=본문,
                highlights=[_plain(x) for x in _YELLOW.findall(본문) if _plain(x)],
                people_sure=people_notes(본문, sure=True),
                people_maybe=people_notes(본문, sure=False),
                empty_slot=빈자리,
            )
        )
    return 회의들, 걸린것


def _덩어리제목(text: str) -> bool:
    """날짜가 아닌 빨간 굵은 줄 중 **회의 제목으로 볼 것**인가.

    `정해야함` 처럼 문장 속 강조는 회의가 아니다. 회의 제목으로 보는 것은
    `(특정일 없음)` 처럼 **덩어리를 여는 말**뿐이라, 길이와 꼬리말로 가른다.
    애매하면 **자르지 않고** 못 자른 것으로 넘긴다 — 잘못 자르면 남의 회의
    내용이 엉뚱한 회의에 붙는데, 그건 눈에 안 띈다.
    """
    if len(text) < 6:
        return False
    return any(x in text for x in ("특정일 없음", "필요내용", "정리한 내용"))


# 색이 없어도 날짜처럼 보이는 줄. `26.7.5` 처럼 한 자리 달·일도 잡는다 —
# **놓치는 쪽이 위험하므로 넉넉하게 본다.** 자르지는 않고 말만 하기 때문에
# 헛짚어도 값이 싸다.
_DATE_LIKE = re.compile(r"^\s{0,3}\**\s*(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def date_like_lines(body: str) -> list[str]:
    """회의 **본문 안**에 줄 맨 앞 날짜처럼 보이는 것.

    `_RED` 가 못 알아본 회의 제목이면 여기 걸린다 — 색이 빨강이 아니거나,
    색 없이 `**26.07.26**` 이거나, `26.7.5` 처럼 자릿수가 다를 때다.
    그런 것은 **아무 경고 없이 앞 회의에 흡수되므로** 말해 준다.
    """
    나온것 = []
    for line in body.splitlines():
        말 = _plain(_TAG.sub("", line))
        if _DATE_LIKE.match(말):
            나온것.append(말.strip()[:70])
    return 나온것


def people_notes(body: str, *, sure: bool | None = None) -> list[str]:
    """**사람 평가로 읽히는 대목**을 짚는다. 자동으로 빼지 않는다.

    `26.06.21` 이 여덟 명의 MBTI 와 개인 평가다(`체력 약함`, `추진력 약함`,
    `사람 쪼는거 못함`). 역할 분담을 위해 그 자리에서 적은 것이지만
    **업무 지식이 아니라 사람 품평이다** — 0장의 "지식은 사람이 아니라 기록에
    남긴다" 는 업무 지식을 말한 것이지 사람 품평이 아니다 (CLAUDE.md 9장).

    사람이 보고 정하도록 **어느 줄인지만** 돌려준다.

    `sure=True` 면 MBTI 가 든 줄만(**거의 확실**), `sure=False` 면 나머지
    평가말이 든 줄만(**볼 만함**), `None` 이면 둘 다. 나누는 이유는 6단계에
    적혀 있다 — 한 목록이면 사람이 안 읽는다.
    """
    말들 = _MBTI if sure is True else (_평가꼬리 if sure is False else _평가말)
    짚은것 = []
    for line in body.splitlines():
        말 = _plain(line).lstrip("-\t ").strip()
        if not 말:
            continue
        if sure is False and any(x in 말 for x in _MBTI):
            continue                     # 거의 확실 쪽에 이미 들어갔다
        if any(x in 말 for x in 말들):
            짚은것.append(말)
    return 짚은것
