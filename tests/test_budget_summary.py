"""예산 대비 지출 집계 테스트."""

from sqlalchemy.orm import Session

from app import models
from app.domain.budget import build_budget_summary


def _add_expense(db, retreat, category, **kwargs):
    entry = models.ExpenseEntry(
        retreat_id=retreat.id, budget_category_id=category.id, **kwargs
    )
    db.add(entry)
    db.commit()
    return entry


def test_카테고리별_예산_대비_집행액과_진행률을_계산한다(db: Session, sample_retreat):
    poster = sample_retreat.budget_categories[0]  # 예산 300,000
    _add_expense(db, sample_retreat, poster, amount=100_000)

    summary = build_budget_summary(db, retreat=sample_retreat)
    row = next(r for r in summary.categories if r.category.id == poster.id)

    assert row.planned == 300_000
    assert row.spent == 100_000
    assert row.remaining == 200_000
    assert row.progress_pct == 33.3


def test_식대_지출은_지원금액만_예산에서_집행된_것으로_본다(db: Session, sample_retreat):
    meal_cat = sample_retreat.budget_categories[4]  # 모임 식사비, 예산 1,000,000
    _add_expense(
        db,
        sample_retreat,
        meal_cat,
        amount=130_600,
        is_meal_expense=True,
        meal_headcount=12,
        subsidy_amount=96_000,
        personal_burden_amount=34_600,
    )

    summary = build_budget_summary(db, retreat=sample_retreat)
    row = next(r for r in summary.categories if r.category.id == meal_cat.id)

    assert row.spent == 96_000


def test_지출이_없는_카테고리는_집행액이_0이다(db: Session, sample_retreat):
    summary = build_budget_summary(db, retreat=sample_retreat)

    assert all(row.spent == 0 for row in summary.categories)
    assert all(row.progress_pct == 0 for row in summary.categories)


def test_전체_합계를_계산한다(db: Session, sample_retreat):
    cats = sample_retreat.budget_categories
    _add_expense(db, sample_retreat, cats[0], amount=100_000)
    _add_expense(db, sample_retreat, cats[1], amount=200_000)

    summary = build_budget_summary(db, retreat=sample_retreat)

    assert summary.total_planned == 300_000 + 800_000 + 4_000_000 + 2_500_000 + 1_000_000
    assert summary.total_spent == 300_000
    assert summary.total_remaining == summary.total_planned - 300_000


def test_예산을_초과하면_초과로_표시된다(db: Session, sample_retreat):
    poster = sample_retreat.budget_categories[0]  # 예산 300,000
    _add_expense(db, sample_retreat, poster, amount=350_000)

    summary = build_budget_summary(db, retreat=sample_retreat)
    row = next(r for r in summary.categories if r.category.id == poster.id)

    assert row.is_over_budget is True
    assert row.remaining == -50_000


def test_예산이_0인_카테고리의_진행률은_0으로_처리한다(db: Session, sample_retreat):
    cat = models.BudgetCategory(
        retreat_id=sample_retreat.id, level1="기타", level2="미정", planned_amount=0
    )
    db.add(cat)
    db.commit()
    _add_expense(db, sample_retreat, cat, amount=10_000)

    summary = build_budget_summary(db, retreat=sample_retreat)
    row = next(r for r in summary.categories if r.category.id == cat.id)

    assert row.progress_pct == 0
    assert row.is_over_budget is True


def test_카테고리에_연결되지_않은_지출도_총_집행액에_포함된다(db: Session, sample_retreat):
    db.add(models.ExpenseEntry(retreat_id=sample_retreat.id, amount=70_000))
    db.commit()

    summary = build_budget_summary(db, retreat=sample_retreat)

    assert summary.total_spent == 70_000
    assert summary.uncategorized_spent == 70_000
