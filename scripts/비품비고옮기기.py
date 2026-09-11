# -*- coding: utf-8 -*-
"""비품 비고를 품목에서 회차(run)로 옮깁니다 (4-18 · 2026-09-11 도막 4).

## 왜 옮기는가

비고는 **「어디서 빌린다」·「이번엔 두 상자」** 같은, 그 회차 그 자리에서 쓰는
말입니다. 그런데 `EquipmentItem.note` 에 있어서 **회차를 넘어 따라다녔습니다** —
품목은 라이브러리라 다음 회차에도 같은 행이고, 지난 회차의 사정이 새 회차의
설명처럼 보입니다. 묶음(`group_name`)을 품목에서 회차로 옮긴 것과 같은 판단이고
(도막 2), 그때 비고만 남겨 둔 것이 이번에 걸렸습니다.

**자국은 들여오기 코드에 있었습니다** — 시트의 비고를 **「비어 있을 때만」** 적고
있었습니다. 자리가 맞았다면 그런 조건이 필요 없습니다. 한 칸을 여러 회차가
나눠 쓰고 있어서 서로 밀어내지 않으려고 둔 조건이었습니다.

## 무엇을 하나

품목의 비고를 **그 품목의 run 전부**에 같은 값으로 넣고, 다 옮긴 뒤에
`equipment_items.note` 칸을 걷습니다.

- **run 이 여럿이면 전부에 넣습니다.** 어느 회차의 말인지 지금은 알 수 없으므로
  고르지 않습니다 — 고르면 나머지가 조용히 사라집니다. 사람이 화면에서 지웁니다
- **run 이 하나도 없는 품목의 비고는 갈 곳이 없습니다.** 옮기지 않고 **몇 건인지
  세어 말합니다.** 그 값은 칸을 걷는 순간 사라지므로, **그런 품목이 하나라도
  있으면 칸을 안 걷고 멈춥니다** — 세어 놓고 버리면 센 뜻이 없습니다
- **이미 run 에 비고가 있으면 덮지 않습니다.** 사람이 화면에서 적은 것이
  시트에서 온 옛 값에 밀리면 안 됩니다

## 부팅은 이 일을 하지 않습니다

`app/db.py` 는 `equipment_runs.note` 를 **붙이기만** 합니다. 칸을 걷는 것은
여기서만 합니다 — 부팅이 걷으면 **아직 안 옮긴 값이 서버를 켜는 순간 사라집니다.**
부팅은 남은 값이 있으면 한 줄 말하고 지나갑니다(`_warn_old_equipment_shape`).

## 순서

    묶음옮기기  →  **비고옮기기**  →  비품옮기기 · 들여오기

앞의 둘은 표의 모양을 바꾸는 것이라 먼저입니다.

## 기본은 미리보기

`--실행` 일 때만 바꿉니다(계정정리.py · 비품옮기기.py 와 같은 꼴). 바꾸기 직전에
`VACUUM INTO` 사본을 뜨고, **세션이 여는 파일과 사본을 뜰 파일이 다르면 아무것도
안 합니다**(11-2). 미리보기는 **수만** 찍습니다 — 비고 본문도 품목 이름도 안
찍습니다. 거기에 사람 이름이 섞여 있을 수 있습니다.

두 번째로 돌리면 「옮길 것이 없습니다」 입니다.

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/비품비고옮기기.py
    .venv\\Scripts\\python.exe scripts/비품비고옮기기.py --실행
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글·기호가 깨지지 않게 한다 — 안내를 못 찍고
# 죽으면 무엇이 옮겨졌는지 사람이 알 수 없다 (계정정리.py 와 같다)
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import text                                      # noqa: E402
from sqlalchemy.engine import make_url                           # noqa: E402
from sqlalchemy.exc import OperationalError                      # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from app import config                                           # noqa: E402
from app.db import SessionLocal                                  # noqa: E402
from scripts import backup                                       # noqa: E402


class 멈춤(Exception):
    """사람이 봐야 하는 자리 — 아무것도 바꾸지 않고 멈춘다."""


def 칸들(db: Session, 표: str) -> set[str]:
    return {r[1] for r in db.execute(text(f"PRAGMA table_info({표})"))}


def 옛칸이있나(db: Session) -> bool:
    """`equipment_items.note` 가 아직 있는가 — 없으면 이미 옮긴 것이다."""
    return "note" in 칸들(db, "equipment_items")


def 센다(db: Session) -> dict[str, int]:
    """**아무것도 안 바꾼다** — 미리보기와 실행이 같은 셈을 쓴다."""
    한줄 = lambda q: db.execute(text(q)).scalar_one()             # noqa: E731
    # **별칭을 받는다** — 조인에서는 `note` 하나만 쓰면 어느 표의 것인지
    # 모호해서 sqlite 가 거절한다. 두 칸 이름이 같은 자리라 늘 붙여 쓴다
    값있는 = lambda 별: f"{별}.note IS NOT NULL AND {별}.note != ''"   # noqa: E731
    값있는품목 = 값있는("i")
    return {
        "품목": 한줄("SELECT COUNT(*) FROM equipment_items"),
        "비고있는품목": 한줄(
            f"SELECT COUNT(*) FROM equipment_items i WHERE {값있는품목}"),
        # 값을 받을 run — 이미 제 비고가 있는 run 은 덮지 않으므로 뺀다
        "채울run": 한줄(f"""
            SELECT COUNT(*) FROM equipment_runs r
              JOIN equipment_items i ON i.id = r.item_id
             WHERE {값있는품목}
               AND (r.note IS NULL OR r.note = '')"""),
        "이미있는run": 한줄(f"""
            SELECT COUNT(*) FROM equipment_runs r
              JOIN equipment_items i ON i.id = r.item_id
             WHERE {값있는품목}
               AND r.note IS NOT NULL AND r.note != ''"""),
        # **갈 곳이 없는 비고 — 「빈 run 이 하나도 없다」 로 묻는다.**
        # 처음에는 「run 이 하나도 없다」 로 물었는데, 그러면 **run 은 있는데 전부
        # 제 비고를 갖고 있는 품목**이 0 으로 세어지고 UPDATE 도 한 줄 안 걸려,
        # 칸을 걷는 순간 그 값이 사라진다(검토가 재현했다). 바깥 문과 안쪽 문이
        # 서로 다른 것을 보고 있던 자리다
        "갈곳없는비고": 한줄(f"""
            SELECT COUNT(*) FROM equipment_items i
             WHERE {값있는품목}
               AND NOT EXISTS (SELECT 1 FROM equipment_runs r
                                WHERE r.item_id = i.id
                                  AND (r.note IS NULL OR r.note = ''))"""),
        # 그중 「run 이 아예 없는 것」 — 사람이 무엇을 해야 하는지 갈리므로 따로 센다
        "run없는품목": 한줄(f"""
            SELECT COUNT(*) FROM equipment_items i
             WHERE {값있는품목}
               AND NOT EXISTS (SELECT 1 FROM equipment_runs r WHERE r.item_id = i.id)"""),
        "run둘이상": 한줄(f"""
            SELECT COUNT(*) FROM (
                SELECT r.item_id FROM equipment_runs r
                  JOIN equipment_items i ON i.id = r.item_id
                 WHERE {값있는품목}
                 GROUP BY r.item_id HAVING COUNT(*) > 1)"""),
    }


def 미리보기(수: dict[str, int]) -> None:
    print(f"품목 {수['품목']}개 · 그중 비고가 있는 품목 {수['비고있는품목']}개")
    print(f"  옮겨 담을 run {수['채울run']}개 "
          f"(run 이 둘 이상인 품목 {수['run둘이상']}개 — 전부에 같은 값을 넣습니다) · "
          f"이미 제 비고가 있어 안 건드릴 run {수['이미있는run']}개")
    if 수["갈곳없는비고"]:
        print(f"!! 갈 곳이 없는 비고 {수['갈곳없는비고']}개 "
              f"(그중 run 이 아예 없는 품목 {수['run없는품목']}개 · "
              f"나머지는 run 이 전부 제 비고를 갖고 있습니다) — 옮길 자리가 없습니다.")
        print("   그대로 두면 칸을 걷을 때 사라지므로 실행해도 걷지 않고 멈춥니다.")
        print("   그 품목에 run 을 만들어 주거나 그 run 의 비고를 비우고 다시 돌리세요.")
    else:
        print("  갈 곳이 없는 비고 0개 — 걷어도 잃는 값이 없습니다.")
    print("바꾸지 않았습니다. 실제로 옮기려면:")
    print("    python scripts/비품비고옮기기.py --실행")


def 사본을_뜬다() -> pathlib.Path:
    원본 = pathlib.Path(config.DATA_DIR) / "app.db"
    여는것 = make_url(config.DATABASE_URL).database
    if not 여는것 or pathlib.Path(여는것).resolve() != 원본.resolve():
        raise 멈춤(f"세션이 여는 DB({여는것})와 사본을 뜰 파일({원본})이 다릅니다 — 옮기지 않았습니다.")
    사본 = backup.snapshot(원본, pathlib.Path(config.DATA_DIR) / "backups")
    print(f"  사본을 떴습니다: {사본.name}  ({사본.stat().st_size:,} 바이트)")
    return 사본


def 옮긴다(db: Session, 수: dict[str, int]) -> None:
    """**한 트랜잭션이다.** 옮기고 나서 칸을 걷는다 — 순서가 거꾸로면 값을 잃는다."""
    사본을_뜬다()
    x = lambda q: db.execute(text(q))                             # noqa: E731
    # pysqlite 는 DML 앞에서만 BEGIN 을 낸다 — ALTER 로 시작하면 그 한 줄이
    # 트랜잭션 **밖에서** 커밋된다(도막 2 에서 검토가 잰 자리). 먼저 연다
    x("BEGIN")
    try:
        x("""UPDATE equipment_runs
                SET note = (SELECT i.note FROM equipment_items i WHERE i.id = equipment_runs.item_id)
              WHERE (note IS NULL OR note = '')
                AND EXISTS (SELECT 1 FROM equipment_items i
                             WHERE i.id = equipment_runs.item_id
                               AND i.note IS NOT NULL AND i.note != '')""")
        # **다 옮긴 뒤에만 걷는다.** 갈 곳 없는 값이 있으면 여기 오지 않는다
        # (부르는 쪽이 막는다) — 그래도 한 번 더 세어 본다. 세는 것과 거는 것이
        # 갈리면 「센 뜻이 없다」 가 된다
        # **그 값이 실제로 닿았는가** 를 묻는다 — 「run 에 무언가 적혀 있는가」 가
        # 아니다. 그렇게 물으면 사람이 적어 둔 딴 말이 있는 run 이 「닿았다」 로
        # 세어져, 품목의 비고가 안 옮겨진 채 칸이 걷힌다
        남음 = x("""SELECT COUNT(*) FROM equipment_items i
                     WHERE i.note IS NOT NULL AND i.note != ''
                       AND NOT EXISTS (SELECT 1 FROM equipment_runs r
                                        WHERE r.item_id = i.id AND r.note = i.note)""").scalar_one()
        if 남음:
            db.rollback()
            raise 멈춤(f"옮기고 나서도 갈 곳 없는 비고가 {남음}개 남아 걷지 않고 되돌렸습니다.")
        x("ALTER TABLE equipment_items DROP COLUMN note")
        db.commit()
    except Exception:
        db.rollback()
        raise


def 옮기기(db: Session, 실행: bool) -> int:
    # **회차 쪽 칸이 없으면 아무것도 못 한다.** 그 칸은 부팅이 붙이므로(4-18),
    # 서버를 한 번도 안 켠 DB 에 이것부터 돌리면 질의가 「그런 칸 없음」 으로
    # 터지고 `OperationalError` 갈래가 **표가 없다**는 엉뚱한 안내를 냅니다 —
    # 그 안내를 따라가면 빈 DB 를 새로 만드는 길입니다(검토가 재현했다).
    # 그래서 여기서 먼저 보고 사람 말로 말한다.
    if "note" not in 칸들(db, "equipment_runs"):
        raise 멈춤("equipment_runs 에 비고 칸이 아직 없습니다 — 이 칸은 앱이 뜰 때 붙습니다.\n"
                  "  서버를 한 번 켠 뒤(docs/배포-안내.md 12-1) 다시 돌리세요.")
    if not 옛칸이있나(db):
        print("옮길 것이 없습니다 — equipment_items 에 비고 칸이 이미 없습니다.")
        return 0
    수 = 센다(db)
    if not 수["비고있는품목"]:
        # 칸만 남고 값이 없다 — 걷는 것은 그대로 한다(모델에 없는 칸이 남으면
        # 다음 사람이 「어느 쪽이 정본인가」 를 다시 묻는다)
        if not 실행:
            print(f"품목 {수['품목']}개 · 비고가 있는 품목 0개 — 옮길 값은 없고 칸만 남았습니다.")
            print("바꾸지 않았습니다. 칸을 걷으려면 --실행 을 붙이세요.")
            return 0
        사본을_뜬다()
        db.execute(text("ALTER TABLE equipment_items DROP COLUMN note"))
        db.commit()
        print("옮길 값은 없어서 칸만 걷었습니다.")
        return 0
    if not 실행:
        미리보기(수)
        return 0
    if 수["갈곳없는비고"]:
        raise 멈춤(f"갈 곳이 없는 비고가 {수['갈곳없는비고']}개 있습니다"
                  f"(그중 run 이 아예 없는 품목 {수['run없는품목']}개) — "
                  "걷으면 그 값이 사라지므로 아무것도 안 했습니다.\n"
                  "  그 품목에 run 을 만들어 주거나 그 run 의 비고를 비우고 다시 돌리세요.")
    옮긴다(db, 수)
    print(f"옮겼습니다: 비고가 있던 품목 {수['비고있는품목']}개 → run {수['채울run']}개 · "
          f"이미 제 비고가 있어 안 건드린 run {수['이미있는run']}개 · "
          f"equipment_items.note 칸을 걷었습니다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="비품 비고를 품목에서 회차(run)로 옮깁니다 (4-18).",
        epilog="기본은 미리보기입니다. 실제로 옮기려면 --실행 을 붙이세요.",
    )
    ap.add_argument("--실행", action="store_true", help="실제로 옮깁니다")
    args = ap.parse_args()

    with SessionLocal() as db:
        try:
            return 옮기기(db, getattr(args, "실행"))
        except 멈춤 as e:
            print(f"!! {e}")
            return 1
        except OperationalError:
            print("데이터베이스를 열었는데 표가 없습니다 — 빈 파일을 만든 것 같습니다.")
            print(f"  지금 보고 있는 곳: {config.DATABASE_URL}")
            print("  DCB_DATA_DIR 이 운영 데이터 폴더를 가리키는지 확인하세요.")
            return 1


if __name__ == "__main__":
    sys.exit(main())
