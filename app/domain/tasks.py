"""업무(라이브러리 + 이번 회차 run)를 **만드는 곳은 여기 하나다** (14장).

보드의 「새로 만들기」 와 회의록 쪽(항목 전환 · 제안 반영)이 같은 함수를
부른다. 두 벌이던 시절에 제목 자르기 하나가 이미 갈렸다 — 같은 것이 두
곳에 있으면 반드시 갈리고, 갈린 쪽을 아무도 눈치채지 못한다.

여기 없는 만들기는 **모양이 달라서** 그대로 둔다 — 개수를 세어 두지
않는다(10장: 도구가 자라면 자리도 늘어난다). 목록의 정본은
`tests/test_stage12.py` 의 g01 허용 목록이다:

- `domain/library.create_retreat` — 회차 개설의 **일괄** 생성. 라이브러리
  전체에 run 을 만들고(미선택도 included=False 로), 번호를 1부터 매기고,
  지난 논의를 실어 온다 — 일회성 업무 하나를 만드는 이 함수와 다른 일이다
- `routers/board.add_existing` — **이미 있는** 라이브러리를 run 으로.
  라이브러리를 만들지 않는다
- `routers/library.create_library_task` — 라이브러리 **항목만** (회차가
  없어도 된다). run 을 만들지 않는다

갈렸던 것은 **더 안전한 쪽**으로 맞췄다:

- 제목: strip + 200자 자름 (전환 쪽에만 있었다 — DB 가 String(200) 이라
  자르지 않으면 다른 DB 백엔드에서 터진다) · 빈 제목 거절 (양쪽에 있었다)
- 분류 검증 · 하위는 상위 필수 (add_new 쪽에만 있었다)
- 마감 < 시작 거절 (add_new 쪽에만 있었다)
- 날짜 없음 허용 (전환 쪽에만 있었다 — 달력의 「날짜 없는 업무」, 4-13)
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TASK_KINDS, Department, Retreat, TaskLibrary, TaskRun


def 제목다듬기(title: str) -> str:
    """저장될 제목 — 앞뒤 공백을 떼고 200자에서 자른다.

    **다듬는 규칙도 한 곳이다.** 만들 때와 「이미 만들었나」 를 셀 때가
    다르게 다듬으면, 같은 제목이 서로 다른 것으로 읽혀 두 번 만들어진다.
    """
    return title.strip()[:200]


def made_from_meeting(db: Session, retreat: Retreat, meeting_id: int) -> dict:
    """그 회의록에서 만들어진 이번 회차의 업무 — `{제목: run}`.

    **저장하지 않고 셈한다.** 제안은 `Meeting.suggest_json` 에 통째로
    들어 있고 본문이 바뀌면 새로 쓰이므로, 거기에 run_id 를 적어 두면
    다시 읽는 순간 사라진다 — 그러면 단추가 되살아나 같은 업무가 하나
    더 생긴다(막으려던 바로 그것). 출처의 정본은
    `TaskRun.source_meeting_id` 하나이고(4-9 와 같은 원칙), 제목이 그
    회의에서 그 제안의 이름이다.

    **범위는 그 회의록에서 온 이번 회차의 업무 전부다** — 항목 전환으로
    만든 것도, 이번 회차에서 뺀 것(`included=False`)도 센다.

    - 전환으로 만든 것을 안 세면 제안을 눌러 **같은 이름이 목록에 둘**
      선다 — 같은 회의록·같은 제목이면 같은 업무다
    - **뺀 것도 센다.** 안 세면 제안을 다시 눌러 새로 만들게 되는데,
      `create_run` 은 늘 새 라이브러리 행을 만들므로 **같은 제목의
      라이브러리가 둘**이 되고 6-2 의 실행 이력이 두 줄로 갈린다.
      「목록에 없는 것을 가리킨다」 는 문제는 화면이 푼다 — 그 제안에
      「빼 둔 업무입니다」 와 **되살리기**를 낸다 (4-14 · 12장)
    """
    rows = db.scalars(
        select(TaskRun)
        .join(TaskLibrary, TaskLibrary.id == TaskRun.library_id)
        .where(
            TaskRun.retreat_id == retreat.id,
            TaskRun.source_meeting_id == meeting_id,
        )
    )
    # 같은 제목이 둘이면 **먼저 만든 것**을 가리킨다 — 나중 것으로 가면
    # 링크가 옮겨 다닌다
    나온것: dict = {}
    for run in sorted(rows, key=lambda r: r.id):
        나온것.setdefault(제목다듬기(run.library.title), run)
    return 나온것


def create_run(
    db: Session,
    retreat: Retreat,
    *,
    title: str,
    kind: str = "main",
    department: Department | None = None,
    parent_library_id: int | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
    assignee_id: int | None = None,
    source_meeting_id: int | None = None,
) -> tuple[TaskLibrary, TaskRun]:
    """일회성 업무 하나 — 라이브러리 항목 + 이번 회차의 run.

    검증(제목·분류·날짜)에 걸리면 ValueError 를 낸다 — 부르는 라우터가
    400 으로 옮긴다. **권한은 여기서 보지 않는다** — 경로마다 문이 다르다
    (보드는 부서 편집 검사, 전환은 항목의 부서로 — 각 라우터에).
    커밋과 활동기록도 부르는 쪽 몫이다 — 남길 말이 경로마다 다르다.
    """
    from app.domain import board as board_domain
    from app.domain import dweek
    from app.domain import library as lib_domain

    title = 제목다듬기(title)
    if not title:
        raise ValueError("업무 이름을 입력해주세요.")
    if kind not in TASK_KINDS:
        raise ValueError("알 수 없는 분류입니다.")
    if kind == "sub" and parent_library_id is None:
        raise ValueError("하위 업무는 상위 업무를 골라야 합니다.")
    end = end or start
    if start and end and end < start:
        raise ValueError("마감이 시작보다 빠릅니다.")

    # 고른 날짜를 라이브러리의 상대 위치로 되돌려 둔다 (다음 회차에서 다시
    # 계산된다). 날짜가 없으면 상대 위치도 없다 — 지어내지 않는다.
    rel = (
        dweek.relative_position(retreat.start_date, start, end)
        if start and retreat.start_date
        else {}
    )
    lib = TaskLibrary(
        title=title,
        kind=kind,
        parent_library_id=parent_library_id,
        # 키가 없는 부서(구설계)는 None — run 의 department_id 로는 남는다
        default_department_key=department.key if department else None,
        related_department_keys=[],
        related_library_ids=[],
        origin="history",
        **rel,
    )
    db.add(lib)
    db.flush()
    run = TaskRun(
        library_id=lib.id,
        retreat_id=retreat.id,
        included=True,
        department_id=department.id if department else None,
        assignee_id=assignee_id,
        d_week=lib.default_d_week,
        start_date=start,
        end_date=end,
        status="대기",
        run_no=lib_domain.next_run_no(db, retreat.id),  # max+1 (4-14)
        source_meeting_id=source_meeting_id,  # 출처 — 업무 쪽에 (8장)
    )
    db.add(run)
    db.flush()
    # 새로 만든 업무도 라이브러리의 선행을 잇는다 — 여기가 없으면 링크가
    # 비어 그 업무는 조용히 '진행 가능' 이 된다 (4-10)
    board_domain.relink_prerequisites(db, retreat)
    return lib, run
