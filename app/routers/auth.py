"""전화번호 인증 로그인."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import DEV_MODE
from app.db import get_db
from app.deps import log_activity
from app.domain.auth import AuthError, issue_auth_code, normalize_phone, verify_auth_code
from app.domain.permissions import ADMIN
from app.models import User
from app.security import clear_session, get_optional_user, set_session
from app.sms import send_auth_code
from app.templating import redirect, render

router = APIRouter()


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(get_optional_user)):
    if user is not None:
        return redirect("/")
    return render(request, "login.html", {"step": "phone"})


@router.post("/login/code")
def request_code(
    request: Request,
    phone_number: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        phone = normalize_phone(phone_number)
    except ValueError as exc:
        return render(
            request, "login.html", {"step": "phone", "error": str(exc)}, status_code=400
        )

    user_count = db.scalar(select(func.count()).select_from(User))
    known = db.scalars(select(User).where(User.phone_number == phone)).first()
    if known is None and user_count:
        return render(
            request,
            "login.html",
            {
                "step": "phone",
                "error": "등록되지 않은 번호입니다. 총무팀에 계정 등록을 요청해주세요.",
            },
            status_code=403,
        )

    code = issue_auth_code(db, phone_number=phone)
    try:
        send_auth_code(phone, code)
    except RuntimeError as exc:
        return render(
            request, "login.html", {"step": "phone", "error": str(exc)}, status_code=500
        )

    return render(
        request,
        "login.html",
        {
            "step": "code",
            "phone_number": phone,
            # 개발 모드에서만 화면에 코드를 노출한다 (SMS 벤더 연동 전 테스트용)
            "dev_code": code if DEV_MODE else None,
            "is_first_user": known is None and not user_count,
        },
    )


@router.post("/login/verify")
def verify(
    request: Request,
    phone_number: str = Form(...),
    code: str = Form(...),
    name: str = Form(""),
    db: Session = Depends(get_db),
):
    phone = normalize_phone(phone_number)
    try:
        verify_auth_code(db, phone_number=phone, code=code.strip())
    except AuthError as exc:
        return render(
            request,
            "login.html",
            {"step": "code", "phone_number": phone, "error": str(exc)},
            status_code=400,
        )

    user = db.scalars(select(User).where(User.phone_number == phone)).first()
    if user is None:
        # 최초 1인은 총무팀(관리자)으로 자동 등록된다.
        user = User(
            phone_number=phone,
            name=(name.strip() or "총무팀"),
            role=ADMIN,
        )
        db.add(user)
        db.commit()
        log_activity(
            db,
            retreat_id=None,
            actor=user,
            action="최초_관리자_등록",
            target_type="user",
            target_id=user.id,
            summary=f"{user.name}({phone}) 계정이 총무팀 관리자로 생성됨",
        )

    if not user.is_active:
        return render(
            request,
            "login.html",
            {"step": "phone", "error": "비활성화된 계정입니다. 총무팀에 문의해주세요."},
            status_code=403,
        )

    response = redirect("/", message=f"{user.name}님, 환영합니다.")
    set_session(response, user.id)
    return response


@router.get("/logout")
def logout():
    response = redirect("/login", message="로그아웃되었습니다.")
    clear_session(response)
    return response
