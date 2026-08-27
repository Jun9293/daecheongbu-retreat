"""예산 대비 지출 집계.

식대 지출은 지원금액만 수련회 예산에서 집행된 것으로 본다(초과분은 개인부담).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BudgetCategory, ExpenseEntry, Retreat


@dataclass
class CategorySummary:
    category: BudgetCategory
    planned: int
    spent: int

    @property
    def remaining(self) -> int:
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
class BudgetSummary:
    categories: list[CategorySummary] = field(default_factory=list)
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
    return BudgetSummary(categories=rows, uncategorized_spent=uncategorized)
