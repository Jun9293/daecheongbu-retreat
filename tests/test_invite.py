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
    # 원문은 URL 을 타지 않는다 — 화면에서 꺼낸다
    page = admin_client.get(response.headers["location"])
    new = page.text.split("/invite/")[1].split('"')[0]
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
    """매번 새로 만들면 서버를 켤 때마다 전원이 로그아웃된다.

    **이 테스트가 통과하는데도 실전에서 끊길 수 있었다.** 여기서 보는 것은
    "한 프로세스 안에서 두 번 부르면 같은 값" 까지다. 파일이 실제로 **남았는지**,
    쓰기가 조용히 실패하지는 않았는지는 보지 않았다 — 그 경우가 바로
    "재시작할 때마다 로그인이 풀린다" 인데 아무 오류도 나지 않는다.
    그쪽은 `tests/test_secret_key.py` 가 본다.
    """
    from app import config

    # 환경변수가 있으면 그것을 쓴다 (운영에서 권장하는 길)
    monkeypatch.setenv("DCB_SECRET_KEY", "고정된-키")
    key, source = config._secret_key()
    assert key == "고정된-키"
    assert "환경변수" in source                     # 어디서 왔는지 함께 돌려준다

    # 없으면 데이터 폴더에 만들어 두고, 다음 번에도 같은 값을 읽는다
    monkeypatch.delenv("DCB_SECRET_KEY", raising=False)
    monkeypatch.setattr(config, "SECRET_KEY_PATH", tmp_path / "secret_key.txt")
    first, made = config._secret_key()
    saved = tmp_path / "secret_key.txt"
    assert saved.exists()
    assert len(first) >= 32
    assert "새로 만듦" in made
    again, reread = config._secret_key()           # 재시작해도 같다
    assert again == first
    assert "파일" in reread
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


# ══════════════════════════════════════════════════════════════════════
# 마무리 — 원문이 URL 을 타지 않는 것과 부서 배정. 아래 번호는 그 작업 기준이다.
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def with_departments(admin_client):
    """실제 Department 행이 있는 회차 하나."""
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회",
            start_date=dt.date(2026, 8, 21),
            end_date=dt.date(2026, 8, 23),
        )
        db.add(retreat)
        db.flush()
        for order, (key, name) in enumerate(
            [("sketch", "4 스케치"), ("hebron", "5 헤브론")]
        ):
            db.add(
                models.Department(
                    retreat_id=retreat.id, key=key, name=name,
                    color_tag="#888", sort_order=order,
                )
            )
        db.commit()
        return retreat.id


def _live_tokens(user_id: int) -> list[str]:
    with app_session() as db:
        return [
            t.token_hash
            for t in db.scalars(
                select(models.InviteToken).where(
                    models.InviteToken.user_id == user_id,
                    models.InviteToken.used_at.is_(None),
                    models.InviteToken.revoked_at.is_(None),
                )
            )
        ]


# ── 마무리 1 · 2 ──────────────────────────────────────────────────────


def test_마무리01_계정을_만들어도_주소창에_원문이_없다(with_departments, admin_client):
    """총무팀은 이 링크를 자기가 쓰는 게 아니라 복사해서 보낸다.
    주소창에 실리면 7일 내내 살아 있는 링크가 방문 기록에 남는다."""
    response = admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "member", "department_key": "sketch"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]

    with app_session() as db:
        person = db.scalars(
            select(models.User).where(models.User.name == "박서진")
        ).first()
    # 화면에서 원문을 꺼내 그것이 URL 어디에도 없는지 본다
    page = admin_client.get(location)
    raw = page.text.split("/invite/")[1].split('"')[0]
    assert len(raw) > 20
    assert invites.hash_token(raw) in _live_tokens(person.id)   # 진짜 그 링크다

    assert raw not in location
    assert "issued=" not in location
    assert raw not in str(page.url)


def test_마무리01b_재발급도_마찬가지다(with_departments, admin_client, person):
    response = admin_client.post(
        f"/admin/users/{person['user_id']}/invite", follow_redirects=False
    )
    location = response.headers["location"]
    page = admin_client.get(location)
    raw = page.text.split("/invite/")[1].split('"')[0]
    assert raw not in location
    assert raw not in str(page.url)


def test_마무리02_서버가_보는_URL_에도_원문이_없다(with_departments, admin_client):
    """접속 로그에 남는 것은 경로와 쿼리다. 거기에 원문이 있으면 안 된다."""
    response = admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "member", "department_key": "sketch"},
        follow_redirects=False,
    )
    location = response.headers["location"]
    page = admin_client.get(location)
    raw = page.text.split("/invite/")[1].split('"')[0]

    # 리다이렉트를 따라간 뒤의 최종 URL (= 서버 접속 로그에 남는 것)
    with app_session() as db:
        person_id = db.scalars(
            select(models.User).where(models.User.name == "박서진")
        ).first().id
    followed = admin_client.post(
        f"/admin/users/{person_id}/invite", follow_redirects=True
    )
    fresh = followed.text.split("/invite/")[1].split('"')[0]
    for url in (location, str(page.url), str(followed.url)):
        assert raw not in url
        assert fresh not in url
    # 쿼리에는 한 번 쓰면 사라지는 키만 있다
    assert location.startswith("/admin/users?k=")
    key = location.split("k=")[1]
    assert key != raw and raw not in key


# ── 마무리 3 ──────────────────────────────────────────────────────────


def test_마무리03_새로고침하면_링크가_다시_나오지_않는다(with_departments, admin_client):
    response = admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "member", "department_key": "sketch"},
        follow_redirects=False,
    )
    location = response.headers["location"]

    first = admin_client.get(location)
    assert "/invite/" in first.text
    assert "한 번만 보입니다" in first.text

    again = admin_client.get(location)                 # 새로고침
    assert "/invite/" not in again.text
    assert "한 번만 보입니다" not in again.text


def test_마무리03b_꺼내는_자리는_한_번만_준다():
    key = invites.stash("비밀-원문")
    assert invites.take(key) == "비밀-원문"
    assert invites.take(key) is None
    assert invites.take("없는키") is None
    assert invites.take(None) is None


# ── 마무리 4 · 5 ──────────────────────────────────────────────────────


def test_마무리04_없는_부서_키는_목록에_없다(with_departments, admin_client):
    page = admin_client.get("/admin/users")
    assert 'value="sketch"' in page.text
    assert 'value="hebron"' in page.text
    # 어느 회차에도 없는 부서는 고를 수 없다
    assert 'value="saechingu"' not in page.text
    assert 'value="koram"' not in page.text


def test_마무리04b_없는_부서로_저장하려_하면_막힌다(with_departments, admin_client):
    """목록에 없어도 손으로 보낼 수 있다. 조용히 None 으로 떨어뜨리지 않는다."""
    response = admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "member", "department_key": "saechingu"},
    )
    assert response.status_code == 200
    assert "이번 회차" in response.text and "없는 부서라 배정할 수 없습니다" in response.text
    assert "새친구팀" in response.text

    with app_session() as db:
        assert db.scalars(
            select(models.User).where(models.User.name == "박서진")
        ).first() is None                              # 계정도 만들어지지 않는다


def test_마무리04c_변경할_때도_막힌다(with_departments, admin_client):
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

    response = admin_client.post(
        f"/admin/users/{person_id}/update",
        data={"role": "member", "department_key": "koram"},
    )
    assert response.status_code == 200
    assert "이번 회차" in response.text and "없는 부서라 배정할 수 없습니다" in response.text

    with app_session() as db:
        from app.domain.departments import department_key_of

        # 원래 부서가 그대로다 — 조용히 떨어지지 않았다
        assert department_key_of(db, db.get(models.User, person_id)) == "sketch"


# ── 마무리 5 ──────────────────────────────────────────────────────────


def test_마무리05_배정에_실패했는데_성공_메시지가_뜨지_않는다(with_departments, admin_client):
    response = admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "member", "department_key": "saechingu"},
    )
    assert "배정할 수 없습니다" in response.text
    assert "설정을 바꿨습니다" not in response.text
    assert "/invite/" not in response.text            # 링크도 발급되지 않는다


def test_마무리05b_부서_없음은_그대로_허용된다(with_departments, admin_client):
    """빈 값은 '부서 미지정'이라는 뜻이라 막지 않는다."""
    response = admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "member", "department_key": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "k=" in response.headers["location"]

    with app_session() as db:
        person = db.scalars(
            select(models.User).where(models.User.name == "박서진")
        ).first()
        assert person is not None
        assert person.department_id is None


# ══════════════════════════════════════════════════════════════════════
# 배포 직전 — 부서 목록을 현재 회차로 좁힌 것. 아래 번호는 그 작업 기준이다.
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def two_rounds(admin_client):
    """회차 두 개. 지난 회차에만 있는 부서('봉사팀 공통')를 넣는다.

    회차가 하나뿐인 픽스처로는 이 버그가 재현되지 않는다 — 모든 회차를 훑어도
    결과가 같기 때문이다.
    """
    with app_session() as db:
        old = models.Retreat(
            name="2026 여름수련회",
            start_date=dt.date(2026, 8, 21),
            end_date=dt.date(2026, 8, 23),
        )
        db.add(old)
        db.flush()
        for order, (key, name) in enumerate(
            [("sketch", "4 스케치"), ("bongsa", "봉사팀 공통")]
        ):
            db.add(
                models.Department(
                    retreat_id=old.id, key=key, name=name,
                    color_tag="#888", sort_order=order,
                )
            )
        db.flush()

        # 지난 회차의 '봉사팀 공통' 에 붙어 있는 계정 — 해체 전에 만든 사람이다
        gone = next(d for d in old.departments if d.key == "bongsa")
        legacy = models.User(
            name="옛 봉사팀원", phone_number="01077770000",
            role="member", department_id=gone.id,
        )
        db.add(legacy)

        new = models.Retreat(
            name="2027 겨울수련회",
            start_date=dt.date(2027, 1, 14),
            end_date=dt.date(2027, 1, 17),
        )
        db.add(new)
        db.flush()
        for order, (key, name) in enumerate(
            [("sketch", "4 스케치"), ("hebron", "5 헤브론")]
        ):
            db.add(
                models.Department(
                    retreat_id=new.id, key=key, name=name,
                    color_tag="#888", sort_order=order,
                )
            )
        db.commit()
        return {"old": old.id, "new": new.id, "legacy_id": legacy.id,
                "legacy_dept_id": gone.id}


# ── 배포 3 ────────────────────────────────────────────────────────────


def test_배포03_현재_회차에_없는_부서는_목록에_없다(two_rounds, admin_client):
    """해체된 부서가 남아 있으면 저장은 되는데 그 사람은 아무 업무도 못 고친다."""
    page = admin_client.get("/admin/users")
    assert page.status_code == 200

    form = page.text.split('class="userform"')[1].split("</form>")[0]
    assert 'value="sketch"' in form
    assert 'value="hebron"' in form          # 이번 회차에 있는 것
    assert 'value="bongsa"' not in form      # 지난 회차에만 있는 것


# ── 배포 4 ────────────────────────────────────────────────────────────


def test_배포04_그런_부서로_저장하려_하면_막힌다(two_rounds, admin_client):
    response = admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "member", "department_key": "bongsa"},
    )
    assert response.status_code == 200
    assert "이번 회차" in response.text
    assert "없는 부서라 배정할 수 없습니다" in response.text
    assert "봉사팀 공통" in response.text or "bongsa" in response.text

    with app_session() as db:
        assert db.scalars(
            select(models.User).where(models.User.name == "박서진")
        ).first() is None


def test_배포04b_바꿀_때도_막힌다(two_rounds, admin_client):
    """이미 그 부서인 사람은 '유지'라 통과한다(05b). 여기서 보는 것은
    **새로 배정하는** 경우다."""
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

    response = admin_client.post(
        f"/admin/users/{person_id}/update",
        data={"role": "member", "department_key": "bongsa"},
    )
    assert response.status_code == 200
    assert "없는 부서라 배정할 수 없습니다" in response.text


# ── 배포 5 ────────────────────────────────────────────────────────────


def test_배포05_지난_회차_부서에_붙은_계정은_건드리지_않는다(two_rounds, admin_client):
    """조용히 바꾸거나 지우면 총무팀이 모르는 채로 소속이 사라진다."""
    page = admin_client.get("/admin/users")

    # 소속은 그대로 남아 있다
    with app_session() as db:
        person = db.get(models.User, two_rounds["legacy_id"])
        assert person.department_id == two_rounds["legacy_dept_id"]

    # 화면에는 "이번 회차에 없음" 으로 보인다
    assert "이번 회차에 없음" in page.text
    assert "이번 회차에 없는 부서에 붙어 있는 계정이 있습니다" in page.text
    assert "옛 봉사팀원" in page.text


def test_배포05b_권한만_바꿔도_지난_부서가_지워지지_않는다(two_rounds, admin_client):
    """화면이 그 값을 그대로 되돌려 보낸다. 그때 '이번 회차에 없다'고 막아
    버리거나 빈 값으로 처리하면, 권한만 고쳤는데 소속이 조용히 사라진다."""
    before = two_rounds["legacy_dept_id"]

    response = admin_client.post(
        f"/admin/users/{two_rounds['legacy_id']}/update",
        data={"role": "dept_lead", "department_key": "bongsa"},   # 화면이 되돌려 보내는 값
        follow_redirects=False,
    )
    assert response.status_code == 303

    with app_session() as db:
        person = db.get(models.User, two_rounds["legacy_id"])
        assert person.role == "dept_lead"                 # 바꾸려던 것은 바뀌고
        assert person.department_id == before             # 소속은 그대로다


def test_배포05c_지난_부서를_남에게_새로_붙이는_것은_막힌다(two_rounds, admin_client):
    """유지는 통과시키되 **새로 배정하는 것**은 막는다."""
    admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "member", "department_key": "sketch"},
        follow_redirects=False,
    )
    with app_session() as db:
        other_id = db.scalars(
            select(models.User).where(models.User.name == "박서진")
        ).first().id

    response = admin_client.post(
        f"/admin/users/{other_id}/update",
        data={"role": "member", "department_key": "bongsa"},
    )
    assert response.status_code == 200
    assert "없는 부서라 배정할 수 없습니다" in response.text
    with app_session() as db:
        from app.domain.departments import department_key_of

        assert department_key_of(db, db.get(models.User, other_id)) == "sketch"


def test_배포05d_지난_부서를_실제로_뗄_수는_있다(two_rounds, admin_client):
    """유지를 통과시킨다고 해서 못 떼는 것은 아니다 — 빈 값은 그대로 미지정이다."""
    admin_client.post(
        f"/admin/users/{two_rounds['legacy_id']}/update",
        data={"role": "member", "department_key": ""},
        follow_redirects=False,
    )
    with app_session() as db:
        assert db.get(models.User, two_rounds["legacy_id"]).department_id is None


# ── 배포 6 ────────────────────────────────────────────────────────────


def test_배포06_회차가_하나도_없어도_화면이_죽지_않는다(admin_client):
    with app_session() as db:
        assert db.scalars(select(models.Retreat)).first() is None

    page = admin_client.get("/admin/users")
    assert page.status_code == 200
    assert "아직 부서가 없습니다" in page.text

    # 부서 없이 계정은 만들 수 있다
    response = admin_client.post(
        "/admin/users/new",
        data={"name": "박서진", "phone_number": "01099991111",
              "role": "admin", "department_key": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303

    # 부서를 넣으려 하면 회차가 없다고 말한다
    blocked = admin_client.post(
        "/admin/users/new",
        data={"name": "다른사람", "phone_number": "01088880000",
              "role": "member", "department_key": "sketch"},
    )
    assert blocked.status_code == 200
    assert "아직 회차가 없어" in blocked.text
