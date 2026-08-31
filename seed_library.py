"""업무 라이브러리 · 회차 이력 시드 (CLAUDE.md 6-8).

복제할 직전 회차가 없으므로 2026 여름수련회(Belong)를 라이브러리 초기값으로
올린다. 실제 실행 이력은 이 한 회차뿐이며, 자동 분류는 쌓인 회차 수에 맞춰
표현을 바꾼다 (1회차면 "지난 회차 실행/미실행", 3회차 이상이면 필수/추천/후순위).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

import seed_library_data as L
from app.domain import dweek
from app.models import (
    Department,
    DiscussionEntry,
    Retreat,
    TaskLibrary,
    TaskRun,
    User,
)

# 부서 리더 계정 — 부서별로 보이는 화면이 다른 것을 확인하려면 필요하다.
# (전화번호는 모두 자리표시자)
EXTRA_USERS = [
    ("스케치 리더", "01000000021", "dept_lead", "sketch"),
    ("헤브론 리더", "01000000022", "dept_lead", "hebron"),
    ("코람데오 리더", "01000000023", "dept_lead", "koram"),
    ("선교사회 리더", "01000000024", "dept_lead", "seongyo"),
    ("개기자 리더", "01000000025", "dept_lead", "gaegija"),
]


def _d(iso: str) -> dt.date:
    return dt.date(*map(int, iso.split("-")))


def _make_departments(db: Session, retreat: Retreat) -> dict[str, Department]:
    by_key: dict[str, Department] = {}
    for order, (key, name, color) in enumerate(L.DEPARTMENTS):
        dept = Department(
            retreat_id=retreat.id, key=key, name=name, color_tag=color, sort_order=order
        )
        db.add(dept)
        db.flush()
        by_key[key] = dept
    return by_key


def build_library(db: Session) -> dict[str, TaskLibrary]:
    """라이브러리 업무를 만든다. 상위 → 하위 순으로 두 번 훑는다."""
    by_title: dict[str, TaskLibrary] = {}

    for (
        title,
        kind,
        parent,
        dept_key,
        anchor,
        d_week,
        offset,
        span,
        related_depts,
        note,
    ) in L.LIBRARY:
        if parent is not None:
            continue
        lib = TaskLibrary(
            title=title,
            kind=kind,
            default_department_key=dept_key,
            related_department_keys=related_depts,
            related_library_ids=[],
            date_anchor=anchor,
            default_d_week=d_week,
            default_offset_days=offset,
            default_span_days=span,
            origin="history",
            reclassification_note=note,
        )
        db.add(lib)
        db.flush()
        by_title[title] = lib

    for (
        title,
        kind,
        parent,
        dept_key,
        anchor,
        d_week,
        offset,
        span,
        related_depts,
        note,
    ) in L.LIBRARY:
        if parent is None:
            continue
        lib = TaskLibrary(
            title=title,
            kind=kind,
            parent_library_id=by_title[parent].id,
            default_department_key=dept_key,
            related_department_keys=related_depts,
            related_library_ids=[],
            date_anchor=anchor,
            default_d_week=d_week,
            default_offset_days=offset,
            default_span_days=span,
            origin="history",
            reclassification_note=note,
        )
        db.add(lib)
        db.flush()
        by_title[title] = lib

    # 라이브러리에는 있지만 2026 여름에는 실행하지 않은 업무
    for title, dept_key, d_week in L.LIBRARY_ONLY:
        lib = TaskLibrary(
            title=title,
            kind="main",
            default_department_key=dept_key,
            related_department_keys=[],
            related_library_ids=[],
            date_anchor="week",
            default_d_week=d_week,
            default_offset_days=0,
            default_span_days=0,
            origin="history",
        )
        db.add(lib)
        db.flush()
        by_title[title] = lib

    # 업무 간 연결 — 양방향으로 저장한다
    for a, b in L.RELATIONS:
        if a not in by_title or b not in by_title:
            continue
        left, right = by_title[a], by_title[b]
        left.related_library_ids = sorted({*(left.related_library_ids or []), right.id})
        right.related_library_ids = sorted({*(right.related_library_ids or []), left.id})

    db.flush()
    return by_title


def _add_runs(
    db: Session,
    retreat: Retreat,
    libraries: dict[str, TaskLibrary],
    depts: dict[str, Department],
    *,
    included_titles: set[str],
    status_by_title: dict[str, str] | None = None,
) -> dict[str, TaskRun]:
    open_date = retreat.start_date
    runs: dict[str, TaskRun] = {}
    for title, lib in libraries.items():
        included = title in included_titles
        start, end = dweek.resolve_dates(
            open_date,
            anchor=lib.date_anchor,
            d_week=lib.default_d_week,
            offset_days=lib.default_offset_days,
            span_days=lib.default_span_days,
        )
        dept = depts.get(lib.default_department_key or "")
        run = TaskRun(
            library_id=lib.id,
            retreat_id=retreat.id,
            included=included,
            department_id=dept.id if dept else None,
            d_week=lib.default_d_week,
            start_date=start if included else None,
            end_date=end if included else None,
            status=(status_by_title or {}).get(title, "완료" if included else "대기"),
        )
        db.add(run)
        db.flush()
        runs[title] = run
    return runs


def seed_current(
    db: Session, retreat: Retreat, libraries: dict[str, TaskLibrary]
) -> dict[str, TaskRun]:
    """2026 여름수련회 — 보드에 실제로 뜨는 회차."""
    depts = {d.key: d for d in retreat.departments if d.key}
    included = {title for title in L.RUN_STATUS if title in libraries}
    runs = _add_runs(
        db,
        retreat,
        libraries,
        depts,
        included_titles=included,
        status_by_title=L.RUN_STATUS,
    )

    for title, entries in L.DISCUSSIONS.items():
        run = runs.get(title)
        if run is None:
            raise ValueError(f"논의 내역의 업무를 라이브러리에서 찾을 수 없습니다: {title}")
        for date_iso, body, fix in entries:
            entry = DiscussionEntry(
                run_id=run.id,
                authored_at=_d(date_iso) if date_iso else None,
                body=body,
                author_name="총무팀",
            )
            db.add(entry)
            db.flush()
            if fix:
                follow = DiscussionEntry(
                    run_id=run.id,
                    authored_at=_d(date_iso) if date_iso else None,
                    body=fix,
                    author_name="총무팀",
                    supersedes_entry_id=entry.id,
                )
                db.add(follow)
                db.flush()
    return runs


def seed_extra_users(db: Session, depts: dict[str, Department]) -> None:
    for name, phone, role, dept_key in EXTRA_USERS:
        dept = depts.get(dept_key)
        db.add(
            User(
                name=name,
                phone_number=phone,
                role=role,
                department_id=dept.id if dept else None,
            )
        )
    db.flush()


def seed_all(db: Session, current: Retreat, *, demo: bool = False) -> None:
    """라이브러리 → 이번 회차 실행 기록.

    실제 이력은 2026 여름수련회(Belong) 한 회차뿐이다. 지어낸 과거 회차를
    넣으면 자동 분류가 없는 근거 위에서 계산되므로 만들지 않는다.
    이력이 얕은 동안에는 라이브러리의 '필수 지정'이 구멍 방지를 맡는다.
    """
    libraries = build_library(db)
    seed_current(db, current, libraries)
    if demo:
        # 부서 리더 계정은 화면을 눌러보기 위한 자리표시자다. 실제 계정은
        # 총무팀이 /admin/users 에서 만든다 (CLAUDE.md 4-12).
        seed_extra_users(db, {d.key: d for d in current.departments if d.key})
    db.commit()
