"""세션 쿠키 + 요청 단위 권한 처리."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, SESSION_COOKIE, SESSION_MAX_AGE
from app.db import get_db
from app.domain import permissions as perm
from app.models import User

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="dcb-session")


class LoginRequired(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")


def set_session(response: Response, user_id: int) -> None:
    token = _serializer.dumps({"uid": user_id})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def _user_id_from_request(request: Request) -> int | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("uid")


def get_optional_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    user_id = _user_id_from_request(request)
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise LoginRequired()
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not perm.can_manage_retreat(user.role):
        raise HTTPException(status_code=403, detail="총무팀(관리자)만 사용할 수 있는 기능입니다.")
    return user


def require_editor(user: User = Depends(get_current_user)) -> User:
    """열람 전용 계정이 쓰기 동작을 시도하는 것을 막는다."""
    if perm.is_readonly(user.role):
        raise HTTPException(status_code=403, detail="열람 전용 계정은 편집할 수 없습니다.")
    return user


def assert_can_edit_department(db, user: User, target_department_id: int | None) -> None:
    """부서 귀속 항목(지출·체크리스트)의 편집 권한 — **키로 비교한다** (2장).

    Department 행은 회차마다 새로 만들어진다. id 로 견주면 새 회차가 열리는
    순간 부서 리더가 자기 부서 지출조차 못 만지는데(403), 화면 버튼도 같은
    비교라 버튼까지 사라져 **조용히** 틀린다. 키를 알아보려면 두 부서 행을
    읽어야 해서 db 를 받는다. 키 없는 부서(구설계 데이터)만 행(id)으로
    견준다 — None == None 으로 남의 부서까지 통과시키면 안 된다.
    """
    from app.domain.departments import department_key_of
    from app.models import Department

    target = db.get(Department, target_department_id) if target_department_id else None
    if target is not None and target.key:
        ok = perm.can_edit_department_by_key(
            role=user.role,
            user_department_key=department_key_of(db, user),
            target_department_key=target.key,
        )
    else:
        ok = perm.can_edit_department_content(
            role=user.role,
            user_department_id=user.department_id,
            target_department_id=target_department_id,
        )
    if not ok:
        raise HTTPException(
            status_code=403, detail="내 부서의 항목만 편집할 수 있습니다."
        )
