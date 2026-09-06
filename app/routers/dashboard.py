"""옛 /dashboard (이전 설계의 홈) — 화면은 지웠다 (14장 「옛 화면 걷어내기」).

그 자리는 4-15 홈(/)이 맡는다. 옛 링크가 남아 있을 수 있으므로 301 로 잇는다.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/dashboard")
def dashboard_moved():
    return RedirectResponse("/", status_code=301)
