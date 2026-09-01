"""관리자 계정 중복 정리와 재발 방지 (CLAUDE.md 4-12). 수용 기준 1~11.

관리자 계정이 넷이 됐고 그중 셋이 같은 이름이었다. 초대 링크를 한 번 쓰고
다시 열려다 403 이 나자 `create_admin.py` 를 또 돌린 결과다.

**조용한 문제가 아니다** — 총무팀 에스컬레이션은 admin 전원에게 가므로 같은
사람에게 알림이 세 번 간다.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app import models
from app.domain import auth as invites
from scripts import create_admin, healthcheck, merge_users
from tests.conftest import app_session


@pytest.fixture
def admins(client):
    """같은 이름의 관리자 셋 + 다른 사람 하나. 실제로 벌어진 모양 그대로."""
    with app_session() as db:
        rows = [
            models.User(name="박민준", phone_number="01000000001", role="admin"),
            models.User(name="정하윤", phone_number="01000000002", role="admin"),
            models.User(name="박민준", phone_number="01077770001", role="admin"),
            models.User(name="박민준", phone_number="01012345678", role="admin"),
        ]
        db.add_all(rows)
        db.commit()
        return {"first": rows[0].id, "real": rows[2].id, "typo": rows[3].id,
                "other": rows[1].id}


def users_named(db, name):
    return list(db.scalars(select(models.User).where(models.User.name == name)
                           .order_by(models.User.id)))


# ---------------------------------------------------------------- 1. 같은 연락처


def test_01_같은_연락처면_새_계정을_만들지_않고_링크만_재발급한다(admins, capsys):
    with app_session() as db:
        before = db.scalars(select(models.User)).all()
        code = create_admin.create(db, "박민준", "01077770001", force=False)
    assert code == 0

    out = capsys.readouterr().out
    assert "이미 있는 계정입니다" in out
    assert "새 링크를 발급했습니다" in out

    with app_session() as db:
        after = db.scalars(select(models.User)).all()
        assert len(after) == len(before), "계정이 늘었다"
        # 링크는 실제로 새로 났다
        live = db.scalars(select(models.InviteToken).where(
            models.InviteToken.user_id == admins["real"],
            models.InviteToken.used_at.is_(None),
            models.InviteToken.revoked_at.is_(None))).all()
        assert len(live) == 1


def test_01b_비활성_계정이면_다시_켜고_관리자로_되돌린다(admins, capsys):
    with app_session() as db:
        person = db.get(models.User, admins["real"])
        person.is_active = False
        person.role = "member"
        db.commit()

    with app_session() as db:
        create_admin.create(db, "박민준", "01077770001", force=False)
    out = capsys.readouterr().out
    assert "다시 켰습니다" in out and "관리자로 바꿨습니다" in out

    with app_session() as db:
        person = db.get(models.User, admins["real"])
        assert person.is_active and person.role == "admin"


# ---------------------------------------------------------------- 2·3. 같은 이름


def test_02_같은_이름의_관리자가_있으면_멈추고_기존_계정을_보여준다(admins, capsys):
    with app_session() as db:
        before = len(db.scalars(select(models.User)).all())
        code = create_admin.create(db, "박민준", "01099998888", force=False)

    assert code == 1, "멈추지 않았다"
    out = capsys.readouterr().out
    assert "이미 있습니다" in out and "만들지 않았습니다" in out
    assert "01077770001" in out and "01012345678" in out   # 기존 계정을 보여준다
    assert "--reissue" in out                              # 링크만 받는 길을 안내
    assert "--force" in out                                # 동명이인 길도 안내

    with app_session() as db:
        assert len(db.scalars(select(models.User)).all()) == before


def test_03_force_로는_만들_수_있다_동명이인(admins, capsys):
    with app_session() as db:
        code = create_admin.create(db, "박민준", "01099998888", force=True)
    assert code == 0

    out = capsys.readouterr().out
    assert "하나 더 만들었습니다" in out
    assert "알림이 그만큼 갑니다" in out                    # 대가를 말해준다

    with app_session() as db:
        assert len(users_named(db, "박민준")) == 4


# ---------------------------------------------------------------- 4. reissue


def test_04_reissue_는_계정을_만들지_않고_링크만_준다(admins, capsys):
    with app_session() as db:
        before = len(db.scalars(select(models.User)).all())
        code = create_admin.reissue(db, "01012345678")
    assert code == 0

    out = capsys.readouterr().out
    assert "링크를 다시 발급했습니다" in out
    assert "계정을 새로 만들지 않았습니다" in out
    assert "/invite/" in out

    with app_session() as db:
        assert len(db.scalars(select(models.User)).all()) == before


def test_04b_없는_연락처면_있는_관리자를_보여주고_멈춘다(admins, capsys):
    with app_session() as db:
        code = create_admin.reissue(db, "01011112222")
    assert code == 1
    out = capsys.readouterr().out
    assert "계정이 없습니다" in out
    assert "있는 관리자 계정" in out
    assert "01077770001" in out


def test_04c_옛_링크는_재발급하면_함께_취소된다(admins):
    with app_session() as db:
        person = db.get(models.User, admins["typo"])
        old = invites.issue(db, user=person)
        create_admin.reissue(db, "01012345678")

    with app_session() as db:
        live = db.scalars(select(models.InviteToken).where(
            models.InviteToken.user_id == admins["typo"],
            models.InviteToken.revoked_at.is_(None),
            models.InviteToken.used_at.is_(None))).all()
        assert len(live) == 1
        assert live[0].token_hash != invites.hash_token(old)


# ---------------------------------------------------------------- 5. 예시 번호


def test_05_도움말과_안내에_예시_번호가_없다():
    """그대로 복사해 넣어 계정이 하나 더 생겼다."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    # 화면의 입력 안내에도 두지 않는다 — 사람이 실제로 복사하는 자리다
    for name in ("scripts/create_admin.py", "docs/배포-안내.md",
                 "app/templates/admin_users.html"):
        text = (root / name).read_text(encoding="utf-8")
        assert "01012345678" not in text, f"{name} 에 예시 번호가 남아 있다"


# ---------------------------------------------------------------- 6·7·8. 정리


def test_06_apply_없이는_아무것도_바꾸지_않는다(admins):
    with app_session() as db:
        rows = merge_users.survey(db)
        assert len(rows) == 1
        assert rows[0]["name"] == "박민준"
        assert len(rows[0]["people"]) == 3

        result = merge_users.merge(db, keep_id=admins["real"], apply=False)
        assert result["applied"] is False
        assert {p.id for p in result["deactivated"]} == {admins["first"], admins["typo"]}

    with app_session() as db:
        assert all(u.is_active for u in users_named(db, "박민준"))
        assert db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "계정_중복_정리")).all() == []


def test_07_apply_하면_남길_계정만_활성으로_남는다(admins):
    with app_session() as db:
        result = merge_users.merge(db, keep_id=admins["real"], apply=True)
    assert result["applied"] is True

    with app_session() as db:
        assert db.get(models.User, admins["real"]).is_active is True
        assert db.get(models.User, admins["first"]).is_active is False
        assert db.get(models.User, admins["typo"]).is_active is False
        # 다른 사람은 건드리지 않는다
        assert db.get(models.User, admins["other"]).is_active is True

        # 비활성화한 계정의 초대 링크도 함께 죽는다
        live = db.scalars(select(models.InviteToken).where(
            models.InviteToken.user_id == admins["typo"],
            models.InviteToken.revoked_at.is_(None),
            models.InviteToken.used_at.is_(None))).all()
        assert live == []

        logs = list(db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "계정_중복_정리")))
        assert len(logs) == 1
        assert f"id={admins['real']}" in logs[0].summary


def test_08_어느_계정도_지워지지_않는다(admins):
    """지난 회차의 논의와 지출에 작성자로 남아 있다 — 지우면 '누가 썼는지
    모르는 것' 이 된다 (4-12)."""
    with app_session() as db:
        before = {u.id for u in db.scalars(select(models.User))}
        merge_users.merge(db, keep_id=admins["real"], apply=True)

    with app_session() as db:
        after = {u.id for u in db.scalars(select(models.User))}
    assert after == before

    import inspect

    source = inspect.getsource(merge_users)
    assert "db.delete" not in source, "지우는 코드가 있다"


# ---------------------------------------------------------------- 9. 기록


def test_09_비활성화해도_기록과_작성자가_그대로다(admins):
    """옮기면 '누가 썼는가' 가 사실과 달라진다."""
    with app_session() as db:
        retreat = models.Retreat(
            name="회차", start_date=dt.date(2026, 8, 21), end_date=dt.date(2026, 8, 23))
        db.add(retreat)
        db.flush()
        lib = models.TaskLibrary(
            title="포스터 제작", kind="main", default_department_key="sketch",
            related_department_keys=[], related_library_ids=[],
            date_anchor="week", default_d_week=13, default_offset_days=0,
            default_span_days=6)
        db.add(lib)
        db.flush()
        run = models.TaskRun(
            library_id=lib.id, retreat_id=retreat.id, included=True, d_week=13,
            start_date=dt.date(2026, 5, 24), end_date=dt.date(2026, 5, 31),
            status="대기")
        db.add(run)
        db.flush()
        entry = models.DiscussionEntry(
            run_id=run.id, authored_at=dt.date(2026, 5, 25),
            body="스케치팀과 의논함", author_id=admins["typo"],
            author_name="박민준")
        db.add(entry)
        db.add(models.ActivityLog(
            retreat_id=retreat.id, actor_type="user", actor_id=admins["typo"],
            actor_name="박민준", action="상태 변경", target_type="task_run",
            target_id=run.id))
        db.commit()
        entry_id, run_id = entry.id, run.id

    with app_session() as db:
        merge_users.merge(db, keep_id=admins["real"], apply=True)

    with app_session() as db:
        saved = db.get(models.DiscussionEntry, entry_id)
        assert saved is not None
        assert saved.body == "스케치팀과 의논함"
        assert saved.author_id == admins["typo"], "작성자가 옮겨졌다"
        assert saved.author_name == "박민준"

        log = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "상태 변경")).one()
        assert log.actor_id == admins["typo"]

        # 비활성화된 그 계정은 그대로 있다 (로그인만 막힌다)
        person = db.get(models.User, admins["typo"])
        assert person is not None and person.is_active is False


def test_09b_남긴_기록_수를_세어_보여준다(admins):
    """남길 계정을 고를 때 '어느 쪽에 실제 기록이 있나' 가 근거가 된다."""
    with app_session() as db:
        counts = merge_users.trace_counts(db, admins["typo"])
        assert counts == {}                      # 아직 아무 기록도 없다

        rows = merge_users.survey(db)
        person = next(p for p in rows[0]["people"] if p["id"] == admins["typo"])
        assert person["phone"] == "01012345678"
        assert person["traces"] == {}
        assert person["last_seen"] is None


# ---------------------------------------------------------------- 10·11. 자가진단


def test_10_자가진단이_같은_이름_여럿을_문제로_알린다(admins):
    ok, message = healthcheck.check_admin()

    assert ok is False, "중복인데 정상이라고 말한다"
    assert "박민준(3)" in message
    assert "같은 이름이 여럿입니다" in message
    assert "merge_users.py" in message
    assert "알림이 그 수만큼" in message


def test_11_관리자가_하나뿐이면_정상이다(admins):
    with app_session() as db:
        merge_users.merge(db, keep_id=admins["real"], apply=True)
        # 다른 이름의 관리자도 비활성화해 한 명만 남긴다
        db.get(models.User, admins["other"]).is_active = False
        db.commit()

    ok, message = healthcheck.check_admin()
    assert ok is True
    assert "관리자 1명" in message
    assert "박민준" in message
    assert "(" not in message                    # 개수 표시가 붙지 않는다


def test_11b_관리자가_없으면_만드는_법을_알려준다(client):
    ok, message = healthcheck.check_admin()
    assert ok is False
    assert "계정이 없습니다" in message
    assert "create_admin.py" in message
    assert "01012345678" not in message          # 예시 번호를 주지 않는다
