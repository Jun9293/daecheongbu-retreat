"""수입 (CLAUDE.md 7-6) — 수입 항목과 **회비·후원금 입금 내역**.

전에는 수입 표가 예산 화면 아래에 붙어 있었다. 입금 내역이 붙으면서 한
화면에 지출 예산 · 수입 항목 · 입금 줄 셋이 쌓여 무엇을 보러 온 화면인지
읽히지 않아 떼어 냈다. **수입 항목을 고치는 길은 그대로 하나다** —
`/budget/incomes*` 가 그 길이고 여기서 새로 짓지 않는다(같은 표에 쓰는
길이 둘이 되면 갈린다).

캡처는 Claude 에게 보여 주고 줄을 받는다. 세는 것과 가르는 것은 전부
`domain/deposits.py` 에 있다.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.domain import deposits as D
from app.domain import llm
from app.domain.budget import build_budget_summary, 수입종류
from app.models import IncomeDeposit, Retreat, User
from app.security import get_current_user, require_admin
from app.templating import redirect, render

router = APIRouter(prefix="/income")

# 캡처 한 장의 상한. Anthropic 이 그림 한 장을 5MB 까지 받는다 — 그보다 크면
# 보내 봐야 거절당하므로 **보내기 전에** 우리 말로 막는다 (4-9 의 그 자리).
MAX_CAPTURE_BYTES = 5 * 1024 * 1024


def _돌아갈곳(retreat: Retreat, 필터: str) -> str:
    return f"/income?retreat_id={retreat.id}" + (f"&filter={필터}" if 필터 else "")


@router.get("")
def income_page(
    request: Request,
    filter: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    summary = build_budget_summary(db, retreat=retreat)
    줄들 = D.목록(db, retreat_id=retreat.id)
    보일줄 = D.걸러낸다(줄들, filter)
    return render(
        request,
        "income.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "summary": summary,
            "수입종류": 수입종류,
            "입금줄들": [
                {
                    "d": d,
                    "회비": D.회비몫(d),
                    "후원금": D.후원금몫(d),
                    "분류": D.분류(d),
                    "추정": D.추정인가(d),
                }
                for d in 보일줄
            ],
            "입금합": D.합(줄들),
            "필터": filter,
            "키상태": llm.상태(),
            "active_tab": "income",
            "page_subtitle": "수입",
        },
    )


@router.post("/deposits/capture")
def upload_capture(
    capture: UploadFile = File(...),
    filter: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    """입금 내역 캡처를 읽어 **전부 후원금 · 추정**으로 담는다 (7-6).

    읽은 만큼만 반영하고 **「다 읽었다」 고 말하지 않는다** — 캡처가 잘렸거나
    흐린 줄이 있으면 그만큼 빠진 채로 들어온다.
    """
    media_type = (capture.content_type or "").split(";")[0].strip()
    if media_type not in llm.ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"캡처는 PNG · JPEG · GIF · WEBP 만 올릴 수 있습니다 (받은 것: {media_type or '알 수 없음'}).",
        )
    data = capture.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > MAX_CAPTURE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"캡처는 5MB 이하만 올릴 수 있습니다 (받은 것: {len(data) / 1024 / 1024:.1f}MB).",
        )

    try:
        줄들, 대답 = D.읽는다(data, media_type)
    except llm.LlmUnavailable as exc:
        # 키가 없는 것과 API 가 죽은 것 — 사람이 할 일이 달라 그대로 옮긴다
        raise HTTPException(status_code=503, detail=f"캡처를 읽지 못했습니다 — {exc}") from None
    except D.못읽음:
        raise HTTPException(
            status_code=502,
            detail="캡처를 읽지 못했습니다 — 다시 찍어 올리거나 직접 입력해 주세요.",
        ) from None

    if not 줄들:
        return redirect(
            _돌아갈곳(retreat, filter),
            message="캡처를 읽지 못했습니다 — 다시 찍어 올리거나 직접 입력해 주세요."
            f" (약 {대답.원:,.0f}원)",
        )

    넣음, 건너뜀 = D.담는다(db, retreat_id=retreat.id, 줄들=줄들)
    db.commit()
    말 = (
        f"캡처 1장 · 입금 {len(줄들)}건 읽음"
        + (f" · 겹친 입금 {건너뜀}건 건너뜀" if 건너뜀 else "")
        + f" · {넣음}건 담음 (약 {대답.원:,.0f}원)."
        " 캡처에 안 보이거나 흐린 줄은 빠졌을 수 있습니다 — 눈으로 맞춰 보세요."
    )
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="입금_캡처읽기",
        target_type="income_deposit",
        target_id=retreat.id,
        summary=f"읽음 {len(줄들)} · 담음 {넣음} · 겹침 {건너뜀}",
    )
    return redirect(_돌아갈곳(retreat, filter), message=말)


def _그줄(db: Session, retreat: Retreat, deposit_id: int) -> IncomeDeposit:
    d = db.get(IncomeDeposit, deposit_id)
    if d is None or d.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="입금 줄을 찾을 수 없습니다.")
    return d


@router.post("/deposits/{deposit_id}")
def save_deposit(
    deposit_id: int,
    kind: str = Form(D.후원금),
    fee_amount: str = Form(""),
    filter: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    """한 줄의 분류를 정한다 — 저장하면 **「추정」 이 풀린다** (7-6)."""
    d = _그줄(db, retreat, deposit_id)
    if d.canceled_at is not None:
        raise HTTPException(status_code=409, detail="취소된 입금 줄입니다. 되살린 뒤에 고치세요.")
    전 = {"회비": D.회비몫(d), "후원금": D.후원금몫(d)}
    if kind == D.회비:
        raw = (fee_amount or "").strip().replace(",", "")
        try:
            # 비우면 전액 회비다 — 회비로 바꾸려고 금액을 또 치게 하지 않는다
            몫 = d.amount if raw == "" else int(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail="회비 금액은 숫자로 적어주세요.") from None
    elif kind == D.후원금:
        몫 = None
    else:
        raise HTTPException(status_code=400, detail=f"모르는 분류입니다: {kind}")
    try:
        D.사람이정한다(d, 회비금액=몫)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="입금_분류",
        target_type="income_deposit",
        target_id=d.id,
        summary=f"{d.depositor} / {d.amount:,}원 → {D.분류(d)}",
        before_value=전,
        after_value={"회비": D.회비몫(d), "후원금": D.후원금몫(d)},
    )
    return redirect(_돌아갈곳(retreat, filter), message="입금 줄을 저장했습니다.")


@router.post("/deposits/{deposit_id}/cancel")
def toggle_deposit_canceled(
    deposit_id: int,
    filter: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    """잘못 읽힌 줄은 **지우지 않고 취소 표시**를 단다 (0장 · 7-3 과 같은 모양).

    캡처를 읽는 것은 사람이 아니라 모델이라 틀린 줄이 들어올 수 있다. 지우면
    그 줄이 왜 있었는지가 함께 사라지고, 같은 캡처를 다시 올리면 겹침으로
    걸러지지도 않는다.
    """
    d = _그줄(db, retreat, deposit_id)
    if d.canceled_at is None:
        d.canceled_at = dt.datetime.now()
        action, 말 = "입금_취소", "입금 줄을 취소했습니다. 행은 흐리게 남고 합계에서 빠집니다."
    else:
        d.canceled_at = None
        action, 말 = "입금_되살림", "입금 줄을 되살렸습니다."
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action=action,
        target_type="income_deposit",
        target_id=d.id,
        summary=f"{d.depositor} / {d.amount:,}원",
    )
    return redirect(_돌아갈곳(retreat, filter), message=말)
