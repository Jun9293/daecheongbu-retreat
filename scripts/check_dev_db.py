# -*- coding: utf-8 -*-
"""개발 DB 에 실명이 있으면 devserve 를 **띄우지 않는다** (11-2).

2026-09-07 에 개발 DB($env:TEMP\\dcb-dev\\app.db)가 익명화 이전 자료를 들고
있었고, 그걸로 찍은 스크린샷 2장에 실명 7개가 들어간 채 **커밋 직전까지**
갔다 — 검토자가 막았다. 스크린샷은 늘 개발 서버에서 찍으므로, 서버가
뜨기 전에 DB 를 검사하는 것이 그 길을 입구에서 막는다.

- **글자 칸 전부를 본다** — 안 볼 것만 이유와 함께 뺀다 (아래 `제외칸`).
  볼 목록은 세 번 불완전했다(11-2) — 목록을 고쳐야 잡히는 구조는 그 사이가
  늘 뚫려 있다
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

# **볼 칸을 손으로 고르지 않는다 — 전부 보고, 안 볼 것만 이유와 함께 뺀다.**
# 「무엇을 보는가」 목록은 세 번 불완전했다(사람 이름만 · 텍스트만 · 칸 일부만).
# 새 칸이 생기면 목록을 고쳐야 잡히는 구조는 그 사이가 늘 뚫려 있다 —
# 글자 칸은 스키마에서 읽어 기본으로 전부 훑고(새 칸도 저절로 대상이 된다),
# 값의 형태가 정해져 있어 사람·장소·연락처가 들어올 수 없는 칸만 뺀다.
# 시험(test9)이 이 제외 목록을 모델과 견주고, 볼 칸마다 심어서 걸리는지 잰다.
제외칸: dict[tuple[str, str], str] = {
    ("activity_logs", "action"): "동작 슬러그 (코드가 정한 값)",
    ("activity_logs", "actor_type"): "user|claude|system",
    ("activity_logs", "target_type"): "대상 종류 슬러그",
    ("departments", "color_tag"): "색 값",
    ("departments", "key"): "영문 부서 키 (2장)",
    ("draft_submissions", "department_key"): "영문 부서 키",
    ("draft_submissions", "library_ids"): "숫자 id JSON",
    ("expense_receipts", "stored_name"): "임의 난수 파일명 (4-9)",
    ("file_assets", "status"): "상태 enum (옛 표)",
    ("file_versions", "stored_name"): "임의 난수 파일명",
    ("invite_tokens", "token_hash"): "토큰 해시 (4-12)",
    ("meeting_items", "kind"): "종류 enum",
    ("meetings", "origin"): "노션|직접 enum",
    ("meetings", "suggest_hash"): "본문 해시",
    ("meetings", "suggest_state"): "상태 enum",
    ("meetings", "suggest_tokens"): "토큰 수 문자열",
    ("notification_logs", "kind"): "알림 종류 enum (4-11)",
    ("notifications", "dedupe_key"): "기계 중복 키",
    ("notifications", "kind"): "알림 종류 enum",
    ("notifications", "link"): "내부 경로 (/tasks?task=N)",
    ("notifications", "target_type"): "대상 종류 슬러그",
    ("program_items", "part_key"): "고정 파트 목록 (5-3)",
    ("program_items", "phase"): "pre|mid|post",
    ("program_items", "scope"): "team|person",
    ("programs", "audience"): "all|staff",
    ("programs", "day"): "선발대|N일차|폐회 (5-1)",
    ("programs", "end_time"): "HH:MM",
    ("programs", "start_time"): "HH:MM",
    ("programs", "track"): "main|ops",
    ("push_subscriptions", "auth"): "푸시 키",
    ("push_subscriptions", "endpoint"): "푸시 서버 주소",
    ("push_subscriptions", "p256dh"): "푸시 키",
    ("push_subscriptions", "user_agent"): "브라우저가 만든 기계 문자열",
    ("retreat_drafts", "department_keys"): "영문 부서 키 JSON",
    ("retreat_drafts", "status"): "수집중|생성완료|취소",
    ("review_requests", "status"): "대기|승인|반려",
    ("schedule_days", "label"): "일자 라벨 (옛 표)",
    ("schedule_items", "end_time"): "HH:MM (옛 표)",
    ("schedule_items", "start_time"): "HH:MM (옛 표)",
    ("task_attachments", "stored_name"): "임의 난수 파일명 (4-9)",
    ("task_library", "date_anchor"): "week|open",
    ("task_library", "default_department_key"): "영문 부서 키",
    ("task_library", "origin"): "history|claude_suggestion",
    ("task_library", "prerequisite_library_ids"): "숫자 id JSON",
    ("task_library", "related_department_keys"): "영문 부서 키 JSON",
    ("task_library", "related_library_ids"): "숫자 id JSON",
    ("task_runs", "blocked_by_run_ids"): "숫자 id JSON",
    ("task_runs", "status"): "대기|진행중|완료 (4-3)",
    ("tasks", "blocked_by_task_ids"): "숫자 id JSON (옛 표)",
    ("tasks", "related_department_ids"): "숫자 id JSON (옛 표)",
    ("tasks", "status"): "상태 enum (옛 표)",
    ("users", "role"): "권한 enum",
}

_글자형 = ("CHAR", "TEXT", "CLOB", "JSON")


def 볼칸들(con: sqlite3.Connection) -> list[tuple[str, str]]:
    """이 DB 의 글자 칸 전부에서 제외칸을 뺀 것."""
    나온것 = []
    표들 = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master"
        " WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for 표 in 표들:
        for _cid, 칸, 형, *_ in con.execute(f"PRAGMA table_info({표})"):
            형 = (형 or "").upper()
            if (any(t in 형 for t in _글자형) or 형 == "") and (표, 칸) not in 제외칸:
                나온것.append((표, 칸))
    return 나온것


def 실명이있나(db_path: pathlib.Path) -> dict:
    """{칸 이름: 걸린 수}. 비면 깨끗한 것이다. 이름은 담지 않는다."""
    if not _anon.MAP_PATH.exists():
        return {}          # 대응표가 없는 컴퓨터 — 대조할 실명이 없다

    # 대응표가 깨졌으면(load_map 의 SystemExit) **그대로 멈춘다** —
    # 삼키면 게이트가 조용히 꺼진 채 통과한다 (fail-open). 빈 목록도
    # 통과가 아니다 — 센 것이 0이면 성공이 아니라 실패다 (11-3)
    names, phones, _장소 = _anon.load_map()
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
    # 연락처도 본다 — 사람 이름만 보는 검사는 연락처에 아무 말도 하지
    # 않았다 (11-2). 숫자 그대로와 3-4-4 표기 둘 다 잡는다
    for num, _ in phones:
        patterns.append(re.compile(rf"(?<!\d){re.escape(num)}(?!\d)"))
        if len(num) == 11:
            hy = f"{num[:3]}-{num[3:7]}-{num[7:]}"
            patterns.append(re.compile(rf"(?<!\d){re.escape(hy)}(?!\d)"))

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    걸림: dict[str, int] = {}
    try:
        for 표, 칸 in 볼칸들(con):
            수 = 0
            for (값,) in con.execute(f'SELECT "{칸}" FROM "{표}" WHERE "{칸}" IS NOT NULL'):
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
