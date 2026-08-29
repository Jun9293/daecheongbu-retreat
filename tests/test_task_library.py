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
    assert lib.classify(bits).label == expected


def test_a_single_round_does_not_pretend_to_be_three():
    """한 회차 기록으로 "최근 3회 모두 실행"이라고 말할 수는 없다."""
    done = lib.classify([True])
    skipped = lib.classify([False])
    assert done.label == "지난 회차 실행"
    assert skipped.label == "지난 회차 미실행"
    assert done.required is True and done.default_on is True
    assert skipped.required is False and skipped.default_on is False


def test_two_rounds_say_two():
    assert lib.classify([True, True]).label == "2회 모두 실행"
    assert lib.classify([True, False]).label == "2회 중 1회"
    assert lib.classify([False, False]).label == "2회 모두 미실행"
    assert lib.classify([True, True]).required is True
    assert lib.classify([True, False]).required is False


def test_no_history_at_all():
    verdict = lib.classify([])
    assert verdict.label == lib.NO_HISTORY
    assert verdict.required is False       # 이력만으로는 경고할 수 없다
    assert verdict.default_on is True


def test_every_verdict_explains_its_basis():
    """근거 없는 분류는 신뢰를 잃는다."""
    for bits in ([], [True], [False], [True, True], [True, False, True]):
        assert lib.classify(bits).basis


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
    assert rows["차량 신청"]["verdict"]["label"] == lib.MUST
    assert rows["네컷 프레임"]["verdict"]["label"] == lib.RECOMMENDED
    assert rows["야외 체육대회"]["verdict"]["label"] == lib.LOW
    # 빠지면 경고할 대상은 '전 회차에서 빠짐없이 한 것'뿐이다
    assert rows["차량 신청"]["required"] is True
    assert rows["네컷 프레임"]["required"] is False


def test_history_depth_counts_the_rounds_behind_the_classification(db):
    assert lib.history_depth(db) == 0
    make_retreat(db, "1회차", dt.date(2026, 8, 21))
    db.commit()
    assert lib.history_depth(db) == 1
    for i in range(3):
        make_retreat(db, f"추가{i}", dt.date(2027 + i, 8, 21))
    db.commit()
    assert lib.history_depth(db) == 3      # 최근 3회차까지만 본다


def test_manual_required_flag_works_without_any_history(db):
    """이력이 없어도 구멍 방지 경고가 작동해야 한다."""
    marked = make_library(db, "결산 보고서 본부 제출")
    marked.always_required = True
    make_library(db, "야외 체육대회")
    db.commit()

    rows = {r["title"]: r for r in lib.catalog(db, open_date=dt.date(2027, 1, 15))}
    assert rows["결산 보고서 본부 제출"]["verdict"]["label"] == lib.NO_HISTORY
    assert rows["결산 보고서 본부 제출"]["always_required"] is True
    assert rows["결산 보고서 본부 제출"]["required"] is True     # 수동 지정만으로 경고 대상
    assert rows["야외 체육대회"]["required"] is False


def test_manual_and_automatic_required_are_combined(db):
    retreat = make_retreat(db, "직전", dt.date(2026, 8, 21))
    auto = make_library(db, "차량 신청")
    manual = make_library(db, "수련회 티셔츠 제작")
    manual.always_required = True
    run(db, retreat, auto, included=True)
    run(db, retreat, manual, included=False)   # 지난 회차엔 하지 않았다
    db.commit()

    rows = {r["title"]: r for r in lib.catalog(db, open_date=dt.date(2027, 1, 15))}
    assert rows["차량 신청"]["required"] is True          # 이력 근거
    assert rows["수련회 티셔츠 제작"]["required"] is True  # 수동 지정 근거
    assert rows["수련회 티셔츠 제작"]["verdict"]["label"] == "지난 회차 미실행"


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


def test_mobile_groups_sort_departments_inside_each_week(db):
    """같은 주 안에서는 부서 정렬 순서를 따른다 (D-주차 → 부서)."""
    retreat = make_retreat(db, "회차", dt.date(2026, 8, 21))   # chongmuM=0, sketch=1
    late = make_library(db, "포스터 제작", dept="sketch", d_week=13, span=0)
    early = make_library(db, "봉사팀 개별 미팅", dept="chongmuM", d_week=13, span=0)
    for library in (late, early):                              # 일부러 역순으로 넣는다
        row = run(db, retreat, library)
        row.start_date = row.end_date = dt.date(2026, 5, 24)
    db.commit()

    groups = board_view.build(db, retreat)["mobile_groups"]
    assert len(groups) == 1
    assert [r["department_name"] for r in groups[0]["rows"]] == ["chongmuM", "sketch"]


def test_catalog_carries_sub_tasks_so_you_can_see_what_comes_along(db):
    """고르는 단위는 상위지만, 무엇이 딸려 오는지 보이지 않으면 고를 수가 없다."""
    retreat = make_retreat(db, "직전", dt.date(2026, 8, 21))
    main = make_library(db, "객원 모집", dept="chongmuM", d_week=13, span=21)
    make_library(db, "객원 모집 마감", dept="chongmuM", d_week=10, span=0, parent=main)
    make_library(db, "객원 모집 시작", dept="chongmuM", d_week=13, span=0, parent=main)
    run(db, retreat, main)
    db.commit()

    row = lib.catalog(db, open_date=dt.date(2027, 1, 15))[0]
    assert row["sub_count"] == 2
    # 하위도 진행 순서대로 — 시작이 이른 것이 먼저
    assert [c["title"] for c in row["children"]] == ["객원 모집 시작", "객원 모집 마감"]
    assert row["children"][0]["start_date"] == dt.date(2026, 10, 18)   # D-13주
    assert row["children"][1]["start_date"] == dt.date(2026, 11, 8)    # D-10주


def test_catalog_is_ordered_by_progress_not_insertion(db):
    """진행 순서로 읽히려면 등록 순서가 아니라 시작일 순이어야 한다."""
    make_retreat(db, "직전", dt.date(2026, 8, 21))
    make_library(db, "늦게 시작", d_week=2, span=0)
    make_library(db, "일찍 시작", d_week=13, span=0)
    make_library(db, "중간", d_week=7, span=0)
    db.commit()

    rows = lib.catalog(db, open_date=dt.date(2027, 1, 15))
    assert [r["title"] for r in rows] == ["일찍 시작", "중간", "늦게 시작"]


def test_schedules_stay_separable_from_main_tasks(db):
    """일정은 논의 없이 날짜만 지키면 되는 별도 업무다 — 섞이면 안 된다."""
    make_retreat(db, "직전", dt.date(2026, 8, 21))
    main = make_library(db, "집회 운영 준비", d_week=6, span=27)
    make_library(db, "큐시트 제작", d_week=6, span=12, parent=main)
    schedule = make_library(db, "수련회 기도회", d_week=1, span=0)
    schedule.kind = "schedule"
    db.commit()

    rows = {r["title"]: r for r in lib.catalog(db, open_date=dt.date(2027, 1, 15))}
    assert rows["집회 운영 준비"]["kind"] == "main"
    assert rows["집회 운영 준비"]["sub_count"] == 1
    assert rows["수련회 기도회"]["kind"] == "schedule"
    assert rows["수련회 기도회"]["children"] == []
    assert "큐시트 제작" not in rows          # 하위는 상위 안에만 들어간다
