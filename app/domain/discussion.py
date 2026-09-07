"""논의가 걸린 곳 (CLAUDE.md 4-9).

논의 한 줄이 여러 업무에 걸릴 수 있다 — 회의는 여러 업무를 한 자리에서
이야기하고, 회의록에서 들어오는 것이 이미 그 모양이다.

**저장은 한 곳에만.** 본문은 DiscussionEntry 한 행, 걸린 곳은
DiscussionEntryRun 이 유일한 출처다. DiscussionEntry.run_id 는 남으나 읽지
않는다(읽는 곳은 db._link_discussion_runs 의 한 번 옮기기뿐). 여기의
attach/detach/runs_of 가 그 표를 읽고 쓰는 유일한 창구다 — 두 곳에서
읽으면 구조가 바뀔 때 한쪽만 고쳐진다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DiscussionEntry, DiscussionEntryRun, TaskRun


class LastAttachmentError(Exception):
    """마지막 한 곳을 떼려 했다 — 붙을 곳 없는 논의를 만들지 않는다 (4-9)."""


def links_of(db: Session, entry: DiscussionEntry) -> list[DiscussionEntryRun]:
    """살아 있는(떼지 않은) 링크 행."""
    return list(
        db.scalars(
            select(DiscussionEntryRun)
            .where(
                DiscussionEntryRun.entry_id == entry.id,
                DiscussionEntryRun.detached_at.is_(None),
            )
            .order_by(DiscussionEntryRun.attached_at, DiscussionEntryRun.id)
        )
    )


def runs_of(db: Session, entry: DiscussionEntry) -> list[TaskRun]:
    """이 논의가 걸린 업무들 — **읽는 곳은 여기 하나다** (4-9)."""
    ids = [link.run_id for link in links_of(db, entry)]
    if not ids:
        return []
    runs = {r.id: r for r in db.scalars(select(TaskRun).where(TaskRun.id.in_(ids)))}
    return [runs[i] for i in ids if i in runs]


def attach(db: Session, entry: DiscussionEntry, run: TaskRun) -> DiscussionEntryRun:
    """논의를 업무에 건다. 뗐던 자리에 다시 걸면 그 행을 되살린다.

    (entry, run) 쌍은 유니크라 새 행을 만들면 부딪힌다 — 떼고 다시 거는 것은
    '다시 걸림' 이지 '두 번 걸림' 이 아니다.
    """
    existing = db.scalar(
        select(DiscussionEntryRun).where(
            DiscussionEntryRun.entry_id == entry.id,
            DiscussionEntryRun.run_id == run.id,
        )
    )
    if existing is not None:
        if existing.detached_at is not None:
            existing.detached_at = None
            existing.attached_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
        return existing
    link = DiscussionEntryRun(entry_id=entry.id, run_id=run.id)
    db.add(link)
    return link


def detach(db: Session, entry: DiscussionEntry, run: TaskRun) -> DiscussionEntryRun:
    """논의를 이 업무에서 뗀다 — 지우지 않는다(detached_at).

    마지막 한 곳을 떼려 하면 막는다. 붙을 곳 없는 논의는 어느 화면에도
    안 떠서, 있는데 아무도 못 보는 기록이 된다.
    """
    alive = links_of(db, entry)
    target = next((link for link in alive if link.run_id == run.id), None)
    if target is None:
        raise LookupError("이 업무에 걸려 있지 않은 논의입니다.")
    if len(alive) <= 1:
        raise LastAttachmentError(
            "마지막 한 곳입니다 — 여기서 떼면 이 논의가 어디에도 남지 않습니다."
        )
    target.detached_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    return target
