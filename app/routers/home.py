"""홈 (CLAUDE.md 4-15) — `/` 가 홈이다. 보드는 `/board` 그대로다.

숫자는 전부 `domain/home.build` 에서 온다 — 여기서는 아무것도 세지 않는다.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, resolve_retreat
from app.domain import home as home_domain
from app.models import User
from app.security import get_current_user
from app.templating import render

router = APIRouter()


@router.get("/")
def home_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = request.query_params.get("retreat_id")
    retreat = resolve_retreat(db, user, int(raw) if raw and raw.isdigit() else None)
    if retreat is None:
        return render(request, "no_retreat.html", {"user": user})

    view = home_domain.build(db, retreat, user, today=dt.date.today())
    return render(
        request,
        "home.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "home": view,
            "active_tab": "home",
            "page_subtitle": "홈",
        },
    )
