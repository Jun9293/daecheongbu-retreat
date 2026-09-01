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
    ("task_library", "rules", "TEXT"),
    ("task_library", "prerequisite_library_ids", "TEXT"),
    ("task_runs", "started_at", "DATE"),
    ("task_runs", "completed_at", "DATE"),
    # 나중에 붙었다. 기존 행은 NULL 이므로 읽는 쪽이 'person' 으로 본다 (5-2)
    ("program_items", "scope", "VARCHAR(10)"),
    # 봉사자 시간표(5-8) 때문에 붙었다. 기존 행은 NULL —
    # 읽는 쪽이 audience_key / track_key / is_parallel 로 감싼다.
    ("programs", "end_time", "VARCHAR(5)"),
    ("programs", "audience", "VARCHAR(10)"),
    ("programs", "track", "VARCHAR(10)"),
    ("programs", "parallel", "BOOLEAN"),
    # 비활성 계정이 놓은 번호 (4-12). 되살릴 때 돌려준다.
    ("users", "retired_phone", "VARCHAR(20)"),
    # 링크 첨부 (4-9). 기존 행은 NULL — 값이 없으면 파일이다.
    ("task_attachments", "url", "VARCHAR(2000)"),
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


def _swap_phone_index() -> None:
    """`phone_number` 의 전체 유니크 인덱스를 **번호를 쥔 행만** 보는 것으로 바꾼다.

    비활성 계정이 번호를 놓으면(빈 문자열) 그런 행이 여럿 생기는데, 예전의 전체
    유니크 인덱스는 그것을 막는다. 겹치면 안 되는 것은 **번호를 실제로 쥔 계정
    끼리**이므로 조건부 인덱스가 그 규칙을 정확히 적는다.

    인덱스만 바꾸므로 표를 다시 만들지 않는다 — 운영 중인 파일에 그런 위험을
    지울 이유가 없다.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index'")
            )
        }
        if "ix_users_phone_number" in names:
            conn.execute(text("DROP INDEX ix_users_phone_number"))
        if "ix_users_phone_held" not in names:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone_held"
                    " ON users (phone_number) WHERE phone_number != ''"
                )
            )


def _release_inactive_phones() -> None:
    """이미 비활성인 계정들이 붙들고 있던 번호를 한 번 놓게 한다 (4-12).

    이 규칙이 생기기 전에 비활성화된 계정들은 여전히 번호를 쥐고 있어서,
    남긴 계정에 그 번호를 넣을 수 없다 — 정리를 끝낼 수 없는 상태다.
    **무엇을 옮겼는지 로그에 남긴다.** 조용히 사라지면 나중에 "번호가 왜
    없어졌지" 를 아무도 설명하지 못한다.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    import logging

    from sqlalchemy import text

    with engine.begin() as conn:
        rows = list(
            conn.execute(
                text(
                    "SELECT id, name, phone_number FROM users"
                    " WHERE is_active = 0 AND phone_number != ''"
                    " AND (retired_phone IS NULL OR retired_phone = '')"
                )
            )
        )
        for user_id, name, phone in rows:
            conn.execute(
                text(
                    "UPDATE users SET retired_phone = :phone, phone_number = ''"
                    " WHERE id = :id"
                ),
                {"phone": phone, "id": user_id},
            )
        if rows:
            logging.getLogger("dcb.db").info(
                "비활성 계정 %d개가 연락처를 놓았습니다 — %s",
                len(rows),
                " · ".join(f"{name}({phone})" for _, name, phone in rows),
            )


def init_db() -> None:
    from app import models  # noqa: F401  (모델 등록)

    Base.metadata.create_all(bind=engine)
    _catch_up_columns()
    _swap_phone_index()
    _release_inactive_phones()
