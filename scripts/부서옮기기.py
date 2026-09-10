# -*- coding: utf-8 -*-
"""`users.department_id` 를 `user_departments` 로 옮기고 그 칸을 지웁니다 (도막 4).

## 무엇을 하나

- `department_id` 가 있는 계정마다 소속 줄 하나 — 옛 `role` 이 `dept_lead`
  면 리더, `member` 면 팀원. 옛 역할 `dept_lead`·`member` 는 전체 역할
  「일반」(`general`)이 됩니다 — 부서 역할은 이제 소속 줄에서 파생합니다.
- 옮긴 뒤 **`users.department_id` 칸을 지웁니다.** 같은 것이 두 곳에 있으면
  갈립니다. SQLite 는 FK 가 걸린 칸을 `DROP COLUMN` 으로 못 지우므로 표를
  **다시 만들어 옮깁니다**(SQLite 문서의 12단계 그대로 — `foreign_keys=OFF`
  · 새 표 · 복사 · 옛 표 삭제 · 이름 바꿈 · `foreign_key_check`).

## 다시 돌려도 됩니다

소속 줄을 넣은 뒤 표 재생성이 실패하면 「칸도 있고 줄도 있는」 상태로 남는데,
그대로 다시 `--실행` 하면 됩니다 — `perm.assign` 은 있는 줄의 역할만 맞추므로
줄이 둘이 되지 않고, 칸이 있으면 재생성만 다시 합니다.

## 되돌릴 수 없으므로 먼저 뜁니다

`계정정리.py` 와 같은 길입니다 — 지우기 직전에 `VACUUM INTO` 사본을 뜨고,
사본이 안 떠지면 아무것도 안 합니다. 세션이 여는 파일과 사본을 뜰 파일이
다르면 거절합니다.

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/부서옮기기.py           # 미리보기
    .venv\\Scripts\\python.exe scripts/부서옮기기.py --실행    # 옮기고 칸을 지움
"""

from __future__ import annotations

import sys as _sys

for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import text                                   # noqa: E402
from sqlalchemy.exc import OperationalError                   # noqa: E402
from sqlalchemy.orm import Session                            # noqa: E402
from sqlalchemy.schema import CreateTable                     # noqa: E402

from app import config                                        # noqa: E402
from app.db import Base, SessionLocal, engine                 # noqa: E402
from app.deps import log_activity                             # noqa: E402
from app.domain import permissions as perm                    # noqa: E402
from app.models import Department, User                       # noqa: E402
from scripts import backup                                    # noqa: E402


def 칸이있나(db: Session) -> bool:
    cols = [r[1] for r in db.execute(text("pragma table_info(users)"))]
    return "department_id" in cols


def 옮길것(db: Session) -> list[tuple[int, str, int | None]]:
    """(user_id, 옛 role, department_id) — department_id 가 있거나 옛 역할인 계정."""
    rows = db.execute(text(
        "select id, role, department_id from users "
        "where department_id is not null or role in ('dept_lead','member') order by id"
    )).all()
    return [(r[0], r[1], r[2]) for r in rows]


def 미리보기(db: Session) -> int:
    if not 칸이있나(db):
        print("users.department_id 칸이 없습니다 — 이미 옮겼습니다. 할 일이 없습니다.")
        return 0
    rows = 옮길것(db)
    print()
    print(f"옮길 계정 {len(rows)}개 (department_id 가 있거나 옛 역할인 계정)")
    print(f"  {'id':>4}  {'옛 role':<10} {'부서 행':>6}  → 전체 역할 · 부서 역할")
    for uid, role, dept in rows:
        top, dept_role = perm.LEGACY_ROLE_MAP.get(role, (role, perm.MEMBER))
        # 가리키는 부서 행이 없으면(끊긴 id) 소속 없이 일반이 된다 — 실행과 같은 말을 한다
        있음 = dept is not None and db.get(Department, dept) is not None
        뒤 = dept_role if 있음 else ("(부서 행 없음 → 소속 없이)" if dept is not None else "(소속 없음)")
        print(f"  {uid:>4}  {role:<10} {dept if dept is not None else '-':>6}  → {top} · {뒤}")
    print()
    print("  **아직 아무것도 안 했습니다.** 실제로 옮기려면:")
    print("    python scripts/부서옮기기.py --실행")
    return 0


def 표를_다시_만든다(db_path: pathlib.Path) -> None:
    """`users` 에서 `department_id` 칸을 뺀 표로 바꿔 놓는다 (SQLite 12단계).

    **세션 밖의 날 연결에서 돌린다.** `PRAGMA foreign_keys=OFF` 는 트랜잭션
    안에서는 아무 일도 안 하는데, 켜진 채로 `DROP TABLE users` 를 하면 SQLite 가
    행을 먼저 지우면서 `ON DELETE CASCADE` 가 돌아 **알림·토큰·소속 줄이 통째로
    사라진다** — 아무 오류도 나지 않는다. 그래서 `isolation_level=None` 으로 열어
    PRAGMA 를 먼저 세우고 그 뒤에 BEGIN 한다.
    """
    import sqlite3

    from sqlalchemy import MetaData

    tbl = User.__table__
    # 모델의 지금 모양 그대로 새 표를 만든다 — 인덱스는 CREATE TABLE 에 안 실리므로
    # 뒤에 따로 만든다 (`ix_users_phone_held` 는 옛 표와 함께 사라진다)
    new = tbl.to_metadata(MetaData(), name="users_new")
    ddl = str(CreateTable(new).compile(engine))
    cols = ", ".join(c.name for c in tbl.columns)
    con = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 0, "외래키가 안 꺼졌다"
        con.execute("BEGIN")
        con.execute(ddl)
        con.execute(f"INSERT INTO users_new ({cols}) SELECT {cols} FROM users")
        con.execute("DROP TABLE users")
        con.execute("ALTER TABLE users_new RENAME TO users")
        con.execute(
            "CREATE UNIQUE INDEX ix_users_phone_held ON users(phone_number) WHERE phone_number != ''")
        문제 = con.execute("PRAGMA foreign_key_check").fetchall()
        if 문제:
            con.execute("ROLLBACK")
            raise RuntimeError(f"표를 다시 만든 뒤 외래키가 어긋납니다: {문제[:5]}")
        con.execute("COMMIT")
        con.execute("PRAGMA foreign_keys=ON")
    finally:
        con.close()


def 옮긴다(db: Session) -> tuple[int, pathlib.Path]:
    # **세션이 실제로 여는 파일**을 뜬다 — 설정 값이 아니라 엔진이 쥔 경로다.
    # 그러면 「다른 파일의 사본을 뜨고도 떴다고 찍는」 자리가 생기지 않는다
    여는것 = engine.url.database
    if not 여는것:
        raise RuntimeError("파일 DB 가 아닙니다 — 옮기지 않았습니다.")
    원본 = pathlib.Path(여는것)
    사본 = backup.snapshot(원본, pathlib.Path(config.DATA_DIR) / "backups")
    print(f"  사본을 떴습니다: {사본.name}  ({사본.stat().st_size:,} 바이트)")

    # 새 표는 없으면 만든다 (create_all 은 있는 표를 안 건드린다)
    Base.metadata.create_all(bind=engine)

    n, 끊김 = 0, 0
    for uid, role, dept_id in 옮길것(db):
        person = db.get(User, uid)
        top, dept_role = perm.LEGACY_ROLE_MAP.get(role, (role, perm.MEMBER))
        person.role = top
        if dept_id is not None:
            dept = db.get(Department, dept_id)
            if dept is not None:
                perm.assign(db, person, dept, dept_role)
                n += 1
            else:
                끊김 += 1
                print(f"  !! id {uid}: department_id={dept_id} 가 가리키는 부서 행이 없어 소속 없이 둡니다")
    if 끊김:
        print(f"  !! 끊긴 부서 id 가 {끊김}개 — 그 계정은 소속 없는 일반(열람 전용)이 됩니다")
    db.commit()
    # 세션이 쥔 연결을 놓아야 날 연결이 표를 바꿀 수 있다
    db.close()
    engine.dispose()
    표를_다시_만든다(pathlib.Path(여는것))
    return n, 사본


def main() -> int:
    ap = argparse.ArgumentParser(description="users.department_id 를 user_departments 로 옮깁니다.")
    ap.add_argument("--실행", action="store_true", help="실제로 옮기고 칸을 지웁니다")
    args = ap.parse_args()
    with SessionLocal() as db:
        try:
            if not getattr(args, "실행"):
                return 미리보기(db)
            if not 칸이있나(db):
                print("users.department_id 칸이 없습니다 — 이미 옮겼습니다.")
                return 0
            n, 사본 = 옮긴다(db)
            log_activity(db, retreat_id=None, actor=None, action="부서_옮김",
                         target_type="user", target_id=None,
                         summary=f"users.department_id 를 소속 줄 {n}개로 옮기고 칸을 지웠습니다.")
            print(f"  소속 줄 {n}개를 만들고 users.department_id 칸을 지웠습니다.")
            print(f"  되돌리려면 서버를 끄고 {사본.name} 을 data/app.db 로 되돌립니다 (11-2).")
            return 0
        except OperationalError:
            print("데이터베이스를 열었는데 표가 없습니다 — 빈 파일을 만든 것 같습니다.")
            print(f"  지금 보고 있는 곳: {config.DATABASE_URL}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
