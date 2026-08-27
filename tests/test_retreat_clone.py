"""회차(Retreat) 복제 테스트.

CLAUDE.md 3-1: "Retreat 생성/복제 (부서 목록, 예산 카테고리 포함 복제)"
지출/할일 같은 실행 데이터는 복제하지 않는다.
"""

import datetime as dt

from sqlalchemy.orm import Session

from app import models
from app.domain.clone import clone_retreat


def test_복제된_회차는_부서_목록을_그대로_가져온다(db: Session, sample_retreat):
    new_retreat = clone_retreat(
        db, source=sample_retreat, name="2027 겨울수련회", start_date=None, end_date=None
    )
    db.commit()

    names = [d.name for d in new_retreat.departments]
    assert names == ["총무팀", "홍보팀", "찬양팀"]


def test_복제된_회차는_예산_카테고리와_예산금액을_그대로_가져온다(db: Session, sample_retreat):
    new_retreat = clone_retreat(
        db, source=sample_retreat, name="2027 겨울수련회", start_date=None, end_date=None
    )
    db.commit()

    assert len(new_retreat.budget_categories) == 5
    first = new_retreat.budget_categories[0]
    assert (first.level1, first.level2, first.level3) == ("홍보", "포스터", "인쇄비")
    assert first.planned_amount == 300_000


def test_복제된_부서와_카테고리는_새_회차에_귀속된다(db: Session, sample_retreat):
    new_retreat = clone_retreat(
        db, source=sample_retreat, name="2027 겨울수련회", start_date=None, end_date=None
    )
    db.commit()

    assert new_retreat.id != sample_retreat.id
    assert all(d.retreat_id == new_retreat.id for d in new_retreat.departments)
    assert all(c.retreat_id == new_retreat.id for c in new_retreat.budget_categories)
    # 원본은 그대로 남아 있어야 한다
    db.refresh(sample_retreat)
    assert len(sample_retreat.departments) == 3


def test_복제_출처가_기록된다(db: Session, sample_retreat):
    new_retreat = clone_retreat(
        db, source=sample_retreat, name="2027 겨울수련회", start_date=None, end_date=None
    )
    db.commit()

    assert new_retreat.cloned_from_retreat_id == sample_retreat.id


def test_식대_상한_설정값도_함께_복제된다(db: Session, sample_retreat):
    sample_retreat.meal_subsidy_per_person = 5_000
    db.commit()

    new_retreat = clone_retreat(
        db, source=sample_retreat, name="2027 겨울수련회", start_date=None, end_date=None
    )
    db.commit()

    assert new_retreat.meal_subsidy_per_person == 5_000


def test_지출과_할일은_복제되지_않는다(db: Session, sample_retreat):
    db.add(
        models.Task(retreat_id=sample_retreat.id, title="포스터 시안 확정", status="대기")
    )
    db.add(models.ExpenseEntry(retreat_id=sample_retreat.id, amount=50_000))
    db.commit()

    new_retreat = clone_retreat(
        db, source=sample_retreat, name="2027 겨울수련회", start_date=None, end_date=None
    )
    db.commit()

    assert new_retreat.tasks == []
    assert new_retreat.expenses == []


def test_새_회차의_기간을_지정할_수_있다(db: Session, sample_retreat):
    new_retreat = clone_retreat(
        db,
        source=sample_retreat,
        name="2027 겨울수련회",
        start_date=dt.date(2027, 1, 5),
        end_date=dt.date(2027, 1, 7),
    )
    db.commit()

    assert new_retreat.start_date == dt.date(2027, 1, 5)
    assert new_retreat.end_date == dt.date(2027, 1, 7)
