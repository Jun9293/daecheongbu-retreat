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
os.environ["DCB_SECRET_KEY"] = "test-secret"

import datetime as dt  # noqa: E402

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

    # 부서는 키를 갖는다 — 소속·알림이 키로 돈다 (2장 · 도막 4)
    for i, (key, name) in enumerate([("chongmu", "총무팀"), ("hongbo", "홍보팀"), ("chanyang", "찬양팀")]):
        db.add(models.Department(retreat_id=retreat.id, key=key, name=name, sort_order=i))

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
    """초대 링크로 들어온다 (CLAUDE.md 4-12).

    실제 흐름과 같은 길을 쓴다 — 계정을 만들고 링크를 발급해 그 링크를 연다.
    `phone` 은 사람을 알아보는 값일 뿐 더 이상 인증 수단이 아니다.
    첫 사용자는 총무팀(admin)이 된다.
    """
    from sqlalchemy import func, select

    from app.domain import auth as invites
    from app.models import User

    from app.db import SessionLocal

    with SessionLocal() as db:
        person = db.scalars(select(User).where(User.phone_number == phone)).first()
        if person is None:
            first = db.scalar(select(func.count()).select_from(User)) == 0
            person = User(
                name=name, phone_number=phone, role="admin" if first else "general"
            )
            db.add(person)
            db.commit()
        raw = invites.issue(db, user=person)

    response = client.get(f"/invite/{raw}", follow_redirects=False)
    assert response.status_code == 303, response.text
    return response


def dept_key_of(db, user):
    """시험용 — 그 사람의 부서 키 **하나**(없으면 None, 둘 이상이면 실패).
    옛 「한 사람 → 키 하나」 를 부르던 단언이 그대로 읽히게 두었다."""
    from app.domain import permissions as perm

    keys = sorted(perm.my_dept_keys(user))
    assert len(keys) <= 1, f"부서가 여럿이다: {keys}"
    return keys[0] if keys else None


def legacy_user(db, *, role="member", dept=None, **kw):
    """열린 세션 안에서 옛 모양(`role="dept_lead"` + 부서 하나)으로 계정을 만든다.

    `make_user` 는 세션을 따로 열어 id 만 돌려주는데, 회차·부서·업무를 한 세션에서
    같이 만드는 시험은 그 세션 안의 `User` 객체가 필요하다. 소속은 `perm.assign`
    으로 놓는다 — 표를 직접 안 만진다.
    """
    from app.domain import permissions as perm
    from app.models import Department, User

    top, dept_role = perm.LEGACY_ROLE_MAP.get(role, (role, perm.MEMBER))
    person = User(role=top, **kw)
    db.add(person)
    if dept is not None:
        db.flush()
        perm.assign(db, person, db.get(Department, dept), dept_role)
    return person


def make_user(name, phone, role="member", dept=None, departments=None):
    """시험용 계정을 DB 에 직접 만든다.

    전에는 구설계 POST(/users/create) 로 만들었는데, 그 엔드포인트는 화면이
    없어져 단계 2 에서 지웠다 (14장). 실제 흐름의 계정 생성은 /admin/users
    (4-12)이고, 여기는 픽스처라 저장만 하면 된다.

    **부서 여럿을 받는다** (도막 4). `departments=[(dept_id, "lead"), (dept_id, "member")]`.
    옛 부르기 `role="dept_lead", dept=N`(부서 하나) 도 그대로 통과한다 — 전체
    역할은 「일반」 이 되고 그 부서에 리더로 붙는다. `role="member"` 이고
    부서가 없으면 소속 없는 일반이다(열람 전용 · ②).
    """
    from app.db import SessionLocal
    from app.domain import permissions as perm
    from app.models import Department, User

    digits = "".join(ch for ch in phone if ch.isdigit())
    top, dept_role = perm.LEGACY_ROLE_MAP.get(role, (role, perm.MEMBER))
    rows = list(departments or [])
    if dept is not None:
        rows.insert(0, (dept, dept_role))
    with SessionLocal() as db:
        person = User(name=name, phone_number=digits, role=top)
        db.add(person)
        db.flush()
        for dept_id, r in rows:
            perm.assign(db, person, db.get(Department, dept_id), r)
        db.commit()
        return person.id


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


def mirror_discussion_links(db) -> None:
    """링크 행이 없는 논의에 걸린 곳(DiscussionEntryRun)을 채운다 (4-9).

    픽스처가 옛 모양(run_id 만)으로 논의를 만들면, 화면·판정은 링크 표만
    읽으므로 그 논의가 안 보인다. 운영에서는 앱이 뜰 때
    `app.db._link_discussion_runs` 가 같은 일을 한다 — 시험은 엔진이
    제각각이라 세션을 받아 여기서 돌린다. 두 번 불러도 두 번 걸지 않는다.
    """
    from sqlalchemy import text

    db.execute(
        text(
            "INSERT INTO discussion_entry_runs (entry_id, run_id, attached_at)"
            " SELECT e.id, e.run_id, CURRENT_TIMESTAMP FROM discussion_entries e"
            " WHERE NOT EXISTS (SELECT 1 FROM discussion_entry_runs l"
            "                   WHERE l.entry_id = e.id)"
        )
    )
    db.commit()
