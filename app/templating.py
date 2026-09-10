"""Jinja2 템플릿 환경과 공용 헬퍼."""

from __future__ import annotations

import datetime as dt
import os
import urllib.parse

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR
from app.domain import permissions as perm

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# **화면과 코드는 같이 움직여야 합니다.**
#
# Jinja 는 기본으로 요청마다 템플릿을 디스크에서 다시 읽습니다. 그런데 파이썬은
# 켤 때 읽은 모듈을 그대로 들고 있습니다. 그래서 서버를 켜 둔 채 코드를 고치면
# **새 화면 + 옛 코드** 가 짝지어져서, 화면이 라우터가 아직 안 넘기는 값을 읽고
# 500 이 납니다. 실제로 이 조합으로 `/live` 와 `/live/staff` 가 세 번 죽었습니다.
# 코드는 맞았고 테스트도 통과했는데 돌던 서버만 옛것이었습니다.
#
# 그래서 **운영에서는 템플릿도 켤 때 한 번만 읽습니다.** 둘이 함께 낡으므로
# 화면이 잠깐 옛것일 수는 있어도 서로 어긋나지는 않습니다 — 고친 것을 반영하려면
# 어차피 서버를 다시 켜야 하고, 그건 코드도 마찬가지였습니다.
#
# 개발에서는 `--reload` 가 프로세스를 통째로 다시 띄우므로 켜 둡니다
# (`scripts/devserve.bat` 이 `DCB_DEV` 와 `--reload-include *.html` 을 함께 줍니다).
templates.env.auto_reload = bool(os.environ.get("DCB_DEV"))

FLASH_COOKIE = "dcb_flash"


# ── 정적 파일 주소 ────────────────────────────────────────────────────
#
# **번호를 손으로 올리지 않습니다.** `?v=1` 을 화면마다 박아 두고 고칠 때마다
# 사람이 올리는 방식이었는데, 달력 쪽이 계속 1 이었습니다. 그래서 기간 비침을
# 만들어 배포했는데도 화면에 나타나지 않았습니다 — 사람에게는 "기능이 안
# 만들어진 것" 으로 보였습니다.
#
# **왜 그렇게까지 되는가** — 원점은 `Cache-Control` 을 보내지 않지만
# Cloudflare 가 `/static` 에 `max-age=14400`(4시간)을 붙입니다. 그 동안
# 브라우저는 **서버에 물어보지도 않고** 갖고 있던 파일을 씁니다. HTML 은
# 캐시되지 않으므로(`cf-cache-status: DYNAMIC`) 화면만 새것이 되고 코드는
# 옛것이 됩니다 — 새 화면 + 옛 코드, 11-2 가 적어 둔 그 조합입니다.
#
# 그래서 **파일 내용에서 번호를 만듭니다.** 파일이 바뀌면 주소가 바뀌고,
# 안 바뀌면 그대로라 쓸데없이 다시 받지도 않습니다.
#
# **번호는 쿼리(`?v=`)가 아니라 경로에 넣습니다** — `/static/js/calendar.<해시>.js`.
# 쿼리로 두면 Cloudflare 의 캐시 키에 쿼리가 들어가야만 통하는데, **그 스위치는
# 이 저장소에 없습니다.** 대시보드에서 `Ignore Query String` 으로 바뀌는 순간
# 사람들이 1년짜리 옛 파일을 물게 되고, 그건 지난번 4시간보다 훨씬 나쁩니다.
#
# 경로에 넣으면 하나 더 얻습니다 — **손으로 박을 수가 없습니다.** 해시 없는
# 주소는 파일이 나오지 않으므로(`main.HashedStatic`) 그 자리에서 드러납니다.
# 조용히 옛 파일을 먹이는 대신 눈앞에서 깨지는 쪽을 고른 것입니다.
_STATIC_DIR = BASE_DIR / "app" / "static"
_static_stamps: dict[str, str] = {}

# 해시를 붙이는 종류. **아이콘·매니페스트는 뺍니다** — 서비스워커와
# `manifest.webmanifest` 가 고정 주소로 가리키고 있어서(11-3), 해시를 붙이면
# 그쪽이 못 찾습니다.
HASHED_SUFFIXES = (".js", ".css")


def static(path: str) -> str:
    """`/static/js/calendar.<해시>.js` — 번호가 **경로 안**에 있다."""
    stamp = _static_stamps.get(path)
    # 개발에서는 매번 다시 잰다. 운영에서는 켤 때 한 번이면 된다 —
    # 고친 것을 반영하려면 어차피 서버를 다시 켜야 한다 (11-2).
    if stamp is None or templates.env.auto_reload:
        import hashlib

        try:
            data = (_STATIC_DIR / path).read_bytes()
            stamp = hashlib.md5(data).hexdigest()[:8]
        except OSError:
            # 없는 파일이라도 화면을 죽이지 않는다 — 그건 404 로 드러난다
            stamp = "0"
        _static_stamps[path] = stamp

    for suffix in HASHED_SUFFIXES:
        if path.endswith(suffix):
            return f"/static/{path[: -len(suffix)]}.{stamp}{suffix}"
    return f"/static/{path}"


templates.env.globals["static"] = static


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


def can_edit_dept(user, department) -> bool:
    """화면의 편집 버튼 — 서버 판정(assert_can_edit_department)과 **같은 축**
    (부서 키 · 2장 · 「내 부서 중 하나인가」 · 도막 4)으로 가른다.
    Department **행**을 받는다. id 로 견주면 새 회차가 열리는 순간 버튼이
    조용히 사라져, 403 이 나기도 전에 길이 없다.
    """
    return perm.can_edit_department_key(
        user, department.key if department is not None else None)


def is_other_dept(user, department) -> bool:
    """내 부서가 아닌 항목인지 — 흐리게 표시할 대상. **키로, 집합으로** 비교한다
    (2장 · 도막 4). 총무팀은 아무것도 흐리지 않는다. 소속이 하나도 없으면
    부서 있는 항목이 전부 남의 것이다 — None == None 으로 내 것이 되면 안 된다.
    """
    if user is None or perm.is_admin(user):
        return False
    mine = perm.my_dept_keys(user)
    if department is None:
        return True
    if not mine or not department.key:
        return True
    return department.key not in mine


templates.env.globals["ROLE_LABELS"] = perm.ROLE_LABELS
templates.env.globals["today"] = dt.date.today
templates.env.globals["can_edit_dept"] = can_edit_dept
templates.env.globals["is_other_dept"] = is_other_dept
# **열람 전용인가는 사람을 받는다** (도막 4 · ②) — 소속이 없는 일반도 열람 전용이다
templates.env.globals["is_readonly"] = perm.is_readonly
templates.env.globals["내_부서키"] = perm.my_dept_keys
templates.env.globals["is_lead_of"] = perm.is_lead_of
# **계좌를 보일지 말지는 한 함수가 정한다** — 화면·엑셀·칩이 같이 쓴다
templates.env.globals["계좌를_본다"] = (
    lambda user: user is not None and perm.can_see_account(user))
# 엑셀을 받을 수 있는가 — 열람 전용만 못 받는다. 계좌가 보이는지와 다른 물음이다
templates.env.globals["엑셀을_받는다"] = (
    lambda user: user is not None and not perm.is_readonly(user))
templates.env.globals["is_admin"] = lambda user: user is not None and perm.is_admin(user)
# 총무팀 일정(진행 화면)의 이름 — 사이드바와 화면 제목이 같은 한 곳(domain.live)에서 (5장)
from app.domain.live import SCREEN_TITLE as _live_title  # noqa: E402

templates.env.globals["live_title"] = _live_title


def _active_draft(context: dict) -> dict | None:
    """진행 중인 회차 준비가 있으면 상단에 표시한다."""
    if context.get("user") is None:
        return None
    from app.db import SessionLocal
    from app.domain import drafts as draft_domain

    with SessionLocal() as db:
        draft = draft_domain.active_draft(db)
        if draft is None:
            return None
        data = draft_domain.progress(draft)
        return {"name": draft.name, "submitted": data["submitted"], "total": data["total"]}


def _badge_counts(context: dict) -> dict:
    """사이드바 배지의 두 항 (4-0) — 안 읽은 **시스템** 알림 + 답 대기 중 요청.

    사람 발신(확인요청)은 앞항에서 빼고 뒷항으로만 센다 — 안 그러면 요청
    하나가 배지에 +2 로 뜬다(봐둘것 T-c 였던 것). 뒷항은 알림 페이지의
    「답을 기다리는 것」 칩과 **같은 함수**(pending_for_user)라 두 수가 같다.
    """
    user = context.get("user")
    if user is None:
        return {"unread_count": 0, "pending_review_count": 0}

    from app.db import SessionLocal
    from app.notifications import system_unread_count

    with SessionLocal() as db:
        counts = {"unread_count": system_unread_count(db, user), "pending_review_count": 0}
        retreat = context.get("retreat")
        if retreat is not None:
            from app.routers.reviews import pending_for_user

            counts["pending_review_count"] = len(pending_for_user(db, user, retreat))
    return counts


def _side_dept_name(context: dict) -> str | None:
    """사이드바 사용자 카드의 소속 한 줄 — 「헤브론 리더 · 총무팀」 (도막 4).

    부서 이름은 **지금 보는 회차의 이름**을 우선 쓴다 (키로 찾는다 · 2장).
    소속이 없으면 None — 화면이 「부서 미지정」 을 낸다."""
    user = context.get("user")
    if user is None:
        return None
    retreat = context.get("retreat")
    names = {}
    if retreat is not None:
        names = {d.key: d.name for d in retreat.departments if d.key}
    return perm.describe(user, dept_names=names) or None


def _external_link(context: dict) -> dict | None:
    """사이드바의 바깥 링크 (도막 4) — 로그인한 화면에서만, DB 에 값이 있을 때만."""
    if context.get("user") is None:
        return None
    from app.db import SessionLocal
    from app.routers.settings import external_link

    with SessionLocal() as db:
        return external_link(db)


def render(
    request: Request, template_name: str, context: dict, status_code: int = 200
) -> HTMLResponse:
    flash = request.cookies.get(FLASH_COOKIE)
    ctx = {
        "request": request,
        "flash": urllib.parse.unquote(flash) if flash else None,
        **_badge_counts(context),
        "active_draft": _active_draft(context),
        "side_dept_name": _side_dept_name(context),
        "external_link": _external_link(context),
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
