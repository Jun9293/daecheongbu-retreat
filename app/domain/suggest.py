"""회의록을 읽고 제안한다 — **창구는 한 곳** (CLAUDE.md 회의록 4단계).

회의록 화면에서 부르든 나중에 채팅으로 부르든 **읽고 제안하는 길은 여기
하나**다. 두 벌이 되면 이 프로젝트가 다섯 번 고쳐 온 그 모양이 다시 난다
(색·기간·툴팁·`onOpen`·`onAssignee`).

## 두 가지를 낸다

1. **논의** — 그 회의 내용이 어느 업무의 사정인지 (`kind='discussion'`)
2. **새 업무** — 회의에 할 일처럼 적혔는데 보드의 **어느 이름과도 겹치지
   않는 것** (`kind='new'`)

**첫째가 더 어렵다.** 250건 중 하나를 고르는 일이고, 틀리면 남의 회의 내용이
엉뚱한 업무에 남는다. 그래서 제안마다 **왜 그 업무인지**를 함께 낸다 (6-3).

## 아직 문장을 읽지 않는다

**지금 고르는 방법은 낱말 겹침뿐이다.** 회의록과 업무 이름에 같은 낱말이
둘 이상 나오면 논의 후보로 내고, 할 일처럼 생긴 줄인데 어느 업무 이름과도
안 겹치면 새 업무 후보로 낸다.

**그 사실을 화면이 사람에게 말한다.** 감추면 실제로 어떤지 영영 모르지만,
감추지 않는 것만으로는 부족하다 — 위험한 것은 틀린 제안이 아니라 **사람이
처음에 세우는 기대**다. "읽고 제안했다" 로 읽히면 몇 번 엉뚱한 것을 보고
다시 안 쓴다. 한 번 잃으면 안 돌아온다 (6-3).

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
다 정해져 있다 (6-6). 가리면 안 되는 것은 `status`·`completed_at` 처럼
**나중에 알게 된 것**이다.
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
    """그 시점에 **알 수 있었던 것만.** 상태는 담지 않는다 — 담으면 본다."""

    run_id: int
    title: str
    department: str | None
    start: dt.date | None
    end: dt.date | None


@dataclass
class 제안:
    kind: str                       # 'discussion' | 'new'
    text: str                       # 사람이 읽을 제안 내용
    why: str                        # **왜 그 업무인지** (6-3)
    run_id: int | None = None       # discussion 일 때 붙일 업무
    run_title: str | None = None
    meeting_id: int | None = None   # 어느 회의록에서 왔는가 (출처)
    evidence: list[str] = field(default_factory=list)


def board_as_of(db: Session, retreat: Retreat, as_of: dt.date) -> list[BoardRow]:
    """그 시점의 보드.

    **`as_of` 를 받아 두고 쓰지 않는다.** 존재를 가리지 않기로 했기 때문이다
    (머리말). 그래도 인자를 남기는 이유는 부르는 쪽이 "언제 기준인가" 를
    **의식하고 넘기게** 하기 위해서다 — 빼 버리면 시뮬레이션에서 날짜를 안
    넘겨도 아무 일이 없고, 나중에 기간으로 거를 일이 생겼을 때 그 자리가 없다.
    지금 실제로 하는 일은 **상태를 안 담는 것** 하나다.

    **`board.load_runs` 를 쓴다.** 직접 `select(TaskRun)` 을 하면 `library` ·
    `department` 를 건건이 읽어 N+1 이 난다 — 실제로 그랬다(업무 96건에
    107쿼리). `load_runs` 는 셋을 미리 붙여 온다.
    """
    return [
        BoardRow(
            run_id=r.id,
            title=r.library.title or "",
            department=r.department.name if r.department else None,
            start=r.start_date,
            end=r.end_date,
        )
        for r in board_domain.load_runs(db, retreat)
    ]


def _낱말(text: str) -> set[str]:
    """견줄 낱말. 두 글자 이상의 한글·영문 덩이만."""
    return {w for w in re.findall(r"[가-힣A-Za-z]{2,}", text)}


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
        말 = re.sub(r"<[^>]+>", "", line).strip(" \t-•◦▪*")
        말 = re.sub(r"^\d+[.)]\s*", "", 말).strip()
        if not (6 <= len(말) <= 60):
            continue
        if not any(x in 말 for x in _할일말):
            continue
        if len(_낱말(말)) < 2:
            continue
        나온것.append(말)
    return 나온것


def suggest(db: Session, *, retreat: Retreat, meeting: Meeting,
            as_of: dt.date | None = None, limit: int = 5) -> list[제안]:
    """한 회의록을 읽고 제안한다. **여기가 유일한 창구다.**"""
    본문 = (meeting.body or "").strip()
    if not 본문:
        return []                                   # 할 말이 없으면 빈 목록
    기준일 = as_of or meeting.meeting_date or dt.date.today()
    rows = board_as_of(db, retreat, 기준일)
    if not rows:
        return []

    나온것: list[제안] = []

    # ── ① 논의 — 이미 있는 업무에 붙일 것 ────────────────────────────
    점수 = []
    for row in rows:
        n, 낱말 = 겹침(본문, row.title)
        if n >= 2:                     # 한 낱말만 겹친 것은 우연이 너무 많다
            점수.append((n, 낱말, row))
    점수.sort(key=lambda x: (-x[0], x[2].title))
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

    # ── ② 새 업무 — 보드의 어느 이름과도 안 겹치는 할 일 ──────────────
    보드낱말 = [_낱말(r.title) for r in rows]
    for 말 in 할일줄(본문)[: limit * 4]:
        말낱말 = _낱말(말)
        if any(len(말낱말 & t) >= 2 for t in 보드낱말):
            continue                   # 이미 있는 업무 이야기다
        나온것.append(제안(
            kind="new",
            # 회의록의 문장은 **사람의 원문**이라 그대로 붙인다
            text=판정단어_뺀다("새 업무로 만듭니다 — ") + 말,
            why="회의록에 할 일처럼 적혔는데 보드의 어느 업무 이름과도"
                f" 두 낱말 이상 겹치지 않습니다 (보드 {len(rows)}건과 견줬습니다)",
            meeting_id=meeting.id,
            evidence=sorted(말낱말)[:5],
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
