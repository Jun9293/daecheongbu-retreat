"""업무 라이브러리 관리 — 필수 지정 (CLAUDE.md 6-1, 6-7).

자동 분류는 실행 이력에서 계산되므로, 회차가 한 번밖에 쌓이지 않은 동안에는
근거가 얇습니다. 그동안 구멍 방지를 맡는 것이 여기서 손으로 다는 '필수' 표시입니다.
이력이 쌓이면 자동 분류가 같은 판단을 하게 되고, 그때도 이 표시는 그대로 유효합니다.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, log_activity, resolve_retreat
from app.domain import library as lib_domain
from app.domain.departments import DEPARTMENT_COLORS, DEPARTMENT_NAMES
from app.models import TaskLibrary, User
from app.security import require_admin
from app.templating import redirect, render

router = APIRouter()


@router.get("/library")
def library_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    retreat = resolve_retreat(db, user, None)
    open_date = (retreat.start_date if retreat else None) or dt.date.today()
    rows = lib_domain.catalog(db, open_date=open_date)

    departments = {}
    if retreat:
        departments = {d.key: (d.name, d.color) for d in retreat.departments}

    items = []
    for row in rows:
        key = row["department_key"]
        name, color = departments.get(
            key, (DEPARTMENT_NAMES.get(key, "담당 없음"), DEPARTMENT_COLORS.get(key, "#69726D"))
        )
        items.append({**row, "department_name": name, "department_color": color})

    return render(
        request,
        "library.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "items": items,
            "history_depth": lib_domain.history_depth(db),
            "round_labels": lib_domain.round_labels(db),
            "required_count": sum(1 for i in items if i["always_required"]),
            "active_tab": "library",
            "page_subtitle": "업무 라이브러리",
        },
    )


@router.post("/library/{library_id}/required")
def set_required(
    library_id: int,
    request: Request,
    required: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    lib = db.get(TaskLibrary, library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다.")

    before = bool(lib.always_required)
    lib.always_required = required == "on"
    db.commit()
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="필수_지정_변경",
        target_type="task_library",
        target_id=lib.id,
        summary=f"{lib.title}: {'필수 지정' if lib.always_required else '필수 해제'}",
        before_value={"always_required": before},
        after_value={"always_required": bool(lib.always_required)},
    )
    return redirect(
        "/library",
        message=f"'{lib.title}' 을(를) {'필수로 지정' if lib.always_required else '필수에서 해제'}했습니다.",
    )


@router.post("/library/required/bulk")
def set_required_bulk(
    library_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """체크된 것만 필수로 남긴다. 화면 전체를 한 번에 저장하는 경로."""
    chosen = set(library_ids)
    changed = 0
    for lib in db.scalars(select(TaskLibrary).where(TaskLibrary.archived_at.is_(None))):
        if lib.parent_library_id is not None:
            continue
        want = lib.id in chosen
        if bool(lib.always_required) != want:
            lib.always_required = want
            changed += 1
    db.commit()
    if changed:
        log_activity(
            db,
            retreat_id=None,
            actor=user,
            action="필수_지정_일괄변경",
            target_type="task_library",
            target_id=None,
            summary=f"{changed}건의 필수 지정을 바꿨습니다.",
        )
    return redirect(
        "/library",
        message=f"필수 지정 {changed}건을 저장했습니다." if changed else "바뀐 내용이 없습니다.",
    )


class LibraryTaskIn(BaseModel):
    title: str
    department_key: str | None = None
    kind: str = "main"
    d_week: int = 4
    span_days: int = 0
    parent_library_id: int | None = None


@router.post("/library/new")
def create_library_task(
    payload: LibraryTaskIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """마법사에서 바로 라이브러리에 업무를 만든다. 회차가 없어도 된다."""
    from app.models import TASK_KINDS

    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="업무 이름을 입력해주세요.")
    if payload.kind not in TASK_KINDS:
        raise HTTPException(status_code=400, detail="알 수 없는 분류입니다.")
    if payload.kind == "sub" and payload.parent_library_id is None:
        raise HTTPException(status_code=400, detail="하위 업무는 상위 업무를 골라야 합니다.")

    lib = TaskLibrary(
        title=title,
        kind=payload.kind,
        parent_library_id=payload.parent_library_id,
        default_department_key=payload.department_key,
        related_department_keys=[],
        related_library_ids=[],
        date_anchor="week",
        default_d_week=max(1, payload.d_week),
        default_offset_days=0,
        default_span_days=max(0, payload.span_days),
        origin="history",
    )
    db.add(lib)
    db.commit()
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="라이브러리_업무_생성",
        target_type="task_library",
        target_id=lib.id,
        summary=f"{title} (D-{lib.default_d_week}주)",
    )
    return {"library_id": lib.id, "title": lib.title}


@router.post("/library/{library_id}/edit")
def edit_library_task(
    library_id: int,
    payload: LibraryTaskIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """라이브러리 업무를 고친다.

    이미 치른 회차의 실행 기록(TaskRun)의 날짜는 건드리지 않는다.
    지나간 회차에서 실제로 언제 했는지는 사실이므로 바뀌면 안 된다.
    """
    from app.models import TASK_KINDS

    lib = db.get(TaskLibrary, library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다.")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="업무 이름을 입력해주세요.")
    if payload.kind not in TASK_KINDS:
        raise HTTPException(status_code=400, detail="알 수 없는 분류입니다.")

    before = {"title": lib.title, "d_week": lib.default_d_week,
              "department": lib.default_department_key, "kind": lib.kind}
    lib.title = title
    lib.kind = payload.kind
    lib.default_department_key = payload.department_key
    lib.default_d_week = max(1, payload.d_week)
    lib.default_span_days = max(0, payload.span_days)
    if payload.kind != "sub":
        lib.parent_library_id = None
    elif payload.parent_library_id is not None:
        lib.parent_library_id = payload.parent_library_id
    db.commit()
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="라이브러리_업무_수정",
        target_type="task_library",
        target_id=lib.id,
        summary=f"{before['title']} → {lib.title}",
        before_value=before,
        after_value={"title": lib.title, "d_week": lib.default_d_week,
                     "department": lib.default_department_key, "kind": lib.kind},
    )
    return {"library_id": lib.id, "title": lib.title}
