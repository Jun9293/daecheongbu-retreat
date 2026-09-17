# -*- coding: utf-8 -*-
"""노션에서 들인 업무에 상위(`TaskLibrary.parent_library_id`)를 채웁니다 (2026-09-17 · 사람이 정함).

노션은 Main 아래의 Sub · 일정을 페이지 중첩이 아니라 `관련업무` 관계로 그립니다(봐둘것 BF-a).
앱은 들일 때 그 관계를 `related_library_ids` 로 옮겨 두었으므로 **노션을 다시 부르지 않습니다.**

- **Main 은 노션 업무속성으로 가릅니다 — 앱 `kind` 가 아닙니다.** 노션에서 속성이 빈 줄도 앱에는
  `main` 으로 들어가 있어(`노션업무들이기 --구분없음 main`) `kind` 로 가르면 한 줄이 빠집니다.
  업무속성은 저장소 밖 `data/노션업무전체.real.tsv` 에 있고, 읽는 곳은 `노션업무들이기.읽는다` 하나입니다
- **부모 고르기** — Main 이 아닌 줄의 `related_library_ids` 가 가리키는 Main 이
  하나면 그것, 여럿이면 **노션 담당팀이 같은 Main 이 하나일 때** 그것. 그 밖(같은 담당팀이 여럿 · 없음 ·
  Main 을 안 가리킴)은 **비웁니다.** 같은 담당팀으로 고른 것은 노션에 적힌 것이 아니라 추측입니다
- **Main 에는 부모를 안 둡니다** — Main 끼리의 관련업무는 「관련」 이지 「상위」 가 아닙니다(2장)
- **담당 부서가 다른 부모도 채웁니다** — 화면에서 자식을 부모 부서로 옮기지 않는 것은 화면의 일입니다.
  그 수를 따로 셉니다(앱 `default_department_key` 로 견줌)
- **`related_library_ids` 는 안 건드립니다** — 상위와 관련은 섞지 않고 둘 다 둡니다(2장 · 사람이 정함)
- **이미 부모가 있는 줄이 하나라도 있으면 멈춥니다** — 사람이 앱에서 고른 부모를 덮지 않습니다
- **고리를 봅니다** — 채운 뒤의 모양에서 부모를 따라 올라가다 같은 줄을 두 번 만나면 멈춥니다
- 노션 줄과 앱 라이브러리는 **노션 페이지 id** 로 잇습니다(제목은 열쇠가 못 됩니다). 한쪽에만 있는 줄이
  있으면 멈춥니다

## 기본은 미리보기

`--실행` 일 때만 바꿉니다. 바꿀 것이 있을 때만 직전에 `VACUUM INTO` 사본을 뜨고, 세션이 여는 파일과
사본을 뜰 파일이 다르면 아무것도 안 합니다. 넣은 뒤 commit 전에 **DB 를 다시 세어** 계획과 견주고
다르면 되돌립니다. **값은 안 찍습니다 — 건수만.** 사람이 볼 짝 표(제목이 든 것)는 저장소 밖
`data/업무계층채우기.real.md` 에 씁니다.

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/업무계층채우기.py
    .venv\\Scripts\\python.exe scripts/업무계층채우기.py --실행
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
from app.models import ActivityLog, TaskLibrary                      # noqa: E402
from scripts.노션업무들이기 import 읽는다                              # noqa: E402
from scripts.비품들여오기 import 멈춤                                  # noqa: E402
from scripts.재정들여오기 import 사본을_뜬다                            # noqa: E402

채움행위 = "업무_상위_채움"


def _키(노션id: str | None) -> str:
    return (노션id or "").replace("-", "").strip().lower()


def _목록(값) -> list[int]:
    if isinstance(값, str):
        try:
            값 = json.loads(값)
        except ValueError:
            값 = []
    return [int(x) for x in (값 or [])]


@dataclass
class 계획:
    채울: dict[int, int] = field(default_factory=dict)          # 자식 라이브러리 id → 부모 라이브러리 id
    하나만: list[int] = field(default_factory=list)
    같은팀: list[int] = field(default_factory=list)
    가를수없음: dict[int, list[int]] = field(default_factory=dict)   # 자식 → 후보 Main 들
    안가리킴: list[int] = field(default_factory=list)
    부서다름: list[int] = field(default_factory=list)
    main수: int = 0
    수: dict[str, int] = field(default_factory=dict)


def 고른다(db: Session, 노션들: list[dict]) -> 계획:
    """아무것도 안 바꾼다 — 미리보기와 실행이 같이 쓴다."""
    libs = {_키(l.notion_page_id): l for l in db.scalars(
        select(TaskLibrary).where(TaskLibrary.notion_page_id.is_not(None)))}
    줄들 = {_키(r["id"]): r for r in 노션들}
    if set(libs) != set(줄들):
        raise 멈춤(f"노션 줄과 앱 라이브러리가 1:1 로 맞지 않습니다(노션 {len(줄들)} · 앱 {len(libs)} · "
                  f"노션에만 {len(set(줄들) - set(libs))} · 앱에만 {len(set(libs) - set(줄들))}) — 아무것도 안 했습니다.")
    이미 = [l.id for l in libs.values() if l.parent_library_id is not None]
    if 이미:
        raise 멈춤(f"상위가 이미 적힌 라이브러리가 {len(이미)} 개 있습니다 — 덮지 않고 멈춥니다. 아무것도 안 했습니다.")

    id로 = {l.id: (l, 줄들[k]) for k, l in libs.items()}
    진짜main = {i for i, (_, r) in id로.items() if r["구분"] == "Main"}
    판 = 계획(main수=len(진짜main))
    for i, (lib, r) in sorted(id로.items()):
        if i in 진짜main:
            continue
        후보 = sorted({j for j in _목록(lib.related_library_ids) if j in 진짜main})
        if not 후보:
            판.안가리킴.append(i)
            continue
        if len(후보) == 1:
            부모 = 후보[0]
            판.하나만.append(i)
        else:
            같은 = [j for j in 후보 if id로[j][1]["담당"] == r["담당"]]
            if len(같은) != 1:
                판.가를수없음[i] = 후보
                continue
            부모 = 같은[0]
            판.같은팀.append(i)
        판.채울[i] = 부모
        if (id로[부모][0].default_department_key or "") != (lib.default_department_key or ""):
            판.부서다름.append(i)

    # **고리** — 채운 뒤의 모양에서 부모를 따라 올라간다(지금 DB 의 다른 부모까지 함께)
    지금부모 = dict(db.execute(select(TaskLibrary.id, TaskLibrary.parent_library_id)
                           .where(TaskLibrary.parent_library_id.is_not(None))).all())
    뒤 = {**지금부모, **판.채울}
    고리 = 0
    for 시작 in 판.채울:
        본 = {시작}
        x = 뒤.get(시작)
        while x is not None:
            if x in 본:
                고리 += 1
                break
            본.add(x)
            x = 뒤.get(x)
    if 고리:
        raise 멈춤(f"채우면 상위를 따라가다 고리에 빠지는 줄이 {고리} 개 생깁니다 — 아무것도 안 했습니다.")
    자식이main = sum(1 for p in 판.채울.values() if p not in 진짜main)

    판.수 = {"노션 줄(표지 뺌)": len(줄들), "노션 Main(업무속성)": len(진짜main),
            "Main 이 아닌 줄": len(id로) - len(진짜main),
            "채울 것": len(판.채울), "  · Main 하나만 가리킴": len(판.하나만),
            "  · 같은 담당팀 Main 이 하나": len(판.같은팀),
            "  · 채울 것 중 담당 부서가 다른 부모": len(판.부서다름),
            "비울 것": len(판.가를수없음) + len(판.안가리킴),
            "  · Main 여럿 · 가를 수 없음": len(판.가를수없음),
            "  · Main 을 안 가리킴": len(판.안가리킴),
            "부모가 Main 이 아닌 것": 자식이main, "고리": 고리}
    return 판


def 센다(db: Session) -> dict[str, int]:
    """아무것도 안 바꾼다 — 실행 전후를 DB 에서 다시 센다."""
    노션 = TaskLibrary.notion_page_id.is_not(None)
    return {"상위가 있는 노션 라이브러리": db.scalar(select(func.count(TaskLibrary.id))
                                               .where(노션, TaskLibrary.parent_library_id.is_not(None))),
            "상위가 있는 라이브러리 전체": db.scalar(select(func.count(TaskLibrary.id))
                                               .where(TaskLibrary.parent_library_id.is_not(None))),
            "라이브러리": db.scalar(select(func.count(TaskLibrary.id))),
            "채움 기록": db.scalar(select(func.count(ActivityLog.id)).where(ActivityLog.action == 채움행위))}


def 관련지문(db: Session) -> list[tuple[int, str]]:
    """`related_library_ids` 를 안 건드렸는지 견줄 지문."""
    return [(i, json.dumps(_목록(v), sort_keys=True)) for i, v in
            db.execute(select(TaskLibrary.id, TaskLibrary.related_library_ids).order_by(TaskLibrary.id)).all()]


def 넣는다(db: Session, 판: 계획) -> None:
    """넣기만 한다 — commit 은 부르는 쪽이 한다."""
    for 자식, 부모 in 판.채울.items():
        db.get(TaskLibrary, 자식).parent_library_id = 부모
    db.add(ActivityLog(actor_type="system", actor_name="업무계층채우기", action=채움행위,
                       target_type="task_library",
                       summary=f"노션 관련업무로 상위를 채움 — {len(판.채울)} (Main 하나 {len(판.하나만)} · "
                               f"같은 담당팀 {len(판.같은팀)} · 부서 다른 부모 {len(판.부서다름)}) · 비움 "
                               f"{len(판.가를수없음) + len(판.안가리킴)} (봐둘것 BF-a)",
                       after_value={"채움": {str(k): v for k, v in 판.채울.items()}}))
    db.flush()


def 짝표쓰기(db: Session, 판: 계획, 경로: pathlib.Path) -> None:
    """**저장소 밖** — 제목이 든다. 사람이 가를 수 없는 줄의 부모를 고를 때 본다."""
    제목 = dict(db.execute(select(TaskLibrary.id, TaskLibrary.title)).all())
    줄 = ["# 업무 상위 채우기 짝 표 (저장소 밖 · 값이 든다)", "",
          f"채울 것 {len(판.채울)} · 가를 수 없음 {len(판.가를수없음)} · Main 을 안 가리킴 {len(판.안가리킴)}", "",
          "## Main 여럿 · 가를 수 없음 — 사람이 고른다", ""]
    for i, 후보 in 판.가를수없음.items():
        줄.append(f"- {i} · {제목.get(i, '')} ← " + " / ".join(f"{j} · {제목.get(j, '')}" for j in 후보))
    줄 += ["", "## 같은 담당팀으로 고른 것 — 추측", ""]
    for i in 판.같은팀:
        줄.append(f"- {i} · {제목.get(i, '')} ← {판.채울[i]} · {제목.get(판.채울[i], '')}")
    줄 += ["", "## 담당 부서가 다른 부모", ""]
    for i in 판.부서다름:
        줄.append(f"- {i} · {제목.get(i, '')} ← {판.채울[i]} · {제목.get(판.채울[i], '')}")
    경로.write_text("\n".join(줄) + "\n", encoding="utf-8")


def 돌린다(db: Session, *, 실행: bool, 파일: pathlib.Path | None = None, 사본: bool = True,
          짝표: pathlib.Path | None = None) -> 계획:
    경로 = 파일 or pathlib.Path(config.DATA_DIR) / "노션업무전체.real.tsv"
    노션들, _ = 읽는다(경로)
    판 = 고른다(db, 노션들)
    짝표 = 짝표 or pathlib.Path(config.DATA_DIR) / "업무계층채우기.real.md"
    짝표쓰기(db, 판, 짝표)
    print("업무 상위 채우기 (건수만):")
    for k, v in 판.수.items():
        print(f"  {k}: {v}")
    print(f"  짝 표: {짝표.parent.name}/{짝표.name} (저장소 밖)")
    print("  related_library_ids 는 안 건드립니다 — 상위와 관련을 둘 다 둡니다.")
    if not 실행:
        print("바꾸지 않았습니다. 실제로 채우려면 --실행 을 붙이세요.")
        return 판
    if not 판.채울:
        print("채울 것이 없습니다 — 아무것도 안 했습니다.")
        return 판
    전, 전지문 = 센다(db), 관련지문(db)
    if 사본:
        사본을_뜬다()
    try:
        넣는다(db, 판)
        지금 = 센다(db)
        if (지금["상위가 있는 노션 라이브러리"] != 전["상위가 있는 노션 라이브러리"] + len(판.채울)
                or 지금["상위가 있는 라이브러리 전체"] != 전["상위가 있는 라이브러리 전체"] + len(판.채울)
                or 지금["라이브러리"] != 전["라이브러리"]
                or 지금["채움 기록"] != 전["채움 기록"] + 1):
            raise 멈춤("채운 뒤 수가 계획과 다릅니다 — 되돌렸습니다.")
        if 관련지문(db) != 전지문:
            raise 멈춤("related_library_ids 가 바뀌었습니다 — 되돌렸습니다.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    print("채웠습니다 (건수만):")
    for k, v in 센다(db).items():
        print(f"  {k}: {v}")
    return 판


def main() -> int:
    ap = argparse.ArgumentParser(description="노션에서 들인 업무에 상위를 채웁니다.",
                                 epilog="기본은 미리보기입니다. 실제로 채우려면 --실행 을 붙이세요.")
    ap.add_argument("--실행", action="store_true")
    args = ap.parse_args()
    with SessionLocal() as db:
        try:
            돌린다(db, 실행=getattr(args, "실행"))
            return 0
        except 멈춤 as e:
            print(f"!! {e}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
