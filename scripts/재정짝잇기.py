# -*- coding: utf-8 -*-
"""들여온 재정에서 **예산 항목과 못 이은 지출**을 시트 자신의 결산 식 연결로 잇습니다 (2026-09-15 · 봐둘것 BB-h).

2026 여름 회차를 들일 때 `scripts/재정들여오기.py` 는 지출과 예산 항목을 글자(구분 · 항목 · 세부)로 이었고(지금은 결산 식이 기본 · BB-i), 두 탭의 이름이 다른 줄은
「예산 항목 미지정」 으로 들어갔습니다. 그런데 시트는 예산 탭의 결산금액 식으로 **그 지출이 어느 예산 줄에
잡히는지 이미 적어 두었습니다**(7-1). 사람이 그 연결을 정본으로 정했습니다 — 이 스크립트가 그 식을
`재정들여오기.결산식으로` 로 따라가 채웁니다.

- **대상은 들여온 지출 중 예산 항목이 없는 것만**입니다. 이미 항목이 있는 지출(글자로 이은 것 · 사람이 고른 것)은
  안 건드립니다
- 식이 가리키는 예산 줄이 **하나가 아니거나, 그 예산 항목이 지금 취소 표시면** 채우지 않고 짝 표에 남깁니다
- 채우면 예산 항목과 그에 딸린 구분 · 항목 · 세부항목-1 글자가 바뀝니다 — 사람이 화면 「고치기」 에서 고른 것과
  같은 결과입니다(`routers/expenses.py` 의 `update_expense`). 부서 · 금액 · 지원금액은 안 바뀝니다
- 시트 줄과 앱 행은 **들여온 순서로** 맞춥니다 — 예산 항목은 글자 순서가, 지출은 금액 · 날짜 순서가 들여온 대로여야
  하고, 들인 뒤 바뀌어 맞지 않으면 아무것도 안 하고 멈춥니다

값은 찍지 않습니다(건수만). 짝 표는 `data/재정짝잇기.real.md` 에 줄 번호와 까닭만 씁니다.

## 기본은 미리보기

`--실행` 일 때만 바꿉니다. 채울 것이 있을 때만 직전에 `VACUUM INTO` 사본을 뜨고, 세션이 여는 파일과 사본을 뜰 파일이
다르면 아무것도 안 합니다(재정들여오기 의 `사본을_뜬다`). 넣은 뒤 commit 전에 DB 를 다시 세어 계획과 견줍니다.
채울 것이 없으면 「채울 것이 없습니다」 로 끝납니다.

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/재정짝잇기.py data/Belong예산.real.xlsx --회차 1
    .venv\\Scripts\\python.exe scripts/재정짝잇기.py data/Belong예산.real.xlsx --회차 1 --실행
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
from collections import Counter
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select                                  # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from app import config                                               # noqa: E402
from app.db import SessionLocal                                      # noqa: E402
from app.models import ActivityLog, BudgetCategory, ExpenseEntry, Retreat  # noqa: E402
from scripts.비품들여오기 import 멈춤, 회차머리                           # noqa: E402
from scripts.재정들여오기 import 들여오기행위, 결산식으로, 사본을_뜬다, 읽는다  # noqa: E402

짝잇기행위 = "재정_짝잇기"


@dataclass
class 계획:
    수: Counter
    채울: list = field(default_factory=list)      # (지출 id, 예산 항목 id)
    짝: list = field(default_factory=list)        # (지출 시트 줄, 까닭)


def _창(행들: list, 열쇠들: list, 열쇠) -> list:
    """들여온 순서의 열쇠 줄(시트)과 **한 곳에서만** 맞는 앱 행 연속 구간."""
    n = len(열쇠들)
    맞는곳 = [i for i in range(len(행들) - n + 1) if all(열쇠(행들[i + j]) == 열쇠들[j] for j in range(n))]
    return [행들[맞는곳[0] + j] for j in range(n)] if len(맞는곳) == 1 else []


def 고른다(db: Session, retreat: Retreat, 경로: pathlib.Path) -> 계획:
    """미리보기와 실행이 **같은 계획**을 쓴다."""
    if not db.scalar(select(func.count()).select_from(ActivityLog).where(
            ActivityLog.retreat_id == retreat.id, ActivityLog.action == 들여오기행위)):
        raise 멈춤("이 회차에는 시트에서 재정을 들여온 기록이 없습니다 — 먼저 scripts/재정들여오기.py 를 돌리세요.")
    판 = 읽는다(경로)
    식 = 결산식으로(경로)

    예산들 = list(db.scalars(select(BudgetCategory).where(BudgetCategory.retreat_id == retreat.id)
                          .order_by(BudgetCategory.id)))
    예산창 = _창(예산들, [(b["구분"] or "", b["항목"] or "", b["세부"]) for b in 판.예산],
               lambda c: (c.level1, c.level2, c.level3))
    지출들 = list(db.scalars(select(ExpenseEntry).where(ExpenseEntry.retreat_id == retreat.id)
                          .order_by(ExpenseEntry.id)))
    지출창 = _창(지출들, [(e["금액"], e["일자"]) for e in 판.지출], lambda x: (x.amount, x.expense_date))
    if not 예산창 or not 지출창:
        raise 멈춤("들여온 예산 항목이나 지출이 시트와 순서대로 맞지 않습니다(들인 뒤 바뀌었거나 다른 시트) — 아무것도 안 했습니다.")
    예산줄로 = {b["줄"]: c for b, c in zip(판.예산, 예산창)}

    수 = Counter()
    판2 = 계획(수)
    들여온id = {x.id for x in 지출창}
    수["들여온 뒤에 생긴 미지정 지출(안 건드림)"] = sum(
        1 for x in 지출들 if x.id not in 들여온id and x.canceled_at is None and x.budget_category_id is None)
    for e, x in zip(판.지출, 지출창):
        if x.canceled_at is not None:
            continue
        if x.budget_category_id is not None:
            수["이미 예산 항목 있음(안 건드림)"] += 1
            # 글자로 이은 것이 결산 식과 같은지도 같은 판에서 센다 — 두 길이 어긋나면 사람이 본다(봐둘것 BB-i)
            가리킨 = 식.get(e["줄"], set())
            하나 = next(iter(가리킨)) if len(가리킨) == 1 else None
            같은 = 하나 is not None and 예산줄로.get(하나) is not None and 예산줄로[하나].id == x.budget_category_id
            수["이미 이은 것 중 결산 식이 가리키는 항목과 다른 것"] += not 같은
            continue
        수["예산 항목 미지정"] += 1
        가리킴 = 식.get(e["줄"], set())
        if len(가리킴) != 1:
            판2.짝.append((e["줄"], f"결산 식이 가리키는 예산 줄이 {len(가리킴)}개"))
            수["못 채움(식이 가리키는 예산 줄이 하나가 아님)"] += 1
            continue
        c = 예산줄로.get(next(iter(가리킴)))
        if c is None:
            판2.짝.append((e["줄"], "결산 식이 가리키는 줄이 들여온 예산 줄이 아님"))
            수["못 채움(들여온 예산 줄이 아님)"] += 1
            continue
        if c.canceled_at is not None:
            판2.짝.append((e["줄"], "결산 식이 가리키는 예산 항목이 취소 표시"))
            수["못 채움(가리키는 예산 항목이 취소됨)"] += 1
            continue
        판2.채울.append((x.id, c.id))
        수["채울 것"] += 1
    return 판2


def 넣는다(db: Session, retreat: Retreat, 판: 계획) -> None:
    """한 트랜잭션의 안쪽 — commit 은 부르는 쪽이 DB 를 다시 세어 맞을 때만."""
    for 지출id, 예산id in 판.채울:
        x, c = db.get(ExpenseEntry, 지출id), db.get(BudgetCategory, 예산id)
        # 사람이 화면 고치기에서 고른 것과 같은 결과 — 구분·항목·세부항목-1 은 항목의 글자를 따른다(update_expense)
        x.budget_category_id = c.id
        x.level1, x.level2, x.level3a = c.level1, c.level2, c.level3
    db.add(ActivityLog(retreat_id=retreat.id, actor_type="system", actor_name="재정짝잇기",
                       action=짝잇기행위, target_type="retreat", target_id=retreat.id,
                       summary=f"시트 결산 식으로 예산 항목을 이음 — 채움 {len(판.채울)} · 못 채움 {len(판.짝)}",
                       after_value={"채움": len(판.채울), "못 채움": len(판.짝),
                                    "지출 id": [지출id for 지출id, _ in 판.채울]}))
    db.flush()


def 미지정수(db: Session, retreat: Retreat) -> int:
    return db.scalar(select(func.count()).select_from(ExpenseEntry).where(
        ExpenseEntry.retreat_id == retreat.id, ExpenseEntry.canceled_at.is_(None),
        ExpenseEntry.budget_category_id.is_(None))) or 0


def 짝표쓰기(경로: pathlib.Path, 판: 계획) -> None:
    줄 = ["# 재정 짝잇기 — 못 채운 지출 (줄 번호와 까닭만)", "", f"## {len(판.짝)}건", "",
          "| 지출 시트 줄 | 까닭 |", "|---|---|"]
    줄 += [f"| {r} | {까닭} |" for r, 까닭 in 판.짝]
    경로.write_text("\n".join(줄) + "\n", encoding="utf-8")


def 돌린다(db: Session, 경로: pathlib.Path, 회차id: int | None, 실행: bool, *, 사본: bool = True) -> 계획:
    retreat = 회차머리(db, 회차id)
    판 = 고른다(db, retreat, 경로)
    짝표쓰기(pathlib.Path(config.DATA_DIR) / "재정짝잇기.real.md", 판)
    print("시트 결산 식으로 이을 것(건수만):")
    for k in sorted(판.수):
        print(f"  {k}: {판.수[k]}")
    print(f"  짝 표: data/재정짝잇기.real.md ({len(판.짝)})")
    if not 판.채울:
        print("채울 것이 없습니다.")
        return 판
    if not 실행:
        print("바꾸지 않았습니다. 실제로 채우려면 --실행 을 붙이세요.")
        return 판
    전 = 미지정수(db, retreat)
    if 사본:
        사본을_뜬다()
    try:
        넣는다(db, retreat, 판)
        # 계획에서 되짚지 않고 DB 에서 다시 센다 — 미지정 수 · 채운 행마다 항목
        if 미지정수(db, retreat) != 전 - len(판.채울):
            raise 멈춤("채운 뒤 미지정 수가 계획과 다릅니다 — 되돌렸습니다.")
        for 지출id, 예산id in 판.채울:
            x, c = db.get(ExpenseEntry, 지출id), db.get(BudgetCategory, 예산id)
            if x.budget_category_id != 예산id or (x.level1, x.level2, x.level3a) != (c.level1, c.level2, c.level3):
                raise 멈춤("채운 지출의 예산 항목이나 그 글자가 계획과 다릅니다 — 되돌렸습니다.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    print(f"채웠습니다. 예산 항목 미지정: {전} → {미지정수(db, retreat)}")
    return 판


def main() -> int:
    ap = argparse.ArgumentParser(description="못 이은 지출을 시트 결산 식 연결로 예산 항목에 잇습니다.",
                                 epilog="기본은 미리보기입니다. 실제로 채우려면 --실행 을 붙이세요.")
    ap.add_argument("시트", type=pathlib.Path)
    ap.add_argument("--회차", type=int, default=None)
    ap.add_argument("--실행", action="store_true")
    args = ap.parse_args()
    with SessionLocal() as db:
        try:
            돌린다(db, args.시트, getattr(args, "회차"), getattr(args, "실행"))
            return 0
        except 멈춤 as e:
            print(f"!! {e}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
