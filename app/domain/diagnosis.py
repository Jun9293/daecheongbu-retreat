"""진단 패널 — 이 업무가 왜 시작되지 못하는지 (CLAUDE.md 4-10).

저장하지 않고 요청할 때마다 계산한다. 상태·회의록·돌발이슈로 변수가 계속
바뀌므로 어딘가에 굳혀 두면 곧 사실과 어긋난다.

**패널 이름이 판정 결과다.** 그리고 그 이름이 총무팀의 대응을 가른다 —
진행 불가는 남을 기다리는 상태, 진행 가능인데 안 된 건 우리가 안 한 상태다.
그래서 기한이 지났어도 막는 요인이 없으면 '진행 가능' 이다.

판정에 쓰는 값은 전부 계산값이다. 저장된 status='지연' 은 담당자가 손으로
눌러야만 붙으므로 판정에 넣지 않고 근거로만 보여준다. 착수 여부도 상태가
아니라 started_at 으로 본다 — 상태로 보면 담당자가 '진행중' 으로 바꾸는
것만으로 판정이 움직여, 막는 요인이 그대로인데 총무팀이 볼 이유가 없어진다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.domain.board import (
    has_started,
    load_runs,
    lost_prerequisites,
    overdue_days_of,
    overdue_of,
)
from app.models import Retreat, TaskRun

# 판정 (CLAUDE.md 4-10). tone 은 화면의 색 계열이다.
BLOCKED = "진행 불가"
PARTIAL = "일부 진행 가능"
GO = "진행 가능"
DONE = "완료"
SCHEDULE = "일정"        # 판정하지 않는다
CLOSED = "종료된 회차"    # 판정하지 않는다

TONES = {
    BLOCKED: "block",
    PARTIAL: "part",
    GO: "go",
    DONE: "done",
    SCHEDULE: "plain",
    CLOSED: "plain",
}

CHAIN_DEPTH = 3       # 연쇄 후속을 몇 홉까지 따라갈지
CROWD_MIN = 3         # 이만큼 몰려 있어야 '집중' 이라고 말한다

# 논의 신호의 임계값 (CLAUDE.md 4-10).
# 한두 번 고쳐 쓰는 것은 흔한 일이라 그것까지 신호로 내면 소음이 된다.
FLIP_MIN = 2          # 논의가 이만큼 뒤집혔을 때만 말한다
STALE_DAYS = 21       # 마지막 논의 후 이만큼 지나야 '멈춰 있다' 고 본다


@dataclass
class Diagnosis:
    verdict: str
    summary: str
    reasons: list[dict] = field(default_factory=list)
    judged: bool = True

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "tone": TONES.get(self.verdict, "plain"),
            "summary": self.summary,
            "reasons": self.reasons,
            "judged": self.judged,
        }


def _reason(kind: str, text: str) -> dict:
    return {"kind": kind, "text": text}


def _settled(run: TaskRun, today: dt.date) -> bool:
    """이 업무가 남을 막지 않는 상태인가.

    '일정' 은 산출물 없이 날짜만 지키면 되는 것이라(4-2) 아무도 완료를 누르지
    않는다. 날짜가 지났으면 끝난 것으로 본다 — 그러지 않으면 총 리허설을 선행
    으로 둔 업무가 리허설이 지나간 뒤에도 영원히 '진행 불가' 다.
    """
    if run.status == "완료":
        return True
    if run.library.kind == "schedule":
        end = run.end_date or run.start_date
        return bool(end and end < today)
    return False


def blocking_of(run: TaskRun, by_id: dict[int, TaskRun], today: dt.date) -> list[TaskRun]:
    """이 업무를 막고 있는 선행들."""
    return [
        by_id[i]
        for i in (run.blocked_by_run_ids or [])
        if i in by_id and not _settled(by_id[i], today)
    ]


def date_settled_prerequisites(
    run: TaskRun, by_id: dict[int, TaskRun], today: dt.date
) -> list[TaskRun]:
    """완료가 아니라 **날짜로** 끝난 것으로 본 선행들.

    아무도 "끝났다" 고 누르지 않았고 시스템이 날짜만 보고 그렇게 친 것이다.
    실제로 진행됐는지 취소됐는지는 확인된 적이 없다. 막지는 않되 그 판단이
    있었다는 사실은 화면에 남긴다 — 조용히 사라지면 '진행 가능' 인데 화면에
    이유가 없다. 사라진 선행·안 이어진 링크와 같은 종류의 문제다.
    """
    return [
        by_id[i]
        for i in (run.blocked_by_run_ids or [])
        if i in by_id and by_id[i].status != "완료" and _settled(by_id[i], today)
    ]


def verdict_of(run: TaskRun, by_id: dict[int, TaskRun], today: dt.date) -> str:
    """판정만. 하위 업무의 근거도 이 함수를 써야 본 판정과 어긋나지 않는다."""
    if run.status == "완료":
        return DONE
    if run.library.kind == "schedule":
        return SCHEDULE
    blocking = blocking_of(run, by_id, today)
    if not blocking:
        return GO
    return PARTIAL if has_started(run) else BLOCKED


def _label(run: TaskRun) -> str:
    dept = run.department.name if run.department else "담당 없음"
    return f"{run.library.title} ({dept})"


def _chain(run: TaskRun, by_id: dict[int, TaskRun], blocks: dict[int, list[int]]) -> list[TaskRun]:
    """지연되면 연쇄로 밀리는 후속 업무.

    blocks 는 한 홉이다. A→B→C 에서 A 가 밀리면 C 까지 밀리므로 깊이 3까지
    따라간다. 방문한 run 을 기억해 고리에서 멈춘다. 이미 완료된 후속은
    넣지 않는다 — 끝난 일은 밀릴 것이 없다 (CLAUDE.md 4-10).
    """
    out: list[TaskRun] = []
    seen = {run.id}
    frontier = [run.id]
    for _ in range(CHAIN_DEPTH):
        nxt: list[int] = []
        for node_id in frontier:
            for follower_id in blocks.get(node_id, []):
                if follower_id in seen:
                    continue
                seen.add(follower_id)
                follower = by_id.get(follower_id)
                if follower is None:
                    continue
                nxt.append(follower_id)
                if follower.status != "완료":
                    out.append(follower)
        if not nxt:
            break
        frontier = nxt
    return out


def _crowding(run: TaskRun, runs: list[TaskRun]) -> int:
    """같은 부서에서 기간이 겹치는 미완료 업무 건수.

    완료된 것을 세면 바쁜 팀과 일을 끝낸 팀이 구분되지 않는다.
    """
    start = run.start_date
    end = run.end_date or start
    if not start or run.department_id is None:
        return 0
    count = 0
    for other in runs:
        if other.id == run.id or other.department_id != run.department_id:
            continue
        if other.status == "완료":
            continue
        o_start = other.start_date
        o_end = other.end_date or o_start
        if not o_start:
            continue
        if o_start <= end and o_end >= start:
            count += 1
    return count


def diagnose(
    db: Session,
    retreat: Retreat,
    run: TaskRun,
    *,
    today: dt.date | None = None,
    runs: list[TaskRun] | None = None,
) -> Diagnosis:
    """한 업무의 판정과 근거. 오늘 날짜를 주입할 수 있다 (테스트가 날짜에 흔들리면 안 된다)."""
    today = today or dt.date.today()
    runs = runs if runs is not None else load_runs(db, retreat)
    by_id = {r.id: r for r in runs}

    blocks: dict[int, list[int]] = {}
    for other in runs:
        for blocker_id in other.blocked_by_run_ids or []:
            if blocker_id in by_id:
                blocks.setdefault(blocker_id, []).append(other.id)

    # ── 판정하지 않는 경우 ────────────────────────────────────────────
    closing = retreat.end_date or retreat.start_date
    if getattr(retreat, "is_archived", False) or (closing and closing < today):
        return Diagnosis(
            verdict=CLOSED,
            summary=f"종료된 회차입니다. 최종 상태는 '{run.status}' 입니다.",
            reasons=[],
            judged=False,
        )

    if run.status == "완료":
        return Diagnosis(
            verdict=DONE,
            summary=_done_summary(run),
            # 완료된 업무에 "지연 시 N건이 연쇄로 밀립니다" 를 붙이면
            # 같은 패널 안에서 요약과 근거가 서로 부정한다.
            reasons=_context(db, run, runs, by_id, blocks, today, judged=False, chain=False),
        )

    if run.library.kind == "schedule":
        end = run.end_date or run.start_date
        left = (end - today).days if end else None
        if left is None:
            tail = "날짜가 정해지지 않았습니다."
        elif left > 0:
            tail = f"{left}일 남았습니다."
        elif left == 0:
            tail = "오늘입니다."
        else:
            tail = f"{-left}일 지났습니다."
        return Diagnosis(
            verdict=SCHEDULE,
            summary=f"날짜만 지키면 되는 업무입니다. {tail}",
            reasons=_context(db, run, runs, by_id, blocks, today, judged=False),
            judged=False,
        )

    # ── 판정 ─────────────────────────────────────────────────────────
    blocking = blocking_of(run, by_id, today)
    started = has_started(run)

    if not blocking:
        verdict = GO
        if overdue_of(run, today):
            summary = (
                f"막는 요인은 없습니다. 다만 마감이 {overdue_days_of(run, today)}일 지났습니다 — "
                "기다릴 것이 없으므로 우리 쪽에서 처리하면 됩니다."
            )
        else:
            summary = "막는 요인이 없습니다. 지금 진행할 수 있습니다."
    elif not started:
        verdict = BLOCKED
        summary = f"선행 업무 {len(blocking)}건이 끝나지 않아 아직 착수하지 못했습니다."
    else:
        verdict = PARTIAL
        summary = f"착수했으나 선행 {len(blocking)}건이 도착하지 않아 일부가 대기 중입니다."

    return Diagnosis(
        verdict=verdict,
        summary=summary,
        reasons=_context(db, run, runs, by_id, blocks, today, blocking=blocking),
    )


def _context(
    db: Session,
    run: TaskRun,
    runs: list[TaskRun],
    by_id: dict[int, TaskRun],
    blocks: dict[int, list[int]],
    today: dt.date,
    *,
    blocking: list[TaskRun] | None = None,
    judged: bool = True,
    chain: bool = True,
) -> list[dict]:
    """판정의 근거. 선행 미완료와 빠진 선행이 맨 위다 (CLAUDE.md 4-10)."""
    reasons: list[dict] = []

    # 1) 선행 미완료 — 남을 기다리는 이유
    for other in blocking or []:
        tail = ""
        if overdue_of(other, today):
            tail = f" · 그쪽도 기한 {overdue_days_of(other, today)}일 초과"
        reasons.append(_reason("선행", f"{_label(other)} 미완료 · {other.status}{tail}"))

    # 2) 날짜로 끝난 것으로 본 선행 — 막지 않지만 판단이 있었다는 것은 남긴다
    for other in date_settled_prerequisites(run, by_id, today):
        reasons.append(
            _reason(
                "선행",
                f"선행 '{other.library.title}' 은(는) 날짜가 지나 끝난 것으로 봤습니다 "
                "— 실제로 진행됐는지는 확인되지 않았습니다",
            )
        )

    # 3) 빠진 선행 — 막는 것으로 치지 않지만 조용히 사라지게 두지도 않는다
    for title in lost_prerequisites(run, runs):
        reasons.append(
            _reason("선행", f"선행 '{title}' 이(가) 이번 회차에서 빠졌습니다 — 확인 필요")
        )

    # 4) 상위 업무 — 표시만. 나를 포함하는 관계지 앞을 막는 관계가 아니다
    parent_library_id = run.library.parent_library_id
    if parent_library_id:
        parent = next((r for r in runs if r.library_id == parent_library_id), None)
        if parent is not None and parent.status != "완료":
            reasons.append(
                _reason("상위", f"상위 '{parent.library.title}' 이(가) 아직 {parent.status}")
            )

    # 5) 하위 업무 — 표시만
    children = [r for r in runs if r.library.parent_library_id == run.library_id]
    if children:
        unfinished = [c for c in children if c.status != "완료"]
        # 판정 규칙을 여기서 다시 쓰지 않는다 — 본 판정과 어긋난다
        blocked_kids = [c for c in unfinished if verdict_of(c, by_id, today) == BLOCKED]
        text = f"하위 {len(children)}건 중 {len(unfinished)}건 미완료"
        if blocked_kids:
            text += f" · {len(blocked_kids)}건 진행 불가"
        reasons.append(_reason("하위", text))

    # 6) 기한
    if judged or run.status != "완료":
        if overdue_of(run, today):
            reasons.append(
                _reason("기한", f"마감에서 {overdue_days_of(run, today)}일 경과")
            )
        else:
            end = run.end_date or run.start_date
            if end and (end - today).days <= 3:
                reasons.append(_reason("기한", f"마감까지 {(end - today).days}일"))
    if run.status == "지연":
        # 저장된 '지연' 은 판정에 넣지 않는다. 사람이 남긴 표시로만 보여준다.
        reasons.append(_reason("표시", "담당자가 지연으로 표시함"))

    # 7) 연쇄되는 후속
    followers = _chain(run, by_id, blocks) if chain else []
    if followers:
        names = ", ".join(_label(c) for c in followers[:4])
        more = f" 외 {len(followers) - 4}건" if len(followers) > 4 else ""
        reasons.append(
            _reason("영향", f"지연 시 {len(followers)}건이 연쇄로 밀립니다 — {names}{more}")
        )

    # 8) 부서 업무 집중도
    crowd = _crowding(run, runs)
    if crowd >= CROWD_MIN:
        dept = run.department.name if run.department else "담당 없음"
        reasons.append(_reason("집중", f"같은 기간 {dept}에 미완료 업무 {crowd}건이 몰려 있습니다"))

    # 9) 논의 기록에서 오는 신호 — 문장을 읽지 않고 세기만 한다
    reasons.extend(discussion_signals(run, today))

    return reasons


def _done_summary(run: TaskRun) -> str:
    """완료 요약. end_date 는 계획된 마감이지 실제로 끝난 날이 아니다."""
    planned = run.end_date or run.start_date
    actual = run.completed_at
    if actual is None:
        # completed_at 이 없던 시절의 기록. '기준' 이라고 단정하지 않는다.
        when = f"{planned.month}/{planned.day} 마감" if planned else "날짜 없이"
        return f"{when}으로 완료 처리되었습니다. 후속 업무를 막고 있지 않습니다."
    late = (actual - planned).days if planned else 0
    tail = f" (예정보다 {late}일 늦게 완료)" if late > 0 else ""
    return f"{actual.month}/{actual.day}에 완료되었습니다{tail}. 후속 업무를 막고 있지 않습니다."


def discussion_signals(run: TaskRun, today: dt.date) -> list[dict]:
    """논의 기록에서 나오는 신호 — 문장을 읽지 않고 세기만 한다.

    CLAUDE.md 4-10 이 '논의 맥락' 을 통째로 후속으로 미뤄 두었지만, 절반은
    지금 데이터 모델만으로 계산된다. 그 절반이 여기다. 문장을 실제로 읽는
    절반만 LLM 으로 남는다.

    셋 다 **판정을 바꾸지 않는다.** 근거로만 나간다.
    """
    entries = list(run.discussions or [])
    if not entries:
        return []

    out: list[dict] = []
    mine = [e for e in entries if e.carried_from_run_id is None]
    carried = [e for e in entries if e.carried_from_run_id is not None]

    # 번복 — 결정이 여러 번 뒤집혔다면 아직 정해지지 않은 것이다
    flips = sum(1 for e in entries if e.supersedes_entry_id is not None)
    if flips >= FLIP_MIN:
        out.append(_reason("논의", f"논의가 {flips}번 뒤집혔습니다 — 아직 정해지지 않았을 수 있습니다"))

    # 멈춘 기간 — '진행 가능' 인데 방치된 것과 '진행 불가' 는 대응이 다르다.
    # 그 둘을 가르는 것이 이 신호다.
    #
    # authored_at 은 nullable 이고, 지난 회차 논의를 옮길 때 None 도 그대로
    # 따라온다. 날짜가 없는 것은 "언제인지 모른다" 는 뜻이므로 세지 않는다 —
    # 섞어서 max 를 부르면 date 와 None 을 비교하다 패널 전체가 죽는다.
    dated = [e.authored_at for e in mine if e.authored_at is not None]
    if dated and run.status != "완료":
        idle = (today - max(dated)).days
        if idle >= STALE_DAYS:
            out.append(_reason("논의", f"마지막 논의 후 {idle}일 지났습니다"))

    # 이번 회차 기록이 아직 없다
    if carried and not mine:
        out.append(_reason("논의", "지난 회차 논의만 있고 이번 회차 기록은 아직 없습니다"))

    return out
