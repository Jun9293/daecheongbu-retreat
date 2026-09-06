"""회차가 끝났는가 — 판정은 여기 하나다 (CLAUDE.md 4-10).

진단 패널(4-10) · 진행 화면(5-6) · 결산 홈(4-15) · 회차 상세의 남은 지출(4-17)
이 전부 이 함수를 부른다. 각자 판정하면 화면마다 「종료」 의 뜻이 갈리고,
갈린 쪽을 아무도 눈치채지 못한다.

`today` 는 인자로 받는다 (5-2) — 테스트가 실행 시각에 따라 갈리면 안 되고,
한 화면을 그리는 동안 여러 계산이 서로 다른 '지금' 을 보면 안 된다.
"""

from __future__ import annotations

import datetime as dt


def is_over(retreat, today: dt.date) -> bool:
    """폐회일(closeDate)이 오늘보다 이르거나 보관된 회차면 끝난 것이다.

    폐회일 **당일은 아직 진행 중**이다 — 결산 홈으로 바뀌는 것은 폐회일
    다음 날부터다 (4-15).

    폐회일이 비어 있으면 개회일로 물러선다 — 4-10(진단)·5-6(진행)이 원래
    그렇게 봐 왔다. 날짜가 개회일 하나뿐인 회차가 영영 '진행 중' 으로
    남으면, 지난 회차를 열 때마다 전부 기한 초과로 보인다.

    속성 이름이 다른 객체는 여기서 터져야 한다 — getattr 로 삼키면 모든
    회차가 조용히 '진행 중' 이 된다.
    """
    if retreat.is_archived:
        return True
    close = retreat.end_date or retreat.start_date
    return close is not None and close < today
