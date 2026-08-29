"""각 팀이 자기 업무를 고르는 화면 (CLAUDE.md 6-6).

총무팀이 초안을 열면 부서마다 칸이 하나씩 생긴다. 부서 리더는 자기 칸만 채운다.
임시저장은 몇 번이든, 제출은 "우리 팀은 다 골랐다"는 표시다. 총무팀이 회차를
열기 전까지는 제출한 뒤에도 고칠 수 있다.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, log_activity
from app.domain import drafts as draft_domain
from app.domain import dweek
from app.domain import library as lib_domain
from app.domain import permissions as perm
from app.domain import suggestions as suggest_domain
from app.domain.departments import DEPARTMENT_COLORS, DEPARTMENT_NAMES
from app.models import RetreatDraft, User
from app.security import get_current_user
from app.templating import render

router = APIRouter()


def _my_department_key(db: Session, user: User) -> str | None:
    if user.department_id is None:
        return None
    from app.models import Department

    dept = db.get(Department, user.department_id)
    return dept.key if dept else None


@router.get("/draft")
def draft_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """내 부서의 업무 선택 칸."""
    draft = draft_domain.active_draft(db)
    if draft is None:
        return render(
            request,
            "draft_none.html",
            {"user": user, "retreats": all_retreats(db), "page_subtitle": "회차 준비"},
        )

    key = request.query_params.get("department")
    mine = _my_department_key(db, user)
    is_admin = perm.can_manage_retreat(user.role)
    if key and not is_admin and key != mine:
        raise HTTPException(status_code=403, detail="내 부서의 칸만 볼 수 있습니다.")
    key = key or mine
    if key is None:
        raise HTTPException(status_code=400, detail="소속 부서가 없어 고를 수 없습니다. 총무팀에 문의해주세요.")
    if key not in (draft.department_keys or []):
        raise HTTPException(status_code=404, detail="이번 회차에 포함되지 않은 부서입니다.")

    submission = draft_domain.submission_for(db, draft, key)
    catalog = lib_domain.catalog(db, open_date=draft.open_date)
    proposals = suggest_domain.generate(
        db, open_date=draft.open_date, base_retreat=lib_domain.latest_retreat(db)
    )

    chosen = set(submission.library_ids or [])
    adopted = set(submission.adopted_titles or [])
    untouched = submission.saved_at is None

    items = []
    for row in catalog:
        if row["department_key"] != key:
            continue
        items.append(
            {
                **row,
                "id": str(row["library_id"]),
                "selected": row["verdict"]["default_on"] if untouched else row["library_id"] in chosen,
            }
        )
    for proposal in proposals:
        if proposal["department_key"] != key:
            continue
        start = dweek.week_date(draft.open_date, proposal["d_week"])
        items.append(
            {
                "id": f"new:{proposal['title']}",
                "library_id": None,
                "title": proposal["title"],
                "kind": "main",
                "department_key": key,
                "d_week": proposal["d_week"],
                "start_date": start,
                "end_date": start,
                "verdict": {"label": lib_domain.SUGGESTED, "tone": lib_domain.TONE_NEW,
                            "basis": proposal["source"], "default_on": True, "required": False},
                "always_required": False,
                "required": False,
                "history": [],
                "rationale": proposal["rationale"],
                "children": [],
                "sub_count": 0,
                "selected": True if untouched else proposal["title"] in adopted,
            }
        )

    items.sort(key=lambda i: (i["start_date"], i["kind"] != "main", i["title"]))

    return render(
        request,
        "draft.html",
        {
            "user": user,
            "retreats": all_retreats(db),
            "draft": draft,
            "submission": submission,
            "department_key": key,
            "department_name": DEPARTMENT_NAMES.get(key, key),
            "department_color": DEPARTMENT_COLORS.get(key, "#69726D"),
            "items": items,
            "progress": draft_domain.progress(draft),
            "history_depth": lib_domain.history_depth(db),
            "can_edit": is_admin or key == mine,
            "viewer_is_admin": is_admin,
            "dept_names": DEPARTMENT_NAMES,
            "dept_colors": DEPARTMENT_COLORS,
            "page_subtitle": "회차 준비",
            "active_tab": "draft",
        },
    )


class SelectionIn(BaseModel):
    library_ids: list[int] = []
    adopted: list[str] = []
    note: str | None = None
    submit: bool = False


@router.post("/draft/{department_key}/save")
def save(
    department_key: str,
    payload: SelectionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    draft = draft_domain.active_draft(db)
    if draft is None:
        raise HTTPException(status_code=404, detail="진행 중인 회차 준비가 없습니다.")
    if perm.is_readonly(user.role):
        raise HTTPException(status_code=403, detail="열람 전용 계정은 고를 수 없습니다.")
    if not perm.can_manage_retreat(user.role) and _my_department_key(db, user) != department_key:
        raise HTTPException(status_code=403, detail="내 부서의 칸만 채울 수 있습니다.")

    submission = draft_domain.submission_for(db, draft, department_key)
    if submission is None:
        raise HTTPException(status_code=404, detail="그 부서의 칸이 없습니다.")

    draft_domain.save_selection(
        db,
        submission,
        library_ids=payload.library_ids,
        adopted_titles=payload.adopted,
        note=payload.note,
        user=user,
        submit=payload.submit,
    )
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="회차준비_제출" if payload.submit else "회차준비_임시저장",
        target_type="draft_submission",
        target_id=submission.id,
        summary=f"{DEPARTMENT_NAMES.get(department_key, department_key)} "
        f"{len(payload.library_ids) + len(payload.adopted)}건",
    )
    return {"state": submission.state, "progress": _progress_json(draft)}


def _progress_json(draft: RetreatDraft) -> dict:
    data = draft_domain.progress(draft)
    return {
        "submitted": data["submitted"],
        "total": data["total"],
        "all_in": data["all_in"],
        "rows": [
            {**r, "at": r["at"].isoformat() if isinstance(r["at"], dt.datetime) else None,
             "name": DEPARTMENT_NAMES.get(r["department_key"], r["department_key"])}
            for r in data["rows"]
        ],
    }
