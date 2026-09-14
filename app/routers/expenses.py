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
    FILTERS,
    build_budget_summary,
    entries_of,
    filter_entries,
    list_totals,
    next_receipt_number,
    receipt_has_links,
    unlinked_receipt_count,
)
from app.domain import permissions as perm
from app.domain.meal import calculate_meal_settlement
from app.models import (
    _now,
    BudgetCategory,
    Department,
    ExpenseEntry,
    ExpenseReceipt,
    Retreat,
    User,
)
from app.security import assert_can_edit_department, get_current_user, require_editor
from app.templating import redirect, render
from app.domain.departments import departments_of

router = APIRouter()


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
    original_no: str = "",
) -> ExpenseReceipt | None:
    """새 영수증 한 장을 만들어 잇는다 — 파일이든 「결산 파일에 별첨」 같은 메모든 (7-4).
    이미 있는 영수증에 잇는 것은 `link_receipt` 다 — 그때는 새 번호를 안 준다."""
    saved = _save_receipt_file(file)
    memo = memo.strip()
    if saved is None and not memo:
        return None
    receipt = ExpenseReceipt(
        number=next_receipt_number(db, retreat),
        original_no=original_no.strip() or None,
        stored_name=saved[0] if saved else None,
        original_name=saved[1] if saved else None,
        memo=memo or None,
    )
    entry.attach_receipt(receipt)
    return receipt


def _departments(db: Session, retreat: Retreat) -> list[Department]:
    return departments_of(db, retreat.id)


def _my_department_id(db: Session, retreat: Retreat, user: User) -> int | None:
    """이 회차에서의 내 부서 행 — **키로 찾는다** (2장). 소속 행이 다른 회차
    것이어도 이번 회차의 같은 키 부서를 돌려준다. 없으면(키 없는 부서 등)
    원래 행으로 물러선다."""
    # 소속이 여럿이면 **리더인 부서 중 첫째**, 아니면 첫 소속 (도막 4 · ③과 같은 규칙).
    # 폼의 부서 칸은 하나를 고르는 자리라 기본값도 하나여야 한다
    keys = sorted(perm.lead_keys(user)) or sorted(perm.my_dept_keys(user))
    for my_key in keys:
        mine = db.scalar(
            select(Department.id).where(
                Department.retreat_id == retreat.id, Department.key == my_key
            )
        )
        if mine is not None:
            return mine
    return None


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
            **_my_account(user),
            "attendees": "",
            "level3b": "",
        }
    # **남의 계좌를 미리 채워 주지 않는다.** 직전 지출의 값을 그대로
    # 넣으면, 그 지출을 낸 사람의 계좌가 다음 사람의 입력칸에 뜬다 —
    # 목록에서 계좌를 가려 놓고 폼으로 새면 가린 뜻이 없다.
    # 총무팀은 원래 다 보는 자리라 그대로 두고(직전 값이 편하다),
    # 나머지는 **자기 것만** 채운다.
    #
    # **이름과 계좌는 함께 떨어집니다.** 계좌만 자기 것으로 바꾸면
    # (남의 이름, 내 계좌) 가 뜨는데, 환급은 `payer_name` 으로 사람을
    # 가르고 돈은 계좌 셋으로 갑니다 — 두 칸이 서로를 부정하는데
    # 화면에는 아무 표시도 나지 않습니다.
    # **계좌를 보일지는 `permissions.can_see_account` 하나가 정합니다** —
    # 화면·엑셀·이 폼이 같이 부릅니다. 여기만 다른 함수를 부르면 그 함수가
    # 바뀔 때 이 자리만 따로 움직입니다
    남이낸것 = perm.can_see_account(user)
    # 계좌 셋은 **한 벌로** 고른다 — 칸마다 따로 물러서면 (남의 은행, 내 번호) 가 섞인다
    직전 = {"payer_bank": last.payer_bank, "payer_account_number": last.payer_account_number,
            "payer_account_holder": last.payer_account_holder}
    return {
        "department_id": last.department_id,
        "payer_name": (last.payer_name if 남이낸것 else None) or user.name,
        **({k: v or "" for k, v in 직전.items()}
           if 남이낸것 and any(직전.values()) else _my_account(user)),
        "attendees": " ".join(last.meal_attendee_names or []),
        "level3b": _next_meal_label(last.level3b),
    }


def _my_account(user: User) -> dict:
    """등록 폼에 미리 채울 내 계좌 셋 — 설정 › 내 정보에서 적은 것."""
    return {"payer_bank": user.bank_name or "",
            "payer_account_number": user.account_number or "",
            "payer_account_holder": user.account_holder or ""}


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

    # 필터 조건도 합도 domain.budget 에서 — 홈 결산의 N 과 같은 정의다 (4-15)
    entries = filter_entries(entries_of(db, retreat), filter)
    totals = list_totals(entries)

    # 예산 라인별 그룹 — 헤더의 예산/집행/잔액은 summary 의 그 항목 값이다 (7-4).
    # 취소된 예산 항목에 걸린 지출도 그 항목 아래에 남는다(머리가 「취소된 항목」 을 말함)
    summary = build_budget_summary(db, retreat=retreat)
    row_by_category = {row.category.id: row
                       for row in summary.categories + summary.canceled_categories}
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
            "unlinked_receipts": unlinked_receipt_count(db, retreat),
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
    payer_bank: str = Form(""),
    payer_account_number: str = Form(""),
    payer_account_holder: str = Form(""),
    note: str = Form(""),
    paid: str = Form(""),
    paid_date: str = Form(""),
    is_meal_expense: str = Form(""),
    meal_headcount: str = Form(""),
    meal_attendees: str = Form(""),
    level3b: str = Form(""),
    receipt: UploadFile | None = File(None),
    receipt_memo: str = Form(""),
    receipt_original_no: str = Form(""),
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
        # 취소된 항목은 선택지에 없다 — 옛 화면이나 손으로 보낸 요청이 거기 새 지출을
        # 붙이면 합계에서 「취소된 항목에 걸린 지출」 로만 보여 알아채기 어렵다
        if category.canceled_at is not None:
            raise HTTPException(status_code=400, detail="취소된 예산 항목입니다. 되살린 뒤에 붙여주세요.")

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
        payer_bank=payer_bank.strip() or None,
        payer_account_number=payer_account_number.strip() or None,
        payer_account_holder=payer_account_holder.strip() or None,
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
    added = _add_receipt(db, retreat, entry, file=receipt, memo=receipt_memo,
                         original_no=receipt_original_no)
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
    original_no: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    """새 영수증 한 장을 더 붙인다 — 새 번호를 받는다 (7-4)."""
    entry = _my_entry(db, user, retreat, entry_id)
    added = _add_receipt(db, retreat, entry, file=receipt, memo=memo, original_no=original_no)
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


def _my_entry(db: Session, user: User, retreat: Retreat, entry_id: int) -> ExpenseEntry:
    """이 회차의 지출이고 내가 고칠 수 있는가 — 영수증을 붙이고 잇고 떼는 문이 같다."""
    entry = db.get(ExpenseEntry, entry_id)
    if entry is None or entry.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="지출 내역을 찾을 수 없습니다.")
    assert_can_edit_department(db, user, entry.department_id)
    return entry


@router.post("/expenses/{entry_id}/receipts/link")
def link_receipt(
    entry_id: int,
    number: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    """**이미 있는 영수증에 잇는다** — 새 번호를 주지 않는다 (7-4 · 사람이 정한 시트-가 ㄷ).

    종이 한 장에 지출 여럿이 걸리는 자리다. 번호로 고른다 — 행마다 영수증 목록을
    싣으면 지출 × 영수증만큼 화면이 커진다. 금액은 지출마다 그대로다.
    """
    entry = _my_entry(db, user, retreat, entry_id)
    receipt = db.scalar(
        select(ExpenseReceipt)
        .join(ExpenseEntry, ExpenseEntry.id == ExpenseReceipt.expense_id)
        .where(ExpenseEntry.retreat_id == retreat.id, ExpenseReceipt.number == number))
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"이 회차에 영수증 {number}번이 없습니다.")
    # **한 번도 이어진 적 없는 영수증은 잇지 않는다** — scripts/영수증잇기옮기기.py 가 원래
    # 지출에 이을 몫이다. 여기서 먼저 이으면 그 스크립트가 줄이 있다고 건너뛰어 원래 지출에
    # 영영 안 이어진다 (봐둘것 BB-d)
    if not receipt_has_links(db, receipt):
        raise HTTPException(status_code=409, detail=f"영수증 {number}번은 아직 원래 지출에 이어지지 않았습니다. 총무팀이 옛 영수증을 먼저 잇습니다.")
    if receipt in entry.receipts:
        return redirect(f"/expenses?retreat_id={retreat.id}",
                        message=f"영수증 {number}번은 이미 이 지출에 이어져 있습니다.")
    entry.attach_receipt(receipt)
    db.commit()
    log_activity(db, retreat_id=retreat.id, actor=user, action="영수증_잇기",
                 target_type="expense", target_id=entry.id, summary=f"[{number}] 잇기")
    return redirect(f"/expenses?retreat_id={retreat.id}", message=f"영수증 {number}번을 이었습니다.")


@router.post("/expenses/{entry_id}/receipts/{receipt_id}/detach")
def detach_receipt(
    entry_id: int,
    receipt_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    """**떼는 것은 지우는 것이 아니다** — 잇기 줄에 detached_at 을 찍고 영수증 행은 남긴다 (0장).

    마지막 한 곳에서 떼어도 된다 — 잘못 붙인 영수증이 그 지출에 영영 남던 자리다.
    뗀 영수증은 번호로 다시 이을 수 있다.
    """
    entry = _my_entry(db, user, retreat, entry_id)
    link = next((l for l in entry.receipt_links
                 if l.receipt_id == receipt_id and l.detached_at is None), None)
    if link is None:
        raise HTTPException(status_code=404, detail="이 지출에 이어진 영수증이 아닙니다.")
    # 저장 시각은 UTC — 같은 줄의 attached_at(models._now)과 한 시계로 (4-16)
    link.detached_at = _now()
    db.commit()
    log_activity(db, retreat_id=retreat.id, actor=user, action="영수증_떼기",
                 target_type="expense", target_id=entry.id,
                 summary=f"[{link.receipt.number}] 떼기 — 영수증은 남음")
    return redirect(f"/expenses?retreat_id={retreat.id}",
                    message=f"영수증 {link.receipt.number}번을 뗐습니다. 영수증은 남아 번호로 다시 이을 수 있습니다.")


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
