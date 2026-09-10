# -*- coding: utf-8 -*-
"""체크리스트에 있던 비품 목록을 비품 표로 옮깁니다 (4-18).

## 무엇을 옮기나

`task_id` 가 비어 있고 `moved_at` 이 비어 있는 체크리스트 — 업무에 딸린
준비물 체크리스트는 건드리지 않습니다.

- `Checklist.name` → `EquipmentItem.group_name`(묶음)
- `Checklist.department_id` 가 가리키는 부서의 **키** → `EquipmentItem.team_key`
  (부서가 없거나 키가 없으면 빈 문자열 — 총무팀 소관)
- `ChecklistItem.label` → `EquipmentItem.name`
- 수량 · 체크 · 누가 · 언제 · 순서 → `EquipmentRun` 그대로

같은 (team_key, group_name, name) 이 라이브러리에 이미 있으면 새 행을 만들지
않고 그것을 씁니다. 옮긴 체크리스트에는 `moved_at` 을 찍고 **행과 항목은
지우지 않습니다**(0장).

## 기본은 미리보기

`--실행` 을 붙였을 때만 바꿉니다(계정정리.py 와 같은 꼴). 바꾸기 직전에
`VACUUM INTO` 사본을 뜨고, 사본이 안 떠지면 아무것도 바꾸지 않습니다(11-2).
미리보기는 체크리스트 이름 · 항목 수 · 새로 설 라이브러리 행 수만 찍습니다 —
사람 이름은 찍지 않습니다. 「바꾸지 않았습니다」 는 행 기준의 말입니다 — 표 둘과
`moved_at` 칸은 미리보기에서도 붙습니다(부팅과 같은 `init_db` 를 먼저 부르므로).

두 번째로 돌리면 옮길 것이 없습니다 — 그때 「성공」 이 아니라 「옮길 것이
없습니다」 라고 말합니다.

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/비품옮기기.py           # 미리보기
    .venv\\Scripts\\python.exe scripts/비품옮기기.py --실행    # 실제로 옮김
"""

from __future__ import annotations

import sys as _sys

for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                 # noqa: E402
from sqlalchemy.engine import make_url                        # noqa: E402
from sqlalchemy.exc import OperationalError                   # noqa: E402
from sqlalchemy.orm import Session                            # noqa: E402

from app import config                                        # noqa: E402
from app.db import SessionLocal                               # noqa: E402
from app.models import Checklist, EquipmentItem, EquipmentRun, Retreat  # noqa: E402
from scripts import backup                                    # noqa: E402


def 대상(db: Session) -> list[Checklist]:
    """업무에 안 딸렸고 아직 안 옮긴 체크리스트."""
    return list(db.scalars(
        select(Checklist)
        .where(Checklist.task_id.is_(None), Checklist.moved_at.is_(None))
        .order_by(Checklist.retreat_id, Checklist.sort_order, Checklist.id)
    ))


def 팀키(checklist: Checklist) -> str:
    dept = checklist.department
    return (dept.key or "") if dept is not None else ""


def 열쇠들(db: Session, 목록: list[Checklist]) -> tuple[set[tuple[str, str, str]], int]:
    """옮길 항목의 (team_key, group_name, name) 전부와, 그중 라이브러리에 없는 수."""
    있는 = {(i.team_key, i.group_name, i.name) for i in db.scalars(select(EquipmentItem))}
    전부: set[tuple[str, str, str]] = set()
    for c in 목록:
        for it in c.items:
            전부.add((팀키(c), c.name, it.label))
    return 전부, len(전부 - 있는)


def 미리보기(db: Session, 목록: list[Checklist]) -> None:
    항목수 = sum(len(c.items) for c in 목록)
    _, 새행 = 열쇠들(db, 목록)
    print(f"옮길 체크리스트 {len(목록)}개 · 항목 {항목수}개 · 새로 설 라이브러리 행 {새행}개")
    for c in 목록:
        r = db.get(Retreat, c.retreat_id)
        print(f"  [{r.name if r else c.retreat_id}] {c.name} — 항목 {len(c.items)}개")
    print("바꾸지 않았습니다. 실제로 옮기려면:")
    print("    python scripts/비품옮기기.py --실행")


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


def 옮긴다(db: Session, 목록: list[Checklist]) -> dict[str, int]:
    """사본을 먼저 뜨고 옮긴다. 라이브러리에 있는 품목은 그것을 쓴다."""
    사본을_뜬다()
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    수 = {"체크리스트": 0, "항목": 0, "새품목": 0, "겹침": 0}
    만든것: set[tuple[int, int]] = set()
    for c in 목록:
        key = 팀키(c)
        for it in c.items:
            item = db.scalar(select(EquipmentItem).where(
                EquipmentItem.team_key == key, EquipmentItem.group_name == c.name,
                EquipmentItem.name == it.label))
            if item is None:
                item = EquipmentItem(team_key=key, group_name=c.name, name=it.label)
                db.add(item)
                db.flush()
                수["새품목"] += 1
            # 같은 회차에 같은 품목이 이미 있으면(한 체크리스트에 같은 이름이 둘)
            # 유니크에 걸리므로 만들지 않고 센다 — 조용히 넘기지 않는다.
            # **세션이 autoflush=False 라** 방금 add 한 run 을 select 가 못 본다 —
            # 이 판에서 만든 것을 집합으로 들고 함께 본다 (검토가 짚음)
            if (c.retreat_id, item.id) in 만든것 or db.scalar(select(EquipmentRun).where(
                    EquipmentRun.retreat_id == c.retreat_id, EquipmentRun.item_id == item.id)):
                수["겹침"] += 1
                continue
            만든것.add((c.retreat_id, item.id))
            db.add(EquipmentRun(
                retreat_id=c.retreat_id, item_id=item.id, included=True,
                quantity=it.quantity, checked=it.checked, checked_by_id=it.checked_by_id,
                checked_by_name=it.checked_by_name, checked_at=it.checked_at,
                sort_order=it.sort_order,
            ))
            수["항목"] += 1
        c.moved_at = now
        수["체크리스트"] += 1
    db.commit()
    return 수


def 옮기기(db: Session, 실행: bool) -> int:
    목록 = 대상(db)
    if not 목록:
        print("옮길 것이 없습니다 — 업무에 안 딸린 체크리스트가 전부 이미 옮겨졌거나 없습니다.")
        return 0
    if not 실행:
        미리보기(db, 목록)
        return 0
    수 = 옮긴다(db, 목록)
    print(f"옮겼습니다: 체크리스트 {수['체크리스트']}개 · 항목 {수['항목']}개 · "
          f"새 라이브러리 행 {수['새품목']}개"
          + (f" · 같은 회차에 이미 있어 건너뛴 항목 {수['겹침']}개" if 수["겹침"] else ""))
    print("체크리스트의 행과 항목은 그대로 남았고 moved_at 만 찍혔습니다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="체크리스트의 비품 목록을 비품 표로 옮깁니다 (4-18).",
        epilog="기본은 미리보기입니다. 실제로 옮기려면 --실행 을 붙이세요.",
    )
    ap.add_argument("--실행", action="store_true", help="실제로 옮깁니다")
    args = ap.parse_args()

    # 표 둘과 moved_at 칸은 앱이 뜰 때 붙는다(부팅 마이그레이션) — 서버를 다시 켜기
    # 전에 이 스크립트를 먼저 돌려도 걸리지 않게 같은 것을 여기서 한 번 부른다.
    # 이미 있으면 아무 일도 안 한다
    from app.db import init_db
    init_db()

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
