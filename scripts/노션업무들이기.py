# -*- coding: utf-8 -*-
"""노션 업무 DB 를 **그대로** 한 회차의 업무로 들입니다 (2026-09-16 · 사람이 정함).

짝짓기를 걷은 자리입니다 — 앞선 판들은 노션 줄과 앱 run 을 점수로 짝지어 사람에게
확인을 받는 길이었고(`scripts/노션업무짝짓기.py` · `scripts/업무대조확인표.py`), 사람이
**그 길 대신 노션을 그대로 옮겨 놓는 쪽**으로 정했습니다. 그래서 이 스크립트는 아무것도
견주지 않습니다 — 노션 줄을 읽어 그대로 새로 세웁니다.

- 읽는 곳은 `data/노션업무전체.real.tsv`(저장소 밖 · 노션에서 조회해 옮겨 적은 것)
  뿐입니다. 칸은 `id · 할 일 · 업무속성 · 담당팀 · 관련 팀 · 시작 · 마감 · 관련업무 · 설명`
- **D-주차 표지는 뺍니다** — 판정은 `노션업무짝짓기.표지인가` 하나입니다(두 벌이 되면 갈립니다)
- 노션 페이지 id 는 `TaskLibrary.notion_page_id` 에 남습니다. **제목은 열쇠가 못 됩니다** —
  회의록에서 파일 이름을 열쇠로 쓰다 같은 자리를 한 번 겪었습니다
- 관련업무는 **노션 id → 이번에 선 라이브러리 id** 로 옮깁니다. 표지를 가리키거나 이 표에 없는
  대상은 못 옮기고 몇 건인지 셉니다. 노션 쪽이 한쪽에만 적혀 있어도 앱은 양쪽에 적습니다(2장)
- 설명은 **업무 규칙**(`TaskLibrary.rules`)으로 갑니다 — 회차를 넘어가는 진행 방식 자리입니다(4-9).
  **노션 페이지 본문은 안 들입니다** — 속성이 아니라 페이지마다 따로 읽어야 하는 글입니다
- **진행 상황·행사 전후·참여자 칸은 안 들입니다.** 상태는 전부 「대기」 로 섭니다
- **읽은 줄 · 표지 · 남은 줄을 셋 다 찍습니다** — 그 셋이 맞아야 노션이 스스로 센 수와 대조가 됩니다.
  칸이 정해진 수보다 많거나, 날짜 꼴이 아니거나, 마감이 시작보다 빠르면 **줄 번호를 말하고 멈춥니다**
- **두 번 들이지 않습니다** — 같은 노션 페이지 id 를 가진 라이브러리가 이미 있으면 미리보기부터 멈춥니다.
  **범위는 저장소 전체이지 한 회차가 아닙니다**(라이브러리가 회차를 넘기 때문입니다) — 그래서 **다음 회차에
  이 스크립트를 그대로 쓸 수는 없습니다.** 그때는 「같은 노션 줄을 다음 회차에 어떻게 세울지」 를 먼저 정합니다
- 새 run 의 번호는 **어느 갈래든 남은 번호 다음부터** 잇습니다(4-14). 「삭제」 라고 1부터 주면 1..102 가
  살아 있는 **다른** 업무를 가리키게 되는데, 그것이 4-14 가 막으려던 바로 그 상태입니다. 빈 번호는 안 메웁니다

## 지금 있는 102 건을 어떻게 하나 — 갈래가 둘이고 기본은 안 지우는 쪽입니다

0장이 「아무것도 삭제하지 않는다」 이므로 **기본은 `--지움방식 뺌`** 입니다 — run 을 지우지 않고
`included` 를 끄는 것이고, 논의 · 첨부 · 확인 요청이 그대로 남습니다. `--지움방식 삭제` 는 행을
지웁니다 — 그때 논의 · 논의 잇기 · 첨부가 **함께 사라집니다**(FK 가 CASCADE). 어느 쪽이든
**라이브러리 행은 안 지웁니다**: 다른 회차의 run 이 같은 라이브러리를 가리키고 있어서 지우면 그 회차가
함께 무너집니다.

**무엇을 잃는지 지우기 전에 셉니다**(0장) — 표마다 몇 행이 걸리는지 미리보기가 냅니다. FK 가
`NO ACTION` 인 자리(확인 요청 · 회의 항목)가 걸려 있으면 `삭제` 는 **사람 말로 멈춥니다.**

## 기본은 미리보기

`--실행` 일 때만 바꿉니다. 바꿀 것이 있을 때만 직전에 `VACUUM INTO` 사본을 뜨고, 세션이 여는 파일과
사본을 뜰 파일이 다르면 아무것도 안 합니다. 넣은 뒤 commit 전에 **DB 를 다시 세어** 계획과 견주고
다르면 되돌립니다. **값은 안 찍습니다 — 건수만.**

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/노션업무들이기.py --회차 1
    .venv\\Scripts\\python.exe scripts/노션업무들이기.py --회차 1 --실행
"""

from __future__ import annotations

import sys as _sys

for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import argparse
import json
import pathlib
import sys
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select                                  # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from app import config                                               # noqa: E402
from app.db import SessionLocal                                      # noqa: E402
from app.domain import dweek                                         # noqa: E402
from app.models import Department, Retreat, TaskLibrary, TaskRun     # noqa: E402
from scripts.노션업무짝짓기 import 표지인가                            # noqa: E402
from scripts.비품들여오기 import 멈춤, 회차머리                         # noqa: E402
from scripts.재정들여오기 import 사본을_뜬다                            # noqa: E402

# 노션 「담당팀」·「관련 팀」 → 앱 부서 키(2장). **「2 봉사팀 공통」 은 앱에 부서가 없습니다** —
# 2장에서 해체했으므로 비우고(총무팀 소관) 몇 건인지 셉니다. 「교개협」 도 앱 부서가 아닙니다.
팀표 = {"1 총무M": "chongmuM", "1 총무팀": "chongmu", "3 선교사회": "seongyo", "4 스케치": "sketch",
       "5 헤브론": "hebron", "6 코람데오": "koram", "7 재정": "jaejeong", "8 개기자": "gaegija",
       "9 새친구팀": "saechingu"}
구분표 = {"Main": "main", "Sub": "sub", "Sch": "schedule"}
지움방식들 = ("뺌", "삭제")
칸이름 = ("id", "제목", "구분", "담당", "관련팀", "시작", "마감", "관련업무", "설명")


def _날짜(값: str, 줄번호: int):
    """**줄 번호를 함께 말한다** — 값을 못 찍는 파일이라 줄 번호가 사람의 유일한 손잡이다(4-18)."""
    import datetime as dt
    if not 값:
        return None
    try:
        return dt.date.fromisoformat(값)
    except ValueError:
        raise 멈춤(f"{줄번호}번째 줄의 날짜 꼴이 아닙니다 — 아무것도 안 했습니다.") from None


def 읽는다(경로: pathlib.Path) -> tuple[list[dict], dict[str, int]]:
    """tsv 를 읽어 **표지를 뺀** 줄과 **읽은 수**를 돌려준다. 값을 고치지 않는다.

    읽은 줄 · 표지 · 남은 줄을 셋 다 돌려주는 까닭은, 그 셋이 맞아야 노션이 스스로 센 수와
    대조가 되기 때문이다(4-18 의 「읽은 줄 수를 찍고 사람이 시트에서 세어 맞춥니다」).
    마지막 수 하나만 찍으면 옮겨 적다 한 줄이 빠져도 알 길이 없다.
    """
    if not 경로.exists():
        raise 멈춤(f"노션 줄 파일이 없습니다: data/{경로.name}")
    줄들 = []
    for 번호, 한줄 in enumerate(경로.read_text(encoding="utf-8").splitlines(), 1):
        if not 한줄.strip():
            continue
        칸 = 한줄.split("\t")
        # **칸이 남으면 멈춘다** — 뒤의 빈 칸을 안 쓴 줄과 「가운데 칸이 빠진 줄」 은 패딩으로
        # 구별이 안 되고, 빠지면 그 줄의 뒤 칸이 통째로 한 칸씩 밀린 채 조용히 들어간다
        if len(칸) > len(칸이름):
            raise 멈춤(f"{번호}번째 줄의 칸이 {len(칸)}개입니다(최대 {len(칸이름)}) — 아무것도 안 했습니다.")
        r = dict(zip(칸이름, 칸 + [""] * len(칸이름)))
        r["줄번호"] = 번호
        줄들.append(r)
    if not 줄들:
        raise 멈춤("노션 줄 파일이 비었습니다.")
    빈것 = [r["줄번호"] for r in 줄들 if not r["id"] or not r["제목"]]
    if 빈것:
        raise 멈춤(f"id 나 제목이 빈 줄이 {len(빈것)}개 있습니다(첫 줄 {빈것[0]}) — 아무것도 안 했습니다.")
    if len({r["id"] for r in 줄들}) != len(줄들):
        raise 멈춤("같은 노션 id 가 두 줄에 있습니다 — 아무것도 안 했습니다.")
    for r in 줄들:                                     # 날짜 꼴과 앞뒤를 여기서 한 번에 본다
        시작, 마감 = _날짜(r["시작"], r["줄번호"]), _날짜(r["마감"], r["줄번호"])
        if 마감 and 시작 and 마감 < 시작:
            raise 멈춤(f"{r['줄번호']}번째 줄의 마감이 시작보다 빠릅니다 — 아무것도 안 했습니다.")
        if 마감 and not 시작:
            raise 멈춤(f"{r['줄번호']}번째 줄에 시작 없이 마감만 있습니다 — 아무것도 안 했습니다.")
    남은 = [r for r in 줄들 if not 표지인가(r["제목"])]
    return 남은, {"읽은 줄": len(줄들), "D-주차 표지": len(줄들) - len(남은), "남은 줄": len(남은)}


def _목록(글: str, 줄번호: int = 0) -> list[str]:
    """`["a","b"]` 를 읽는다 — 비었으면 빈 목록. **여기도 줄 번호를 말한다**(다른 멈춤과 같게)."""
    글 = (글 or "").strip()
    if not 글:
        return []
    try:
        값 = json.loads(글)
    except ValueError:
        raise 멈춤(f"{줄번호}번째 줄의 목록 칸이 json 이 아닙니다 — 아무것도 안 했습니다.") from None
    if not isinstance(값, list):
        raise 멈춤(f"{줄번호}번째 줄의 목록 칸이 배열이 아닙니다 — 아무것도 안 했습니다.")
    return [str(x) for x in 값]


@dataclass
class 계획:
    세울: list[dict] = field(default_factory=list)      # 라이브러리+run 으로 설 줄
    관계: dict[str, list[str]] = field(default_factory=dict)   # 노션 id → 노션 id 들 (양쪽으로 편 것)
    내릴: list[int] = field(default_factory=list)       # 지금 회차의 run id
    수: dict[str, int] = field(default_factory=dict)
    지움방식: str = "뺌"
    # 새 run 이 받을 첫 번호. **회차 안에서 번호가 겹치면 안 된다**(4-14 — 회의에서 번호로 부른다).
    # 「뺌」 은 옛 run 이 번호를 쥔 채 남으므로 그 뒤부터 잇고, 「삭제」 는 1부터다.
    번호시작: int = 1


# 사람이 읽을 이름만 적는다 — **표도 칸도 `ondelete` 도 스키마에서 받는다.**
# 손으로 적어 두었더니 하루도 안 돼 한 칸이 틀렸다(`meeting_items` 를 NO ACTION 으로 적었는데
# 실제로는 SET NULL 이었고, 그 어긋남이 「삭제」 를 막는 조건으로 쓰이고 있었다 — 두 번째 검토 [A]).
# 11-2 의 「목록에 든 것을 보는 것이 아니라 닿지 않는 칸이 없는지를 잰다」 와 같은 자리다.
_사람말 = {"discussion_entries": "논의", "discussion_entry_runs": "논의 잇기",
         "task_attachments": "첨부", "notification_logs": "보낸 알림 기록",
         "review_requests": "확인 요청", "meeting_items": "회의 항목이 가리킴"}
# 지우는 것을 **막는** 걸림. 나머지(CASCADE = 함께 사라짐 · SET NULL = 가리킴을 잃음)는 막지 않는다.
_막는걸림 = ("NO ACTION", "RESTRICT")


def 걸리는곳() -> list[tuple[str, str, str, str]]:
    """(사람 말, 표, 칸, ondelete) — `task_runs.id` 를 가리키는 FK 를 **스키마에서** 훑는다."""
    from app.models import Base, TaskRun
    난것 = []
    for 표 in Base.metadata.sorted_tables:
        for fk in 표.foreign_keys:
            if fk.column is not TaskRun.__table__.c.id:
                continue
            난것.append((_사람말.get(표.name, 표.name), 표.name, fk.parent.name,
                       (fk.ondelete or "NO ACTION").upper()))
    return sorted(난것, key=lambda x: (x[1], x[2]))


def 잃을것(db: Session, run_ids: list[int]) -> dict[str, int]:
    """그 run 들을 지우면 어느 표에 몇 행이 걸리는지 — **아무것도 안 바꾼다.**

    `CASCADE` 는 함께 사라지는 것이고 `SET NULL` 은 **가리킴만 잃는 것**이라 뜻이 다르다
    (`scripts/계정정리.py` 가 「함께 사라지는 것」 과 「이름을 잃는 것」 을 가른 그 구분).
    한 칸에 섞으면 0장의 「무엇을 잃는지 안 뒤에 지웁니다」 가 성립하지 않는다.
    """
    from sqlalchemy import text
    자리 = ",".join(str(int(i)) for i in run_ids)
    난것 = {}
    for 이름, 표, 칸, 걸림 in 걸리는곳():
        수 = 0 if not run_ids else db.execute(
            text(f"SELECT COUNT(*) FROM {표} WHERE {칸} IN ({자리})")).scalar_one()
        난것[f"삭제면 걸림 · {이름}({걸림})"] = 수
    return 난것


def 고른다(db: Session, retreat: Retreat, 노션들: list[dict], *,
          구분없음: str = "main", 지움방식: str = "뺌") -> 계획:
    """아무것도 바꾸지 않고 계획만 세운다 — 미리보기와 실행이 같은 것을 쓴다."""
    if 지움방식 not in 지움방식들:
        raise 멈춤(f"--지움방식 은 {' 또는 '.join(지움방식들)} 입니다.")
    if 구분없음 not in 구분표.values():
        raise 멈춤(f"--구분없음 은 {' · '.join(구분표.values())} 중 하나입니다.")
    if not retreat.start_date:
        raise 멈춤("회차에 개회일이 없어 D-주차를 셀 수 없습니다 — 아무것도 안 했습니다.")

    # **두 번 들이지 않는다** — 열쇠가 이미 있으므로 그것으로 본다(재정들여오기가 활동 기록으로 막는 그 자리).
    이미 = db.scalar(select(func.count(TaskLibrary.id)).where(TaskLibrary.notion_page_id.in_({r["id"] for r in 노션들})))
    if 이미:
        raise 멈춤(f"같은 노션 페이지 id 를 가진 라이브러리가 이미 {이미}개 있습니다 — 이미 들여온 것으로 보고 아무것도 안 했습니다.")

    부서키 = {d.key: d.id for d in db.scalars(select(Department).where(Department.retreat_id == retreat.id)) if d.key}
    판 = 계획(지움방식=지움방식)
    셈 = {"노션 줄(표지 뺌)": len(노션들), "구분 없어 기본으로 둘 줄": 0, "담당을 못 옮긴 줄": 0,
         "관련팀을 일부 버린 줄": 0, "날짜가 없는 줄": 0, "업무 규칙이 붙는 줄": 0,
         "노션이 적은 관련업무 칸의 항목": 0, "옮길 수 있는 관련업무 항목": 0,
         "자기·표지·이 표 밖을 가리켜 못 옮기는 항목": 0}

    for 순서, r in enumerate(노션들, 1):
        구분 = 구분표.get(r["구분"] or "", "")
        if not 구분:
            구분 = 구분없음
            셈["구분 없어 기본으로 둘 줄"] += 1
        키 = 팀표.get(r["담당"] or "")
        if (r["담당"] or "") and not 키:
            셈["담당을 못 옮긴 줄"] += 1
        관련팀 = [팀표[x] for x in _목록(r["관련팀"], r.get("줄번호", 0)) if x in 팀표]
        if len(관련팀) != len(_목록(r["관련팀"], r.get("줄번호", 0))):
            셈["관련팀을 일부 버린 줄"] += 1
        시작, 마감 = _날짜(r["시작"], r.get("줄번호", 0)), _날짜(r["마감"], r.get("줄번호", 0))
        if not 시작:
            셈["날짜가 없는 줄"] += 1
        if (r["설명"] or "").strip():
            셈["업무 규칙이 붙는 줄"] += 1
        자리 = (dweek.relative_position(retreat.start_date, 시작, 마감 or 시작) if 시작
                else {"date_anchor": "week", "default_d_week": None, "default_offset_days": 0, "default_span_days": 0})
        판.세울.append({
            "노션id": r["id"], "제목": r["제목"], "구분": 구분, "부서키": 키,
            "부서id": 부서키.get(키) if 키 else None, "관련팀": 관련팀,
            "시작": 시작, "마감": 마감 or 시작, "규칙": (r["설명"] or "").replace("⏎", "\n").strip() or None,
            "자리": 자리, "번호": 순서,
        })

    # 관련업무 — 노션 쪽이 한쪽에만 적혀 있어도 앱은 양쪽에 적는다(2장)
    양쪽: dict[str, set[str]] = {r["id"]: set() for r in 노션들}
    for r in 노션들:
        대상들 = _목록(r["관련업무"], r.get("줄번호", 0))
        셈["노션이 적은 관련업무 칸의 항목"] += len(대상들)
        for x in 대상들:
            if x in 양쪽 and x != r["id"]:
                양쪽[r["id"]].add(x)
                양쪽[x].add(r["id"])
                셈["옮길 수 있는 관련업무 항목"] += 1
            else:
                셈["자기·표지·이 표 밖을 가리켜 못 옮기는 항목"] += 1
    판.관계 = {k: sorted(v) for k, v in 양쪽.items() if v}

    지금 = db.scalars(select(TaskRun).where(TaskRun.retreat_id == retreat.id)).all()
    판.내릴 = [t.id for t in 지금]
    셈["지금 회차의 run"] = len(지금)
    셈["그중 이미 빼 둔 run"] = sum(1 for t in 지금 if not t.included)
    셈["지금 회차 run 이 쓰는 라이브러리"] = len({t.library_id for t in 지금})
    셈["그 라이브러리를 함께 쓰는 다른 회차의 run"] = db.scalar(
        select(func.count(TaskRun.id)).where(TaskRun.retreat_id != retreat.id,
                                             TaskRun.library_id.in_([t.library_id for t in 지금] or [-1]))) or 0
    # **지울 때 걸리는 참조는 지우기 전에 센다**(0장) — 문장 한 줄로 말하지 않고 표마다 셈에 담는다.
    # 「뺌」 이면 하나도 안 사라지지만 그때도 찍는다: 두 갈래를 견주고 고르는 것이 사람이다.
    셈.update(잃을것(db, 판.내릴))
    # **어느 갈래든 남은 번호 다음부터 잇는다**(4-14). 「삭제」 라고 1부터 주면 1..102 가
    # **살아 있는 다른 업무**를 가리키게 되는데, 그것이 4-14 가 막으려던 바로 그 상태다
    # (행이 사라져 가리킬 곳이 없는 것과 다르다 — 두 번째 검토 [C]). 빈 번호는 안 메운다
    판.번호시작 = (max((t.run_no or 0) for t in 지금) + 1) if 지금 else 1
    이름들 = {r["제목"] for r in 노션들}
    셈["제목이 같은 라이브러리가 이미 있는 줄"] = db.scalar(
        select(func.count(TaskLibrary.id)).where(TaskLibrary.title.in_(이름들))) or 0
    셈["새로 설 라이브러리"] = len(판.세울)
    셈["새로 설 run"] = len(판.세울)
    판.수 = 셈
    return 판


def 센다(db: Session, retreat: Retreat) -> dict[str, int]:
    """**아무것도 안 바꾼다** — 미리보기·실행·다시 세기가 같은 셈을 쓴다."""
    run = lambda 조건: db.scalar(select(func.count(TaskRun.id)).where(TaskRun.retreat_id == retreat.id, *조건))  # noqa: E731
    수 = {"run": run([]), "산 run": run([TaskRun.included.is_(True)]),
         "라이브러리": db.scalar(select(func.count(TaskLibrary.id))),
         "다른 회차 run": db.scalar(select(func.count(TaskRun.id)).where(TaskRun.retreat_id != retreat.id))}
    for 이름 in ("main", "sub", "schedule"):
        수[f"산 run · {이름}"] = db.scalar(
            select(func.count(TaskRun.id)).join(TaskLibrary, TaskLibrary.id == TaskRun.library_id)
            .where(TaskRun.retreat_id == retreat.id, TaskRun.included.is_(True), TaskLibrary.kind == 이름))
    return 수


def 넣는다(db: Session, retreat: Retreat, 판: 계획) -> None:
    """넣기만 한다 — commit 은 부르는 쪽이 한다."""
    if 판.지움방식 == "삭제":
        # **FK 가 NO ACTION 인 자리는 지우려는 순간 걸린다.** 먼저 보고 사람 말로 멈춘다 —
        # 안 그러면 flush 에서 IntegrityError 원시 트레이스백이 나온다(검토 [3])
        막는것 = {k: v for k, v in 잃을것(db, 판.내릴).items()
                if v and any(f"({걸림})" in k for 걸림 in _막는걸림)}
        if 막는것:
            raise 멈춤("지우려는 run 을 FK 가 막는 자리가 있습니다 — "
                      + " · ".join(f"{k} {v}" for k, v in 막는것.items()) + ". 아무것도 안 했습니다.")
        for rid in 판.내릴:
            db.delete(db.get(TaskRun, rid))
    else:
        for rid in 판.내릴:
            db.get(TaskRun, rid).included = False
    db.flush()

    선것: dict[str, TaskLibrary] = {}
    for 줄 in 판.세울:
        lib = TaskLibrary(title=줄["제목"], kind=줄["구분"], default_department_key=줄["부서키"],
                          related_department_keys=줄["관련팀"], related_library_ids=[],
                          prerequisite_library_ids=[], rules=줄["규칙"],
                          notion_page_id=줄["노션id"], origin="history", **줄["자리"])
        db.add(lib)
        선것[줄["노션id"]] = lib
    db.flush()
    for 노션id, 대상들 in 판.관계.items():
        선것[노션id].related_library_ids = [선것[x].id for x in 대상들]
    번호 = 판.번호시작 - 1
    for 줄 in 판.세울:
        번호 += 1
        db.add(TaskRun(library_id=선것[줄["노션id"]].id, retreat_id=retreat.id, included=True,
                       run_no=번호, department_id=줄["부서id"], d_week=줄["자리"]["default_d_week"],
                       start_date=줄["시작"], end_date=줄["마감"], status="대기", blocked_by_run_ids=[]))
    db.flush()


def 미리보기찍기(판: 계획, 읽은수: dict[str, int]) -> None:
    print("노션 업무 그대로 들이기 (건수만):")
    for k, v in 읽은수.items():
        print(f"  {k}: {v}")
    print("  ↑ 이 셋을 노션에서 세어 맞춰 보세요 — 옮겨 적다 빠진 줄이 있으면 수가 다릅니다.")
    for k, v in 판.수.items():
        print(f"  {k}: {v}")
    print(f"  새 run 이 받을 번호: {판.번호시작} 부터 (어느 갈래든 남은 번호 다음부터 잇습니다 — 4-14)")
    print(f"  지움방식: {판.지움방식} — " + ("run 행을 지웁니다(위 「삭제면 걸림」 이 함께 사라지거나 가리킴을 잃습니다)"
                                        if 판.지움방식 == "삭제" else
                                        "run 을 안 지우고 included 를 끕니다(0장) — 위 「삭제면 걸림」 은 하나도 안 사라집니다"))
    print("  라이브러리 행은 어느 쪽이든 안 지웁니다 — 다른 회차의 run 이 같은 것을 가리킵니다.")
    # **미리보기가 실행 결과를 미리 말한다**(11-2 의 순서가 선 전제) — 눌러 보고서야 알면 안 된다
    막을것 = {k: v for k, v in 판.수.items() if v and any(f"({걸림})" in k for 걸림 in _막는걸림)}
    if 판.지움방식 == "삭제" and 막을것:
        print("!! 이대로 --실행 하면 **아무것도 안 하고 멈춥니다** — FK 가 막는 자리: "
              + " · ".join(f"{k.split(' · ')[1]} {v}" for k, v in 막을것.items()))


def 돌린다(db: Session, 회차id: int | None, *, 실행: bool, 구분없음: str = "main",
          지움방식: str = "뺌", 파일: pathlib.Path | None = None, 사본: bool = True) -> 계획:
    retreat = 회차머리(db, 회차id)
    경로 = 파일 or pathlib.Path(config.DATA_DIR) / "노션업무전체.real.tsv"
    노션들, 읽은수 = 읽는다(경로)
    판 = 고른다(db, retreat, 노션들, 구분없음=구분없음, 지움방식=지움방식)
    미리보기찍기(판, 읽은수)          # **실행 때도 찍는다** — 안 찍으면 실행 로그에 계획 수가 안 남는다
    if not 실행:
        print("바꾸지 않았습니다. 실제로 넣으려면 --실행 을 붙이세요.")
        return 판
    전 = 센다(db, retreat)
    if 사본:
        사본을_뜬다()
    try:
        넣는다(db, retreat, 판)
        지금 = 센다(db, retreat)                       # 계획에서 되짚지 않고 DB 에서 다시 센다
        바랄run = len(판.세울) + (0 if 판.지움방식 == "삭제" else 전["run"])
        if 지금["run"] != 바랄run or 지금["산 run"] != len(판.세울):
            raise 멈춤(f"넣은 뒤 run 수가 계획과 다릅니다(run {지금['run']} · 산 run {지금['산 run']}) — 되돌렸습니다.")
        if 지금["라이브러리"] != 전["라이브러리"] + len(판.세울):
            raise 멈춤("넣은 뒤 라이브러리 수가 계획과 다릅니다 — 되돌렸습니다.")
        if 지금["다른 회차 run"] != 전["다른 회차 run"]:
            raise 멈춤("다른 회차의 run 이 바뀌었습니다 — 되돌렸습니다.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    print("넣었습니다 (건수만):")
    for k, v in 센다(db, retreat).items():
        print(f"  {k}: {v}")
    return 판


def main() -> int:
    ap = argparse.ArgumentParser(description="노션 업무를 그대로 한 회차의 업무로 들입니다.",
                                 epilog="기본은 미리보기입니다. 실제로 넣으려면 --실행 을 붙이세요.")
    ap.add_argument("--회차", type=int, default=None)
    ap.add_argument("--실행", action="store_true")
    ap.add_argument("--구분없음", default="main", help="노션에 업무속성이 없는 줄을 무엇으로 둘지")
    ap.add_argument("--지움방식", default="뺌", help=" · ".join(지움방식들))
    args = ap.parse_args()
    with SessionLocal() as db:
        try:
            돌린다(db, getattr(args, "회차"), 실행=getattr(args, "실행"),
                 구분없음=getattr(args, "구분없음"), 지움방식=getattr(args, "지움방식"))
            return 0
        except 멈춤 as e:
            print(f"!! {e}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
