# -*- coding: utf-8 -*-
"""이미 갈린 채 선 약 묶음을 **의약품** 하나로 합칩니다 (4-18 · 2026-09-11 도막 5).

## 왜 있나

도막 4 가 `묶음표` 를 고쳐 약 이름 구분들을 전부 `의약품` 으로 보내게 했는데,
그것은 **앞으로 들여올 것**에만 걸립니다. 이미 선 `EquipmentRun.group_name` 은
안 바뀝니다 — 총무 시트가 그전에 들어가 있어서, 화면에 `의약품` 과 `소화제`·
`감기약`·`연고` 가 나란히 서 있습니다. 이 스크립트가 그것을 합칩니다.

## 무엇을 옮기나 — 약 이름 목록을 여기 적지 않는다

이 회차 run 의 `group_name` 을 **`묶음표` 에 물어** `의약품` 이 나오면 옮깁니다.
**묶음표가 정본입니다** — 약 이름을 여기 또 적으면 두 곳이 되고, 표에 약이 하나
늘 때 이 스크립트만 조용히 옛 목록으로 돕니다.

## `통제` 는 이 규칙으로 안 걸립니다

그 run 의 `group_name` 이 **글자 그대로 `통제`** 라서 묶음표를 지나도 `통제`
입니다(들어간 값이 `진통제` 였는데 「통제」 가 그 안에 들어 있어 그리로 갔습니다 —
도막 4 가 표의 순서를 고쳤지만 이미 선 행은 그대로입니다). **약인지는 품목 이름을
봐야 압니다.** 기계가 못 가르는 자리라 `--더 <물품이름>` 으로 사람이 짚습니다 —
여러 번 줄 수 있고, **미리보기가 이름을 보여 준 묶음(`이름을보일묶음`) 안에서만**
찾습니다. 거기 없는 이름이면 멈추고 말합니다 — 보여 준 것과 옮기는 것이 같아야
사람이 짚은 대로 갑니다.

## 겹치면 아무것도 안 합니다

바꾼 뒤 (회차·품목·묶음)이 같아지는 자리가 **하나라도** 있으면 몇 건인지 말하고
멈춥니다. 합치면 한쪽의 수량·체크를 잃는데 **그것은 사람이 정할 일이지 스크립트가
정할 일이 아닙니다**(4-18 의 「한 줄로 합치면 한쪽의 수량·체크를 잃는다」).

## 기본은 미리보기

`--실행` 일 때만 바꿉니다(다른 비품 스크립트들과 같은 꼴). 바꾸기 직전에
`VACUUM INTO` 사본을 뜨고, 세션이 여는 파일과 사본을 뜰 파일이 다르면 아무것도
안 합니다(11-2).

회차는 `--회차 <id>` 로 고릅니다 — 안 주면 열려 있는 회차가 둘 이상일 때 멈추고,
보관된 회차를 대놓고 고르면 경고하고 지나갑니다. **그 판정은 여기 없습니다** —
`비품들여오기.회차머리` 하나를 부릅니다.

두 번째로 돌리면 「합칠 것이 없습니다」 입니다.

## 순서

**사슬은 CLAUDE.md 4-18 에 한 번만 적혀 있습니다** — 여기 옮겨 적으면 한 칸 늘 때
둘 중 하나만 고쳐집니다(검토가 짚었다).

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/비품묶음합치기.py --회차 1
    .venv\\Scripts\\python.exe scripts/비품묶음합치기.py --회차 1 --더 "진통제" --실행
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글·기호가 깨지지 않게 한다 — 안내를 못 찍고
# 죽으면 무엇이 합쳐졌는지 사람이 알 수 없다 (다른 비품 스크립트와 같다)
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import argparse
import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                   # noqa: E402
from sqlalchemy.engine import make_url                          # noqa: E402
from sqlalchemy.exc import OperationalError                     # noqa: E402
from sqlalchemy.orm import Session                              # noqa: E402

from app import config                                          # noqa: E402
from app.db import SessionLocal                                 # noqa: E402
from app.models import EquipmentItem, EquipmentRun, Retreat     # noqa: E402
from scripts import backup                                      # noqa: E402
from scripts.비품들여오기 import 멈춤, 묶음이름쯤, 사람자국, 회차머리  # noqa: E402

# 합쳐 놓을 이름. **묶음표의 쓸 이름과 같은 글자**여야 한다 — 다르면 합친 것이
# 또 다른 묶음으로 서고, 다음에 들여오는 줄이 그 옆에 하나 더 선다
의약품 = "의약품"

# 미리보기에서 **물품 이름까지 보여 줄 묶음.** 여기 든 것은 「묶음 이름만으로는
# 약인지 알 수 없는 자리」 다 — `통제` 가 그렇다(값이 `진통제` 였는데 표의 옛
# 순서 때문에 그리로 갔다). 사람이 그 이름을 보고 `--더` 로 짚는다.
# **자리를 세어 두는 목록이 아니라 이유가 있는 목록이다**(10장) — 늘어나도
# 그때 그 이유를 여기 함께 적는다
이름을보일묶음 = ("통제",)


def 줄들(db: Session, retreat: Retreat) -> list[tuple[EquipmentRun, EquipmentItem]]:
    return list(db.execute(
        select(EquipmentRun, EquipmentItem)
        .join(EquipmentItem, EquipmentItem.id == EquipmentRun.item_id)
        .where(EquipmentRun.retreat_id == retreat.id)
        .order_by(EquipmentRun.group_name, EquipmentRun.sort_order, EquipmentRun.id)
    ).all())


def 고른다(모두: list[tuple[EquipmentRun, EquipmentItem]], 더: list[str]) -> tuple[list, dict]:
    """옮길 run 을 고르고 센다. **아무것도 안 바꾼다** — 미리보기와 실행이 같은 함수를 쓴다.

    고르는 길이 둘이다 — ① 묶음 이름을 `묶음표` 에 물어 `의약품` 이 나오는 것
    ② 사람이 `--더` 로 짚은 물품의 run. 둘 다 **이미 의약품인 run 은 뺀다**
    (그러지 않으면 두 번째 판이 「합칠 것이 없습니다」 를 못 낸다).
    """
    짚은이름 = set(더)
    묶음별 = Counter()
    갈묶음 = Counter()          # 의약품으로 갈 묶음마다 몇 줄인가
    옮길 = []
    for run, item in 모두:
        묶음별[run.group_name or "묶음 없음"] += 1
        if run.group_name == 의약품:
            continue
        표가말하는것 = 묶음이름쯤(run.group_name)
        # **짚음은 보여 준 묶음 안에서만 센다.** 이름만 보면 같은 이름의 run 이
        # 다른 묶음에 있을 때 그것까지 딸려 가는데(품목 유니크가 (팀, 이름)이라
        # 팀이 다른 같은 이름도 따로 선다), **미리보기가 이름을 보여 준 곳은
        # `이름을보일묶음` 뿐**이라 사람은 「거기 그것」 을 짚었다고 믿는다.
        # 보여 준 것과 옮기는 것이 같아야 한다 (검토 5)
        짚음 = item.name in 짚은이름 and run.group_name in 이름을보일묶음
        if 표가말하는것 == 의약품 or 짚음:
            옮길.append((run, item))
            갈묶음[run.group_name or "묶음 없음"] += 1
    return 옮길, {"묶음별": 묶음별, "갈묶음": 갈묶음}


def 겹침수(모두: list[tuple[EquipmentRun, EquipmentItem]], 옮길: list) -> int:
    """바꾸고 나면 (회차·품목·묶음)이 같아지는 run 이 몇 개인가.

    **유니크가 셋이라 그대로 넣으면 IntegrityError 다.** 그런데 그것보다 앞서,
    합치는 순간 한쪽의 수량·체크를 잃는다 — 그래서 터지기 전에 세어 말하고 멈춘다.
    """
    옮길id = {run.id for run, _ in 옮길}
    뒤 = Counter()
    for run, item in 모두:
        묶음 = 의약품 if run.id in 옮길id else run.group_name
        뒤[(item.id, 묶음)] += 1
    return sum(n - 1 for n in 뒤.values() if n > 1)


def 없는이름(모두: list[tuple[EquipmentRun, EquipmentItem]], 더: list[str]) -> list[str]:
    """짚을 수 있는 이름인가 — **옮기는 범위와 같은 것을 묻는다.**

    「이 회차에 있는가」 로 물으면 `이름을보일묶음` 밖의 이름을 「있다」 고 하고는
    한 줄도 안 옮긴다 — 사람은 짚었다고 믿는다. 두 자리가 같은 것을 봐야 한다.
    """
    # **이미 옮겨진 이름도 「있는 이름」 이다.** 그러지 않으면 사람이 같은 명령을
    # 한 번 더 쳤을 때 — 보고가 적어 둔 순서가 바로 그것이다 — 「없는 물품」 으로
    # 멈춘다. 둘째 판은 「합칠 것이 없습니다」 여야 한다 (시험 b03 이 잡았다)
    있는 = {item.name for run, item in 모두
           if run.group_name in 이름을보일묶음 or run.group_name == 의약품}
    return [이름 for 이름 in 더 if 이름 not in 있는]


def 보일이름(name: str) -> str:
    """미리보기에 낼 물품 이름 — **사람 자국이 있으면 이름 대신 말한다.**

    이 출력은 사람이 보고 `--더` 에 옮겨 적는 자리라 이름이 필요하다. 그런데
    시트에서 온 이름에 성함이 붙은 것이 있어서(4-18) 그대로 찍으면 그 출력이
    새는 자리가 된다 — 자국이 보이면 이름을 안 내고 몇 개인지만 센다.
    """
    return "(자국 있음)" if 사람자국(name) else name


def 미리보기(모두, 옮길, 수: dict) -> None:
    print("지금 이 회차의 묶음 — " + " · ".join(
        f"{k} {v}" for k, v in 수["묶음별"].most_common()))
    if 수["갈묶음"]:
        print(f"{의약품} 으로 갈 묶음 — " + " · ".join(
            f"{k} {v}" for k, v in 수["갈묶음"].most_common()))
    else:
        print(f"{의약품} 으로 갈 묶음이 없습니다.")

    for 묶음 in 이름을보일묶음:
        이름들 = [item.name for run, item in 모두 if run.group_name == 묶음]
        if not 이름들:
            continue
        가린수 = sum(1 for n in 이름들 if 사람자국(n))
        print(f"「{묶음}」 묶음에 선 물품 {len(이름들)}개 — "
              + " · ".join(보일이름(n) for n in 이름들))
        if 가린수:
            print(f"   그중 {가린수}개는 이름에 사람 자국이 있어 안 찍었습니다.")
        print(f"   약이면 --더 \"<물품이름>\" 으로 짚어 주세요 (여러 번 줄 수 있습니다).")

    print(f"옮길 run {len(옮길)}개.")
    print("바꾸지 않았습니다. 실제로 합치려면 --실행 을 붙이세요.")


def 사본을_뜬다() -> pathlib.Path:
    원본 = pathlib.Path(config.DATA_DIR) / "app.db"
    여는것 = make_url(config.DATABASE_URL).database
    if not 여는것 or pathlib.Path(여는것).resolve() != 원본.resolve():
        raise 멈춤(f"세션이 여는 DB({여는것})와 사본을 뜰 파일({원본})이 다릅니다 — 합치지 않았습니다.")
    사본 = backup.snapshot(원본, pathlib.Path(config.DATA_DIR) / "backups")
    print(f"  사본을 떴습니다: {사본.name}  ({사본.stat().st_size:,} 바이트)")
    return 사본


def 합치기(db: Session, 회차id: int | None, 더: list[str], 실행: bool) -> int:
    retreat = 회차머리(db, 회차id)
    모두 = 줄들(db, retreat)

    빠진 = 없는이름(모두, 더)
    if 빠진:
        # **먼저 멈춘다.** 오타 하나를 조용히 흘리면 사람은 짚었다고 믿고
        # 그 run 은 갈린 채 남는다 — 화면에서야 알아차린다
        raise 멈춤(f"--더 로 짚은 물품이 이 회차에 없습니다: {', '.join(빠진)}\n"
                  "  미리보기에 찍히는 이름을 그대로 적어 주세요.")

    옮길, 수 = 고른다(모두, 더)
    if not 옮길:
        print("합칠 것이 없습니다 — 이 회차에 의약품으로 옮길 묶음이 없습니다.")
        return 0

    겹침 = 겹침수(모두, 옮길)
    if 겹침:
        # 세어 말하고 멈춘다 — 무엇을 잃을지 아는 것은 사람이다 (4-18)
        raise 멈춤(f"합치면 (회차·품목·묶음)이 같아지는 run 이 {겹침}건 생깁니다 — "
                  "아무것도 바꾸지 않았습니다.\n"
                  "  합치면 한쪽의 수량·체크를 잃습니다. 화면에서 한쪽을 먼저 정리하고 다시 돌리세요.")

    if not 실행:
        미리보기(모두, 옮길, 수)
        return 0

    사본을_뜬다()
    for run, _ in 옮길:
        run.group_name = 의약품
    db.commit()
    print(f"합쳤습니다: run {len(옮길)}개를 「{의약품}」 으로 옮겼습니다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="이미 갈린 약 묶음을 의약품 하나로 합칩니다 (4-18).",
        epilog="기본은 미리보기입니다. 실제로 합치려면 --실행 을 붙이세요.",
    )
    ap.add_argument("--회차", type=int, default=None,
                    help="회차 id (안 주면 열린 회차가 둘 이상일 때 멈춥니다)")
    ap.add_argument("--더", action="append", default=[], metavar="물품이름",
                    help="묶음 이름으로는 약인 줄 모르는 물품 (여러 번 줄 수 있습니다)")
    ap.add_argument("--실행", action="store_true", help="실제로 합칩니다")
    args = ap.parse_args()

    with SessionLocal() as db:
        try:
            return 합치기(db, getattr(args, "회차"), list(getattr(args, "더")),
                        getattr(args, "실행"))
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
