"""홈 (CLAUDE.md 4-15) — 숫자는 전부 여기서, 그리고 여기도 세지 않는다.

지표의 근거는 도메인 함수다 — 기한 초과는 `board.overdue_of`, 담당자 없는
마감 임박은 `escalation.unassigned_runs_due_soon`, 예산은
`budget.build_budget_summary`. **홈 라우터·템플릿에는 세는 코드가 없다** —
이 모듈이 그 함수들을 불러 모아 담고, 화면은 받아 그리기만 한다.

`today` 는 인자로 받는다 (5-2) — 폐회일 다음 날부터 결산 홈으로 바뀌는
분기(period.is_over)가 시각에 걸려 있어서, 주입할 수 없으면 시험이 날짜에
흔들린다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain import board, escalation, period
from app.domain import permissions as perm
from app.domain.board import overdue_of
from app.domain.budget import BudgetSummary, build_budget_summary
from app.models import Retreat, TaskRun, User

WEEK_DAYS = 7  # 「이번 주」 = 오늘 다음 날부터 7일 안


@dataclass
class HomeView:
    retreat: Retreat
    today: dt.date
    over: bool                       # period.is_over — 참이면 결산 홈 (4-15)

    # ── 보통 홈 ──────────────────────────────────────────────────────
    remaining: int = 0               # 남은 할 일 (미완료)
    done: int = 0
    total: int = 0
    overdue_count: int = 0           # board.overdue_of 계산값 — 저장된 '지연' 이 아니다
    unassigned_soon_count: int = 0   # escalation — 담당자 없이 마감 7일 이내
    budget: BudgetSummary | None = None
    top_categories: list = field(default_factory=list)   # 지출 상위 (CategorySummary)
    my_today: list = field(default_factory=list)         # 내 담당 · 마감 ≤ 오늘 · 미완료
    # 내 부서**들**의 미완료 업무 중 담당자가 없는 것 — 부서마다 한 줄
    # (키 · 이름 · 수). 링크가 `?dept=키` 하나를 받으므로 부서마다 따로 낸다 (도막 4)
    mine_unassigned: list = field(default_factory=list)
    my_dept_keys: set = field(default_factory=set)   # 내 부서 키 집합 (2장 · 도막 4)
    week: list = field(default_factory=list)             # 미완료 · 오늘 뒤 7일 안 마감
    overdue_ids: set = field(default_factory=set)        # 행의 지연 배지도 계산값에서 (4-10)
    dim_ids: set = field(default_factory=set)            # 소속 외 행 — 부서는 **키로** 비교 (2장)
    badges: dict = field(default_factory=dict)           # run_id → board.paint_of 의 badge (4-3)

    # ── 결산 홈 ──────────────────────────────────────────────────────
    unpaid_refund_count: int = 0     # budget.refund_entries — 개인이 냈는데 미지급
    no_receipt_count: int = 0        # budget.no_receipt_entries — ExpenseReceipt 0건
    open_task_count: int = 0         # 미완료 업무 (정리 필요)


TOP_CATEGORY_COUNT = 6


def _runs(db: Session, retreat: Retreat) -> list[TaskRun]:
    return list(
        db.scalars(
            select(TaskRun)
            .where(TaskRun.retreat_id == retreat.id, TaskRun.included.is_(True))
            .options(
                selectinload(TaskRun.library),
                selectinload(TaskRun.department),
                selectinload(TaskRun.assignee),
            )
        )
    )


def _end_of(run: TaskRun) -> dt.date | None:
    return run.end_date or run.start_date


def build(db: Session, retreat: Retreat, user: User, *, today: dt.date) -> HomeView:
    runs = _runs(db, retreat)
    open_runs = [r for r in runs if r.status != "완료"]
    view = HomeView(retreat=retreat, today=today, over=period.is_over(retreat, today))

    if view.over:
        # 결산 홈 — 경고 띠·지연 지표 대신 정리할 것을 낸다 (4-15).
        # 숫자는 지출 필터와 **같은 함수**다 — 홈의 N 을 눌러 간 화면
        # (?filter=refund · ?filter=noreceipt)의 행 수와 같아야 한다.
        from app.domain.budget import no_receipt_entries, refund_entries

        view.unpaid_refund_count = len(refund_entries(db, retreat))
        view.no_receipt_count = len(no_receipt_entries(db, retreat))
        view.open_task_count = len(open_runs)
        view.budget = build_budget_summary(db, retreat=retreat)
        view.done = len(runs) - len(open_runs)
        view.total = len(runs)
        return view

    view.remaining = len(open_runs)
    view.done = len(runs) - len(open_runs)
    view.total = len(runs)
    view.overdue_ids = {r.id for r in open_runs if overdue_of(r, today)}
    view.overdue_count = len(view.overdue_ids)
    view.unassigned_soon_count = len(
        escalation.unassigned_runs_due_soon(runs, today=today)
    )

    view.budget = build_budget_summary(db, retreat=retreat)
    view.top_categories = sorted(
        view.budget.categories, key=lambda row: -row.spent
    )[:TOP_CATEGORY_COUNT]

    view.my_today = sorted(
        (
            r
            for r in open_runs
            if r.assignee_id == user.id and _end_of(r) and _end_of(r) <= today
        ),
        key=_end_of,
    )
    # **내 할 일이 비었을 때 낼 것** (4-15). 담당자가 안 정해진 업무는
    # 「누구 일도 아닌 것」 이라 아무 화면에도 안 뜨는데, 그게 정확히
    # 놓치는 지점이다 (달력의 「날짜 없는 업무」 와 같은 자리 · 4-13).
    # **부서는 키로 본다** (2장) — id 로 보면 새 회차가 열리는 순간 0 이
    # 되고, 0 이면 화면이 아무 말도 안 해서 왜 없어졌는지 알 수 없다.
    view.my_dept_keys = perm.my_dept_keys(user)
    names = {d.key: d.name for d in retreat.departments if d.key}
    for key in sorted(view.my_dept_keys):
        n = sum(1 for r in open_runs
                if r.assignee_id is None
                and (r.department.key if r.department else None) == key)
        if n:
            view.mine_unassigned.append({"key": key, "name": names.get(key, key), "count": n})
    view.week = sorted(
        (
            r
            for r in open_runs
            if _end_of(r) and today < _end_of(r) <= today + dt.timedelta(days=WEEK_DAYS)
        ),
        key=_end_of,
    )
    # 배지는 한 곳에서 만든다 (board.paint_of · 4-3) — 화면은 받아 그리기만 한다
    view.badges = {
        r.id: board.paint_of(r, today)["badge"] for r in view.my_today + view.week
    }

    # 소속 외 흐림 — id 로 비교하면 새 회차가 열리는 순간 자기 부서까지 흐려진다 (2장).
    # 총무팀(admin)은 전부 선명하다 (9장의 소속 외 규칙과 같다)
    if not perm.is_admin(user) and view.my_dept_keys:
        view.dim_ids = {
            r.id
            for r in runs
            if (r.department.key if r.department else None) not in view.my_dept_keys
        }
    return view
