"""대청부 수련회 총무팀 통합 관리 시스템 — 애플리케이션 진입점."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.config import BASE_DIR
from app.db import init_db
from app.routers import auth, budget, dashboard, expenses, export, schedule, settings, tasks
from app.security import get_optional_user
from app.templating import render

logging.basicConfig(level=logging.INFO)

STATIC_DIR = BASE_DIR / "app" / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="대청부 수련회 관리 시스템", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(schedule.router)
app.include_router(tasks.router)
app.include_router(budget.router)
app.include_router(expenses.router)
app.include_router(settings.router)
app.include_router(export.router)


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


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
        from app.db import SessionLocal
        from app.models import User
        from app.security import _user_id_from_request

        uid = _user_id_from_request(request)
        if uid:
            with SessionLocal() as db:
                user = db.get(User, uid)
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
