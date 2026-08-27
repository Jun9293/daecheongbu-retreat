"""테스트 공통 픽스처.

app 패키지를 import 하기 전에 임시 DB/업로드 경로를 환경변수로 지정한다.
(운영 데이터가 있는 data/ 를 테스트가 건드리지 않도록)
"""

import os
import pathlib
import tempfile

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="dcb-test-"))
os.environ["DCB_DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["DCB_DATA_DIR"] = str(_TMP)
os.environ["DCB_DEV_MODE"] = "1"
os.environ["DCB_SECRET_KEY"] = "test-secret"

import datetime as dt  # noqa: E402
import re  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402
from app.db import Base  # noqa: E402


def _make_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db() -> Session:
    engine = _make_engine()
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def sample_retreat(db: Session) -> models.Retreat:
    """부서 3개 + 예산 카테고리 5개를 가진 회차."""
    retreat = models.Retreat(
        name="2026 여름수련회 Belong",
        start_date=dt.date(2026, 7, 20),
        end_date=dt.date(2026, 7, 23),
        meal_subsidy_per_person=8_000,
    )
    db.add(retreat)
    db.flush()

    for i, name in enumerate(["총무팀", "홍보팀", "찬양팀"]):
        db.add(models.Department(retreat_id=retreat.id, name=name, sort_order=i))

    categories = [
        ("홍보", "포스터", "인쇄비", 300_000),
        ("시스템", "음향", "렌탈", 800_000),
        ("장소비", "숙소", None, 4_000_000),
        ("식비", "본행사 식사", "자율배식", 2_500_000),
        ("그 외", "수련회 준비지원", "모임 식사비", 1_000_000),
    ]
    for i, (l1, l2, l3, amount) in enumerate(categories):
        db.add(
            models.BudgetCategory(
                retreat_id=retreat.id,
                level1=l1,
                level2=l2,
                level3=l3,
                planned_amount=amount,
                sort_order=i,
            )
        )
    db.commit()
    return retreat


# ---------------------------------------------------------------- 웹 통합 테스트


@pytest.fixture
def client():
    """빈 DB 위에서 실제 앱을 띄운 테스트 클라이언트."""
    from fastapi.testclient import TestClient

    from app.db import engine
    from app.main import app

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(engine)


def login_as(client, phone: str, name: str = "테스터"):
    """전화번호 인증 로그인 (개발 모드에서 화면에 노출되는 코드를 사용)."""
    response = client.post("/login/code", data={"phone_number": phone})
    assert response.status_code == 200, response.text
    match = re.search(r"<b>(\d{6})</b>", response.text)
    assert match, "개발 모드 인증코드를 찾을 수 없습니다."
    code = match.group(1)

    response = client.post(
        "/login/verify",
        data={"phone_number": phone, "code": code, "name": name},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response


@pytest.fixture
def admin_client(client):
    """최초 로그인 사용자 = 총무팀(관리자).

    `client` 와는 쿠키를 공유하지 않는 별도 클라이언트여야 한다.
    (같은 객체를 쓰면 '로그인하지 않은 사용자' 테스트가 실제로는 로그인 상태가 된다)
    """
    from fastapi.testclient import TestClient

    from app.main import app

    admin = TestClient(app)
    login_as(admin, "01011112222", name="총무 김간사")
    return admin


def app_session() -> Session:
    from app.db import SessionLocal

    return SessionLocal()
