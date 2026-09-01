"""준비 단계 보드 · 세팅 마법사 웹 흐름 (Phase 1 완료 기준)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.domain import board as board_view
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
    assert response.json()["bar_background"] == board_view.BAR_DONE[0]  # 완료는 눈에 띄지 않는 회색
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
    # 이력이 한 회차뿐이면 "필수"라고 말하지 않는다 — 기록만큼만 표현한다
    assert data["history_depth"] == 1
    assert titles["포스터 제작"]["verdict"]["label"] == "지난 회차 실행"


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


# ---------------------------------------------------------------- 필수 지정


def test_라이브러리_화면에서_필수를_지정할_수_있다(admin_client, board_data):
    page = admin_client.get("/library")
    assert page.status_code == 200
    assert "포스터 제작" in page.text
    assert "자동 분류의 근거는" in page.text or "실행 이력이" in page.text

    with app_session() as db:
        tshirt = models.TaskLibrary(
            title="수련회 티셔츠 제작",
            kind="main",
            default_department_key="chongmuM",
            related_department_keys=[],
            related_library_ids=[],
            date_anchor="week",
            default_d_week=9,
            default_offset_days=0,
            default_span_days=0,
        )
        db.add(tshirt)
        db.commit()
        tshirt_id = tshirt.id

    response = admin_client.post(
        "/library/required/bulk", data={"library_ids": [tshirt_id]}, follow_redirects=False
    )
    assert response.status_code == 303
    with app_session() as db:
        assert db.get(models.TaskLibrary, tshirt_id).always_required is True


def test_이력이_없어도_필수_지정이_경고를_만든다(admin_client, board_data):
    """이 업무는 지난 회차에 실행되지 않아 자동으로는 경고 대상이 아니다."""
    with app_session() as db:
        never = models.TaskLibrary(
            title="결산 보고서 본부 제출",
            kind="main",
            default_department_key="chongmuM",
            related_department_keys=[],
            related_library_ids=[],
            date_anchor="week",
            default_d_week=1,
            default_offset_days=0,
            default_span_days=0,
            always_required=True,
        )
        db.add(never)
        db.commit()

    data = admin_client.post(
        "/setup/preview", json={"open_date": "2027-01-15", "department_keys": ["chongmuM"]}
    ).json()
    row = next(i for i in data["items"] if i["title"] == "결산 보고서 본부 제출")
    # 자동 판정은 "하지 않았다" 쪽인데도
    assert row["verdict"]["label"] == "지난 회차 미실행"
    assert row["verdict"]["required"] is False
    # 수동 지정 때문에 경고 대상이 된다
    assert row["always_required"] is True
    assert row["required"] is True


def test_부서_리더는_라이브러리를_고칠_수_없다(lead_client, board_data):
    assert lead_client.get("/library").status_code == 403
    assert lead_client.post("/library/required/bulk", data={}).status_code == 403


# ---------------------------------------------------------------- 격자 좌표


def test_바의_격자_좌표가_실제_날짜와_맞는다(admin_client, board_data):
    """서브그리드는 열 인덱스가 한 칸 밀리기 쉽다 (CLAUDE.md 9장)."""
    from app.domain import board as board_view

    with app_session() as db:
        retreat = db.get(models.Retreat, board_data["retreat_id"])
        view = board_view.build(db, retreat)
        axis = view["axis"]

    # 세 지점: 주 단위 첫 칸 · 일 단위 전환 · 수련회 칸
    assert axis.column_of(dt.date(2026, 5, 24)) == 1       # D-13주 일요일
    assert axis.column_of(dt.date(2026, 5, 30)) == 1       # 같은 주는 같은 칸
    assert axis.column_of(dt.date(2026, 8, 2)) == 11       # D-3주 = 마지막 주 단위 칸
    assert axis.column_of(dt.date(2026, 8, 9)) == 12       # D-2주 일요일 = 일 단위 첫 칸
    assert axis.column_of(dt.date(2026, 8, 10)) == 13      # 하루 = 한 칸
    assert axis.column_of(dt.date(2026, 8, 20)) == 23      # 개회 전날
    assert axis.column_of(dt.date(2026, 8, 21)) == 24      # 수련회 칸
    assert axis.column_of(dt.date(2026, 8, 23)) == 24      # 폐회일도 같은 칸
    assert axis.total == 24
    assert axis.shift_index == 12                          # 굵은 세로선 위치


# ---------------------------------------------------------------- 모바일


def test_모바일_목록은_D주차_다음_부서로_묶인다(admin_client, board_data):
    """폰에서는 "이번 주에 뭐가 있나"가 먼저 보여야 한다."""
    from app.domain import board as board_view

    with app_session() as db:
        retreat = db.get(models.Retreat, board_data["retreat_id"])
        groups = board_view.build(db, retreat)["mobile_groups"]

    labels = [g["label"] for g in groups]
    # 바깥 묶음은 D-주차, 이른 주차가 먼저
    assert labels == ["D-13주 · 5/24 주", "D-11주 · 6/7 주", "D-2주 · 8/9 주"]
    assert [r["title"] for r in groups[0]["rows"]] == ["포스터 제작"]
    assert [r["title"] for r in groups[-1]["rows"]] == ["차량 신청"]
    # 모든 실행 업무가 어느 묶음엔가 들어간다
    assert sum(len(g["rows"]) for g in groups) == 3


def test_마법사가_계층과_순서를_함께_내려준다(admin_client, board_data):
    data = admin_client.post(
        "/setup/preview", json={"open_date": "2027-01-15", "department_keys": ["chongmuM", "sketch"]}
    ).json()

    poster = next(i for i in data["items"] if i["title"] == "포스터 제작")
    assert poster["task_kind"] == "main"
    assert [c["title"] for c in poster["children"]] == ["포스터 확정"]
    assert poster["children"][0]["start_label"]        # 하위도 날짜가 계산돼 온다

    # 진행 순서 — 라이브러리 등록 순이 아니라 시작일 순
    starts = [i["start"] for i in data["items"] if i["kind"] == "library"]
    assert starts == sorted(starts)

    # 제안은 하위가 없다
    assert all(i["children"] == [] for i in data["items"] if i["kind"] == "suggestion")


# ---------------------------------------------------------------- 날짜 옮기기


def test_바를_끌어_날짜를_옮길_수_있다(admin_client, board_data):
    run_id = board_data["runs"]["포스터 제작"]      # 2026-05-24 ~ 06-14 (21일)

    response = admin_client.post(
        f"/board/task/{run_id}/dates", json={"start": "2026-06-07", "end": "2026-06-28"}
    )

    assert response.status_code == 200
    assert response.json()["start"] == "2026-06-07"
    assert response.json()["d_week"] == 11          # D-주차가 다시 계산된다
    with app_session() as db:
        run = db.get(models.TaskRun, run_id)
        assert run.start_date == dt.date(2026, 6, 7)
        assert run.end_date == dt.date(2026, 6, 28)


def test_바를_끌어_옮기면_색도_함께_온다(admin_client, board_data):
    """수용기준 4 — **한쪽만 고치면 또 두 벌이다.**

    달력이 마감일을 옮길 때 색을 서버에서 받게 했으므로 보드도 같은 응답을
    써야 한다. 지금은 보드의 바가 저장된 상태로만 칠해져서(4-13) 날짜만
    옮기면 값이 같지만, **그 규칙이 바뀌었을 때 따라오지 않는 자리가 바로
    어긋나는 자리다.** 그래서 응답에 색이 실려 오는지, 화면이 그것을 쓰는지
    둘 다 본다.
    """
    run_id = board_data["runs"]["포스터 제작"]

    saved = admin_client.post(
        f"/board/task/{run_id}/dates", json={"start": "2026-06-07", "end": "2026-06-28"}
    ).json()

    # 상태 변경과 **같은 모양**이다 (board.paint_of 한 곳에서 나온다)
    for key in ("bar_background", "bar_border", "dot_background", "dot_border",
                "status", "overdue", "overdue_days", "color"):
        assert key in saved, f"/dates 응답에 {key} 가 없다"

    status = admin_client.post(
        f"/board/task/{run_id}/status", json={"status": "진행중"}
    ).json()
    assert set(status) <= set(saved) | {"start", "end", "d_week", "label"}

    # 보드 화면이 그 값을 실제로 쓰는가
    js = admin_client.get("/static/js/board.js").text
    block = js[js.index("function applySavedDates("):]
    block = block[: block.index("\n}")]
    assert "saved.bar_background" in block, "받은 색을 쓰지 않는다"
    assert "saved.bar_border" in block
    # 고스트 바는 칠하지 않는다 — 원본이 아니다
    assert "el.dataset.ghost" in block


def test_날짜를_옮겨도_라이브러리_기준은_그대로다(admin_client, board_data):
    """한 회차에서 일정을 당겼다고 다음 회차의 기준까지 움직이면 안 된다."""
    run_id = board_data["runs"]["포스터 제작"]
    with app_session() as db:
        before = db.get(models.TaskRun, run_id).library.default_d_week

    admin_client.post(f"/board/task/{run_id}/dates", json={"start": "2026-07-05"})

    with app_session() as db:
        assert db.get(models.TaskRun, run_id).library.default_d_week == before


def test_마감이_시작보다_빠르면_거부한다(admin_client, board_data):
    run_id = board_data["runs"]["포스터 제작"]
    assert admin_client.post(
        f"/board/task/{run_id}/dates", json={"start": "2026-06-07", "end": "2026-06-01"}
    ).status_code == 400


def test_부서_리더는_남의_부서_업무를_옮길_수_없다(lead_client, board_data):
    mine = board_data["runs"]["포스터 제작"]        # 스케치
    other = board_data["runs"]["차량 신청"]         # 총무M

    assert lead_client.post(f"/board/task/{mine}/dates", json={"start": "2026-06-07"}).status_code == 200
    assert lead_client.post(f"/board/task/{other}/dates", json={"start": "2026-08-16"}).status_code == 403


def test_보드가_바마다_편집_권한을_실어_보낸다(lead_client, board_data):
    """끌 수 있는 바인지 화면이 알아야 커서와 동작이 갈린다."""
    page = lead_client.get("/board").text
    assert '"can_edit"' in page


def test_담당팀을_옮기면_담당자도_함께_정리된다(admin_client, board_data):
    """넘긴 팀 사람이 담당자로 남아 있으면 뜻이 맞지 않는다."""
    run_id = board_data["runs"]["포스터 제작"]        # 스케치
    with app_session() as db:
        lead = db.scalars(select(models.User).where(models.User.phone_number == "01055556666")).one()
        db.get(models.TaskRun, run_id).assignee_id = lead.id
        db.commit()

    response = admin_client.post(f"/board/task/{run_id}/department", json={"key": "chongmuM"})

    assert response.status_code == 200
    with app_session() as db:
        run = db.get(models.TaskRun, run_id)
        assert run.department.key == "chongmuM"
        assert run.assignee_id is None        # 스케치 사람은 더 이상 담당이 아니다


def test_담당팀을_담당_없음으로도_옮길_수_있다(admin_client, board_data):
    run_id = board_data["runs"]["포스터 제작"]
    assert admin_client.post(f"/board/task/{run_id}/department", json={"key": None}).status_code == 200
    with app_session() as db:
        assert db.get(models.TaskRun, run_id).department_id is None


def test_이번_회차에_없는_부서로는_옮길_수_없다(admin_client, board_data):
    run_id = board_data["runs"]["포스터 제작"]
    assert admin_client.post(
        f"/board/task/{run_id}/department", json={"key": "koram"}
    ).status_code == 400


def test_부서_리더는_남의_부서_업무의_담당팀을_못_바꾼다(lead_client, board_data):
    other = board_data["runs"]["차량 신청"]           # 총무M
    assert lead_client.post(
        f"/board/task/{other}/department", json={"key": "sketch"}
    ).status_code == 403


# ---------------------------------------------------------------- 논의 수정


def test_써_놓은_논의를_고칠_수_있다(admin_client, board_data):
    run_id = board_data["runs"]["포스터 제작"]
    entry = admin_client.post(
        f"/board/task/{run_id}/discussion", json={"body": "B안으로 확정"}
    ).json()["discussions"][0]

    response = admin_client.post(
        f"/board/task/{run_id}/discussion/{entry['id']}", json={"body": "B안으로 최종 확정"}
    )

    assert response.status_code == 200
    assert response.json()["discussions"][0]["body"] == "B안으로 최종 확정"
    with app_session() as db:
        assert db.get(models.DiscussionEntry, entry["id"]).body == "B안으로 최종 확정"


def test_빈_내용으로는_고칠_수_없다(admin_client, board_data):
    run_id = board_data["runs"]["포스터 제작"]
    entry = admin_client.post(
        f"/board/task/{run_id}/discussion", json={"body": "원본"}
    ).json()["discussions"][0]

    assert admin_client.post(
        f"/board/task/{run_id}/discussion/{entry['id']}", json={"body": "   "}
    ).status_code == 400


def test_남이_쓴_논의는_고칠_수_없다(admin_client, lead_client, board_data):
    """말을 바꾸는 것은 취소선 + 후속 기록으로 남긴다. 이 기능은 오타용이다."""
    run_id = board_data["runs"]["포스터 제작"]      # 스케치 — 리더가 편집 가능한 업무
    mine = lead_client.post(
        f"/board/task/{run_id}/discussion", json={"body": "리더가 쓴 기록"}
    ).json()["discussions"][0]
    theirs = admin_client.post(
        f"/board/task/{run_id}/discussion", json={"body": "총무팀이 쓴 기록"}
    ).json()["discussions"][-1]

    # 자기 것은 고친다
    assert lead_client.post(
        f"/board/task/{run_id}/discussion/{mine['id']}", json={"body": "리더가 고친 기록"}
    ).status_code == 200
    # 남의 것은 못 고친다
    assert lead_client.post(
        f"/board/task/{run_id}/discussion/{theirs['id']}", json={"body": "가로채기"}
    ).status_code == 403
    # 총무팀은 전부 고칠 수 있다
    assert admin_client.post(
        f"/board/task/{run_id}/discussion/{mine['id']}", json={"body": "총무팀이 정리"}
    ).status_code == 200


def test_지난_회차에서_따라온_기록은_고칠_수_없다(admin_client, board_data):
    """그 회차의 사실이므로 여기서 손대지 않는다."""
    run_id = board_data["runs"]["포스터 제작"]
    with app_session() as db:
        carried = models.DiscussionEntry(
            run_id=run_id, authored_at=dt.date(2026, 7, 26),
            body="스트랩 재고 때문에 100×140mm 로 확정",
            author_name="총무팀", carried_from_run_id=999,
        )
        db.add(carried)
        db.commit()
        carried_id = carried.id

    detail = admin_client.get(f"/board/task/{run_id}").json()
    row = next(d for d in detail["discussions"] if d["id"] == carried_id)
    assert row["carried"] is True
    assert row["can_edit"] is False
    assert admin_client.post(
        f"/board/task/{run_id}/discussion/{carried_id}", json={"body": "고쳐보기"}
    ).status_code == 403


def test_업무_규칙은_라이브러리에_남는다(admin_client, board_data):
    """규칙은 회차의 사정이 아니라 '이 업무는 이렇게 한다'이므로 라이브러리에 붙는다."""
    run_id = board_data["runs"]["포스터 제작"]
    body = "1. 스케치팀에 의뢰서를 먼저 보낸다\n2. 시안은 3종 이상 받는다\n  • 인쇄 전 총무M 확인"

    saved = admin_client.post(f"/board/task/{run_id}/rules", json={"body": body})
    assert saved.status_code == 200
    assert saved.json()["rules"] == body          # 줄바꿈이 그대로 남는다

    detail = admin_client.get(f"/board/task/{run_id}").json()
    assert detail["rules"] == body

    with app_session() as db:
        run = db.get(models.TaskRun, run_id)
        assert run.library.rules == body          # 회차가 아니라 라이브러리에 있다


def test_규칙을_비우면_지워진다(admin_client, board_data):
    run_id = board_data["runs"]["포스터 제작"]
    admin_client.post(f"/board/task/{run_id}/rules", json={"body": "한 줄 규칙"})
    cleared = admin_client.post(f"/board/task/{run_id}/rules", json={"body": "   "})
    assert cleared.status_code == 200
    assert cleared.json()["rules"] is None


def test_남의_부서_업무의_규칙은_못_고친다(lead_client, board_data):
    run_id = board_data["runs"]["차량 신청"]
    res = lead_client.post(f"/board/task/{run_id}/rules", json={"body": "끼어들기"})
    assert res.status_code == 403
