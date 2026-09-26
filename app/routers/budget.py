"""예산 (CLAUDE.md 7-3) — 구분 › 항목 › 세부항목 · 소계 · 수입 · 잔액.

숫자는 전부 domain.budget 의 summary 에서 온다 — 여기서 세지 않는다.
예산금액 = 단가 × 명수 × 횟수, 셋이 비면 직접 입력값. 넷 다 저장한다.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.domain.budget import build_budget_summary, income_amount_of, planned_amount_of
from app.models import BudgetCategory, IncomeItem, Retreat, User
from app.security import get_current_user, require_admin
from app.templating import redirect, render

router = APIRouter(prefix="/budget")


def _바뀐칸만(전: dict, 후: dict) -> tuple[dict, dict]:
    """활동 기록에 남길 전후 — **바뀐 칸만** (7-3 · 7-4 · 재정 차례 5). 비면 기록을 안 남긴다."""
    칸들 = [k for k in 후 if 전.get(k) != 후[k]]
    return {k: 전.get(k) for k in 칸들}, {k: 후[k] for k in 칸들}


def _int_or_none(raw: str) -> int | None:
    raw = (raw or "").strip()
    if raw == "":
        return None
    return int(raw)


@router.get("")
def budget_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    summary = build_budget_summary(db, retreat=retreat)
    return render(
        request,
        "budget.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "summary": summary,
            "예산행들": [_행모양(row) for row in summary.categories],
            "active_tab": "budget",
            "page_subtitle": "예산",
        },
    )


def _apply_fields(
    category: BudgetCategory,
    *,
    level1: str,
    level2: str,
    level3: str,
    unit_price: str,
    headcount: str,
    times: str,
    planned_amount: int,
) -> None:
    category.level1 = level1.strip()
    category.level2 = level2.strip()
    category.level3 = level3.strip() or None
    category.unit_price = _int_or_none(unit_price)
    category.headcount = _int_or_none(headcount)
    category.times = _int_or_none(times)
    # 셋이 다 있으면 계산이 이기고, 비면 직접 입력값이다 (7-3) — 한 곳(domain)에서
    category.planned_amount = max(
        0,
        planned_amount_of(
            category.unit_price, category.headcount, category.times, planned_amount
        ),
    )


def _행모양(row) -> dict:
    """화면이 편집할 때 쓰는 줄 하나 (7-3 · 2026-09-26).

    **보는 판과 같은 값에서 나온다** — 서버가 그린 표와 편집 표가 다른 것을
    보이면 어느 쪽이 맞는지 화면이 말해 주지 않는다. `spent` 는 읽기만 하는
    값이라 함께 싣고(편집해도 안 보낸다), 나머지가 저장 대상이다.
    """
    cat = row.category
    return {
        "id": cat.id,
        "level1": cat.level1,
        "level2": cat.level2,
        "level3": cat.level3 or "",
        "unit_price": cat.unit_price,
        "headcount": cat.headcount,
        "times": cat.times,
        "planned_amount": cat.planned_amount,
        "note": cat.note or "",
        "spent": row.spent,
    }


class 예산줄(BaseModel):
    id: int | None = None
    level1: str = ""
    level2: str = ""
    level3: str = ""
    unit_price: int | None = None
    headcount: int | None = None
    times: int | None = None
    planned_amount: int = 0
    note: str = ""


class 예산표(BaseModel):
    rows: list[예산줄]
    removed: list[int] = []


@router.post("/bulk")
def save_bulk(
    payload: 예산표,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    """표 전체를 한 번에 저장한다 (7-3 · 2026-09-26 사람이 정한 확정본).

    줄마다 「수정」 을 두지 않고 **「전체 편집」 하나**로 바꾸므로, 저장도 한
    번이다. 순서(`sort_order`)가 여기서 정해진다 — 화면에서 끌어 옮긴 자리가
    곧 그 값이다.

    **전부 되거나 전부 안 된다.** 한 줄이 틀렸는데 앞의 열 줄만 저장되면,
    화면은 「실패」 인데 표는 반쯤 바뀐 채로 남는다(7-5 가 들여오기에서 막은
    그 모양). 그래서 먼저 다 읽어 보고, 하나라도 걸리면 아무것도 안 바꾼다.

    **빼는 것은 지우는 것이 아니다**(0장 · 7-3) — `removed` 는 **취소 표시**를
    찍을 뿐이고 행과 걸린 지출은 남는다. 되살리는 길도 그대로다. 화면의 말도
    「취소」 그대로다: 7-3 이 이미 쓰는 말이라 새 말을 지어내지 않는다.
    """
    있는것 = {
        cat.id: cat
        for cat in db.scalars(
            select(BudgetCategory).where(BudgetCategory.retreat_id == retreat.id)
        )
    }

    # ── 먼저 읽기만 한다 — 걸리는 줄이 있으면 아무것도 안 바꾼다 ──
    for 자리, 줄 in enumerate(payload.rows, start=1):
        if not 줄.level1.strip() or not 줄.level2.strip():
            raise HTTPException(status_code=400, detail=f"{자리}번째 줄 — 구분과 항목은 비울 수 없습니다.")
        for 이름, 값 in (("단가", 줄.unit_price), ("명수", 줄.headcount),
                        ("횟수", 줄.times), ("예산금액", 줄.planned_amount)):
            if 값 is not None and 값 < 0:
                raise HTTPException(status_code=400, detail=f"{자리}번째 줄 — {이름}은 0보다 작을 수 없습니다.")
        if 줄.id is not None and 줄.id not in 있는것:
            raise HTTPException(status_code=400, detail="이 회차에 없는 예산 항목이 섞여 있습니다.")
    for cid in payload.removed:
        if cid not in 있는것:
            raise HTTPException(status_code=400, detail="이 회차에 없는 예산 항목을 취소하려 합니다.")
    # **같은 줄이 양쪽에 오면 거절한다** (2026-09-26 커밋 전 검토 [U]) — 화면은
    # 그런 몸을 안 만들지만, 서버가 그 모호함을 조용히 푸는 쪽(취소)으로 정하면
    # 나중에 다른 화면이 같은 몸을 보냈을 때 **고친 줄 알고 취소된다**
    겹침 = {줄.id for 줄 in payload.rows if 줄.id is not None} & set(payload.removed)
    if 겹침:
        raise HTTPException(status_code=400, detail="같은 예산 항목을 고치면서 동시에 취소할 수 없습니다.")

    센다 = {"고침": 0, "새로": 0, "취소": 0}
    취소: list[BudgetCategory] = []
    되살림: list[BudgetCategory] = []
    새줄: list[BudgetCategory] = []
    for 자리, 줄 in enumerate(payload.rows, start=1):
        cat = 있는것.get(줄.id) if 줄.id is not None else None
        새것 = cat is None
        if 새것:
            cat = BudgetCategory(retreat_id=retreat.id)
            db.add(cat)
        전 = _category_values(cat) if not 새것 else {}
        _apply_fields(
            cat,
            level1=줄.level1, level2=줄.level2, level3=줄.level3,
            unit_price="" if 줄.unit_price is None else str(줄.unit_price),
            headcount="" if 줄.headcount is None else str(줄.headcount),
            times="" if 줄.times is None else str(줄.times),
            planned_amount=줄.planned_amount,
        )
        cat.note = 줄.note.strip() or None
        cat.sort_order = 자리
        # 되살아난 줄 — 편집 표에 있다는 것은 「이 회차에서 쓴다」 는 뜻이다
        if cat.canceled_at is not None:
            cat.canceled_at = None
            되살림.append(cat)
        if 새것:
            센다["새로"] += 1
            새줄.append(cat)
        elif _바뀐칸만(전, _category_values(cat))[1]:
            센다["고침"] += 1

    for cid in payload.removed:
        cat = 있는것[cid]
        if cat.canceled_at is None:
            cat.canceled_at = dt.datetime.now()
            센다["취소"] += 1
            취소.append(cat)

    db.commit()
    # **줄마다도 남긴다** (2026-09-26 두 번째 검토 [4]) — 같은 일을 하는
    # `/categories/{id}/cancel` 과 `/categories` 가 줄마다 남기는데 묶음 저장만
    # 합계 한 줄이면 **같은 사실이 길에 따라 다르게 기록된다**(지출 쪽에서 고친
    # 그 자리와 같다). 0장이 기대는 자리라 더 그렇다
    for 이름, 것들 in (("예산항목_취소", 취소), ("예산항목_되살림", 되살림),
                      ("예산항목_생성", 새줄)):
        for cat in 것들:
            log_activity(db, retreat_id=retreat.id, actor=user, action=이름,
                         target_type="budget_category", target_id=cat.id,
                         summary=f"[{cat.display_name}] 표 저장에서")
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="예산표_저장",
        target_type="retreat",
        target_id=retreat.id,
        summary=f"고침 {센다['고침']} · 새로 {센다['새로']} · 취소 {센다['취소']}",
    )
    return {"ok": True, **센다}


@router.post("/categories")
def create_category(
    level1: str = Form(...),
    level2: str = Form(...),
    level3: str = Form(""),
    unit_price: str = Form(""),
    headcount: str = Form(""),
    times: str = Form(""),
    planned_amount: int = Form(0),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    max_order = (
        db.scalar(
            select(func.max(BudgetCategory.sort_order)).where(
                BudgetCategory.retreat_id == retreat.id
            )
        )
        or 0
    )
    category = BudgetCategory(retreat_id=retreat.id, sort_order=max_order + 1)
    _apply_fields(
        category,
        level1=level1, level2=level2, level3=level3,
        unit_price=unit_price, headcount=headcount, times=times,
        planned_amount=planned_amount,
    )
    db.add(category)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="예산항목_생성",
        target_type="budget_category",
        target_id=category.id,
        summary=f"{category.display_name} / {category.planned_amount:,}원",
    )
    return redirect(f"/budget?retreat_id={retreat.id}", message="예산 항목을 추가했습니다.")


@router.post("/categories/{category_id}/update")
def update_category(
    category_id: int,
    level1: str = Form(...),
    level2: str = Form(...),
    level3: str = Form(""),
    unit_price: str = Form(""),
    headcount: str = Form(""),
    times: str = Form(""),
    planned_amount: int = Form(0),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    category = db.get(BudgetCategory, category_id)
    if category is None or category.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="예산 항목을 찾을 수 없습니다.")
    # 취소된 항목은 못 고친다 (재정 차례 5) — 취소는 그 시점의 값을 지키는 것이고, 되살린 뒤에 고친다.
    # 화면은 취소된 행에 「수정」 을 안 그리지만 손으로 보낸 요청이 값을 바꾸던 자리다
    if category.canceled_at is not None:
        raise HTTPException(status_code=409, detail="취소된 예산 항목입니다. 되살린 뒤에 고치세요.")

    before = _category_values(category)
    _apply_fields(
        category,
        level1=level1, level2=level2, level3=level3,
        unit_price=unit_price, headcount=headcount, times=times,
        planned_amount=planned_amount,
    )
    전, 후 = _바뀐칸만(before, _category_values(category))
    if not 후:
        db.rollback()
        return redirect(f"/budget?retreat_id={retreat.id}", message="바뀐 것이 없습니다.")
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="예산항목_수정",
        target_type="budget_category",
        target_id=category.id,
        summary=category.display_name,
        before_value=전,
        after_value=후,
    )
    return redirect(f"/budget?retreat_id={retreat.id}", message="예산 항목을 수정했습니다.")


def _category_values(category: BudgetCategory) -> dict:
    """취소·되살림 기록에 남길 그때의 값 — 되살리면 이것이 돌아온다 (7-3)."""
    return {
        "name": category.display_name,
        "planned_amount": category.planned_amount,
        "unit_price": category.unit_price,
        "headcount": category.headcount,
        "times": category.times,
    }


@router.post("/categories/{category_id}/cancel")
def toggle_category_canceled(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    """예산 항목은 지우지 않는다 (0장) — 지출과 같은 취소 표시를 토글한다 (7-3).

    전에는 행을 지웠고, 걸린 지출이 한 건이라도 있으면 「먼저 지출을 옮겨주세요」 로
    막았다. **그 가드는 걷었다**(2026-09-14 · 사람이 정한 나-ㄴ) — 취소된 지출까지
    세어 막아서 「취소된 지출만 걸린 항목」 이 영영 못 내려갔고, 이제는 행을 안
    지우므로 걸린 지출이 갈 곳을 잃을 일도 없다. 걸린 지출은 그 항목에 남고, 그
    집행은 summary 의 canceled_category_spent 로 합계에 계속 든다.
    """
    category = db.get(BudgetCategory, category_id)
    if category is None or category.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="예산 항목을 찾을 수 없습니다.")

    values = _category_values(category)
    if category.canceled_at is None:
        category.canceled_at = dt.datetime.now()
        action, message = "예산항목_취소", "예산 항목을 취소했습니다. 행은 아래에 흐리게 남고 합계에서 빠집니다."
    else:
        category.canceled_at = None
        action, message = "예산항목_되살림", "예산 항목을 되살렸습니다."
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action=action,
        target_type="budget_category",
        target_id=category_id,
        summary=f"{values['name']} / {values['planned_amount']:,}원",
        before_value=values,
        after_value=values,
    )
    return redirect(f"/budget?retreat_id={retreat.id}", message=message)


# ── 수입 (7-3) — 예산 페이지의 섹션이다. 집행률 분모에는 안 들어간다 ────


@router.post("/incomes")
def create_income(
    name: str = Form(...),
    unit_price: str = Form(""),
    headcount: str = Form(""),
    amount: int = Form(0),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    if not name.strip():
        raise HTTPException(status_code=400, detail="수입 이름을 적어주세요.")
    max_order = (
        db.scalar(
            select(func.max(IncomeItem.sort_order)).where(IncomeItem.retreat_id == retreat.id)
        )
        or 0
    )
    unit = _int_or_none(unit_price)
    head = _int_or_none(headcount)
    income = IncomeItem(
        retreat_id=retreat.id,
        name=name.strip(),
        unit_price=unit,
        headcount=head,
        # 단가 × 명수가 있으면 그것이 금액이다 — 식은 domain 에 (7-3)
        amount=max(0, income_amount_of(unit, head, amount)),
        note=note.strip() or None,
        sort_order=max_order + 1,
    )
    db.add(income)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="수입_생성",
        target_type="income",
        target_id=income.id,
        summary=f"{income.name} / {income.amount:,}원",
    )
    return redirect(f"/budget?retreat_id={retreat.id}", message="수입을 추가했습니다.")


@router.post("/incomes/{income_id}/update")
def update_income(
    income_id: int,
    name: str = Form(...),
    unit_price: str = Form(""),
    headcount: str = Form(""),
    amount: int = Form(0),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    """수입을 고친다 (7-3 · 재정 차례 5) — 예산 항목 고치기와 같은 모양이다.

    총무팀만 · 취소된 수입은 409 · 금액 식은 등록과 같은 domain 함수 · 활동 기록에 전후 값.
    """
    income = db.get(IncomeItem, income_id)
    if income is None or income.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="수입 항목을 찾을 수 없습니다.")
    if income.canceled_at is not None:
        raise HTTPException(status_code=409, detail="취소된 수입입니다. 되살린 뒤에 고치세요.")
    if not name.strip():
        raise HTTPException(status_code=400, detail="수입 이름을 적어주세요.")
    값 = lambda i: {"name": i.name, "amount": i.amount, "unit_price": i.unit_price,  # noqa: E731
                   "headcount": i.headcount, "note": i.note}
    before = 값(income)
    income.name = name.strip()
    income.unit_price = _int_or_none(unit_price)
    income.headcount = _int_or_none(headcount)
    income.amount = max(0, income_amount_of(income.unit_price, income.headcount, amount))
    income.note = note.strip() or None
    전, 후 = _바뀐칸만(before, 값(income))
    if not 후:
        db.rollback()
        return redirect(f"/budget?retreat_id={retreat.id}", message="바뀐 것이 없습니다.")
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="수입_수정",
        target_type="income",
        target_id=income.id,
        summary=f"{income.name} / {income.amount:,}원",
        before_value=전,
        after_value=후,
    )
    return redirect(f"/budget?retreat_id={retreat.id}", message="수입을 고쳤습니다.")


@router.post("/incomes/{income_id}/cancel")
def toggle_income_canceled(
    income_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    """수입은 지우지 않는다 (0장) — 지출과 같은 취소 표시를 토글한다 (7-3)."""
    income = db.get(IncomeItem, income_id)
    if income is None or income.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="수입 항목을 찾을 수 없습니다.")
    values = {
        "name": income.name, "amount": income.amount, "unit_price": income.unit_price,
        "headcount": income.headcount, "note": income.note,
    }
    if income.canceled_at is None:
        income.canceled_at = dt.datetime.now()
        action, message = "수입_취소", "수입을 취소했습니다. 행은 흐리게 남고 합계에서 빠집니다."
    else:
        income.canceled_at = None
        action, message = "수입_되살림", "수입을 되살렸습니다."
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action=action,
        target_type="income",
        target_id=income_id,
        summary=f"{income.name} / {income.amount:,}원",
        before_value=values,
        after_value=values,
    )
    return redirect(f"/budget?retreat_id={retreat.id}", message=message)
