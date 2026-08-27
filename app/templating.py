"""Jinja2 템플릿 환경과 공용 헬퍼."""

from __future__ import annotations

import datetime as dt
import urllib.parse

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR
from app.domain import permissions as perm

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

FLASH_COOKIE = "dcb_flash"


def won(value: int | float | None) -> str:
    if value is None:
        return "-"
    return f"{int(value):,}원"


def num(value: int | float | None) -> str:
    if value is None:
        return "-"
    return f"{int(value):,}"


def kdate(value: dt.date | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y.%m.%d")


def short_date(value: dt.date | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%m/%d")


def dday(value: dt.date | None, today: dt.date | None = None) -> str:
    if value is None:
        return ""
    today = today or dt.date.today()
    delta = (value - today).days
    if delta == 0:
        return "오늘"
    if delta > 0:
        return f"D-{delta}"
    return f"D+{abs(delta)}"


templates.env.filters["won"] = won
templates.env.filters["num"] = num
templates.env.filters["kdate"] = kdate
templates.env.filters["short_date"] = short_date
templates.env.filters["dday"] = dday
def can_edit_dept(user, target_department_id: int | None) -> bool:
    """템플릿에서 편집 버튼 노출 여부를 판단할 때 쓴다."""
    if user is None:
        return False
    return perm.can_edit_department_content(
        role=user.role,
        user_department_id=user.department_id,
        target_department_id=target_department_id,
    )


def is_other_dept(user, target_department_id: int | None) -> bool:
    """내 부서가 아닌 항목인지 — 흐리게 표시할 대상."""
    if user is None or user.role == perm.ADMIN:
        return False
    if user.department_id is None:
        return target_department_id is not None
    return target_department_id != user.department_id


templates.env.globals["ROLE_LABELS"] = perm.ROLE_LABELS
templates.env.globals["today"] = dt.date.today
templates.env.globals["can_edit_dept"] = can_edit_dept
templates.env.globals["is_other_dept"] = is_other_dept
templates.env.globals["is_readonly"] = perm.is_readonly
templates.env.globals["is_admin"] = lambda user: user is not None and perm.can_manage_retreat(user.role)


def _badge_counts(context: dict) -> dict:
    """모든 화면 상단에 표시할 미확인 알림 / 대기 중인 확인 요청 수."""
    user = context.get("user")
    if user is None:
        return {"unread_count": 0, "pending_review_count": 0}

    from app.db import SessionLocal
    from app.notifications import unread_count

    with SessionLocal() as db:
        counts = {"unread_count": unread_count(db, user), "pending_review_count": 0}
        retreat = context.get("retreat")
        if retreat is not None:
            from app.routers.reviews import pending_for_user

            counts["pending_review_count"] = len(pending_for_user(db, user, retreat))
    return counts


def render(
    request: Request, template_name: str, context: dict, status_code: int = 200
) -> HTMLResponse:
    flash = request.cookies.get(FLASH_COOKIE)
    ctx = {
        "request": request,
        "flash": urllib.parse.unquote(flash) if flash else None,
        **_badge_counts(context),
        **context,
    }
    response = templates.TemplateResponse(
        request=request, name=template_name, context=ctx, status_code=status_code
    )
    if flash:
        response.delete_cookie(FLASH_COOKIE)
    return response


def redirect(url: str, message: str | None = None) -> RedirectResponse:
    """POST 처리 후 리다이렉트 (+ 1회성 안내 메시지)."""
    response = RedirectResponse(url=url, status_code=303)
    if message:
        response.set_cookie(
            FLASH_COOKIE, urllib.parse.quote(message), max_age=10, httponly=False
        )
    return response
