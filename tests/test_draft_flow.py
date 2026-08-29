"""회차 준비 초안 — 각 팀이 고르고 총무팀이 모아서 연다 (CLAUDE.md 6-6)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from tests.conftest import app_session, login_as

OPEN = "2027-01-15"
CLOSE = "2027-01-17"
DEPTS = ["chongmuM", "sketch"]


@pytest.fixture
def library(admin_client):
    """직전 회차 하나 + 부서별 라이브러리 업무."""
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회", start_date=dt.date(2026, 8, 21), end_date=dt.date(2026, 8, 23)
        )
        db.add(retreat)
        db.flush()
        for order, (key, name) in enumerate([("chongmuM", "1 총무M"), ("sketch", "4 스케치")]):
            db.add(models.Department(retreat_id=retreat.id, key=key, name=name,
                                     color_tag="#2F4858", sort_order=order))
        db.flush()
        depts = {d.key: d for d in retreat.departments}

        made = {}
        for title, key, week in [("차량 신청", "chongmuM", 2), ("집회 운영 준비", "chongmuM", 6),
                                 ("포스터 제작", "sketch", 13), ("명찰 디자인", "sketch", 5)]:
            lib = models.TaskLibrary(
                title=title, kind="main", default_department_key=key,
                related_department_keys=[], related_library_ids=[],
                date_anchor="week", default_d_week=week, default_offset_days=0, default_span_days=0,
            )
            db.add(lib)
            db.flush()
            db.add(models.TaskRun(library_id=lib.id, retreat_id=retreat.id, included=True,
                                  department_id=depts[key].id, d_week=week,
                                  start_date=dt.date(2026, 6, 1), end_date=dt.date(2026, 6, 1),
                                  status="완료"))
            made[title] = lib.id

        lead = models.User(name="스케치 리더", phone_number="01055556666",
                           role="dept_lead", department_id=depts["sketch"].id)
        db.add(lead)
        db.commit()
        return made


@pytest.fixture
def lead_client(library):
    from app.main import app

    client = TestClient(app)
    login_as(client, "01055556666")
    return client


def open_draft(client):
    return client.post("/setup/draft", json={
        "name": "2027 겨울수련회", "open_date": OPEN, "close_date": CLOSE,
        "meal_subsidy": 8000, "department_keys": DEPTS,
    })


# ---------------------------------------------------------------- 초안 열기


def test_총무팀만_각_팀에_요청할_수_있다(admin_client, lead_client, library):
    assert lead_client.post("/setup/draft", json={
        "name": "x", "open_date": OPEN, "close_date": CLOSE,
        "meal_subsidy": 8000, "department_keys": DEPTS,
    }).status_code == 403
    assert open_draft(admin_client).status_code == 200


def test_초안을_열면_부서마다_빈_칸이_생긴다(admin_client, library):
    open_draft(admin_client)
    with app_session() as db:
        draft = db.scalars(select(models.RetreatDraft)).one()
        assert draft.status == "수집중"
        assert {s.department_key for s in draft.submissions} == set(DEPTS)
        assert all(s.state == "대기" for s in draft.submissions)


def test_초안을_다시_열면_앞의_것은_접힌다(admin_client, library):
    open_draft(admin_client)
    open_draft(admin_client)
    with app_session() as db:
        states = [d.status for d in db.scalars(select(models.RetreatDraft).order_by(models.RetreatDraft.id))]
    assert states == ["취소", "수집중"]      # 동시에 두 개가 열려 있으면 팀이 헷갈린다


# ---------------------------------------------------------------- 팀의 선택


def test_부서_리더는_자기_칸만_채울_수_있다(admin_client, lead_client, library):
    open_draft(admin_client)

    mine = lead_client.post("/draft/sketch/save", json={
        "library_ids": [library["포스터 제작"]], "adopted": [], "submit": False})
    other = lead_client.post("/draft/chongmuM/save", json={"library_ids": [], "adopted": []})

    assert mine.status_code == 200
    assert other.status_code == 403


def test_임시저장과_제출은_상태가_다르다(admin_client, lead_client, library):
    open_draft(admin_client)

    saved = lead_client.post("/draft/sketch/save", json={
        "library_ids": [library["포스터 제작"]], "adopted": [], "submit": False}).json()
    assert saved["state"] == "작성중"
    assert saved["progress"]["submitted"] == 0

    sent = lead_client.post("/draft/sketch/save", json={
        "library_ids": [library["포스터 제작"]], "adopted": [], "note": "명찰은 이번에 뺍니다",
        "submit": True}).json()
    assert sent["state"] == "제출"
    assert sent["progress"]["submitted"] == 1
    assert sent["progress"]["all_in"] is False      # 총무M 이 아직 남았다


def test_제출한_뒤에도_고칠_수_있다(admin_client, lead_client, library):
    """총무팀이 회차를 열기 전까지는 언제든."""
    open_draft(admin_client)
    lead_client.post("/draft/sketch/save", json={
        "library_ids": [library["포스터 제작"]], "adopted": [], "submit": True})

    again = lead_client.post("/draft/sketch/save", json={
        "library_ids": [library["포스터 제작"], library["명찰 디자인"]], "adopted": [], "submit": True})

    assert again.status_code == 200
    with app_session() as db:
        sub = db.scalars(select(models.DraftSubmission)
                         .where(models.DraftSubmission.department_key == "sketch")).one()
        assert len(sub.library_ids) == 2


def test_모든_팀이_제출하면_all_in(admin_client, lead_client, library):
    open_draft(admin_client)
    lead_client.post("/draft/sketch/save", json={
        "library_ids": [library["포스터 제작"]], "adopted": [], "submit": True})
    last = admin_client.post("/draft/chongmuM/save", json={
        "library_ids": [library["차량 신청"]], "adopted": [], "submit": True}).json()

    assert last["progress"]["all_in"] is True
    assert last["progress"]["submitted"] == 2


# ---------------------------------------------------------------- 총무팀이 모아 연다


def test_마법사가_제출된_선택만_모은다(admin_client, lead_client, library):
    """작성 중인 초안은 아직 그 팀의 답이 아니다."""
    open_draft(admin_client)
    lead_client.post("/draft/sketch/save", json={
        "library_ids": [library["포스터 제작"]], "adopted": [], "submit": True})
    admin_client.post("/draft/chongmuM/save", json={
        "library_ids": [library["차량 신청"]], "adopted": [], "submit": False})   # 임시저장만

    data = admin_client.post("/setup/preview", json={
        "open_date": OPEN, "department_keys": DEPTS}).json()

    assert data["draft"]["submitted"] == 1
    assert data["draft"]["all_in"] is False
    assert data["draft"]["selected"] == [library["포스터 제작"]]
    states = {r["department_key"]: r["state"] for r in data["draft"]["rows"]}
    assert states == {"sketch": "제출", "chongmuM": "작성중"}


def test_회차를_만들면_초안이_닫힌다(admin_client, lead_client, library):
    open_draft(admin_client)
    lead_client.post("/draft/sketch/save", json={
        "library_ids": [library["포스터 제작"]], "adopted": [], "submit": True})

    created = admin_client.post("/setup/create", json={
        "name": "2027 겨울수련회", "open_date": OPEN, "close_date": CLOSE,
        "meal_subsidy": 8000, "department_keys": DEPTS,
        "selected": [library["포스터 제작"]], "adopted": [],
    }).json()

    with app_session() as db:
        draft = db.scalars(select(models.RetreatDraft)).one()
        assert draft.status == "생성완료"
        assert draft.created_retreat_id == created["retreat_id"]
        runs = {r.library.title: r.included for r in db.scalars(
            select(models.TaskRun).where(models.TaskRun.retreat_id == created["retreat_id"]))}
        assert runs["포스터 제작"] is True
        assert runs["차량 신청"] is False       # 제출되지 않은 팀의 업무는 빠진다

    # 닫힌 뒤에는 팀 화면이 다시 비어 있어야 한다
    assert "진행 중인 회차 준비가 없습니다" in lead_client.get("/draft").text


# ---------------------------------------------------------------- 회차 개설 이후 업무 추가


def test_라이브러리에서_업무를_더_넣을_수_있다(admin_client, library):
    """회차를 연 뒤에도 업무는 늘어난다."""
    admin_client.post("/setup/create", json={
        "name": "2027 겨울수련회", "open_date": OPEN, "close_date": CLOSE,
        "meal_subsidy": 8000, "department_keys": DEPTS,
        "selected": [library["포스터 제작"]], "adopted": [],
    })
    new_id = admin_client.post("/setup/preview", json={"open_date": OPEN, "department_keys": DEPTS})
    page = admin_client.get("/board/add")
    assert page.status_code == 200
    assert "차량 신청" in page.text            # 아직 안 들어간 업무만 보인다
    assert new_id.status_code == 200

    response = admin_client.post("/board/add/existing", json={"library_ids": [library["차량 신청"]]})
    assert response.status_code == 200
    with app_session() as db:
        retreat = db.scalars(select(models.Retreat).order_by(models.Retreat.id.desc())).first()
        run = db.scalars(select(models.TaskRun).where(
            models.TaskRun.retreat_id == retreat.id,
            models.TaskRun.library_id == library["차량 신청"])).one()
        assert run.included is True
        assert run.start_date == dt.date(2027, 1, 3)      # D-2주로 다시 계산된다


def test_새_업무를_만들면_라이브러리에도_남는다(admin_client, library):
    """다음 회차의 후보가 되어야 하므로 회차에만 넣고 끝내지 않는다."""
    admin_client.post("/setup/create", json={
        "name": "2027 겨울수련회", "open_date": OPEN, "close_date": CLOSE,
        "meal_subsidy": 8000, "department_keys": DEPTS, "selected": [], "adopted": [],
    })

    response = admin_client.post("/board/add/new", json={
        "title": "방한 물품 추가 구매", "department_key": "chongmuM",
        "kind": "main", "d_week": 3, "span_days": 7,
    })

    assert response.status_code == 200
    with app_session() as db:
        lib_row = db.get(models.TaskLibrary, response.json()["library_id"])
        assert lib_row.title == "방한 물품 추가 구매"
        assert lib_row.default_d_week == 3
        run = db.scalars(select(models.TaskRun).where(
            models.TaskRun.library_id == lib_row.id)).one()
        assert run.included is True
        assert run.start_date == dt.date(2026, 12, 27)    # D-3주
        assert run.end_date == dt.date(2027, 1, 3)


def test_부서_리더는_남의_부서_업무를_추가할_수_없다(admin_client, lead_client, library):
    admin_client.post("/setup/create", json={
        "name": "2027 겨울수련회", "open_date": OPEN, "close_date": CLOSE,
        "meal_subsidy": 8000, "department_keys": DEPTS, "selected": [], "adopted": [],
    })

    assert lead_client.post("/board/add/new", json={
        "title": "남의 부서 일", "department_key": "chongmuM", "kind": "main", "d_week": 3,
    }).status_code == 403
    assert lead_client.post("/board/add/new", json={
        "title": "우리 부서 일", "department_key": "sketch", "kind": "main", "d_week": 3,
    }).status_code == 200
