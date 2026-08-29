"""새 회차 세팅 마법사 (CLAUDE.md 6-6, 6-7).

4단계: 회차 정보 → 부서 확정 → 업무 라이브러리 → 확인 및 생성.
날짜 재계산·분류·명절 충돌·구멍 경고는 모두 서버에서 계산한다.
화면은 개회일이나 선택이 바뀔 때마다 /setup/preview 를 다시 부른다.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DEFAULT_MEAL_SUBSIDY_PER_PERSON
from app.db import get_db
from app.deps import all_retreats, log_activity
from app.domain import drafts as draft_domain
from app.domain import dweek
from app.domain import library as lib_domain
from app.domain import suggestions as suggest_domain
from app.domain.departments import DEPARTMENT_MASTER, DEPARTMENT_NAMES
from app.models import User
from app.security import require_admin
from app.templating import redirect, render

router = APIRouter()


def _parse(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - 폼 검증 실패
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다.") from exc


def _default_open_date(db: Session) -> dt.date:
    """직전 회차의 반년 뒤 첫 금요일쯤을 기본값으로 제안한다."""
    base = lib_domain.latest_retreat(db)
    if base is None or base.start_date is None:
        return dt.date.today() + dt.timedelta(days=90)
    return base.start_date + dt.timedelta(days=147)


@router.get("/setup")
def setup_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    base = lib_domain.latest_retreat(db)
    departments = (
        [{"key": d.key, "name": d.name, "color": d.color} for d in base.departments]
        if base and base.departments
        else [{"key": k, "name": n, "color": c} for k, n, c in DEPARTMENT_MASTER]
    )
    open_date = _default_open_date(db)
    season = "겨울" if open_date.month in (12, 1, 2) else "여름"
    return render(
        request,
        "setup.html",
        {
            "user": user,
            "retreat": base,
            "retreats": all_retreats(db),
            "departments": departments,
            "default_name": f"{open_date.year} {season}수련회",
            "default_open": open_date.isoformat(),
            "default_close": (open_date + dt.timedelta(days=2)).isoformat(),
            "default_subsidy": DEFAULT_MEAL_SUBSIDY_PER_PERSON,
            "base_retreat_name": base.name if base else None,
            "round_labels": lib_domain.round_labels(db),
            "draft": draft_domain.active_draft(db),
            "active_tab": "setup",
            "page_subtitle": "새 회차 만들기",
        },
    )


class PreviewIn(BaseModel):
    open_date: str
    close_date: str | None = None
    department_keys: list[str] = []
    selected: list[int] | None = None
    adopted: list[str] | None = None


@router.post("/setup/preview")
def preview(
    payload: PreviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """개회일·선택이 바뀔 때마다 다시 계산해서 돌려준다."""
    open_date = _parse(payload.open_date)
    base = lib_domain.latest_retreat(db)

    clashes = dweek.holiday_clashes(open_date)
    clash_weeks = {c["d_week"] for c in clashes}

    catalog = lib_domain.catalog(db, open_date=open_date)
    proposals = suggest_domain.generate(db, open_date=open_date, base_retreat=base)

    items = []
    for row in catalog:
        items.append(
            {
                "id": str(row["library_id"]),
                "kind": "library",
                "task_kind": row["kind"],          # main | schedule
                "title": row["title"],
                "department_key": row["department_key"],
                "d_week": row["d_week"],
                "start": row["start_date"].isoformat(),
                "start_label": f"{row['start_date'].month}/{row['start_date'].day}",
                "children": [
                    {
                        "title": sub["title"],
                        "d_week": sub["d_week"],
                        "start_label": f"{sub['start_date'].month}/{sub['start_date'].day}",
                        "department_key": sub["department_key"],
                    }
                    for sub in row["children"]
                ],
                "verdict": row["verdict"],
                "always_required": row["always_required"],
                "required": row["required"],
                "history": row["history"],
                "rationale": row["rationale"],
                "sub_count": row["sub_count"],
                "clash": row["d_week"] in clash_weeks,
            }
        )
    for proposal in proposals:
        start = dweek.week_date(open_date, proposal["d_week"])
        items.append(
            {
                "id": f"new:{proposal['title']}",
                "kind": "suggestion",
                "task_kind": "main",
                "children": [],
                "title": proposal["title"],
                "department_key": proposal["department_key"],
                "d_week": proposal["d_week"],
                "start": start.isoformat(),
                "start_label": f"{start.month}/{start.day}",
                "verdict": {
                    "label": lib_domain.SUGGESTED,
                    "tone": lib_domain.TONE_NEW,
                    "default_on": True,
                    "required": False,
                    "basis": proposal["source"],
                },
                "always_required": False,
                "required": False,
                "history": [],
                "rationale": proposal["rationale"],
                "source": proposal["source"],
                "sub_count": 0,
                "clash": proposal["d_week"] in clash_weeks,
            }
        )

    weeks = [
        {
            "d_week": n,
            "date": dweek.week_date(open_date, n).isoformat(),
            "label": f"{dweek.week_date(open_date, n).month}/{dweek.week_date(open_date, n).day}",
            "holiday": dweek.holiday_in_week(dweek.week_date(open_date, n)),
        }
        for n in range(dweek.FIRST_D_WEEK, 0, -1)
    ]

    return {
        "items": items,
        "weeks": weeks,
        "clashes": [
            {"d_week": c["d_week"], "name": c["name"],
             "label": f"{c['sunday'].month}/{c['sunday'].day}"}
            for c in clashes
        ],
        "round_labels": lib_domain.round_labels(db),
        "history_depth": lib_domain.history_depth(db),
        "base_retreat": base.name if base else None,
        "suggestions": proposals,
        "draft": _draft_state(db),
    }


def _draft_state(db: Session) -> dict | None:
    """팀별 수집이 진행 중이면 그 현황과 제출된 선택을 함께 준다."""
    draft = draft_domain.active_draft(db)
    if draft is None:
        return None
    library_ids, adopted = draft_domain.merged_selection(draft)
    data = draft_domain.progress(draft)
    return {
        "id": draft.id,
        "name": draft.name,
        "open_date": draft.open_date.isoformat(),
        "close_date": draft.close_date.isoformat(),
        "meal_subsidy": draft.meal_subsidy_per_person,
        "department_keys": draft.department_keys or [],
        "submitted": data["submitted"],
        "total": data["total"],
        "all_in": data["all_in"],
        "rows": [
            {
                "department_key": r["department_key"],
                "name": DEPARTMENT_NAMES.get(r["department_key"], r["department_key"]),
                "state": r["state"],
                "count": r["count"],
                "by": r["by"],
                "note": r["note"],
            }
            for r in data["rows"]
        ],
        "selected": sorted(library_ids),
        "adopted": sorted(adopted),
    }


@router.post("/setup/department")
def new_department_key(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """새 부서에 회차를 넘어 쓸 키를 발급한다.

    한글 이름으로는 안전한 키를 만들 수 없으므로 번호를 붙인다.
    이 키가 다음 회차에서도 같은 부서임을 알아보는 유일한 근거다.
    """
    from app.models import Department

    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="부서 이름을 입력해주세요.")
    used = {d.key for d in db.scalars(select(Department)) if d.key}
    used |= {k for k, _, _ in DEPARTMENT_MASTER}
    n = 1
    while f"team{n}" in used:
        n += 1
    return {"key": f"team{n}", "name": name, "color": payload.get("color") or "#69726D"}


class DraftIn(BaseModel):
    name: str
    open_date: str
    close_date: str
    meal_subsidy: int = DEFAULT_MEAL_SUBSIDY_PER_PERSON
    department_keys: list[str]
    new_departments: list[dict] = []


@router.post("/setup/draft")
def open_draft(
    payload: DraftIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """업무 선택을 각 팀에 맡긴다. 부서마다 빈 칸이 하나씩 생긴다."""
    open_date = _parse(payload.open_date)
    close_date = _parse(payload.close_date)
    if close_date < open_date:
        raise HTTPException(status_code=400, detail="폐회일이 개회일보다 빠릅니다.")
    if not payload.department_keys:
        raise HTTPException(status_code=400, detail="부서를 하나 이상 남겨주세요.")

    draft = draft_domain.open_draft(
        db,
        name=payload.name.strip() or "새 회차",
        open_date=open_date,
        close_date=close_date,
        meal_subsidy=payload.meal_subsidy,
        department_keys=payload.department_keys,
        actor=user,
    )
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="회차준비_시작",
        target_type="retreat_draft",
        target_id=draft.id,
        summary=f"{draft.name} — {len(payload.department_keys)}개 부서에 업무 선택 요청",
    )
    return {"draft_id": draft.id, "redirect": "/draft"}


class NewDepartment(BaseModel):
    key: str
    name: str
    color: str | None = None


class CreateIn(BaseModel):
    name: str
    open_date: str
    close_date: str
    meal_subsidy: int = DEFAULT_MEAL_SUBSIDY_PER_PERSON
    department_keys: list[str]
    new_departments: list[NewDepartment] = []
    selected: list[int] = []
    adopted: list[str] = []


@router.post("/setup/create")
def create(
    payload: CreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    open_date = _parse(payload.open_date)
    close_date = _parse(payload.close_date)
    if close_date < open_date:
        raise HTTPException(status_code=400, detail="폐회일이 개회일보다 빠릅니다.")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="회차 이름을 입력해주세요.")
    if not payload.department_keys:
        raise HTTPException(status_code=400, detail="부서를 하나 이상 남겨주세요.")

    base = lib_domain.latest_retreat(db)
    proposals = {
        p["title"]: p for p in suggest_domain.generate(db, open_date=open_date, base_retreat=base)
    }
    adopted = [
        {
            "title": title,
            "department_key": proposals[title]["department_key"],
            "d_week": proposals[title]["d_week"],
            "rationale": proposals[title]["rationale"],
        }
        for title in payload.adopted
        if title in proposals
    ]

    retreat = lib_domain.create_retreat(
        db,
        name=payload.name.strip(),
        open_date=open_date,
        close_date=close_date,
        meal_subsidy=payload.meal_subsidy,
        department_keys=payload.department_keys,
        selected_library_ids=set(payload.selected),
        adopted_suggestions=adopted,
        new_departments=[d.model_dump() for d in payload.new_departments],
        actor=user,
    )
    draft = draft_domain.active_draft(db)
    if draft is not None:
        draft_domain.close_draft(db, draft, retreat_id=retreat.id)

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="회차_생성",
        target_type="retreat",
        target_id=retreat.id,
        summary=(
            f"{retreat.name} — 실행 {len(payload.selected) + len(adopted)}건 · "
            f"미실행 {lib_domain.excluded_count(db, retreat)}건"
        ),
    )
    return {"retreat_id": retreat.id, "redirect": f"/board?retreat_id={retreat.id}"}


@router.get("/setup/done/{retreat_id}")
def done(retreat_id: int, user: User = Depends(require_admin)):
    return redirect(f"/board?retreat_id={retreat_id}", message="새 회차를 만들었습니다.")
