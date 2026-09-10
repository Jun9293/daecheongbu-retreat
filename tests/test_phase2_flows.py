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
    # 진행 중인 회차여야 한다 — 끝난 회차에는 위험 점검이 알림을 안 만든다 (UI 정리 판 2)
    retreat = _create_retreat(admin_client, start=(TODAY + dt.timedelta(days=40)).isoformat(),
                              end=(TODAY + dt.timedelta(days=43)).isoformat())
    depts = _create_departments(admin_client, list(dept_names))
    return retreat, depts


def _make_user(admin_client, name, phone, role, dept_id=None):
    # 구설계 POST(/users/create) 는 지웠다 (14장) — DB 에 직접 만든다
    from tests.conftest import make_user

    make_user(name, phone, role, dept_id)
    with app_session() as db:
        return db.scalars(
            select(models.User).where(models.User.name == name)
        ).one()


def _make_task(admin_client, title, dept_id=None, **extra):
    """옛 Task 행을 DB 에 직접 만든다.

    옛 /tasks/create 는 단계 3 에서 지웠다 (4-14) — 표와 행은 남으므로,
    남은 코드(위험 점검·확인 요청)가 그 행을 어떻게 다루는지는 계속 시험한다.
    """
    with app_session() as db:
        task = models.Task(
            retreat_id=db.scalars(select(models.Retreat)).first().id,
            title=title,
            department_id=dept_id,
            assignee_id=int(extra["assignee_id"]) if extra.get("assignee_id") else None,
            due_date=dt.date.fromisoformat(extra["due_date"]) if extra.get("due_date") else None,
            status=extra.get("status", "대기"),
            blocked_by_task_ids=[],
            related_department_ids=[],
        )
        db.add(task)
        db.commit()
        return task


def _request_review(task, department_ids, message=""):
    """확인 요청을 직접 만든다 — 옛 /tasks/{id}/review-request 는 지웠고(4-14),
    만드는 함수(create_review_requests)는 파일 쪽이 계속 쓴다. 응답 흐름
    (/reviews/{id}/respond)은 그대로 살아 있다."""
    from app.routers.reviews import create_review_requests

    with app_session() as db:
        retreat = db.get(models.Retreat, task.retreat_id)
        requester = db.scalars(
            select(models.User).where(models.User.role == "admin")
        ).first()
        created = create_review_requests(
            db,
            retreat=retreat,
            requester=requester,
            department_ids=department_ids,
            message=message,
            task=db.get(models.Task, task.id),
        )
        db.commit()
        return [r.id for r in created]


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
#
# 옛 /tasks 의 선행 지정·시작가능 알림 흐름은 화면과 함께 지웠다 (4-14).
# 순환·자기 자신 거부는 도메인이 지키고(tests/test_dependencies.py),
# 새 화면의 선행은 보드 엔드포인트(/board/task/{id}/prerequisites)가 맡는다 —
# tests/test_prerequisites.py 가 그쪽을 시험한다.


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


# (옛 /tasks 라우터의 담당자 지정 알림은 화면과 함께 지웠다 — 4-14.
#  TaskRun 쪽 알림은 4-11 의 묶음이 맡는다: tests/test_notify.py)


# ================================================================ 확인 요청


def test_확인_요청을_보내면_상대_부서에_알림이_간다(admin_client):
    _, depts = _setup(admin_client)
    hongbo, chanyang = depts
    reviewer = _make_user(admin_client, "박찬양", "010-3333-4444", "dept_lead", chanyang.id)
    task = _make_task(admin_client, "포스터 시안 확정", hongbo.id)

    _request_review(task, [chanyang.id], "문구 확인 부탁드려요")

    with app_session() as db:
        review = db.scalars(select(models.ReviewRequest)).one()
        assert review.status == "대기"
        assert review.department_id == chanyang.id

    bodies = [n.body or "" for n in _unread(reviewer.id)]
    assert any("문구 확인 부탁드려요" in b for b in bodies)


def test_요청받은_부서가_승인하면_요청자에게_결과_알림이_간다(admin_client, client):
    _, depts = _setup(admin_client)
    hongbo, chanyang = depts
    _make_user(admin_client, "박찬양", "010-3333-4444", "dept_lead", chanyang.id)
    task = _make_task(admin_client, "포스터 시안 확정", hongbo.id)
    _request_review(task, [chanyang.id], "확인 부탁")
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
    _request_review(task, [chanyang.id])
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
    _request_review(task, [chanyang.id])
    with app_session() as db:
        review = db.scalars(select(models.ReviewRequest)).one()

    login_as(client, "01033334444")
    client.post(f"/reviews/{review.id}/respond", data={"decision": "승인"}, follow_redirects=True)
    client.post(f"/reviews/{review.id}/respond", data={"decision": "반려"}, follow_redirects=True)

    with app_session() as db:
        assert db.get(models.ReviewRequest, review.id).status == "승인"


# ================================================================ 파일
#
# 작업 파일 화면(/files)은 UI 개편 단계 4 에서 지웠다 (14장) — 파일은 업무
# 첨부(4-9)가 그 자리다. 올리기·버전·내려받기·형식 거부는 첨부파일 시험
# (`test_attachments.py`)이 지키고, 남은 FileAsset 행의 이관은
# `test_stage4.py::test4_fm01` 이 지킨다. 여기 있던 일곱 시험은 지운 기능의
# 시험이라 함께 지웠다 — 확인 요청의 승인·반려 흐름은 위 절이 그대로 지킨다.


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
        # 옛 Task 가 아니라 TaskRun 이 만들어진다 — 옛 Task 는 어느 화면에도
        # 안 나타난다 (12장). 담당자·부서·마감이 항목에서 그대로 온다.
        run = db.scalars(
            select(models.TaskRun)
            .join(models.TaskLibrary)
            .where(models.TaskLibrary.title == "인쇄소 견적 3곳 비교")
        ).one()
        assert run.assignee_id == worker.id
        assert run.department_id == depts[0].id
        assert run.end_date == TODAY + dt.timedelta(days=5)
        assert run.source_meeting_id == meeting.id      # 출처 (8장)
        assert db.get(models.MeetingItem, item.id).converted_run_id == run.id
        # 옛 Task 행은 만들어지지 않는다
        assert db.scalars(
            select(models.Task).where(models.Task.title == "인쇄소 견적 3곳 비교")
        ).first() is None

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
        runs = db.scalars(
            select(models.TaskRun)
            .join(models.TaskLibrary)
            .where(models.TaskLibrary.title == "견적 비교")
        ).all()
    assert len(runs) == 1


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

    # /more 는 지웠다 — 설정 › 점검(4-17)이 그 자리다.
    # /files 도 지웠다(단계 4) — 업무 첨부(4-9)가 그 자리다.
    # /reviews 는 301 → /notifications 을 따라가 200 이면 된다 (4-16)
    for path in ["/settings/checkup", "/notifications", "/reviews", "/checklists", "/meetings"]:
        response = admin_client.get(path)
        assert response.status_code == 200, f"{path} → {response.status_code}"


def test_열람전용_계정은_Phase2_기능도_편집할_수_없다(admin_client, client):
    _, depts = _setup(admin_client)
    _make_user(admin_client, "정전도사", "010-5555-6666", "viewer")
    meeting = _make_meeting(admin_client)

    login_as(client, "01055556666")

    assert client.get("/notifications").status_code == 200  # 열람은 가능
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
