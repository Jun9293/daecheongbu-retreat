"""회의록을 읽고 제안한다 — **창구는 한 곳** (CLAUDE.md 회의록 4단계).

회의록 화면에서 부르든 나중에 채팅으로 부르든 **읽고 제안하는 길은 여기
하나**다. 두 벌이 되면 이 프로젝트가 다섯 번 고쳐 온 그 모양이 다시 난다
(색·기간·툴팁·`onOpen`·`onAssignee`).

## 세 가지를 낸다

1. **결정사항** — 이 회의에서 정해진 것 (`kind='decision'`).
   **회의록의 그 줄을 그대로 인용한다** — 사람이 인용을 보면 3초 만에 맞는지 안다
2. **논의** — 그 회의 내용이 어느 업무의 사정인지 (`kind='discussion'`)
3. **새 업무** — 회의에 할 일로 나왔는데 목록에 없는 것 (`kind='new'`)

**둘째가 가장 어렵다.** 250건 중 하나를 고르는 일이고, 틀리면 남의 회의 내용이
엉뚱한 업무에 남는다. 그래서 제안마다 **왜 그 업무인지**를 함께 낸다 (6-3).

## 이제 문장을 읽는다 — 못 읽으면 낱말로 물러선다

2026-09-03 에 사람이 표본 21개를 채점했다. 낱말 겹침은 **14/21** 이었고,
틀린 일곱 중 넷이 *"낱말은 겹쳤는데 그 얘기를 한 적이 없다"*, 하나가
*"결정과 단순 의견을 못 가린다"* 였다 (`docs/review/제안-성적표.md`).
**둘 다 이름만 봐서는 못 넘는다.** 그래서 Claude API 로 회의록과 업무 목록을
함께 읽는다 (`분석()`).

**낱말 겹침을 지우지 않았다.** 키가 없거나 API 가 죽었을 때 갈 자리가
필요하다. 그때 빈 목록을 내면 "할 말이 없다"(조건 4의 정상)와 구별되지
않는데, **구별되지 않는 실패가 이 프로젝트에서 가장 비싼 실패다.**
그래서 물러서되 **물러섰다고 화면에 적는다** (`결과.방식` · `결과.말`).

**어느 쪽이든 화면이 무엇으로 골랐는지 말한다.** 감추면 실제로 어떤지 영영
모르지만, 감추지 않는 것만으로는 부족하다 — 위험한 것은 틀린 제안이 아니라
**사람이 처음에 세우는 기대**다. 한 번 잃으면 안 돌아온다 (6-3).

## 지키는 것 (4-10 의 조건들)

- **판정 단어는 우리가 지어낸 문장에만 건다** (조건 7). 사람이 쓴 회의 제목에
  `완료` 가 들어 있으면 그건 그 사람의 말이지 우리 판정이 아니다 —
  거기까지 지우면 원문이 뭉개진다
- **할 말이 없으면 빈 목록을 낸다** (조건 4). 억지로 만들면 근거 없는 제안이 된다
- **실패해도 화면은 살아 있다** (조건 8) — 부르는 쪽이 빈 목록을 받는다
- **아무것도 자동으로 반영되지 않는다.** 사람이 하나씩 고른다

## 그 시점의 보드 (3단계)

**가리는 것은 존재가 아니라 상태다.** 처음에는 "시작일이 지난 것만" 으로
걸렀다가 6월 회의에 제안이 하나도 안 나와서 틀렸다는 것을 알았다 — 6월
회의가 8월 업무를 얘기하는 것은 자연스럽고, 업무 목록은 회차를 열 때 이미
다 정해져 있다 (6-6).

**대신 상태를 그날로 되돌린다.** 저장된 `status` 는 **오늘의 값**이라 그대로
보여주면 8월에 끝난 것을 알고 6월 회의를 고르게 된다 — 잰 것이 아니라 답을
본 것이 된다. 그래서 `started_at`·`completed_at` **날짜에서 그날의 상태를
다시 계산한다** (`_상태`). 4-10 이 기한 초과를 저장된 '지연' 이 아니라
날짜로 계산하기로 한 것과 같은 자리다.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import board as board_domain
from app.models import Meeting, Retreat

# 4-10 이 쓰는 판정 단어. **우리가 지어낸 문장에는 나오면 안 된다.**
판정단어 = ("진행 불가", "진행 가능", "일부 진행", "완료", "지연")

# 할 일처럼 읽히는 줄의 꼬리말. 회의록이 실제로 그렇게 쓰여 있다 —
# `…확인 필요` · `…요청` · `…제작하기`. 완벽한 규칙이 아니라 **추리는 그물**이다.
_할일말 = ("필요", "요청", "확인", "정하기", "만들기", "준비", "제작",
          "문의", "전달", "구매", "섭외", "예정", "해야", "하기로")


@dataclass
class BoardRow:
    """그 시점에 **알 수 있었던 것만.**

    처음에는 상태를 아예 안 담았다 — 담으면 본다는 이유였다. 문장으로 읽는
    판(회의록 5단계)에서는 상태가 필요해졌는데, **저장된 `status` 를 담으면
    안 된다.** 그건 오늘의 상태이지 그 회의 날의 상태가 아니고, 6월 회의를
    분석하면서 8월에 끝난 것을 알고 고르면 **잘 맞히는 것처럼 보인다.**

    그래서 `started_at` · `completed_at` **날짜에서 그날의 상태를 다시
    계산한다** (`_상태`). 4-10 이 기한 초과를 저장된 '지연' 이 아니라 날짜로
    계산하기로 한 것과 같은 자리다.
    """

    run_id: int
    title: str
    department: str | None
    start: dt.date | None
    end: dt.date | None
    kind: str = "main"                  # 'main' | 'sub' | 'schedule' (4-2)
    parent_title: str | None = None
    # **그 회의 날 기준.** `None` 은 *모른다* 는 뜻이다 — 기본값을 '대기' 로
    # 두면 모르는 것을 주장하게 된다 (6-9). 아래 `_상태` 를 보라.
    status: str | None = None


@dataclass
class 제안:
    kind: str                       # 'decision' | 'discussion' | 'new' | '더있음'
    text: str                       # 사람이 읽을 제안 내용
    why: str                        # **왜 그 업무인지** (6-3)
    run_id: int | None = None       # discussion 일 때 붙일 업무
    run_title: str | None = None
    meeting_id: int | None = None   # 어느 회의록에서 왔는가 (출처)
    evidence: list[str] = field(default_factory=list)
    # ── 문장으로 읽는 판에서 붙었다 (회의록 5단계) ────────────────────
    quote: str | None = None        # 결정사항 — **회의록의 그 줄 그대로**
    title: str | None = None        # 새 업무 — 다듬은 제목
    parent_run_id: int | None = None
    parent_title: str | None = None
    department: str | None = None


def board_as_of(db: Session, retreat: Retreat, as_of: dt.date) -> list[BoardRow]:
    """그 시점의 보드.

    **`as_of` 는 존재를 가리는 데 쓰지 않는다.** 6월 회의가 8월 업무를
    얘기하는 것은 자연스럽고, 업무 목록은 회차를 열 때 이미 다 정해져 있다
    (6-6). 처음에 "시작일이 지난 것만" 으로 걸렀다가 6월 회의에 제안이 하나도
    안 나와서 틀렸다는 것을 알았다.

    **`as_of` 가 실제로 하는 일은 상태를 그날로 되돌리는 것이다** (`_상태`).
    저장된 `status` 는 오늘의 값이라, 그것을 보여주면 8월에 끝난 것을 알고
    6월 회의를 고르게 된다 — 잰 것이 아니라 답을 본 것이 된다.

    **`board.load_runs` 를 쓴다.** 직접 `select(TaskRun)` 을 하면 `library` ·
    `department` 를 건건이 읽어 N+1 이 난다 — 실제로 그랬다(업무 96건에
    107쿼리). `load_runs` 는 셋을 미리 붙여 온다.
    """
    runs = list(board_domain.load_runs(db, retreat))
    # 상위 이름 — 라이브러리 id 로 이어져 있다 (8장 `parentLibraryId`)
    이름 = {r.library_id: (r.library.title or "") for r in runs if r.library}
    return [
        BoardRow(
            run_id=r.id,
            title=r.library.title or "",
            department=r.department.name if r.department else None,
            start=r.start_date,
            end=r.end_date,
            kind=(r.library.kind if r.library else None) or "main",
            parent_title=이름.get(getattr(r.library, "parent_library_id", None)),
            status=_상태(r, as_of),
        )
        for r in runs
    ]


def _상태(run, as_of: dt.date) -> str | None:
    """**그날의 상태.** 저장된 `status` 를 읽지 않는다. 모르면 `None`.

    저장된 값은 오늘의 상태다. 6월 회의를 분석하면서 8월에 끝난 것을 알고
    고르면 잘 맞히는 것처럼 보이는데, 그건 잰 것이 아니라 답을 본 것이다.
    날짜 둘만 본다 — `completed_at` · `started_at` (8장).

    **날짜가 둘 다 없으면 '대기' 라고 하지 않는다.** 옮겨 온 자료는 그 둘이
    비어 있어서 96건이 **전부 '대기'** 로 나갔다. 구별에 기여하지 않으면서
    토큰만 먹고, **8월에 끝난 일도 '대기' 로 보인다** — 모델은 그것을
    "아직 안 한 일" 로 읽는다. **'대기' 는 주장이다. 모르는 것을 주장하지
    않는다** (6-9).
    """
    끝 = getattr(run, "completed_at", None)
    시작 = getattr(run, "started_at", None)
    if 끝 and 끝 <= as_of:
        return "완료"
    if 시작 and 시작 <= as_of:
        return "진행중"
    if 끝 or 시작:
        # 날짜가 있는데 아직 그날이 안 됐다 — 그건 **아는 것**이다
        return "대기"
    return None


def catalog(rows: list[BoardRow]) -> str:
    """보드를 **글로** 펼친다. 문장으로 읽는 판이 이것을 앞에 놓고 판단한다.

    낱말 겹침은 이름만 봤다. 이름만 보면 `프로그램 자료 헤브론 전달` 이
    무엇의 하위인지, 어느 부서 것인지, 언제 하는 것인지 알 수 없다 —
    성적표에서 틀린 일곱 중 넷이 정확히 그 자리였다.

    한 줄에 하나씩, **run_id 를 앞에 붙인다.** 대답이 이 번호로 돌아오므로
    이름을 되짚어 찾을 필요가 없다 — 이름으로 받으면 같은 이름이 둘일 때
    엉뚱한 업무에 논의가 남는다.
    """
    분류 = {"main": "Main", "sub": "하위", "schedule": "일정"}
    줄 = []
    for x in rows:
        기간 = (f"{x.start.isoformat()}~{x.end.isoformat()}"
                if x.start and x.end else "기간 미정")
        속성 = 분류.get(x.kind, x.kind)
        if x.parent_title:
            속성 += f"(상위: {x.parent_title})"
        칸 = [f"[{x.run_id}] {x.title}", x.department or "담당팀 없음", 속성, 기간]
        # **모르면 칸을 아예 뺀다.** `상태 모름` 을 96줄에 96번 쓰는 것보다
        # 빼는 것이 싸고, 빠진 것이 곧 "모름" 이라는 뜻은 아래 머리말 한 줄이
        # 말해 준다. 있는 것만 적으면 **있다는 사실 자체가 정보**가 된다.
        if x.status:
            칸.append(x.status)
        줄.append(" · ".join(칸))
    아는것 = sum(1 for x in rows if x.status)
    머리 = ("(맨 끝의 상태는 그 회의 날 기준입니다. "
           f"{len(rows)}건 중 {아는것}건만 적혀 있고, "
           "**적히지 않은 것은 시작·완료 기록이 없어 모르는 것**입니다 — "
           "아직 안 한 일이라는 뜻이 아닙니다.)")
    return 머리 + "\n" + "\n".join(줄)


def _낱말(text: str) -> set[str]:
    """견줄 낱말. 두 글자 이상의 한글·영문 덩이만."""
    return {w for w in re.findall(r"[가-힣A-Za-z]{2,}", text)}


def 흔한낱말(rows: list[BoardRow], 넘으면: int = 3) -> set[str]:
    """보드에서 **여러 업무 이름에 두루 나오는 낱말**.

    `제작` 은 업무 이름 11개에, `준비`·`확정`·`완료` 는 6개에 나온다. 이런
    낱말만으로 겹친 것은 관계를 말해 주지 않는다 — `확인, 조정` 이 겹쳤다고
    그 회의가 그 업무 이야기인 것은 아니다.

    잰 결과 이 조건은 논의 제안을 104개에서 95개로 줄인다. 크지 않지만
    **줄어드는 아홉 개가 정확히 가장 약한 것들**이라 남긴다.
    """
    셈: dict[str, int] = {}
    for x in rows:
        for w in _낱말(x.title):
            셈[w] = 셈.get(w, 0) + 1
    return {w for w, c in 셈.items() if c > 넘으면}


def 겹침(a: str, b: str) -> tuple[int, list[str]]:
    """두 글의 겹치는 낱말 수와 그 낱말들. **왜 그 업무인지의 근거**가 된다."""
    공통 = sorted(_낱말(a) & _낱말(b), key=len, reverse=True)
    return len(공통), 공통[:5]


def 판정단어_뺀다(text: str) -> str:
    """**우리가 지어낸 문장**에서 판정 단어를 지운다 (4-10 조건 7).

    코드가 판정에 안 넣어도, 요약이 "진행 불가로 보입니다" 라고 쓰면 사람은
    판정으로 읽는다. 패널 이름이 판정 결과인 화면이라 더 그렇다.

    **사람이 쓴 원문에는 걸지 않는다.** 회의 제목이 `26.08.16 최종패킹 완료`
    면 그 `완료` 는 그 사람의 말이지 우리 판정이 아니고, 지우면
    `26.08.16 최종패킹 …` 이 되어 **원문이 뭉개진다.** 조건 7 이 막는 것은
    우리가 판정을 내리는 것이지 남의 글을 검열하는 것이 아니다.
    """
    for w in 판정단어:
        text = text.replace(w, "…")
    return text


def 할일줄(본문: str) -> list[str]:
    """회의록에서 **할 일처럼 읽히는 줄**만 추린다.

    완벽한 규칙이 아니다 — 꼬리말로 거르는 **그물**이고, 걸린 것 중 보드에
    없는 것만 새 업무 후보로 낸다. 새 업무는 틀려도 사람이 안 고르면 그만이라
    논의보다 값이 싸지만, 그래도 **근거는 함께 낸다** (6-3).
    """
    나온것 = []
    for line in 본문.splitlines():
        말 = re.sub(r"<[^>]+>", "", line)
        말 = 말.replace("**", "").replace("~~", "")   # 마크업이 새어 나왔다
        말 = 말.strip(" \t-•◦▪*→⇒")
        말 = re.sub(r"^\d+[.)]\s*", "", 말).strip()
        if not (6 <= len(말) <= 40):
            continue
        # **꼬리에 있어야 한다.** 가운데 있으면 그냥 서술문이다 —
        # `외부강사 섭외의 경우 진행해보면서 대안 설정이 계속 필요할 것으로 예상됨`
        # 은 할 일이 아니라 의견이다
        if not any(말.endswith(x) or 말.endswith(x + "기") for x in _할일말):
            continue
        if len(_낱말(말)) < 2:
            continue
        나온것.append(말)
    return 나온것


def 낱말제안(db: Session, *, retreat: Retreat, meeting: Meeting,
           as_of: dt.date | None = None, limit: int = 5) -> list[제안]:
    """**낱말 겹침으로만** 고른다 — 문장을 읽지 않는다.

    2026-09-03 에 사람이 표본 21개를 채점했고 14/21 이었다
    (`docs/review/제안-성적표.md`). 그래서 지금은 이것이 **첫째 길이 아니라
    물러설 자리**다 — Claude 를 못 부를 때 여기로 온다. 지우지 않은 이유는
    아래 `분석()` 의 머리말에 적혀 있다.
    """
    본문 = (meeting.body or "").strip()
    if not 본문:
        return []                                   # 할 말이 없으면 빈 목록
    기준일 = as_of or meeting.meeting_date or dt.date.today()
    rows = board_as_of(db, retreat, 기준일)
    if not rows:
        return []

    나온것: list[제안] = []

    # ── ① 논의 — 이미 있는 업무에 붙일 것 ────────────────────────────
    흔함 = 흔한낱말(rows)
    점수 = []
    for row in rows:
        n, 낱말 = 겹침(본문, row.title)
        # 두 낱말 이상 겹치되, **그중 하나는 흔하지 않아야** 한다.
        # `확인, 조정` 처럼 아무 업무에나 있는 낱말만으로는 관계가 아니다
        if n >= 2 and any(w not in 흔함 for w in 낱말):
            점수.append((n, 낱말, row))
    점수.sort(key=lambda x: (-x[0], x[2].title))
    잘린수 = max(0, len(점수) - limit)
    for n, 낱말, row in 점수[:limit]:
        나온것.append(제안(
            kind="discussion",
            # **제목은 사람의 원문이라 손대지 않는다.** 지어낸 부분만 거른다
            text=meeting.title + 판정단어_뺀다(" 의 내용을 이 업무의 논의로 남깁니다"),
            why=f"회의록과 업무 이름에 '{', '.join(낱말)}' 이(가) 함께 나옵니다"
                f" (겹친 낱말 {n}개)",
            run_id=row.run_id,
            run_title=row.title,
            meeting_id=meeting.id,
            evidence=낱말,
        ))
    if 잘린수:
        # **조용히 자르지 않는다.** 걸린 것이 더 있다는 사실을 말한다
        나온것.append(제안(
            kind="더있음",
            text=f"이름이 겹치는 업무가 {잘린수}건 더 있습니다",
            why="가장 많이 겹친 것부터 보여 주고 나머지는 접었습니다"
                " — 다 보여 주면 어느 것이 가까운지 알 수 없습니다",
            meeting_id=meeting.id,
        ))

    # ── ② 새 업무 — 보드의 어느 이름과도 안 겹치는 할 일 ──────────────
    #
    # **그물이 반대로 기울어 있었다.** 업무 이름은 짧고(`선발대 운영`) 회의록
    # 줄은 길어서(`선발대 점심 주문 준비`) 겹치는 낱말이 하나뿐이었고, 그래서
    # **보드에 있는데 이름이 짧을수록 새 업무로 잘못 나왔다.**
    #
    # 그래서 셋을 더한다 —
    #   · 가장 가까운 기존 업무를 **근거로 함께 낸다.** 전에는 그 줄 자신의
    #     낱말을 근거라고 냈는데 그건 아무것도 증명하지 않는다
    #   · 줄의 낱말이 **전부 보드 어딘가에 이미 있으면** 새 업무가 아니다
    #   · 가장 가까운 것과 한 낱말이라도 겹치면 **사람이 그것을 보고 판단한다**
    보드전체 = set()
    보드낱말 = []
    for x in rows:
        w = _낱말(x.title)
        보드낱말.append((w, x.title))
        보드전체 |= w
    본것: set[str] = set()
    for 말 in 할일줄(본문)[: limit * 6]:
        if 말 in 본것:
            continue          # 같은 줄이 두 번 적힌 회의가 있다
        본것.add(말)
        말낱말 = _낱말(말)
        if not 말낱말:
            continue
        가까움, 가까운제목 = max(((len(말낱말 & w), t) for w, t in 보드낱말),
                             key=lambda z: z[0])
        if 가까움 >= 2:
            continue                   # 이미 있는 업무 이야기다
        if 말낱말 <= 보드전체:
            continue                   # 낱말이 전부 보드에 이미 있다
        근거 = (f"가장 가까운 것: 「{가까운제목}」 (겹친 낱말 {가까움}개)"
              if 가까움 else "보드의 어느 업무 이름과도 한 낱말도 겹치지 않습니다")
        나온것.append(제안(
            kind="new",
            # 회의록의 문장은 **사람의 원문**이라 그대로 붙인다
            text=판정단어_뺀다("새 업무로 만듭니다 — ") + 말,
            why=f"회의록에 할 일처럼 적혔습니다. {근거}"
                f" — 보드 {len(rows)}건과 견줬습니다",
            meeting_id=meeting.id,
            evidence=[가까운제목] if 가까움 else [],
        ))
        if sum(1 for x in 나온것 if x.kind == "new") >= limit:
            break
    return 나온것


def simulate(db: Session, *, retreat: Retreat, until: dt.date,
             limit: int = 5) -> list[tuple[Meeting, list[제안]]]:
    """`until` 까지의 회의록을 **시간순으로 하나씩** 넣으면서 그때 무엇을
    제안하는지 본다 (3단계).
    """
    회의들 = db.scalars(
        select(Meeting)
        .where(Meeting.retreat_id == retreat.id,
               Meeting.meeting_date.is_not(None),
               Meeting.meeting_date <= until)
        .order_by(Meeting.meeting_date, Meeting.id)
    ).all()
    return [(m, suggest(db, retreat=retreat, meeting=m,
                        as_of=m.meeting_date, limit=limit)) for m in 회의들]


# ══════════════════════════════════════════════════════════════════════
# 문장으로 읽는다 (회의록 5단계)
# ══════════════════════════════════════════════════════════════════════
#
# **왜 바꿨나.** 낱말 겹침은 표본 21개에서 14개였다. 틀린 일곱 중 넷이
# "낱말은 겹쳤는데 그 얘기를 한 적이 없다" 이고 하나가 "결정과 단순 의견을
# 못 가린다" 였다 — 둘 다 이름만 봐서는 못 넘는다
# (`docs/review/제안-성적표.md` 의 '판단').
#
# **낱말 겹침을 지우지 않았다.** 키가 없거나 API 가 죽었을 때 갈 곳이
# 필요하기 때문이다. 그때 빈 목록을 내면 "할 말이 없다"(조건 4의 정상)와
# 구별되지 않는데, **구별되지 않는 실패가 이 프로젝트에서 가장 비싼
# 실패다.** 그래서 물러서되 **물러섰다고 화면에 적는다.**

import json                                                # noqa: E402

from app.models import DiscussionEntry                     # noqa: E402
from app.domain import llm as llm_mod                      # noqa: E402
from app.domain import meeting_import                      # noqa: E402

_시스템 = """당신은 교회 대학청년부 수련회 준비 시스템의 보조입니다.
회의록 한 편과 그 회차의 준비 업무 목록을 받아, 사람이 골라 쓸 제안을 만듭니다.

내는 것은 세 가지입니다.

1. 결정사항 — 이 회의에서 **정해진 것**. 의견·제안·검토 중인 것은 아닙니다.
   반드시 회의록의 그 줄을 **글자 그대로** 인용하세요. 고치거나 다듬지 마세요.
2. 논의 — 이 회의 내용이 **어느 업무의 사정인지**. 목록의 run_id 로 답하세요.
3. 새 업무 — 회의에 할 일로 나왔는데 목록에 없는 것.

지킬 것

- **확신이 없으면 넣지 마세요.** 빈 배열이 정상이고 흔한 답입니다.
  회의록 절반쯤은 아무것도 낼 것이 없습니다.
- 논의의 근거는 **왜 그 업무인지를 문장으로** 적으세요.
  "낱말이 겹칩니다" 는 근거가 아닙니다. 회의에서 무슨 얘기를 했고 그것이
  그 업무의 무엇에 해당하는지를 쓰세요.
- 회의록에 그 업무 얘기가 **실제로 나오지 않으면 넣지 마세요.** 이름이
  비슷하다는 이유로 넣으면 안 됩니다.
- 새 업무 제목은 **업무 이름답게** 짧은 명사구로 다듬으세요
  (예: "큐시트 제작", "명찰 스트랩 발주"). 회의록 문장을 그대로 쓰지 마세요.
  가능하면 어느 업무의 하위인지(상위_run_id)와 어느 부서인지를 함께 적으세요.
- 다음 낱말을 당신의 문장에 쓰지 마세요: 진행 불가, 진행 가능, 일부 진행,
  완료, 지연. (이 시스템에서 판정을 뜻하는 말이라 사람이 판정으로 읽습니다.)
- **사람에 대한 평가는 인용하지도 요약하지도 마세요.** 성격·MBTI·능력 품평이
  회의록에 있어도 제안에 담지 마세요. 업무 내용만 다룹니다.
- 사람 이름은 업무 담당을 말할 때만 쓰세요.

JSON 만 출력하세요. 설명을 붙이지 마세요."""

_1차틀 = """{
  "결정사항": [{"인용": "회의록의 줄 그대로", "무엇": "무엇이 정해졌는지 한 문장"}],
  "논의후보": [{"run_id": 12, "왜": "왜 그 업무인지 문장으로"}],
  "새업무": [{"제목": "다듬은 이름", "왜": "문장", "상위_run_id": null, "부서": null}]
}"""

_2차틀 = """{
  "논의": [{"run_id": 12, "왜": "문장", "이미있음": false}]
}"""


@dataclass
class 결과:
    """제안과 **그것을 어떻게 얻었는지.**

    방식을 함께 내는 이유는 하나다 — 낱말로 물러섰을 때 화면이 그렇게 말해야
    하기 때문이다. 값만 내면 물러선 것을 아무도 모른다.
    """

    제안들: list[제안]
    방식: str                       # '문장' | '낱말'
    말: str                         # 화면에 그대로 뜨는 한 줄
    사람평가: list[str] = field(default_factory=list)
    글자수: int = 0                 # 보낸 업무 목록 크기 (2단계)
    원: float = 0.0                 # 이 회의 하나에 든 값 (3단계)
    부른횟수: int = 0
    실패: bool = False
    # **잰 것을 적는다.** 어림한 값(회의당 37~43원)이 실제로는 113원이었다 —
    # 세 배다. `usage` 를 그대로 받아 둔다
    입력토큰: int = 0
    출력토큰: int = 0
    생각토큰: int = 0
    # **걸러서 빈 것도 그렇다고 말한다.** 조용히 사라지면 "할 말이 없다" 와
    # 구별되지 않는다 (기준 5)
    걸러낸것: list[str] = field(default_factory=list)


def 평가조각(평가줄: list[str]) -> list[str]:
    """평가 줄을 **막을 만한 조각**으로 쪼갠다.

    줄 통째로 견주면 못 잡는다 — 실제로 걸린 것은
    `정하윤은 체력 약함이라 스트랩 발주를 맡깁니다` 처럼 **한 조각만 옮겨
    붙은 것**이었다. 그렇다고 아무 조각이나 막으면 `정하윤` 같은 이름까지
    막혀서, **담당을 적는 정상적인 문장이 함께 지워진다.**

    그래서 조건을 둘 다 건다 — 네 글자 이상이고, **평가로 읽히게 만든 그
    말(`약함`·`잘함`·MBTI …)을 실제로 품고 있을 것.** 그 말이 없으면 그
    조각은 평가가 아니라 그냥 사실이다.
    """
    말들 = tuple(meeting_import._평가말)
    조각: list[str] = []
    for 줄 in 평가줄:
        for 부분 in re.split(r"[,/·:;]| - ", 줄):
            짧 = re.sub(r"\s+", "", 부분)
            if len(짧) >= 4 and any(w in 부분 for w in 말들):
                조각.append(짧)
    return 조각


def 못읽었나(답: object, 읽은것: dict) -> str:
    """답이 왔는데 **읽지 못했는가.** 못 읽었으면 그 까닭을 한 줄로.

    2026-09-03 에 `26.08.09` 가 이랬다 —

        stop_reason: max_tokens · output_tokens 4000 (생각 3042)
        JSON 이 `"왜": "홍보영상의 8/9, 8/16 …` 에서 **문장 한가운데 잘림**

    잘린 JSON 은 `json_만` 이 `{}` 로 돌려주고, 화면에는 **"낼 것을 찾지
    못했습니다"** 가 떴다. 모델이 판단해서 없는 것과 우리가 못 읽은 것이
    **같은 모양**이었던 것이다 — 이 프로젝트가 가장 비싸다고 적어 둔 실패다.
    """
    # **`잘렸나` 속성이 아니라 값을 본다.** 속성으로 물으면 시험이 넣는
    # 가짜 대답에는 그 속성이 없어 조용히 다른 가지로 빠진다
    if getattr(답, "stop_reason", "") == "max_tokens":
        return ("답이 길어서 중간에 잘렸습니다"
                f" (생각에 {getattr(답, 'thinking_tokens', 0):,}토큰을 썼습니다)")
    if (getattr(답, "text", "") or "").strip() and not 읽은것:
        return "답이 왔는데 읽지 못했습니다 (JSON 이 아닙니다)"
    return ""


def 사람평가_섞였나(글: str, 평가줄: list[str]) -> bool:
    """그 글에 사람 평가 대목이 들어 있는가 (6단계).

    **보내는 것과 남기는 것은 다르다.** 회의록을 보내는 것은 막지 않되,
    제안에 그 대목이 인용돼 들어가면 논의로 남고 그러면 **회차를 볼 수 있는
    누구나 보게 된다** (4-9). 그래서 나온 제안 쪽에서 한 번 더 거른다 —
    프롬프트로만 막으면 안 지켜졌을 때 아무 표시가 없다.
    """
    납작 = re.sub(r"\s+", "", 글 or "")
    if not 납작:
        return False
    return any(x in 납작 for x in 평가조각(평가줄))


def _번호맵(rows: list[BoardRow]) -> dict[int, BoardRow]:
    return {x.run_id: x for x in rows}


def _2차를_부르나(후보: list[dict], 이력있는: set[int]) -> tuple[bool, str]:
    """**언제 2차를 부르는가** (3단계).

    조건은 하나다 — *1차가 논의 후보를 냈고, 그중 논의 이력이 있는 업무가
    하나라도 있을 때.* 이력이 없으면 2차가 볼 것이 없어서 같은 것을 한 번 더
    묻는 것이 되고, 값만 두 배가 된다.

    돌려주는 둘째 값은 **왜 안 불렀는지**다. 안 부른 것이 조용하면 나중에
    "2차가 도는 게 맞나" 를 코드를 읽어야 알 수 있다.
    """
    if not 후보:
        return False, "1차가 논의 후보를 내지 않았습니다"
    걸린것 = [x for x in 후보 if x.get("run_id") in 이력있는]
    if not 걸린것:
        return False, "후보 업무에 지난 논의가 없어 볼 것이 없습니다"
    return True, f"후보 {len(걸린것)}건에 지난 논의가 있습니다"


def _논의이력(db: Session, run_ids: list[int], 줄당: int = 400) -> str:
    """후보 업무들의 지난 논의만. **전체를 보내지 않는다** — 250건이면
    목록만으로 몇십 배가 된다 (2단계)."""
    번호 = [r for r in run_ids if isinstance(r, int)]
    if not 번호:
        return "(없음)"
    행 = db.scalars(
        select(DiscussionEntry)
        .where(DiscussionEntry.run_id.in_(번호))
        .order_by(DiscussionEntry.run_id, DiscussionEntry.authored_at)
    ).all()
    if not 행:
        return "(없음)"
    return "\n".join(f"[{e.run_id}] {e.authored_at} — {(e.body or '')[:줄당]}"
                     for e in 행)


def _제안으로(답: dict, 논의: list[dict], rows: list[BoardRow],
           meeting: Meeting, 평가줄: list[str], limit: int,
           걸러낸것: list[str] | None = None) -> list[제안]:
    """대답을 화면이 아는 모양으로 옮긴다.

    여기서 **두 가지를 거른다** — 판정 단어(4-10 조건 7)와 사람 평가(6단계).
    프롬프트로만 막으면 안 지켜졌을 때 아무 표시가 없다.
    """
    맵 = _번호맵(rows)
    나온것: list[제안] = []

    for x in (답.get("결정사항") or [])[:limit]:
        if not isinstance(x, dict):
            continue
        인용 = (x.get("인용") or "").strip()
        무엇 = (x.get("무엇") or "").strip()
        if not 인용:
            continue
        # **사람 평가가 섞이면 통째로 뺀다.** 결정사항은 인용이 본체라
        # 인용을 지우면 남는 것이 없다
        if 사람평가_섞였나(인용, 평가줄) or 사람평가_섞였나(무엇, 평가줄):
            if 걸러낸것 is not None:
                걸러낸것.append("사람 평가가 섞여 결정사항 1건을 뺐습니다")
            continue
        나온것.append(제안(
            kind="decision",
            text=판정단어_뺀다(무엇) if 무엇 else "회의에서 정해진 것으로 읽었습니다",
            why=판정단어_뺀다(무엇) if 무엇 else "회의에서 정해진 것으로 읽었습니다",
            quote=인용,                       # **회의록의 줄 그대로** (9번)
            meeting_id=meeting.id,
        ))

    for x in 논의[:limit]:
        row = 맵.get(x.get("run_id"))
        if row is None:
            # **조용히 버리지 않는다.** 모델이 없는 번호를 대면 그만큼 제안이
            # 줄어드는데, 줄어든 이유가 화면 어디에도 안 남는다
            if 걸러낸것 is not None:
                걸러낸것.append(f"목록에 없는 번호({x.get('run_id')})라 논의 1건을 뺐습니다")
            continue
        왜 = 판정단어_뺀다((x.get("왜") or "").strip())
        if 사람평가_섞였나(왜, 평가줄):
            왜 = "회의 내용이 이 업무의 사정으로 읽힙니다"
        나온것.append(제안(
            kind="discussion",
            text=f"{meeting.title} 의 내용을 이 업무의 논의로 남깁니다",
            why=왜 or "회의 내용이 이 업무의 사정으로 읽힙니다",
            run_id=row.run_id,
            run_title=row.title,
            meeting_id=meeting.id,
        ))

    for x in (답.get("새업무") or [])[:limit]:
        if not isinstance(x, dict):
            continue
        제목 = 판정단어_뺀다((x.get("제목") or "").strip())
        if not 제목:
            continue
        왜 = 판정단어_뺀다((x.get("왜") or "").strip())
        if 사람평가_섞였나(제목, 평가줄) or 사람평가_섞였나(왜, 평가줄):
            if 걸러낸것 is not None:
                걸러낸것.append("사람 평가가 섞여 새 업무 1건을 뺐습니다")
            continue
        상위 = 맵.get(x.get("상위_run_id"))
        나온것.append(제안(
            kind="new",
            text=f"새 업무로 만듭니다 — {제목}",
            why=왜 or "회의에 할 일로 나왔는데 목록에 없습니다",
            title=제목,
            parent_run_id=상위.run_id if 상위 else None,
            parent_title=상위.title if 상위 else None,
            department=(x.get("부서") or (상위.department if 상위 else None)),
            meeting_id=meeting.id,
        ))
    return 나온것


def 분석(db: Session, *, retreat: Retreat, meeting: Meeting,
        as_of: dt.date | None = None, limit: int = 5,
        부르기=None) -> 결과:
    """한 회의록을 **문장으로** 읽는다. 못 읽으면 낱말로 물러선다.

    `부르기` 는 시험이 넣는 자리다 — 실제 API 를 안 부르고도 이 함수의
    판단(2차 규칙·사람 평가 거르기·판정 단어)을 그대로 시험할 수 있어야 한다.
    """
    본문 = (meeting.body or "").strip()
    기준일 = as_of or meeting.meeting_date or dt.date.today()
    평가줄 = meeting_import.people_notes(본문) if 본문 else []

    def 물러선다(말: str, 실패: bool) -> 결과:
        return 결과(
            제안들=낱말제안(db, retreat=retreat, meeting=meeting,
                        as_of=기준일, limit=limit),
            방식="낱말", 말=말, 사람평가=평가줄, 실패=실패,
        )

    쓸것 = 부르기 or llm_mod.ask
    if 부르기 is None and not llm_mod.read_key():
        return 물러선다(llm_mod.상태().말, False)
    if not 본문:
        return 결과([], "문장", "회의 내용이 비어 있습니다.", 평가줄)

    rows = board_as_of(db, retreat, 기준일)
    if not rows:
        return 결과([], "문장", "이 회차에 업무가 없습니다.", 평가줄)
    목록 = catalog(rows)

    묶음: list = []
    try:
        일차 = 쓸것(
            _시스템,
            f"# 준비 업무 목록 ({len(rows)}건)\n{목록}\n\n"
            f"# 회의록\n제목: {meeting.title}\n"
            f"날짜: {기준일.isoformat()}\n\n{본문}\n\n"
            f"# 이 틀로 답하세요\n{_1차틀}",
        )
    except llm_mod.LlmUnavailable as exc:                        # noqa: BLE001
        return 물러선다(f"{exc} — 낱말이 겹치는 정도로만 골랐습니다.", True)
    묶음.append(일차)
    답 = llm_mod.json_만(일차.text)

    # **답은 왔는데 읽지 못한 경우를 `실패` 로 나눈다** (기준 4).
    # 여기서 안 나누면 "모델이 낼 것이 없다고 했다" 와 같은 모양이 된다
    if 못읽음 := 못읽었나(일차, 답):
        r = 물러선다(f"{못읽음} — 낱말이 겹치는 정도로만 골랐습니다.", True)
        r.원, r.글자수, r.부른횟수 = 일차.원, len(목록), 1
        r.입력토큰, r.출력토큰 = 일차.in_tokens, 일차.out_tokens
        r.생각토큰 = getattr(일차, "thinking_tokens", 0)
        return r

    후보 = [x for x in (답.get("논의후보") or []) if isinstance(x, dict)]
    번호들 = [x.get("run_id") for x in 후보 if isinstance(x.get("run_id"), int)]
    이력있는 = set()
    if 번호들:
        이력있는 = {
            r for (r,) in db.execute(
                select(DiscussionEntry.run_id)
                .where(DiscussionEntry.run_id.in_(번호들)).distinct())
        }
    부를까, 왜2 = _2차를_부르나(후보, 이력있는)
    논의 = [{"run_id": x.get("run_id"), "왜": x.get("왜") or ""} for x in 후보]
    if 부를까:
        try:
            이차 = 쓸것(
                _시스템,
                f"# 후보 업무의 지난 논의\n{_논의이력(db, 번호들)}\n\n"
                f"# 회의록\n제목: {meeting.title}\n\n{본문}\n\n"
                f"# 1차에서 고른 후보\n{json.dumps(후보, ensure_ascii=False)}\n\n"
                "지난 논의를 보고 **정말 이 업무의 사정인지** 다시 판단하세요.\n"
                "이미 같은 얘기가 남아 있으면 이미있음=true 로 표시하세요.\n"
                f"# 이 틀로 답하세요\n{_2차틀}",
            )
        except llm_mod.LlmUnavailable:                           # noqa: BLE001
            pass            # 1차 결과를 그대로 쓴다 — 있는 것을 버리지 않는다
        else:
            묶음.append(이차)
            둘 = llm_mod.json_만(이차.text).get("논의")
            if isinstance(둘, list):
                논의 = [x for x in 둘 if isinstance(x, dict)]

    걸러낸것: list[str] = []
    나온것 = _제안으로(답, 논의, rows, meeting, 평가줄, limit, 걸러낸것)
    원 = sum(getattr(x, "원", 0.0) for x in 묶음)
    입력 = sum(getattr(x, "in_tokens", 0) for x in 묶음)
    출력 = sum(getattr(x, "out_tokens", 0) for x in 묶음)
    생각 = sum(getattr(x, "thinking_tokens", 0) for x in 묶음)
    모델 = getattr(묶음[0], "model", llm_mod.MODEL)
    # **"읽고 골랐습니다" 는 화면이 말한다.** 여기서 또 쓰면 한 줄에 같은
    # 말이 두 번 뜬다 — 여기는 **사실만** 적는다 (모델·횟수·값·2차 여부)
    말 = (f"{모델} 에 {len(묶음)}번 물었고 약 {원:,.0f}원 들었습니다"
          f" (토큰 {입력:,}/{출력:,}). 2차: {왜2}.")
    if 걸러낸것:
        # **걸러서 빈 것도 그렇다고 말한다** (기준 5). 조용히 사라지면
        # "할 말이 없다" 와 구별되지 않는다
        말 += " " + " ".join(dict.fromkeys(걸러낸것))
    return 결과(나온것, "문장", 말, 평가줄, len(목록), 원, len(묶음),
              입력토큰=입력, 출력토큰=출력, 생각토큰=생각, 걸러낸것=걸러낸것)


def suggest_full(db: Session, *, retreat: Retreat, meeting: Meeting,
                 as_of: dt.date | None = None, limit: int = 5,
                 부르기=None) -> 결과:
    """화면이 쓰는 창구. `suggest()` 는 목록만 필요한 자리(시뮬레이션)가 쓴다."""
    return 분석(db, retreat=retreat, meeting=meeting, as_of=as_of,
              limit=limit, 부르기=부르기)


def suggest(db: Session, *, retreat: Retreat, meeting: Meeting,
            as_of: dt.date | None = None, limit: int = 5) -> list[제안]:
    """한 회의록을 읽고 제안한다. **여기가 유일한 창구다.**

    키가 있으면 문장으로 읽고, 없거나 못 부르면 낱말 겹침으로 물러선다.
    물러선 것을 아는 것이 중요하면 `suggest_full()` 을 쓴다 — 그쪽이
    방식과 값을 함께 낸다.
    """
    return 분석(db, retreat=retreat, meeting=meeting, as_of=as_of,
              limit=limit).제안들
