"""업무 만들기를 한 곳으로 — domain/tasks.create_run 하나를 모든 경로가 지난다.

라이브러리+run 만들기가 두 벌이던 시절 제목 자르기 하나가 이미 갈렸다.
같은 것이 두 곳에 있으면 반드시 갈리고, 갈린 쪽을 아무도 눈치채지
못한다 — 그래서 두 경로의 **결과가 같은지**와, 한 곳만 고치면 **모든
경로가 따라오는지**를 잰다.
"""

from __future__ import annotations

import datetime as dt
import pathlib

from sqlalchemy import select

from app import models
from tests.conftest import app_session, login_as, make_user
from tests.test_stage11 import 생성자리
from tests.test_web_flows import _create_departments, _create_retreat

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = dt.date.today()
D = TODAY + dt.timedelta(days=14)


def _세팅(admin_client):
    """회차 + 키 있는 부서 둘. 키는 화면(설정)이 아직 안 붙이므로 직접 단다
    — 권한 비교의 축이 키다 (2장)."""
    retreat = _create_retreat(admin_client)
    depts = _create_departments(admin_client, ["홍보팀", "찬양팀"])
    with app_session() as db:
        for d, key in zip(depts, ["hongbo", "chanyang"]):
            db.get(models.Department, d.id).key = key
        db.commit()
    return retreat, depts


def _회의와_항목(admin_client, dept_id=None, due=None, content="현수막 시안 확정"):
    admin_client.post(
        "/meetings/create",
        data={"title": "주간 점검 회의", "meeting_date": TODAY.isoformat(),
              "attendees": "", "body": "논의", "link_retreat": "retreat"},
        follow_redirects=True,
    )
    with app_session() as db:
        meeting = db.scalars(select(models.Meeting)).first()
    res = admin_client.post(
        f"/meetings/{meeting.id}/items",
        data={"kind": "액션아이템", "content": content,
              "department_id": str(dept_id) if dept_id else "",
              "due_date": due.isoformat() if due else ""},
        follow_redirects=True,
    )
    with app_session() as db:
        item = db.scalars(
            select(models.MeetingItem).order_by(models.MeetingItem.id.desc())
        ).first()
    return meeting, item, res


def _run_of(title):
    with app_session() as db:
        return db.scalars(
            select(models.TaskRun).join(models.TaskLibrary)
            .where(models.TaskLibrary.title == title)
        ).one()


# ════════════════════════════════════════════════════════════════════
# 1-c. 두 경로가 만든 run 의 필드가 같다 — 같은 입력, 같은 결과
# ════════════════════════════════════════════════════════════════════


def test12_s01_두_경로가_같은_입력에_같은_결과를_낸다(admin_client):
    _, depts = _세팅(admin_client)
    # 경로 A — 보드의 「새로 만들기」
    r = admin_client.post("/board/add/new", json={
        "title": "무대 배너 제작", "department_key": "hongbo",
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})
    assert r.status_code == 200
    # 경로 B — 회의 항목 전환 (같은 부서 · 같은 날짜)
    _, item, _ = _회의와_항목(admin_client, depts[0].id, due=D, content="무대 배너 제작B")
    admin_client.post(f"/meetings/items/{item.id}/to-task", follow_redirects=True)

    a, b = _run_of("무대 배너 제작"), _run_of("무대 배너 제작B")
    with app_session() as db:
        la = db.get(models.TaskLibrary, a.library_id)
        lb = db.get(models.TaskLibrary, b.library_id)
        # 경로가 달라도 값이 같아야 하는 필드 전부
        assert (la.kind, la.default_department_key, la.date_anchor,
                la.default_d_week, la.default_offset_days, la.default_span_days,
                la.origin) == \
               (lb.kind, lb.default_department_key, lb.date_anchor,
                lb.default_d_week, lb.default_offset_days, lb.default_span_days,
                lb.origin)
        assert (a.department_id, a.d_week, a.start_date, a.end_date,
                a.status, a.included) == \
               (b.department_id, b.d_week, b.start_date, b.end_date,
                b.status, b.included)
        assert b.run_no == a.run_no + 1          # 같은 번호줄 (max+1)
    # 경로마다 다른 것은 출처뿐이다 — 회의에서 온 것만 회의록을 가리킨다
    assert a.source_meeting_id is None and b.source_meeting_id is not None


def test12_s02_필드를_하나_더하면_모든_경로가_따라온다(admin_client, monkeypatch):
    """create_run 한 곳을 바꾸면(여기서는 감싸서 표식을 심는다) 보드 ·
    항목 전환 · 제안 반영 세 경로가 전부 따라오는지 — 세 경로가 실제로
    같은 함수를 지난다는 증명이다 (수용 2 · 4)."""
    import app.domain.tasks as tasks_domain

    원래 = tasks_domain.create_run

    def 표식심기(*a, **k):
        lib, run = 원래(*a, **k)
        lib.suggestion_rationale = "한곳표식"
        return lib, run

    monkeypatch.setattr(tasks_domain, "create_run", 표식심기)
    _, depts = _세팅(admin_client)

    admin_client.post("/board/add/new", json={
        "title": "보드길", "department_key": "hongbo",
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})
    meeting, item, _ = _회의와_항목(admin_client, depts[0].id, content="전환길")
    admin_client.post(f"/meetings/items/{item.id}/to-task", follow_redirects=True)
    admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new", json={
        "title": "제안길", "department": "홍보팀", "parent_run_id": None})

    with app_session() as db:
        for 제목 in ("보드길", "전환길", "제안길"):
            lib = db.scalars(select(models.TaskLibrary)
                             .where(models.TaskLibrary.title == 제목)).one()
            assert lib.suggestion_rationale == "한곳표식", f"{제목} 이 한 곳을 안 지났다"


# ════════════════════════════════════════════════════════════════════
# 2. 전환 권한 — 부서가 적힌 항목은 그 부서의 축이다
# ════════════════════════════════════════════════════════════════════


def _리더클라이언트(name, phone, dept_id):
    from fastapi.testclient import TestClient

    from app.main import app

    make_user(name, phone, "dept_lead", dept_id)
    c = TestClient(app)
    # make_user 는 숫자만 저장한다 — 하이픈 그대로 넘기면 login_as 가 못
    # 찾고 부서 없는 새 계정을 만들어, 403 이 「다른 부서라서」 가 아니게 된다
    login_as(c, "".join(ch for ch in phone if ch.isdigit()), name=name)
    return c


def test12_p01_부서_적힌_항목은_다른_부서가_전환하지_못한다(admin_client):
    _, depts = _세팅(admin_client)
    _, item, _ = _회의와_항목(admin_client, depts[0].id)          # 홍보팀 항목
    남부서 = _리더클라이언트("찬양 리더", "010-7777-0001", depts[1].id)

    res = 남부서.post(f"/meetings/items/{item.id}/to-task", follow_redirects=False)
    assert res.status_code == 403                                # 막는 쪽
    with app_session() as db:
        assert db.scalars(select(models.TaskRun)).all() == []


def test12_p02_같은_키의_리더는_전환할_수_있다(admin_client):
    _, depts = _세팅(admin_client)
    _, item, _ = _회의와_항목(admin_client, depts[0].id)
    내부서 = _리더클라이언트("홍보 리더", "010-7777-0002", depts[0].id)

    res = 내부서.post(f"/meetings/items/{item.id}/to-task", follow_redirects=False)
    assert res.status_code == 303                                # 뚫리는 쪽
    with app_session() as db:
        assert len(db.scalars(select(models.TaskRun)).all()) == 1


def test12_p03_부서_없는_항목은_편집자면_된다(admin_client):
    _, depts = _세팅(admin_client)
    _, item, _ = _회의와_항목(admin_client, None)                 # 부서 없음
    남부서 = _리더클라이언트("찬양 리더", "010-7777-0003", depts[1].id)

    res = 남부서.post(f"/meetings/items/{item.id}/to-task", follow_redirects=False)
    assert res.status_code == 303
    with app_session() as db:
        assert len(db.scalars(select(models.TaskRun)).all()) == 1


def test12_p04_다른_회차의_부서_id_는_항목에_못_단다(admin_client):
    """add_item 검증 (2-c) — 다른 회차의 부서 id 가 들어오면 전환된 업무가
    엉뚱한 자리에 서거나 어디에도 안 선다. 입구에서 400."""
    _세팅(admin_client)
    with app_session() as db:
        다른회차 = models.Retreat(name="지난 회차", start_date=TODAY - dt.timedelta(days=400))
        db.add(다른회차)
        db.flush()
        남의부서 = models.Department(retreat_id=다른회차.id, name="옛 부서", sort_order=0)
        db.add(남의부서)
        db.commit()
        남의부서id = 남의부서.id
    meeting, _, _ = _회의와_항목(admin_client, None)
    res = admin_client.post(
        f"/meetings/{meeting.id}/items",
        data={"kind": "액션아이템", "content": "엉뚱한 부서", "department_id": str(남의부서id)},
        follow_redirects=False,
    )
    assert res.status_code == 400


# ════════════════════════════════════════════════════════════════════
# 3. 길 하나로 — 제안 반영이 업무를 만든다
# ════════════════════════════════════════════════════════════════════


def test12_a01_제안을_업무로_반영하면_출처가_남는다(admin_client):
    _, depts = _세팅(admin_client)
    meeting, _, _ = _회의와_항목(admin_client, None)
    res = admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new", json={
        "title": "영상 출연자 섭외", "department": "홍보팀", "parent_run_id": None})
    assert res.status_code == 200
    body = res.json()
    run = _run_of("영상 출연자 섭외")
    assert run.source_meeting_id == meeting.id
    assert body["run_id"] == run.id and body["dept_missed"] is False
    with app_session() as db:
        assert db.get(models.TaskRun, run.id).department_id == depts[0].id


def test12_a02_부서_이름을_못_맞추면_비우고_말한다(admin_client):
    _세팅(admin_client)
    meeting, _, _ = _회의와_항목(admin_client, None)
    res = admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new", json={
        "title": "방한 물품 점검", "department": "없는팀", "parent_run_id": None})
    assert res.status_code == 200
    assert res.json()["dept_missed"] is True                      # 조용히 다른 값이 되지 않는다
    assert _run_of("방한 물품 점검").department_id is None


def test12_a03_상위를_고르면_하위로_선다(admin_client):
    _, depts = _세팅(admin_client)
    admin_client.post("/board/add/new", json={
        "title": "홍보영상 제작", "department_key": "hongbo",
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})
    상위run = _run_of("홍보영상 제작")
    meeting, _, _ = _회의와_항목(admin_client, None)
    res = admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new", json={
        "title": "출연자 일정 확정", "department": None,
        "parent_run_id": 상위run.id})
    assert res.status_code == 200
    with app_session() as db:
        lib = db.scalars(select(models.TaskLibrary)
                         .where(models.TaskLibrary.title == "출연자 일정 확정")).one()
        assert lib.kind == "sub" and lib.parent_library_id == 상위run.library_id


# ════════════════════════════════════════════════════════════════════
# 수용 2. 만드는 곳은 한 곳 — grep (허용 목록 밖이 생기면 빨개진다)
# ════════════════════════════════════════════════════════════════════


def test12_g01_라이브러리와_run_을_만드는_곳이_정해진_곳뿐이다():
    """일회성 업무의 라이브러리+run 생성은 domain/tasks.create_run 하나다.
    나머지 셋은 모양이 달라 남긴 곳 — 이유는 domain/tasks.py 머리에 있다.
    주석·문자열은 걷어내고 본다 (test11 의 생성자리 — 10장)."""
    허용 = {
        ("domain/tasks.py", "TaskLibrary"),   # create_run — 만드는 곳
        ("domain/tasks.py", "TaskRun"),
        ("domain/library.py", "TaskLibrary"),  # create_retreat 의 일괄 생성
        ("domain/library.py", "TaskRun"),
        ("routers/board.py", "TaskRun"),       # add_existing — 있는 라이브러리를 run 으로
        ("routers/library.py", "TaskLibrary"),  # 라이브러리 항목만 (회차 없이)
    }
    나온것 = set()
    for p in (ROOT / "app").rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        for 이름 in ("TaskLibrary", "TaskRun"):
            if 생성자리(src, 이름):
                나온것.add((p.relative_to(ROOT / "app").as_posix(), 이름))
    assert 나온것 == 허용, f"허용 밖: {나온것 - 허용} / 사라짐: {허용 - 나온것}"
