"""지출 (CLAUDE.md 7-4) — 예산 라인별 그룹 · 식대 정산 · 영수증 N개 · 환급 필터.

그룹 헤더의 예산/집행/잔액은 domain.budget 의 summary 에서 온다 — 예산
페이지와 같은 값이다. 「환급 대상자」 는 별도 페이지가 아니라 이 목록의
필터(?filter=refund)다. 옛 /refunds 는 301 로 잇는다.
"""

from __future__ import annotations

import datetime as dt
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ALLOWED_UPLOAD_EXTS, MAX_UPLOAD_BYTES, UPLOAD_DIR
from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.domain.budget import (
    build_budget_summary,
    entries_of,
    is_refund_target,
    next_receipt_number,
)
from app.domain.meal import calculate_meal_settlement
from app.models import (
    BudgetCategory,
    Department,
    ExpenseEntry,
    ExpenseReceipt,
    Retreat,
    User,
)
from app.security import assert_can_edit_department, get_current_user, require_editor
from app.templating import redirect, render

router = APIRouter()

# 칩과 홈 결산이 같은 정의를 쓴다 (4-15) — 홈의 N = 그 필터 화면의 행 수
FILTERS = ("all", "meal", "unpaid", "refund", "noreceipt")


def _parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    return dt.date.fromisoformat(raw)


def parse_attendees(raw: str) -> list[str]:
    """비고에 텍스트로 적던 명단을 배열로 분리한다 (7-2).

    쉼표·줄바꿈·공백 어느 것으로 구분해도 받아준다.
    """
    if not raw:
        return []
    return [name for name in re.split(r"[,\n\r\t ]+", raw.strip()) if name]


def _save_receipt_file(file: UploadFile | None) -> tuple[str, str] | None:
    """영수증 파일을 임의 이름으로 저장한다 → (디스크 이름, 올린 이름)."""
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
    return name, file.filename


def _add_receipt(
    db: Session,
    retreat: Retreat,
    entry: ExpenseEntry,
    *,
    file: UploadFile | None,
    memo: str,
) -> ExpenseReceipt | None:
    """영수증 하나를 붙인다 — 파일이든 「결산 파일에 별첨」 같은 메모든 (7-4)."""
    saved = _save_receipt_file(file)
    memo = memo.strip()
    if saved is None and not memo:
        return None
    receipt = ExpenseReceipt(
        expense_id=entry.id,
        number=next_receipt_number(db, retreat),
        stored_name=saved[0] if saved else None,
        original_name=saved[1] if saved else None,
        memo=memo or None,
    )
    db.add(receipt)
    return receipt


def _departments(db: Session, retreat: Retreat) -> list[Department]:
    return list(
        db.scalars(
            select(Department)
            .where(Department.retreat_id == retreat.id)
            .order_by(Department.sort_order, Department.id)
        )
    )


def _my_department_id(db: Session, retreat: Retreat, user: User) -> int | None:
    """이 회차에서의 내 부서 행 — **키로 찾는다** (2장). 소속 행이 다른 회차
    것이어도 이번 회차의 같은 키 부서를 돌려준다. 없으면(키 없는 부서 등)
    원래 행으로 물러선다."""
    from app.domain.departments import department_key_of

    my_key = department_key_of(db, user)
    if my_key:
        mine = db.scalar(
            select(Department.id).where(
                Department.retreat_id == retreat.id, Department.key == my_key
            )
        )
        if mine is not None:
            return mine
    return user.department_id


def _last_meal_defaults(db: Session, retreat: Retreat, user: User) -> dict:
    """'모임 식사비-1, -2, -3...' 반복 입력을 줄이기 위한 직전 입력값 제안 (7-2)."""
    my_dept = _my_department_id(db, retreat, user)
    # 취소된 행은 제안하지 않는다 (7-4) — 잘못 넣어 취소한 「모임 식사비-N」
    # 이름이 다시 제안되면 같은 실수를 한 번 더 부른다
    query = select(ExpenseEntry).where(
        ExpenseEntry.retreat_id == retreat.id, ExpenseEntry.is_meal_expense,
        ExpenseEntry.canceled_at.is_(None),
    )
    if my_dept:
        query = query.where(ExpenseEntry.department_id == my_dept)
    last = db.scalars(query.order_by(ExpenseEntry.id.desc())).first()
    if last is None:
        return {
            "department_id": my_dept,
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
    filter: str = "all",
    meal_only: int = 0,
    unpaid_only: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    # 옛 쿼리 이름도 받는다 — 즐겨찾기가 조용히 전체 목록으로 떨어지면 안 된다
    if filter not in FILTERS:
        filter = "all"
    if meal_only:
        filter = "meal"
    if unpaid_only:
        filter = "unpaid"

    entries = entries_of(db, retreat)
    # 취소된 행은 「전체」 에만 흐리게 남는다 (7-4) — 나머지 필터는 챙길 일의
    # 목록이라, 안 쓴 돈이 끼면 홈의 숫자와도 갈린다
    if filter == "meal":
        entries = [e for e in entries if e.is_meal_expense and e.canceled_at is None]
    elif filter == "unpaid":
        entries = [e for e in entries if not e.paid and e.canceled_at is None]
    elif filter == "refund":
        # 홈 결산의 「미지급 환급 N건」 과 같은 정의 — budget.refund_entries (4-15)
        entries = [e for e in entries
                   if is_refund_target(e) and not e.paid and e.canceled_at is None]
    elif filter == "noreceipt":
        entries = [e for e in entries if not e.receipts and e.canceled_at is None]

    # 취소된 행은 합계에 넣지 않는다 (7-4) — 「전체」 에서 행은 보여도
    # 숫자는 실제로 쓴 돈이어야 한다
    live = [e for e in entries if e.canceled_at is None]
    totals = {
        "amount": sum(e.amount for e in live),
        "subsidy": sum(e.subsidy_amount for e in live if e.is_meal_expense),
        "burden": sum(e.personal_burden_amount for e in live if e.is_meal_expense),
        "settlement": sum(e.settlement_amount for e in live),
    }

    # 예산 라인별 그룹 — 헤더의 예산/집행/잔액은 summary 의 그 항목 값이다 (7-4)
    summary = build_budget_summary(db, retreat=retreat)
    row_by_category = {row.category.id: row for row in summary.categories}
    groups: list[dict] = []
    seen: dict[int | None, dict] = {}
    for e in entries:
        key = e.budget_category_id
        group = seen.get(key)
        if group is None:
            group = seen[key] = {
                "row": row_by_category.get(key),  # None 이면 예산 항목 미지정
                "entries": [],
            }
            groups.append(group)
        group["entries"].append(e)

    return render(
        request,
        "expenses.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "summary": summary,
            "groups": groups,
            "entry_count": len(entries),
            "departments": _departments(db, retreat),
            "meal_defaults": _last_meal_defaults(db, retreat, user),
            "next_receipt_number": next_receipt_number(db, retreat),
            "today": dt.date.today().isoformat(),
            "filter": filter,
            "totals": totals,
            "active_tab": "expenses",
            "page_subtitle": "지출",
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
    receipt_memo: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    dept_id = int(department_id) if department_id else None
    # 부서는 **이 지출의 회차** 행이어야 한다 (2장) — 키 비교 도입으로 「내
    # 키의 아무 회차 부서 행」 이 권한을 통과하므로, 다른 회차의 행 id 가
    # 붙으면 목록·집계가 그 부서를 못 찾는다. 걸러서 진행하지 않고 거절한다
    if dept_id is not None:
        dept = db.get(Department, dept_id)
        if dept is None or dept.retreat_id != retreat.id:
            raise HTTPException(status_code=400, detail="이 회차의 부서가 아닙니다.")
    assert_can_edit_department(db, user, dept_id)

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
        expense_date=_parse_date(expense_date) or dt.date.today(),
        amount=amount,
        department_id=dept_id,
        payer_name=payer_name.strip() or None,
        payer_account=payer_account.strip() or None,
        paid=bool(paid),
        paid_date=_parse_date(paid_date),
        note=note.strip() or None,
        is_meal_expense=is_meal,
        meal_headcount=headcount,
        meal_attendee_names=attendees,
        subsidy_amount=subsidy,
        personal_burden_amount=burden,
        created_by_id=user.id,
    )
    db.add(entry)
    db.flush()
    added = _add_receipt(db, retreat, entry, file=receipt, memo=receipt_memo)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="지출_등록",
        target_type="expense",
        target_id=entry.id,
        summary=(f"[{added.number}] " if added else "")
        + f"{amount:,}원"
        + (f" / 식대 {headcount}명 → 지원 {subsidy:,}원" if is_meal else ""),
    )
    message = "지출을 등록했습니다."
    if is_meal:
        message = f"식대 등록 완료 — 지원금액 {subsidy:,}원 / 개인부담 {burden:,}원"
    return redirect(f"/expenses?retreat_id={retreat.id}", message=message)


@router.post("/expenses/{entry_id}/receipts")
def add_receipt(
    entry_id: int,
    receipt: UploadFile | None = File(None),
    memo: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    """영수증을 하나 더 붙인다 — 지출 1건에 N개 (7-4)."""
    entry = db.get(ExpenseEntry, entry_id)
    if entry is None or entry.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="지출 내역을 찾을 수 없습니다.")
    assert_can_edit_department(db, user, entry.department_id)

    added = _add_receipt(db, retreat, entry, file=receipt, memo=memo)
    if added is None:
        raise HTTPException(status_code=400, detail="파일이나 메모 중 하나는 있어야 합니다.")
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="영수증_추가",
        target_type="expense",
        target_id=entry.id,
        summary=f"[{added.number}] " + (added.original_name or added.memo or ""),
    )
    return redirect(f"/expenses?retreat_id={retreat.id}", message=f"영수증 {added.number}번을 붙였습니다.")


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
    assert_can_edit_department(db, user, entry.department_id)

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
        summary=f"[지출 {entry.id}] {'지급완료' if entry.paid else '미지급'}",
    )
    sep = "&" if "?" in redirect_to else "?"
    return redirect(
        f"{redirect_to}{sep}retreat_id={retreat.id}",
        message="지급 여부를 변경했습니다.",
    )


@router.post("/expenses/{entry_id}/cancel")
def toggle_canceled(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    """지출은 지우지 않는다 (0장) — 취소 표시를 토글한다.

    옛 「삭제」 단추가 행을 실제로 지웠는데, 4-9 에서 업무의 삭제 단추를 막은
    원칙과 정면으로 부딪힌다. 취소된 행은 흐리게 남고 합계·집행률·영수증
    총액에서 빠지며(7-4), 잘못 눌렀으면 같은 단추로 되살린다.
    """
    entry = db.get(ExpenseEntry, entry_id)
    if entry is None or entry.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="지출 내역을 찾을 수 없습니다.")
    assert_can_edit_department(db, user, entry.department_id)

    if entry.canceled_at is None:
        entry.canceled_at = dt.datetime.now()
        action, message = "지출_취소", "지출을 취소했습니다. 행은 흐리게 남고 합계에서 빠집니다."
    else:
        entry.canceled_at = None
        action, message = "지출_되살림", "지출을 되살렸습니다."
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action=action,
        target_type="expense",
        target_id=entry_id,
        summary=f"[지출 {entry_id}] {action.split('_')[1]}",
    )
    return redirect(f"/expenses?retreat_id={retreat.id}", message=message)


@router.get("/refunds")
def old_refund_list(request: Request):
    """옛 환급 대상자 페이지 — 지출 목록의 필터가 그 자리다 (7-4).

    쿼리를 버리지 않는다 — 옛 즐겨찾기 `/refunds?retreat_id=N` 이
    현재 회차로 조용히 떨어지면 다른 회차를 보게 된다.
    """
    query = str(request.url.query)
    target = "/expenses?filter=refund" + (f"&{query}" if query else "")
    return RedirectResponse(target, status_code=301)


@router.get("/uploads/{filename}")
def get_upload(filename: str, user: User = Depends(get_current_user)):
    """업로드된 영수증은 로그인한 사용자만 볼 수 있다."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다.")
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(path)
