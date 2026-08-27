"""지출 등록 / 식대 정산 / 환급 대상자 관리."""

from __future__ import annotations

import datetime as dt
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import ALLOWED_UPLOAD_EXTS, MAX_UPLOAD_BYTES, UPLOAD_DIR
from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.domain.meal import calculate_meal_settlement
from app.models import (
    BudgetCategory,
    Department,
    ExpenseEntry,
    Retreat,
    User,
)
from app.security import assert_can_edit_department, get_current_user, require_editor
from app.templating import redirect, render

router = APIRouter()


def _parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    return dt.date.fromisoformat(raw)


def parse_attendees(raw: str) -> list[str]:
    """비고에 텍스트로 적던 명단을 배열로 분리한다.

    쉼표·줄바꿈·공백 어느 것으로 구분해도 받아준다.
    """
    if not raw:
        return []
    return [name for name in re.split(r"[,\n\r\t ]+", raw.strip()) if name]


def _save_receipt(file: UploadFile | None) -> str | None:
    if file is None or not file.filename:
        return None
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"허용되지 않는 파일 형식입니다: {ext} (이미지 또는 PDF만 가능)",
        )
    data = file.file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="영수증 파일은 10MB 이하만 업로드할 수 있습니다.")
    name = f"{secrets.token_hex(12)}{ext}"
    (UPLOAD_DIR / name).write_bytes(data)
    return f"/uploads/{name}"


def _next_receipt_number(db: Session, retreat: Retreat) -> int:
    current = db.scalar(
        select(func.max(ExpenseEntry.receipt_number)).where(
            ExpenseEntry.retreat_id == retreat.id
        )
    )
    return (current or 0) + 1


def _departments(db: Session, retreat: Retreat) -> list[Department]:
    return list(
        db.scalars(
            select(Department)
            .where(Department.retreat_id == retreat.id)
            .order_by(Department.sort_order, Department.id)
        )
    )


def _categories(db: Session, retreat: Retreat) -> list[BudgetCategory]:
    return list(
        db.scalars(
            select(BudgetCategory)
            .where(BudgetCategory.retreat_id == retreat.id)
            .order_by(BudgetCategory.sort_order, BudgetCategory.id)
        )
    )


def _last_meal_defaults(db: Session, retreat: Retreat, user: User) -> dict:
    """'모임 식사비-1, -2, -3...' 반복 입력을 줄이기 위한 직전 입력값 제안."""
    query = select(ExpenseEntry).where(
        ExpenseEntry.retreat_id == retreat.id, ExpenseEntry.is_meal_expense
    )
    if user.department_id:
        query = query.where(ExpenseEntry.department_id == user.department_id)
    last = db.scalars(query.order_by(ExpenseEntry.id.desc())).first()
    if last is None:
        return {
            "department_id": user.department_id,
            "payer_name": user.name,
            "payer_account": user.bank_account or "",
            "attendees": "",
            "level3b": "",
        }
    return {
        "department_id": last.department_id,
        "payer_name": last.payer_name or user.name,
        "payer_account": last.payer_account or user.bank_account or "",
        "attendees": " ".join(last.meal_attendee_names or []),
        "level3b": _next_meal_label(last.level3b),
    }


def _next_meal_label(previous: str | None) -> str:
    """'모임 식사비-2' → '모임 식사비-3'."""
    if not previous:
        return "모임 식사비-1"
    match = re.match(r"^(.*?)-(\d+)$", previous)
    if match:
        return f"{match.group(1)}-{int(match.group(2)) + 1}"
    return f"{previous}-2"


@router.get("/expenses")
def expense_list(
    request: Request,
    meal_only: int = 0,
    unpaid_only: int = 0,
    department_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    query = select(ExpenseEntry).where(ExpenseEntry.retreat_id == retreat.id)
    if meal_only:
        query = query.where(ExpenseEntry.is_meal_expense)
    if unpaid_only:
        query = query.where(ExpenseEntry.paid.is_(False))
    if department_id:
        query = query.where(ExpenseEntry.department_id == department_id)

    entries = list(db.scalars(query.order_by(ExpenseEntry.id.desc())))

    return render(
        request,
        "expenses.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "entries": entries,
            "departments": _departments(db, retreat),
            "categories": _categories(db, retreat),
            "meal_defaults": _last_meal_defaults(db, retreat, user),
            "next_receipt_number": _next_receipt_number(db, retreat),
            "today": dt.date.today().isoformat(),
            "filters": {
                "meal_only": meal_only,
                "unpaid_only": unpaid_only,
                "department_id": department_id,
            },
            "totals": {
                "amount": sum(e.amount for e in entries),
                "subsidy": sum(e.subsidy_amount for e in entries if e.is_meal_expense),
                "burden": sum(
                    e.personal_burden_amount for e in entries if e.is_meal_expense
                ),
                "settlement": sum(e.settlement_amount for e in entries),
            },
        },
    )


@router.post("/expenses/create")
def create_expense(
    budget_category_id: str = Form(""),
    expense_date: str = Form(""),
    amount: int = Form(0),
    department_id: str = Form(""),
    payer_name: str = Form(""),
    payer_account: str = Form(""),
    note: str = Form(""),
    paid: str = Form(""),
    paid_date: str = Form(""),
    is_meal_expense: str = Form(""),
    meal_headcount: str = Form(""),
    meal_attendees: str = Form(""),
    level3b: str = Form(""),
    receipt: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    dept_id = int(department_id) if department_id else None
    assert_can_edit_department(user, dept_id)

    if amount < 0:
        raise HTTPException(status_code=400, detail="금액은 0원 이상이어야 합니다.")

    category = None
    if budget_category_id:
        category = db.get(BudgetCategory, int(budget_category_id))
        if category is None or category.retreat_id != retreat.id:
            raise HTTPException(status_code=404, detail="예산 항목을 찾을 수 없습니다.")

    is_meal = bool(is_meal_expense)
    headcount = int(meal_headcount) if (is_meal and meal_headcount) else None
    attendees = parse_attendees(meal_attendees) if is_meal else None

    if is_meal:
        settlement = calculate_meal_settlement(
            amount=amount,
            headcount=headcount or 0,
            per_person_cap=retreat.meal_subsidy_per_person,
        )
        subsidy = settlement.subsidy_amount
        burden = settlement.personal_burden_amount
    else:
        subsidy, burden = amount, 0

    entry = ExpenseEntry(
        retreat_id=retreat.id,
        budget_category_id=category.id if category else None,
        level1=category.level1 if category else None,
        level2=category.level2 if category else None,
        level3a=category.level3 if category else None,
        level3b=level3b.strip() or None,
        receipt_number=_next_receipt_number(db, retreat),
        expense_date=_parse_date(expense_date) or dt.date.today(),
        amount=amount,
        department_id=dept_id,
        payer_name=payer_name.strip() or None,
        payer_account=payer_account.strip() or None,
        paid=bool(paid),
        paid_date=_parse_date(paid_date),
        note=note.strip() or None,
        receipt_file_url=_save_receipt(receipt),
        is_meal_expense=is_meal,
        meal_headcount=headcount,
        meal_attendee_names=attendees,
        subsidy_amount=subsidy,
        personal_burden_amount=burden,
        created_by_id=user.id,
    )
    db.add(entry)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="지출_등록",
        target_type="expense",
        target_id=entry.id,
        summary=f"[{entry.receipt_number}] {amount:,}원"
        + (f" / 식대 {headcount}명 → 지원 {subsidy:,}원" if is_meal else ""),
    )
    message = "지출을 등록했습니다."
    if is_meal:
        message = f"식대 등록 완료 — 지원금액 {subsidy:,}원 / 개인부담 {burden:,}원"
    return redirect(f"/expenses?retreat_id={retreat.id}", message=message)


@router.post("/expenses/{entry_id}/paid")
def toggle_paid(
    entry_id: int,
    redirect_to: str = Form("/expenses"),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    entry = db.get(ExpenseEntry, entry_id)
    if entry is None or entry.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="지출 내역을 찾을 수 없습니다.")
    assert_can_edit_department(user, entry.department_id)

    entry.paid = not entry.paid
    entry.paid_date = dt.date.today() if entry.paid else None
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="지급여부_변경",
        target_type="expense",
        target_id=entry.id,
        summary=f"[{entry.receipt_number}] {'지급완료' if entry.paid else '미지급'}",
    )
    sep = "&" if "?" in redirect_to else "?"
    return redirect(
        f"{redirect_to}{sep}retreat_id={retreat.id}",
        message="지급 여부를 변경했습니다.",
    )


@router.post("/expenses/{entry_id}/delete")
def delete_expense(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    entry = db.get(ExpenseEntry, entry_id)
    if entry is None or entry.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="지출 내역을 찾을 수 없습니다.")
    assert_can_edit_department(user, entry.department_id)

    receipt_number = entry.receipt_number
    db.delete(entry)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="지출_삭제",
        target_type="expense",
        target_id=entry_id,
        summary=f"[{receipt_number}] 삭제",
    )
    return redirect(f"/expenses?retreat_id={retreat.id}", message="지출을 삭제했습니다.")


@router.get("/refunds")
def refund_list(
    request: Request,
    unpaid_only: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """환급 대상자 리스트 — 결제자에게 얼마를 돌려줘야 하는지."""
    query = select(ExpenseEntry).where(
        ExpenseEntry.retreat_id == retreat.id,
        ExpenseEntry.subsidy_amount > 0,
    )
    if unpaid_only:
        query = query.where(ExpenseEntry.paid.is_(False))

    entries = list(db.scalars(query.order_by(ExpenseEntry.id.desc())))

    by_payer: dict[str, dict] = {}
    for entry in entries:
        key = f"{entry.payer_name or '(미지정)'}|{entry.payer_account or ''}"
        row = by_payer.setdefault(
            key,
            {
                "payer_name": entry.payer_name or "(미지정)",
                "payer_account": entry.payer_account or "",
                "total": 0,
                "entries": [],
            },
        )
        row["total"] += entry.subsidy_amount
        row["entries"].append(entry)

    return render(
        request,
        "refunds.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "groups": sorted(by_payer.values(), key=lambda r: -r["total"]),
            "unpaid_only": unpaid_only,
            "grand_total": sum(r["total"] for r in by_payer.values()),
        },
    )


@router.get("/uploads/{filename}")
def get_upload(filename: str, user: User = Depends(get_current_user)):
    """업로드된 영수증은 로그인한 사용자만 볼 수 있다."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다.")
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(path)
