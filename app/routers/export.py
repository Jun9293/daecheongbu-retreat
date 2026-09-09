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
from app.security import require_admin

router = APIRouter(prefix="/export")


@router.get("/expenses.xlsx")
def export_expenses(
    db: Session = Depends(get_db),
    # **총무팀(admin)만 받습니다.** 이 파일에는 지출자 계좌가 두 시트에
    # 들어갑니다(`budget_xlsx` 의 지출 상세·환급 대상자). 화면에서 계좌를
    # 가려 놓고 파일을 열어 두면 가린 뜻이 없고, **파일 쪽이 더 넓습니다** —
    # 한 번 나가면 손을 떠나 돌아다닙니다 (5-8).
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    summary = build_budget_summary(db, retreat=retreat)
    # 취소된 지출은 결산 파일에 넣지 않는다 (7-4) — summary 가 이미 빼고
    # 세므로, 행만 남기면 파일 안에서 합계와 행이 서로 안 맞는다
    entries = [e for e in entries_of(db, retreat) if e.canceled_at is None]
    buffer = budget_xlsx.write(summary, entries)

    filename = f"{retreat.name}_지출내역.xlsx"
    quoted = urllib.parse.quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
