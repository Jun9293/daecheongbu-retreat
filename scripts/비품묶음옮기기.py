# -*- coding: utf-8 -*-
"""비품의 묶음(group_name)을 품목에서 회차로 옮깁니다 (4-18 · 2026-09-10 도막 2).

## 왜

처음 만든 표는 품목의 유니크가 (team_key, group_name, name) 이라 **같은 물건이
묶음마다 다른 품목**이 됐습니다 — 시트를 들여오면 릴선이 넷, 멀티탭이 둘로 서고
이미 옮긴 서른 줄과도 겹칩니다. 정한 원칙은 「품목은 회차를 넘어 남고, 어디에
쓰는지는 그 회차의 것」 인데 어디에 쓰는지가 품목의 신분증에 들어 있었습니다.

새 모양 — `equipment_items` 는 (team_key, name) 유니크이고 group_name 이 없다.
`equipment_runs` 에 group_name(NOT NULL · 기본 "")이 있고 유니크는
(retreat_id, item_id, group_name) 셋이다 — 같은 품목을 두 자리에서 챙기면 두 줄이고
각각 따로 체크한다.

## 순서 (한 트랜잭션 — 첫 문장이 `BEGIN` 이다. pysqlite 는 DML 앞에서만 스스로
## 트랜잭션을 열어, 안 그러면 첫 ALTER 가 밖에서 혼자 커밋된다 — 검토가 재서 잡았다)

1. 각 run 의 group_name 을 그 run 이 가리키던 품목의 group_name 으로 채운다
   (칸이 없으면 먼저 만든다 · 이미 값이 있으면 그대로)
2. 같은 (team_key, name) 의 품목을 하나로 모은다 — 남기는 것은 id 가 작은 쪽,
   사라지는 품목을 가리키던 run 의 item_id 는 남기는 쪽으로. 사라지는 쪽의
   unit·note 는 버리지 않는다 — unit 은 남는 쪽이 비었을 때 그 값으로, note 는
   서로 다른 것을 「 / 」 로 이어 남는 쪽에 둔다(0장)
3. 그러고도 (회차·품목·묶음)이 겹치는 run 이 있으면 **아무것도 바꾸지 않고**
   몇 건인지 말한다 — 조용히 넘기지 않는다. 사람이 그 줄을 정리한 뒤 다시 돌린다
4. 옛 표를 `_old` 로 이름을 바꾸고 새 모양의 표 둘을 세운 뒤 행을 옮겨 담고 옛
   표를 지운다. SQLite 는 유니크 제약을 그 자리에서 못 걷어 표를 다시 세운다

전부 SQL 로 합니다 — ORM 은 이미 새 모양이라 옛 칸을 못 읽고, 세션이 autoflush=False
라 방금 넣은 행을 select 가 못 보는 함정도 그래서 없습니다.

## 기본은 미리보기

`--실행` 을 붙였을 때만 바꿉니다(계정정리.py · 비품옮기기.py 와 같은 꼴). 바꾸기
직전에 `VACUUM INTO` 사본을 뜨고, 세션이 여는 파일과 사본을 뜰 파일이 다르면 아무것도
안 합니다(11-2). 미리보기는 품목 수 · 합쳐질 품목 수 · run 수 · 묶음이 채워질 run 수 ·
겹침 수만 찍습니다 — 사람 이름은 찍지 않습니다.

이미 새 모양이면 「옮길 것이 없습니다」 라고 말하고 아무것도 안 합니다.

## 되돌리기

사본이 `data/backups/app-<때>.db` 로 떠 있습니다. 서버를 끄고 그 파일을 `data/app.db`
로 되돌리면 옮기기 전입니다(11-2 「되돌리기」 — 같은 날짜의 uploads·vapid 는 이
스크립트가 안 건드렸으므로 DB 만).

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/비품묶음옮기기.py           # 미리보기
    .venv\\Scripts\\python.exe scripts/비품묶음옮기기.py --실행    # 실제로 옮김
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
from sqlalchemy.engine import make_url                        # noqa: E402
from sqlalchemy.exc import OperationalError                   # noqa: E402
from sqlalchemy.orm import Session                            # noqa: E402

from app import config                                        # noqa: E402
from app.db import Base, SessionLocal                         # noqa: E402
from app.models import EquipmentItem, EquipmentRun            # noqa: E402
from scripts import backup                                    # noqa: E402


def 칸들(db: Session, 표: str) -> set[str]:
    return {row[1] for row in db.execute(text(f"PRAGMA table_info({표})"))}


def 옛모양인가(db: Session) -> bool:
    """묶음이 품목에 있으면 옛 모양이다. 표가 없으면(새 DB 라 아직 안 만들어짐) 아니다."""
    return "group_name" in 칸들(db, "equipment_items")


def _묶음식(db: Session) -> str:
    """run 의 묶음을 무엇으로 볼지 — 칸이 있으면 그것(비면 품목 것), 없으면 품목 것."""
    if "group_name" in 칸들(db, "equipment_runs"):
        return "COALESCE(NULLIF(r.group_name, ''), i.group_name, '')"
    return "COALESCE(i.group_name, '')"


def 셈(db: Session) -> dict[str, int]:
    """미리보기가 찍는 다섯 수 — 이름은 없다."""
    묶음 = _묶음식(db)
    품목 = db.execute(text("SELECT COUNT(*) FROM equipment_items")).scalar_one()
    남을 = db.execute(text(
        "SELECT COUNT(*) FROM (SELECT 1 FROM equipment_items GROUP BY team_key, name)")).scalar_one()
    run = db.execute(text("SELECT COUNT(*) FROM equipment_runs")).scalar_one()
    if "group_name" in 칸들(db, "equipment_runs"):
        채울 = db.execute(text("SELECT COUNT(*) FROM equipment_runs WHERE group_name = ''")).scalar_one()
    else:
        채울 = run
    겹침 = db.execute(text(f"""
        SELECT COUNT(*) - (SELECT COUNT(*) FROM (
            SELECT 1 FROM equipment_runs r
            JOIN equipment_items i ON i.id = r.item_id
            GROUP BY r.retreat_id,
                     (SELECT MIN(o.id) FROM equipment_items o
                       WHERE o.team_key = i.team_key AND o.name = i.name),
                     {묶음}))
        FROM equipment_runs""")).scalar_one()
    # 사라질 품목 중 unit·note 를 가진 것 — 남는 쪽에 합쳐진다(버리지 않는다)
    합칠 = db.execute(text("""
        SELECT COUNT(*) FROM equipment_items o
         WHERE o.id <> (SELECT MIN(o2.id) FROM equipment_items o2
                         WHERE o2.team_key = o.team_key AND o2.name = o.name)
           AND (o.unit IS NOT NULL OR o.note IS NOT NULL)""")).scalar_one()
    return {"품목": 품목, "합쳐질품목": 품목 - 남을, "run": run, "묶음채울run": 채울,
            "겹침": 겹침, "unit·note합칠": 합칠}


def 미리보기(수: dict[str, int]) -> None:
    print(f"품목 {수['품목']}개 (합쳐질 품목 {수['합쳐질품목']}개 · 그중 unit·note 를 남는 쪽에 합칠 것 "
          f"{수['unit·note합칠']}개) · run {수['run']}개 "
          f"(묶음이 채워질 run {수['묶음채울run']}개) · 겹침 {수['겹침']}건")
    if 수["겹침"]:
        print("!! 합치면 (회차·품목·묶음)이 겹치는 run 이 있습니다 — 실행해도 옮기지 않고 멈춥니다.")
    print("바꾸지 않았습니다. 실제로 옮기려면:")
    print("    python scripts/비품묶음옮기기.py --실행")


def 사본을_뜬다() -> pathlib.Path:
    """되돌릴 수 없으므로 먼저 뜬다 — 계정정리.py 와 같은 검사·같은 자리."""
    원본 = pathlib.Path(config.DATA_DIR) / "app.db"
    여는것 = make_url(config.DATABASE_URL).database
    if not 여는것 or pathlib.Path(여는것).resolve() != 원본.resolve():
        raise RuntimeError(
            f"세션이 여는 DB({여는것})와 사본을 뜰 파일({원본})이 다릅니다 — 옮기지 않았습니다.")
    사본 = backup.snapshot(원본, pathlib.Path(config.DATA_DIR) / "backups")
    print(f"  사본을 떴습니다: {사본.name}  ({사본.stat().st_size:,} 바이트)")
    return 사본


ITEM_COLS = "id, team_key, name, unit, note, created_at"
RUN_COLS = ("id, retreat_id, item_id, group_name, included, quantity, location, checked, "
            "checked_by_id, checked_by_name, checked_at, sort_order")


def 옮긴다(db: Session) -> dict[str, int]:
    """사본을 먼저 뜨고, 한 트랜잭션 안에서 채우고 · 모으고 · 표를 다시 세운다."""
    사본을_뜬다()
    conn = db.connection()
    x = lambda sql, **kw: conn.execute(text(sql), kw)  # noqa: E731

    # **여기서 트랜잭션을 연다.** pysqlite 는 DML 앞에서만 BEGIN 을 내므로, 이것이 없으면
    # 아래 첫 ALTER 가 밖에서 혼자 커밋되어 「한 트랜잭션」 이 거짓이 된다 (검토가 잼)
    x("BEGIN")

    # 1. run 의 묶음을 품목의 묶음으로
    if "group_name" not in 칸들(db, "equipment_runs"):
        x("ALTER TABLE equipment_runs ADD COLUMN group_name VARCHAR(100) NOT NULL DEFAULT ''")
    채움 = x("""UPDATE equipment_runs SET group_name =
                  (SELECT COALESCE(i.group_name, '') FROM equipment_items i WHERE i.id = equipment_runs.item_id)
                WHERE group_name = ''""").rowcount

    # 2·3. 남길 품목(id 가 작은 쪽)으로 잇고, 겹치면 멈춘다 — 아무것도 안 바꾼 채
    x("""CREATE TEMP TABLE _eq_map AS
           SELECT o.id AS id,
                  (SELECT MIN(o2.id) FROM equipment_items o2
                    WHERE o2.team_key = o.team_key AND o2.name = o.name) AS keep
             FROM equipment_items o""")
    겹침 = x("""SELECT COUNT(*) - (SELECT COUNT(*) FROM (
                    SELECT 1 FROM equipment_runs r JOIN _eq_map m ON m.id = r.item_id
                    GROUP BY r.retreat_id, m.keep, r.group_name))
                FROM equipment_runs""").scalar_one()
    수 = {"품목": x("SELECT COUNT(*) FROM equipment_items").scalar_one(),
          "남는품목": x("SELECT COUNT(DISTINCT keep) FROM _eq_map").scalar_one(),
          "run": x("SELECT COUNT(*) FROM equipment_runs").scalar_one(),
          "묶음채움": 채움, "겹침": 겹침}
    if 겹침:
        db.rollback()
        return 수

    # 4. 표를 다시 세운다 — 옛 것은 _old 로, 이름 붙은 인덱스는 걷고(새 표가 같은 이름을
    #    쓴다), 새 모양을 create_all 로 세우고, 행을 옮겨 담는다
    for (idx,) in x("""SELECT name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL
                       AND tbl_name IN ('equipment_items', 'equipment_runs')""").all():
        x(f'DROP INDEX "{idx}"')
    x("ALTER TABLE equipment_runs RENAME TO equipment_runs_old")
    x("ALTER TABLE equipment_items RENAME TO equipment_items_old")
    Base.metadata.create_all(bind=conn, tables=[EquipmentItem.__table__, EquipmentRun.__table__])
    # 남는 품목 한 줄 — unit 은 남는 쪽 것이 비면 사라지는 쪽 것, note 는 서로 다른 것을
    # 「 / 」 로 이어 붙인다. 버리면 0장(아무것도 잃지 않는다)에 걸린다
    x("""INSERT INTO equipment_items (id, team_key, name, unit, note, created_at)
         SELECT k.id, k.team_key, k.name,
                COALESCE(k.unit, (SELECT MAX(o.unit) FROM equipment_items_old o
                                   WHERE o.team_key = k.team_key AND o.name = k.name)),
                (SELECT group_concat(n, ' / ') FROM (
                     SELECT DISTINCT o.note AS n FROM equipment_items_old o
                      WHERE o.team_key = k.team_key AND o.name = k.name AND o.note IS NOT NULL
                      ORDER BY o.id)),
                k.created_at
           FROM equipment_items_old k WHERE k.id IN (SELECT keep FROM _eq_map)""")
    x(f"""INSERT INTO equipment_runs ({RUN_COLS})
          SELECT r.id, r.retreat_id, m.keep, r.group_name, r.included, r.quantity, r.location,
                 r.checked, r.checked_by_id, r.checked_by_name, r.checked_at, r.sort_order
            FROM equipment_runs_old r JOIN _eq_map m ON m.id = r.item_id""")
    x("DROP TABLE equipment_runs_old")
    x("DROP TABLE equipment_items_old")
    x("DROP TABLE _eq_map")
    깨진 = x("PRAGMA foreign_key_check(equipment_runs)").all()
    if 깨진:
        db.rollback()
        raise RuntimeError(f"옮긴 뒤 FK 가 {len(깨진)}건 깨져 있어 되돌렸습니다.")
    db.commit()
    return 수


def 옮기기(db: Session, 실행: bool) -> int:
    if not 옛모양인가(db):
        print("옮길 것이 없습니다 — 비품 표가 이미 새 모양(묶음이 회차에)입니다.")
        return 0
    if not 실행:
        미리보기(셈(db))
        return 0
    수 = 옮긴다(db)
    if 수["겹침"]:
        print(f"!! 옮기지 않았습니다 — 합치면 (회차·품목·묶음)이 겹치는 run 이 {수['겹침']}건 있습니다. "
              "그 줄을 사람이 정리한 뒤 다시 돌리세요. 표는 그대로입니다(사본은 떴습니다).")
        return 1
    print(f"옮겼습니다: 품목 {수['품목']}개 → {수['남는품목']}개 · run {수['run']}개 그대로 · "
          f"묶음을 채운 run {수['묶음채움']}개")
    print("품목의 묶음 칸과 옛 유니크를 걷고 새 유니크 둘 — (team_key, name) · (retreat_id, item_id, group_name) — 을 걸었습니다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="비품의 묶음을 품목에서 회차로 옮깁니다 (4-18).",
        epilog="기본은 미리보기입니다. 실제로 옮기려면 --실행 을 붙이세요.",
    )
    ap.add_argument("--실행", action="store_true", help="실제로 옮깁니다")
    args = ap.parse_args()
    with SessionLocal() as db:
        try:
            return 옮기기(db, getattr(args, "실행"))
        except OperationalError:
            print("데이터베이스를 열었는데 표가 없습니다 — 빈 파일을 만든 것 같습니다.")
            print(f"  지금 보고 있는 곳: {config.DATABASE_URL}")
            print("  DCB_DATA_DIR 이 운영 데이터 폴더를 가리키는지 확인하세요.")
            return 1


if __name__ == "__main__":
    sys.exit(main())
