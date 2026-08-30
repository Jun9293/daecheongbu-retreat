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

    고르는 단위는 상위 업무(Main·일정)다. 하위 업무는 상위를 따라가지만,
    무엇이 딸려 오는지 보이지 않으면 고를 수가 없으므로 함께 실어 보낸다.
    진행 순서로 읽히도록 시작일 순으로 정렬한다.
    """
    history_retreats = past_retreats(db, exclude_id=exclude_retreat_id)
    recent = history_retreats[-HISTORY_WINDOW:]
    all_ids = [r.id for r in history_retreats]
    runs = _runs_by_library(db, all_ids)

    every = list(
        db.scalars(
            select(TaskLibrary)
            .where(TaskLibrary.archived_at.is_(None))
            .order_by(TaskLibrary.id)
        )
    )
    libraries = [lib for lib in every if lib.parent_library_id is None]
    children: dict[int, list[TaskLibrary]] = {}
    for row in every:
        if row.parent_library_id is not None:
            children.setdefault(row.parent_library_id, []).append(row)

    def dates_of(lib: TaskLibrary) -> tuple[dt.date, dt.date]:
        return dweek.resolve_dates(
            open_date,
            anchor=lib.date_anchor,
            d_week=lib.default_d_week,
            offset_days=lib.default_offset_days,
            span_days=lib.default_span_days,
        )

    result = []
    for lib in libraries:
        # 그 회차에 기록 자체가 없으면 미실행으로 본다
        bits = [
            bool(runs[(lib.id, r.id)].included) if (lib.id, r.id) in runs else False
            for r in recent
        ]
        verdict = classify(bits)
        start, end = dates_of(lib)
        subs = sorted(children.get(lib.id, []), key=lambda c: (dates_of(c)[0], c.id))
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
                "sub_count": len(subs),
                "children": [
                    {
                        "library_id": sub.id,
                        "title": sub.title,
                        "kind": sub.kind,
                        "d_week": sub.default_d_week,
                        "start_date": dates_of(sub)[0],
                        "end_date": dates_of(sub)[1],
                        "department_key": sub.default_department_key,
                    }
                    for sub in subs
                ],
            }
        )
    # 진행 순서 — 이른 업무부터. 같은 날이면 Main 을 일정보다 먼저.
    result.sort(key=lambda r: (r["start_date"], r["kind"] != "main", r["title"]))
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


# ---------------------------------------------------------------- 선후행 관계
#
# 관련업무(related_library_ids)와 섞지 않는다. 관련은 방향이 없고 양쪽에 서로
# 적지만, 선행은 방향이 있고 **가진 쪽에만** 적는다. 후속("나를 기다리는 업무")은
# 저장하지 않고 여기서 계산한다 — 양쪽에 적으면 한쪽만 지워졌을 때 어느 쪽이
# 맞는지 알 수 없기 때문이다. (CLAUDE.md 2장)


def prerequisites_of(lib: TaskLibrary) -> list[int]:
    """ALTER 로 붙은 컬럼은 기존 행에서 NULL 이므로 반드시 감싼다."""
    return list(lib.prerequisite_library_ids or [])


def _ancestors(lib: TaskLibrary, by_id: dict[int, TaskLibrary]) -> set[int]:
    seen: set[int] = set()
    node = by_id.get(lib.parent_library_id) if lib.parent_library_id else None
    while node is not None and node.id not in seen:
        seen.add(node.id)
        node = by_id.get(node.parent_library_id) if node.parent_library_id else None
    return seen


def _descendants(library_id: int, children: dict[int, list[TaskLibrary]]) -> set[int]:
    out: set[int] = set()
    stack = list(children.get(library_id, []))
    while stack:
        node = stack.pop()
        if node.id in out:
            continue
        out.add(node.id)
        stack.extend(children.get(node.id, []))
    return out


def validate_prerequisite(db: Session, lib: TaskLibrary, prerequisite_id: int) -> str | None:
    """지정할 수 없으면 사유를, 괜찮으면 None 을 돌려준다."""
    if prerequisite_id == lib.id:
        return "자기 자신을 선행 업무로 지정할 수 없습니다."

    target = db.get(TaskLibrary, prerequisite_id)
    if target is None:
        return "선행으로 지정할 업무를 찾을 수 없습니다."
    if target.archived_at is not None:
        return f"보관된 업무({target.title})는 선행으로 지정할 수 없습니다."

    every = list(db.scalars(select(TaskLibrary)))
    by_id = {row.id: row for row in every}
    children: dict[int, list[TaskLibrary]] = {}
    for row in every:
        if row.parent_library_id is not None:
            children.setdefault(row.parent_library_id, []).append(row)

    # 상위-하위는 포함 관계지 앞을 막는 관계가 아니다 (CLAUDE.md 4-10)
    if prerequisite_id in _ancestors(lib, by_id):
        return f"상위 업무({target.title})는 선행 조건이 아닙니다."
    if prerequisite_id in _descendants(lib.id, children):
        return f"하위 업무({target.title})는 선행 조건이 아닙니다."

    # 순환 — target 에서 선행을 거슬러 올라가 lib 에 닿으면 고리가 생긴다
    stack = [prerequisite_id]
    seen: set[int] = set()
    while stack:
        node_id = stack.pop()
        if node_id == lib.id:
            return f"{target.title} 을(를) 선행으로 두면 선후행이 고리가 됩니다."
        if node_id in seen:
            continue
        seen.add(node_id)
        node = by_id.get(node_id)
        if node is not None:
            stack.extend(prerequisites_of(node))
    return None


def set_prerequisites(db: Session, lib: TaskLibrary, ids: list[int]) -> list[int]:
    """검증을 통과한 것만 저장한다. 위반이 하나라도 있으면 ValueError."""
    before = prerequisites_of(lib)
    kept: list[int] = []
    try:
        for raw in ids:
            prerequisite_id = int(raw)
            if prerequisite_id in kept:
                continue
            # 한 번에 여러 개를 넣을 때 앞의 것까지 반영해 고리를 본다
            lib.prerequisite_library_ids = list(kept)
            problem = validate_prerequisite(db, lib, prerequisite_id)
            if problem:
                raise ValueError(problem)
            kept.append(prerequisite_id)
    except ValueError:
        lib.prerequisite_library_ids = before
        raise
    lib.prerequisite_library_ids = kept
    return kept


def dependents_map(db: Session) -> dict[int, list[int]]:
    """library_id → 그것을 선행으로 가진 업무들(후속). 저장하지 않고 계산한다."""
    out: dict[int, list[int]] = {}
    for row in db.scalars(select(TaskLibrary).where(TaskLibrary.archived_at.is_(None))):
        for prerequisite_id in prerequisites_of(row):
            out.setdefault(prerequisite_id, []).append(row.id)
    return out


def top_owner(db: Session) -> dict[int, int]:
    """library_id → 그것을 품은 최상위 업무의 id.

    마법사가 고르는 단위는 상위 업무인데 선행은 하위에도 붙으므로,
    "이 선행이 이번 회차에 들어오는가"를 물으려면 최상위로 올려야 한다.
    """
    every = {row.id: row for row in db.scalars(select(TaskLibrary))}
    out: dict[int, int] = {}
    for library_id, row in every.items():
        node, guard = row, 0
        while node.parent_library_id is not None and guard < 20:
            parent = every.get(node.parent_library_id)
            if parent is None:
                break
            node, guard = parent, guard + 1
        out[library_id] = node.id
    return out


def flat_catalog(db: Session, *, open_date: dt.date) -> list[dict]:
    """선후행을 지정하기 위한 평평한 목록.

    catalog() 는 상위만 돌려주고 하위는 children 에 중첩하는데, 선후행이 실제로
    필요한 자리는 "확인 → 확인완료 및 전달" 같은 하위 업무 사이다. 그래서
    catalog() 는 그대로 두고(마법사 3단계가 쓴다) 여기서 한 줄씩 펼친다.
    """
    every = list(
        db.scalars(
            select(TaskLibrary).where(TaskLibrary.archived_at.is_(None)).order_by(TaskLibrary.id)
        )
    )
    by_id = {row.id: row for row in every}
    children: dict[int, list[TaskLibrary]] = {}
    for row in every:
        if row.parent_library_id is not None:
            children.setdefault(row.parent_library_id, []).append(row)
    dependents = dependents_map(db)

    def dates_of(lib: TaskLibrary) -> tuple[dt.date, dt.date]:
        return dweek.resolve_dates(
            open_date,
            anchor=lib.date_anchor,
            d_week=lib.default_d_week,
            offset_days=lib.default_offset_days,
            span_days=lib.default_span_days,
        )

    def brief(library_id: int) -> dict | None:
        row = by_id.get(library_id)
        if row is None:
            return None
        return {
            "library_id": row.id,
            "title": row.title,
            "kind": row.kind,
            "d_week": row.default_d_week,
            "department_key": row.default_department_key,
        }

    rows: list[dict] = []

    def emit(lib: TaskLibrary, depth: int) -> None:
        start, end = dates_of(lib)
        rows.append(
            {
                "library_id": lib.id,
                "title": lib.title,
                "kind": lib.kind,
                "depth": depth,
                "parent_library_id": lib.parent_library_id,
                "parent_title": by_id[lib.parent_library_id].title
                if lib.parent_library_id in by_id
                else None,
                "department_key": lib.default_department_key,
                "d_week": lib.default_d_week,
                "start_date": start,
                "end_date": end,
                "prerequisites": [b for b in (brief(i) for i in prerequisites_of(lib)) if b],
                "dependents": [b for b in (brief(i) for i in dependents.get(lib.id, [])) if b],
            }
        )
        for sub in sorted(children.get(lib.id, []), key=lambda c: (dates_of(c)[0], c.id)):
            emit(sub, depth + 1)

    tops = [row for row in every if row.parent_library_id is None]
    for lib in sorted(tops, key=lambda row: (dates_of(row)[0], row.kind != "main", row.title)):
        emit(lib, 0)
    return rows


def prerequisite_proposals(db: Session, *, limit: int = 12) -> list[dict]:
    """선행 후보를 제안한다 — 근거를 함께 낸다 (CLAUDE.md 6-3).

    조건은 둘 다 만족해야 한다: 이미 관련업무로 묶여 있고, D-주차가 명확히 앞선다.
    제안일 뿐이므로 저장하지 않고, 라이브러리 행으로 만들지도 않는다
    (origin='claude_suggestion' 은 업무를 새로 만들 때 쓰는 것이지 관계에는 쓰지 않는다).
    """
    every = list(
        db.scalars(
            select(TaskLibrary).where(TaskLibrary.archived_at.is_(None)).order_by(TaskLibrary.id)
        )
    )
    by_id = {row.id: row for row in every}
    out: list[dict] = []
    for lib in every:
        if lib.default_d_week is None:
            continue
        already = set(prerequisites_of(lib))
        for related_id in lib.related_library_ids or []:
            other = by_id.get(related_id)
            if other is None or other.default_d_week is None:
                continue
            if related_id in already or other.id == lib.id:
                continue
            # D-주차는 클수록 이르다. 저쪽이 명확히 앞서야 선행 후보다.
            if other.default_d_week <= lib.default_d_week:
                continue
            if validate_prerequisite(db, lib, related_id) is not None:
                continue
            out.append(
                {
                    "library_id": lib.id,
                    "title": lib.title,
                    "prerequisite_id": other.id,
                    "prerequisite_title": other.title,
                    "rationale": f"관련업무 · D-{other.default_d_week}주 → D-{lib.default_d_week}주",
                }
            )
    out.sort(key=lambda r: (-(by_id[r["prerequisite_id"]].default_d_week or 0), r["title"]))
    return out[:limit]


def missing_prerequisites(db: Session, selected_top_ids: set[int]) -> list[dict]:
    """고른 업무가 기다려야 할 업무가 이번 목록에 없는 경우.

    링크를 만들지 않고 (업무, 빠진 선행) 목록으로 돌려준다 — 마법사 4단계 경고와
    회차 생성이 같은 판단을 쓴다.
    """
    every = list(
        db.scalars(
            select(TaskLibrary).where(TaskLibrary.archived_at.is_(None)).order_by(TaskLibrary.id)
        )
    )
    by_id = {row.id: row for row in every}
    owner = top_owner(db)
    out: list[dict] = []
    for lib in every:
        if owner.get(lib.id) not in selected_top_ids:
            continue
        for prerequisite_id in prerequisites_of(lib):
            target = by_id.get(prerequisite_id)
            if target is None:
                continue
            if owner.get(prerequisite_id) in selected_top_ids:
                continue
            out.append(
                {
                    "library_id": lib.id,
                    "title": lib.title,
                    "prerequisite_id": target.id,
                    "prerequisite_title": target.title,
                }
            )
    return out


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
    new_departments: list[dict] | None = None,
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
    known = {key for key, _, _ in source}
    for extra in new_departments or []:      # 이번 회차에 새로 생긴 부서
        if extra["key"] not in known:
            source.append((extra["key"], extra["name"], extra.get("color") or "#69726D"))
            known.add(extra["key"])
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

    # 1패스 — 실행 기록을 먼저 전부 만든다.
    # 선행 관계를 여기서 채울 수 없는 이유: 선행 업무의 run 이 아직 없어 id 를 가리킬 수 없다.
    run_by_library: dict[int, TaskRun] = {}
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
            blocked_by_run_ids=[],
        )
        db.add(run)
        db.flush()
        run_by_library[lib.id] = run

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

    # 2패스 — 라이브러리의 선행 관계를 이번 회차의 run 으로 옮긴다.
    # included 끼리만 잇는다. 보드는 included 인 run 만 싣기 때문에 미포함 run 을
    # 가리키면 화면에서 끊긴 참조가 된다. 잇지 못한 건은 링크를 만들지 않고
    # (업무, 빠진 선행) 으로 모아 두었다가 부른 쪽에 알린다.
    unmet: list[dict] = []
    for lib in libraries:
        run = run_by_library[lib.id]
        if lib.id not in included_ids:
            continue
        links: list[int] = []
        for prerequisite_id in prerequisites_of(lib):
            target = run_by_library.get(prerequisite_id)
            if target is None or prerequisite_id not in included_ids:
                unmet.append(
                    {
                        "library_id": lib.id,
                        "title": lib.title,
                        "prerequisite_id": prerequisite_id,
                        "prerequisite_title": next(
                            (row.title for row in libraries if row.id == prerequisite_id),
                            "(라이브러리에 없음)",
                        ),
                    }
                )
                continue
            links.append(target.id)
        run.blocked_by_run_ids = links

    db.commit()
    retreat.unmet_prerequisites = unmet   # 마법사 4단계가 읽는다 (저장하지 않는 부가 정보)
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
