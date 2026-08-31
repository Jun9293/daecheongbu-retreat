"""초대 링크로 들어오는 자리 (CLAUDE.md 4-12).

로그인 화면이 따로 없다. 총무팀이 카카오톡으로 보낸 링크를 열면 그 기기에
장기 세션이 붙는다. 쓸 사람이 19명이고 총무팀이 그분들 연락처를 이미 알고
있으므로, 인증 절차를 하나 더 두는 것보다 이쪽이 빠르고 덜 막힌다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import log_activity
from app.domain import auth as invites
from app.models import User
from app.security import clear_session, get_optional_user, set_session
from app.templating import redirect, render

router = APIRouter()


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(get_optional_user)):
    """로그인 화면은 없다. 어떻게 들어오는지만 알려준다."""
    if user is not None:
        return redirect("/board")
    return render(request, "login.html", {})


@router.get("/invite/{token}")
def redeem(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    user, reason = invites.redeem(db, token)
    if user is None:
        return render(request, "login.html", {"error": reason}, status_code=403)

    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="초대_링크_사용",
        target_type="user",
        target_id=user.id,
        summary=f"{user.name} 님이 초대 링크로 들어왔습니다.",
    )
    response = redirect("/board", message=f"{user.name}님, 환영합니다.")
    set_session(response, user.id)
    return response


@router.get("/logout")
def logout():
    response = redirect("/login", message="로그아웃되었습니다.")
    clear_session(response)
    return response
