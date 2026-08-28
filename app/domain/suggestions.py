"""Claude 제안 — 라이브러리에 없는 업무를 근거와 함께 제안한다 (CLAUDE.md 6-3).

**근거 없는 제안은 하지 않는다.** 모든 제안은 아래 둘 중 하나에서 나온다.

1. 지난 회차에서 실제로 문제가 됐던 것 — 지연 기록과 논의 내역에서 도출
2. 이번 회차의 조건이 달라서 필요한 것 — 계절·개회월이 복제 원본과 다를 때

2번이 특히 중요하다. 복제만 하면 없는 항목은 빠졌다는 사실조차 모른다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Retreat, TaskLibrary, TaskRun

MAX_GENERIC = 3  # 이력에서 자동 생성하는 일반 제안 수 제한

# 지난 회차의 특정 업무가 지연됐을 때만 뜨는 제안.
# 어떤 업무 때문에 나온 제안인지가 근거 문장에 남는다.
DELAY_TEMPLATES: dict[str, dict] = {
    "홍보영상 (롱폼2 참교육)": {
        "title": "영상 출연자 섭외·일정 확정",
        "department_key": "hebron",
        "d_week": 8,
        "rationale": (
            "지난 회차 「홍보영상 (롱폼2 참교육)」이 출연자 일정 문제로 촬영되지 못했고, "
            "대체 일정도 잡히지 않은 채 끝났습니다. 촬영 전 섭외를 별도 업무로 떼어내면 "
            "같은 지연을 막을 수 있습니다."
        ),
    },
    "수련회장 계약내용 최종 조정·확인": {
        "title": "수련회장 계약 1차 체결",
        "department_key": "chongmuM",
        "d_week": 6,
        "rationale": (
            "지난 회차에는 계약 확인이 D-1주 한 번뿐이었고, 담당자 부재로 불발되어 "
            "개회 직전까지 미확정으로 남았습니다. 확인을 두 단계로 나눠 앞당기는 것을 제안합니다."
        ),
    },
}

# 이미 정해진 내용이 뒤집힌 논의 기록이 있을 때 뜨는 제안
SUPERSEDE_TEMPLATES: dict[str, dict] = {
    "명찰디자인 완료": {
        "title": "디자인 발주 사양 확정",
        "department_key": "sketch",
        "d_week": 7,
        "rationale": (
            "지난 회차 명찰 사이즈가 스트랩 재고 문제로 90×130에서 100×140으로 뒤늦게 "
            "변경됐습니다. 발주 전에 사양을 확정하는 단계가 없었습니다."
        ),
    },
}

WINTER_MONTHS = (12, 1, 2)
SUMMER_MONTHS = (6, 7, 8, 9)


def _season(date: dt.date | None) -> str | None:
    if date is None:
        return None
    if date.month in WINTER_MONTHS:
        return "겨울"
    if date.month in SUMMER_MONTHS:
        return "여름"
    return None


def generate(
    db: Session, *, open_date: dt.date, base_retreat: Retreat | None
) -> list[dict]:
    """이번 회차에 제안할 업무 목록. 각 항목에 근거(rationale)가 반드시 붙는다."""
    existing = {
        row.title
        for row in db.scalars(select(TaskLibrary).where(TaskLibrary.archived_at.is_(None)))
    }
    out: list[dict] = []

    def push(item: dict, source: str) -> None:
        if item["title"] in existing or any(o["title"] == item["title"] for o in out):
            return
        out.append({**item, "source": source})

    # ── 1. 지난 회차에서 실제로 문제가 됐던 것 ─────────────────────────
    generic = 0
    if base_retreat is not None:
        runs = list(
            db.scalars(
                select(TaskRun).where(
                    TaskRun.retreat_id == base_retreat.id, TaskRun.included
                )
            )
        )
        for run in sorted(runs, key=lambda r: r.start_date or dt.date.min):
            title = run.library.title
            reversed_decision = any(
                entry.supersedes_entry_id is not None for entry in run.discussions
            )
            if run.status == "지연" and title in DELAY_TEMPLATES:
                push(DELAY_TEMPLATES[title], f"지난 회차 「{title}」 지연")
            elif reversed_decision and title in SUPERSEDE_TEMPLATES:
                push(SUPERSEDE_TEMPLATES[title], f"지난 회차 「{title}」 논의 번복")
            elif run.status == "지연" and generic < MAX_GENERIC:
                last = run.discussions[-1].body if run.discussions else None
                rationale = (
                    f"지난 회차 「{title}」이(가) 지연으로 끝났습니다."
                    + (f" 마지막 논의 기록: “{last}”" if last else "")
                    + " 착수 전에 확정해야 할 것을 앞단계로 떼어내는 것을 검토하세요."
                )
                push(
                    {
                        "title": f"{title} 선행 조건 확정",
                        "department_key": run.department.key if run.department else None,
                        "d_week": (run.d_week or 4) + 2,
                        "rationale": rationale,
                    },
                    f"지난 회차 「{title}」 지연",
                )
                generic += 1

    # ── 2. 이번 회차의 조건이 달라서 필요한 것 ─────────────────────────
    season = _season(open_date)
    base_season = _season(base_retreat.start_date if base_retreat else None)

    if season == "겨울" and base_season == "여름":
        push(
            {
                "title": "방한·난방 물품 점검",
                "department_key": "chongmu",
                "d_week": 3,
                "rationale": (
                    "이번은 겨울 회차입니다. 복제 원본인 여름 회차의 비품 목록에는 "
                    "난방·방한 관련 항목이 전혀 없습니다."
                ),
            },
            "계절 변경 (여름 → 겨울)",
        )

    if open_date.month == 1:
        push(
            {
                "title": "폭설 대비 교통 대안 계획",
                "department_key": "chongmuM",
                "d_week": 2,
                "rationale": (
                    "1월 개회입니다. 차량 신청만으로는 결항이나 도로 통제 상황에 "
                    "대응할 수 없습니다."
                ),
            },
            "1월 개회",
        )

    if not any("피드백 설문" in title or "참가자 설문" in title for title in existing):
        push(
            {
                "title": "참가자 피드백 설문 준비",
                "department_key": "chongmu",
                "d_week": 1,
                "rationale": (
                    "지난 회차에 부서별 피드백은 있었으나 참가자 대상 설문은 없었습니다. "
                    "다음 회차 기획의 근거가 됩니다."
                ),
            },
            "라이브러리에 없는 항목",
        )

    return out
