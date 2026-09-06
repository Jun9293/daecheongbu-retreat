"""옛 /schedule (이전 설계의 일정표) — 화면은 지웠다 (14장 「옛 화면 걷어내기」).

그 자리는 5-8 봉사자 시간표(/live/staff)가 맡는다. 옛 링크가 카카오톡 어딘가에
남아 있을 수 있으므로 301 로 잇는다. `ScheduleDay`·`ScheduleItem` **표와 행은
남긴다** — 아무것도 삭제하지 않는다 (0장 첫 원칙).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/schedule")


@router.get("")
def schedule_moved():
    return RedirectResponse("/live/staff", status_code=301)
