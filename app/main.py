"""대청부 수련회 총무팀 통합 관리 시스템 — 애플리케이션 진입점."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.config import BASE_DIR, RISK_SCAN_INTERVAL_SECONDS
from app.db import init_db
from app.routers import (
    invite,
    attachments,
    board,
    calendar,
    live,
    budget,
    checklists,
    dashboard,
    drafts,
    expenses,
    export,
    files,
    library,
    meetings,
    notifications,
    reviews,
    schedule,
    settings,
    setup,
    tasks,
    admin_users,
    notify_admin,
)
from app.security import get_optional_user
from app.templating import HASHED_SUFFIXES, render

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dcb.main")

STATIC_DIR = BASE_DIR / "app" / "static"


async def _risk_scan_loop() -> None:
    """주기적으로 모든 회차의 위험(지연·기한임박·담당자 미지정)을 점검한다.

    사람이 매번 확인하러 다니지 않아도 시스템이 스스로 알아차리게 하는 부분.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Retreat
    from app.notifications import run_risk_scan

    while True:
        try:
            await asyncio.sleep(RISK_SCAN_INTERVAL_SECONDS)
            with SessionLocal() as db:
                total = 0
                for retreat in db.scalars(select(Retreat).where(~Retreat.is_archived)):
                    total += run_risk_scan(db, retreat=retreat)
                if total:
                    logger.info("정기 점검: 알림 %d건 생성", total)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - 점검 실패가 서버를 멈추면 안 된다
            logger.exception("정기 위험 점검 실패")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    # 세션 키가 어디서 왔는지 남긴다 (CLAUDE.md 4-12).
    # **지문이 재시작마다 달라지면 그것이 "로그인이 풀린다" 의 원인이다.**
    # 키 자체는 절대 남기지 않는다 — 로그가 새면 세션을 위조할 수 있다.
    from app.config import SECRET_KEY_FINGERPRINT, SECRET_KEY_SOURCE

    logger.info(
        "세션 키: %s · 지문 %s (재시작 전후로 지문이 같으면 로그인이 유지됩니다)",
        SECRET_KEY_SOURCE,
        SECRET_KEY_FINGERPRINT,
    )
    scanner = None
    if RISK_SCAN_INTERVAL_SECONDS > 0:
        scanner = asyncio.create_task(_risk_scan_loop())
    try:
        yield
    finally:
        if scanner is not None:
            scanner.cancel()


app = FastAPI(title="대청부 수련회 관리 시스템", lifespan=lifespan)


class HashedStatic(StaticFiles):
    """`/static/js/calendar.<해시>.js` 를 받아 실제 파일을 내주고,
    **우리가 정한** 캐시 기간을 붙인다.

    ## 왜 캐시 기간을 우리가 말하는가

    지금까지 원점은 아무 캐시 헤더도 보내지 않았고, 4시간(`max-age=14400`)은
    **Cloudflare 가 알아서 정한 값**이었다. 우리가 말한 적이 없으므로 언제
    달라져도 알 수 없고, 실제로 그 4시간 때문에 고친 코드가 사용자에게
    가지 않았다. 주소가 내용에 따라 바뀌므로 같은 주소는 영원히 같은
    내용이고, 그래서 1년 + `immutable` 이 안전하다.

    ## 왜 쿼리가 아니라 경로인가

    `?v=<해시>` 가 통하려면 Cloudflare 의 캐시 키에 쿼리가 들어가야 하는데
    **그 스위치는 이 저장소에 없다.** 대시보드에서 `Ignore Query String` 으로
    바뀌는 순간 1년짜리 옛 파일을 물게 되고, 그건 지난번 4시간보다 훨씬 나쁘다.

    경로에 넣으면 하나 더 얻는다 — **손으로 박을 수가 없다.** 해시 없는
    `/static/js/calendar.js` 는 **404 다.** 조용히 옛 파일을 먹이는 대신
    눈앞에서 깨지는 쪽을 골랐다. `?v=` 는 빠뜨려도 아무 일이 없어서
    실제로 한 화면이 몇 달 동안 `?v=1` 이었다.

    **해시가 맞는지까지는 보지 않는다.** 어떤 8자리가 와도 떼고 지금 파일을
    내준다. 요청마다 파일을 다시 해시로 뜨는 값을 치를 만한 이득이 없어서다 —
    막으려던 것은 "해시를 아예 안 붙이는 것"(그건 위에서 404 로 막힌다)이고,
    `calendar.deadbeef.js` 를 손으로 지어내는 사람은 없다. 덤으로 **열어 둔
    옛 탭이 계속 돈다** — 그 탭은 새로고침하면 어차피 새 주소를 받는다
    (HTML 은 `cf-cache-status: DYNAMIC` 이라 캐시되지 않는다).

    **해시를 붙이지 않는 것들** — 아이콘 같은 것은 그대로 통과시킨다.
    `sw.js` 와 `manifest.webmanifest` 가 고정 주소로 가리키고 있어서
    해시를 붙이면 그쪽이 못 찾는다. 목록은 `templating.HASHED_SUFFIXES`.
    """

    #  이름.<8자리 16진수>.확장자
    _HASHED = re.compile(r"^(?P<stem>.+)\.(?P<stamp>[0-9a-f]{8})(?P<ext>\.[A-Za-z0-9]+)$")

    def get_path(self, scope) -> str:
        path = super().get_path(scope)
        head, name = os.path.split(path)
        m = self._HASHED.match(name)
        if m:
            return os.path.join(head, m["stem"] + m["ext"])
        # 해시가 붙어야 하는 종류인데 안 붙어 있으면 **없는 파일로 둔다.**
        # 손으로 박은 주소가 그 자리에서 드러나야 하기 때문이다.
        if name.endswith(HASHED_SUFFIXES):
            return os.path.join(head, name + ".해시가-빠졌습니다")
        return path

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


app.mount("/static", HashedStatic(directory=str(STATIC_DIR)), name="static")

app.include_router(invite.router)
# 준비 단계 보드가 홈이다 (dashboard 보다 먼저 등록해 "/" 를 잡는다)
app.include_router(board.router)
app.include_router(calendar.router)
app.include_router(attachments.router)
app.include_router(live.router)
app.include_router(setup.router)
app.include_router(library.router)
app.include_router(drafts.router)
app.include_router(dashboard.router)
app.include_router(schedule.router)
app.include_router(tasks.router)
app.include_router(budget.router)
app.include_router(expenses.router)
app.include_router(settings.router)
app.include_router(export.router)
# Phase 2
app.include_router(notifications.router)
app.include_router(notify_admin.router)
app.include_router(admin_users.router)
app.include_router(reviews.router)
app.include_router(files.router)
app.include_router(checklists.router)
app.include_router(meetings.router)


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """브라우저가 기본으로 요청하는 경로. 없으면 로그에 404 가 계속 남는다."""
    return FileResponse(STATIC_DIR / "icons" / "icon-192.png", media_type="image/png")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """서비스워커는 루트 경로에서 서빙되어야 앱 전체를 제어할 수 있다.

    **여기를 `static()` 으로 옮기지 않는다.** 주소에 내용 해시가 붙으면
    배포할 때마다 등록 주소가 달라져 **매번 새로 등록되고 옛 등록이 남는다.**
    `/manifest.webmanifest` 도 같은 이유로 고정 주소다 — 매니페스트 주소가
    바뀌면 홈 화면에 추가한 앱이 다른 앱으로 읽힌다.
    """
    return FileResponse(STATIC_DIR / "js" / "sw.js", media_type="application/javascript")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse(url="/login", status_code=303)

    accepts_html = "text/html" in request.headers.get("accept", "")
    if not accepts_html:
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    user = None
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        from app.db import SessionLocal
        from app.models import User
        from app.security import _user_id_from_request

        uid = _user_id_from_request(request)
        if uid:
            with SessionLocal() as db:
                # 세션이 닫힌 뒤 화면에서 user.department 를 읽으므로 미리 같이 로드한다
                user = db.scalars(
                    select(User).options(joinedload(User.department)).where(User.id == uid)
                ).first()
    except Exception:  # pragma: no cover - 오류 화면에서 또 터지지 않게
        user = None

    return render(
        request,
        "error.html",
        {"status_code": exc.status_code, "detail": exc.detail, "user": user},
        status_code=exc.status_code,
    )


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}
