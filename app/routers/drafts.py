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


def _default_key(user: User, allowed: list[str]) -> tuple[str | None, list[str]]:
    """`/draft` 의 기본 칸 (도막 4 · ③) — **리더인 부서 중 첫째**, 둘 이상이거나
    **리더 없이 팀원으로 둘 이상이면** 고르게 한다 (UI 정리 판 1 · 4-b — 봐둘것 AM-c).
    돌려주는 것: (키, 고를 것들). `allowed` 는 이번 초안에 든 부서 키다 — 그 밖의
    소속은 후보가 아니다."""
    leads = sorted(k for k in perm.lead_keys(user) if k in allowed)
    if len(leads) > 1:
        return None, leads
    if leads:
        return leads[0], []
    mine = sorted(k for k in perm.my_dept_keys(user) if k in allowed)
    if len(mine) > 1:
        return None, mine
    return (mine[0] if mine else None), []


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
    is_admin = perm.is_admin(user)
    if key and not is_admin and key not in perm.my_dept_keys(user):
        raise HTTPException(status_code=403, detail="내 부서의 칸만 볼 수 있습니다.")
    if not key:
        key, choices = _default_key(user, draft.department_keys or [])
        if choices:
            # 리더인 부서가 둘 이상, 또는 리더 없이 팀원으로 둘 이상 — 어느 칸을 채울지 고른다 (③)
            return render(
                request,
                "draft_pick.html",
                {"user": user, "retreats": all_retreats(db), "draft": draft,
                 "choices": [{"key": k, "name": DEPARTMENT_NAMES.get(k, k)} for k in choices],
                 "page_subtitle": "회차 준비"},
            )
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
            "can_edit": is_admin or key in perm.my_dept_keys(user),   # 소속 중 하나 (도막 4)
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
    if perm.is_readonly(user):
        raise HTTPException(status_code=403, detail="열람 전용 계정은 고를 수 없습니다.")
    if not perm.is_admin(user) and department_key not in perm.my_dept_keys(user):
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
