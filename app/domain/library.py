"""업무 라이브러리 — 자동 분류와 회차 생성 (CLAUDE.md 6장).

핵심은 업무가 회차에 속하지 않는다는 것이다. 업무는 라이브러리에 계속 남고,
회차는 "그중 무엇을 실행했는지"만 기록한다. 이번에 빼도 삭제되지 않고
included=False 로 남으며, 그 기록이 다음 회차 분류의 입력값이 된다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import dweek
from app.domain.departments import DEPARTMENT_MASTER
from app.models import (
    Department,
    DiscussionEntry,
    Retreat,
    TaskLibrary,
    TaskRun,
    User,
)

# 자동 분류 (CLAUDE.md 6-2)
MUST = "필수"
RECOMMENDED = "추천"
LOW = "후순위"
SUGGESTED = "Claude 제안"
NO_HISTORY = "이력 없음"

HISTORY_WINDOW = 3  # 최근 3회차까지 본다

# 색·정렬에 쓰는 톤. 라벨은 쌓인 회차 수에 따라 달라지지만 톤은 넷뿐이다.
TONE_MUST = "must"
TONE_REC = "rec"
TONE_LOW = "low"
TONE_NEW = "new"


class Verdict:
    """자동 분류 결과.

    라벨은 근거의 두께를 그대로 드러낸다. 회차가 하나뿐인데 "필수"라고
    말하면 없는 확신을 지어내는 것이므로, 그때는 "지난 회차 실행"이라고만 한다.
    """

    __slots__ = ("label", "tone", "default_on", "required", "basis")

    def __init__(self, label, tone, *, default_on, required, basis):
        self.label = label
        self.tone = tone
        self.default_on = default_on
        self.required = required
        self.basis = basis          # 판단의 근거를 한 줄로

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "tone": self.tone,
            "default_on": self.default_on,
            "required": self.required,
            "basis": self.basis,
        }


def classify(recent_bits: list[bool]) -> Verdict:
    """쌓인 회차 수에 맞춰 분류한다.

    이력이 3회차 이상 쌓이기 전에는 필수·추천·후순위라는 말을 쓰지 않는다.
    한 회차 기록으로 "최근 3회 모두 실행"이라고 말할 수는 없기 때문이다.

        0회차 — 이력 없음
        1회차 — 지난 회차 실행 / 미실행
        2회차 — 2회 모두 실행 / 2회 중 1회 / 2회 모두 미실행
        3회차+ — 필수 / 추천 / 후순위
    """
    depth = len(recent_bits)
    done = sum(1 for bit in recent_bits if bit)

    if depth == 0:
        return Verdict(NO_HISTORY, TONE_NEW, default_on=True, required=False,
                       basis="실행 이력이 없습니다.")
    if depth == 1:
        if done:
            return Verdict("지난 회차 실행", TONE_MUST, default_on=True, required=True,
                           basis="기록된 한 회차에서 실행했습니다.")
        return Verdict("지난 회차 미실행", TONE_LOW, default_on=False, required=False,
                       basis="기록된 한 회차에서 실행하지 않았습니다.")
    if depth == 2:
        if done == 2:
            return Verdict("2회 모두 실행", TONE_MUST, default_on=True, required=True,
                           basis="기록된 2회차 모두 실행했습니다.")
        if done == 0:
            return Verdict("2회 모두 미실행", TONE_LOW, default_on=False, required=False,
                           basis="기록된 2회차 모두 실행하지 않았습니다.")
        return Verdict("2회 중 1회", TONE_REC, default_on=True, required=False,
                       basis="기록된 2회차 중 1회 실행했습니다.")

    if done >= depth:
        return Verdict(MUST, TONE_MUST, default_on=True, required=True,
                       basis=f"최근 {depth}회차 모두 실행했습니다.")
    if done == 0:
        return Verdict(LOW, TONE_LOW, default_on=False, required=False,
                       basis=f"최근 {depth}회차 모두 실행하지 않았습니다.")
    return Verdict(RECOMMENDED, TONE_REC, default_on=True, required=False,
                   basis=f"최근 {depth}회차 중 {done}회 실행했습니다.")


def history_depth(db: Session, *, exclude_retreat_id: int | None = None) -> int:
    """분류 근거가 되는 회차 수 (최대 3)."""
    return len(past_retreats(db, exclude_id=exclude_retreat_id)[-HISTORY_WINDOW:])


def past_retreats(db: Session, *, exclude_id: int | None = None) -> list[Retreat]:
    """오래된 순으로 정렬된 지난 회차 목록."""
    rows = list(db.scalars(select(Retreat).order_by(Retreat.start_date, Retreat.id)))
    return [r for r in rows if r.id != exclude_id]


def latest_retreat(db: Session, *, exclude_id: int | None = None) -> Retreat | None:
    rows = past_retreats(db, exclude_id=exclude_id)
    return rows[-1] if rows else None


def _runs_by_library(db: Session, retreat_ids: list[int]) -> dict[tuple[int, int], TaskRun]:
    if not retreat_ids:
        return {}
    rows = db.scalars(select(TaskRun).where(TaskRun.retreat_id.in_(retreat_ids)))
    return {(run.library_id, run.retreat_id): run for run in rows}


def catalog(
    db: Session,
    *,
    open_date: dt.date,
    exclude_retreat_id: int | None = None,
) -> list[dict]:
    """세팅 마법사 3단계에 뿌릴 라이브러리 목록.

    상위 업무(Main·일정)만 고른다. 하위 업무는 상위를 따라간다.
    """
    history_retreats = past_retreats(db, exclude_id=exclude_retreat_id)
    recent = history_retreats[-HISTORY_WINDOW:]
    all_ids = [r.id for r in history_retreats]
    runs = _runs_by_library(db, all_ids)

    libraries = list(
        db.scalars(
            select(TaskLibrary)
            .where(TaskLibrary.parent_library_id.is_(None))
            .where(TaskLibrary.archived_at.is_(None))
            .order_by(TaskLibrary.id)
        )
    )
    children: dict[int, int] = {}
    for row in db.scalars(
        select(TaskLibrary).where(TaskLibrary.parent_library_id.is_not(None))
    ):
        children[row.parent_library_id] = children.get(row.parent_library_id, 0) + 1

    result = []
    for lib in libraries:
        # 그 회차에 기록 자체가 없으면 미실행으로 본다
        bits = [
            bool(runs[(lib.id, r.id)].included) if (lib.id, r.id) in runs else False
            for r in recent
        ]
        verdict = classify(bits)
        start, end = dweek.resolve_dates(
            open_date,
            anchor=lib.date_anchor,
            d_week=lib.default_d_week,
            offset_days=lib.default_offset_days,
            span_days=lib.default_span_days,
        )
        result.append(
            {
                "library_id": lib.id,
                "title": lib.title,
                "kind": lib.kind,
                "department_key": lib.default_department_key,
                "d_week": lib.default_d_week,
                "start_date": start,
                "end_date": end,
                "verdict": verdict.as_dict(),
                "always_required": bool(lib.always_required),
                # 빠지면 경고할 대상인지 — 수동 지정과 자동 판정을 함께 본다
                "required": bool(lib.always_required) or verdict.required,
                "history": [
                    {
                        "retreat_id": r.id,
                        "label": _round_label(r),
                        "executed": bool(runs[(lib.id, r.id)].included)
                        if (lib.id, r.id) in runs
                        else False,
                    }
                    for r in history_retreats
                ],
                "origin": lib.origin,
                "rationale": lib.suggestion_rationale,
                "sub_count": children.get(lib.id, 0),
            }
        )
    return result


def _round_label(retreat: Retreat) -> str:
    """'2026 여름수련회 Belong' → '26여'. 이력 막대 머리글에 쓴다."""
    if retreat.start_date is None:
        return retreat.name[:3]
    year = retreat.start_date.strftime("%y")
    season = "겨" if retreat.start_date.month in (11, 12, 1, 2, 3) else "여"
    return f"{year}{season}"


def round_labels(db: Session, *, exclude_retreat_id: int | None = None) -> list[str]:
    return [_round_label(r) for r in past_retreats(db, exclude_id=exclude_retreat_id)]


# ---------------------------------------------------------------- 회차 생성


def create_retreat(
    db: Session,
    *,
    name: str,
    open_date: dt.date,
    close_date: dt.date,
    meal_subsidy: int,
    department_keys: list[str],
    selected_library_ids: set[int],
    adopted_suggestions: list[dict] | None = None,
    actor: User | None = None,
) -> Retreat:
    """마법사가 고른 내용으로 새 회차를 만든다.

    선택하지 않은 업무도 TaskRun 을 만든다 (included=False). 그래야
    "이번엔 하지 않았다"가 기록으로 남아 다음 회차 분류에 반영된다.
    """
    base = latest_retreat(db)

    retreat = Retreat(
        name=name,
        start_date=open_date,
        end_date=close_date,
        meal_subsidy_per_person=meal_subsidy,
        cloned_from_retreat_id=base.id if base else None,
    )
    db.add(retreat)
    db.flush()

    # ── 부서 ─────────────────────────────────────────────────────────
    source = (
        [(d.key, d.name, d.color_tag) for d in base.departments]
        if base and base.departments
        else [(k, n, c) for k, n, c in DEPARTMENT_MASTER]
    )
    dept_by_key: dict[str, Department] = {}
    order = 0
    for key, dept_name, color in source:
        if key not in department_keys:
            continue
        dept = Department(
            retreat_id=retreat.id, key=key, name=dept_name, color_tag=color, sort_order=order
        )
        db.add(dept)
        dept_by_key[key] = dept
        order += 1
    db.flush()

    # ── 채택한 Claude 제안을 라이브러리에 올린다 ──────────────────────
    selected = set(selected_library_ids)
    for suggestion in adopted_suggestions or []:
        lib = TaskLibrary(
            title=suggestion["title"],
            kind="main",
            default_department_key=suggestion.get("department_key"),
            related_department_keys=[],
            related_library_ids=[],
            date_anchor="week",
            default_d_week=suggestion.get("d_week") or dweek.FIRST_D_WEEK,
            default_offset_days=0,
            default_span_days=suggestion.get("span_days", 0),
            origin="claude_suggestion",
            suggestion_rationale=suggestion.get("rationale"),
        )
        db.add(lib)
        db.flush()
        selected.add(lib.id)

    # ── 실행 기록 ────────────────────────────────────────────────────
    libraries = list(
        db.scalars(
            select(TaskLibrary).where(TaskLibrary.archived_at.is_(None)).order_by(TaskLibrary.id)
        )
    )
    included_ids: set[int] = set()
    for lib in libraries:
        if lib.parent_library_id is None:
            if lib.id in selected:
                included_ids.add(lib.id)
    for lib in libraries:  # 하위 업무는 상위를 따라간다
        if lib.parent_library_id is not None and lib.parent_library_id in included_ids:
            included_ids.add(lib.id)

    base_runs = (
        {run.library_id: run for run in db.scalars(
            select(TaskRun).where(TaskRun.retreat_id == base.id)
        )}
        if base
        else {}
    )

    for lib in libraries:
        start, end = dweek.resolve_dates(
            open_date,
            anchor=lib.date_anchor,
            d_week=lib.default_d_week,
            offset_days=lib.default_offset_days,
            span_days=lib.default_span_days,
        )
        included = lib.id in included_ids
        dept = dept_by_key.get(lib.default_department_key or "")
        run = TaskRun(
            library_id=lib.id,
            retreat_id=retreat.id,
            included=included,
            department_id=dept.id if dept else None,
            d_week=lib.default_d_week,
            start_date=start if included else None,
            end_date=end if included else None,
            status="대기",  # 진행 상태는 넘어가지 않는다
        )
        db.add(run)
        db.flush()

        # 지난 회차 논의는 참고용으로 따라온다 (CLAUDE.md 6-9)
        previous = base_runs.get(lib.id)
        if included and previous is not None:
            for entry in previous.discussions:
                db.add(
                    DiscussionEntry(
                        run_id=run.id,
                        authored_at=entry.authored_at,
                        body=entry.body,
                        author_name=entry.author_name,
                        carried_from_run_id=previous.id,
                    )
                )

    db.commit()
    return retreat


def excluded_count(db: Session, retreat: Retreat) -> int:
    """이번 회차에 '미실행'으로 기록된 업무 수."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(TaskRun)
            .where(TaskRun.retreat_id == retreat.id, ~TaskRun.included)
        )
        or 0
    )


def reschedule(db: Session, retreat: Retreat) -> int:
    """개회일이 바뀌면 모든 업무 날짜를 D-주차를 유지한 채 옮긴다.

    라이브러리에는 절대 날짜가 없고 상대 위치만 있으므로, 새 개회일로
    다시 계산하기만 하면 된다 (CLAUDE.md 6-4).
    """
    if retreat.start_date is None:
        return 0
    runs = list(db.scalars(select(TaskRun).where(TaskRun.retreat_id == retreat.id)))
    moved = 0
    for run in runs:
        lib = run.library
        start, end = dweek.resolve_dates(
            retreat.start_date,
            anchor=lib.date_anchor,
            d_week=lib.default_d_week,
            offset_days=lib.default_offset_days,
            span_days=lib.default_span_days,
        )
        if not run.included:
            continue
        if run.start_date != start or run.end_date != end:
            run.start_date, run.end_date = start, end
            run.d_week = lib.default_d_week
            moved += 1
    db.commit()
    return moved
