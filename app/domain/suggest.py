"""회의록을 읽고 제안한다 — **창구는 한 곳** (CLAUDE.md 회의록 4단계).

회의록 화면에서 부르든 나중에 채팅으로 부르든 **읽고 제안하는 길은 여기
하나**다. 두 벌이 되면 이 프로젝트가 다섯 번 고쳐 온 그 모양이 다시 난다
(색·기간·툴팁·`onOpen`·`onAssignee`).

## 두 가지를 낸다

1. **새 업무** — 회의에서 나왔는데 보드에 없는 것
2. **이미 있는 업무에 붙일 논의** — 그 회의 내용이 어느 업무의 사정인지

**둘째가 더 어렵다.** 250건 중 하나를 고르는 일이고, 틀리면 남의 회의 내용이
엉뚱한 업무에 남는다. 그래서 제안마다 **왜 그 업무인지**를 함께 낸다 (6-3).

## 지키는 것 (4-10 의 조건들)

- **판정 단어를 쓰지 않는다** (조건 7) — `진행 불가`·`진행 가능`·`일부 진행
  가능`·`완료`. 코드가 판정에 안 넣어도 사람은 판정으로 읽는다
- **할 말이 없으면 빈 목록을 낸다** (조건 4). 억지로 만들면 근거 없는 제안이 된다
- **실패해도 화면은 살아 있다** (조건 8) — 부르는 쪽이 빈 목록을 받는다
- **아무것도 자동으로 반영되지 않는다.** 사람이 하나씩 고른다

## 그 시점의 보드만 본다 (3단계)

`as_of` 를 받아 **그때 알 수 있었던 것만** 본다 — 업무 이름·부서·기간.
8월 상태(`status`·`completed_at`)를 함께 주면 이미 끝난 일을 알고 제안하는데,
그러면 잘 맞히는 것처럼 보인다 — **시뮬레이션이 성립하지 않는다.**

**가리는 것은 존재가 아니라 상태다.** 처음에는 "시작일이 지난 것만" 으로
걸렀다가 6월 회의에 제안이 하나도 안 나와서 틀렸다는 것을 알았다 —
6월 회의가 8월 업무를 얘기하는 것은 자연스럽다 (`board_as_of`).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Meeting, Retreat, TaskRun

# 4-10 이 쓰는 판정 단어. **출력에 나오면 안 된다.**
판정단어 = ("진행 불가", "진행 가능", "일부 진행", "완료", "지연")


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
    kind: str                       # 'new' | 'discussion'
    text: str                       # 사람이 읽을 제안 내용
    why: str                        # **왜 그 업무인지** (6-3)
    run_id: int | None = None       # discussion 일 때 붙일 업무
    run_title: str | None = None
    meeting_id: int | None = None   # 어느 회의록에서 왔는가 (출처)
    evidence: list[str] = field(default_factory=list)


def board_as_of(db: Session, retreat: Retreat, as_of: dt.date) -> list[BoardRow]:
    """그 시점의 보드. **가리는 것은 '존재' 가 아니라 '상태' 다.**

    처음에는 "시작일이 지난 것만" 으로 걸렀다가 **틀렸다는 것을 확인했다** —
    6월 회의가 8월 업무를 얘기하는 것은 자연스럽다. 업무 목록은 회차를 열
    때 이미 다 정해져 있고(6-6 마법사), 그때도 보드에 보인다.

    가리면 안 되는 것은 **나중에 알게 된 것**이다 — `status` · `completed_at` ·
    `started_at`. 8월의 완료 여부를 6월 제안에 쓰면 이미 끝난 일을 알고
    제안하는 것이고, 그러면 잘 맞히는 것처럼 보인다.
    **시뮬레이션이 성립하지 않는다.**

    그래서 `TaskRun` 을 그대로 넘기지 않고 **그때 알 수 있었던 것만** 담은
    `BoardRow` 로 옮겨 담는다. 넘기면 부르는 쪽이 `.status` 를 볼 수 있고,
    볼 수 있으면 언젠가 본다.
    """
    runs = db.scalars(
        select(TaskRun).where(TaskRun.retreat_id == retreat.id, TaskRun.included)
    ).all()
    return [
        BoardRow(
            run_id=r.id,
            title=r.library.title or "",
            department=r.department.name if r.department else None,
            start=r.start_date,
            end=r.end_date,
        )
        for r in runs
    ]


def _낱말(text: str) -> set[str]:
    """견줄 낱말. 두 글자 이상의 한글·영문 덩이만."""
    return {w for w in re.findall(r"[가-힣A-Za-z]{2,}", text)}


def 겹침(a: str, b: str) -> tuple[int, list[str]]:
    """두 글의 겹치는 낱말 수와 그 낱말들. **왜 그 업무인지의 근거**가 된다."""
    공통 = sorted(_낱말(a) & _낱말(b), key=len, reverse=True)
    return len(공통), 공통[:5]


def 판정단어_뺀다(text: str) -> str:
    """출력에서 판정 단어를 지운다 (4-10 조건 7).

    코드가 판정에 안 넣어도, 요약이 "진행 불가로 보입니다" 라고 쓰면 사람은
    판정으로 읽는다. 패널 이름이 판정 결과인 화면이라 더 그렇다.
    """
    for w in 판정단어:
        text = text.replace(w, "…")
    return text


def suggest(db: Session, *, retreat: Retreat, meeting: Meeting,
            as_of: dt.date | None = None, limit: int = 5) -> list[제안]:
    """한 회의록을 읽고 제안한다. **여기가 유일한 창구다.**

    지금은 낱말이 겹치는 정도로 고른다 — 문장을 읽는 것은 다음 단계다.
    그래도 **근거는 지금부터 낸다**(겹친 낱말). 근거 없는 제안은 신뢰를 잃고,
    한 번 잃으면 돌아오지 않는다 (6-3).
    """
    본문 = (meeting.body or "").strip()
    if not 본문:
        return []                                   # 할 말이 없으면 빈 목록
    기준일 = as_of or meeting.meeting_date or dt.date.today()
    runs = board_as_of(db, retreat, 기준일)
    if not runs:
        return []

    점수 = []
    for row in runs:
        n, 낱말 = 겹침(본문, row.title)
        if n >= 2:                     # 한 낱말만 겹친 것은 우연이 너무 많다
            점수.append((n, 낱말, row))
    점수.sort(key=lambda x: (-x[0], x[2].title))

    나온것: list[제안] = []
    for n, 낱말, row in 점수[:limit]:
        나온것.append(제안(
            kind="discussion",
            text=판정단어_뺀다(f"{meeting.title} 의 내용을 이 업무의 논의로 남깁니다"),
            why=f"회의록과 업무 이름에 '{', '.join(낱말)}' 이(가) 함께 나옵니다"
                f" (겹친 낱말 {n}개)",
            run_id=row.run_id,
            run_title=row.title,
            meeting_id=meeting.id,
            evidence=낱말,
        ))
    return 나온것


def simulate(db: Session, *, retreat: Retreat, until: dt.date,
             limit: int = 5) -> list[tuple[Meeting, list[제안]]]:
    """`until` 까지의 회의록을 **시간순으로 하나씩** 넣으면서 그때 무엇을
    제안하는지 본다 (3단계).

    **그 시점의 보드만 쓴다** — 각 회의의 `as_of` 는 그 회의 날짜다.
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
