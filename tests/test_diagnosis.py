"""진단 패널 (CLAUDE.md 4-10).

수용 기준 1~13 에 하나씩 대응한다. 함수 이름 앞의 숫자가 그 번호다.

**오늘 날짜를 주입한다.** 판정이 날짜에 달려 있으므로 실행일에 따라 결과가
갈리면 테스트가 아니다.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select, text

from app import models
from app.domain import board as board_view
from app.domain import diagnosis
from tests.conftest import app_session

OPEN = dt.date(2026, 8, 21)
CLOSE = dt.date(2026, 8, 23)
TODAY = dt.date(2026, 6, 1)          # 회차 전. 종료된 회차가 아니다.


def _lib(db, title, *, key="sketch", kind="main", parent=None, d_week=10):
    row = models.TaskLibrary(
        title=title,
        kind=kind,
        parent_library_id=parent,
        default_department_key=key,
        related_department_keys=[],
        related_library_ids=[],
        prerequisite_library_ids=[],
        date_anchor="week",
        default_d_week=d_week,
        default_offset_days=0,
        default_span_days=0,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def board(admin_client):
    """미래 회차 하나. 업무는 각 케이스가 필요한 만큼 상태를 바꿔 쓴다."""
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회 Belong", start_date=OPEN, end_date=CLOSE
        )
        db.add(retreat)
        db.flush()
        depts = {}
        for order, (key, name, color) in enumerate(
            [("sketch", "4 스케치", "#B95A83"), ("hebron", "5 헤브론", "#4A8A5C")]
        ):
            dept = models.Department(
                retreat_id=retreat.id, key=key, name=name, color_tag=color, sort_order=order
            )
            db.add(dept)
            db.flush()
            depts[key] = dept

        gear = _lib(db, "장비 확인", key="hebron", d_week=12)
        deliver = _lib(db, "장비 전달", key="hebron", d_week=8)
        poster = _lib(db, "포스터 제작", key="sketch", d_week=9)
        design = _lib(db, "시안 확정", key="sketch", kind="sub", parent=poster.id, d_week=11)
        rehearsal = _lib(db, "총 리허설", key="sketch", kind="schedule", d_week=2)

        # 장비 전달 은 장비 확인 을 기다린다
        deliver.prerequisite_library_ids = [gear.id]

        runs = {}
        dates = {
            "장비 확인": (dt.date(2026, 5, 10), dt.date(2026, 5, 17)),
            "장비 전달": (dt.date(2026, 6, 20), dt.date(2026, 6, 27)),
            "포스터 제작": (dt.date(2026, 5, 20), dt.date(2026, 5, 27)),   # 이미 지난 기한
            "시안 확정": (dt.date(2026, 5, 3), dt.date(2026, 5, 10)),
            "총 리허설": (dt.date(2026, 6, 11), dt.date(2026, 6, 11)),
        }
        for lib in (gear, deliver, poster, design, rehearsal):
            start, end = dates[lib.title]
            run = models.TaskRun(
                library_id=lib.id,
                retreat_id=retreat.id,
                included=True,
                department_id=depts[lib.default_department_key].id,
                d_week=lib.default_d_week,
                start_date=start,
                end_date=end,
                status="대기",
                blocked_by_run_ids=[],
            )
            db.add(run)
            db.flush()
            runs[lib.title] = run.id

        # 회차의 선행 링크 (create_retreat 2패스가 하는 일과 같다)
        db.get(models.TaskRun, runs["장비 전달"]).blocked_by_run_ids = [runs["장비 확인"]]
        db.commit()
        return {
            "retreat_id": retreat.id,
            "runs": runs,
            "libs": {"gear": gear.id, "deliver": deliver.id, "poster": poster.id},
        }


def _judge(run_title, board, *, today=TODAY):
    with app_session() as db:
        retreat = db.get(models.Retreat, board["retreat_id"])
        run = db.get(models.TaskRun, board["runs"][run_title])
        return diagnosis.diagnose(db, retreat, run, today=today)


def _set(run_title, board, **fields):
    with app_session() as db:
        run = db.get(models.TaskRun, board["runs"][run_title])
        for key, value in fields.items():
            setattr(run, key, value)
        db.commit()


def _kinds(result):
    return [r["kind"] for r in result.reasons]


def _texts(result):
    return " / ".join(r["text"] for r in result.reasons)


# ── 1 ─────────────────────────────────────────────────────────────────


def test_01_started_at_이_있고_컬럼이_자동으로_붙는다(board):
    assert hasattr(models.TaskRun, "started_at")

    from app.db import _ADDED_COLUMNS, engine

    assert ("task_runs", "started_at", "DATE") in _ADDED_COLUMNS
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(task_runs)"))}
    assert "started_at" in columns


# ── 2 ─────────────────────────────────────────────────────────────────


def test_02_대기를_벗어나면_찍히고_되돌려도_지워지지_않는다(board, admin_client):
    run_id = board["runs"]["포스터 제작"]
    with app_session() as db:
        assert db.get(models.TaskRun, run_id).started_at is None

    assert admin_client.post(
        f"/board/task/{run_id}/status", json={"status": "진행중"}
    ).status_code == 200
    with app_session() as db:
        stamped = db.get(models.TaskRun, run_id).started_at
        assert stamped is not None

    # 되돌려도 지우지 않는다 — 착수했다는 사실은 사라지지 않는다
    assert admin_client.post(
        f"/board/task/{run_id}/status", json={"status": "대기"}
    ).status_code == 200
    with app_session() as db:
        run = db.get(models.TaskRun, run_id)
        assert run.status == "대기"
        assert run.started_at == stamped


def test_02b_기존_행은_상태로_보정한다(board):
    """started_at 이 없던 시절의 행. NULL 이면서 대기가 아니면 착수한 것으로 본다."""
    with app_session() as db:
        run = db.get(models.TaskRun, board["runs"]["포스터 제작"])
        run.status = "진행중"
        run.started_at = None
        db.commit()
        assert board_view.has_started(run) is True
        run.status = "대기"
        db.commit()
        assert board_view.has_started(run) is False


# ── 3 ─────────────────────────────────────────────────────────────────


def test_03_상태를_안_눌러도_기한_초과로_잡힌다(board):
    """'지연' 은 사람이 손으로 눌러야만 붙는다. 날짜에서 계산해야 놓쳐도 알아차린다."""
    with app_session() as db:
        run = db.get(models.TaskRun, board["runs"]["포스터 제작"])
        assert run.status == "대기"                       # 아무도 누르지 않았다
        assert board_view.overdue_of(run, TODAY) is True   # 마감 5/27 < 6/1
        assert board_view.overdue_days_of(run, TODAY) == 5

        done = db.get(models.TaskRun, board["runs"]["시안 확정"])
        done.status = "완료"
        db.commit()
        assert board_view.overdue_of(done, TODAY) is False  # 끝난 것은 초과가 아니다

    result = _judge("포스터 제작", board)
    assert any("5일 경과" in r["text"] for r in result.reasons)


def test_03b_저장된_지연은_판정이_아니라_근거로만_나간다(board):
    _set("포스터 제작", board, status="지연")
    result = _judge("포스터 제작", board)
    assert result.verdict == diagnosis.GO          # 막는 요인이 없으므로
    assert "담당자가 지연으로 표시함" in _texts(result)


# ── 4 ─────────────────────────────────────────────────────────────────


def test_04_기한이_지났어도_막는_요인이_없으면_진행_가능(board):
    result = _judge("포스터 제작", board)
    assert result.verdict == diagnosis.GO
    assert "막는 요인은 없습니다" in result.summary
    assert any("일 경과" in r["text"] for r in result.reasons)   # 근거로는 나온다


# ── 5 ─────────────────────────────────────────────────────────────────


def test_05_선행_미완료에_미착수면_진행_불가(board):
    result = _judge("장비 전달", board)
    assert result.verdict == diagnosis.BLOCKED
    assert "선행" in _kinds(result)
    assert "장비 확인" in _texts(result)


# ── 6 ─────────────────────────────────────────────────────────────────


def test_06_선행_미완료여도_착수했으면_일부_진행_가능(board):
    _set("장비 전달", board, status="진행중", started_at=dt.date(2026, 5, 30))
    result = _judge("장비 전달", board)
    assert result.verdict == diagnosis.PARTIAL


def test_06b_판정은_상태가_아니라_started_at_으로_갈린다(board):
    """상태만 바꿔서는 판정이 움직이지 않아야 한다 — 자기 신고로 판정이 바뀌면 안 된다."""
    _set("장비 전달", board, status="진행중", started_at=None)
    # 기존 행 보정 규칙이 걸리므로 착수로 본다
    assert _judge("장비 전달", board).verdict == diagnosis.PARTIAL
    # started_at 이 있고 상태를 대기로 되돌려도 착수한 것은 그대로다
    _set("장비 전달", board, status="대기", started_at=dt.date(2026, 5, 30))
    assert _judge("장비 전달", board).verdict == diagnosis.PARTIAL


# ── 7 ─────────────────────────────────────────────────────────────────


def test_07_선행이_미완료여도_본인이_완료면_완료(board):
    """완료를 맨 위에서 끊지 않으면 선행이 남은 채 끝낸 업무가 '진행 불가'로 찍힌다."""
    _set("장비 전달", board, status="완료")
    result = _judge("장비 전달", board)
    assert result.verdict == diagnosis.DONE
    assert "후속 업무를 막고 있지 않습니다" in result.summary


# ── 8 ─────────────────────────────────────────────────────────────────


def test_08_회차를_연_뒤_선행이_빠지면_근거에_뜬다(board):
    """필터가 조용히 삼키면 '진행 가능'으로 바뀐다 — 막는 요인이 없어져서가 아니라
    안 보이게 돼서다."""
    with app_session() as db:
        gone = db.get(models.TaskRun, board["runs"]["장비 확인"])
        gone.included = False           # 회차를 연 뒤 뺐다
        db.commit()

    result = _judge("장비 전달", board)
    # 막는 것으로 치지는 않는다 (이번에 안 하기로 한 것일 수 있다)
    assert result.verdict == diagnosis.GO
    # 그러나 조용히 사라지지는 않는다
    assert "이번 회차에서 빠졌습니다" in _texts(result)
    assert "장비 확인" in _texts(result)

    # 보드 meta 도 같은 것을 싣는다
    with app_session() as db:
        retreat = db.get(models.Retreat, board["retreat_id"])
        view = board_view.build(db, retreat, today=TODAY)
        row = next(
            m for m in view["meta"].values() if m["title"] == "장비 전달"
        )
        assert row["lost_prerequisites"] == ["장비 확인"]
        assert row["blocked_by_run_ids"] == []


# ── 9 ─────────────────────────────────────────────────────────────────


def test_09_일정_분류는_판정하지_않고_남은_날짜를_보여준다(board):
    result = _judge("총 리허설", board)
    assert result.verdict == diagnosis.SCHEDULE
    assert result.judged is False
    assert "날짜만 지키면 되는 업무입니다" in result.summary
    assert "10일 남았습니다" in result.summary       # 6/11 - 6/1


# ── 10 ────────────────────────────────────────────────────────────────


def test_10_종료된_회차에서는_판정하지_않는다(board):
    later = CLOSE + dt.timedelta(days=9)   # 폐회 이후
    result = _judge("장비 전달", board, today=later)
    assert result.verdict == diagnosis.CLOSED
    assert result.judged is False
    assert "종료된 회차입니다" in result.summary


def test_10b_보관된_회차도_판정하지_않는다(board):
    with app_session() as db:
        db.get(models.Retreat, board["retreat_id"]).is_archived = True
        db.commit()
    assert _judge("장비 전달", board).verdict == diagnosis.CLOSED


# ── 11 ────────────────────────────────────────────────────────────────


def test_11_연쇄_후속은_3단계까지_따라가고_완료는_빠진다(board):
    """A→B→C→D 에서 A 가 밀리면 D 까지 센다. 완료된 것은 밀릴 것이 없다."""
    with app_session() as db:
        retreat = db.get(models.Retreat, board["retreat_id"])
        runs = {}
        for i, title in enumerate(["A", "B", "C", "D", "E"]):
            lib = _lib(db, f"연쇄 {title}", key="sketch", d_week=12 - i)
            run = models.TaskRun(
                library_id=lib.id, retreat_id=retreat.id, included=True,
                d_week=lib.default_d_week, start_date=dt.date(2026, 5, 1),
                end_date=dt.date(2026, 5, 8), status="대기", blocked_by_run_ids=[],
            )
            db.add(run)
            db.flush()
            runs[title] = run.id
        db.get(models.TaskRun, runs["B"]).blocked_by_run_ids = [runs["A"]]
        db.get(models.TaskRun, runs["C"]).blocked_by_run_ids = [runs["B"]]
        db.get(models.TaskRun, runs["D"]).blocked_by_run_ids = [runs["C"]]
        db.get(models.TaskRun, runs["E"]).blocked_by_run_ids = [runs["D"]]  # 4홉 — 넘어간다
        db.get(models.TaskRun, runs["C"]).status = "완료"                   # 완료는 빠진다
        db.commit()

        a = db.get(models.TaskRun, runs["A"])
        result = diagnosis.diagnose(db, retreat, a, today=TODAY)

    chain = next(r["text"] for r in result.reasons if r["kind"] == "영향")
    assert "연쇄 B" in chain
    assert "연쇄 C" not in chain      # 완료된 후속은 넣지 않는다
    assert "연쇄 D" in chain          # 3홉까지는 따라간다
    assert "연쇄 E" not in chain      # 4홉은 넘어간다
    assert "3건" in chain or "2건" in chain


def test_11b_고리에서_멈춘다(board):
    """A→B→A 로 이어져 있어도 무한히 돌지 않는다."""
    with app_session() as db:
        retreat = db.get(models.Retreat, board["retreat_id"])
        ids = {}
        for title in ("고리 A", "고리 B"):
            lib = _lib(db, title, key="sketch")
            run = models.TaskRun(
                library_id=lib.id, retreat_id=retreat.id, included=True,
                start_date=dt.date(2026, 5, 1), end_date=dt.date(2026, 5, 8),
                status="대기", blocked_by_run_ids=[],
            )
            db.add(run)
            db.flush()
            ids[title] = run.id
        db.get(models.TaskRun, ids["고리 A"]).blocked_by_run_ids = [ids["고리 B"]]
        db.get(models.TaskRun, ids["고리 B"]).blocked_by_run_ids = [ids["고리 A"]]
        db.commit()

        result = diagnosis.diagnose(
            db, retreat, db.get(models.TaskRun, ids["고리 A"]), today=TODAY
        )
    chain = next((r["text"] for r in result.reasons if r["kind"] == "영향"), "")
    assert "1건" in chain                 # 자기 자신으로 되돌아오지 않는다


# ── 12 ────────────────────────────────────────────────────────────────


def test_12_집중도는_미완료만_센다(board):
    """완료된 것을 세면 바쁜 팀과 일을 끝낸 팀이 구분되지 않는다."""
    with app_session() as db:
        retreat = db.get(models.Retreat, board["retreat_id"])
        target = db.get(models.TaskRun, board["runs"]["포스터 제작"])
        sketch = target.department_id
        made = []
        for i in range(4):
            lib = _lib(db, f"겹치는 업무 {i}", key="sketch")
            run = models.TaskRun(
                library_id=lib.id, retreat_id=retreat.id, included=True,
                department_id=sketch,
                start_date=dt.date(2026, 5, 21), end_date=dt.date(2026, 5, 26),
                status="대기", blocked_by_run_ids=[],
            )
            db.add(run)
            db.flush()
            made.append(run.id)
        db.commit()

        runs = board_view.load_runs(db, retreat)
        # 같은 부서에서 기간이 겹치는 미완료 4건. 시안 확정(5/3~5/10)은 겹치지 않는다.
        assert diagnosis._crowding(target, runs) == 4

        for run_id in made:                             # 넷을 끝내면
            db.get(models.TaskRun, run_id).status = "완료"
        db.commit()
        runs = board_view.load_runs(db, retreat)
        assert diagnosis._crowding(target, runs) == 0   # 미완료만 센다


# ── 13 ────────────────────────────────────────────────────────────────


def test_13_상위와_하위는_근거에만_나오고_판정을_바꾸지_않는다(board):
    """상위는 나를 포함하는 관계지 앞을 막는 관계가 아니다."""
    _set("포스터 제작", board, status="대기")      # 상위는 미완료
    result = _judge("시안 확정", board)
    assert result.verdict == diagnosis.GO          # 상위가 미완료여도 막지 않는다
    assert "상위" in _kinds(result)
    assert "포스터 제작" in _texts(result)

    # 하위 상태는 상위 쪽 근거에 나온다
    parent = _judge("포스터 제작", board)
    assert "하위" in _kinds(parent)
    assert "하위 1건 중 1건 미완료" in _texts(parent)
    assert parent.verdict == diagnosis.GO          # 하위도 판정을 바꾸지 않는다


# ── 화면으로 나가는 모양 ──────────────────────────────────────────────


def test_상세_API_가_판정을_함께_싣는다(board, admin_client):
    # API 는 주입 없이 진짜 오늘을 쓴다. 폐회일이 지난 회차는 판정하지 않으므로
    # (수용 기준 10) 배선을 보려면 아직 끝나지 않은 회차여야 한다.
    with app_session() as db:
        retreat = db.get(models.Retreat, board["retreat_id"])
        retreat.start_date = dt.date.today() + dt.timedelta(days=30)
        retreat.end_date = dt.date.today() + dt.timedelta(days=33)
        db.commit()

    data = admin_client.get(f"/board/task/{board['runs']['장비 전달']}").json()
    assert data["diagnosis"]["verdict"] == diagnosis.BLOCKED
    assert data["diagnosis"]["tone"] == "block"
    assert any(r["kind"] == "선행" for r in data["diagnosis"]["reasons"])

    page = admin_client.get("/board")
    assert 'id="diag"' in page.text and 'id="dgTtl"' in page.text
