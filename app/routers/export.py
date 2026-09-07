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
from app.domain.budget import build_budget_summary, entries_of
from app.models import Retreat, User
from app.security import get_current_user

router = APIRouter(prefix="/export")


@router.get("/expenses.xlsx")
def export_expenses(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    summary = build_budget_summary(db, retreat=retreat)
    entries = entries_of(db, retreat)
    buffer = budget_xlsx.write(summary, entries)

    filename = f"{retreat.name}_지출내역.xlsx"
    quoted = urllib.parse.quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
