"""재정 엑셀 — **화면과 같은 함수의 결과를 놓기만 한다** (7-3 · 5-8과 같은 원칙).

세 시트: 지출 상세내역 · 예산 대비 집행 · 환급 대상자.
숫자는 전부 domain.budget 이 만든 것을 받는다 — 여기서 다시 세면 화면과
파일이 갈리고, 갈린 쪽이 파일이면 그 사실을 아무도 모른 채 카카오톡으로
돌아다닌다.
"""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.domain.budget import BudgetSummary, is_refund_target
from app.models import ExpenseEntry

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(color="FFFFFF", bold=True)
BOLD = Font(bold=True)
MONEY = "#,##0"


def _style_header(ws, ncols: int) -> None:
    for col in range(1, ncols + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"


def _widths(ws, widths: list[int]) -> None:
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width


def write(summary: BudgetSummary, entries: list[ExpenseEntry]) -> io.BytesIO:
    """summary(화면과 같은 것)와 지출 목록을 받아 통째로 놓는다."""
    wb = Workbook()

    # 1) 지출 상세내역 — 시트 「Belong 예산」 의 컬럼 순서 (7-1)
    ws = wb.active
    ws.title = "지출 상세내역"
    headers = [
        "구분", "항목", "세부항목-1", "세부항목-2", "세부항목-3", "부서",
        "영수증번호", "지출일자", "금액", "지원금액", "개인부담액",
        "식사인원", "참석자 명단", "비고", "지급여부", "지급일", "지출자", "지출자 계좌",
    ]
    ws.append(headers)
    for e in entries:
        numbers = ", ".join(str(r.number) for r in e.receipts) or None
        ws.append(
            [
                e.level1, e.level2, e.level3a, e.level3b, e.level3c,
                e.department.name if e.department else None,
                numbers,
                e.expense_date,
                e.amount,
                # 같은 식을 다시 적지 않는다 — 집행 금액은 모델의 한 곳에서
                e.settlement_amount,
                e.personal_burden_amount if e.is_meal_expense else 0,
                e.meal_headcount,
                " ".join(e.meal_attendee_names or []) or None,
                e.note,
                "지급완료" if e.paid else "미지급",
                e.paid_date,
                e.payer_name,
                e.payer_account,
            ]
        )
    for row in ws.iter_rows(min_row=2, min_col=9, max_col=11):
        for cell in row:
            cell.number_format = MONEY
    for row in ws.iter_rows(min_row=2, min_col=8, max_col=8):
        for cell in row:
            cell.number_format = "yyyy-mm-dd"
    _style_header(ws, len(headers))
    _widths(ws, [12, 16, 14, 14, 14, 10, 10, 12, 12, 12, 12, 9, 30, 24, 10, 12, 10, 20])

    # 2) 예산 대비 집행 — 구분 소계·총계·비율 전부 summary 의 값이다 (7-3)
    ws2 = wb.create_sheet("예산 대비 집행")
    ws2.append(["구분", "항목", "세부항목", "예산금액", "결산금액", "차액", "비율(%)", "집행률(%)"])
    for group in summary.groups:
        for row in group.rows:
            cat = row.category
            ws2.append(
                [cat.level1, cat.level2, cat.level3,
                 row.planned, row.spent, row.remaining, row.ratio_pct, row.progress_pct]
            )
        sub = ws2.max_row + 1
        ws2.append([f"{group.name} 소계", "", "", group.planned, group.spent, group.remaining, "", ""])
        for col in range(1, 9):
            ws2.cell(row=sub, column=col).font = BOLD
    total_row = ws2.max_row + 1
    ws2.append(
        ["총계", "", "", summary.total_planned, summary.total_spent,
         summary.total_remaining, "", summary.progress_pct]
    )
    for col in range(1, 9):
        ws2.cell(row=total_row, column=col).font = BOLD
    if summary.uncategorized_spent:
        ws2.append(["(예산 항목 미지정 지출)", "", "", 0, summary.uncategorized_spent, "", "", ""])
    if summary.incomes:
        ws2.append([])
        ws2.append(["수입", "", "", "", "", "", "", ""])
        for income in summary.incomes:
            ws2.append([income.name, income.note, "", income.amount, "", "", "", ""])
        ws2.append(["총 수입", "", "", summary.total_income, "", "", "", ""])
        ws2.append(["잔액 (총 수입 − 총 지출예산)", "", "", summary.balance, "", "", "", ""])
    for row in ws2.iter_rows(min_row=2, min_col=4, max_col=6):
        for cell in row:
            cell.number_format = MONEY
    _style_header(ws2, 8)
    _widths(ws2, [16, 20, 18, 14, 14, 14, 10, 10])

    # 3) 환급 대상자 — 개인이 대신 낸 것 (7-4). 지급된 것도 함께 싣되 표시한다
    ws3 = wb.create_sheet("환급 대상자")
    # 열 이름은 「환급액」 — 비식대 행에는 전액이 들어가므로 「지원금액」 이라
    # 적으면 열 이름과 값의 뜻이 어긋난다
    ws3.append(["영수증번호", "항목", "지출일자", "환급액", "지출자", "계좌", "지급여부"])
    refund_rows = [e for e in entries if is_refund_target(e)]
    for e in refund_rows:
        ws3.append(
            [
                ", ".join(str(r.number) for r in e.receipts) or None,
                e.budget_category.display_name if e.budget_category else None,
                e.expense_date,
                e.settlement_amount,
                e.payer_name,
                e.payer_account,
                "지급완료" if e.paid else "미지급",
            ]
        )
    ws3.append([])
    unpaid = [e for e in refund_rows if not e.paid]
    ws3.append(["미지급 합계", "", "", sum(e.settlement_amount for e in unpaid), "", "", f"{len(unpaid)}건"])
    for row in ws3.iter_rows(min_row=2, min_col=4, max_col=4):
        for cell in row:
            cell.number_format = MONEY
    _style_header(ws3, 7)
    _widths(ws3, [12, 26, 12, 14, 12, 26, 10])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
