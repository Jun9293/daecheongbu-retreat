# -*- coding: utf-8 -*-
"""지금 있는 영수증을 잇기 표에 한 번 잇습니다 (7-4 · 2026-09-14 재정 차례 4).

## 왜 필요한가

영수증 한 장에 지출 여럿이 걸릴 수 있게 **잇기 표**(`expense_receipt_links`)를
두었고, 어느 지출에 걸렸는가는 이제 그 표만 말합니다. 그 표가 생기기 전의
영수증은 `expense_receipts.expense_id` 하나만 들고 있어서, **잇기 줄이 없으면
어느 지출에도 안 보입니다.**

## 부팅이 아니라 이 스크립트가 하는 까닭

잇기 줄을 만드는 것은 **값을 채우는 전환**입니다. 부팅이 칸을 붙이는 것은
「운영은 읽기만」 의 밖이지만 값을 채우는 것은 안이고(11-2), 부팅이 값을 채우는
전환을 더 늘리지 않기로 했습니다(봐둘것 BA-h). 그래서 미리보기 → 실행 → 다시
세기를 지나는 이 자리에 둡니다.

## 무엇을 하나

**잇기 줄이 하나도 없는** 영수증마다 `expense_id` 가 가리키는 지출에 줄 하나를
만듭니다. 뗀 적이 있는 영수증(끊긴 줄이 남은 것)은 건드리지 않습니다 — 사람이
뗀 것을 다시 붙이면 안 됩니다. 두 번째로 돌리면 「이을 것이 없습니다」 입니다.

## 기본은 미리보기

`--실행` 일 때만 바꿉니다. 바꾸기 직전에 `VACUUM INTO` 사본을 뜨고, 세션이 여는
파일과 사본을 뜰 파일이 다르면 아무것도 안 합니다(비품비고옮기기.py 와 같은 꼴).
**수만** 찍습니다 — 메모·파일 이름은 안 찍습니다.

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/영수증잇기옮기기.py
    .venv\\Scripts\\python.exe scripts/영수증잇기옮기기.py --실행
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글이 깨지지 않게 한다 (계정정리.py 와 같다)
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
from sqlalchemy.orm import Session                               # noqa: E402

from app import config                                           # noqa: E402
from app.db import SessionLocal                                  # noqa: E402
from scripts import backup                                       # noqa: E402


class 멈춤(Exception):
    """사람이 봐야 하는 자리 — 아무것도 바꾸지 않고 멈춘다."""


_안이어진 = ("FROM expense_receipts r WHERE NOT EXISTS"
           " (SELECT 1 FROM expense_receipt_links l WHERE l.receipt_id = r.id)")


def 센다(db: Session) -> dict[str, int]:
    """**아무것도 안 바꾼다** — 미리보기와 실행과 다시 세기가 같은 셈을 쓴다."""
    한줄 = lambda q: db.execute(text(q)).scalar_one()             # noqa: E731
    return {
        "영수증": 한줄("SELECT COUNT(*) FROM expense_receipts"),
        "이을것": 한줄(f"SELECT COUNT(*) {_안이어진}"),
        "산잇기": 한줄("SELECT COUNT(*) FROM expense_receipt_links WHERE detached_at IS NULL"),
        "끊긴잇기": 한줄("SELECT COUNT(*) FROM expense_receipt_links WHERE detached_at IS NOT NULL"),
    }


def 표가있나(db: Session) -> bool:
    return bool(db.execute(text(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='expense_receipt_links'")).first())


def 사본을_뜬다() -> pathlib.Path:
    원본 = pathlib.Path(config.DATA_DIR) / "app.db"
    여는것 = make_url(config.DATABASE_URL).database
    if not 여는것 or pathlib.Path(여는것).resolve() != 원본.resolve():
        raise 멈춤(f"세션이 여는 DB({여는것})와 사본을 뜰 파일({원본})이 다릅니다 — 잇지 않았습니다.")
    사본 = backup.snapshot(원본, pathlib.Path(config.DATA_DIR) / "backups")
    print(f"  사본을 떴습니다: {사본.name}  ({사본.stat().st_size:,} 바이트)")
    return 사본


def 잇는다(db: Session) -> int:
    """잇기 줄이 하나도 없는 영수증을 처음 붙은 지출에 잇는다 — 한 트랜잭션. 만든 줄 수를 돌려준다."""
    return db.execute(text(
        "INSERT INTO expense_receipt_links (receipt_id, expense_id, attached_at)"
        f" SELECT r.id, r.expense_id, CURRENT_TIMESTAMP {_안이어진}")).rowcount


def 옮기기(db: Session, 실행: bool, *, 사본: bool = True) -> int:
    if not 표가있나(db):
        raise 멈춤("expense_receipt_links 표가 아직 없습니다 — 이 표는 앱이 뜰 때 섭니다.\n"
                  "  서버를 한 번 켠 뒤(docs/배포-안내.md 12-1) 다시 돌리세요.")
    수 = 센다(db)
    print(f"영수증 {수['영수증']}장 · 산 잇기 {수['산잇기']}줄 · 끊긴 잇기 {수['끊긴잇기']}줄")
    if not 수["이을것"]:
        print("이을 것이 없습니다 — 잇기 줄이 하나도 없는 영수증이 0장입니다.")
        return 0
    print(f"  잇기 줄이 하나도 없는 영수증 {수['이을것']}장 → 처음 붙은 지출에 한 줄씩 잇습니다")
    if not 실행:
        print("바꾸지 않았습니다. 실제로 이으려면 --실행 을 붙이세요.")
        return 0
    if 사본:
        사본을_뜬다()
    try:
        만든 = 잇는다(db)
        if 만든 != 수["이을것"]:
            raise 멈춤(f"센 수({수['이을것']})와 만든 줄({만든})이 달라 되돌렸습니다.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    뒤 = 센다(db)
    print(f"이었습니다: {만든}줄 · 다시 세면 산 잇기 {뒤['산잇기']}줄 · 이을 것 {뒤['이을것']}장")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="지금 있는 영수증을 잇기 표에 한 번 잇습니다 (7-4).",
        epilog="기본은 미리보기입니다. 실제로 이으려면 --실행 을 붙이세요.",
    )
    ap.add_argument("--실행", action="store_true", help="실제로 잇습니다")
    args = ap.parse_args()
    with SessionLocal() as db:
        try:
            return 옮기기(db, getattr(args, "실행"))
        except 멈춤 as e:
            print(f"!! {e}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
