"""초대 링크 로그인 (CLAUDE.md 4-12).

수용 기준 2~6, 8, 9 에 대응한다.

토큰 원문을 저장하지 않는 것이 이 파일이 지키는 핵심이다 — DB 파일이 새면
링크가 그대로 새는 구조를 만들지 않기 위해서다.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from sqlalchemy import select

from app import models
from app.domain import auth as invites
from tests.conftest import app_session, login_as

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def person(admin_client):
    """총무팀이 만든 계정 하나 (아직 링크를 쓰지 않은 상태)."""
    with app_session() as db:
        row = models.User(name="스케치 담당", phone_number="01088887777", role="member")
        db.add(row)
        db.commit()
        raw = invites.issue(db, user=row)
        return {"user_id": row.id, "token": raw}


# ── 2 ─────────────────────────────────────────────────────────────────


def test_02_링크로_들어오고_두_번째는_거부된다(person, client):
    first = client.get(f"/invite/{person['token']}", follow_redirects=False)
    assert first.status_code == 303
    assert first.headers["location"].startswith("/board")

    # 로그인이 실제로 붙었다
    assert client.get("/board").status_code == 200

    # 같은 링크를 다시 쓰면 거부된다
    second = client.get(f"/invite/{person['token']}", follow_redirects=False)
    assert second.status_code == 403
    assert "이미 사용한 링크" in second.text


# ── 3 ─────────────────────────────────────────────────────────────────


def test_03_7일_지난_링크는_거부된다(person, client):
    with app_session() as db:
        token = db.scalars(
            select(models.InviteToken).where(
                models.InviteToken.user_id == person["user_id"]
            )
        ).first()
        assert (token.expires_at - token.created_at).days == invites.INVITE_TTL_DAYS
        token.expires_at = dt.datetime.now() - dt.timedelta(minutes=1)
        db.commit()

    response = client.get(f"/invite/{person['token']}", follow_redirects=False)
    assert response.status_code == 403
    assert "만료된 링크" in response.text
    assert "7일" in response.text


# ── 4 ─────────────────────────────────────────────────────────────────


def test_04_토큰_원문이_DB_에_없다(person):
    raw = person["token"]
    with app_session() as db:
        token = db.scalars(
            select(models.InviteToken).where(
                models.InviteToken.user_id == person["user_id"]
            )
        ).first()
        assert token.token_hash != raw
        assert len(token.token_hash) == 64            # sha256 hex
        assert token.token_hash == invites.hash_token(raw)
        # 어느 칸에도 원문이 들어 있지 않다
        assert not hasattr(token, "token")
        for column in token.__table__.columns:
            assert getattr(token, column.name) != raw


def test_04b_모델에_원문_칸_자체가_없다():
    names = {c.name for c in models.InviteToken.__table__.columns}
    assert "token_hash" in names
    assert "token" not in names


# ── 5 ─────────────────────────────────────────────────────────────────


def test_05_총무팀이_재발급하면_옛_링크가_죽는다(person, admin_client, client):
    old = person["token"]
    response = admin_client.post(
        f"/admin/users/{person['user_id']}/invite", follow_redirects=False
    )
    assert response.status_code == 303
    new = response.headers["location"].split("issued=")[1].split("&")[0]
    assert new != old

    # 옛 링크는 취소됐다 — 재발급했는데 옛 것이 살아 있으면 "한 번 쓰면 만료"가 뜻을 잃는다
    assert client.get(f"/invite/{old}", follow_redirects=False).status_code == 403
    assert client.get(f"/invite/{new}", follow_redirects=False).status_code == 303


def test_05b_총무팀이_취소할_수_있다(person, admin_client, client):
    assert admin_client.post(
        f"/admin/users/{person['user_id']}/revoke", follow_redirects=False
    ).status_code == 303
    response = client.get(f"/invite/{person['token']}", follow_redirects=False)
    assert response.status_code == 403
    assert "취소된 링크" in response.text


def test_05c_비활성화하면_링크도_함께_죽는다(person, admin_client, client):
    admin_client.post(
        f"/admin/users/{person['user_id']}/active", data={"active": ""},
        follow_redirects=False,
    )
    response = client.get(f"/invite/{person['token']}", follow_redirects=False)
    assert response.status_code == 403


# ── 6 ─────────────────────────────────────────────────────────────────


def test_06_SECRET_KEY_가_고정이라_재시작해도_유지된다(tmp_path, monkeypatch):
    """매번 새로 만들면 서버를 켤 때마다 전원이 로그아웃된다."""
    from app import config

    # 환경변수가 있으면 그것을 쓴다 (운영에서 권장하는 길)
    monkeypatch.setenv("DCB_SECRET_KEY", "고정된-키")
    assert config._secret_key() == "고정된-키"

    # 없으면 데이터 폴더에 만들어 두고, 다음 번에도 같은 값을 읽는다
    monkeypatch.delenv("DCB_SECRET_KEY", raising=False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    first = config._secret_key()
    saved = tmp_path / "secret_key.txt"
    assert saved.exists()
    assert len(first) >= 32
    assert config._secret_key() == first           # 재시작해도 같다
    assert saved.read_text(encoding="utf-8").strip() == first


def test_06b_세션은_90일짜리다():
    from app.config import SESSION_MAX_AGE

    assert SESSION_MAX_AGE == 60 * 60 * 24 * 90


# ── 8 ─────────────────────────────────────────────────────────────────


def test_08_사용자_삭제_경로가_없다(person, admin_client):
    """지난 회차 기록의 작성자가 사라지면 안 된다. 비활성화만 둔다."""
    from app.main import app

    # app.routes 에는 경로가 없는 감싸개가 섞인다. 스펙으로 보는 편이 확실하다.
    spec = app.openapi()["paths"]
    rows = {path: methods for path, methods in spec.items()
            if path.startswith("/admin/users")}
    assert rows, "계정 관리 경로가 있어야 한다"
    for path, methods in rows.items():
        assert "delete" not in path and "remove" not in path
        assert "delete" not in {m.lower() for m in methods}
    assert "/admin/users/{user_id}/active" in rows      # 비활성화는 있다

    # 비활성화는 되고, 기록은 남는다
    admin_client.post(
        f"/admin/users/{person['user_id']}/active", data={"active": ""},
        follow_redirects=False,
    )
    with app_session() as db:
        row = db.get(models.User, person["user_id"])
        assert row is not None and row.is_active is False


def test_08b_비활성_계정은_링크가_있어도_못_들어온다(person, client):
    with app_session() as db:
        db.get(models.User, person["user_id"]).is_active = False
        db.commit()
    response = client.get(f"/invite/{person['token']}", follow_redirects=False)
    assert response.status_code == 403
    assert "비활성화된 계정" in response.text


# ── 9 ─────────────────────────────────────────────────────────────────


def test_09_SMS_코드가_남아_있지_않다():
    assert not (ROOT / "app" / "sms.py").exists()
    assert not (ROOT / "app" / "routers" / "auth.py").exists()

    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "send_auth_code" not in text, path
        assert "DEV_MODE" not in text, path
        assert "AuthCode" not in text, path
    assert not hasattr(models, "AuthCode")


def test_09b_개발용_인증번호_화면이_없다(client):
    page = client.get("/login")
    assert page.status_code == 200
    assert "data-dev-code" not in page.text
    assert 'name="code"' not in page.text
    assert "초대 링크" in page.text

    # 옛 경로도 사라졌다
    assert client.post("/login/code", data={"phone_number": "01011112222"}).status_code == 404
    assert client.post("/login/verify", data={}).status_code == 404


def test_09c_템플릿에도_인증번호_입력칸이_없다():
    for path in (ROOT / "app" / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "data-dev-code" not in text, path
        assert "인증번호 받기" not in text, path


# ── 10 ────────────────────────────────────────────────────────────────


def test_10_기본_시드에_자리표시자_계정이_없다(client):
    """자리표시자 계정을 심어 두면 배포 뒤에도 남아 담당자 후보에 섞인다."""
    import seed as seed_module

    seed_module.seed()              # demo=False 가 기본이다

    with app_session() as db:
        assert db.scalars(select(models.User)).all() == []
        assert db.scalars(select(models.Retreat)).first() is not None   # 실제 이력은 남는다
        assert db.scalars(select(models.TaskLibrary)).first() is not None


def test_10b_demo_로_부르면_눌러볼_계정이_생긴다(client):
    import seed as seed_module

    seed_module.seed(demo=True)
    with app_session() as db:
        assert db.scalars(select(models.User)).all()


def test_10c_로그인_방법을_안내한다():
    """첫 관리자는 스크립트로 만든다 — 화면에 들어가려면 이미 관리자여야 하므로."""
    assert (ROOT / "scripts" / "create_admin.py").exists()
