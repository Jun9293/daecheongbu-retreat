"""대청부 수련회 총무팀 통합 관리 시스템 — 애플리케이션 진입점."""

from __future__ import annotations

import asyncio
import logging
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
from app.templating import render

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
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
    """서비스워커는 루트 경로에서 서빙되어야 앱 전체를 제어할 수 있다."""
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
