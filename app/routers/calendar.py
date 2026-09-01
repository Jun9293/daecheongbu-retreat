"""달력 보기 (CLAUDE.md 4-13).

**점을 누르면 보드의 상세 패널이 열립니다** — 여기서 새로 만들지 않습니다.
`/board?task=<run_id>` 가 이미 그 일을 합니다(알림을 누르고 들어올 때 쓰던 길,
4-11). 패널을 한 벌 더 만들면 논의·상태·첨부가 두 곳에서 갈립니다.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat
from app.domain import calendar as calendar_domain
from app.domain.departments import department_key_of
from app.models import Retreat, User
from app.security import get_current_user
from app.templating import render

router = APIRouter()

# 고른 범위와 '미완료만' 을 기기에 남긴다. 다음에 열면 그대로 —
# 담당자는 늘 같은 것을 보러 오므로 매번 다시 고르게 하지 않는다.
SCOPE_COOKIE = "dcb_cal_scope"
OPEN_COOKIE = "dcb_cal_open"


def _today() -> dt.date:
    return dt.date.today()


@router.get("/calendar")
def calendar_page(
    request: Request,
    month: str | None = None,
    scope: str | None = None,
    only_open: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    my_key = department_key_of(db, user)

    # 주소에 없으면 지난번에 고른 것, 그것도 없으면 기본값.
    # **기본은 `내 것`** — "내가 뭘 해야 하나" 를 보려고 여는 화면이다
    chosen = scope or request.cookies.get(SCOPE_COOKIE) or "mine"
    if only_open is None:
        open_only = request.cookies.get(OPEN_COOKIE) == "1"
    else:
        open_only = only_open in ("1", "true", "on")

    view = calendar_domain.build(
        db,
        retreat,
        today=_today(),
        user=user,
        my_dept_key=my_key,
        month=month,
        scope=chosen,
        only_open=open_only,
    )

    response = render(
        request,
        "calendar.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "cal": view,
            "active_tab": "calendar",
            "page_subtitle": "달력",
        },
    )
    # 구조가 실제로 쓴 값을 남긴다 — 부서가 없어 'mine' 으로 떨어졌으면
    # 그 값이 남아야 다음에 열 때도 같은 화면이 뜬다
    response.set_cookie(SCOPE_COOKIE, view["scope"],
                        max_age=60 * 60 * 24 * 180, httponly=False)
    response.set_cookie(OPEN_COOKIE, "1" if view["only_open"] else "0",
                        max_age=60 * 60 * 24 * 180, httponly=False)
    return response
