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
    assert "issued=" in response.headers["location"]      # 링크가 함께 발급된다

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
