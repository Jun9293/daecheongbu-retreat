"""식대 정산 계산 로직 테스트.

공식(실측 검증): 지원금액 = min(금액, 인원수 × 1인당 상한)
근거: Belong 예산.xlsx "지출 상세내역" 시트
"""
import pytest

from app.domain.meal import calculate_meal_settlement


def test_상한을_넘으면_인원수x상한까지만_지원한다():
    # 실측 사례: 12명 / 130,600원 → 지원 96,000원
    result = calculate_meal_settlement(amount=130_600, headcount=12, per_person_cap=8_000)

    assert result.subsidy_amount == 96_000
    assert result.personal_burden_amount == 34_600


def test_상한_미만이면_영수증_금액을_전액_지원한다():
    # 실측 사례: 9명 / 68,900원 → 지원 68,900원 전액
    result = calculate_meal_settlement(amount=68_900, headcount=9, per_person_cap=8_000)

    assert result.subsidy_amount == 68_900
    assert result.personal_burden_amount == 0


def test_상한값은_회차별로_다르게_적용된다():
    # 소그룹지원비 규정(5,000원) 사례
    result = calculate_meal_settlement(amount=100_000, headcount=10, per_person_cap=5_000)

    assert result.subsidy_amount == 50_000
    assert result.personal_burden_amount == 50_000


def test_인원수가_0이면_지원금액은_0이고_전액_개인부담이다():
    result = calculate_meal_settlement(amount=30_000, headcount=0, per_person_cap=8_000)

    assert result.subsidy_amount == 0
    assert result.personal_burden_amount == 30_000


def test_금액과_상한이_정확히_같으면_전액_지원된다():
    result = calculate_meal_settlement(amount=80_000, headcount=10, per_person_cap=8_000)

    assert result.subsidy_amount == 80_000
    assert result.personal_burden_amount == 0


def test_음수_금액은_거부한다():
    with pytest.raises(ValueError):
        calculate_meal_settlement(amount=-1, headcount=5, per_person_cap=8_000)


def test_음수_인원수는_거부한다():
    with pytest.raises(ValueError):
        calculate_meal_settlement(amount=10_000, headcount=-1, per_person_cap=8_000)


def test_음수_상한은_거부한다():
    with pytest.raises(ValueError):
        calculate_meal_settlement(amount=10_000, headcount=5, per_person_cap=-1)
