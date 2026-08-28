"""준비 단계 보드 · 세팅 마법사 웹 흐름 (Phase 1 완료 기준)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from tests.conftest import app_session, login_as

OPEN = dt.date(2026, 8, 21)


@pytest.fixture
def board_data(admin_client):
    """부서 2개 · 라이브러리 업무 3건(연결 · 관련팀 포함)을 가진 회차."""
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회 Belong", start_date=OPEN, end_date=dt.date(2026, 8, 23)
        )
        db.add(retreat)
        db.flush()
        depts = {}
        for order, (key, name, color) in enumerate(
            [("chongmuM", "1 총무M", "#2F4858"), ("sketch", "4 스케치", "#B95A83")]
        ):
            dept = models.Department(
                retreat_id=retreat.id, key=key, name=name, color_tag=color, sort_order=order
            )
            db.add(dept)
            db.flush()
            depts[key] = dept

        poster = models.TaskLibrary(
            title="포스터 제작",
            kind="main",
            default_department_key="sketch",
            related_department_keys=["chongmuM"],
            related_library_ids=[],
            date_anchor="week",
            default_d_week=13,
            default_offset_days=0,
            default_span_days=21,
        )
        car = models.TaskLibrary(
            title="차량 신청",
            kind="main",
            default_department_key="chongmuM",
            related_department_keys=[],
            related_library_ids=[],
            date_anchor="week",
            default_d_week=2,
            default_offset_days=0,
            default_span_days=6,
        )
        db.add_all([poster, car])
        db.flush()
        poster.related_library_ids = [car.id]
        car.related_library_ids = [poster.id]

        confirm = models.TaskLibrary(
            title="포스터 확정",
            kind="sub",
            parent_library_id=poster.id,
            default_department_key="sketch",
            related_department_keys=[],
            related_library_ids=[],
            date_anchor="week",
            default_d_week=11,
            default_offset_days=0,
            default_span_days=0,
        )
        db.add(confirm)
        db.flush()

        runs = {}
        for lib, status in [(poster, "진행중"), (car, "대기"), (confirm, "완료")]:
            start = dt.date(2026, 5, 24) if lib is poster else dt.date(2026, 8, 9)
            if lib is confirm:
                start = dt.date(2026, 6, 7)
            run = models.TaskRun(
                library_id=lib.id,
                retreat_id=retreat.id,
                included=True,
                department_id=depts[lib.default_department_key].id,
                d_week=lib.default_d_week,
                start_date=start,
                end_date=start + dt.timedelta(days=lib.default_span_days),
                status=status,
            )
            db.add(run)
            db.flush()
            runs[lib.title] = run.id

        lead = models.User(
            name="스케치 리더",
            phone_number="01055556666",
            role="dept_lead",
            department_id=depts["sketch"].id,
        )
        db.add(lead)
        db.commit()
        return {"retreat_id": retreat.id, "runs": runs}


@pytest.fixture
def lead_client(board_data):
    from app.main import app

    client = TestClient(app)
    login_as(client, "01055556666")
    return client


# ---------------------------------------------------------------- 보드 화면


def test_보드가_부서_트리와_타임라인으로_그려진다(admin_client, board_data):
    page = admin_client.get("/board")

    assert page.status_code == 200
    assert "포스터 제작" in page.text
    assert "차량 신청" in page.text
    # 주 단위 축의 첫 칸과 마지막 수련회 칸
    assert "D-13" in page.text
    assert "수련회" in page.text


def test_관련팀_행에_고스트_바가_생긴다(admin_client, board_data):
    """담당팀이 아니어도 결과물을 받아야 하는 팀 행에 점선으로 나타난다."""
    page = admin_client.get("/board").text
    # 총무M 은 포스터 제작의 담당이 아니지만 관련팀이다
    assert page.count("포스터 제작") >= 4  # 원본(라벨+바) + 고스트(라벨+바)
    assert "ghostrow" in page


def test_업무_상세에_연결된_업무와_논의가_함께_온다(admin_client, board_data):
    run_id = board_data["runs"]["포스터 제작"]
    data = admin_client.get(f"/board/task/{run_id}").json()

    assert data["title"] == "포스터 제작"
    assert data["department"] == "4 스케치"
    assert data["related_departments"] == ["1 총무M"]
    assert [r["title"] for r in data["related"]] == ["차량 신청"]
    assert data["can_edit"] is True


def test_상태를_바꾸면_저장되고_바_색이_함께_온다(admin_client, board_data):
    run_id = board_data["runs"]["차량 신청"]

    response = admin_client.post(f"/board/task/{run_id}/status", json={"status": "완료"})

    assert response.status_code == 200
    assert response.json()["background"] == "#DFE3E0"  # 완료는 눈에 띄지 않는 회색
    with app_session() as db:
        assert db.get(models.TaskRun, run_id).status == "완료"


def test_알_수_없는_상태는_거부한다(admin_client, board_data):
    run_id = board_data["runs"]["차량 신청"]
    assert admin_client.post(f"/board/task/{run_id}/status", json={"status": "보류"}).status_code == 400


def test_논의를_추가하면_이전_기록은_지워지지_않고_취소선만_그어진다(admin_client, board_data):
    run_id = board_data["runs"]["포스터 제작"]

    first = admin_client.post(
        f"/board/task/{run_id}/discussion", json={"body": "B안으로 확정"}
    ).json()["discussions"]
    assert len(first) == 1

    second = admin_client.post(
        f"/board/task/{run_id}/discussion",
        json={"body": "가독성 문제로 C안 + B안 색상", "supersedes_entry_id": first[0]["id"]},
    ).json()["discussions"]

    assert len(second) == 2
    assert second[0]["body"] == "B안으로 확정"
    assert second[0]["superseded"] is True     # 기록은 남고 취소선만
    assert second[1]["superseded"] is False


def test_빈_논의는_저장하지_않는다(admin_client, board_data):
    run_id = board_data["runs"]["포스터 제작"]
    assert admin_client.post(
        f"/board/task/{run_id}/discussion", json={"body": "   "}
    ).status_code == 400


# ---------------------------------------------------------------- 권한


def test_부서_리더는_자기_부서_업무만_편집할_수_있다(lead_client, board_data):
    mine = board_data["runs"]["포스터 제작"]       # 스케치
    other = board_data["runs"]["차량 신청"]        # 총무M

    assert lead_client.get(f"/board/task/{mine}").json()["can_edit"] is True
    assert lead_client.get(f"/board/task/{other}").json()["can_edit"] is False

    assert lead_client.post(f"/board/task/{mine}/status", json={"status": "완료"}).status_code == 200
    assert lead_client.post(f"/board/task/{other}/status", json={"status": "완료"}).status_code == 403


def test_부서_리더는_다른_부서_업무도_볼_수는_있다(lead_client, board_data):
    """소속 외 업무는 숨기지 않는다 — 존재는 인지되어야 한다."""
    page = lead_client.get("/board")
    assert page.status_code == 200
    assert "차량 신청" in page.text


def test_세팅_마법사는_총무팀만_들어갈_수_있다(lead_client, admin_client, board_data):
    assert lead_client.get("/setup").status_code == 403
    assert admin_client.get("/setup").status_code == 200


# ---------------------------------------------------------------- 세팅 마법사


def test_미리보기가_D주차와_명절_충돌을_계산한다(admin_client, board_data):
    data = admin_client.post(
        "/setup/preview", json={"open_date": "2027-01-15", "department_keys": ["chongmuM", "sketch"]}
    ).json()

    weeks = {w["d_week"]: w for w in data["weeks"]}
    assert weeks[13]["date"] == "2026-10-18"        # D-13주 일요일
    assert {c["d_week"] for c in data["clashes"]} == {3, 4}   # 성탄 · 연말 주간

    titles = {i["title"]: i for i in data["items"]}
    assert titles["포스터 제작"]["start"] == "2026-10-18"
    # 이력이 한 회차뿐이므로 필수(최근 3회 전부)는 될 수 없다
    assert titles["포스터 제작"]["classification"] == "추천"


def test_회차를_만들면_보드가_채워지고_뺀_업무는_미실행으로_남는다(admin_client, board_data):
    preview = admin_client.post(
        "/setup/preview", json={"open_date": "2027-01-15", "department_keys": ["chongmuM"]}
    ).json()
    poster = next(i for i in preview["items"] if i["title"] == "포스터 제작")
    car = next(i for i in preview["items"] if i["title"] == "차량 신청")

    response = admin_client.post(
        "/setup/create",
        json={
            "name": "2027 겨울수련회",
            "open_date": "2027-01-15",
            "close_date": "2027-01-17",
            "meal_subsidy": 8000,
            "department_keys": ["chongmuM"],       # 스케치 제외
            "selected": [int(car["id"])],          # 포스터 제작은 이번에 안 한다
            "adopted": [],
        },
    )
    assert response.status_code == 200
    new_id = response.json()["retreat_id"]

    with app_session() as db:
        runs = {
            r.library.title: r
            for r in db.scalars(select(models.TaskRun).where(models.TaskRun.retreat_id == new_id))
        }
        assert runs["차량 신청"].included is True
        assert runs["차량 신청"].start_date == dt.date(2027, 1, 3)   # D-2주 일요일
        assert runs["차량 신청"].status == "대기"
        assert runs["포스터 제작"].included is False   # 삭제되지 않고 기록으로 남는다
        assert runs["포스터 확정"].included is False   # 하위도 상위를 따라간다
        assert int(poster["id"]) == runs["포스터 제작"].library_id

    board = admin_client.get(f"/board?retreat_id={new_id}")
    assert "차량 신청" in board.text


def test_폐회일이_개회일보다_빠르면_거부한다(admin_client, board_data):
    response = admin_client.post(
        "/setup/create",
        json={
            "name": "잘못된 회차",
            "open_date": "2027-01-15",
            "close_date": "2027-01-10",
            "meal_subsidy": 8000,
            "department_keys": ["chongmuM"],
            "selected": [],
            "adopted": [],
        },
    )
    assert response.status_code == 400
