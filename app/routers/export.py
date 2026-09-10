"""재정 엑셀 내려받기 — 화면과 같은 함수의 결과를 내보낸다 (7-3).

시트를 만드는 곳은 domain.budget_xlsx 하나다. 숫자는 전부 domain.budget 의
summary 에서 나오고, 여기서는 그것을 파일로 흘려보내기만 한다.
"""

from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_retreat
from app.domain import budget_xlsx
from app.domain import permissions as perm
from app.domain.budget import build_budget_summary, entries_of
from app.models import Retreat, User
from app.security import require_editor

router = APIRouter(prefix="/export")


@router.get("/expenses.xlsx")
def export_expenses(
    db: Session = Depends(get_db),
    # **편집자 이상이 받습니다. 열람 전용만 못 받습니다.**
    # 전에는 총무팀만 받았는데, 그러면 화면은 계좌만 빼고 누구나 보는데
    # 파일은 통째로 막혀 **같은 표인데 보는 사람이 갈립니다** (5-8).
    # 막을 것은 표가 아니라 계좌라, 계좌 칸만 빼고 표는 함께 봅니다.
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    summary = build_budget_summary(db, retreat=retreat)
    # 취소된 지출은 결산 파일에 넣지 않는다 (7-4) — summary 가 이미 빼고
    # 세므로, 행만 남기면 파일 안에서 합계와 행이 서로 안 맞는다
    entries = [e for e in entries_of(db, retreat) if e.canceled_at is None]
    # **판정은 여기서 하지 않습니다** — `permissions.can_see_account` 하나가
    # 정하고 화면·칩도 같은 것을 부릅니다. 못 보는 사람의 파일에는 계좌
    # **칸 자체가 없습니다**(빈 칸이 아니라 없는 칸).
    buffer = budget_xlsx.write(
        summary, entries, 계좌를_보인다=perm.can_see_account(user))

    filename = f"{retreat.name}_지출내역.xlsx"
    quoted = urllib.parse.quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
