"""위험 감지 및 에스컬레이션 규칙.

"담당자가 놓쳐도 시스템이 대신 알아차린다"는 이 프로젝트의 존재 이유에 해당하는 로직.
순수 함수로 두어 누구에게 보낼지(수신자 결정)와 어떻게 보낼지(푸시/앱)는 서비스 계층이 정한다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

DONE = "완료"
OPEN_STATUSES = ("대기", "진행중", "피드백요청", "지연")

RISK_OVERDUE = "지연"
RISK_DUE_SOON = "기한임박"
RISK_UNASSIGNED = "담당자미지정"
RISK_BLOCKER_LATE = "선행지연"

# 마감 리마인드를 보내는 시점 (매일 보내면 무뎌지므로 D-3, D-1, 당일만)
DUE_SOON_DAYS = (3, 1, 0)
# 담당자 없이 이 기간 안에 들어오면 총무팀에 에스컬레이션
UNASSIGNED_ESCALATION_DAYS = 7


@dataclass
class Risk:
    kind: str
    task: object
    message: str
    dedupe_key: str
    escalate_to_admin: bool = False
    related_task: object | None = None


def _is_open(task) -> bool:
    return task.status in OPEN_STATUSES


def tasks_to_mark_delayed(tasks: list, *, today: dt.date) -> list:
    """기한이 지났는데 아직 '지연'으로 바뀌지 않은 할 일들."""
    return [
        task
        for task in tasks
        if task.status in ("대기", "진행중", "피드백요청")
        and task.due_date is not None
        and task.due_date < today
    ]


def unassigned_runs_due_soon(runs: list, *, today: dt.date) -> list:
    """담당자 없이 마감이 코앞인 준비 업무(TaskRun) — 총무팀이 봐야 할 것.

    기준(며칠 안인가)은 scan_risks 의 담당자미지정과 같은 상수를 쓴다 —
    옛 할 일과 새 준비 업무가 다른 잣대를 갖게 두지 않는다. 홈의 경고 띠(4-15)가
    이 목록의 길이를 그대로 쓴다 — 홈에서 다시 세지 않는다.
    """
    out = []
    for run in runs:
        if run.status == DONE or not run.included:
            continue
        if run.assignee_id is not None:
            continue
        end = run.end_date or run.start_date
        if end is None:
            continue
        days_left = (end - today).days
        if 0 <= days_left <= UNASSIGNED_ESCALATION_DAYS:
            out.append(run)
    return out


def scan_risks(tasks: list, *, today: dt.date) -> list[Risk]:
    """할 일 목록에서 드러나야 할 위험을 모두 찾아낸다."""
    risks: list[Risk] = []
    tasks_by_id = {task.id: task for task in tasks}

    for task in tasks:
        if not _is_open(task):
            continue

        if task.due_date is not None:
            days_left = (task.due_date - today).days

            if days_left < 0:
                risks.append(
                    Risk(
                        kind=RISK_OVERDUE,
                        task=task,
                        message=f"기한이 {abs(days_left)}일 지났습니다.",
                        dedupe_key=f"{RISK_OVERDUE}:{task.id}:{abs(days_left)}",
                        escalate_to_admin=True,
                    )
                )
            elif days_left in DUE_SOON_DAYS:
                label = "오늘까지" if days_left == 0 else f"D-{days_left}"
                risks.append(
                    Risk(
                        kind=RISK_DUE_SOON,
                        task=task,
                        message=f"마감 {label}입니다.",
                        dedupe_key=f"{RISK_DUE_SOON}:{task.id}:{days_left}",
                    )
                )

            if task.assignee_id is None and 0 <= days_left <= UNASSIGNED_ESCALATION_DAYS:
                risks.append(
                    Risk(
                        kind=RISK_UNASSIGNED,
                        task=task,
                        message=f"담당자가 지정되지 않았는데 마감이 {days_left}일 남았습니다.",
                        dedupe_key=f"{RISK_UNASSIGNED}:{task.id}:{days_left}",
                        escalate_to_admin=True,
                    )
                )

        for blocker_id in task.blocked_by_task_ids or []:
            blocker = tasks_by_id.get(blocker_id)
            if blocker is None or blocker.status == DONE:
                continue
            if blocker.due_date is None or blocker.due_date >= today:
                continue
            overdue_days = (today - blocker.due_date).days
            risks.append(
                Risk(
                    kind=RISK_BLOCKER_LATE,
                    task=task,
                    related_task=blocker,
                    message=(
                        f"선행 작업 '{blocker.title}'이(가) {overdue_days}일 지연되어 "
                        "이 작업도 늦어질 수 있습니다."
                    ),
                    dedupe_key=f"{RISK_BLOCKER_LATE}:{task.id}:{blocker.id}:{overdue_days}",
                    escalate_to_admin=True,
                )
            )

    return risks
