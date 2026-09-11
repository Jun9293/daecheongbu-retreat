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


class 비밀번호를바꿔야함(Exception):
    """관리자가 발급한 첫 비밀번호로 들어온 채다 (4-12).

    **막는 곳은 여기 하나다** — `get_current_user`. 화면마다 걸면 새 화면이
    하나 늘 때마다 그 자리를 안 걸게 되고, 안 건 화면만 조용히 열린다.
    바꾸는 화면 자신은 이 문을 안 쓴다(`get_optional_user` 로 받는다) —
    그러지 않으면 바꾸러 가는 길이 스스로를 막는다.
    """


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
    _mark_first_seen(db, user)
    return user


def _mark_first_seen(db: Session, user: User) -> None:
    """**처음 화면을 연 때를 한 번만 찍는다** (4-16).

    문이 여기 하나라 여기서 찍는다 — 초대 링크를 여는 자리에서 찍으면
    링크 없이 세션이 살아 있는 계정(이미 쓰던 사람)은 영영 안 찍힌다.
    NULL 일 때만 쓰므로 계정마다 한 번이고, 그 뒤로는 읽기만 한다.

    이 값이 사이드바 배지의 경계다: **들어오기 전에 쌓인 것은 안 센다.**
    처음 들어온 사람이 275 를 보면 시스템이 밀린 것으로 읽히는데, 그건
    그 사람이 놓친 것이 아니라 그 사람이 없던 동안 쌓인 것이다.
    """
    if getattr(user, "first_seen_at", None) is not None:
        return
    import datetime as dt

    # **저장하는 시각은 이 저장소에서 전부 UTC 이고 tz 를 안 붙인다**
    # (`models._now`). 벽시계로 찍으면 아홉 시간 앞서서, 들어온 직후
    # 아홉 시간 동안 온 알림이 「들어오기 전 것」 으로 밀린다.
    user.first_seen_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    db.commit()


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise LoginRequired()
    # 첫 비밀번호인 채로는 아무 화면도 안 연다 (4-12). 인증 의존이 하나라
    # 여기서 한 번 막으면 전부 막힌다.
    #
    # **비밀번호가 있을 때만 막는다.** 이 칸이 붙기 전에 만들어진 계정은
    # 기본값이 참인 채로 서 있는데 **바꿀 비밀번호가 아예 없다** — 그런
    # 사람에게 「총무팀이 전해 준 첫 비밀번호를 바꾸세요」 라고 말하면
    # 거짓이고, 세션이 살아 있던 열몇 사람이 서버를 다시 켜는 순간 그
    # 화면에 갇힌다. 관리자가 발급하면 해시가 생기면서 그때 막힌다.
    if getattr(user, "must_change_password", False) and getattr(user, "password_hash", None):
        raise 비밀번호를바꿔야함()
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not perm.is_admin(user):
        raise HTTPException(status_code=403, detail="총무팀(관리자)만 사용할 수 있는 기능입니다.")
    return user


def require_editor(user: User = Depends(get_current_user)) -> User:
    """열람 전용 계정이 쓰기 동작을 시도하는 것을 막는다."""
    if perm.is_readonly(user):
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
    from app.models import Department

    target = db.get(Department, target_department_id) if target_department_id else None
    # **내 부서 중 하나인가** (도막 4) — 판정은 permissions 하나다. 키 없는
    # 부서(구설계 데이터)는 견줄 근거가 없어 admin 만 통과한다
    ok = perm.can_edit_department_key(user, target.key if target is not None else None)
    if not ok:
        raise HTTPException(
            status_code=403, detail="내 부서의 항목만 편집할 수 있습니다."
        )
