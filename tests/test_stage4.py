"""UI 개편 단계 4 — 목록·드로어 다듬기 · 알림 통합(4-16) · 확인 요청(4-9) ·
파일 이관 · 종료 회차의 조용함(1-a) · 번호(4-14).

값을 시험에 박지 않는다 (11-3) — 문서가 말할 값 대신 값끼리 맞는지를 본다.
막는 코드에는 막히는 쪽 시험이 함께 있다.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest
from sqlalchemy import select, text

from app import models
from app.domain import board as board_domain
from app.domain import discussion, home as home_domain, suggestions, tasklist
from tests.conftest import app_session, login_as, make_user

TODAY = dt.date.today()
ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(*parts) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


# ════════════════════════════════════════════════════════════════════
# 1-a. 종료된 회차에는 지연이 없다
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def over_world(admin_client):
    """끝난 회차 + 그 안에서 기한을 넘긴 미완료 업무."""
    close = TODAY - dt.timedelta(days=10)
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회 Belong",
            start_date=close - dt.timedelta(days=2), end_date=close)
        db.add(retreat)
        db.flush()
        dept = models.Department(retreat_id=retreat.id, key="chongmuM",
                                 name="1 총무M", color_tag="#2F4858", sort_order=0)
        db.add(dept)
        db.flush()
        lib = models.TaskLibrary(title="포스터 제작", kind="main", default_d_week=5)
        db.add(lib)
        db.flush()
        run = models.TaskRun(
            library_id=lib.id, retreat_id=retreat.id, included=True,
            department_id=dept.id, d_week=5, run_no=1,
            start_date=close - dt.timedelta(days=9),
            end_date=close - dt.timedelta(days=3), status="대기")
        db.add(run)
        db.commit()
        ids = {"retreat": retreat.id, "run": run.id}
    admin_client.get(f"/board?retreat_id={ids['retreat']}")
    return ids


def test4_a01_종료_회차에서_지연이_꺼진다(over_world):
    """같은 run 을 폐회일(지연)과 폐회일+1(지연 아님)로 잰다 — 경계는
    period.is_over 와 같다(폐회일 당일까지는 진행 중)."""
    with app_session() as db:
        run = db.get(models.TaskRun, over_world["run"])
        close = run.retreat.end_date
        assert board_domain.overdue_of(run, close) is True
        assert board_domain.overdue_of(run, close + dt.timedelta(days=1)) is False
        assert board_domain.overdue_days_of(run, close + dt.timedelta(days=1)) == 0


def test4_a02_세_화면이_종료_회차에서_조용하다(over_world):
    """바·점·배지·홈 지표·목록 칩 전부 — test_c01 방식으로 세 화면을 함께 잰다."""
    with app_session() as db:
        retreat = db.get(models.Retreat, over_world["retreat"])
        run = db.get(models.TaskRun, over_world["run"])
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()

        paint = board_domain.paint_of(run, TODAY)
        assert paint["overdue"] is False
        assert paint["badge"] == {"label": "대기", "cls": "wait"}
        assert paint["bar_background"] != board_domain.BAR_LATE[0]

        board = board_domain.build(db, retreat, today=TODAY)
        assert board["late"] == 0
        row = next(r for d in board["departments"] for r in d["rows"])
        assert row["status"] == "대기"

        lst = tasklist.build(db, retreat, today=TODAY, my_key=None)
        assert lst.state_counts["late"] == 0
        assert lst.rows[0]["badge"]["cls"] == "wait"

        home = home_domain.build(db, retreat, admin, today=TODAY)
        assert home.over is True and home.overdue_count == 0


# ════════════════════════════════════════════════════════════════════
# 1-b. late_in_base — 두 기준
# ════════════════════════════════════════════════════════════════════


def test4_b01_늦음의_두_기준(db, sample_retreat):
    """폐회 시점 미완료(overdue_of@폐회일) · 마감 넘겨 끝남(completed_at > due).
    마감 전에 끝난 것은 안 잡힌다."""
    close = sample_retreat.end_date

    def run(title, *, end, status, completed=None):
        lib = models.TaskLibrary(title=title, kind="main", default_d_week=4)
        db.add(lib)
        db.flush()
        row = models.TaskRun(
            library_id=lib.id, retreat_id=sample_retreat.id, included=True,
            start_date=end - dt.timedelta(days=5), end_date=end,
            status=status, completed_at=completed)
        db.add(row)
        db.commit()
        return row

    미완 = run("폐회까지 미완", end=close - dt.timedelta(days=4), status="대기")
    늦완 = run("마감 넘겨 폐회 전 완료", end=close - dt.timedelta(days=6),
             status="완료", completed=close - dt.timedelta(days=2))
    제때 = run("마감 전에 완료", end=close - dt.timedelta(days=2),
             status="완료", completed=close - dt.timedelta(days=5))

    out = suggestions.generate(
        db, open_date=close + dt.timedelta(days=140), base_retreat=sample_retreat)
    sources = " / ".join(x["source"] for x in out)
    assert "「폐회까지 미완」 지연" in sources
    assert "「마감 넘겨 폐회 전 완료」 지연" in sources
    assert "「마감 전에 완료」" not in sources

    # **기준 회차를 보관해도 그대로 잡힌다** — overdue_of 를 쓰면 is_archived 가
    # 종료로 읽혀 지연 제안이 통째로 조용히 죽는다. 그래서 overdue_by_date 다.
    sample_retreat.is_archived = True
    db.commit()
    archived = suggestions.generate(
        db, open_date=close + dt.timedelta(days=140), base_retreat=sample_retreat)
    assert "「폐회까지 미완」 지연" in " / ".join(x["source"] for x in archived)

    # 날짜 비교는 overdue_by_date·due_of 가 쥔다 — end_date 를 직접 견주지 않는다
    src = _read("app", "domain", "suggestions.py")
    assert re.search(r"run\.end_date", src) is None
    assert "due_of" in src and "overdue_by_date" in src


# ════════════════════════════════════════════════════════════════════
# 1-c · 1-d. 번복의 걸린 곳 · 출처 정본
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def world(admin_client):
    """진행 중 회차 + 부서 둘 + 업무 몇."""
    with app_session() as db:
        retreat = models.Retreat(name="2027 여름수련회",
                                 start_date=TODAY + dt.timedelta(days=40),
                                 end_date=TODAY + dt.timedelta(days=43))
        db.add(retreat)
        db.flush()
        chongmu = models.Department(retreat_id=retreat.id, key="chongmuM",
                                    name="1 총무M", color_tag="#2F4858", sort_order=0)
        hebron = models.Department(retreat_id=retreat.id, key="hebron",
                                   name="5 헤브론", color_tag="#4A8A5C", sort_order=1)
        db.add_all([chongmu, hebron])
        db.flush()
        runs = {}

        def run(title, no, dept=chongmu):
            lib = models.TaskLibrary(title=title, kind="main", default_d_week=5)
            db.add(lib)
            db.flush()
            row = models.TaskRun(
                library_id=lib.id, retreat_id=retreat.id, included=True,
                department_id=dept.id, d_week=5, run_no=no,
                start_date=TODAY + dt.timedelta(days=no),
                end_date=TODAY + dt.timedelta(days=no + 6), status="대기")
            db.add(row)
            db.flush()
            runs[title] = row.id

        run("명찰 제작", 1)
        run("스트랩 발주", 2)
        run("헤브론 장비", 3, hebron)
        db.commit()
        ids = {"retreat": retreat.id, "chongmu": chongmu.id, "hebron": hebron.id,
               "runs": runs}
    admin_client.get(f"/board?retreat_id={ids['retreat']}")
    return ids


def test4_c01_번복이_걸린_곳을_물려받는다(admin_client, world):
    """둘에 걸린 논의를 한쪽에서 번복하면 두 화면 다 취소선이다 (4-9)."""
    a, b = world["runs"]["명찰 제작"], world["runs"]["스트랩 발주"]
    root_id = admin_client.post(f"/board/task/{a}/discussion",
                                json={"body": "사이즈 100×140"}).json()["discussions"][-1]["id"]
    with app_session() as db:
        entry = db.get(models.DiscussionEntry, root_id)
        discussion.attach(db, entry, db.get(models.TaskRun, b))
        db.commit()

    fixed = admin_client.post(
        f"/board/task/{a}/discussion",
        json={"body": "스트랩 재고 때문에 90×130 으로", "supersedes_entry_id": root_id},
    )
    assert fixed.status_code == 200
    for run_id in (a, b):
        rows = admin_client.get(f"/board/task/{run_id}").json()["discussions"]
        root = next(x for x in rows if x["id"] == root_id)
        assert root["superseded"] is True, f"run {run_id} 에서 취소선이 없다"
        assert any(x["replaces"] == root_id for x in rows), f"run {run_id} 에 후속이 없다"


def test4_d01_출처는_source_meeting_id_하나다(admin_client, world):
    """apply 본문에 「[회의록 …] 에서 옮김」 첫 줄을 더 넣지 않는다 (4-9)."""
    a = world["runs"]["명찰 제작"]
    with app_session() as db:
        meeting = models.Meeting(retreat_id=world["retreat"], title="9월 회의",
                                 meeting_date=dt.date(2027, 9, 1), body="명찰 관련 결정")
        db.add(meeting)
        db.commit()
        meeting_id = meeting.id
    entry_id = admin_client.post(f"/meetings/{meeting_id}/suggestions/apply",
                                 json={"run_ids": [a]}).json()["entry_id"]
    with app_session() as db:
        entry = db.get(models.DiscussionEntry, entry_id)
        assert entry.body == "명찰 관련 결정"
        assert "에서 옮김" not in entry.body
        assert entry.source_meeting_id == meeting_id


# ════════════════════════════════════════════════════════════════════
# 1-e ~ 1-h. 색 · 크기 · draft 행 · system actor
# ════════════════════════════════════════════════════════════════════


def test4_e01_셋째_붉은_값이_없다():
    """드로어 STATUS 의 지연 점은 CSS 토큰 값(--red-ink)과 같다 (4-0).

    **낱말만 잰다** — 다만 여기서 재는 것은 **값**이다(색·라벨). 값은
    파일에 적힌 그것이 곧 결과라, 낱말과 동작이 갈릴 자리가 없다.
    """
    js = _read("app", "static", "js", "drawer.js")
    assert "#C8442E" not in js
    assert re.search(r"'지연':\s*\{label: '지연',\s*color: '#A33F38'\}", js)
    # 판정 단어는 화면과 같은 말을 쓴다 (4-11) — 드로어만 '대기' 를 '예정' 으로
    # 불러 목록 배지와 갈라져 있었다. 상태 이름 넷은 그대로가 곧 라벨이다.
    for name in ("대기", "진행중", "완료", "지연"):
        assert re.search(rf"'{name}':\s*\{{label: '{name}'", js), f"{name} 라벨이 다른 말이다"
    for path in (ROOT / "docs" / "checks").glob("*"):
        assert "#C8442E" not in path.read_text(encoding="utf-8"), path.name
    # 아무도 안 읽던 옛 색 표도 걷었다 — 이름은 주석에 남으므로(10장) 대입만 찾는다
    assert re.search(r"^STATUS_COLORS\s*=", _read("app", "domain", "board.py"),
                     re.MULTILINE) is None


def test4_f01_걸린_업무_이름은_14px_다():
    css = _read("app", "static", "css", "retreat.css")
    block = css[css.index(".eplaces .pl{"):]
    block = block[: block.index("}")]
    assert "var(--fz-md)" in block and "--fz-xs" not in block


def test4_g01_draft_행이_같은_partial_이다():
    """손으로 쓴 trow/subrow 마크업 0곳 — 행은 taskrow 매크로에서 나온다 (6-6)."""
    src = _read("app", "templates", "draft.html")
    assert '<div class="trow' not in src
    assert '<div class="subrow' not in src
    assert 'from "partials/taskrow.html" import taskrow, subrow' in src


def test4_h01_전환_로그는_system_이다(world):
    from app import db as db_module

    run_id = world["runs"]["명찰 제작"]
    with app_session() as db:
        db.execute(text("UPDATE task_runs SET status='지연' WHERE id=:id"), {"id": run_id})
        db.commit()
    db_module._convert_stored_late()
    with app_session() as db:
        row = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.summary == "저장 지연 → 대기 (계산값으로 전환)",
            models.ActivityLog.target_id == run_id)).one()
        assert row.actor_type == "system"
        assert row.actor_name == "앱 시작"


# ════════════════════════════════════════════════════════════════════
# 2-c. 번호 — 한 번 매기고 안 바뀐다
# ════════════════════════════════════════════════════════════════════


def test4_no01_번호를_한_번만_매긴다(world):
    from app import db as db_module
    from app.domain import library as lib_domain

    with app_session() as db:
        retreat_id = world["retreat"]
        db.execute(text("UPDATE task_runs SET run_no=NULL WHERE retreat_id=:r"),
                   {"r": retreat_id})
        db.commit()

    db_module._assign_run_numbers()
    with app_session() as db:
        rows = sorted(
            db.scalars(select(models.TaskRun).where(
                models.TaskRun.retreat_id == retreat_id)),
            key=lambda r: (r.start_date is None, r.start_date or dt.date.max, r.id))
        nums = [r.run_no for r in rows]
        assert nums == list(range(1, len(rows) + 1))   # 시작일 → id 순으로 1부터
        first = {r.id: r.run_no for r in rows}

    db_module._assign_run_numbers()                     # 두 번 떠도
    with app_session() as db:
        again = {r.id: r.run_no for r in db.scalars(
            select(models.TaskRun).where(models.TaskRun.retreat_id == retreat_id))}
        assert again == first
        assert lib_domain.next_run_no(db, retreat_id) == len(first) + 1


def test4_no02_번호가_세_자리에_보인다(admin_client, world):
    run_id = world["runs"]["명찰 제작"]
    page = admin_client.get(f"/tasks?retreat_id={world['retreat']}").text
    assert '<span class="runno">1</span>' in page      # 목록 행
    board = admin_client.get(f"/board?retreat_id={world['retreat']}").text
    assert '<span class="runno">1</span>' in board     # 보드 행 제목 앞
    detail = admin_client.get(f"/board/task/{run_id}").json()
    assert detail["run_no"] == 1                       # 드로어 제목이 이 값을 그린다
    js = _read("app", "static", "js", "drawer.js")
    assert "run_no" in js and "runno" in js


# ════════════════════════════════════════════════════════════════════
# 2-d ~ 2-h. 드로어 머리 · 제목 · 관련팀 · 연결 카드 · 같은 partial
# ════════════════════════════════════════════════════════════════════


def test4_dm01_드로어_머리에_알약이_없다():
    """알약(.pill)은 홈의 D-day 배지와 이름이 부딪혀 연보라로 떴다 — 드로어
    머리는 그 클래스를 아예 안 쓴다 (4-9)."""
    js = _read("app", "static", "js", "drawer.js")
    assert 'class="pill' not in js
    assert "dmeta" in js and 'class="dl"' not in js    # 알약 마크업이 아니라 정의 표


def test4_t01_제목_편집_셋(admin_client, client, world):
    a = world["runs"]["명찰 제작"]
    saved = admin_client.post(f"/board/task/{a}/title", json={"title": "명찰 제작 (신형)"})
    assert saved.status_code == 200
    assert saved.json()["title"] == "명찰 제작 (신형)"
    with app_session() as db:
        run = db.get(models.TaskRun, a)
        assert run.library.title == "명찰 제작 (신형)"   # 라이브러리에 붙는다
        assert db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "업무_제목_변경")).first() is not None

    assert admin_client.post(f"/board/task/{a}/title",
                             json={"title": "  "}).status_code == 400   # 막는 쪽

    make_user("열람이", "01044440001", "viewer", department_id=world["chongmu"])
    login_as(client, "01044440001")
    client.get(f"/board?retreat_id={world['retreat']}")
    assert client.post(f"/board/task/{a}/title",
                       json={"title": "몰래"}).status_code == 403


def test4_r01_관련팀_저장과_행_반영(admin_client, world):
    a = world["runs"]["명찰 제작"]
    ok = admin_client.post(f"/board/task/{a}/related-departments",
                           json={"keys": ["hebron"]})
    assert ok.status_code == 200
    assert ok.json()["related_departments"] == ["5 헤브론"]
    # 모르는 키는 400 — 이름이 아니라 키로 받는다 (2장)
    assert admin_client.post(f"/board/task/{a}/related-departments",
                             json={"keys": ["없는키"]}).status_code == 400
    # 보드의 고스트 바(관련팀 행)에 반영된다
    with app_session() as db:
        retreat = db.get(models.Retreat, world["retreat"])
        board = board_domain.build(db, retreat, today=TODAY)
        hebron_block = next(d for d in board["departments"] if d["key"] == "hebron")
        assert any(r["run_id"] == a for r in hebron_block["ghost_rows"])


def test4_g02_연결_카드_셋이_순서대로_있다():
    js = _read("app", "static", "js", "drawer.js")
    at_pre = js.index("'→', '선행'")
    at_dep = js.index("'←', '후속'")
    at_rel = js.index("'↔', '관련'")
    assert at_pre < at_dep < at_rel
    assert "relcard" in js


def test4_g03_세_화면의_드로어가_같은_partial_이다(admin_client, world):
    def drawer_of(path):
        page = admin_client.get(path).text
        start = page.index('<aside class="drawer"')
        end = page.index("</aside>", start) + len("</aside>")
        return page[start:end]

    q = f"?retreat_id={world['retreat']}"
    a = drawer_of(f"/board{q}")
    b = drawer_of(f"/calendar{q}")
    c = drawer_of(f"/tasks{q}")
    assert a == b == c, "드로어가 화면마다 갈렸다"
    assert 'data-p="review"' in a                       # 확인 요청 탭 포함


# ════════════════════════════════════════════════════════════════════
# 3 · 4. 알림 통합 · 확인 요청 보내기
# ════════════════════════════════════════════════════════════════════


def test4_v01_드로어에서_보낸_요청이_세_자리에_뜬다(admin_client, client, world):
    """받는 부서의 「받은 것」 · 내 「내가 보낸 요청」 · 사이드바 배지 (4-16)."""
    from app.notifications import unread_count
    from app.routers.reviews import pending_for_user

    a = world["runs"]["명찰 제작"]
    lead_id = make_user("헤브론 리더", "01055550001", "dept_lead",
                        department_id=world["hebron"])
    # 모르는 키는 걸러서 진행하지 않고 거절한다 (5-1) — 둘 중 하나만 가면
    # 보낸 사람은 둘 다 갔다고 믿는다
    assert admin_client.post(f"/board/task/{a}/review-request",
                             json={"department_keys": ["hebron", "없는키"],
                                   "message": "x"}).status_code == 400

    sent = admin_client.post(f"/board/task/{a}/review-request",
                             json={"department_keys": ["hebron"],
                                   "message": "사이즈 확인 부탁"})
    assert sent.status_code == 200
    rows = sent.json()["reviews"]
    assert rows and rows[0]["status"] == "대기"

    with app_session() as db:
        review = db.scalars(select(models.ReviewRequest)).one()
        assert review.run_id == a                       # run 을 가리킨다
        assert review.task_id is None                   # 옛 표는 새로 쓰지 않는다
        lead = db.get(models.User, lead_id)
        retreat = db.get(models.Retreat, world["retreat"])
        assert unread_count(db, lead) > 0               # 배지 재료 1
        assert len(pending_for_user(db, lead, retreat)) == 1   # 배지 재료 2

    # 받은 것 — 사람 발신 배지 + 승인·반려 폼 (기존 /reviews/{id}/respond)
    login_as(client, "01055550001")
    client.get(f"/board?retreat_id={world['retreat']}")
    inbox = client.get("/notifications").text
    assert "확인 요청" in inbox and 'class="sender human"' in inbox
    assert f'action="/reviews/{review.id}/respond"' in inbox

    # 내가 보낸 요청 — 요청자의 탭
    sent_tab = admin_client.get("/notifications?tab=sent").text
    assert "명찰 제작" in sent_tab and "대기" in sent_tab

    # 답하면 요청자에게 결과가 가고 상태가 바뀐다 (기존 엔드포인트)
    done = client.post(f"/reviews/{review.id}/respond",
                       data={"decision": "승인", "comment": "좋습니다"},
                       follow_redirects=False)
    assert done.status_code in (302, 303)
    assert "/notifications" in done.headers["location"]
    with app_session() as db:
        assert db.get(models.ReviewRequest, review.id).status == "승인"


def test4_v02_받는_쪽도_부서를_키로_본다(admin_client, client, world):
    """받는 사람의 소속이 **지난 회차의** 부서 행을 가리켜도 — 알림·배지·답
    버튼·respond 전부 동작한다 (2장). id 비교였다면 새 회차가 열리는 순간
    넷 다 조용히 사라진다 — 4-11 이 경고한 바로 그 모양."""
    from app.notifications import unread_count
    from app.routers.reviews import pending_for_user

    a = world["runs"]["명찰 제작"]
    with app_session() as db:
        old = models.Retreat(name="지난 회차", start_date=TODAY - dt.timedelta(days=400),
                             end_date=TODAY - dt.timedelta(days=397))
        db.add(old)
        db.flush()
        old_hebron = models.Department(retreat_id=old.id, key="hebron",
                                       name="5 헤브론", color_tag="#4A8A5C", sort_order=0)
        db.add(old_hebron)
        db.commit()
        old_dept_id = old_hebron.id
    lead_id = make_user("옛 소속 리더", "01055550002", "dept_lead",
                        department_id=old_dept_id)

    sent = admin_client.post(f"/board/task/{a}/review-request",
                             json={"department_keys": ["hebron"],
                                   "message": "새 회차에서 보낸 요청"})
    assert sent.status_code == 200

    with app_session() as db:
        review = db.scalars(select(models.ReviewRequest).order_by(
            models.ReviewRequest.id.desc())).first()
        lead = db.get(models.User, lead_id)
        retreat = db.get(models.Retreat, world["retreat"])
        assert review.department_id != old_dept_id          # 요청은 이번 회차 행
        assert unread_count(db, lead) > 0                   # 알림이 갔다
        assert review.id in [r.id for r in pending_for_user(db, lead, retreat)]

    login_as(client, "01055550002")
    client.get(f"/board?retreat_id={world['retreat']}")
    page = client.get("/notifications").text
    assert f'action="/reviews/{review.id}/respond"' in page  # 답 버튼이 뜬다
    done = client.post(f"/reviews/{review.id}/respond",
                       data={"decision": "승인"}, follow_redirects=False)
    assert done.status_code in (302, 303)                    # 403 이 아니다
    with app_session() as db:
        assert db.get(models.ReviewRequest, review.id).status == "승인"


def test4_n01_모두_읽음은_이_회차만이다(admin_client, world):
    from app.notifications import mark_all_read, notify, unread_count

    with app_session() as db:
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()
        other = models.Retreat(name="다른 회차", start_date=TODAY, end_date=TODAY)
        db.add(other)
        db.commit()
        notify(db, users=[admin], retreat_id=world["retreat"], kind="테스트",
               title="이 회차", dedupe_key="a")
        notify(db, users=[admin], retreat_id=other.id, kind="테스트",
               title="다른 회차", dedupe_key="b")
    # 버튼의 N = 실제로 지울 수(이 회차) — 전 회차 합(2)이 아니다
    page = admin_client.get(f"/notifications?retreat_id={world['retreat']}").text
    # 수는 「모두 읽음」 단추가 아니라 그 줄이 말한다 (4-16) — 단추 옆
    # 괄호는 칩 줄 끝에 있던 시절의 모양이다. 재는 것은 같다:
    # **말한 수와 실제로 지우는 범위가 같은가**
    assert "안 읽은 알림 1건" in page
    with app_session() as db:
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()
        n = mark_all_read(db, admin, retreat_id=world["retreat"])
        assert n == 1                                   # 이 회차 것만
        assert unread_count(db, admin) == 1             # 다른 회차 것은 남는다


def test4_n02_저장_구조는_불변이다():
    """Review·Notification 스키마 그대로 — _ADDED_COLUMNS 외 마이그레이션 0 (4-16)."""
    from app.db import _ADDED_COLUMNS

    by_table: dict = {}
    for table, column, _ in _ADDED_COLUMNS:
        by_table.setdefault(table, set()).add(column)
    assert by_table.get("review_requests") == {"run_id"}
    assert "notifications" not in by_table
    # 표를 다시 만들거나 지우는 마이그레이션이 없다
    src = _read("app", "db.py")
    assert "DROP TABLE" not in src and "ALTER TABLE notifications" not in src


def test4_n03_옛_화면이_없고_301_이다(admin_client):
    r = admin_client.get("/reviews", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/notifications?tab=sent"
    assert not (ROOT / "app" / "templates" / "reviews.html").exists()
    assert not (ROOT / "app" / "templates" / "files.html").exists()
    # 단계 2 의 임시 한 줄(옛 알림함 배너)도 화면과 함께 사라졌다
    assert "pending-reviews-line" not in _read("app", "templates", "notifications.html")


# ════════════════════════════════════════════════════════════════════
# 5. /files 이관
# ════════════════════════════════════════════════════════════════════


def test4_fm01_작업_파일이_업무_첨부로_간다(admin_client, world, monkeypatch, capsys):
    import scripts.migrate_files as mig
    from app.config import ASSET_DIR

    a = world["runs"]["명찰 제작"]
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    with app_session() as db:
        # 옛 Task 행(제목이 run 과 같은 것)에 연결된 포스터 + 미연결 큐시트
        old_task = models.Task(retreat_id=world["retreat"], title="명찰 제작 (신형)"
                               if db.get(models.TaskRun, a).library.title == "명찰 제작 (신형)"
                               else "명찰 제작",
                               blocked_by_task_ids=[], related_department_ids=[])
        db.add(old_task)
        db.flush()
        poster = models.FileAsset(retreat_id=world["retreat"], task_id=old_task.id,
                                  department_id=world["chongmu"], title="수련회 포스터",
                                  status="승인")
        db.add(poster)
        db.flush()
        for no in (1, 2):
            stored = f"t4-poster-v{no}.png"
            (ASSET_DIR / stored).write_bytes(b"PNG" + bytes([no]))
            db.add(models.FileVersion(file_asset_id=poster.id, version_no=no,
                                      original_name=f"poster_v{no}.png",
                                      stored_name=stored, size_bytes=4))
        db.add(models.ReviewRequest(retreat_id=world["retreat"],
                                    file_asset_id=poster.id,
                                    department_id=world["hebron"],
                                    requester_name="총무"))
        db.commit()
        asset_rows = len(db.scalars(select(models.FileAsset)).all())

    # 미리보기 — 아무것도 안 바뀐다
    monkeypatch.setattr("sys.argv", ["migrate_files.py"])
    assert mig.main() == 0
    assert "미리보기" in capsys.readouterr().out
    with app_session() as db:
        assert db.scalars(select(models.TaskAttachment)).all() == []

    # --실행 — 첨부 2건 · review.run_id 채움 · 원본 행 불변
    monkeypatch.setattr("sys.argv", ["migrate_files.py", "--실행"])
    assert mig.main() == 0
    with app_session() as db:
        files = db.scalars(select(models.TaskAttachment).where(
            models.TaskAttachment.run_id == a)).all()
        assert sorted(f.original_name for f in files) == ["poster_v1.png", "poster_v2.png"]
        review = db.scalars(select(models.ReviewRequest).where(
            models.ReviewRequest.file_asset_id.isnot(None))).one()
        assert review.run_id == a
        assert len(db.scalars(select(models.FileAsset)).all()) == asset_rows  # 행 불변
        log = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "작업파일_이관")).one()
        assert "당시 상태: 승인" in log.summary
    # 첨부 탭(드로어 JSON)에 보인다
    detail = admin_client.get(f"/board/task/{a}").json()
    assert {f["name"] for f in detail["attachments"]} >= {"poster_v1.png", "poster_v2.png"}

    # 두 번 돌리면 멈춘다 — 같은 파일이 두 벌 생기면 안 된다
    assert mig.main() == 1


def test4_fm02_files_라우트가_없다(admin_client):
    assert admin_client.get("/files", follow_redirects=False).status_code == 404
    assert not (ROOT / "app" / "routers" / "files.py").exists()


# ════════════════════════════════════════════════════════════════════
# 6. 회의록 — 업무 여러 개 고르기
# ════════════════════════════════════════════════════════════════════


def test4_mm01_둘을_체크해_반영하면_링크_두_행이다(admin_client, world):
    a, b = world["runs"]["명찰 제작"], world["runs"]["스트랩 발주"]
    with app_session() as db:
        meeting = models.Meeting(retreat_id=world["retreat"], title="10월 회의",
                                 meeting_date=dt.date(2027, 10, 1), body="명찰과 스트랩")
        db.add(meeting)
        db.commit()
        meeting_id = meeting.id
    r = admin_client.post(f"/meetings/{meeting_id}/suggestions/apply",
                          json={"run_ids": [a, b]})
    entry_id = r.json()["entry_id"]
    with app_session() as db:
        links = db.scalars(select(models.DiscussionEntryRun).where(
            models.DiscussionEntryRun.entry_id == entry_id)).all()
        assert sorted(l.run_id for l in links) == sorted([a, b])
        assert len(db.scalars(select(models.DiscussionEntry).where(
            models.DiscussionEntry.id == entry_id)).all()) == 1
    for run_id, other in ((a, "스트랩 발주"), (b, "명찰 제작")):
        rows = admin_client.get(f"/board/task/{run_id}").json()["discussions"]
        got = next(x for x in rows if x["id"] == entry_id)
        assert any(p["here"] for p in got["runs"])
        assert any(p["title"].startswith(other[:3]) for p in got["runs"] if not p["here"])

    # 화면 쪽 — 제안 목록이 번호+제목 목록을 받고, 체크한 run_ids 를 보낸다
    data = admin_client.get(f"/meetings/{meeting_id}/suggestions").json()
    assert data["runs"] and all("run_id" in r and "title" in r for r in data["runs"])
    js = _read("app", "static", "js", "meeting.js")
    assert "run_ids" in js and "mt-runs" in js
