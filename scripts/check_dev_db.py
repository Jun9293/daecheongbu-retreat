# -*- coding: utf-8 -*-
"""개발 DB 에 실명이 있으면 devserve 를 **띄우지 않는다** (11-2).

2026-09-07 에 개발 DB($env:TEMP\\dcb-dev\\app.db)가 익명화 이전 자료를 들고
있었고, 그걸로 찍은 스크린샷 2장에 실명 7개가 들어간 채 **커밋 직전까지**
갔다 — 검토자가 막았다. 스크린샷은 늘 개발 서버에서 찍으므로, 서버가
뜨기 전에 DB 를 검사하는 것이 그 길을 입구에서 막는다.

- 사람 이름이 지나가는 칸만 본다 (아래 `이름칸`)
- 대조는 대응표의 **실명 쪽**과, `anonymize.py` 의 경계 규칙으로 —
  앞뒤가 한글·영문·숫자면 이름이 아니되(안 그러면 한 글자 표기가
  `진행` 같은 보통 낱말 속에서 걸려 서버가 영영 안 뜬다), **`M` 이
  붙었으면 뒤에 조사가 와도 이름이다** (`◯◯M으로` — 11-2 에서 실제로
  샌 모양). 두 규칙 다 anonymize 와 같은 패턴 모양이다 — 두 판이 되면
  갈리고, 갈린 쪽을 아무도 모른다
- **이름은 찍지 않는다.** 몇 칸에서 걸렸는지만 말한다
- 대응표가 없는 컴퓨터(새로 받은 사본)에서는 검사할 것이 없다 — 통과.
  다만 **대응표가 있는데 읽기를 거절당하면(깨짐·겹침) 통과가 아니라
  멈춤이다** — 게이트가 조용히 꺼진 채 초록을 내면 "0개를 보며 초록"
  (11-3)과 같은 모양이다

devserve.bat 이 서버를 띄우기 전에 부른다. 걸리면 0 이 아닌 값으로 끝나
서버가 안 뜬다.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import sqlite3
import sys

# 콘솔이 cp949 여도 안내문이 죽지 않아야 한다 (11-3 — check_names 와 같은 이유)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent

_스펙 = importlib.util.spec_from_file_location(
    "_anonymize_for_devdb", ROOT / "scripts" / "anonymize.py")
_anon = importlib.util.module_from_spec(_스펙)
_스펙.loader.exec_module(_anon)

# 사람 이름이 지나가는 칸 — 늘어나면 여기 더한다 (check_names 의 담당칸과
# 같은 원칙: 이 목록이 곧 "무엇을 보는가" 다)
이름칸: tuple[tuple[str, str], ...] = (
    ("users", "name"),
    ("expense_entries", "payer_name"),
    ("expense_entries", "meal_attendee_names"),   # JSON 배열이지만 글로 본다
    ("budget_categories", "level3"),              # 강사 이름이 들어간다
    ("program_items", "assignee_name"),
    ("program_items", "text"),                    # 실제 카페 이름이 살던 칸 —
                                                  # 장소가 대응표에 든 뒤에도 이
                                                  # 칸을 안 보면 그 경로가 그대로다
    ("programs", "host"),
    ("programs", "name"),
    ("programs", "place"),
    ("meetings", "body"),
    ("discussion_entries", "body"),
)


def 실명이있나(db_path: pathlib.Path) -> dict:
    """{칸 이름: 걸린 수}. 비면 깨끗한 것이다. 이름은 담지 않는다."""
    if not _anon.MAP_PATH.exists():
        return {}          # 대응표가 없는 컴퓨터 — 대조할 실명이 없다

    # 대응표가 깨졌으면(load_map 의 SystemExit) **그대로 멈춘다** —
    # 삼키면 게이트가 조용히 꺼진 채 통과한다 (fail-open). 빈 목록도
    # 통과가 아니다 — 센 것이 0이면 성공이 아니라 실패다 (11-3)
    names = _anon.load_map()[0]
    if not names:
        raise SystemExit("대응표가 비어 있습니다 — 0개를 보는 검사는 통과가 아닙니다 (11-3)")

    if not db_path.exists():
        return {}

    # anonymize 의 경계 규칙과 같은 패턴 모양 (anonymize.py 의 본문 참고) —
    # 낱말에 붙은 것은 이름이 아니고, `이름M` 은 뒤에 조사가 와도 이름이다
    # (`◯◯M으로` — M 가지에는 뒤 lookahead 를 걸지 않는다)
    wordish = _anon.WORDISH
    patterns = [
        re.compile(f"(?<!{wordish}){re.escape(real)}(?:M|(?!{wordish}))")
        for real, _ in names
    ]

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    걸림: dict[str, int] = {}
    try:
        표들 = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for 표, 칸 in 이름칸:
            if 표 not in 표들:
                continue
            칸들 = {r[1] for r in con.execute(f"PRAGMA table_info({표})")}
            if 칸 not in 칸들:
                continue
            수 = 0
            for (값,) in con.execute(f"SELECT {칸} FROM {표} WHERE {칸} IS NOT NULL"):
                글 = str(값)
                if any(p.search(글) for p in patterns):
                    수 += 1
            if 수:
                걸림[f"{표}.{칸}"] = 수
    finally:
        con.close()
    return 걸림


def main() -> int:
    data_dir = pathlib.Path(
        os.environ.get("DCB_DATA_DIR")
        or pathlib.Path(os.environ.get("TEMP", "/tmp")) / "dcb-dev"
    )
    db_path = data_dir / "app.db"
    걸림 = 실명이있나(db_path)
    if not 걸림:
        return 0

    print("!! 개발 DB 에 실명이 있습니다 — 서버를 띄우지 않습니다.")
    for 자리, 수 in sorted(걸림.items()):
        print(f"   {자리}: {수}칸")
    print()
    print("   익명화 이전 자료가 남은 것입니다. 지우고 seed 를 다시 만드세요:")
    print(f'     Remove-Item "{db_path}" -Force')
    print("   그 뒤 devserve 를 다시 켜면 seed(가명)로 새로 만들어집니다.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
