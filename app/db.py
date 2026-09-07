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
    # 회의록을 문장으로 읽은 결과 (회의록 5단계). 본문이 안 바뀌면 다시
    # 부르지 않으려고 해시를 함께 남긴다 — 저장할 때마다 부르기 때문이다.
    ("meetings", "suggest_hash", "VARCHAR(64)"),
    ("meetings", "suggest_state", "VARCHAR(10)"),
    ("meetings", "suggest_json", "TEXT"),
    ("meetings", "suggest_note", "TEXT"),
    ("meetings", "suggest_at", "DATETIME"),
    ("meetings", "suggest_cost", "FLOAT"),
    ("meetings", "suggest_tokens", "VARCHAR(40)"),
    ("meetings", "suggest_due_at", "DATETIME"),
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
    # 회의록의 출처와 옮기기 묶음. 기존 행은 NULL — 읽는 쪽이 '사람' 으로 본다.
    ("meetings", "origin", "VARCHAR(20)"),
    ("meetings", "source_ref", "VARCHAR(200)"),
    ("meetings", "import_batch", "VARCHAR(40)"),
    # 논의의 출처 (4-9). 기존 행은 NULL — 사람이 직접 적은 것으로 본다.
    ("discussion_entries", "source_meeting_id", "INTEGER"),
    # 회차 안에서 고정되는 업무 번호 (4-14). 기존 행은 앱이 뜰 때 한 번 매긴다.
    ("task_runs", "run_no", "INTEGER"),
    # 확인 요청이 가리키는 업무 (4-9 · 4-16). task_id 는 옛 Task 표 FK 라
    # 남기되 새 요청은 이것을 쓴다.
    ("review_requests", "run_id", "INTEGER REFERENCES task_runs(id)"),
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


def _convert_stored_late() -> None:
    """저장된 status='지연' 을 한 번 '대기' 로 되돌린다 (4-3).

    '지연' 은 이제 저장값이 아니라 계산값이다(board.overdue_of) — 저장해 두면
    같은 사실의 출처가 둘이 되고, 담당자가 손으로 눌러야만 붙는 표시가 판정처럼
    읽힌다. 바꾼 것은 ActivityLog 에 남긴다 — 조용히 사라지면 나중에 "내가
    눌러 둔 지연이 왜 없어졌지" 를 아무도 설명하지 못한다.

    두 번 떠도 두 번 바꾸지 않는다 — 바꾸고 나면 '지연' 행이 없다.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        rows = list(
            conn.execute(
                text("SELECT id, retreat_id FROM task_runs WHERE status = '지연'")
            )
        )
        for run_id, retreat_id in rows:
            conn.execute(
                text("UPDATE task_runs SET status = '대기' WHERE id = :id"),
                {"id": run_id},
            )
            conn.execute(
                text(
                    # 사람이 한 일이 아니다 — actor 를 'system' 으로 남긴다.
                    # 'user' 로 남기면 시스템 전환이 사람 행위 모양이 된다.
                    "INSERT INTO activity_logs"
                    " (retreat_id, actor_type, actor_name, action, target_type,"
                    "  target_id, summary, before_value, after_value, created_at)"
                    " VALUES (:retreat_id, 'system', '앱 시작', '업무_상태_변경',"
                    "  'task_run', :id, '저장 지연 → 대기 (계산값으로 전환)',"
                    "  :before, :after, CURRENT_TIMESTAMP)"
                ),
                {
                    "retreat_id": retreat_id,
                    "id": run_id,
                    "before": '{"status": "지연"}',
                    "after": '{"status": "대기"}',
                },
            )
        if rows:
            import logging

            logging.getLogger("dcb.db").info(
                "저장돼 있던 '지연' %d행을 '대기' 로 돌렸습니다 — 지연은 이제 날짜에서 계산합니다",
                len(rows),
            )


def _link_discussion_runs() -> None:
    """링크 행(DiscussionEntryRun)이 없는 논의만 runId 에서 한 번 옮긴다 (4-9).

    걸린 곳의 유일한 출처는 링크 표다. 옛 행은 run_id 하나만 들고 있으므로
    그 값으로 링크 행 하나를 만들어 준다. **여기가 DiscussionEntry.run_id 를
    읽는 유일한 자리다** — 다른 곳은 전부 링크 표를 지난다.

    두 번 떠도 두 번 옮기지 않는다 — 이미 링크가 있는 행은 건너뛴다.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        moved = conn.execute(
            text(
                "INSERT INTO discussion_entry_runs (entry_id, run_id, attached_at)"
                " SELECT e.id, e.run_id, CURRENT_TIMESTAMP FROM discussion_entries e"
                " WHERE NOT EXISTS (SELECT 1 FROM discussion_entry_runs l"
                "                   WHERE l.entry_id = e.id)"
            )
        ).rowcount
        if moved:
            import logging

            logging.getLogger("dcb.db").info(
                "논의 %d건에 걸린 곳 링크 행을 만들었습니다 (runId 에서 한 번 옮김)",
                moved,
            )


def _assign_run_numbers() -> None:
    """번호(run_no)가 없는 run 을 회차별로 **시작일 → id 순으로** 한 번 매긴다 (4-14).

    이미 번호가 있는 행은 절대 다시 매기지 않는다 — 번호는 회의에서 부르는
    손잡이라 바뀌면 지난 회의록의 번호가 전부 낡는다. 새 run 은 만들 때
    그 회차의 max+1 을 받는다(domain.library.next_run_no).
    두 번 떠도 두 번 매기지 않는다 — 매기고 나면 번호 없는 행이 없다.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        retreats = [
            r[0]
            for r in conn.execute(
                text("SELECT DISTINCT retreat_id FROM task_runs WHERE run_no IS NULL")
            )
        ]
        assigned = 0
        for retreat_id in retreats:
            start = conn.execute(
                text("SELECT COALESCE(MAX(run_no), 0) FROM task_runs WHERE retreat_id=:r"),
                {"r": retreat_id},
            ).scalar_one()
            rows = list(
                conn.execute(
                    text(
                        "SELECT id FROM task_runs WHERE retreat_id=:r AND run_no IS NULL"
                        " ORDER BY (start_date IS NULL), start_date, id"
                    ),
                    {"r": retreat_id},
                )
            )
            for offset, (run_id,) in enumerate(rows, start=1):
                conn.execute(
                    text("UPDATE task_runs SET run_no=:n WHERE id=:id"),
                    {"n": start + offset, "id": run_id},
                )
            assigned += len(rows)
        if assigned:
            import logging

            logging.getLogger("dcb.db").info(
                "업무 %d건에 번호(run_no)를 매겼습니다 — 회차별 시작일 → id 순, 한 번만",
                assigned,
            )


def init_db() -> None:
    from app import models  # noqa: F401  (모델 등록)

    Base.metadata.create_all(bind=engine)
    _catch_up_columns()
    _swap_phone_index()
    _release_inactive_phones()
    _convert_stored_late()
    _link_discussion_runs()
    _assign_run_numbers()
