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


def 인원수(names: list[str] | None, 적힌수: int | None) -> int | None:
    """식대 인원 — **명단 이름 수로 센다** (7-2 · 2026-09-26 사람이 정함).

    인원 칸을 따로 두지 않는다: 명단과 인원을 둘 다 받으면 둘이 어긋날 때
    어느 쪽이 맞는지 화면이 말해 주지 못한다(같은 사실이 두 곳에 있으면
    갈린다 — 이 저장소의 그 원칙).

    **다만 시트에서 들여온 옛 줄은 이름 없이 숫자만 있다**(7-5 가 「못 뽑으면
    인원을 비우고 시트의 손 셈을 그대로 둔다」 고 한 그 줄들). 그때는 적힌
    숫자를 쓴다 — 이름이 없다고 0 으로 세면 지원금액이 조용히 0 이 된다.

    **「N명」 과 견줘 다름을 표시하지 않는다**(사람이 정함) — 비고에 적힌 옛
    글은 그 회차의 기록이고, 화면이 그것과 다투면 고칠 수 없는 경고가 는다.
    """
    if names:
        return len(names)
    return 적힌수
