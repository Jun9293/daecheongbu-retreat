"""예산 카테고리 관리 및 예산 대비 지출 현황."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.domain.budget import build_budget_summary
from app.models import BudgetCategory, ExpenseEntry, Retreat, User
from app.security import get_current_user, require_admin
from app.templating import redirect, render

router = APIRouter(prefix="/budget")


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
        },
    )


@router.post("/categories")
def create_category(
    level1: str = Form(...),
    level2: str = Form(...),
    level3: str = Form(""),
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
    category = BudgetCategory(
        retreat_id=retreat.id,
        level1=level1.strip(),
        level2=level2.strip(),
        level3=level3.strip() or None,
        planned_amount=max(0, planned_amount),
        sort_order=max_order + 1,
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
    category.level1 = level1.strip()
    category.level2 = level2.strip()
    category.level3 = level3.strip() or None
    category.planned_amount = max(0, planned_amount)
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
