"""할 일 선후행 의존성 로직 테스트.

설계 원칙: 선행 작업이 끝나면 후행 작업이 '대기' → '시작 가능'으로 자동 전환되고,
선행이 늦어지면 후행 담당자와 총무팀에게 동시에 드러나야 한다.
"""

import pytest

from app.domain.dependencies import (
    CycleError,
    blocking_tasks,
    build_blocker_map,
    is_blocked,
    newly_unblocked,
    validate_blockers,
)
from app.models import Task


def make_task(task_id: int, *, status: str = "대기", blocked_by: list[int] | None = None) -> Task:
    return Task(
        id=task_id,
        retreat_id=1,
        title=f"할일{task_id}",
        status=status,
        blocked_by_task_ids=blocked_by or [],
    )


def test_선행_작업이_없으면_막혀있지_않다():
    task = make_task(1)

    assert is_blocked(task, {}) is False


def test_선행_작업이_완료되지_않았으면_막혀있다():
    blocker = make_task(1, status="진행중")
    task = make_task(2, blocked_by=[1])

    assert is_blocked(task, {1: blocker}) is True


def test_선행_작업이_모두_완료되면_풀린다():
    blocker = make_task(1, status="완료")
    task = make_task(2, blocked_by=[1])

    assert is_blocked(task, {1: blocker}) is False


def test_선행_작업이_여러개면_하나라도_미완료일_때_막혀있다():
    done = make_task(1, status="완료")
    ongoing = make_task(2, status="진행중")
    task = make_task(3, blocked_by=[1, 2])

    assert is_blocked(task, {1: done, 2: ongoing}) is True
    assert [t.id for t in blocking_tasks(task, {1: done, 2: ongoing})] == [2]


def test_삭제된_선행_작업은_막는_것으로_보지_않는다():
    # 선행 작업이 지워졌는데 후행이 영원히 막히면 안 된다
    task = make_task(2, blocked_by=[999])

    assert is_blocked(task, {}) is False


def test_선행_작업이_완료되면_풀린_후행_작업을_알려준다():
    blocker = make_task(1, status="완료")
    unblocked = make_task(2, blocked_by=[1])
    still_blocked = make_task(3, blocked_by=[1, 4])
    other_blocker = make_task(4, status="대기")
    unrelated = make_task(5)

    result = newly_unblocked(
        completed_task_id=1,
        tasks=[blocker, unblocked, still_blocked, other_blocker, unrelated],
    )

    assert [t.id for t in result] == [2]


def test_이미_완료된_후행_작업은_풀림_대상이_아니다():
    blocker = make_task(1, status="완료")
    already_done = make_task(2, status="완료", blocked_by=[1])

    result = newly_unblocked(completed_task_id=1, tasks=[blocker, already_done])

    assert result == []


def test_자기_자신을_선행으로_지정할_수_없다():
    task = make_task(1)

    with pytest.raises(CycleError):
        validate_blockers(task_id=1, blocker_ids=[1], blocker_map=build_blocker_map([task]))


def test_서로를_선행으로_지정하는_순환은_거부한다():
    a = make_task(1, blocked_by=[2])
    b = make_task(2)

    with pytest.raises(CycleError):
        validate_blockers(task_id=2, blocker_ids=[1], blocker_map=build_blocker_map([a, b]))


def test_간접_순환도_거부한다():
    # 1 ← 2 ← 3 인 상태에서 1이 3을 선행으로 지정하면 순환
    a = make_task(1)
    b = make_task(2, blocked_by=[1])
    c = make_task(3, blocked_by=[2])

    with pytest.raises(CycleError):
        validate_blockers(task_id=1, blocker_ids=[3], blocker_map=build_blocker_map([a, b, c]))


def test_순환이_아니면_통과한다():
    a = make_task(1)
    b = make_task(2, blocked_by=[1])
    c = make_task(3)

    validate_blockers(task_id=3, blocker_ids=[2], blocker_map=build_blocker_map([a, b, c]))
