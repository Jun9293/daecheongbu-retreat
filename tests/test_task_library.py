"""업무 라이브러리 자동 분류와 회차 생성 (CLAUDE.md 6-1 ~ 6-4)."""

import datetime as dt

import pytest

from app.domain import board as board_view
from app.domain import library as lib
from app.models import Department, DiscussionEntry, Retreat, TaskLibrary, TaskRun


def make_retreat(db, name, open_date, *, keys=("chongmuM", "sketch")):
    retreat = Retreat(
        name=name, start_date=open_date, end_date=open_date + dt.timedelta(days=2)
    )
    db.add(retreat)
    db.flush()
    for order, key in enumerate(keys):
        db.add(
            Department(
                retreat_id=retreat.id, key=key, name=key, color_tag="#3B6EA5", sort_order=order
            )
        )
    db.flush()
    return retreat


def make_library(db, title, *, dept="chongmuM", d_week=13, span=7, parent=None):
    row = TaskLibrary(
        title=title,
        kind="sub" if parent else "main",
        parent_library_id=parent.id if parent else None,
        default_department_key=dept,
        related_department_keys=[],
        related_library_ids=[],
        date_anchor="week",
        default_d_week=d_week,
        default_offset_days=0,
        default_span_days=span,
    )
    db.add(row)
    db.flush()
    return row


def run(db, retreat, library, *, included=True, status="완료"):
    dept = next((d for d in retreat.departments if d.key == library.default_department_key), None)
    row = TaskRun(
        library_id=library.id,
        retreat_id=retreat.id,
        included=included,
        department_id=dept.id if dept else None,
        d_week=library.default_d_week,
        status=status,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------- 자동 분류


@pytest.mark.parametrize(
    "bits,expected",
    [
        ([True, True, True], lib.MUST),
        ([True, False, True], lib.RECOMMENDED),
        ([False, True, False], lib.RECOMMENDED),
        ([False, False, False], lib.LOW),
    ],
)
def test_classification_comes_from_the_last_three_rounds(bits, expected):
    assert lib.classify(bits, ever_run=True) == expected


def test_a_task_never_run_is_a_suggestion():
    assert lib.classify([False, False, False], ever_run=False) == lib.SUGGESTED


def test_catalog_classifies_from_real_run_records(db):
    past = [
        make_retreat(db, f"회차{i}", dt.date(2024 + i, 8, 20)) for i in range(3)
    ]
    always = make_library(db, "차량 신청")
    sometimes = make_library(db, "네컷 프레임")
    dropped = make_library(db, "야외 체육대회")
    for i, retreat in enumerate(past):
        run(db, retreat, always, included=True)
        run(db, retreat, sometimes, included=(i == 1))
        run(db, retreat, dropped, included=False)
    db.commit()

    rows = {r["title"]: r for r in lib.catalog(db, open_date=dt.date(2027, 1, 15))}
    assert rows["차량 신청"]["classification"] == lib.MUST
    assert rows["네컷 프레임"]["classification"] == lib.RECOMMENDED
    # 한 번도 실행된 적이 없으면 '후순위'가 아니라 이력 없음으로 본다
    assert rows["야외 체육대회"]["classification"] == lib.SUGGESTED


def test_catalog_only_lists_top_level_tasks(db):
    retreat = make_retreat(db, "직전", dt.date(2026, 8, 21))
    main = make_library(db, "포스터 제작")
    make_library(db, "포스터 확정", parent=main)
    run(db, retreat, main)
    db.commit()
    rows = lib.catalog(db, open_date=dt.date(2027, 1, 15))
    assert [r["title"] for r in rows] == ["포스터 제작"]
    assert rows[0]["sub_count"] == 1


# ---------------------------------------------------------------- 회차 생성


def test_create_retreat_records_excluded_tasks_instead_of_deleting(db):
    base = make_retreat(db, "2026 여름수련회", dt.date(2026, 8, 21))
    keep = make_library(db, "차량 신청")
    skip = make_library(db, "수련회 티셔츠 제작")
    run(db, base, keep)
    run(db, base, skip)
    db.commit()

    new = lib.create_retreat(
        db,
        name="2027 겨울수련회",
        open_date=dt.date(2027, 1, 15),
        close_date=dt.date(2027, 1, 17),
        meal_subsidy=8000,
        department_keys=["chongmuM", "sketch"],
        selected_library_ids={keep.id},
    )
    runs = {r.library.title: r for r in db.query(TaskRun).filter_by(retreat_id=new.id)}
    assert runs["차량 신청"].included is True
    assert runs["수련회 티셔츠 제작"].included is False  # 삭제되지 않고 기록으로 남는다
    assert lib.excluded_count(db, new) == 1


def test_create_retreat_recalculates_dates_and_resets_status(db):
    base = make_retreat(db, "2026 여름수련회", dt.date(2026, 8, 21))
    task = make_library(db, "포스터 제작", dept="sketch", d_week=13, span=21)
    run(db, base, task, status="완료")
    db.commit()

    new = lib.create_retreat(
        db,
        name="2027 겨울수련회",
        open_date=dt.date(2027, 1, 15),
        close_date=dt.date(2027, 1, 17),
        meal_subsidy=8000,
        department_keys=["chongmuM", "sketch"],
        selected_library_ids={task.id},
    )
    moved = db.query(TaskRun).filter_by(retreat_id=new.id, library_id=task.id).one()
    assert moved.start_date == dt.date(2026, 10, 18)  # D-13주 일요일
    assert moved.end_date == dt.date(2026, 11, 8)
    assert moved.status == "대기"  # 진행 상태는 넘어가지 않는다


def test_sub_tasks_follow_their_parent(db):
    base = make_retreat(db, "직전", dt.date(2026, 8, 21))
    main = make_library(db, "포스터 제작", dept="sketch")
    sub = make_library(db, "포스터 확정", dept="sketch", parent=main)
    run(db, base, main)
    run(db, base, sub)
    db.commit()

    new = lib.create_retreat(
        db,
        name="새 회차",
        open_date=dt.date(2027, 1, 15),
        close_date=dt.date(2027, 1, 17),
        meal_subsidy=8000,
        department_keys=["chongmuM", "sketch"],
        selected_library_ids=set(),  # 상위를 빼면
    )
    runs = {r.library.title: r for r in db.query(TaskRun).filter_by(retreat_id=new.id)}
    assert runs["포스터 확정"].included is False  # 하위도 함께 빠진다


def test_tasks_of_an_excluded_department_lose_their_owner_but_stay(db):
    base = make_retreat(db, "직전", dt.date(2026, 8, 21))
    task = make_library(db, "CBA커넥트 수련회 기능", dept="sketch")
    run(db, base, task)
    db.commit()

    new = lib.create_retreat(
        db,
        name="새 회차",
        open_date=dt.date(2027, 1, 15),
        close_date=dt.date(2027, 1, 17),
        meal_subsidy=8000,
        department_keys=["chongmuM"],  # 스케치 제외
        selected_library_ids={task.id},
    )
    moved = db.query(TaskRun).filter_by(retreat_id=new.id, library_id=task.id).one()
    assert moved.included is True
    assert moved.department_id is None  # 담당 없는 업무로 남는다


def test_previous_discussions_are_carried_forward(db):
    base = make_retreat(db, "직전", dt.date(2026, 8, 21))
    task = make_library(db, "명찰 디자인", dept="sketch")
    previous = run(db, base, task)
    db.add(
        DiscussionEntry(
            run_id=previous.id,
            authored_at=dt.date(2026, 7, 26),
            body="스트랩 재고 때문에 100×140mm 로 확정",
        )
    )
    db.commit()

    new = lib.create_retreat(
        db,
        name="새 회차",
        open_date=dt.date(2027, 1, 15),
        close_date=dt.date(2027, 1, 17),
        meal_subsidy=8000,
        department_keys=["chongmuM", "sketch"],
        selected_library_ids={task.id},
    )
    moved = db.query(TaskRun).filter_by(retreat_id=new.id, library_id=task.id).one()
    assert [e.body for e in moved.discussions] == ["스트랩 재고 때문에 100×140mm 로 확정"]
    assert moved.discussions[0].carried_from_run_id == previous.id


def test_reschedule_moves_every_task_when_the_opening_changes(db):
    retreat = make_retreat(db, "회차", dt.date(2027, 1, 15))
    task = make_library(db, "포스터 제작", dept="sketch", d_week=13, span=0)
    row = run(db, retreat, task, status="대기")
    row.start_date = dt.date(2026, 10, 18)
    row.end_date = dt.date(2026, 10, 18)
    db.commit()

    retreat.start_date = dt.date(2027, 1, 22)
    db.commit()
    assert lib.reschedule(db, retreat) == 1
    db.refresh(row)
    assert row.start_date == dt.date(2026, 10, 25)  # 정확히 일주일 이동
    assert row.start_date.weekday() == 6


# ---------------------------------------------------------------- 보드


def test_board_axis_switches_from_weeks_to_days(db):
    retreat = make_retreat(db, "회차", dt.date(2026, 8, 21))
    task = make_library(db, "차량 신청", d_week=2, span=6)
    row = run(db, retreat, task, status="진행중")
    row.start_date, row.end_date = dt.date(2026, 8, 9), dt.date(2026, 8, 15)
    db.commit()

    view = board_view.build(db, retreat)
    assert view["columns"] == 24  # 주 11칸 + 일 12칸 + 수련회 1칸
    assert view["shift_index"] == 12
    assert view["headers"][0]["top"] == "D-13"
    assert view["headers"][-1]["kind"] == "retreat"

    bar = view["departments"][0]["rows"][0]
    assert (bar["col_start"], bar["col_end"]) == (12, 19)


def test_related_department_gets_a_ghost_row(db):
    retreat = make_retreat(db, "회차", dt.date(2026, 8, 21))
    task = make_library(db, "홍보물 출력", d_week=8, span=0)
    task.related_department_keys = ["sketch"]
    row = run(db, retreat, task)
    row.start_date = row.end_date = dt.date(2026, 6, 28)
    db.commit()

    view = board_view.build(db, retreat)
    blocks = {b["key"]: b for b in view["departments"]}
    assert blocks["chongmuM"]["count"] == 1
    assert blocks["sketch"]["ghost_count"] == 1
    assert blocks["sketch"]["ghost_rows"][0]["ghost"] is True


def test_completed_tasks_are_grey_and_late_ones_shout():
    """완료를 눈에 띄게 하지 않는다 — 시선은 미완료로 가야 한다."""
    done_bg, _ = board_view.bar_style("완료", "#B95A83", kind="main", ghost=False)
    late_bg, late_border = board_view.bar_style("지연", "#B95A83", kind="main", ghost=False)
    assert done_bg == "#DFE3E0"
    assert late_border == "#C8442E"
    assert late_bg != done_bg
