"""계정 관리 화면 (CLAUDE.md 4-12). 수용 기준 7.

부서를 **키로** 붙이는 것이 이 파일이 지키는 것 — id 로 붙이면 새 회차가
열리는 순간 소속이 끊긴다 (CLAUDE.md 2장).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app import models
from app.domain.departments import department_key_of
from tests.conftest import app_session


@pytest.fixture
def rounds(admin_client):
    """회차 두 개. 같은 부서 키가 회차마다 다른 행으로 존재한다."""
    with app_session() as db:
        ids = {}
        for name, start, end in [
            ("2026 여름수련회", dt.date(2026, 8, 21), dt.date(2026, 8, 23)),
            ("2027 겨울수련회", dt.date(2027, 1, 14), dt.date(2027, 1, 17)),
        ]:
            retreat = models.Retreat(name=name, start_date=start, end_date=end)
            db.add(retreat)
            db.flush()
            for order, (key, dept_name) in enumerate(
                [("sketch", "4 스케치"), ("hebron", "5 헤브론")]
            ):
                db.add(
                    models.Department(
                        retreat_id=retreat.id, key=key, name=dept_name,
                        color_tag="#888", sort_order=order,
                    )
                )
            ids[name] = retreat.id
        db.commit()
        return ids


def test_07_계정을_추가하고_부서는_키로_붙는다(rounds, admin_client):
    response = admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "010-9999-1111",
              "role": "dept_lead", "department_key": "sketch"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "k=" in response.headers["location"]           # 링크가 함께 발급된다

    with app_session() as db:
        person = db.scalars(
            select(models.User).where(models.User.name == "박서진")
        ).first()
        assert person is not None
        assert person.phone_number == "01099991111"        # 숫자만 남는다
        assert person.role == "dept_lead"
        # **키로** 붙었는지 — 어느 회차의 행이든 키가 sketch 면 된다
        assert department_key_of(db, person) == "sketch"


def test_07b_새_회차에서도_소속이_유지된다(rounds, admin_client):
    """id 로 붙이면 여기서 끊긴다."""
    admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "dept_lead", "department_key": "hebron"},
        follow_redirects=False,
    )
    with app_session() as db:
        from app.domain.departments import users_in_department

        found = users_in_department(db, "hebron", role="dept_lead")
        assert [u.name for u in found] == ["박서진"]


def test_07c_권한과_부서를_바꿀_수_있다(rounds, admin_client):
    admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "member", "department_key": "sketch"},
        follow_redirects=False,
    )
    with app_session() as db:
        person_id = db.scalars(
            select(models.User).where(models.User.name == "박서진")
        ).first().id

    assert admin_client.post(
        f"/admin/users/{person_id}/update",
        data={"role": "dept_lead", "department_key": "hebron"},
        follow_redirects=False,
    ).status_code == 303

    with app_session() as db:
        person = db.get(models.User, person_id)
        assert person.role == "dept_lead"
        assert department_key_of(db, person) == "hebron"

    # 부서를 뗄 수도 있다
    admin_client.post(
        f"/admin/users/{person_id}/update",
        data={"role": "member", "department_key": ""},
        follow_redirects=False,
    )
    with app_session() as db:
        assert department_key_of(db, db.get(models.User, person_id)) is None


def test_07d_같은_연락처는_두_번_등록되지_않는다(rounds, admin_client):
    data = {"name": "박서진", "phone_number": "01099991111",
            "role": "member", "department_key": ""}
    admin_client.post("/admin/users/new", data=data, follow_redirects=False)
    again = admin_client.post("/admin/users/new", data=data)
    assert again.status_code == 200
    assert "이미 등록된 연락처" in again.text

    with app_session() as db:
        rows = db.scalars(
            select(models.User).where(models.User.phone_number == "01099991111")
        ).all()
        assert len(rows) == 1


def test_07e_화면이_열리고_사람이_보인다(rounds, admin_client):
    admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "member", "department_key": "sketch"},
        follow_redirects=False,
    )
    page = admin_client.get("/admin/users")
    assert page.status_code == 200
    assert "계정 관리" in page.text
    assert "박서진" in page.text
    assert "삭제 대신 비활성화만 둔 이유" in page.text


def test_07f_총무팀만_들어갈_수_있다(rounds, admin_client, client):
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import login_as

    # 로그인하지 않았으면 로그인 화면으로 돌려보낸다 (401 → /login)
    anonymous = client.get("/admin/users", follow_redirects=False)
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/login"

    with app_session() as db:
        db.add(models.User(name="부서원", phone_number="01055551111", role="member"))
        db.commit()
    member = TestClient(app)
    login_as(member, "01055551111")
    assert member.get("/admin/users").status_code == 403


def test_07g_자기_계정은_비활성화할_수_없다(rounds, admin_client):
    with app_session() as db:
        me = db.scalars(
            select(models.User).where(models.User.role == "admin")
        ).first()
        my_id = me.id

    admin_client.post(
        f"/admin/users/{my_id}/active", data={"active": ""}, follow_redirects=False
    )
    with app_session() as db:
        assert db.get(models.User, my_id).is_active is True


# ══════════════════════════════════════════════════════════════════════
# 연락처 고치기 (4-12). 수용 기준 1~10
#
# 연락처는 계정을 구분하는 열쇠다. 겹치면 **조용히 엉뚱한 계정에 링크가 간다** —
# 그래서 고칠 수는 있되 겹치는 것은 막고, 누구 것인지 말한다.
# ══════════════════════════════════════════════════════════════════════


def make_person(admin_client, name, phone, *, role="member", dept=""):
    admin_client.post(
        "/admin/users/new",
        data={"name": name, "phone_number": phone, "role": role,
              "department_key": dept},
        follow_redirects=False,
    )
    with app_session() as db:
        return db.scalars(
            select(models.User).where(models.User.name == name)).first().id


def save(admin_client, person_id, **fields):
    data = {"role": "member", "department_key": ""}
    data.update(fields)
    return admin_client.post(
        f"/admin/users/{person_id}/update", data=data, follow_redirects=False)


def test_p1_연락처를_고치고_저장할_수_있다(rounds, admin_client):
    person_id = make_person(admin_client, "박서진", "01000000001")

    assert save(admin_client, person_id,
                phone_number="01055556666").status_code == 303

    with app_session() as db:
        assert db.get(models.User, person_id).phone_number == "01055556666"


def test_p2_부서_권한과_같은_저장으로_함께_바뀐다(rounds, admin_client):
    """칸을 따로 두면 어느 것이 저장됐는지 헷갈린다."""
    person_id = make_person(admin_client, "박서진", "01000000001")

    save(admin_client, person_id, phone_number="01055556666",
         role="dept_lead", department_key="hebron")

    with app_session() as db:
        person = db.get(models.User, person_id)
        assert person.phone_number == "01055556666"
        assert person.role == "dept_lead"
        assert department_key_of(db, person) == "hebron"

    # 화면에서도 한 폼이다 — 연락처 칸이 그 줄의 폼에 묶여 있다
    page = admin_client.get("/admin/users").text
    assert f'form="u{person_id}"' in page
    assert 'name="phone_number"' in page


def test_p3_하이픈을_넣어도_숫자만_남는다(rounds, admin_client):
    person_id = make_person(admin_client, "박서진", "01000000001")

    save(admin_client, person_id, phone_number="010-5555-6666")

    with app_session() as db:
        assert db.get(models.User, person_id).phone_number == "01055556666"


def test_p4_빈_값으로는_저장되지_않고_이유가_보인다(rounds, admin_client):
    """연락처가 없으면 나중에 그 계정을 찾을 길이 없다."""
    person_id = make_person(admin_client, "박서진", "01000000001")

    response = save(admin_client, person_id, phone_number="   ")
    assert response.status_code == 303

    page = admin_client.get("/admin/users").text
    assert "연락처를 비울 수 없습니다" in page
    with app_session() as db:
        assert db.get(models.User, person_id).phone_number == "01000000001"

    # 숫자가 하나도 없는 값도 마찬가지다
    save(admin_client, person_id, phone_number="없음")
    with app_session() as db:
        assert db.get(models.User, person_id).phone_number == "01000000001"


def test_p5_다른_계정이_쓰는_번호면_거절하고_누구_것인지_말한다(rounds, admin_client):
    make_person(admin_client, "정하윤", "01077778888")
    person_id = make_person(admin_client, "박서진", "01000000001")

    response = save(admin_client, person_id, phone_number="01077778888")
    assert response.status_code == 303

    page = admin_client.get("/admin/users").text
    assert "이미 정하윤 님이 쓰고 있습니다" in page

    with app_session() as db:
        assert db.get(models.User, person_id).phone_number == "01000000001"
        # 다른 사람 것도 그대로다
        other = db.scalars(select(models.User).where(
            models.User.name == "정하윤")).one()
        assert other.phone_number == "01077778888"


def test_p6_비활성_계정이_놓은_번호는_곧바로_쓸_수_있다(rounds, admin_client):
    """**이 규칙은 뒤집힌 것이다.** 예전에는 비활성 계정이 쓰던 번호도
    거절했다 — "나중에 되살리면 그때 겹친다" 는 이유였다.

    그런데 그러면 중복을 정리한 뒤 **남긴 계정에 실제 번호를 넣을 수 없다.**
    정리를 끝낼 방법이 없어진다. 그래서 비활성화할 때 번호를 놓게 하고
    (로그인은 초대 링크로 하지 번호로 하지 않는다), 되살릴 때 그 사이 아무도
    안 쓰고 있으면 돌려준다 — 겹침은 그때 판단한다 (4-12)."""
    sleeping = make_person(admin_client, "정하윤", "01077778888")
    admin_client.post(f"/admin/users/{sleeping}/active", data={"active": ""},
                      follow_redirects=False)

    person_id = make_person(admin_client, "박서진", "01000000001")
    assert save(admin_client, person_id,
                phone_number="01077778888").status_code == 303

    with app_session() as db:
        assert db.get(models.User, person_id).phone_number == "01077778888"
        # 놓은 쪽은 번호를 쥐고 있지 않지만 원래 번호는 남아 있다
        gone = db.get(models.User, sleeping)
        assert gone.phone_number == ""
        assert gone.retired_phone == "01077778888"


def test_p7_자기_계정의_연락처도_고칠_수_있다(rounds, admin_client):
    with app_session() as db:
        me = db.scalars(select(models.User).where(
            models.User.name == "총무 김간사")).one()
        my_id, my_role = me.id, me.role

    assert save(admin_client, my_id, phone_number="01033334444",
                role=my_role).status_code == 303

    with app_session() as db:
        assert db.get(models.User, my_id).phone_number == "01033334444"


def test_p8_총무팀이_아니면_403(rounds, admin_client, client):
    person_id = make_person(admin_client, "박서진", "01000000001")
    with app_session() as db:
        person = db.get(models.User, person_id)
        person.role = "dept_lead"
        db.commit()

    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import login_as

    lead = TestClient(app)
    login_as(lead, "01000000001")

    response = lead.post(f"/admin/users/{person_id}/update",
                         data={"role": "admin", "phone_number": "01055556666"},
                         follow_redirects=False)
    assert response.status_code == 403

    with app_session() as db:
        person = db.get(models.User, person_id)
        assert person.phone_number == "01000000001"
        assert person.role == "dept_lead"           # 권한도 안 올라갔다


def test_p9_연락처를_바꿔도_살아_있는_링크가_죽지_않는다(rounds, admin_client):
    """링크는 계정에 붙지 번호에 붙지 않는다."""
    from app.domain import auth as invites

    person_id = make_person(admin_client, "박서진", "01000000001")
    with app_session() as db:
        person = db.get(models.User, person_id)
        raw = invites.issue(db, user=person)
        before = invites.live_token(db, user=person)
        assert before is not None
        before_hash = before.token_hash

    save(admin_client, person_id, phone_number="01055556666")

    with app_session() as db:
        person = db.get(models.User, person_id)
        token = invites.live_token(db, user=person)
        assert token is not None, "연락처를 바꿨다고 링크가 죽었다"
        assert token.token_hash == before_hash

    # 그 링크로 실제 로그인도 된다
    from fastapi.testclient import TestClient

    from app.main import app

    fresh = TestClient(app)
    assert fresh.get(f"/invite/{raw}", follow_redirects=False).status_code == 303


def test_p10_바뀐_값이_활동_기록에_남고_안_바뀌었으면_남지_않는다(rounds, admin_client):
    person_id = make_person(admin_client, "박서진", "01000000001")

    save(admin_client, person_id, phone_number="01055556666")
    with app_session() as db:
        log = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "계정_변경",
            models.ActivityLog.target_id == person_id)
            .order_by(models.ActivityLog.id.desc())).first()
        assert log.before_value["phone"] == "01000000001"
        assert log.after_value["phone"] == "01055556666"
        assert "01000000001 → 01055556666" in log.summary

    # 같은 값으로 다시 저장하면 연락처는 기록에 넣지 않는다
    save(admin_client, person_id, phone_number="01055556666")
    with app_session() as db:
        log = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "계정_변경",
            models.ActivityLog.target_id == person_id)
            .order_by(models.ActivityLog.id.desc())).first()
        assert "phone" not in log.before_value
        assert "phone" not in log.after_value


# ══════════════════════════════════════════════════════════════════════
# 비활성 계정은 연락처를 붙들지 않는다 (4-12). 수용 기준 1~10
#
# 삭제로 풀지 않는다 — 지운 계정이 남긴 논의·첨부의 작성자가 사라진다.
# 막힌 것은 삭제가 없어서가 아니라 **비활성 계정이 번호를 놓을 방법이 없어서**다.
# ══════════════════════════════════════════════════════════════════════


def deactivate(admin_client, person_id):
    return admin_client.post(f"/admin/users/{person_id}/active",
                             data={"active": ""}, follow_redirects=False)


def reactivate(admin_client, person_id):
    return admin_client.post(f"/admin/users/{person_id}/active",
                             data={"active": "on"}, follow_redirects=False)


def test_r1_비활성화하면_번호를_놓고_원래_번호는_남는다(rounds, admin_client):
    person_id = make_person(admin_client, "박서진", "01077778888")

    assert deactivate(admin_client, person_id).status_code == 303

    with app_session() as db:
        person = db.get(models.User, person_id)
        assert person.is_active is False
        assert person.phone_number == ""
        assert person.retired_phone == "01077778888"
        assert person.holds_phone is False
        assert person.shown_phone == "01077778888"   # 누구였는지는 남는다


def test_r2_놓은_번호를_다른_활성_계정이_곧바로_쓸_수_있다(rounds, admin_client):
    """중복을 정리한 뒤 남긴 계정에 실제 번호를 넣는 길 — 이것이 목적이다."""
    old_one = make_person(admin_client, "박민준", "01077770001")
    keeper = make_person(admin_client, "박민준2", "01000000001")

    deactivate(admin_client, old_one)
    assert save(admin_client, keeper, phone_number="01077770001").status_code == 303

    with app_session() as db:
        assert db.get(models.User, keeper).phone_number == "01077770001"


def test_r3_다시_활성화하면_원래_번호가_돌아온다(rounds, admin_client):
    person_id = make_person(admin_client, "박서진", "01077778888")
    deactivate(admin_client, person_id)
    reactivate(admin_client, person_id)

    with app_session() as db:
        person = db.get(models.User, person_id)
        assert person.is_active is True
        assert person.phone_number == "01077778888"
        assert person.retired_phone is None          # 다 돌려줬으니 비운다


def test_r4_그_사이_누가_쓰고_있으면_되돌리지_않고_이유를_말한다(rounds, admin_client):
    sleeping = make_person(admin_client, "정하윤", "01077778888")
    deactivate(admin_client, sleeping)

    # 그 번호를 다른 사람이 가져간다
    taker = make_person(admin_client, "박서진", "01000000001")
    save(admin_client, taker, phone_number="01077778888")

    reactivate(admin_client, sleeping)

    page = admin_client.get("/admin/users").text
    assert "되돌리지 못했습니다" in page
    assert "박서진" in page                          # 누가 쓰고 있는지 말한다

    with app_session() as db:
        person = db.get(models.User, sleeping)
        assert person.is_active is True              # 되살아나긴 했다
        assert person.phone_number == ""             # 번호는 비었다
        assert person.retired_phone == "01077778888" # 원래 번호는 그대로 남는다
        assert db.get(models.User, taker).phone_number == "01077778888"

    # 되살아난 뒤에는 다른 번호로 고칠 수 있다
    assert save(admin_client, sleeping, phone_number="01055556666").status_code == 303
    with app_session() as db:
        assert db.get(models.User, sleeping).phone_number == "01055556666"


def test_r5_이미_비활성인_기존_계정도_한_번_정리된다(rounds, admin_client):
    """이 규칙이 생기기 전에 비활성화된 계정은 여전히 번호를 쥐고 있다."""
    from sqlalchemy import text as sql

    from app.db import _release_inactive_phones

    person_id = make_person(admin_client, "박서진", "01077778888")
    with app_session() as db:
        # 옛 상태를 흉내낸다 — 비활성인데 번호를 그대로 쥐고 있다
        db.execute(sql("UPDATE users SET is_active = 0, phone_number = :p,"
                       " retired_phone = NULL WHERE id = :i"),
                   {"p": "01077778888", "i": person_id})
        db.commit()

    _release_inactive_phones()

    with app_session() as db:
        person = db.get(models.User, person_id)
        assert person.phone_number == ""
        assert person.retired_phone == "01077778888"

    # 두 번 돌려도 덧쓰지 않는다
    _release_inactive_phones()
    with app_session() as db:
        assert db.get(models.User, person_id).retired_phone == "01077778888"


def test_r6_화면에서_비활성_계정의_원래_번호가_보인다(rounds, admin_client):
    person_id = make_person(admin_client, "박서진", "01077778888")
    deactivate(admin_client, person_id)

    page = admin_client.get("/admin/users").text
    assert "01077778888" in page                     # 누구였는지 알 수 있다
    assert "(반납)" in page
    assert 'class="mono retired"' in page
    # 그 줄에는 고칠 수 있는 입력칸이 없다
    assert f'form="u{person_id}" class="find sm phone mono"' not in page


def test_r7_비활성_계정의_연락처는_고칠_수_없다(rounds, admin_client):
    person_id = make_person(admin_client, "박서진", "01077778888")
    deactivate(admin_client, person_id)

    save(admin_client, person_id, phone_number="01055556666")

    page = admin_client.get("/admin/users").text
    assert "비활성 계정이라 연락처를 고칠 수 없습니다" in page
    assert "먼저 다시 활성화" in page

    with app_session() as db:
        person = db.get(models.User, person_id)
        assert person.phone_number == ""
        assert person.retired_phone == "01077778888"


def test_r8_활성_계정끼리는_여전히_겹칠_수_없다(rounds, admin_client):
    make_person(admin_client, "정하윤", "01077778888")
    person_id = make_person(admin_client, "박서진", "01000000001")

    save(admin_client, person_id, phone_number="01077778888")

    page = admin_client.get("/admin/users").text
    assert "이미 정하윤 님이 쓰고 있습니다" in page
    with app_session() as db:
        assert db.get(models.User, person_id).phone_number == "01000000001"


def test_r9_활성_변경이_활동_기록에_번호까지_남는다(rounds, admin_client):
    """조용히 사라지거나 조용히 돌아오지 않게 한다."""
    person_id = make_person(admin_client, "박서진", "01077778888")

    deactivate(admin_client, person_id)
    with app_session() as db:
        log = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "계정_활성_변경")
            .order_by(models.ActivityLog.id.desc())).first()
        assert log.summary == "박서진: 비활성 · 연락처 01077778888 반납"

    reactivate(admin_client, person_id)
    with app_session() as db:
        log = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "계정_활성_변경")
            .order_by(models.ActivityLog.id.desc())).first()
        assert log.summary == "박서진: 활성 · 연락처 01077778888 되돌림"

    # 되돌리지 못한 경우도 남는다
    deactivate(admin_client, person_id)
    taker = make_person(admin_client, "정하윤", "01000000001")
    save(admin_client, taker, phone_number="01077778888")
    reactivate(admin_client, person_id)
    with app_session() as db:
        log = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "계정_활성_변경")
            .order_by(models.ActivityLog.id.desc())).first()
        assert "되돌리지 못함(정하윤 사용 중)" in log.summary


def test_r10_번호가_비어도_초대_링크는_멀쩡하다(rounds, admin_client):
    """링크는 계정에 붙지 번호에 붙지 않는다."""
    from app.domain import auth as invites

    person_id = make_person(admin_client, "박서진", "01077778888")
    deactivate(admin_client, person_id)

    with app_session() as db:
        person = db.get(models.User, person_id)
        assert person.phone_number == ""
        person.is_active = True          # 번호는 비운 채로 되살린다
        db.commit()
        raw = invites.issue(db, user=person)

    from fastapi.testclient import TestClient

    from app.main import app

    fresh = TestClient(app)
    assert fresh.get(f"/invite/{raw}", follow_redirects=False).status_code == 303
    # 번호 없이도 화면이 열린다
    assert fresh.get("/board").status_code in (200, 303)


def test_r11_번호를_놓은_계정이_여럿이어도_괜찮다(rounds, admin_client):
    """예전의 전체 유니크 인덱스는 빈 번호가 둘이 되는 것을 막았다."""
    a = make_person(admin_client, "가나", "01011110001")
    b = make_person(admin_client, "다라", "01011110002")

    deactivate(admin_client, a)
    deactivate(admin_client, b)

    with app_session() as db:
        assert db.get(models.User, a).phone_number == ""
        assert db.get(models.User, b).phone_number == ""
        assert db.get(models.User, a).retired_phone == "01011110001"
        assert db.get(models.User, b).retired_phone == "01011110002"


# ════════════════════════════════════════════════════════════════════
#  초대 링크는 완성된 채로 나간다 (4-12)
# ════════════════════════════════════════════════════════════════════
#
# 전에는 `https://<내-주소>/invite/…` 로 찍고 사람이 앞부분을 손으로 갈아
# 끼웠는데, 그러다 **토큰까지 건드려 링크가 깨졌습니다** — 하루에 대여섯 번.


def test_u01_완성된_주소가_나온다():
    from app import config
    from app.domain import auth as invites

    made = invites.invite_url("abc123")
    assert made == f"{config.BASE_URL}/invite/abc123"
    assert "<" not in made and ">" not in made, "자리표시자가 남았다"
    assert made.startswith("http"), "붙여넣어 바로 열리는 형태가 아니다"


def test_u02_환경변수로_주소를_바꾼다(monkeypatch):
    import importlib

    from app import config
    from app.domain import auth as invites

    monkeypatch.setenv("DCB_BASE_URL", "https://내주소.example.com/")
    importlib.reload(config)
    try:
        # 뒤의 / 는 떼고 붙인다 — 안 그러면 //invite 가 된다
        assert config.BASE_URL == "https://내주소.example.com"
        assert invites.invite_url("tok") == "https://내주소.example.com/invite/tok"
    finally:
        monkeypatch.delenv("DCB_BASE_URL", raising=False)
        importlib.reload(config)

    # 직접 넘겨도 된다
    assert invites.invite_url("tok", base="https://other.example.com/") \
        == "https://other.example.com/invite/tok"


def test_u03_스크립트가_자리표시자를_찍지_않는다():
    """`<내-주소>` 를 출력하는 자리가 하나라도 남으면 또 손으로 고치게 된다."""
    for path in ("scripts/create_admin.py", "scripts/merge_users.py",
                 "scripts/healthcheck.py"):
        source = open(path, encoding="utf-8").read()
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped.startswith("print("):
                continue        # 주석·독스트링의 설명은 봐도 된다
            assert "<내-주소>" not in line, f"{path} 가 자리표시자를 찍는다: {line}"

    # create_admin 은 공용 헬퍼로 만든다 — 주소를 두 곳에서 만들지 않는다
    made = open("scripts/create_admin.py", encoding="utf-8").read()
    assert "invites.invite_url(raw)" in made


def test_u04_화면도_완성된_주소를_보여준다(admin_client):
    """앱은 127.0.0.1 에만 열려 있어서 `request.base_url` 은 바깥 주소가
    아니다 — 그걸 복사해 보내면 받는 사람 브라우저에서 열리지 않는다."""
    from app import config

    with app_session() as db:
        person = models.User(
            name="새 사람", phone_number="01077778888", role="member")
        db.add(person)
        db.commit()
        person_id = person.id

    issued = admin_client.post(
        f"/admin/users/{person_id}/invite", follow_redirects=True)
    assert issued.status_code == 200

    text = issued.text
    assert f"{config.BASE_URL}/invite/" in text, "완성된 주소가 아니다"
    assert "127.0.0.1" not in text and "testserver" not in text
    assert "<내-주소>" not in text

    view = open("app/templates/admin_users.html", encoding="utf-8").read()
    assert "request.base_url" not in view, "화면이 자기 주소를 다시 만든다"


def test_u05_자가진단이_주소를_손으로_받지_않아도_된다():
    source = open("scripts/healthcheck.py", encoding="utf-8").read()
    assert "else config.BASE_URL" in source
    assert "from app import config" in source
