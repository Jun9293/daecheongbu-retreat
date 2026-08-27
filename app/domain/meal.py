"""식대(모임 식사비) 정산 계산.

기존 "Belong 예산.xlsx" 지출 상세내역 시트에서 실측 검증한 공식:
    지원금액 = min(영수증 금액, 인원수 × 1인당 상한)
    개인부담액 = 영수증 금액 - 지원금액

1인당 상한은 회차(Retreat)별 설정값이다. 하드코딩 금지.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MealSettlement:
    subsidy_amount: int
    personal_burden_amount: int


def calculate_meal_settlement(
    *, amount: int, headcount: int, per_person_cap: int
) -> MealSettlement:
    if amount < 0:
        raise ValueError("금액은 0원 이상이어야 합니다.")
    if headcount < 0:
        raise ValueError("인원수는 0명 이상이어야 합니다.")
    if per_person_cap < 0:
        raise ValueError("1인당 상한은 0원 이상이어야 합니다.")

    subsidy = min(amount, headcount * per_person_cap)
    return MealSettlement(
        subsidy_amount=subsidy,
        personal_burden_amount=amount - subsidy,
    )
