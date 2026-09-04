"""Phase 2 통합 테스트 — 실제 HTTP 요청으로 안전망 기능 전체를 확인한다."""

import datetime as dt

from sqlalchemy import select

from app import models
from tests.conftest import app_session, login_as
from tests.test_web_flows import (
    DEFAULT_CATEGORIES,
    _create_categories,
    _create_departments,
    _create_retreat,
)

TODAY = dt.date.today()


def _setup(admin_client, dept_names=("홍보팀", "찬양팀")):
    retreat = _create_retreat(admin_client)
    depts = _create_departments(admin_client, list(dept_names))
    return retreat, depts


def _make_user(admin_client, name, phone, role, dept_id=None):
    admin_client.post(
        "/users/create",
        data={
            "name": name,
            "phone_number": phone,
            "role": role,
            "department_id": str(dept_id) if dept_id else "",
        },
        follow_redirects=True,
    )
    with app_session() as db:
        return db.scalars(
            select(models.User).where(models.User.name == name)
        ).one()


def _make_task(admin_client, title, dept_id=None, **extra):
    data = {"title": title, "department_id": str(dept_id) if dept_id else "", "status": "대기"}
    data.update(extra)
    admin_client.post("/tasks/create", data=data, follow_redirects=True)
    with app_session() as db:
        return db.scalars(select(models.Task).where(models.Task.title == title)).one()


def _unread(user_id: int) -> list[models.Notification]:
    with app_session() as db:
        return list(
            db.scalars(
                select(models.Notification).where(
                    models.Notification.user_id == user_id,
                    models.Notification.read_at.is_(None),
                )
            )
        )


# ================================================================ 선후행 의존성


def test_선행_작업을_지정하면_후행이_막힘으로_표시된다(admin_client):
    _setup(admin_client)
    design = _make_task(admin_client, "포스터 시안 확정")
    printing = _make_task(admin_client, "포스터 인쇄 발주")

    response = admin_client.post(
        f"/tasks/{printing.id}/blockers",
        data={"blocker_ids": [str(design.id)]},
        follow_redirects=True,
    )
    assert response.status_code == 200

    page = admin_client.get("/tasks")
    assert "선행 대기: 포스터 시안 확정" in page.text
    with app_session() as db:
        assert db.get(models.Task, printing.id).blocked_by_task_ids == [design.id]


def test_선행이_완료되면_후행_담당자에게_시작가능_알림이_간다(admin_client):
    _, depts = _setup(admin_client)
    hongbo = depts[0]
    worker = _make_user(admin_client, "최부원", "010-4444-5555", "member", hongbo.id)

    design = _make_task(admin_client, "포스터 시안 확정", hongbo.id)
    printing = _make_task(
        admin_client, "포스터 인쇄 발주", hongbo.id, assignee_id=str(worker.id)
    )
    admin_client.post(
        f"/tasks/{printing.id}/blockers",
        data={"blocker_ids": [str(design.id)]},
        follow_redirects=True,
    )

    response = admin_client.post(
        f"/tasks/{design.id}/status", data={"status": "완료"}, follow_redirects=True
    )

    assert response.status_code == 200
    titles = [n.title for n in _unread(worker.id)]
    assert any("시작할 수 있습니다" in t and "포스터 인쇄 발주" in t for t in titles)


def test_선행이_두_개면_하나만_끝나도_시작가능_알림은_안_간다(admin_client):
    _, depts = _setup(admin_client)
    hongbo = depts[0]
    worker = _make_user(admin_client, "최부원", "010-4444-5555", "member", hongbo.id)

    a = _make_task(admin_client, "시안 확정", hongbo.id)
    b = _make_task(admin_client, "예산 승인", hongbo.id)
    printing = _make_task(admin_client, "인쇄 발주", hongbo.id, assignee_id=str(worker.id))
    admin_client.post(
        f"/tasks/{printing.id}/blockers",
        data={"blocker_ids": [str(a.id), str(b.id)]},
        follow_redirects=True,
    )

    admin_client.post(f"/tasks/{a.id}/status", data={"status": "완료"}, follow_redirects=True)

    assert not any("시작할 수 있습니다" in n.title for n in _unread(worker.id))


def test_순환_참조는_거부된다(admin_client):
    _setup(admin_client)
    a = _make_task(admin_client, "A 작업")
    b = _make_task(admin_client, "B 작업")

    admin_client.post(
        f"/tasks/{b.id}/blockers", data={"blocker_ids": [str(a.id)]}, follow_redirects=True
    )
    response = admin_client.post(
        f"/tasks/{a.id}/blockers", data={"blocker_ids": [str(b.id)]}, follow_redirects=True
    )

    assert response.status_code == 200
    with app_session() as db:
        assert db.get(models.Task, a.id).blocked_by_task_ids == []


def test_자기_자신은_선행으로_지정할_수_없다(admin_client):
    _setup(admin_client)
    a = _make_task(admin_client, "A 작업")

    admin_client.post(
        f"/tasks/{a.id}/blockers", data={"blocker_ids": [str(a.id)]}, follow_redirects=True
    )

    with app_session() as db:
        assert db.get(models.Task, a.id).blocked_by_task_ids == []


# ================================================================ 에스컬레이션


def test_점검을_돌리면_기한_지난_할일이_지연으로_바뀌고_총무팀에_알림이_간다(admin_client):
    retreat, depts = _setup(admin_client)
    hongbo = depts[0]
    leader = _make_user(admin_client, "이홍보", "010-2222-3333", "dept_lead", hongbo.id)
    task = _make_task(
        admin_client,
        "포스터 인쇄 발주",
        hongbo.id,
        assignee_id=str(leader.id),
        due_date=(TODAY - dt.timedelta(days=3)).isoformat(),
    )

    response = admin_client.post("/risk-scan", follow_redirects=True)
    assert response.status_code == 200

    with app_session() as db:
        assert db.get(models.Task, task.id).status == "지연"
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()

    assert any("기한이 지났습니다" in n.title for n in _unread(leader.id))
    assert any("기한이 지났습니다" in n.title for n in _unread(admin.id))


def test_담당자가_없고_기한이_임박하면_총무팀에_에스컬레이션된다(admin_client):
    _, depts = _setup(admin_client)
    _make_task(
        admin_client,
        "차량 배차표 작성",
        depts[0].id,
        due_date=(TODAY + dt.timedelta(days=3)).isoformat(),
    )

    admin_client.post("/risk-scan", follow_redirects=True)

    with app_session() as db:
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()
    titles = [n.title for n in _unread(admin.id)]
    assert any("담당자가 없습니다" in t for t in titles)


def test_점검을_두_번_돌려도_알림이_중복되지_않는다(admin_client):
    _, depts = _setup(admin_client)
    _make_task(
        admin_client,
        "차량 배차표 작성",
        depts[0].id,
        due_date=(TODAY - dt.timedelta(days=1)).isoformat(),
    )

    admin_client.post("/risk-scan", follow_redirects=True)
    with app_session() as db:
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()
    first = len(_unread(admin.id))

    admin_client.post("/risk-scan", follow_redirects=True)

    assert len(_unread(admin.id)) == first


def test_부서리더는_위험_점검을_직접_돌릴_수_없다(admin_client, client):
    _, depts = _setup(admin_client)
    _make_user(admin_client, "이홍보", "010-2222-3333", "dept_lead", depts[0].id)

    login_as(client, "01022223333")
    response = client.post("/risk-scan")

    assert response.status_code == 403


def test_담당자로_지정되면_알림을_받는다(admin_client):
    _, depts = _setup(admin_client)
    worker = _make_user(admin_client, "최부원", "010-4444-5555", "member", depts[0].id)

    _make_task(admin_client, "굿즈 수량 취합", depts[0].id, assignee_id=str(worker.id))

    assert any("담당자로 지정됐습니다" in n.title for n in _unread(worker.id))


# ================================================================ 확인 요청


def test_확인_요청을_보내면_상대_부서에_알림이_간다(admin_client):
    _, depts = _setup(admin_client)
    hongbo, chanyang = depts
    reviewer = _make_user(admin_client, "박찬양", "010-3333-4444", "dept_lead", chanyang.id)
    task = _make_task(admin_client, "포스터 시안 확정", hongbo.id)

    response = admin_client.post(
        f"/tasks/{task.id}/review-request",
        data={"department_ids": [str(chanyang.id)], "message": "문구 확인 부탁드려요"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app_session() as db:
        review = db.scalars(select(models.ReviewRequest)).one()
        assert review.status == "대기"
        assert review.department_id == chanyang.id
        assert db.get(models.Task, task.id).status == "피드백요청"

    bodies = [n.body or "" for n in _unread(reviewer.id)]
    assert any("문구 확인 부탁드려요" in b for b in bodies)


def test_요청받은_부서가_승인하면_요청자에게_결과_알림이_간다(admin_client, client):
    _, depts = _setup(admin_client)
    hongbo, chanyang = depts
    _make_user(admin_client, "박찬양", "010-3333-4444", "dept_lead", chanyang.id)
    task = _make_task(admin_client, "포스터 시안 확정", hongbo.id)
    admin_client.post(
        f"/tasks/{task.id}/review-request",
        data={"department_ids": [str(chanyang.id)], "message": "확인 부탁"},
        follow_redirects=True,
    )
    with app_session() as db:
        review = db.scalars(select(models.ReviewRequest)).one()
        requester_id = review.requester_id

    login_as(client, "01033334444")
    response = client.post(
        f"/reviews/{review.id}/respond",
        data={"decision": "승인", "comment": "좋습니다"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app_session() as db:
        updated = db.get(models.ReviewRequest, review.id)
        assert updated.status == "승인"
        assert updated.responder_name == "박찬양"
        assert updated.response_comment == "좋습니다"

    titles = [n.title for n in _unread(requester_id)]
    assert any("승인" in t for t in titles)


def test_요청받지_않은_부서는_응답할_수_없다(admin_client, client):
    _, depts = _setup(admin_client, ("홍보팀", "찬양팀", "새가족팀"))
    hongbo, chanyang, saega = depts
    _make_user(admin_client, "새가족리더", "010-7777-8888", "dept_lead", saega.id)
    task = _make_task(admin_client, "포스터 시안 확정", hongbo.id)
    admin_client.post(
        f"/tasks/{task.id}/review-request",
        data={"department_ids": [str(chanyang.id)]},
        follow_redirects=True,
    )
    with app_session() as db:
        review = db.scalars(select(models.ReviewRequest)).one()

    login_as(client, "01077778888")
    response = client.post(f"/reviews/{review.id}/respond", data={"decision": "승인"})

    assert response.status_code == 403
    with app_session() as db:
        assert db.get(models.ReviewRequest, review.id).status == "대기"


def test_이미_처리된_요청은_다시_처리되지_않는다(admin_client, client):
    _, depts = _setup(admin_client)
    hongbo, chanyang = depts
    _make_user(admin_client, "박찬양", "010-3333-4444", "dept_lead", chanyang.id)
    task = _make_task(admin_client, "포스터 시안 확정", hongbo.id)
    admin_client.post(
        f"/tasks/{task.id}/review-request",
        data={"department_ids": [str(chanyang.id)]},
        follow_redirects=True,
    )
    with app_session() as db:
        review = db.scalars(select(models.ReviewRequest)).one()

    login_as(client, "01033334444")
    client.post(f"/reviews/{review.id}/respond", data={"decision": "승인"}, follow_redirects=True)
    client.post(f"/reviews/{review.id}/respond", data={"decision": "반려"}, follow_redirects=True)

    with app_session() as db:
        assert db.get(models.ReviewRequest, review.id).status == "승인"


# ================================================================ 파일


PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _upload_file(admin_client, dept_id, title="수련회 포스터"):
    admin_client.post(
        "/files/create",
        data={"title": title, "department_id": str(dept_id), "note": "1차 시안"},
        files={"upload": ("poster_v1.png", PNG, "image/png")},
        follow_redirects=True,
    )
    with app_session() as db:
        return db.scalars(select(models.FileAsset).where(models.FileAsset.title == title)).one()


def test_파일을_올리면_v1로_등록된다(admin_client):
    _, depts = _setup(admin_client)
    asset = _upload_file(admin_client, depts[0].id)

    with app_session() as db:
        versions = db.scalars(
            select(models.FileVersion).where(models.FileVersion.file_asset_id == asset.id)
        ).all()

    assert asset.status == "작업중"
    assert len(versions) == 1
    assert versions[0].version_no == 1
    assert versions[0].original_name == "poster_v1.png"


def test_새_버전을_올리면_이력이_쌓이고_최신이_바뀐다(admin_client):
    _, depts = _setup(admin_client)
    asset = _upload_file(admin_client, depts[0].id)

    admin_client.post(
        f"/files/{asset.id}/versions",
        data={"note": "2차 수정"},
        files={"upload": ("poster_v2.png", PNG, "image/png")},
        follow_redirects=True,
    )

    with app_session() as db:
        refreshed = db.get(models.FileAsset, asset.id)
        assert len(refreshed.versions) == 2
        assert refreshed.latest.version_no == 2
        assert refreshed.latest.note == "2차 수정"


def test_파일을_내려받을_수_있다(admin_client):
    _, depts = _setup(admin_client)
    asset = _upload_file(admin_client, depts[0].id)

    response = admin_client.get(f"/files/{asset.id}/download/1")

    assert response.status_code == 200
    assert response.content == PNG


def test_파일_확인_요청이_승인되면_파일_상태도_승인이_된다(admin_client, client):
    _, depts = _setup(admin_client)
    hongbo, chanyang = depts
    _make_user(admin_client, "박찬양", "010-3333-4444", "dept_lead", chanyang.id)
    asset = _upload_file(admin_client, hongbo.id)

    admin_client.post(
        f"/files/{asset.id}/review-request",
        data={"department_ids": [str(chanyang.id)], "message": "확인 부탁"},
        follow_redirects=True,
    )
    with app_session() as db:
        assert db.get(models.FileAsset, asset.id).status == "검토요청"
        review = db.scalars(select(models.ReviewRequest)).one()

    login_as(client, "01033334444")
    client.post(
        f"/reviews/{review.id}/respond", data={"decision": "승인"}, follow_redirects=True
    )

    with app_session() as db:
        assert db.get(models.FileAsset, asset.id).status == "승인"


def test_승인된_파일에_새_버전을_올리면_다시_작업중이_된다(admin_client, client):
    _, depts = _setup(admin_client)
    hongbo, chanyang = depts
    _make_user(admin_client, "박찬양", "010-3333-4444", "dept_lead", chanyang.id)
    asset = _upload_file(admin_client, hongbo.id)
    admin_client.post(
        f"/files/{asset.id}/review-request",
        data={"department_ids": [str(chanyang.id)]},
        follow_redirects=True,
    )
    with app_session() as db:
        review = db.scalars(select(models.ReviewRequest)).one()
    login_as(client, "01033334444")
    client.post(f"/reviews/{review.id}/respond", data={"decision": "승인"}, follow_redirects=True)

    admin_client.post(
        f"/files/{asset.id}/versions",
        data={"note": "수정본"},
        files={"upload": ("poster_v2.png", PNG, "image/png")},
        follow_redirects=True,
    )

    with app_session() as db:
        assert db.get(models.FileAsset, asset.id).status == "작업중"


def test_허용되지_않는_파일_형식은_거부한다(admin_client):
    _, depts = _setup(admin_client)

    response = admin_client.post(
        "/files/create",
        data={"title": "악성", "department_id": str(depts[0].id)},
        files={"upload": ("bad.exe", b"MZ", "application/octet-stream")},
    )

    assert response.status_code == 400
    with app_session() as db:
        assert db.scalars(select(models.FileAsset)).all() == []


def test_타부서_파일에는_새_버전을_올릴_수_없다(admin_client, client):
    _, depts = _setup(admin_client)
    hongbo, chanyang = depts
    _make_user(admin_client, "박찬양", "010-3333-4444", "dept_lead", chanyang.id)
    asset = _upload_file(admin_client, hongbo.id)

    login_as(client, "01033334444")
    response = client.post(
        f"/files/{asset.id}/versions",
        data={"note": "몰래"},
        files={"upload": ("x.png", PNG, "image/png")},
    )

    assert response.status_code == 403


# ================================================================ 체크리스트


def test_체크리스트를_여러_줄로_한_번에_만들_수_있다(admin_client):
    _, depts = _setup(admin_client)

    admin_client.post(
        "/checklists/create",
        data={
            "name": "1일차 집회 비품",
            "department_id": str(depts[0].id),
            "items": "무선마이크 4개\n마이크 배터리\n\nHDMI 케이블",
        },
        follow_redirects=True,
    )

    with app_session() as db:
        checklist = db.scalars(select(models.Checklist)).one()
        labels = [i.label for i in checklist.items]

    assert labels == ["무선마이크 4개", "마이크 배터리", "HDMI 케이블"]  # 빈 줄은 무시
    assert checklist.progress_pct == 0


def test_항목을_체크하면_누가_언제_했는지_남는다(admin_client):
    _, depts = _setup(admin_client)
    admin_client.post(
        "/checklists/create",
        data={"name": "비품", "department_id": str(depts[0].id), "items": "마이크"},
        follow_redirects=True,
    )
    with app_session() as db:
        item = db.scalars(select(models.ChecklistItem)).one()

    admin_client.post(f"/checklists/items/{item.id}/toggle", follow_redirects=True)

    with app_session() as db:
        checked = db.get(models.ChecklistItem, item.id)
        assert checked.checked is True
        assert checked.checked_by_name == "총무 김간사"
        assert checked.checked_at is not None
        assert checked.checklist.progress_pct == 100


def test_체크를_해제하면_기록도_지워진다(admin_client):
    _, depts = _setup(admin_client)
    admin_client.post(
        "/checklists/create",
        data={"name": "비품", "department_id": str(depts[0].id), "items": "마이크"},
        follow_redirects=True,
    )
    with app_session() as db:
        item = db.scalars(select(models.ChecklistItem)).one()

    admin_client.post(f"/checklists/items/{item.id}/toggle", follow_redirects=True)
    admin_client.post(f"/checklists/items/{item.id}/toggle", follow_redirects=True)

    with app_session() as db:
        cleared = db.get(models.ChecklistItem, item.id)
        assert cleared.checked is False
        assert cleared.checked_by_name is None


def test_타부서_체크리스트는_체크할_수_없다(admin_client, client):
    _, depts = _setup(admin_client)
    hongbo, chanyang = depts
    _make_user(admin_client, "박찬양", "010-3333-4444", "dept_lead", chanyang.id)
    admin_client.post(
        "/checklists/create",
        data={"name": "홍보 비품", "department_id": str(hongbo.id), "items": "포스터"},
        follow_redirects=True,
    )
    with app_session() as db:
        item = db.scalars(select(models.ChecklistItem)).one()

    login_as(client, "01033334444")
    response = client.post(f"/checklists/items/{item.id}/toggle")

    assert response.status_code == 403
    with app_session() as db:
        assert db.get(models.ChecklistItem, item.id).checked is False


# ================================================================ 회의록


def _make_meeting(admin_client, title="3차 총무팀 회의"):
    admin_client.post(
        "/meetings/create",
        data={
            "title": title,
            "meeting_date": TODAY.isoformat(),
            "attendees": "이름1 이름2, 이름3",
            "body": "예산 진행 상황 공유",
            "link_retreat": "retreat",
        },
        follow_redirects=True,
    )
    with app_session() as db:
        return db.scalars(select(models.Meeting).where(models.Meeting.title == title)).one()


def test_회의록을_만들면_참석자가_배열로_저장된다(admin_client):
    _setup(admin_client)
    meeting = _make_meeting(admin_client)

    assert meeting.attendee_names == ["이름1", "이름2", "이름3"]
    assert meeting.meeting_date == TODAY


def test_액션아이템을_할일로_등록하면_담당자에게_알림이_간다(admin_client):
    _, depts = _setup(admin_client)
    worker = _make_user(admin_client, "최부원", "010-4444-5555", "member", depts[0].id)
    meeting = _make_meeting(admin_client)

    admin_client.post(
        f"/meetings/{meeting.id}/items",
        data={
            "kind": "액션아이템",
            "content": "인쇄소 견적 3곳 비교",
            "department_id": str(depts[0].id),
            "assignee_id": str(worker.id),
            "due_date": (TODAY + dt.timedelta(days=5)).isoformat(),
        },
        follow_redirects=True,
    )
    with app_session() as db:
        item = db.scalars(select(models.MeetingItem)).one()

    response = admin_client.post(f"/meetings/items/{item.id}/to-task", follow_redirects=True)

    assert response.status_code == 200
    with app_session() as db:
        task = db.scalars(
            select(models.Task).where(models.Task.title == "인쇄소 견적 3곳 비교")
        ).one()
        assert task.assignee_id == worker.id
        assert task.department_id == depts[0].id
        assert task.due_date == TODAY + dt.timedelta(days=5)
        assert db.get(models.MeetingItem, item.id).converted_task_id == task.id

    assert any("새 할 일" in n.title for n in _unread(worker.id))


def test_같은_액션아이템을_두_번_등록하지_않는다(admin_client):
    _, depts = _setup(admin_client)
    meeting = _make_meeting(admin_client)
    admin_client.post(
        f"/meetings/{meeting.id}/items",
        data={"kind": "액션아이템", "content": "견적 비교", "department_id": str(depts[0].id)},
        follow_redirects=True,
    )
    with app_session() as db:
        item = db.scalars(select(models.MeetingItem)).one()

    admin_client.post(f"/meetings/items/{item.id}/to-task", follow_redirects=True)
    admin_client.post(f"/meetings/items/{item.id}/to-task", follow_redirects=True)

    with app_session() as db:
        tasks = db.scalars(select(models.Task).where(models.Task.title == "견적 비교")).all()
    assert len(tasks) == 1


def test_수련회와_무관한_일반_회의도_기록할_수_있다(admin_client):
    _setup(admin_client)

    admin_client.post(
        "/meetings/create",
        data={"title": "주간 사역 회의", "meeting_date": TODAY.isoformat(), "link_retreat": "none"},
        follow_redirects=True,
    )

    with app_session() as db:
        meeting = db.scalars(
            select(models.Meeting).where(models.Meeting.title == "주간 사역 회의")
        ).one()
    assert meeting.retreat_id is None

    page = admin_client.get("/meetings")
    assert "일반 회의" in page.text


# ================================================================ 알림함 · 화면


def test_알림을_읽으면_뱃지_숫자가_줄어든다(admin_client):
    _, depts = _setup(admin_client)
    _make_task(
        admin_client,
        "차량 배차표",
        depts[0].id,
        due_date=(TODAY - dt.timedelta(days=1)).isoformat(),
    )
    admin_client.post("/risk-scan", follow_redirects=True)

    with app_session() as db:
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()
    before = len(_unread(admin.id))
    assert before > 0

    admin_client.post("/notifications/read-all", follow_redirects=True)

    assert len(_unread(admin.id)) == 0
    page = admin_client.get("/")
    assert 'class="badge"' not in page.text


def test_Phase2_화면들이_모두_정상적으로_열린다(admin_client):
    _setup(admin_client)
    _create_categories(admin_client, DEFAULT_CATEGORIES)

    for path in ["/more", "/notifications", "/reviews", "/files", "/checklists", "/meetings"]:
        response = admin_client.get(path)
        assert response.status_code == 200, f"{path} → {response.status_code}"


def test_열람전용_계정은_Phase2_기능도_편집할_수_없다(admin_client, client):
    _, depts = _setup(admin_client)
    _make_user(admin_client, "정전도사", "010-5555-6666", "viewer")
    meeting = _make_meeting(admin_client)

    login_as(client, "01055556666")

    assert client.get("/files").status_code == 200  # 열람은 가능
    assert (
        client.post(
            "/checklists/create", data={"name": "몰래", "items": "x"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/meetings/{meeting.id}/items", data={"kind": "안건", "content": "몰래"}
        ).status_code
        == 403
    )


# ================================================================ 웹 푸시


def test_푸시_구독을_저장할_수_있다(admin_client):
    _setup(admin_client)

    response = admin_client.post(
        "/push/subscribe",
        json={
            "subscription": {
                "endpoint": "https://push.example.com/abc123",
                "keys": {"p256dh": "test-p256dh", "auth": "test-auth"},
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    with app_session() as db:
        sub = db.scalars(select(models.PushSubscription)).one()
    assert sub.endpoint == "https://push.example.com/abc123"


def test_같은_기기가_다시_구독해도_중복_저장되지_않는다(admin_client):
    _setup(admin_client)
    payload = {
        "subscription": {
            "endpoint": "https://push.example.com/abc123",
            "keys": {"p256dh": "k", "auth": "a"},
        }
    }

    admin_client.post("/push/subscribe", json=payload)
    admin_client.post("/push/subscribe", json=payload)

    with app_session() as db:
        assert len(db.scalars(select(models.PushSubscription)).all()) == 1


def test_구독을_해제할_수_있다(admin_client):
    _setup(admin_client)
    admin_client.post(
        "/push/subscribe",
        json={
            "subscription": {
                "endpoint": "https://push.example.com/abc123",
                "keys": {"p256dh": "k", "auth": "a"},
            }
        },
    )

    admin_client.post("/push/unsubscribe", json={"endpoint": "https://push.example.com/abc123"})

    with app_session() as db:
        assert db.scalars(select(models.PushSubscription)).all() == []


def test_푸시_발송이_실패해도_앱_알림함에는_정상적으로_남는다(admin_client):
    """푸시는 실패할 수 있다 (구독 만료·네트워크). 그때도 알림은 살아 있어야 한다."""
    _, depts = _setup(admin_client)
    # 실제로 도달할 수 없는 엔드포인트를 등록해 발송 실패를 만든다
    admin_client.post(
        "/push/subscribe",
        json={
            "subscription": {
                "endpoint": "https://push.invalid.example/does-not-exist",
                "keys": {"p256dh": "bogus", "auth": "bogus"},
            }
        },
    )

    _make_task(
        admin_client,
        "차량 배차표",
        depts[0].id,
        due_date=(TODAY - dt.timedelta(days=1)).isoformat(),
    )
    response = admin_client.post("/risk-scan", follow_redirects=True)

    assert response.status_code == 200
    with app_session() as db:
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()
    assert any("기한이 지났습니다" in n.title for n in _unread(admin.id))


def test_공개키를_내려받을_수_있다(admin_client):
    response = admin_client.get("/push/public-key")

    assert response.status_code == 200
    key = response.json()["key"]
    assert len(key) > 80  # VAPID 공개키 (base64url)
