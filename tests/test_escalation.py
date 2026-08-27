"""위험 감지 / 에스컬레이션 규칙 테스트.

이 프로젝트의 존재 이유에 해당하는 부분 — 담당자가 놓쳐도 시스템이 대신 알아차린다.
"""

import datetime as dt

from app.domain.escalation import (
    RISK_DUE_SOON,
    RISK_OVERDUE,
    RISK_UNASSIGNED,
    RISK_BLOCKER_LATE,
    scan_risks,
    tasks_to_mark_delayed,
)
from app.models import Task

TODAY = dt.date(2026, 7, 1)


def make_task(
    task_id: int,
    *,
    status: str = "대기",
    due: dt.date | None = None,
    assignee_id: int | None = 10,
    blocked_by: list[int] | None = None,
    department_id: int | None = 1,
) -> Task:
    return Task(
        id=task_id,
        retreat_id=1,
        title=f"할일{task_id}",
        status=status,
        due_date=due,
        assignee_id=assignee_id,
        department_id=department_id,
        blocked_by_task_ids=blocked_by or [],
    )


def kinds(risks) -> list[str]:
    return [r.kind for r in risks]


# ------------------------------------------------------------------ 지연


def test_기한이_지난_미완료_할일은_지연으로_감지한다():
    task = make_task(1, due=TODAY - dt.timedelta(days=1))

    risks = scan_risks([task], today=TODAY)

    assert kinds(risks) == [RISK_OVERDUE]
    assert risks[0].task is task
    assert "1일" in risks[0].message


def test_기한이_지나도_완료된_할일은_감지하지_않는다():
    task = make_task(1, status="완료", due=TODAY - dt.timedelta(days=5))

    assert scan_risks([task], today=TODAY) == []


def test_기한이_지난_할일은_상태를_지연으로_자동_전환한다():
    late = make_task(1, status="진행중", due=TODAY - dt.timedelta(days=1))
    on_time = make_task(2, status="진행중", due=TODAY)
    done = make_task(3, status="완료", due=TODAY - dt.timedelta(days=3))
    already = make_task(4, status="지연", due=TODAY - dt.timedelta(days=2))

    result = tasks_to_mark_delayed([late, on_time, done, already], today=TODAY)

    assert [t.id for t in result] == [1]


# ------------------------------------------------------------------ 기한 임박


def test_마감_3일전_1일전_당일에_알린다():
    d3 = make_task(1, due=TODAY + dt.timedelta(days=3))
    d1 = make_task(2, due=TODAY + dt.timedelta(days=1))
    d0 = make_task(3, due=TODAY)

    risks = scan_risks([d3, d1, d0], today=TODAY)

    assert kinds(risks) == [RISK_DUE_SOON] * 3


def test_마감_2일전에는_알리지_않는다():
    # D-3, D-1, 당일만 리마인드 (매일 알림이 쌓여 무뎌지지 않게)
    d2 = make_task(1, due=TODAY + dt.timedelta(days=2))
    d5 = make_task(2, due=TODAY + dt.timedelta(days=5))

    assert scan_risks([d2, d5], today=TODAY) == []


# ------------------------------------------------------------------ 담당자 미지정


def test_담당자가_없는데_기한이_7일_이내면_총무팀에_에스컬레이션한다():
    task = make_task(1, assignee_id=None, due=TODAY + dt.timedelta(days=6))

    risks = scan_risks([task], today=TODAY)

    assert RISK_UNASSIGNED in kinds(risks)
    unassigned = next(r for r in risks if r.kind == RISK_UNASSIGNED)
    assert unassigned.escalate_to_admin is True


def test_담당자가_없어도_기한이_멀면_아직_알리지_않는다():
    task = make_task(1, assignee_id=None, due=TODAY + dt.timedelta(days=20))

    assert scan_risks([task], today=TODAY) == []


def test_담당자도_기한도_없는_할일은_감지하지_않는다():
    # 언제까지인지 정해지지 않은 아이디어 수준의 할 일까지 알리면 소음이 된다
    task = make_task(1, assignee_id=None, due=None)

    assert scan_risks([task], today=TODAY) == []


# ------------------------------------------------------------------ 선행 지연


def test_선행_작업이_지연되면_후행_담당자에게도_알린다():
    blocker = make_task(1, status="진행중", due=TODAY - dt.timedelta(days=2))
    follower = make_task(2, blocked_by=[1], due=TODAY + dt.timedelta(days=10))

    risks = scan_risks([blocker, follower], today=TODAY)

    assert RISK_BLOCKER_LATE in kinds(risks)
    late = next(r for r in risks if r.kind == RISK_BLOCKER_LATE)
    assert late.task is follower
    assert late.related_task is blocker
    assert late.escalate_to_admin is True


def test_선행이_제때_진행중이면_후행은_위험이_아니다():
    blocker = make_task(1, status="진행중", due=TODAY + dt.timedelta(days=5))
    follower = make_task(2, blocked_by=[1], due=TODAY + dt.timedelta(days=10))

    assert kinds(scan_risks([blocker, follower], today=TODAY)) == []


def test_선행이_완료됐으면_후행은_위험이_아니다():
    blocker = make_task(1, status="완료", due=TODAY - dt.timedelta(days=2))
    follower = make_task(2, blocked_by=[1], due=TODAY + dt.timedelta(days=10))

    assert scan_risks([blocker, follower], today=TODAY) == []


# ------------------------------------------------------------------ 중복 방지


def test_같은_상황은_같은_dedupe_키를_만든다():
    task = make_task(1, due=TODAY - dt.timedelta(days=1))

    first = scan_risks([task], today=TODAY)[0]
    second = scan_risks([task], today=TODAY)[0]

    assert first.dedupe_key == second.dedupe_key


def test_날짜가_바뀌면_기한임박_알림은_다시_나간다():
    task = make_task(1, due=TODAY + dt.timedelta(days=3))
    tomorrow_task = make_task(1, due=TODAY + dt.timedelta(days=1))

    d3 = scan_risks([task], today=TODAY)[0]
    d1 = scan_risks([tomorrow_task], today=TODAY)[0]

    assert d3.dedupe_key != d1.dedupe_key


def test_지연_알림은_날짜가_지날수록_다시_나간다():
    yesterday = make_task(1, due=TODAY - dt.timedelta(days=1))
    week_ago = make_task(1, due=TODAY - dt.timedelta(days=7))

    assert (
        scan_risks([yesterday], today=TODAY)[0].dedupe_key
        != scan_risks([week_ago], today=TODAY)[0].dedupe_key
    )
