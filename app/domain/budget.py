"""재정 — 숫자는 전부 여기서 나온다 (CLAUDE.md 7장 · 4-15).

예산 페이지 · 지출 페이지의 그룹 헤더 · 홈의 「예산 집행」 카드 · 결산 홈의
「미지급 환급 · 영수증 없는 지출」 · 회차 상세의 「남은 지출」 · 엑셀 —
전부 이 모듈의 같은 함수를 부른다. **라우터와 템플릿과 엑셀 쪽에는 세는 코드가 없다.**
두 벌이 되면 반드시 어긋나고, 어긋난 쪽이 돈이면 아무도 그냥 넘어가지 않는다.

2026-09-13 에 재어 보니 이 문장이 사실이 아니었다 — 지출 화면의 지표 넷 · 필터 조건 ·
엑셀 환급 시트의 미지급 합계 · 수입 금액 식 · 회차 목록의 지출 건수와 합이 밖에 있었다.
2026-09-14 에 전부 여기로 모았다(`list_totals` · `filter_entries` · `live_entries` ·
`refund_sheet` · `income_amount_of` · `expense_stats`). `tests/test_stage45.py` 가 밖에서
합·사칙 셈으로 다시 세는지 코드에서 끌어낸 이름으로 잰다 — **필터 조건과 건수는 못 본다.**

**취소된 예산 항목·수입은 합에 안 든다** (0장 · 7-3). 취소된 예산 항목에 걸린 지출은
사라지지 않고 `canceled_category_spent` 로 total_spent 에 든다.

식대 지출은 지원금액만 수련회 예산에서 집행된 것으로 본다(초과분은 개인부담 —
공식은 domain.meal). 홈 집행률의 분모는 **지출예산 총액**이고 수입(IncomeItem)은
예산 페이지의 잔액 계산에만 쓴다 (7-3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import account_shape
from app.models import BudgetCategory, ExpenseEntry, ExpenseReceipt, IncomeItem, Retreat

# 시트의 지출자 표기 그대로 — 이 이름이면 수련회 돈으로 바로 나간 것이라
# 환급할 사람이 없다. 개인 이름이면 그 사람에게 돌려줘야 한다 (7-4).
RETREAT_ACCOUNT = "수련회계좌"


def planned_amount_of(
    unit_price: int | None, headcount: int | None, times: int | None, manual: int
) -> int:
    """예산금액 = 단가 × 명수 × 횟수. 셋 중 하나라도 비면 직접 입력값 (7-3)."""
    if unit_price is not None and headcount is not None and times is not None:
        return unit_price * headcount * times
    return manual


def income_amount_of(unit_price: int | None, headcount: int | None, manual: int) -> int:
    """수입 금액 = 단가 × 명수. 둘 중 하나라도 비면 직접 입력값 (7-3).

    근거 없는 숫자를 남기지 않는다 — 둘이 있으면 곱이 이긴다. 전에는 이 식이
    라우터에 있었다(2026-09-14 에 여기로 모음).
    """
    if unit_price is not None and headcount is not None:
        return unit_price * headcount
    return manual


def split_account(raw: str | None, payer_name: str | None = None) -> tuple[str | None, str | None, str | None]:
    """한 칸에 뭉친 계좌(「은행 번호」)를 (은행, 번호, 예금주) 로 가른다 (7-4 · 사람이 정한 시트-라 ㄱ).

    **가르는 규칙은 여기 하나다.** 첫 빈칸으로 가르고 앞뒤 빈칸을 떼며, 예금주는 칸이 없어
    지출자 이름을 쓴다. 빈칸이 없으면 은행을 모르는 것이라 번호에만 넣는다.
    화면은 셋을 따로 받아 가를 일이 없다. **시트 들여오기(차례 6)가 이 함수를 부른다** — 스크립트에
    같은 규칙을 다시 적지 않는다.
    """
    text = (raw or "").strip()
    holder = (payer_name or "").strip() or None
    if not text:
        return None, None, holder
    bank, _, number = text.partition(" ")
    if not number.strip():
        return None, bank, holder
    return bank, number.strip(), holder


def account_problem(bank: str | None, number: str | None, holder: str | None) -> str | None:
    """계좌 셋이 DB 에 들어가도 되는 꼴인가 — 안 되면 까닭, 되면 None (봐둘것 BB-c · 2026-09-14).

    **계좌 칸에 값을 넣는 자리는 전부 이것을 지난다** — 지출 등록 · 지출 고치기 · 내 정보 ·
    시트 들여오기. 막는 것: 번호가 있는데 은행이 빈 것 · 번호에 숫자와 하이픈 말고 다른 글자
    (앞뒤·연속 하이픈 포함) · 숫자가 너무 적거나 많은 것 · 숫자만인 은행 · 지나치게 긴 은행·예금주.
    **셋 다 빈 것과 은행·예금주만 있는 것은 통과다** — 계좌를 안 적은 것이지 틀린 것이 아니다.
    꼴의 경계는 `app/account_shape.py` 에 있고, 시트의 계좌 64 줄이 전부 지나는 것에서 정했다.
    """
    bank, number, holder = ((v or "").strip() for v in (bank, number, holder))
    if number:
        if not bank:
            return "계좌번호가 있으면 은행도 적어주세요."
        if not account_shape.칸꼴.fullmatch(number):
            return "계좌번호는 숫자와 하이픈(-)만 적어주세요."
        if not account_shape.숫자_최소 <= account_shape.숫자수(number) <= account_shape.숫자_최대:
            return f"계좌번호의 숫자는 {account_shape.숫자_최소}~{account_shape.숫자_최대}개여야 합니다."
    if bank and (len(bank) > 20 or not any(ch.isalpha() for ch in bank)):
        return "은행 이름을 확인해주세요."
    if len(holder) > 30:
        return "예금주 이름이 너무 깁니다."
    return None


def account_tail(number: str | None) -> str:
    """화면에 보일 계좌번호의 끝 숫자 넷 — 숫자만 세어 자른다(「…1111」). 복사는 전체를 준다."""
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    return f"…{digits[-4:]}" if digits else ""


@dataclass
class CategorySummary:
    category: BudgetCategory
    planned: int
    spent: int
    # **예산비율** = 항목 예산 / 지출예산 총액 (7-3). 총액을 알아야 하므로 build 가 채운다.
    ratio_pct: float = 0.0
    # **결산비율** = 항목 결산 / 총 결산금액 (2026-09-26 사람이 정함).
    # 「집행률」(결산 ÷ 그 항목의 예산)과 **다른 수다** — 이쪽은 쓴 돈 전체에서
    # 이 항목이 차지하는 몫이라 분모가 총 결산이다. 둘을 한 이름으로 두면
    # 「100%를 넘는 비율」 과 「합이 100인 비율」 이 같은 칸에 섞인다
    settle_ratio_pct: float = 0.0

    @property
    def remaining(self) -> int:
        """차액 = 예산 − 결산. 음수(초과)는 화면이 붉게 칠한다 — 100% 로 덮지 않는다."""
        return self.planned - self.spent

    @property
    def progress_pct(self) -> float:
        if self.planned <= 0:
            return 0.0
        return round(self.spent / self.planned * 100, 1)

    @property
    def is_over_budget(self) -> bool:
        return self.spent > self.planned


@dataclass
class GroupSummary:
    """구분(level1) 소계 — 시트의 소계 행이 하던 일이다 (7-3)."""

    name: str
    rows: list[CategorySummary] = field(default_factory=list)
    # 소계 줄의 두 비율 — 줄의 것과 **같은 분모**를 쓴다. build 가 채운다
    ratio_pct: float = 0.0
    settle_ratio_pct: float = 0.0

    @property
    def planned(self) -> int:
        return sum(r.planned for r in self.rows)

    @property
    def spent(self) -> int:
        return sum(r.spent for r in self.rows)

    @property
    def remaining(self) -> int:
        return self.planned - self.spent

    @property
    def items(self) -> list[list[CategorySummary]]:
        """같은 항목(level2)끼리 묶은 것 — 화면이 **항목 셀을 병합**한다 (7-3).

        묶는 곳이 여기 하나여야 표의 rowspan 과 소계가 같은 것을 센다.
        **이어진 줄만 묶는다** — 사람이 순서를 정하는 표라 떨어져 있는 같은
        이름을 붙이면 사람이 놓은 자리가 화면에서 바뀐다.
        """
        out: list[list[CategorySummary]] = []
        for row in self.rows:
            if out and out[-1][0].category.level2 == row.category.level2:
                out[-1].append(row)
            else:
                out.append([row])
        return out


@dataclass
class BudgetSummary:
    # 산 예산 항목만 — 총액·비율·구분 소계·남은 지출·지출 등록의 선택지가 이것을 쓴다
    categories: list[CategorySummary] = field(default_factory=list)
    groups: list[GroupSummary] = field(default_factory=list)
    # 취소된 예산 항목 (7-3) — 행은 남아 화면 아래에 흐리게 서고 되살릴 수 있다.
    # 합계에는 안 든다. 그 항목에 걸린 지출의 집행은 canceled_category_spent 로 간다
    canceled_categories: list[CategorySummary] = field(default_factory=list)
    # 수입은 취소된 것까지 전부 — 화면이 흐리게 그린다. 합은 active_incomes 로만
    incomes: list[IncomeItem] = field(default_factory=list)
    uncategorized_spent: int = 0
    # **취소된 예산 항목에 걸린 지출의 집행 합** (2026-09-14 · 사람이 정한 나-ㄴ).
    # 항목을 취소해도 쓴 돈은 쓴 돈이라, 그 지출이 합계에서 조용히 사라지면 안 된다.
    # 「예산 항목 미지정」 과 같은 급의 따로 줄로 total_spent 에 든다 — 그래서
    # total_spent 는 늘 「취소 안 된 지출 전부의 집행 합」 이다
    canceled_category_spent: int = 0

    @property
    def total_planned(self) -> int:
        return sum(row.planned for row in self.categories)

    @property
    def total_spent(self) -> int:
        return (sum(row.spent for row in self.categories)
                + self.uncategorized_spent + self.canceled_category_spent)

    @property
    def total_remaining(self) -> int:
        return self.total_planned - self.total_spent

    @property
    def progress_pct(self) -> float:
        if self.total_planned <= 0:
            return 0.0
        return round(self.total_spent / self.total_planned * 100, 1)

    # ── 수입 (7-3) — 잔액 계산에만 쓴다. 집행률 분모는 지출예산 총액이다 ──
    @property
    def active_incomes(self) -> list[IncomeItem]:
        """취소 안 된 수입 — 합 · 잔액 · 「수입 미입력」 판정 · 엑셀이 이것을 본다."""
        return [i for i in self.incomes if i.canceled_at is None]

    @property
    def total_income(self) -> int:
        return sum(i.amount for i in self.active_incomes)

    @property
    def balance(self) -> int:
        """총 수입 − 총 지출예산."""
        return self.total_income - self.total_planned

    # ── 남은 지출 (4-17) — 지출이 한 건도 안 붙은 예산 항목 ─────────────
    @property
    def unspent_rows(self) -> list[CategorySummary]:
        return [row for row in self.categories if row.spent == 0]

    @property
    def unspent_count(self) -> int:
        return len(self.unspent_rows)

    @property
    def unspent_planned(self) -> int:
        return sum(row.planned for row in self.unspent_rows)


def build_budget_summary(db: Session, *, retreat: Retreat) -> BudgetSummary:
    categories = list(
        db.scalars(
            select(BudgetCategory)
            .where(BudgetCategory.retreat_id == retreat.id)
            .order_by(BudgetCategory.sort_order, BudgetCategory.id)
        )
    )
    # 취소된 지출은 집행에 넣지 않는다 (7-4) — 행은 목록에 흐리게 남지만
    # 합계·집행률은 실제로 쓴 돈만 말해야 한다
    expenses = list(
        db.scalars(
            select(ExpenseEntry).where(
                ExpenseEntry.retreat_id == retreat.id,
                ExpenseEntry.canceled_at.is_(None),
            )
        )
    )
    incomes = list(
        db.scalars(
            select(IncomeItem)
            .where(IncomeItem.retreat_id == retreat.id)
            .order_by(IncomeItem.sort_order, IncomeItem.id)
        )
    )

    spent_by_category: dict[int, int] = {}
    uncategorized = 0
    for entry in expenses:
        if entry.budget_category_id is None:
            uncategorized += entry.settlement_amount
        else:
            spent_by_category[entry.budget_category_id] = (
                spent_by_category.get(entry.budget_category_id, 0) + entry.settlement_amount
            )

    def summarize(cat: BudgetCategory) -> CategorySummary:
        return CategorySummary(
            category=cat, planned=cat.planned_amount, spent=spent_by_category.get(cat.id, 0)
        )

    rows = [summarize(cat) for cat in categories if cat.canceled_at is None]
    canceled = [summarize(cat) for cat in categories if cat.canceled_at is not None]
    canceled_spent = sum(row.spent for row in canceled)

    total_planned = sum(r.planned for r in rows)
    # 결산비율의 분모는 **총 결산금액**이다 — 미지정·취소된 항목에 걸린 지출까지
    # 든 값(BudgetSummary.total_spent 와 같은 셈)이라야 화면의 총계와 맞는다
    total_spent = sum(r.spent for r in rows) + uncategorized + canceled_spent
    for row in rows:
        row.ratio_pct = (
            round(row.planned / total_planned * 100, 1) if total_planned > 0 else 0.0
        )
        row.settle_ratio_pct = (
            round(row.spent / total_spent * 100, 1) if total_spent > 0 else 0.0
        )

    # 구분(level1)별 소계 — 목록 순서를 지키며 묶는다
    groups: list[GroupSummary] = []
    by_name: dict[str, GroupSummary] = {}
    for row in rows:
        name = row.category.level1
        group = by_name.get(name)
        if group is None:
            group = by_name[name] = GroupSummary(name=name)
            groups.append(group)
        group.rows.append(row)

    for group in groups:
        group.ratio_pct = (
            round(group.planned / total_planned * 100, 1) if total_planned > 0 else 0.0
        )
        group.settle_ratio_pct = (
            round(group.spent / total_spent * 100, 1) if total_spent > 0 else 0.0
        )

    return BudgetSummary(
        categories=rows, groups=groups, canceled_categories=canceled, incomes=incomes,
        uncategorized_spent=uncategorized, canceled_category_spent=canceled_spent,
    )


# ── 지출 목록의 필터 — 홈 결산의 숫자와 같은 정의다 (4-15) ─────────────
#
# 규칙: 홈의 숫자 = 그 숫자를 눌러 간 화면(?filter=…)의 행 수. 정의가 두 곳에
# 있으면 홈이 3건이라는데 화면에는 2건이 떠서, 보는 사람이 어느 쪽을 믿을지
# 정해야 한다.


def is_refund_target(entry: ExpenseEntry) -> bool:
    """지출자가 수련회계좌면 환급 대상이 아니고, 개인이면 환급 대상이다 (7-4).

    입력이 자유 텍스트라 **공백을 지우고** 견준다 — 「수련회 계좌」 같은 변형
    표기가 환급 목록에 잡음으로 끼지 않게. **빈 값은 환급 대상이 아니다** —
    지출자를 안 적은 것이지 개인이 낸 것이 아니고, 돌려줄 사람도 없다.
    """
    name = "".join((entry.payer_name or "").split())
    if not name:
        return False
    return name != RETREAT_ACCOUNT


def is_unpaid_refund(entry: ExpenseEntry) -> bool:
    """환급 대상 — 개인이 대신 낸 것 중 아직 안 돌려준 것 (미지급).

    취소된 지출은 아니다 — 안 쓴 돈을 돌려줄 일이 없다 (7-4).
    """
    return is_refund_target(entry) and not entry.paid and entry.canceled_at is None


def has_no_receipt(entry: ExpenseEntry) -> bool:
    """영수증이 한 건도 안 붙은 지출 — 결산 홈의 「영수증 없는 지출」 (4-15).

    기준은 **걸린 영수증 0건**(끊기지 않은 잇기 줄 · 2026-09-14)이다. 옛 receipt_file_url 이 아니다 — 그 컬럼은
    남기되 읽지 않는다 (7-4). 취소된 지출은 세지 않는다 — 결산에 안 들어갈
    행의 영수증을 챙기라는 경고는 잡음이다.
    """
    return not entry.receipts and entry.canceled_at is None


# 칩과 홈 결산이 같은 정의를 쓴다 (4-15) — 홈의 N = 그 필터 화면의 행 수.
# **조건은 여기 한 벌이다.** 전에는 지출 라우터가 같은 조건을 다시 적고 있었다
# (2026-09-13 재정 보기 판이 잼 · 2026-09-14 에 모음).
FILTERS = ("all", "meal", "unpaid", "refund", "noreceipt")
_필터조건 = {
    # 「전체」 는 취소된 행도 흐리게 남긴다 (7-4) — 나머지는 챙길 일의 목록이라 뺀다
    "all": lambda e: True,
    "meal": lambda e: e.is_meal_expense and e.canceled_at is None,
    "unpaid": lambda e: not e.paid and e.canceled_at is None,
    "refund": is_unpaid_refund,
    "noreceipt": has_no_receipt,
}


def filter_entries(entries: list[ExpenseEntry], name: str) -> list[ExpenseEntry]:
    """지출 목록의 필터 하나를 건다. 모르는 이름은 「전체」 다."""
    keep = _필터조건.get(name, _필터조건["all"])
    return [e for e in entries if keep(e)]


def refund_entries(db: Session, retreat: Retreat) -> list[ExpenseEntry]:
    return filter_entries(entries_of(db, retreat), "refund")


def no_receipt_entries(db: Session, retreat: Retreat) -> list[ExpenseEntry]:
    return filter_entries(entries_of(db, retreat), "noreceipt")


@dataclass
class ListTotals:
    """지출 화면의 지표 넷 — **지금 필터에 걸린 행** 기준이다.

    summary 의 total_spent(회차 전체의 집행)와 뜻이 달라 같은 함수로 묶지
    않는다(2026-09-14). 식은 같은 모델 속성(settlement_amount 등)을 쓴다.
    취소된 행은 「전체」 에 보여도 합에는 안 든다 (7-4).
    """

    amount: int
    subsidy: int
    burden: int
    settlement: int


def list_totals(entries: list[ExpenseEntry]) -> ListTotals:
    live = live_entries(entries)
    return ListTotals(
        amount=sum(e.amount for e in live),
        subsidy=sum(e.subsidy_amount for e in live if e.is_meal_expense),
        burden=sum(e.personal_burden_amount for e in live if e.is_meal_expense),
        settlement=sum(e.settlement_amount for e in live),
    )


def live_entries(entries: list[ExpenseEntry]) -> list[ExpenseEntry]:
    """취소 안 된 지출 — 결산 파일은 이것만 싣는다 (7-4). 전에는 이 거름이 내려받기
    라우터에 있었다(2026-09-14 커밋 전 검토 [B] 가 짚어 여기로 옮김)."""
    return [e for e in entries if e.canceled_at is None]


@dataclass
class RefundSheet:
    """엑셀 환급 시트 — 개인이 낸 것 전부(지급된 것도)와 미지급 합계·건수."""

    rows: list[ExpenseEntry]
    unpaid_count: int
    unpaid_total: int


def refund_sheet(entries: list[ExpenseEntry]) -> RefundSheet:
    """취소된 지출은 **스스로 뺀다** — 부르는 쪽이 미리 걸렀는지에 기대면, 그 한 줄이
    빠지는 날 「미지급 환급」 이 `is_unpaid_refund` 와 갈리고 아무도 모른다."""
    rows = [e for e in live_entries(entries) if is_refund_target(e)]
    unpaid = [e for e in rows if not e.paid]
    return RefundSheet(
        rows=rows, unpaid_count=len(unpaid),
        unpaid_total=sum(e.settlement_amount for e in unpaid),
    )


def next_receipt_number(db: Session, retreat: Retreat) -> int:
    """다음 영수증 번호 — 회차 안에서 자동 증가 (7-4). 뗀 영수증도 센다 —
    회차는 처음 붙은 지출(expense_id)에서 알고, 번호는 영수증마다 하나다."""
    current = db.scalar(
        select(ExpenseReceipt.number)
        .join(ExpenseEntry, ExpenseEntry.id == ExpenseReceipt.expense_id)
        .where(ExpenseEntry.retreat_id == retreat.id)
        .order_by(ExpenseReceipt.number.desc())
    )
    return (current or 0) + 1


def receipt_has_links(db: Session, receipt: ExpenseReceipt) -> bool:
    """잇기 줄이 하나라도 있었는가(끊긴 것도) — 없으면 잇기 표 전의 영수증이다 (7-4)."""
    from app.models import ExpenseReceiptLink

    return db.scalar(select(ExpenseReceiptLink.id)
                     .where(ExpenseReceiptLink.receipt_id == receipt.id).limit(1)) is not None


def unlinked_receipt_count(db: Session, retreat: Retreat) -> int:
    """이 회차에서 **한 번도 이어진 적 없는** 영수증 수 (7-4 · 2026-09-14 차례 4).

    잇기 표가 생기기 전의 영수증이다 — scripts/영수증잇기옮기기.py 를 돌리기 전에는
    어느 지출에도 안 보인다. 뗀 영수증은 잇기 줄이 남아 있어 여기 안 든다.
    """
    from app.models import ExpenseReceiptLink

    return db.scalar(
        select(func.count()).select_from(ExpenseReceipt)
        .join(ExpenseEntry, ExpenseEntry.id == ExpenseReceipt.expense_id)
        .where(ExpenseEntry.retreat_id == retreat.id,
               ~select(ExpenseReceiptLink.id)
               .where(ExpenseReceiptLink.receipt_id == ExpenseReceipt.id).exists())
    ) or 0


def expense_stats(db: Session, retreat_id: int) -> tuple[int, int]:
    """회차 목록·상세의 「지출 완료 N건 · X원」 — 취소된 행은 넣지 않는다 (7-4).

    X 는 **영수증 총액(amount)** 의 합이다 — 집행(settlement)이 아니다. 전에는
    설정 라우터에 있었고 2026-09-13 재정 보기 판이 못 센 자리였다(2026-09-14 에 모음).
    summary 는 원천에서 빼는데 이 둘만 품으면 같은 화면의 두 숫자가 갈린다.
    """
    live = (ExpenseEntry.retreat_id == retreat_id, ExpenseEntry.canceled_at.is_(None))
    count = db.scalar(select(func.count()).select_from(ExpenseEntry).where(*live)) or 0
    total = db.scalar(
        select(func.coalesce(func.sum(ExpenseEntry.amount), 0)).where(*live)
    ) or 0
    return int(count), int(total)


def entries_of(db: Session, retreat: Retreat) -> list[ExpenseEntry]:
    return list(
        db.scalars(
            select(ExpenseEntry)
            .where(ExpenseEntry.retreat_id == retreat.id)
            .options(selectinload(ExpenseEntry.receipts).selectinload(ExpenseReceipt.expenses))
            .order_by(ExpenseEntry.id)
        )
    )


def 긴줄인가(e: ExpenseEntry) -> bool:
    """그 지출 아래에 **긴 내용 줄**(명단 · 비고)이 서나 (7-4).

    화면과 병합 수가 **같은 이 판정**을 쓴다 — 두 벌이면 rowspan 이 실제 줄
    수와 어긋나고, 어긋난 쪽이 화면이라 표가 통째로 밀린다.
    """
    # **식대는 명단이 비어도 줄이 선다** (2026-09-26 두 번째 검토 [1]) — 그 자리가
    # 인원을 넣는 유일한 길이라, 비었다고 안 그리면 그 줄은 금액도 못 고친다
    return bool(e.note or e.is_meal_expense)


def 세부묶음(entries: list[ExpenseEntry]) -> list[dict]:
    """지출 줄을 **세부항목-2(level3b)로 묶는다** (7-4 · 2026-09-26 확정본).

    화면이 그 칸을 **세로로 병합**하고(같은 세부항목에 영수증이 여럿 걸린다),
    그 묶음에 세부항목-3 이 하나도 없으면 **가로로 합친다**.

    **이어진 줄만 묶는다** — 목록 순서는 사람이 보는 순서라, 떨어져 있는 같은
    이름을 붙이면 줄이 제자리에서 움직인다(예산 표의 `GroupSummary.items` 와
    같은 규칙이다).
    """
    out: list[dict] = []
    for e in entries:
        이름 = (e.level3b or "").strip()
        if out and out[-1]["name"] == 이름:
            out[-1]["entries"].append(e)
        else:
            out.append({"name": 이름, "entries": [e]})
    for blk in out:
        blk["has_l3c"] = any((x.level3c or "").strip() for x in blk["entries"])
        # **그려질 줄 수**다 — 긴 내용이 있는 지출은 아래에 한 줄이 더 선다.
        # 병합(rowspan)이 이 수를 안 쓰면 그 묶음 아래의 칸이 통째로 밀린다
        # (2026-09-26 커밋 전 검토 [C])
        blk["rows"] = len(blk["entries"]) + sum(1 for x in blk["entries"] if 긴줄인가(x))
    return out
