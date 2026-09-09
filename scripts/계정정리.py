# -*- coding: utf-8 -*-
"""사람이 고른 계정 하나만 남기고 나머지를 지웁니다 (0장의 예외).

## 왜 지우는가 — 그리고 왜 이것만 지우는가

이 저장소의 첫 원칙은 **아무것도 삭제하지 않는다** 입니다. 기록이 쌓여야
판단 근거가 생기기 때문입니다. **계정만 예외입니다**(0장) — 같은 사람이
여럿이면 알림이 그 수만큼 가고 담당자 목록에 같은 이름이 여러 번 떠서,
남겨서 얻는 것이 없고 잃는 것만 있습니다.

**화면에는 여전히 삭제가 없습니다**(4-12). 거기서 막는 것은 「누르면
사라지는 단추」 이고, 이 스크립트가 여는 것은 **무엇을 잃는지 세어 보인
뒤 사람이 id 를 고른** 한 갈래입니다. 그래서 기본이 미리보기이고,
`--실행` 을 붙였을 때만 지웁니다.

## 지우기 전에 세는 것

`users.id` 를 가리키는 참조는 `ondelete` 가 자리마다 다릅니다.

- `CASCADE` — 계정과 **함께 사라집니다**
- `SET NULL` — 행은 남고 **「누가 썼는지 모르는 것」 이 됩니다**
- **FK 가 아예 없는 자리** — `activity_logs.actor_id` 는 그냥 정수라
  지운 뒤에도 **없는 id 를 가리킵니다.** `PRAGMA foreign_key_list` 에
  안 나오므로 FK 목록만 보고 지우면 이 행들은 보이지 않습니다.
  그래서 이 스크립트가 **직접 비웁니다** — `actor_name` 은 그대로 두므로
  「누가 했는지」 는 화면에서 계속 읽힙니다.
- **`activity_logs.target_id` 는 건드리지 않습니다.** `target_type='user'`
  인 행이 지운 계정을 가리킨 채 남습니다(2026-09-09 실측 8행). 비우면
  「무엇에 대한 기록인가」 를 잃고, 두면 없는 id 를 가리킵니다 — 어느
  쪽인지는 사람이 정할 일이라 `docs/봐둘것.md` 에 열어 두었습니다.
  `summary` 에 그때의 이름이 실려 있어 읽는 데는 지장이 없습니다.

## 되돌릴 수 없으므로 먼저 뜹니다

지우기 직전에 `scripts/backup.py` 의 `snapshot()`(`VACUUM INTO`)으로
사본을 만듭니다 — **사본이 안 떠지면 아무것도 지우지 않습니다.**
파일 복사가 아니라 `VACUUM INTO` 인 이유는 11-2 에 있습니다.

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/계정정리.py 1           # 미리보기
    .venv\\Scripts\\python.exe scripts/계정정리.py 1 --실행    # 실제로 지움
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글·기호가 깨지지 않게 한다 — 안내를 못 찍고
# 죽으면 무엇이 지워졌는지 사람이 알 수 없다 (관리자링크.py 와 같다)
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select, text                     # noqa: E402
from sqlalchemy.engine import make_url                        # noqa: E402
from sqlalchemy.exc import OperationalError                   # noqa: E402
from sqlalchemy.orm import Session                            # noqa: E402

from app import config                                        # noqa: E402
from app.db import SessionLocal                               # noqa: E402
from app.deps import log_activity                             # noqa: E402
from app.domain import permissions as perm                    # noqa: E402
from app.models import InviteToken, User                      # noqa: E402
from scripts import backup                                    # noqa: E402

# **FK 가 없어 `PRAGMA foreign_key_list` 에 안 나오는 자리.**
# 여기 적힌 것은 스크립트가 직접 비웁니다 — 적지 않으면 지운 뒤에도
# 없는 id 를 가리킨 채 남고, 아무 오류도 나지 않습니다.
FK없는칸 = [("activity_logs", "actor_id")]


def 참조들(db: Session) -> list[tuple[str, str, str]]:
    """`users.id` 를 가리키는 (표, 칸, ondelete) 를 스키마에서 읽는다.

    **목록을 코드에 박지 않습니다** — 표가 하나 늘면 여기도 손대야 하고,
    안 고치면 그 표만 조용히 안 세어집니다 (10장 「자리를 세어 두지
    않습니다」).
    """
    난것: list[tuple[str, str, str]] = []
    for (표,) in db.execute(text(
        "select name from sqlite_master where type='table' order by name"
    )):
        for 줄 in db.execute(text(f'pragma foreign_key_list("{표}")')):
            if 줄[2] == "users":
                난것.append((표, 줄[3], 줄[6] or "NO ACTION"))
    for 표, 칸 in FK없는칸:
        난것.append((표, 칸, "FK 없음"))
    return 난것


def 셈(db: Session, 남길: int) -> list[tuple[str, str, str, int]]:
    """표·칸별로 **지울 계정을 가리키는 행 수**. 남길 계정 것은 뺀다."""
    난것 = []
    for 표, 칸, od in 참조들(db):
        수 = db.execute(text(
            f'select count(*) from "{표}" where "{칸}" is not null and "{칸}" <> :남길'
        ), {"남길": 남길}).scalar_one()
        난것.append((표, 칸, od, 수))
    return sorted(난것, key=lambda r: -r[3])


def 미리보기(db: Session, 남길: int, 지울수: int) -> None:
    표 = 셈(db, 남길)
    걸린것 = [r for r in 표 if r[3]]

    print()
    print(f"지울 계정 {지울수}개 (남길 id {남길} 은 그대로 둡니다)")
    print()
    print(f"  {'표.칸':<38} {'어떻게 되나':<24} {'행':>6}")
    print(f"  {'-' * 38} {'-' * 24} {'-' * 6}")
    뜻 = {
        "CASCADE": "계정과 함께 사라집니다",
        "SET NULL": "남되 누가 썼는지 모릅니다",
        "FK 없음": "스크립트가 직접 비웁니다",
    }
    for t, c, od, n in 걸린것:
        print(f"  {t + '.' + c:<38} {뜻.get(od, od):<24} {n:>6}")
    if not 걸린것:
        print("  (걸리는 행이 없습니다)")

    사라짐 = sum(n for _, _, od, n in 걸린것 if od == "CASCADE")
    이름잃음 = sum(n for _, _, od, n in 걸린것 if od == "SET NULL")
    직접 = sum(n for _, _, od, n in 걸린것 if od == "FK 없음")
    print()
    print(f"  함께 사라지는 행 {사라짐} · 이름을 잃는 행 {이름잃음} · 직접 비우는 행 {직접}")
    print()
    print("  **아직 아무것도 지우지 않았습니다.** 실제로 지우려면:")
    print(f"    python scripts/계정정리.py {남길} --실행")


def 지운다(db: Session, 남길: int, 지울: list[int]) -> pathlib.Path:
    """사본을 먼저 뜨고, FK 없는 칸을 비운 뒤, 계정을 지운다."""
    # **사본이 안 떠지면 아무것도 지우지 않습니다.** 되돌릴 방법이 없는
    # 작업이라, 뜨는 것이 실패하면 그 자리에서 멈추는 것이 맞습니다.
    # **뜨는 파일과 지우는 파일이 같은지 봅니다.** 세션은 DATABASE_URL 을
    # 열고 사본은 DATA_DIR/app.db 를 뜨는데, DCB_DATABASE_URL 로 둘이 갈리면
    # 「다른 파일의 사본」 을 뜨고도 「떴습니다」 가 찍힙니다.
    원본 = pathlib.Path(config.DATA_DIR) / "app.db"
    여는것 = make_url(config.DATABASE_URL).database
    if not 여는것 or pathlib.Path(여는것).resolve() != 원본.resolve():
        raise RuntimeError(
            f"세션이 여는 DB({여는것})와 사본을 뜰 파일({원본})이 다릅니다 — "
            "지우지 않았습니다.")
    사본 = backup.snapshot(원본, pathlib.Path(config.DATA_DIR) / "backups")
    print(f"  사본을 떴습니다: {사본.name}  ({사본.stat().st_size:,} 바이트)")

    # **FK 가 없는 칸은 여기서 비웁니다** — DB 가 대신 해 주지 않습니다.
    # `actor_name` 은 그대로 둡니다: 「누가 했는지」 는 그 문자열이 집니다.
    for 표, 칸 in FK없는칸:
        바뀜 = db.execute(text(
            f'update "{표}" set "{칸}" = null '
            f'where "{칸}" is not null and "{칸}" <> :남길'
        ), {"남길": 남길}).rowcount
        print(f"  {표}.{칸} 을 {바뀜}행 비웠습니다 (이름은 그대로 둡니다)")

    for uid in 지울:
        db.delete(db.get(User, uid))
    db.commit()
    return 사본


def 정리(db: Session, 남길: int, 실행: bool) -> int:
    person = db.get(User, 남길)
    if person is None:
        print(f"id {남길} 인 계정이 없습니다.")
        return 1
    # **남길 계정이 관리자이고 활성이어야 합니다.** 아니면 지운 뒤에
    # 아무도 설정 화면에 못 들어갑니다 — 되돌릴 수 없는 작업이라
    # 그 상태를 만들면 안 됩니다.
    if person.role != perm.ADMIN:
        print(f"id {남길} 은 관리자(admin)가 아닙니다 — 아무것도 지우지 않았습니다.")
        print("  남길 계정은 관리자여야 합니다. 지운 뒤 설정 화면에 들어갈 사람입니다.")
        return 1
    if not person.is_active:
        print(f"id {남길} 은 비활성 계정입니다 — 아무것도 지우지 않았습니다.")
        return 1

    지울 = [uid for (uid,) in db.execute(
        select(User.id).where(User.id != 남길).order_by(User.id))]
    if not 지울:
        print(f"지울 계정이 없습니다 (users 가 id {남길} 하나뿐입니다).")
        return 0

    if not 실행:
        미리보기(db, 남길, len(지울))
        return 0

    # **FK 가 켜져 있는지 봅니다.** 꺼져 있으면 CASCADE 가 안 돌아
    # 가리킬 곳 없는 행이 조용히 남습니다 — 아무 오류도 나지 않습니다.
    if not db.execute(text("pragma foreign_keys")).scalar_one():
        print("!! SQLite 의 외래키가 꺼져 있습니다 — 지우면 CASCADE 가 안 돕니다.")
        print("   app/db.py 의 PRAGMA foreign_keys=ON 이 도는지 보세요.")
        return 1

    print()
    print(f"계정 {len(지울)}개를 지웁니다. 남길 id {남길}.")
    사본 = 지운다(db, 남길, 지울)

    남은수 = db.execute(select(func.count()).select_from(User)).scalar_one()
    log_activity(
        db,
        retreat_id=None,
        actor=None,
        action="계정_삭제",
        target_type="user",
        target_id=남길,
        summary=f"계정 {len(지울)}개를 서버에서 지웠습니다 (남긴 계정 1개).",
    )
    print(f"  지웠습니다. 남은 users 행: {남은수}")
    print(f"  되돌리려면 서버를 끄고 {사본.name} 을 data/app.db 로 되돌립니다 (11-2).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="사람이 고른 계정 하나만 남기고 나머지를 지웁니다 (0장의 예외).",
        epilog="기본은 미리보기입니다. 실제로 지우려면 --실행 을 붙이세요.",
    )
    ap.add_argument("id", type=int, help="남길 관리자 계정 id")
    ap.add_argument("--실행", action="store_true", help="실제로 지웁니다")
    args = ap.parse_args()

    with SessionLocal() as db:
        try:
            return 정리(db, args.id, getattr(args, "실행"))
        except OperationalError:
            # 관리자링크.py 와 같은 자리 — 데이터 폴더를 잘못 짚으면 sqlite 가
            # 빈 파일을 만들고 첫 조회에서 죽는다
            print("데이터베이스를 열었는데 표가 없습니다 — 빈 파일을 만든 것 같습니다.")
            print(f"  지금 보고 있는 곳: {config.DATABASE_URL}")
            print("  DCB_DATA_DIR 이 운영 데이터 폴더를 가리키는지 확인하세요.")
            return 1


if __name__ == "__main__":
    sys.exit(main())
