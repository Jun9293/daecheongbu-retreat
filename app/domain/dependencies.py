"""할 일 선후행 의존성.

Phase 1에서 데이터 구조만 마련했던 `blocked_by_task_ids`를 실제로 동작시킨다.
- 선행 작업이 남아 있으면 후행은 '막힘' 상태
- 선행이 모두 완료되면 후행이 '시작 가능'으로 자동 전환
- 순환 참조(A가 B를, B가 A를 기다리는 상태)는 등록 단계에서 거부
"""

from __future__ import annotations

from typing import Iterable

DONE = "완료"


class CycleError(ValueError):
    """선후행 관계가 순환을 만들 때."""


def build_blocker_map(tasks: Iterable) -> dict[int, list[int]]:
    """{할일 id: [선행 할일 id, ...]}"""
    return {task.id: list(task.blocked_by_task_ids or []) for task in tasks}


def blocking_tasks(task, tasks_by_id: dict[int, object]) -> list:
    """아직 끝나지 않아서 이 할 일을 막고 있는 선행 작업들.

    이미 삭제된 선행 작업은 무시한다 (후행이 영원히 막히지 않도록).
    """
    result = []
    for blocker_id in task.blocked_by_task_ids or []:
        blocker = tasks_by_id.get(blocker_id)
        if blocker is not None and blocker.status != DONE:
            result.append(blocker)
    return result


def is_blocked(task, tasks_by_id: dict[int, object]) -> bool:
    return bool(blocking_tasks(task, tasks_by_id))


def newly_unblocked(*, completed_task_id: int, tasks: list) -> list:
    """방금 완료된 작업 때문에 '시작 가능'이 된 후행 작업들."""
    tasks_by_id = {task.id: task for task in tasks}
    result = []
    for task in tasks:
        if task.status == DONE:
            continue
        if completed_task_id not in (task.blocked_by_task_ids or []):
            continue
        if not is_blocked(task, tasks_by_id):
            result.append(task)
    return result


def validate_blockers(
    *, task_id: int, blocker_ids: list[int], blocker_map: dict[int, list[int]]
) -> None:
    """선행 작업 지정이 순환을 만들지 않는지 검사한다. 문제가 있으면 CycleError."""
    if task_id in blocker_ids:
        raise CycleError("자기 자신을 선행 작업으로 지정할 수 없습니다.")

    candidate = dict(blocker_map)
    candidate[task_id] = list(blocker_ids)

    visiting: set[int] = set()
    done: set[int] = set()

    def visit(node: int) -> None:
        if node in done:
            return
        if node in visiting:
            raise CycleError("선행 작업이 서로를 기다리는 순환 관계가 됩니다.")
        visiting.add(node)
        for parent in candidate.get(node, []):
            visit(parent)
        visiting.discard(node)
        done.add(node)

    visit(task_id)


def dependency_state(task, tasks_by_id: dict[int, object]) -> str:
    """화면에 표시할 의존성 상태."""
    if task.status == DONE:
        return "완료"
    if is_blocked(task, tasks_by_id):
        return "선행대기"
    if task.blocked_by_task_ids and task.status == "대기":
        return "시작가능"
    return ""
