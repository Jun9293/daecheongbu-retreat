"""회차 준비 초안 — 각 팀이 고르고 총무팀이 모아서 연다 (CLAUDE.md 6-6).

총무팀장이 50여 건을 혼자 훑어 고르면 각 팀의 사정이 반영되지 않는다.
회차 정보와 부서만 먼저 정해 두고 업무 선택은 각 팀에 맡긴 뒤, 모두 제출하면
총무팀이 확인하고 회차를 연다. 담당자가 바뀌어도 선택의 근거가 팀에 남는다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DraftSubmission, RetreatDraft, User


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def active_draft(db: Session) -> RetreatDraft | None:
    """지금 팀들이 채우고 있는 초안. 한 번에 하나만 연다."""
    return db.scalars(
        select(RetreatDraft)
        .where(RetreatDraft.status == "수집중")
        .order_by(RetreatDraft.id.desc())
    ).first()


def open_draft(
    db: Session,
    *,
    name: str,
    open_date: dt.date,
    close_date: dt.date,
    meal_subsidy: int,
    department_keys: list[str],
    actor: User | None = None,
) -> RetreatDraft:
    """초안을 열고 부서마다 빈 제출 칸을 만든다."""
    previous = active_draft(db)
    if previous is not None:
        previous.status = "취소"          # 열려 있던 초안은 접는다

    draft = RetreatDraft(
        name=name,
        open_date=open_date,
        close_date=close_date,
        meal_subsidy_per_person=meal_subsidy,
        department_keys=list(department_keys),
        created_by_id=actor.id if actor else None,
    )
    db.add(draft)
    db.flush()
    for key in department_keys:
        db.add(DraftSubmission(draft_id=draft.id, department_key=key, library_ids=[], adopted_titles=[]))
    db.commit()
    return draft


def submission_for(db: Session, draft: RetreatDraft, department_key: str) -> DraftSubmission | None:
    return db.scalars(
        select(DraftSubmission).where(
            DraftSubmission.draft_id == draft.id,
            DraftSubmission.department_key == department_key,
        )
    ).first()


def save_selection(
    db: Session,
    submission: DraftSubmission,
    *,
    library_ids: list[int],
    adopted_titles: list[str],
    note: str | None,
    user: User | None,
    submit: bool,
) -> DraftSubmission:
    """임시저장과 제출은 같은 내용을 쓰고 완료 표시만 다르다.

    제출한 뒤에도 다시 고칠 수 있다 — 총무팀이 회차를 열기 전까지는 언제든.
    """
    submission.library_ids = sorted(set(library_ids))
    submission.adopted_titles = sorted(set(adopted_titles))
    submission.note = (note or "").strip() or None
    submission.saved_at = _now()
    if submit:
        submission.submitted_at = _now()
        submission.submitted_by_id = user.id if user else None
        submission.submitted_by_name = user.name if user else None
    else:
        submission.submitted_at = None      # 다시 작성중으로 되돌린다
    db.commit()
    return submission


def progress(draft: RetreatDraft) -> dict:
    """부서별 진행 상태와 전체 완료 여부."""
    rows = [
        {
            "department_key": s.department_key,
            "state": s.state,
            "count": len(s.library_ids or []) + len(s.adopted_titles or []),
            "by": s.submitted_by_name,
            "at": s.submitted_at,
            "note": s.note,
        }
        for s in draft.submissions
    ]
    submitted = [r for r in rows if r["state"] == "제출"]
    return {
        "rows": rows,
        "submitted": len(submitted),
        "total": len(rows),
        "all_in": bool(rows) and len(submitted) == len(rows),
        "waiting": [r["department_key"] for r in rows if r["state"] != "제출"],
    }


def merged_selection(draft: RetreatDraft) -> tuple[set[int], set[str]]:
    """제출된 것만 모은다. 작성 중인 초안은 아직 팀의 답이 아니다."""
    library_ids: set[int] = set()
    adopted: set[str] = set()
    for s in draft.submissions:
        if not s.submitted_at:
            continue
        library_ids.update(s.library_ids or [])
        adopted.update(s.adopted_titles or [])
    return library_ids, adopted


def close_draft(db: Session, draft: RetreatDraft, *, retreat_id: int) -> None:
    draft.status = "생성완료"
    draft.created_retreat_id = retreat_id
    db.commit()
