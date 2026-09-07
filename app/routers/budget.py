"""예산 (CLAUDE.md 7-3) — 구분 › 항목 › 세부항목 · 소계 · 수입 · 잔액.

숫자는 전부 domain.budget 의 summary 에서 온다 — 여기서 세지 않는다.
예산금액 = 단가 × 명수 × 횟수, 셋이 비면 직접 입력값. 넷 다 저장한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.domain.budget import build_budget_summary, planned_amount_of
from app.models import BudgetCategory, ExpenseEntry, IncomeItem, Retreat, User
from app.security import get_current_user, require_admin
from app.templating import redirect, render

router = APIRouter(prefix="/budget")


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

    before = {
        "name": category.display_name,
        "planned_amount": category.planned_amount,
    }
    _apply_fields(
        category,
        level1=level1, level2=level2, level3=level3,
        unit_price=unit_price, headcount=headcount, times=times,
        planned_amount=planned_amount,
    )
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="예산항목_수정",
        target_type="budget_category",
        target_id=category.id,
        summary=category.display_name,
        before_value=before,
        after_value={
            "name": category.display_name,
            "planned_amount": category.planned_amount,
        },
    )
    return redirect(f"/budget?retreat_id={retreat.id}", message="예산 항목을 수정했습니다.")


@router.post("/categories/{category_id}/delete")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    category = db.get(BudgetCategory, category_id)
    if category is None or category.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="예산 항목을 찾을 수 없습니다.")

    linked = db.scalar(
        select(func.count())
        .select_from(ExpenseEntry)
        .where(ExpenseEntry.budget_category_id == category_id)
    )
    if linked:
        return redirect(
            f"/budget?retreat_id={retreat.id}",
            message=f"지출 {linked}건이 연결되어 있어 삭제할 수 없습니다. 먼저 지출을 옮겨주세요.",
        )

    name = category.display_name
    db.delete(category)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="예산항목_삭제",
        target_type="budget_category",
        target_id=category_id,
        summary=name,
    )
    return redirect(f"/budget?retreat_id={retreat.id}", message="예산 항목을 삭제했습니다.")


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
    # 단가 × 명수가 있으면 그것이 금액이다 — 근거 없는 숫자를 남기지 않는다
    value = unit * head if (unit is not None and head is not None) else amount
    income = IncomeItem(
        retreat_id=retreat.id,
        name=name.strip(),
        unit_price=unit,
        headcount=head,
        amount=max(0, value),
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


@router.post("/incomes/{income_id}/delete")
def delete_income(
    income_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    income = db.get(IncomeItem, income_id)
    if income is None or income.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="수입 항목을 찾을 수 없습니다.")
    name = income.name
    db.delete(income)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="수입_삭제",
        target_type="income",
        target_id=income_id,
        summary=name,
    )
    return redirect(f"/budget?retreat_id={retreat.id}", message="수입을 삭제했습니다.")
