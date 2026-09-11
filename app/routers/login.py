# -*- coding: utf-8 -*-
"""로그인 · 로그아웃 · 첫 비밀번호 바꾸기 (CLAUDE.md 4-12).

**초대 링크는 걷었다** (2026-09-11). 휴대폰 홈 화면에 붙인 앱(PWA)은 쿠키가
사파리와 따로라, 사파리에서 연 링크로는 그 앱 안에서 로그인되지 않는다 —
그리고 그 안에는 주소창이 없어 링크를 붙여 넣을 자리도 없다. 링크 하나뿐인
문은 거기서 막힌다.

옛 주소(`/invite/<토큰>`)는 **404 로 두지 않고 로그인 화면으로 보낸다** —
카카오톡에 남은 링크를 누른 사람에게 「없는 주소」 를 보이면 시스템이
고장난 것으로 읽힌다. `invite_tokens` 표는 지우지 않는다 (0장).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app import config
from app.db import get_db
from app.deps import log_activity
from app.domain import login as 로그인
from app.models import User
from app.security import clear_session, get_optional_user, set_session
from app.templating import redirect, render

router = APIRouter()

옛링크안내 = "초대 링크는 이제 쓰지 않습니다. 아이디와 비밀번호로 들어와주세요."


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(get_optional_user)):
    if user is not None:
        return redirect("/")
    return render(request, "login.html", {"session_days": config.SESSION_DAYS})


@router.post("/login")
def login_submit(
    request: Request,
    login_id: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    """**틀린 사유를 가르지 않는다** — 판정은 `domain/login.들어온다` 하나다.

    여기서 사유를 다시 나누면 그 규칙이 두 곳에 있게 되고, 화면 쪽만
    고쳐질 때 「없는 아이디」 와 「틀린 비밀번호」 가 갈라진다.
    비밀번호 원문은 **어디에도 안 찍는다** — 활동 기록에도 남기지 않는다.
    """
    user, reason = 로그인.들어온다(db, login_id, password)
    if user is None:
        return render(
            request,
            "login.html",
            {"error": reason, "login_id": (login_id or "").strip(),
             "session_days": config.SESSION_DAYS},
            status_code=401,
        )

    response = redirect("/", message=f"{user.name}님, 환영합니다.")
    set_session(response, user.id)
    return response


@router.get("/invite/{token}")
def old_invite(token: str):
    """옛 초대 주소. 토큰은 보지 않고 로그인 화면으로 보낸다."""
    return redirect("/login", message=옛링크안내)


@router.get("/logout")
def logout():
    response = redirect("/login", message="로그아웃되었습니다.")
    clear_session(response)
    return response


# ── 첫 비밀번호를 바꾸는 자리 ────────────────────────────────────────
#
# **이 두 길만 `get_optional_user` 로 받는다.** `get_current_user` 로 받으면
# 그 문이 바로 이 화면을 막아서, 바꾸러 가는 길이 스스로를 막는다.


def _본인(user: User | None):
    if user is None:
        return None
    return user


@router.get("/password")
def password_page(request: Request, user: User | None = Depends(get_optional_user)):
    if _본인(user) is None:
        return redirect("/login")
    return render(request, "password_change.html",
                  {"user": user, "min_length": 로그인.MIN_LENGTH})


@router.post("/password")
def password_submit(
    request: Request,
    password: str = Form(""),
    password2: str = Form(""),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if _본인(user) is None:
        return redirect("/login")

    def 다시(말: str):
        return render(request, "password_change.html",
                      {"user": user, "min_length": 로그인.MIN_LENGTH, "error": 말},
                      status_code=400)

    # **판정은 `domain/login.바꿔도되나` 하나다** — 설정 › 내 정보의 그
    # 자리와 같은 것을 부른다(4-17). 여기서 다시 가르면 두 화면이 갈린다
    탈 = 로그인.바꿔도되나(password, password2)
    if 탈:
        return 다시(탈)

    로그인.비밀번호를정한다(db, user, password)
    # **바꿨다는 사실만** 남긴다. 값은 남기지 않는다
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action=로그인.바꾼_행위,
        target_type="user",
        target_id=user.id,
        summary=로그인.바꾼_말(user),
    )
    return redirect("/", message="비밀번호를 바꿨습니다.")
