# -*- coding: utf-8 -*-
"""노션에서 옮겨 온 회의록에 **노션 페이지 id** 를 답니다 (노션 대조 2판 · 2026-09-15).

`scripts/import_meetings.py` 는 내보낸 `.md` 파일 이름만 출처로 남겼습니다(`meetings.source_ref`).
파일 이름은 사람이 붙인 줄인 이름이라 원본을 가리키는 열쇠가 못 됩니다 — 이 스크립트가 원본 페이지 id 를
`meetings.notion_page_id` 에 채웁니다.

- 페이지 목록은 `data/노션회의록.real.json` 에서 읽습니다(노션에서 조회해 옮겨 적은 것 · 저장소 밖)
- **파일 이름 → 페이지 짝은 이 파일의 `짝짓는다` 하나가 정합니다.** 파일 이름 앞의 번호(「01-」)를 떼고,
  페이지 제목에서 빈칸과 끝의 「회의록」 을 뗀 것과 ① 글자가 같으면 짝, ② 남은 것끼리는 파일 이름 글자가
  제목 안에 **순서대로 다 들어 있고 그런 페이지가 전체 페이지 중 하나일 때만** 짝입니다. 둘 이상이거나 없으면,
  번호를 뗀 출처 이름이 겹치거나 한 페이지가 출처 둘과 짝지어지면 멈춥니다
- **대상은 origin 이 노션이고 출처가 그 파일인 회의 전부**입니다 — 한 파일이 회의 여럿으로 잘렸으면 그 여럿에
  같은 id 를 답니다. 앱에서 만든 회의(origin 이 노션이 아닌 것)는 안 건드립니다
- 이미 id 가 있으면 건너뜁니다. **다른 id 가 이미 있으면 덮지 않고 멈춥니다**
- 값(제목 · id)은 찍지 않습니다 — 건수만

## 기본은 미리보기

`--실행` 일 때만 채웁니다. 채울 것이 있을 때만 직전에 `VACUUM INTO` 사본을 뜨고, 세션이 여는 파일과 사본을 뜰
파일이 다르면 아무것도 안 합니다(재정들여오기 의 `사본을_뜬다`). 채운 뒤 commit 전에 DB 를 다시 세어 계획과
견줍니다. 채울 것이 없으면 「채울 것이 없습니다」 로 끝납니다.

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/회의록id달기.py
    .venv\\Scripts\\python.exe scripts/회의록id달기.py --실행
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
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select                                  # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from app import config                                               # noqa: E402
from app.db import SessionLocal                                      # noqa: E402
from app.models import Meeting                                       # noqa: E402
from scripts.비품들여오기 import 멈춤                                   # noqa: E402
from scripts.재정들여오기 import 사본을_뜬다                            # noqa: E402

노션 = "노션"


def 파일줄기(source_ref: str) -> str:
    return re.sub(r"^\d+-", "", source_ref).replace(" ", "")


def 제목줄기(title: str) -> str:
    return re.sub(r"회의록$", "", title.replace(" ", ""))


def _순서대로든다(짧은: str, 긴: str) -> bool:
    it = iter(긴)
    return all(ch in it for ch in 짧은)


def 짝짓는다(출처들: list[str], 페이지: list[dict]) -> dict[str, dict]:
    """source_ref → 페이지. 글자가 같은 것 먼저, 남은 것은 순서대로 든 것이 하나일 때만."""
    줄기들 = [파일줄기(s) for s in 출처들]
    if len(set(줄기들)) != len(줄기들):
        raise 멈춤("번호를 떼면 이름이 같은 출처 파일이 둘 이상입니다 — 아무것도 안 했습니다.")
    짝: dict[str, dict] = {}
    남은출처 = []
    for s in 출처들:
        같은 = [p for p in 페이지 if 제목줄기(p["title"]) == 파일줄기(s)]
        if len(같은) > 1:
            raise 멈춤("제목이 같은 페이지가 둘 이상인 파일이 있습니다 — 아무것도 안 했습니다.")
        if 같은:
            짝[s] = 같은[0]
        else:
            남은출처.append(s)
    for s in 남은출처:
        # 후보는 **전체 페이지**에서 센다 — 이미 짝지은 페이지를 빼고 세면 여럿에 걸리는 짧은 이름도 하나로 보인다
        든 = [p for p in 페이지 if _순서대로든다(파일줄기(s), 제목줄기(p["title"]))]
        if len(든) != 1:
            raise 멈춤(f"파일 이름으로 페이지를 하나로 못 정한 출처가 있습니다(후보 {len(든)}) — 아무것도 안 했습니다.")
        짝[s] = 든[0]
    if len({p["id"] for p in 짝.values()}) != len(짝):
        raise 멈춤("한 페이지가 출처 파일 둘 이상과 짝지어졌습니다 — 아무것도 안 했습니다.")
    return 짝


@dataclass
class 계획:
    채울: list[tuple[int, str]] = field(default_factory=list)   # (meeting id, page id)
    수: dict[str, int] = field(default_factory=dict)


def 페이지읽기(경로: pathlib.Path) -> list[dict]:
    if not 경로.exists():
        raise 멈춤(f"페이지 목록 파일이 없습니다: data/{경로.name}")
    페이지 = json.loads(경로.read_text(encoding="utf-8")).get("페이지") or []
    if not 페이지 or any(not p.get("id") or not p.get("title") for p in 페이지):
        raise 멈춤("페이지 목록이 비었거나 id · title 이 빠진 줄이 있습니다.")
    return 페이지


def 고른다(db: Session, 페이지: list[dict]) -> 계획:
    회의 = db.scalars(select(Meeting).where(Meeting.origin == 노션)).all()
    출처들 = sorted({m.source_ref for m in 회의 if m.source_ref})
    짝 = 짝짓는다(출처들, 페이지)
    판 = 계획()
    판.수["노션 페이지"] = len(페이지)
    판.수["앱 출처 파일"] = len(출처들)
    판.수["짝지은 파일"] = len(짝)
    판.수["짝 없는 페이지"] = len(페이지) - len(짝)
    판.수["파일 이름 = 페이지 제목(글자 그대로)"] = sum(s == p["title"] for s, p in 짝.items())
    판.수["노션 회의"] = len(회의)
    판.수["회의 제목 = 페이지 제목(글자 그대로)"] = sum(m.title == 짝[m.source_ref]["title"] for m in 회의 if m.source_ref in 짝)
    판.수["출처 없는 노션 회의"] = sum(1 for m in 회의 if not m.source_ref)
    판.수["노션이 아닌 회의(안 건드림)"] = db.scalar(select(func.count(Meeting.id)).where((Meeting.origin != 노션) | (Meeting.origin.is_(None))))
    이미 = 0
    for m in 회의:
        if not m.source_ref:
            continue
        pid = 짝[m.source_ref]["id"]
        if m.notion_page_id == pid:
            이미 += 1
        elif m.notion_page_id:
            raise 멈춤("다른 페이지 id 가 이미 달린 회의가 있습니다 — 덮지 않고 멈춥니다.")
        else:
            판.채울.append((m.id, pid))
    판.수["이미 id 있음"] = 이미
    판.수["채울 회의"] = len(판.채울)
    return 판


def 단수(db: Session) -> int:
    return db.scalar(select(func.count(Meeting.id)).where(Meeting.notion_page_id.is_not(None)))


def 남의칸(db: Session) -> list[tuple[int, str | None]]:
    """노션이 아닌 회의의 (id, 페이지 id) — DB 에서 읽는다."""
    return sorted(db.execute(select(Meeting.id, Meeting.notion_page_id)
                             .where((Meeting.origin != 노션) | (Meeting.origin.is_(None)))).all())


def 돌린다(db: Session, 목록: pathlib.Path, 실행: bool, *, 사본: bool = True) -> 계획:
    판 = 고른다(db, 페이지읽기(목록))
    print("회의록에 노션 페이지 id 달기(건수만):")
    for k, v in 판.수.items():
        print(f"  {k}: {v}")
    if not 판.채울:
        print("채울 것이 없습니다.")
        return 판
    if not 실행:
        print("바꾸지 않았습니다. 실제로 채우려면 --실행 을 붙이세요.")
        return 판
    전 = 단수(db)
    전남 = 남의칸(db)
    if 사본:
        사본을_뜬다()
    try:
        for mid, pid in 판.채울:
            db.get(Meeting, mid).notion_page_id = pid
        db.flush()
        # 계획에서 되짚지 않고 DB 에서 다시 센다 — 칸만 고른 select 는 세션이 든 객체가 아니라 DB 의 값을 읽는다
        if 단수(db) != 전 + len(판.채울):
            raise 멈춤("채운 뒤 id 가 달린 회의 수가 계획과 다릅니다 — 되돌렸습니다.")
        지금 = dict(db.execute(select(Meeting.id, Meeting.notion_page_id)
                               .where(Meeting.id.in_([mid for mid, _ in 판.채울]))).all())
        if any(지금.get(mid) != pid for mid, pid in 판.채울):
            raise 멈춤("채운 회의의 id 가 계획과 다릅니다 — 되돌렸습니다.")
        if 남의칸(db) != 전남:
            raise 멈춤("노션이 아닌 회의가 바뀌었습니다 — 되돌렸습니다.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    print(f"채웠습니다. id 가 달린 회의: {전} → {단수(db)}")
    return 판


def main() -> int:
    ap = argparse.ArgumentParser(description="노션에서 옮긴 회의록에 노션 페이지 id 를 답니다.",
                                 epilog="기본은 미리보기입니다. 실제로 채우려면 --실행 을 붙이세요.")
    ap.add_argument("--실행", action="store_true")
    args = ap.parse_args()
    with SessionLocal() as db:
        try:
            돌린다(db, pathlib.Path(config.DATA_DIR) / "노션회의록.real.json", getattr(args, "실행"))
            return 0
        except 멈춤 as e:
            print(f"!! {e}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
