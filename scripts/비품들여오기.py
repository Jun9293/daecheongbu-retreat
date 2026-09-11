# -*- coding: utf-8 -*-
"""비품 시트(TSV)를 앱의 비품 표로 들여옵니다 (4-18 · 2026-09-11).

## 무엇을 들여오나

이번에는 **총무 시트의 이번 회차 탭**과 **코람데오 장비목록** 둘입니다. 옛 회차
탭과 구매 탭은 담을 자리가 아직 없어 안 들여옵니다(`docs/인계.md`).

| 시트 | 칸 | 어디로 |
|---|---|---|
| 총무 | 구분(맨 왼쪽) | `EquipmentRun.group_name` — **표를 거쳐** 쓸 이름으로 |
| | 챙길 물품 | `EquipmentItem.name` |
| | 필요한 수량 | `EquipmentRun.quantity` (글자다 — 「A3 :11, A4 : 11」 이 그대로 온다) |
| | 위치 | `EquipmentRun.location` — **허용 목록에 있는 값만** |
| | 비고 | `EquipmentItem.note` — 사람 자국이 보이면 통째로 버린다. **비어 있을 때만** 적는다(품목을 새로 만들 때, 그리고 이미 있는 품목의 메모가 비었을 때) — 적혀 있는 메모를 시트가 밀어내지 않는다 |
| | 최종 | `x`·`X` 한 글자면 `included` 를 끈다. 그 밖의 값은 안 들여온다 |
| 코람데오 | 구역 | `group_name` (표를 거쳐) |
| | 물품 · 필요 수량 · 비고 | 위와 같다 |
| | 담당자 | **헤브론이면 헤브론 팀**, 아니면 코람데오. 개인 이름은 아무 데도 안 넣는다 |

`team_key` 는 총무 시트가 `chongmu`, 코람데오가 `koram`(담당자가 헤브론인 줄은
`hebron`)입니다. **현재 수량은 안 들여옵니다** — 회차별 칸이 `quantity` 하나뿐이고
재고는 회차를 넘어 변해서 앉힐 자리가 없습니다(봐둘것 AP-a).

## 사람 이름과 전화는 기본이 거부입니다 (11-2 의 그 자리)

시트에는 **빌려주신 분의 성함과 전화번호**가 제목·위치·비고에 섞여 있습니다.
거르는 것이 아니라 **허락한 것만 넣습니다** — 아래가 그 자리들입니다(10장 「자리를 세어 두지 않습니다」).

- **묶음 이름** — 시트 값을 그대로 쓰지 않고 `묶음표` 를 거칩니다. 표는 「이 말이
  구분 값에 들어 있으면 이 묶음」 이고, **찾는 말은 깨끗한 낱말뿐**입니다.
  표에 없는 값이 나오면 멈추고 그 값을 말합니다 — 사람이 표에 한 줄 더하고 다시
  돌립니다. *값 전체를 열쇠로 두지 않는 이유*: 그러면 성함이 이 저장소에 들어옵니다
- **위치** — `쓸위치` 목록에 있는 값만 넣습니다. 목록 밖은 안 넣고 몇 건인지 셉니다
- **비고** — 전화꼴이나 이름 자국(`M`·`썬`·`언니`·`님`·`집사님`)이 보이면 **그 줄의
  비고를 통째로** 버리고 셉니다. 조각만 지우면 남은 문장이 무슨 말인지 알 수 없고
  지웠다는 것도 안 보입니다
- **품목 이름**에 그 자국이 있으면 **멈춥니다** — 버릴 수 없는 칸이라 사람이 봐야 합니다
- **수량에는 그물이 없습니다** — 「A3 :11, A4 : 11」 같은 값이 그대로 와야 해서입니다.
  사람이 거기에 「◯◯님이 가져옴」 을 적으면 그대로 들어옵니다(검토가 짚음)
- 넓게 잡는 쪽이 있습니다 — 「하나님」·「목사님」 처럼 `님` 으로 끝나는 멀쩡한 말도
  걸려 **그 줄의 비고가 버려집니다.** 버리는 것은 안전한 방향이라 그대로 둡니다

## 잘렸는지 사람이 잽니다

총무 시트 첫 탭에는 자체 합계가 없어 연결기나 내려받기가 중간을 잘라도 알 길이
없습니다. 그래서 **읽은 줄 수 · 건너뛴 빈 줄 수 · 묶음마다의 줄 수**를 찍습니다 —
사람이 시트에서 세어 맞춥니다. 그 수는 코드 어디에도 박지 않습니다.

## 기본은 미리보기

`--실행` 일 때만 바꿉니다(계정정리.py · 비품옮기기.py 와 같은 꼴). 바꾸기 직전에
`VACUUM INTO` 사본을 뜨고, 세션이 여는 파일과 사본을 뜰 파일이 다르면 아무것도 안
합니다(11-2). 미리보기는 **수만** 찍습니다 — 품목 이름도 사람 이름도 안 찍습니다.

이미 있는 것은 건드리지 않습니다 — 같은 (팀, 이름)의 품목은 다시 쓰고, 같은
(회차, 품목, 묶음)의 run 은 **덮어쓰지 않고 건너뜁니다**(사람이 앱에서 체크한 자국이
거기 있습니다). 두 번째로 돌리면 「들여올 것이 없습니다」 입니다.

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/비품들여오기.py 총무 data/비품-총무.real.tsv
    .venv\\Scripts\\python.exe scripts/비품들여오기.py 총무 data/비품-총무.real.tsv --실행
    .venv\\Scripts\\python.exe scripts/비품들여오기.py 코람데오 data/비품-코람데오.real.tsv

`--회차 <id>` 로 회차를 고릅니다. **열려 있는 회차가 둘 이상이면 안 주면 멈춥니다** —
id 와 이름을 늘어놓고 고르라고 합니다. 하나뿐일 때만 그것을 쓰고 이름을 먼저 찍습니다.
"""

from __future__ import annotations

import sys as _sys

for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import argparse
import csv
import io
import pathlib
import re
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                 # noqa: E402
from sqlalchemy.engine import make_url                        # noqa: E402
from sqlalchemy.exc import OperationalError                   # noqa: E402
from sqlalchemy.orm import Session                            # noqa: E402

from app import config                                        # noqa: E402
from app.db import SessionLocal                               # noqa: E402
from app.models import Department, EquipmentItem, EquipmentRun, Retreat  # noqa: E402
from scripts import backup                                    # noqa: E402


class 멈춤(Exception):
    """사람이 봐야 하는 자리 — 아무것도 바꾸지 않고 멈춘다."""


# ── 사람 자국 ─────────────────────────────────────────────────────────
# 전화는 **숫자 셋 묶음**이면 잡는다(010-1234-5678 · 02.123.4567 · 032 123 4567).
# 이름 자국은 이름 뒤에 붙는 말들이다 — 이 저장소의 실명 대응표에 기대지 않는다
# (대응표는 저장소 밖이고, 시트의 외부인은 애초에 거기 없다)
# 구분자 없이 붙여 쓴 번호도 잡는다 — 4-12 가 예로 드는 표기가 그 꼴이다
전화꼴 = re.compile(r"\d{2,4}\s*[-.\s]\s*\d{3,4}\s*[-.\s]\s*\d{4}|01[016-9]\d{7,8}")
# 이름 뒤에 붙는 말. **넓게 잡는다** — 「하나님」·「목사님」·「사이즈M」 처럼 이름과
# 모양이 같은 말도 걸려 그 비고가 버려진다(검토가 짚음). 기계가 못 가리는 자리라
# 버리는 쪽에 둔다 — 버린 수를 찍으므로 사람이 시트에서 다시 읽을 수 있다.
# 「◯◯ 님」 처럼 사이에 빈칸이 있으면 반대로 안 걸린다
이름꼴 = re.compile(r"(?<![가-힣])[가-힣]{2,3}M(?![가-힣])|[가-힣]{1,3}(?:썬|언니|님)(?![가-힣])")


def 사람자국(값: str) -> bool:
    return bool(전화꼴.search(값) or 이름꼴.search(값))


# ── 허락한 것만 ───────────────────────────────────────────────────────
# 시트에 실제로 있는 장소만. 목록 밖의 위치 값에는 사람 이름이 섞여 있다
쓸위치 = {
    "모빌랙", "통합사무실", "통사", "통합 사무실", "본당4층", "자료실", "워십룸",
    "만나식당", "선교사실", "바깥쪽 창고", "선교사실 안쪽 창고", "시설", "대여",
    "시설에서 대여",
}

# 「이 말이 구분 값에 들어 있으면 이 묶음」 — 찾는 말은 **깨끗한 낱말뿐**이다.
# 값 전체를 열쇠로 두면 빌려주신 분의 성함이 이 파일에 들어온다.
# 위에서부터 먼저 맞는 것을 쓴다.
묶음표: list[tuple[str, str]] = [
    # 총무 시트
    ("최대한 어플 확인", "출력물"),          # 그 구역의 첫 칸이 메모로 채워져 있다
    ("사무용품", "사무용품"),
    ("야식 및 간식", "야식·간식"),
    ("테이프", "테이프"),
    ("의약품상자", "의약품"),
    ("소화제", "소화제"),
    ("소염제", "소염제"),
    ("감기약", "감기약"),
    ("설사약", "설사약"),
    ("변비약", "변비약"),
    ("소독약", "소독약"),
    ("알레르기약", "알레르기약"),
    ("버물리", "버물리"),
    ("연고", "연고"),
    ("위생", "위생·방역"),
    ("침례", "침례"),
    ("성찬", "성찬"),
    ("기본 물품", "기본 물품"),
    ("객실", "객실 비품"),
    ("상시기도실", "상시기도실"),
    ("포토존", "포토존"),
    ("골든벨", "골든벨"),
    ("유아실", "유아실"),
    ("통제", "통제"),
    # 코람데오 장비목록
    ("4층 창고", "4층 창고"),
    ("4층 연습실", "4층 연습실"),
    ("통합사무실", "통합사무실"),
    ("자료실", "자료실"),
    ("워십룸", "워십룸"),
    ("다이소", "다이소"),
]

시트들 = {
    "총무": {"팀": "chongmu", "칸": {"물품": "챙길 물품", "수량": "필요한 수량",
                                  "위치": "위치", "비고": "비고", "최종": "최종"},
            "구분칸": "구분"},
    "코람데오": {"팀": "koram", "칸": {"물품": "물품", "수량": "필요 수량",
                                    "담당자": "담당자", "비고": "비고"},
               "구분칸": "구역"},
}


def 묶음이름(값: str) -> str:
    for 찾을말, 쓸이름 in 묶음표:
        if 찾을말 in 값:
            return 쓸이름
    raise 멈춤(f"묶음표에 없는 구분 값입니다: {값!r}\n"
              "  scripts/비품들여오기.py 의 `묶음표` 에 「찾을 말, 쓸 이름」 한 줄을 더하고 다시 돌리세요.\n"
              "  찾을 말은 **사람 이름이 없는 낱말**이어야 합니다 — 이 저장소는 공개입니다 (11-2).\n"
              "  위의 값에 성함이 섞여 있을 수 있습니다 — 보고나 커밋 메시지에 옮겨 적지 마세요.")


# ── TSV 읽기 ──────────────────────────────────────────────────────────

def 읽는다(경로: pathlib.Path) -> list[list[str]]:
    """한 **레코드**가 시트의 한 행이다 — 줄로 자르지 않고 `csv` 에 맡긴다.

    전에는 `splitlines()` 로만 잘랐는데, 그러면 **칸 안에 줄을 바꾼 값**(비고에
    흔하다)이 두 줄로 쪼개져 그 아래 모든 줄의 번호가 하나씩 밀린다 — 오늘 고친
    것과 **같은 종류의 고장**이고, 「찍는 번호는 시트에서 사람이 보는 행 번호」 라는
    보증이 거기서 깨진다(검토가 짚었다). 시트에서 내려받은 TSV 는 그런 칸을
    따옴표로 감싸므로 csv 가 한 레코드로 읽는다.

    지금 재료 둘에는 그런 칸이 없어 **바꿔도 값이 달라지지 않는다** — 두 판독기를
    칸까지 견주어 같은 것을 확인하고 바꿨다(보고 3장).
    """
    raw = 경로.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            글 = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise 멈춤(f"{경로} 를 읽지 못했습니다 (utf-8 도 cp949 도 아닙니다).")
    # newline="" 이어야 csv 가 줄바꿈을 직접 다룬다 — 안 주면 감싼 칸에서 터진다
    return list(csv.reader(io.StringIO(글, newline=""), delimiter="\t"))


def 칸자리(줄들: list[list[str]], 이름들: dict[str, str]) -> tuple[int, dict[str, int]]:
    """머리글 **이름**으로 칸을 찾는다 — 자리(몇 번째)로 찾지 않는다.

    시트에 칸이 하나 끼면 자리로 찾은 것은 조용히 어긋난다. 이름이 하나라도 없으면
    무엇이 없는지 말하고 멈춘다.
    """
    for i, 줄 in enumerate(줄들[:40]):
        칸 = [c.strip() for c in 줄]
        찾음, 빠짐 = {}, []
        for 키, 이름 in 이름들.items():
            자리 = [j for j, c in enumerate(칸) if c == 이름] or \
                   [j for j, c in enumerate(칸) if 이름 in c]
            if not 자리:
                빠짐.append(이름)
            elif len(자리) > 1 and 칸.count(이름) != 1:
                raise 멈춤(f"머리글 {이름!r} 이 {len(자리)}칸에 있습니다 — 어느 칸인지 알 수 없어 멈춥니다.")
            else:
                찾음[키] = 자리[0]
        if not 빠짐:
            return i, 찾음
        if len(찾음) >= 2:       # 머리글 줄은 맞는데 몇 개가 없다 — 여기서 말하고 멈춘다
            raise 멈춤(f"{i + 1}번째 줄이 머리글로 보이는데 찾는 이름이 없습니다: {', '.join(빠짐)}")
    raise 멈춤(f"머리글 줄을 못 찾았습니다 — 찾는 이름: {', '.join(이름들.values())}")


def 줄뽑기(종류: str, 경로: pathlib.Path) -> tuple[list[dict], dict[str, int]]:
    """시트에서 넣을 줄만 뽑는다. 수는 사람이 세어 맞출 수 있게 함께 돌려준다."""
    꼴 = 시트들[종류]
    줄들 = 읽는다(경로)
    머리, 자리 = 칸자리(줄들, 꼴["칸"])
    # 구분 칸 — 이름이 있으면 그 자리, 없으면 맨 왼쪽 (시트가 제목을 거기 둔다)
    구분자리 = next((j for j, c in enumerate(줄들[머리]) if c.strip() == 꼴["구분칸"]), 0)

    칸 = lambda 줄, j: (줄[j] if len(줄) > j else "").strip()   # noqa: E731
    뽑은, 이어받은, 빈줄 = [], "", 0
    # **읽으면서 센다.** 전에는 멈출 때 `줄들.index(줄)` 로 자리를 물었는데,
    # 그것은 **같은 내용의 줄 중 맨 앞엣것**을 돌려준다 — 시트에는 같은 물품이
    # 같은 수량으로 두 번 적힌 줄이 흔하고, 그러면 사람이 찍힌 번호를 열어 보고
    # **아무것도 없는 줄**을 본다(2026-09-11 에 실제로 그랬다).
    # 세는 시작은 `머리 + 2` 다 — 줄들[i] 가 시트의 i+1 행이고 머리글 다음
    # 줄부터 도니까, 찍히는 수가 **사람이 시트에서 보는 행 번호**와 같다.
    for 시트행, 줄 in enumerate(줄들[머리 + 1:], start=머리 + 2):
        앞 = 칸(줄, 구분자리)
        if 앞:
            이어받은 = 앞          # 합친 칸 — 비어 있으면 바로 위의 값을 물려받는다
        이름 = 칸(줄, 자리["물품"])
        if not 이름:
            빈줄 += 1
            continue
        if 사람자국(이름):
            raise 멈춤(f"품목 이름에 사람 자국이 있습니다 (시트의 {시트행}행) — "
                      "이름은 버릴 수 없는 칸이라 멈춥니다. 시트를 고치고 다시 돌리세요.")
        뽑은.append({
            "구분": 이어받은, "이름": 이름,
            "수량": 칸(줄, 자리["수량"]) or None,
            "위치": 칸(줄, 자리["위치"]) if "위치" in 자리 else "",
            "비고": 칸(줄, 자리["비고"]),
            "최종": 칸(줄, 자리["최종"]) if "최종" in 자리 else "",
            "담당자": 칸(줄, 자리["담당자"]) if "담당자" in 자리 else "",
        })
    return 뽑은, {"읽은줄": len(줄들) - 머리 - 1, "넣을줄": len(뽑은), "빈줄": 빈줄}


# ── DB ────────────────────────────────────────────────────────────────

def 회차고르기(db: Session, 회차id: int | None) -> Retreat:
    if 회차id is not None:
        r = db.get(Retreat, 회차id)
        if r is None:
            raise 멈춤(f"id {회차id} 인 회차가 없습니다.")
        return r
    열린 = list(db.scalars(select(Retreat).where(Retreat.is_archived.is_(False))
                          .order_by(Retreat.start_date.desc(), Retreat.id.desc())))
    if not 열린:
        raise 멈춤("열려 있는 회차가 없습니다 — --회차 <id> 로 골라 주세요.")
    if len(열린) > 1:
        # **고르지 않고 멈춘다.** 전에는 「시작일이 늦은 것」 을 말없이 골랐는데,
        # 그 규칙은 **열린 회차가 하나일 때만** 맞았다 — 다음 회차를 미리 열어 두면
        # 가장 늦은 것이 곧 **아직 아무것도 없는 회차**라, 2026-09-11 에 코람데오
        # 28줄이 그리로 들어갔다. 넣고 나서야 알았고 사람이 되돌렸다.
        고를것 = "\n".join(f"    --회차 {r.id}   {r.name}" for r in 열린)
        raise 멈춤(f"열려 있는 회차가 {len(열린)}개라 어디에 넣을지 알 수 없습니다 — "
                  f"--회차 <id> 로 골라 주세요.\n{고를것}")
    print(f"열려 있는 회차가 하나뿐이라 그것을 씁니다: {열린[0].name} (id {열린[0].id})")
    return 열린[0]


def 팀키확인(db: Session, retreat: Retreat, 키들: set[str]) -> None:
    있는 = {d.key for d in db.scalars(
        select(Department).where(Department.retreat_id == retreat.id)) if d.key}
    없는 = sorted(키들 - 있는)
    if 없는:
        raise 멈춤(f"이 회차에 없는 부서 키입니다: {', '.join(없는)} — "
                  "설정 › 부서에서 만들고 다시 돌리세요.")


def 고른다(db: Session, retreat: Retreat, 종류: str, 뽑은: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """넣을 것을 정하고 센다. **아무것도 안 바꾼다** — 미리보기와 실행이 같은 함수를 쓴다."""
    꼴 = 시트들[종류]
    팀키 = {꼴["팀"]}
    for 줄 in 뽑은:
        줄["팀"] = "hebron" if "헤브론" in 줄.get("담당자", "") else 꼴["팀"]
        팀키.add(줄["팀"])
    팀키확인(db, retreat, 팀키)

    있는품목 = {(i.team_key, i.name): i.id for i in db.scalars(select(EquipmentItem))}
    있는run = {(r.item_id, r.group_name) for r in db.scalars(
        select(EquipmentRun).where(EquipmentRun.retreat_id == retreat.id))}
    끝자리: dict[str, int] = {}
    for r in db.scalars(select(EquipmentRun).where(EquipmentRun.retreat_id == retreat.id)):
        끝자리[r.group_name] = max(끝자리.get(r.group_name, -1), r.sort_order)

    수 = Counter()
    묶음별 = Counter()
    새품목: dict[tuple[str, str], None] = {}
    만들것, 만든열쇠 = [], set()
    for 줄 in 뽑은:
        묶음 = 묶음이름(줄["구분"])
        묶음별[묶음] += 1
        열쇠 = (줄["팀"], 줄["이름"])
        있음 = 열쇠 in 있는품목
        if 있음:
            수["다시쓸품목"] += 1
        elif 열쇠 not in 새품목:
            새품목[열쇠] = None
            수["새품목"] += 1

        위치 = 줄["위치"]
        if 위치 and 위치 not in 쓸위치:
            위치, _ = "", 수.update(["위치버림"])
        비고 = 줄["비고"]
        if 비고 and 사람자국(비고):
            비고, _ = "", 수.update(["비고버림"])
        included = not (줄["최종"].strip().lower() == "x")
        if not included:
            수["불필요"] += 1

        run열쇠 = (열쇠, 묶음)
        if (있음 and (있는품목[열쇠], 묶음) in 있는run) or run열쇠 in 만든열쇠:
            수["건너뛸run"] += 1
            continue
        만든열쇠.add(run열쇠)
        수["새run"] += 1
        끝자리[묶음] = 끝자리.get(묶음, -1) + 1
        만들것.append({"팀": 줄["팀"], "이름": 줄["이름"], "묶음": 묶음, "수량": 줄["수량"],
                       "위치": 위치 or None, "비고": 비고 or None, "included": included,
                       "차례": 끝자리[묶음]})
    return 만들것, {**수, "묶음별": 묶음별}


def 미리보기(수: dict, 셈: dict[str, int], retreat: Retreat) -> None:
    묶음별 = 수["묶음별"]
    print(f"읽은 줄 {셈['읽은줄']}개 · 물품 이름이 있는 줄 {셈['넣을줄']}개 · 건너뛴 빈 줄 {셈['빈줄']}개")
    print("  묶음마다의 줄 수 — " + " · ".join(f"{k} {v}" for k, v in 묶음별.most_common()))
    print(f"새로 설 품목 {수.get('새품목', 0)}개 · 이미 있는 품목을 쓰는 줄 {수.get('다시쓸품목', 0)}개 · "
          f"새로 설 run {수.get('새run', 0)}개 · 건너뛸 run {수.get('건너뛸run', 0)}개")
    print(f"위치를 못 넣은 줄 {수.get('위치버림', 0)}개 · 비고를 버린 줄 {수.get('비고버림', 0)}개 · "
          f"이번 회차 불필요로 둘 줄 {수.get('불필요', 0)}개")
    print("시트에서 세어 맞춰 보세요 — 잘렸으면 줄 수가 다릅니다.")
    print("바꾸지 않았습니다. 실제로 넣으려면 --실행 을 붙이세요.")


def 사본을_뜬다() -> pathlib.Path:
    원본 = pathlib.Path(config.DATA_DIR) / "app.db"
    여는것 = make_url(config.DATABASE_URL).database
    if not 여는것 or pathlib.Path(여는것).resolve() != 원본.resolve():
        raise 멈춤(f"세션이 여는 DB({여는것})와 사본을 뜰 파일({원본})이 다릅니다 — 넣지 않았습니다.")
    사본 = backup.snapshot(원본, pathlib.Path(config.DATA_DIR) / "backups")
    print(f"  사본을 떴습니다: {사본.name}  ({사본.stat().st_size:,} 바이트)")
    return 사본


def 넣는다(db: Session, retreat: Retreat, 만들것: list[dict]) -> None:
    사본을_뜬다()
    품목 = {(i.team_key, i.name): i for i in db.scalars(select(EquipmentItem))}
    for 줄 in 만들것:
        열쇠 = (줄["팀"], 줄["이름"])
        item = 품목.get(열쇠)
        if item is None:
            item = EquipmentItem(team_key=줄["팀"], name=줄["이름"], note=줄["비고"])
            db.add(item)
            db.flush()
            품목[열쇠] = item
        elif 줄["비고"] and not item.note:
            # 이미 있는 품목의 메모는 시트가 밀어내지 않는다 — 비어 있을 때만 채운다
            item.note = 줄["비고"]
        db.add(EquipmentRun(retreat_id=retreat.id, item_id=item.id, group_name=줄["묶음"],
                            included=줄["included"], quantity=줄["수량"], location=줄["위치"],
                            checked=False, sort_order=줄["차례"]))
    db.commit()


def 들여오기(db: Session, 종류: str, 경로: pathlib.Path, 회차id: int | None, 실행: bool) -> int:
    retreat = 회차고르기(db, 회차id)
    print(f"회차: {retreat.name} (id {retreat.id}) · 시트: {종류}")
    뽑은, 셈 = 줄뽑기(종류, 경로)
    만들것, 수 = 고른다(db, retreat, 종류, 뽑은)
    if not 만들것:
        # 「잘렸는지」 를 보려고 다시 돌리는 때가 바로 여기다 — 그 수는 늘 찍는다
        print(f"읽은 줄 {셈['읽은줄']}개 · 물품 이름이 있는 줄 {셈['넣을줄']}개 · "
              f"건너뛴 빈 줄 {셈['빈줄']}개")
        print("  묶음마다의 줄 수 — " + " · ".join(f"{k} {v}" for k, v in 수["묶음별"].most_common()))
        print(f"들여올 것이 없습니다 — 새로 설 run 이 0 입니다 "
              f"(이미 있어 건너뛸 run {수.get('건너뛸run', 0)}개).")
        return 0
    if not 실행:
        미리보기(수, 셈, retreat)
        return 0
    넣는다(db, retreat, 만들것)
    print(f"넣었습니다: 새 품목 {수.get('새품목', 0)}개 · 새 run {수.get('새run', 0)}개 · "
          f"건너뛴 run {수.get('건너뛸run', 0)}개 · 위치를 못 넣은 줄 {수.get('위치버림', 0)}개 · "
          f"비고를 버린 줄 {수.get('비고버림', 0)}개 · 이번 회차 불필요 {수.get('불필요', 0)}개")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="비품 시트(TSV)를 앱의 비품 표로 들여옵니다 (4-18).",
        epilog="기본은 미리보기입니다. 실제로 넣으려면 --실행 을 붙이세요.",
    )
    ap.add_argument("종류", choices=sorted(시트들), help="시트 종류")
    ap.add_argument("파일", help="TSV 경로 (data/*.real.tsv — 저장소에 안 들어갑니다)")
    ap.add_argument("--회차", type=int, default=None,
                help="회차 id (열려 있는 회차가 둘 이상이면 반드시 줍니다)")
    ap.add_argument("--실행", action="store_true", help="실제로 넣습니다")
    args = ap.parse_args()

    경로 = pathlib.Path(args.파일)
    if not 경로.exists():
        print(f"파일이 없습니다: {경로}")
        return 1
    with SessionLocal() as db:
        try:
            return 들여오기(db, args.종류, 경로, getattr(args, "회차"), getattr(args, "실행"))
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
