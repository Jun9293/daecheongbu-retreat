"""SQLAlchemy 엔진 / 세션."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    future=True,
)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 나중에 추가된 컬럼. 이미 쓰고 있는 DB 를 버리지 않고 따라잡기 위한 목록이다.
# (테이블, 컬럼, DDL) — 추가만 한다. 이름 변경·삭제는 여기서 하지 않는다.
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("departments", "key", "VARCHAR(40)"),
    ("task_library", "always_required", "BOOLEAN NOT NULL DEFAULT 0"),
)


def _catch_up_columns() -> None:
    """create_all 은 기존 테이블에 컬럼을 더해주지 않는다.

    운영 중인 SQLite 파일이 새 코드보다 뒤처져 있으면 여기서 메운다.
    마이그레이션 도구를 붙이기 전까지의 최소 장치다.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        existing = {
            row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        for table, column, ddl in _ADDED_COLUMNS:
            if table not in existing:
                continue
            columns = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if column in columns:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def init_db() -> None:
    from app import models  # noqa: F401  (모델 등록)

    Base.metadata.create_all(bind=engine)
    _catch_up_columns()
