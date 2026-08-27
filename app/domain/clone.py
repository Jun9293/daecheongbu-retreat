"""회차(Retreat) 복제.

새 회차를 만들 때 직전 회차의 부서 목록과 예산 카테고리를 그대로 가져온다.
지출·할일 같은 실행 데이터는 가져오지 않는다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import BudgetCategory, Department, Retreat


def clone_retreat(
    db: Session,
    *,
    source: Retreat,
    name: str,
    start_date: dt.date | None,
    end_date: dt.date | None,
) -> Retreat:
    new_retreat = Retreat(
        name=name,
        start_date=start_date,
        end_date=end_date,
        cloned_from_retreat_id=source.id,
        meal_subsidy_per_person=source.meal_subsidy_per_person,
    )
    db.add(new_retreat)
    db.flush()

    for dept in source.departments:
        db.add(
            Department(
                retreat_id=new_retreat.id,
                name=dept.name,
                color_tag=dept.color_tag,
                sort_order=dept.sort_order,
            )
        )

    for cat in source.budget_categories:
        db.add(
            BudgetCategory(
                retreat_id=new_retreat.id,
                level1=cat.level1,
                level2=cat.level2,
                level3=cat.level3,
                planned_amount=cat.planned_amount,
                sort_order=cat.sort_order,
            )
        )

    db.flush()
    db.refresh(new_retreat)
    return new_retreat
