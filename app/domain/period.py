"""회차가 끝났는가 — 판정은 여기 하나다 (CLAUDE.md 4-10).

진단 패널(4-10) · 진행 화면(5-6) · 결산 홈(4-15) · 회차 상세의 남은 지출(4-17)
이 전부 이 함수를 **불러야 한다.** 각자 판정하면 화면마다 「종료」 의 뜻이
갈리고, 갈린 쪽을 아무도 눈치채지 못한다.

지금 부르는 곳은 설정의 회차 관리(4-17)뿐이다 — 4-10(diagnosis.py) 과
5-6(live.py) 의 판정을 여기로 모으는 것은 **UI 개편 단계 2** 다. 그때까지
같은 판정이 세 벌로 있는 상태이고, 값이 갈리면 이쪽이 정본이다.

`today` 는 인자로 받는다 (5-2) — 테스트가 실행 시각에 따라 갈리면 안 되고,
한 화면을 그리는 동안 여러 계산이 서로 다른 '지금' 을 보면 안 된다.
"""

from __future__ import annotations

import datetime as dt


def is_over(retreat, today: dt.date) -> bool:
    """폐회일(closeDate)이 오늘보다 이르거나 보관된 회차면 끝난 것이다.

    폐회일 **당일은 아직 진행 중**이다 — 결산 홈으로 바뀌는 것은 폐회일
    다음 날부터다 (4-15 결산 홈 전환).
    """
    if getattr(retreat, "is_archived", False):
        return True
    close = getattr(retreat, "end_date", None)
    return close is not None and close < today
