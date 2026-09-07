"""재정 — 숫자는 전부 여기서 나온다 (CLAUDE.md 7장 · 4-15).

예산 페이지 · 지출 페이지의 그룹 헤더 · 홈의 「예산 집행」 카드 · 결산 홈의
「미지급 환급 · 영수증 없는 지출」 · 회차 상세의 「남은 지출」 · 엑셀 —
전부 이 모듈의 같은 함수를 부른다. **라우터와 템플릿에는 세는 코드가 없다.**
두 벌이 되면 반드시 어긋나고, 어긋난 쪽이 돈이면 아무도 그냥 넘어가지 않는다.

식대 지출은 지원금액만 수련회 예산에서 집행된 것으로 본다(초과분은 개인부담 —
공식은 domain.meal). 홈 집행률의 분모는 **지출예산 총액**이고 수입(IncomeItem)은
예산 페이지의 잔액 계산에만 쓴다 (7-3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import BudgetCategory, ExpenseEntry, IncomeItem, Retreat

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


@dataclass
class CategorySummary:
    category: BudgetCategory
    planned: int
    spent: int
    # 비율 = 항목 예산 / 지출예산 총액 (7-3). 총액을 알아야 하므로 build 가 채운다.
    ratio_pct: float = 0.0

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

    @property
    def planned(self) -> int:
        return sum(r.planned for r in self.rows)

    @property
    def spent(self) -> int:
        return sum(r.spent for r in self.rows)

    @property
    def remaining(self) -> int:
        return self.planned - self.spent


@dataclass
class BudgetSummary:
    categories: list[CategorySummary] = field(default_factory=list)
    groups: list[GroupSummary] = field(default_factory=list)
    incomes: list[IncomeItem] = field(default_factory=list)
    uncategorized_spent: int = 0

    @property
    def total_planned(self) -> int:
        return sum(row.planned for row in self.categories)

    @property
    def total_spent(self) -> int:
        return sum(row.spent for row in self.categories) + self.uncategorized_spent

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
    def total_income(self) -> int:
        return sum(i.amount for i in self.incomes)

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
    expenses = list(
        db.scalars(select(ExpenseEntry).where(ExpenseEntry.retreat_id == retreat.id))
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

    rows = [
        CategorySummary(
            category=cat,
            planned=cat.planned_amount,
            spent=spent_by_category.get(cat.id, 0),
        )
        for cat in categories
    ]

    total_planned = sum(r.planned for r in rows)
    for row in rows:
        row.ratio_pct = (
            round(row.planned / total_planned * 100, 1) if total_planned > 0 else 0.0
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

    return BudgetSummary(
        categories=rows, groups=groups, incomes=incomes, uncategorized_spent=uncategorized
    )


# ── 지출 목록의 필터 — 홈 결산의 숫자와 같은 정의다 (4-15) ─────────────
#
# 규칙: 홈의 숫자 = 그 숫자를 눌러 간 화면(?filter=…)의 행 수. 정의가 두 곳에
# 있으면 홈이 3건이라는데 화면에는 2건이 떠서, 보는 사람이 어느 쪽을 믿을지
# 정해야 한다.


def is_refund_target(entry: ExpenseEntry) -> bool:
    """지출자가 수련회계좌면 환급 대상이 아니고, 개인이면 환급 대상이다 (7-4)."""
    return (entry.payer_name or "").strip() != RETREAT_ACCOUNT


def refund_entries(db: Session, retreat: Retreat) -> list[ExpenseEntry]:
    """환급 대상 — 개인이 대신 낸 것 중 아직 안 돌려준 것 (미지급)."""
    return [
        e
        for e in entries_of(db, retreat)
        if is_refund_target(e) and not e.paid
    ]


def no_receipt_entries(db: Session, retreat: Retreat) -> list[ExpenseEntry]:
    """영수증이 한 건도 안 붙은 지출 — 결산 홈의 「영수증 없는 지출」 (4-15).

    기준은 ExpenseReceipt 0건이다. 옛 receipt_file_url 이 아니다 — 그 컬럼은
    남기되 읽지 않는다 (7-4).
    """
    return [e for e in entries_of(db, retreat) if not e.receipts]


def next_receipt_number(db: Session, retreat: Retreat) -> int:
    """다음 영수증 번호 — 회차 안에서 자동 증가 (7-4)."""
    from app.models import ExpenseReceipt

    current = db.scalar(
        select(ExpenseReceipt.number)
        .join(ExpenseEntry, ExpenseEntry.id == ExpenseReceipt.expense_id)
        .where(ExpenseEntry.retreat_id == retreat.id)
        .order_by(ExpenseReceipt.number.desc())
    )
    return (current or 0) + 1


def entries_of(db: Session, retreat: Retreat) -> list[ExpenseEntry]:
    return list(
        db.scalars(
            select(ExpenseEntry)
            .where(ExpenseEntry.retreat_id == retreat.id)
            .options(selectinload(ExpenseEntry.receipts))
            .order_by(ExpenseEntry.id)
        )
    )
