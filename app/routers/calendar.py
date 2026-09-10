"""달력 보기 (CLAUDE.md 4-13).

점을 누르면 **그 자리에서** 상세 패널이 열린다 — 패널은 보드와 같은 조각
(partials/drawer.html)·같은 코드(drawer.js)다. 한 벌 더 만들면 논의·상태·
첨부가 두 곳에서 갈린다. 달을 넘기는 것은 `/calendar/partial` 이 맡는다 —
전체 페이지와 같은 계산(_view)·같은 partial 을 그린다.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat
from app.domain import calendar as calendar_domain
from app.domain import permissions as perm
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


def _view(
    request: Request,
    month: str | None,
    scope: str | None,
    only_open: str | None,
    db: Session,
    user: User,
    retreat: Retreat,
) -> dict:
    """전체 페이지와 `/calendar/partial` 이 **같은 이 함수**로 달을 그린다 (4-13).

    두 벌이면 화살표로 넘긴 달과 새로고침한 달이 다르게 계산된다.
    """
    my_keys = perm.my_dept_keys(user)

    # 주소에 없으면 지난번에 고른 것, 그것도 없으면 기본값.
    # **기본은 내 부서 전부**(도막 4 · ④) — 소속이 없으면 `내 것`(담당자 나)
    chosen = scope or request.cookies.get(SCOPE_COOKIE) or ("depts" if my_keys else "mine")
    if only_open is None:
        open_only = request.cookies.get(OPEN_COOKIE) == "1"
    else:
        open_only = only_open in ("1", "true", "on")

    return calendar_domain.build(
        db,
        retreat,
        today=_today(),
        user=user,
        my_dept_keys=my_keys,
        month=month,
        scope=chosen,
        only_open=open_only,
    )


@router.get("/calendar/partial")
def calendar_partial(
    request: Request,
    month: str | None = None,
    scope: str | None = None,
    only_open: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """달 격자만 (4-13). 달을 넘길 때 페이지를 다시 그리지 않는다 —
    calendar.js 가 이것을 받아 `#calgrid` 만 갈아 끼운다.
    전체 페이지와 **같은 계산(_view) · 같은 partial** 을 그린다."""
    view = _view(request, month, scope, only_open, db, user, retreat)
    return render(request, "partials/calendar_grid.html", {"cal": view})


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
    view = _view(request, month, scope, only_open, db, user, retreat)

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
