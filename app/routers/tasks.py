"""목록 보기 (CLAUDE.md 4-14).

옛 할 일(Task) 화면을 걷어내고 TaskRun 목록으로 다시 만들었다. 펼쳐지는
상세는 보드 드로어와 **같은 Jinja partial · 같은 JS** 다 — 목록 전용 상세를
만들면 논의·첨부·상태가 두 곳에서 갈린다.

옛 `/tasks/{id}` 는 301 로 `/tasks` 에 보낸다. 그 id 는 옛 Task 표의 것이라
run 으로 잇지 못한다 — 표와 행은 남긴다(0장: 아무것도 삭제하지 않는다).
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat
from app.domain import tasklist
from app.domain.departments import department_key_of
from app.models import Retreat, User
from app.security import get_current_user
from app.templating import render

router = APIRouter()


@router.get("/tasks")
def tasks_page(
    request: Request,
    scope: str = "all",
    state: str = "",
    dept: str = "",
    task: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """목록. `?retreat_id=N` 은 get_current_retreat 가 받아 그 회차로 전환한다 —
    알림 1,483건이 전부 이 주소라 이 길이 끊기면 알림이 끊긴다 (4-11).
    `?task=<run_id>` 는 그 행을 펼친 채 연다 — 보드·달력과 같은 이름이다."""
    my_key = department_key_of(db, user)
    view = tasklist.build(
        db,
        retreat,
        today=dt.date.today(),
        my_key=my_key,
        # 총무팀은 전부 선명하게 — 홈·옛 화면과 같은 규칙 (4-15 · 9장)
        dim=user.role != "admin",
        scope=scope,
        state=state,
        dept=dept,
    )
    # ?task= 로 온 업무가 완료 접힘 안에 있으면 접힌 채 열 수 없다 —
    # 서버가 미리 펴 둔다
    open_in_done = task is not None and any(
        r["run_id"] == task for r in view.done_rows
    )
    return render(
        request,
        "tasks.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "view": view,
            "open_task": task,
            "open_in_done": open_in_done,
            "active_tab": "tasks",
            "page_subtitle": "목록",
        },
    )


@router.get("/tasks/{task_id:int}")
def old_task_detail(task_id: int):
    """옛 상세 주소. 그 id 는 옛 Task 표의 것이라 run 으로 잇지 못한다 —
    `/tasks` 로 301 (4-14)."""
    return RedirectResponse("/tasks", status_code=301)
