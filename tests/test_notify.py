"""웹 푸시 — 보낼 거리를 고르는 규칙 (CLAUDE.md 4-11).

수용 기준 1~14 에 하나씩 대응한다. 함수 이름 앞의 숫자가 그 번호다.

실제 전송은 가짜로 갈아끼운다. 네트워크에 의존하는 테스트를 만들지 않는다 —
검증할 것은 "누구에게 무엇이 가는가" 이고 그건 build_digests 가 정한다.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app import models
from app.domain import diagnosis
from app.domain import notify
from tests.conftest import app_session

OPEN = dt.date(2026, 8, 21)
CLOSE = dt.date(2026, 8, 23)
TODAY = dt.date(2026, 6, 1)


def _lib(db, title, *, key="sketch", kind="main", d_week=10):
    row = models.TaskLibrary(
        title=title, kind=kind, default_department_key=key,
        related_department_keys=[], related_library_ids=[], prerequisite_library_ids=[],
        date_anchor="week", default_d_week=d_week,
        default_offset_days=0, default_span_days=0,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def world(admin_client):
    """스케치·헤브론 두 팀. 헤브론의 '장비 확인' 이 스케치의 '명찰 제작' 을 막는다."""
    with app_session() as db:
        retreat = models.Retreat(name="2026 여름수련회", start_date=OPEN, end_date=CLOSE)
        db.add(retreat)
        db.flush()

        depts = {}
        for order, (key, name) in enumerate([("sketch", "4 스케치"), ("hebron", "5 헤브론")]):
            dept = models.Department(
                retreat_id=retreat.id, key=key, name=name, color_tag="#888", sort_order=order
            )
            db.add(dept)
            db.flush()
            depts[key] = dept

        people = {}
        for name, phone, role, key in [
            ("스케치 담당", "01010001000", "member", "sketch"),
            ("헤브론 담당", "01020002000", "member", "hebron"),
            ("헤브론 리더", "01030003000", "dept_lead", "hebron"),
        ]:
            person = models.User(
                name=name, phone_number=phone, role=role, department_id=depts[key].id
            )
            db.add(person)
            db.flush()
            people[name] = person.id

        gear = _lib(db, "장비 확인", key="hebron", d_week=12)
        badge = _lib(db, "명찰 제작", key="sketch", d_week=9)
        poster = _lib(db, "포스터 제작", key="sketch", d_week=9)
        orphan = _lib(db, "담당 없는 업무", key="hebron", d_week=9)
        rehearsal = _lib(db, "총 리허설", key="sketch", kind="schedule", d_week=2)

        runs = {}
        rows = [
            # (라이브러리, 담당자, 시작, 마감)
            (gear, people["헤브론 담당"], dt.date(2026, 5, 10), dt.date(2026, 5, 17)),
            (badge, people["스케치 담당"], dt.date(2026, 6, 20), dt.date(2026, 6, 27)),
            (poster, people["스케치 담당"], dt.date(2026, 5, 1), dt.date(2026, 5, 27)),
            (orphan, None, dt.date(2026, 5, 1), dt.date(2026, 5, 27)),
            (rehearsal, people["스케치 담당"], dt.date(2026, 5, 20), dt.date(2026, 5, 20)),
        ]
        for lib, assignee, start, end in rows:
            run = models.TaskRun(
                library_id=lib.id, retreat_id=retreat.id, included=True,
                department_id=depts[lib.default_department_key].id,
                assignee_id=assignee, d_week=lib.default_d_week,
                start_date=start, end_date=end, status="대기", blocked_by_run_ids=[],
            )
            db.add(run)
            db.flush()
            runs[lib.title] = run.id

        db.get(models.TaskRun, runs["명찰 제작"]).blocked_by_run_ids = [runs["장비 확인"]]
        db.commit()
        return {"retreat_id": retreat.id, "runs": runs, "people": people,
                "depts": {k: d.id for k, d in depts.items()}}


def _build(today=TODAY):
    with app_session() as db:
        return notify.build_digests(db, today=today)


def _digests(today=TODAY):
    with app_session() as db:
        return {d.user_name: d for d in notify.build_digests(db, today=today)}


def _kinds(digest):
    return [i.kind for i in digest.items]


def _text(digest):
    return digest.body()


# ── 1 · 2 ─────────────────────────────────────────────────────────────


def test_01_진행_불가는_담당자_본인에게_가지_않는다(world):
    """기다리는 중인데 재촉받는 것이 된다."""
    with app_session() as db:
        retreat = db.get(models.Retreat, world["retreat_id"])
        run = db.get(models.TaskRun, world["runs"]["명찰 제작"])
        assert diagnosis.diagnose(db, retreat, run, today=TODAY).verdict == diagnosis.BLOCKED

    out = _digests()
    sketch = out.get("스케치 담당")
    titles = [i.title for i in sketch.items] if sketch else []
    assert "명찰 제작" not in titles


def test_02_선행을_쥔_담당자에게_선행_재촉으로_간다(world):
    out = _digests()
    hebron = out["헤브론 담당"]
    rows = [i for i in hebron.items if i.kind == notify.UNBLOCK]
    assert len(rows) == 1
    assert rows[0].title == "장비 확인"
    assert "'명찰 제작'" in rows[0].line
    assert "기다리고 있습니다" in rows[0].line
    assert "4 스케치" in rows[0].line          # 상대를 특정한다


# ── 3 ─────────────────────────────────────────────────────────────────


def test_03_담당자가_없으면_부서_리더_그다음_총무팀(world):
    out = _digests()
    lead = out.get("헤브론 리더")
    assert lead is not None
    assert "담당 없는 업무" in [i.title for i in lead.items]

    # 부서 리더가 없으면 총무팀(admin)으로 올린다
    with app_session() as db:
        db.get(models.User, world["people"]["헤브론 리더"]).role = "member"
        db.commit()
    out = _digests()
    admin = next((d for name, d in out.items() if name == "총무 김간사"), None)
    assert admin is not None
    assert "담당 없는 업무" in [i.title for i in admin.items]


# ── 4 ─────────────────────────────────────────────────────────────────


def test_04_한_사람에게_하루_한_통이고_여러_업무가_묶인다(world):
    out = _digests()
    sketch = out["스케치 담당"]
    assert len({d.user_id for d in out.values()}) == len(out)   # 사람당 하나
    assert len(sketch.items) >= 2                                # 여러 업무가 한 통에
    assert sketch.title().startswith("수련회 준비 — 오늘 볼 것")
    assert "[" in sketch.body()                                  # kind 별로 묶인다


# ── 5 · 6 · 11 ────────────────────────────────────────────────────────


def test_05_같은_말은_7일_안에_다시_가지_않는다(world):
    sent = []
    with app_session() as db:
        notify.run_digests(db, today=TODAY, sender=lambda _db, d: sent.append(d) or True)
    assert sent

    with app_session() as db:
        again = notify.build_digests(db, today=TODAY + dt.timedelta(days=6))
    assert again == []

    with app_session() as db:
        after = notify.build_digests(db, today=TODAY + dt.timedelta(days=7))
    assert after                                   # 7일이 지나면 다시 간다


def test_06_상태가_바뀌면_7일을_안_기다린다(world):
    with app_session() as db:
        notify.run_digests(db, today=TODAY, sender=lambda _db, _d: True)

    with app_session() as db:
        assert notify.build_digests(db, today=TODAY + dt.timedelta(days=1)) == []
        # 포스터를 지연으로 바꾸면 사정이 달라진 것이므로 같은 말이 아니다
        db.get(models.TaskRun, world["runs"]["포스터 제작"]).status = "지연"
        db.commit()

    with app_session() as db:
        out = notify.build_digests(db, today=TODAY + dt.timedelta(days=1))
    titles = [i.title for d in out for i in d.items]
    assert "포스터 제작" in titles


def test_11_같은_날_두_번_실행해도_중복되지_않는다(world):
    calls = []
    with app_session() as db:
        first = notify.run_digests(db, today=TODAY, sender=lambda _db, d: calls.append(d) or True)
    with app_session() as db:
        second = notify.run_digests(db, today=TODAY, sender=lambda _db, d: calls.append(d) or True)

    assert first["recipients"] > 0
    assert second["recipients"] == 0
    assert len(calls) == first["recipients"]


# ── 7 ─────────────────────────────────────────────────────────────────


def test_07_5건이_넘으면_잘리고_외_N건이_붙는다(world):
    with app_session() as db:
        retreat = db.get(models.Retreat, world["retreat_id"])
        for i in range(6):
            lib = _lib(db, f"밀린 업무 {i}", key="sketch")
            db.add(
                models.TaskRun(
                    library_id=lib.id, retreat_id=retreat.id, included=True,
                    department_id=world["depts"]["sketch"],
                    assignee_id=world["people"]["스케치 담당"],
                    start_date=dt.date(2026, 5, 1), end_date=dt.date(2026, 5, 20),
                    status="대기", blocked_by_run_ids=[],
                )
            )
        db.commit()

    sketch = _digests()["스케치 담당"]
    assert len(sketch.items) == notify.DIGEST_MAX
    assert sketch.overflow > 0
    assert f"외 {sketch.overflow}건" in sketch.body()


# ── 8 ─────────────────────────────────────────────────────────────────


def test_08_보낼_것이_없으면_아무것도_보내지_않는다(world):
    with app_session() as db:
        for run in db.scalars(select(models.TaskRun)):
            run.status = "완료"
        db.commit()

    with app_session() as db:
        assert notify.build_digests(db, today=TODAY) == []
        sent = []
        result = notify.run_digests(db, today=TODAY, sender=lambda _db, d: sent.append(d) or True)
    assert sent == []
    assert result["recipients"] == 0


# ── 9 ─────────────────────────────────────────────────────────────────


def test_09_종료된_회차_일정_완료는_들어가지_않는다(world):
    # '일정' 은 날짜만 지키면 되는 것이라 재촉할 것이 없다
    titles = [i.title for d in _digests().values() for i in d.items]
    assert "총 리허설" not in titles

    # 완료된 업무는 빠진다
    with app_session() as db:
        db.get(models.TaskRun, world["runs"]["포스터 제작"]).status = "완료"
        db.commit()
    assert "포스터 제작" not in [i.title for d in _digests().values() for i in d.items]

    # 종료된 회차는 통째로 빠진다
    assert _digests(today=CLOSE + dt.timedelta(days=1)) == {}

    with app_session() as db:
        db.get(models.Retreat, world["retreat_id"]).is_archived = True
        db.commit()
    assert _digests() == {}


# ── 10 ────────────────────────────────────────────────────────────────


def test_10_기한_초과가_저장된_지연이_아니라_날짜에서_나온다(world):
    """아무도 '지연' 을 누르지 않아도 잡힌다."""
    with app_session() as db:
        run = db.get(models.TaskRun, world["runs"]["포스터 제작"])
        assert run.status == "대기"             # 아무도 누르지 않았다
        db.commit()

    sketch = _digests()["스케치 담당"]
    overdue = [i for i in sketch.items if i.kind == notify.OVERDUE]
    assert [i.title for i in overdue] == ["포스터 제작"]
    assert "마감에서 5일 지났습니다" in overdue[0].line


def test_10b_기한_임박도_잡힌다(world):
    """마감 5/27 기준 3일 이내인 5/25 에 보면 임박이다."""
    sketch = _digests(today=dt.date(2026, 5, 25))["스케치 담당"]
    soon = [i for i in sketch.items if i.kind == notify.DUE_SOON]
    assert "포스터 제작" in [i.title for i in soon]
    assert "2일 남았습니다" in soon[0].line


def test_10c_방치는_재촉하지_않는_문구다(world):
    sketch = _digests()["스케치 담당"]
    stale = [i for i in sketch.items if i.kind == notify.STALE]
    assert stale
    assert "막는 요인이 없습니다" in stale[0].line
    assert "아직 안" not in stale[0].line


# ── 12 · 13 · 14 ──────────────────────────────────────────────────────


def test_12_VAPID_키가_없어도_앱이_뜨고_푸시만_꺼진다(monkeypatch):
    from app import push

    monkeypatch.setattr(push, "_cached_public_key", None)
    monkeypatch.setattr(push, "_load_vapid", lambda: (_ for _ in ()).throw(RuntimeError("키 없음")))
    assert push.application_server_key() == ""
    assert push.push_enabled() is False

    with app_session() as db:
        # 보낼 상대가 있어도 조용히 실패할 뿐 터지지 않는다
        digest = notify.Digest(user_id=1, user_name="아무개", items=[])
        assert push.send_digest(db, digest) is False


def test_12b_앱은_그대로_뜬다(admin_client):
    assert admin_client.get("/board").status_code == 200
    assert admin_client.get("/settings").status_code == 200


def test_13_미리보기는_보내지_않고_보여준다(world, admin_client):
    res = admin_client.get(
        "/admin/notify/preview", params={"today": TODAY.isoformat(), "format": "json"}
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["date"] == TODAY.isoformat()
    assert data["recipients"] > 0
    assert any(d["items"] for d in data["digests"])
    assert "body" in data["digests"][0]

    # 보내지 않았으므로 기록이 남지 않는다 — 다시 불러도 같은 결과다
    with app_session() as db:
        assert db.scalars(select(models.NotificationLog)).first() is None
    assert admin_client.get(
        "/admin/notify/preview", params={"today": TODAY.isoformat(), "format": "json"}
    ).json()["recipients"] == data["recipients"]


def test_13b_미리보기와_실행은_관리자만(world, client):
    from app.main import app
    from fastapi.testclient import TestClient
    from tests.conftest import login_as

    lead = TestClient(app)
    login_as(lead, "01030003000")
    assert lead.get("/admin/notify/preview").status_code in (403, 404)
    assert lead.post("/admin/notify/run").status_code in (403, 404)


def test_14_구독_기본값이_꺼짐이다(world, admin_client):
    """구독은 사용자가 켜야 생긴다. 계정을 만들었다고 저절로 받지 않는다."""
    with app_session() as db:
        assert db.scalars(select(models.PushSubscription)).first() is None

    page = admin_client.get("/settings")
    assert page.status_code == 200
    assert 'id="push-enable"' in page.text
    assert 'id="push-card"' in page.text

    # 구독이 없으면 보낼 곳이 없다
    from app import push

    with app_session() as db:
        digest = notify.Digest(user_id=world["people"]["스케치 담당"], user_name="스케치 담당",
                               items=[])
        assert push.send_digest(db, digest) is False


# ══════════════════════════════════════════════════════════════════════
# 보완 — 아래 번호는 보완 작업의 수용 기준이다.
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def two_rounds(world):
    """회차를 하나 더 연다.

    Department 행은 회차마다 새로 만들어지므로, 부서 리더를 id 로 찾으면 여기서
    무너진다. 회차가 하나뿐인 픽스처로는 이 버그가 재현되지 않는다.
    """
    with app_session() as db:
        old = db.get(models.Retreat, world["retreat_id"])
        new = models.Retreat(
            name="2027 겨울수련회",
            start_date=dt.date(2027, 1, 14),
            end_date=dt.date(2027, 1, 17),
        )
        db.add(new)
        db.flush()

        depts = {}
        for order, key in enumerate(["sketch", "hebron"]):
            src = next(d for d in old.departments if d.key == key)
            dept = models.Department(
                retreat_id=new.id, key=key, name=src.name,
                color_tag=src.color_tag, sort_order=order,
            )
            db.add(dept)
            db.flush()
            depts[key] = dept.id

        lib = _lib(db, "새 회차 담당 없는 업무", key="hebron", d_week=9)
        run = models.TaskRun(
            library_id=lib.id, retreat_id=new.id, included=True,
            department_id=depts["hebron"], assignee_id=None,
            start_date=dt.date(2026, 12, 1), end_date=dt.date(2026, 12, 20),
            status="대기", blocked_by_run_ids=[],
        )
        db.add(run)
        db.flush()
        run_id = run.id
        db.commit()

    # 옛 회차는 지나갔고 새 회차만 살아 있는 날짜
    return {"retreat_id": new.id, "run_id": run_id, "today": dt.date(2026, 12, 28)}


# ── 보완 1 · 2 ────────────────────────────────────────────────────────


def test_보완01_회차를_두_번_열어도_부서_리더가_잡힌다(two_rounds):
    """User.department_id 는 계정을 만들 때의 회차 행을 가리킨다.
    id 로 비교하면 새 회차에서 리더를 못 찾고 조용히 총무팀으로 떨어진다."""
    with app_session() as db:
        run = db.get(models.TaskRun, two_rounds["run_id"])
        who = notify.recipient_for(db, run)
        assert who is not None
        assert who.name == "헤브론 리더"
        assert who.role == "dept_lead"


def test_보완02_리더가_있으면_총무팀으로_떨어지지_않는다(two_rounds):
    out = {d.user_name: d for d in _build(today=two_rounds["today"])}
    assert "헤브론 리더" in out
    assert "새 회차 담당 없는 업무" in [i.title for i in out["헤브론 리더"].items]
    admin = out.get("총무 김간사")
    assert admin is None or "새 회차 담당 없는 업무" not in [i.title for i in admin.items]


def test_보완02b_공용_함수를_같이_쓴다():
    """소속을 키로 보는 자리가 두 벌이 되면 한쪽만 고쳐진다."""
    from app.domain.departments import department_key_of, users_in_department
    from app.routers import board as board_router

    assert board_router._dept_key_of.__module__ == "app.routers.board"
    assert callable(department_key_of) and callable(users_in_department)
    import inspect

    assert "department_key_of" in inspect.getsource(board_router._dept_key_of)


# ── 보완 3 · 4 ────────────────────────────────────────────────────────


def test_보완03_전송에_실패하면_기록하지_않는다(world):
    with app_session() as db:
        result = notify.run_digests(db, today=TODAY, sender=lambda _db, _d: False)
    assert result["recipients"] > 0
    assert result["sent"] == 0
    assert result["skipped"] == result["recipients"]

    with app_session() as db:
        assert db.scalars(select(models.NotificationLog)).first() is None
        # 다음 날 다시 후보가 된다
        assert notify.build_digests(db, today=TODAY + dt.timedelta(days=1))


def test_보완04_구독자가_0명이면_7일_침묵이_생기지_않는다(world, admin_client):
    """배포 전에는 구독자가 0명이다. 실수로 한 번 눌러도 그 주가 소진되면 안 된다."""
    with app_session() as db:
        assert db.scalars(select(models.PushSubscription)).first() is None

    res = admin_client.post("/admin/notify/run", params={"today": TODAY.isoformat()})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sent"] == 0
    assert body["skipped"] == body["recipients"]

    with app_session() as db:
        assert db.scalars(select(models.NotificationLog)).first() is None
        assert notify.build_digests(db, today=TODAY)     # 그대로 후보다


# ── 보완 5 · 6 ────────────────────────────────────────────────────────


def _fake_subscription(db, user_id, endpoint="https://example.test/a"):
    row = models.PushSubscription(
        user_id=user_id, endpoint=endpoint, p256dh="k", auth="a"
    )
    db.add(row)
    db.flush()
    return row


def test_보완05_일시_실패는_발송함으로_세지_않는다(world, monkeypatch):
    from app import push

    with app_session() as db:
        _fake_subscription(db, world["people"]["스케치 담당"])
        db.commit()

    monkeypatch.setattr(push, "push_enabled", lambda: True)
    monkeypatch.setattr(push, "_send_one", lambda _s, _p: push.RETRY)

    with app_session() as db:
        digest = notify.Digest(
            user_id=world["people"]["스케치 담당"], user_name="스케치 담당",
            items=[notify.Item(notify.OVERDUE, 1, "제목", "줄", "진행 가능", "대기")],
        )
        assert push.send_digest(db, digest) is False        # 보낸 것이 아니다
        assert db.scalars(select(models.PushSubscription)).first() is not None  # 구독은 남는다


def test_보완06_만료만_구독을_지운다(world, monkeypatch):
    from app import push

    with app_session() as db:
        _fake_subscription(db, world["people"]["스케치 담당"])
        db.commit()

    monkeypatch.setattr(push, "push_enabled", lambda: True)
    monkeypatch.setattr(push, "_send_one", lambda _s, _p: push.GONE)

    with app_session() as db:
        digest = notify.Digest(
            user_id=world["people"]["스케치 담당"], user_name="스케치 담당",
            items=[notify.Item(notify.OVERDUE, 1, "제목", "줄", "진행 가능", "대기")],
        )
        assert push.send_digest(db, digest) is False
        assert db.scalars(select(models.PushSubscription)).first() is None      # 지워졌다

    # 성공이면 True 이고 구독도 남는다
    with app_session() as db:
        _fake_subscription(db, world["people"]["스케치 담당"], "https://example.test/b")
        db.commit()
    monkeypatch.setattr(push, "_send_one", lambda _s, _p: push.SENT)
    with app_session() as db:
        digest = notify.Digest(
            user_id=world["people"]["스케치 담당"], user_name="스케치 담당",
            items=[notify.Item(notify.OVERDUE, 1, "제목", "줄", "진행 가능", "대기")],
        )
        assert push.send_digest(db, digest) is True
        assert db.scalars(select(models.PushSubscription)).first() is not None


# ── 보완 7 · 8 ────────────────────────────────────────────────────────


def test_보완07_선행_재촉에_기다리는_쪽의_기한이_함께_나온다(world):
    """'진행 불가' 는 그 담당자에게 안 가므로, 이 문장이 없으면 아무도 급한 줄 모른다."""
    with app_session() as db:
        # 명찰 제작(막힌 쪽)의 마감을 과거로 옮긴다
        db.get(models.TaskRun, world["runs"]["명찰 제작"]).end_date = dt.date(2026, 5, 27)
        db.commit()

    hebron = {d.user_name: d for d in _build()}["헤브론 담당"]
    row = next(i for i in hebron.items if i.kind == notify.UNBLOCK)
    assert "그쪽 마감이 5일 지났습니다" in row.line
    assert "'명찰 제작'" in row.line


def test_보완08_기다리는_쪽이_기한_초과일_때만_총무팀에도_간다(world):
    # 기한 안쪽이면 총무팀에는 가지 않는다 (담당자 한 사람 원칙)
    out = {d.user_name: d for d in _build()}
    admin = out.get("총무 김간사")
    admin_unblock = [i for i in admin.items if i.kind == notify.UNBLOCK] if admin else []
    assert admin_unblock == []

    with app_session() as db:
        db.get(models.TaskRun, world["runs"]["명찰 제작"]).end_date = dt.date(2026, 5, 27)
        db.commit()

    out = {d.user_name: d for d in _build()}
    admin = out["총무 김간사"]
    rows = [i for i in admin.items if i.kind == notify.UNBLOCK]
    assert len(rows) == 1
    assert "그쪽 마감이" in rows[0].line
    # 담당자에게도 그대로 간다 (총무팀은 '더해서' 받는 것이다)
    assert any(i.kind == notify.UNBLOCK for i in out["헤브론 담당"].items)


# ── 보완 9 · 10 · 11 ──────────────────────────────────────────────────


def test_보완09_미리보기가_사람이_읽는_화면이다(world, admin_client):
    page = admin_client.get("/admin/notify/preview", params={"today": TODAY.isoformat()})
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "알림 미리보기" in page.text
    assert "보내지 않습니다" in page.text
    # 맨 위에 "오늘 N명에게 M건"
    assert "명</b>에게" in page.text and "건</b>" in page.text
    # 실제로 갈 문구가 그대로 보인다
    assert "수련회 준비 — 오늘 볼 것" in page.text
    assert "막는 요인이 없습니다" in page.text


def test_보완10_구독자가_0명이면_경고가_뜬다(world, admin_client):
    page = admin_client.get("/admin/notify/preview", params={"today": TODAY.isoformat()})
    assert "지금 실행해도 아무에게도 가지 않습니다" in page.text

    with app_session() as db:
        _fake_subscription(db, world["people"]["스케치 담당"])
        db.commit()

    page = admin_client.get("/admin/notify/preview", params={"today": TODAY.isoformat()})
    assert "지금 실행해도 아무에게도 가지 않습니다" not in page.text


def test_보완11_format_json_이_기존_응답을_준다(world, admin_client):
    res = admin_client.get(
        "/admin/notify/preview", params={"today": TODAY.isoformat(), "format": "json"}
    )
    assert res.status_code == 200
    assert "application/json" in res.headers["content-type"]
    data = res.json()
    for key in ("date", "push_enabled", "recipients", "items", "digests"):
        assert key in data
    assert data["digests"][0]["body"]
