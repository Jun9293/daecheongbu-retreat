# -*- coding: utf-8 -*-
"""운영 DB 에 남은 테스트 시드 업무를 **실제로 지웁니다** (0장의 예외 · 2026-09-17 사람이 정함).

## 왜 지우는가

2026-08-29 에 개발용 시드(`seed.py` · 출처가 목업)가 그때 하나뿐인 DB 에 들어갔고, 그 DB 가 그대로
운영이 됐습니다. 그 가운데 **실제로 진행된 적이 없는 업무**가 라이브러리와 두 회차의 run 으로 남아
있습니다 — 진단은 `docs/봐둘것.md` BD-a(커밋 `d18a0c1`), 예외의 근거는 CLAUDE.md 0장입니다.
남겨 두면 6-2 자동 분류가 지어낸 「미실행」 을 판단 근거로 읽습니다(6-9 가 막은 것).

## 무엇을 지우나 — `대상` 한 곳

- **확정** — `seed_library_data.LIBRARY_ONLY` 여섯(라이브러리 97~102): 같은 커밋 · 같은 순간 · 같은 스크립트
- **출처 불명** — 시드 가운데 노션 제목과 부분도 안 겹치는 것(비교 규칙은 봐둘것 BD-a · 한글 · 영문 · 숫자만 남김)
- 그 라이브러리를 가리키는 **모든 run**(두 회차 모두) — 라이브러리를 지우면 run 이 함께 지워지므로(FK CASCADE)
  이 스크립트가 **먼저 run 을 이름 불러** 지웁니다

`대상` 의 id 마다 **시드였다는 흔적**(노션 id 없음 · `origin=history` · 시드가 돈 그 초에 생김)을 다시 봅니다.
하나라도 아니면 **아무것도 안 하고 멈춥니다** — id 가 다른 줄을 가리키게 된 DB 에서 돌면 안 됩니다.

## 걸린 것이 있으면 그 항목은 빼고 말합니다

지우기 직전에 대상마다 **걸린 것**을 셉니다. 하나라도 있으면 그 라이브러리(와 그 run)는 지울 목록에서
빠지고, 무엇 때문인지 id 와 함께 찍습니다 — 사람이 봅니다.

- run 에 걸린 것: 논의 · 논의 잇기 · 첨부 · 확인 요청 · 알림 기록 · 회의 항목 전환 · 따라온 논의 · 활동 기록 ·
  남는 run 의 선행 링크(`blocked_by_run_ids`)
- 라이브러리에 걸린 것: 라이브러리 활동 기록 · 업무 규칙 · 남는 라이브러리의 관련업무 · 선행 · **상위**(`parent_library_id` — 지우면 그 하위가
  말없이 최상위가 됩니다) · 초안 제출의 선택
- 뺀 항목의 하위가 대상이면 그 하위는 그대로 지울 수 있고, **뺀 항목을 상위로 둔 대상**은 없어지지 않으므로
  걸림이 아닙니다. 반대로 뺀 항목이 대상을 가리키면 그 대상도 빠집니다 — 끝까지 되풀이합니다

## 되돌릴 수 없으므로

기본은 **미리보기**이고 `--실행` 일 때만 지웁니다. `--실행` 에는 **사람이 본 미리보기의 id 목록**(`--기대`)을 함께 주고,
지금 고른 목록과 다르면 아무것도 안 합니다 — 그사이 걸림이 풀려 승인 안 된 줄이 끼는 것을 막습니다. 지울 것이 있을 때만 직전에 `VACUUM INTO` 사본을 뜨고,
세션이 여는 파일과 사본 뜰 파일이 다르면 아무것도 안 합니다(`재정들여오기.사본을_뜬다`). 지운 뒤 commit 전에
**DB 를 다시 세어** 계획과 다르면 되돌립니다. 지운 id 와 제목은 저장소 밖 `data/테스트시드삭제.real.md` 에 남습니다
(화면과 이 출력에는 id 와 수만).

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/테스트시드삭제.py            # 미리보기
    .venv\\Scripts\\python.exe scripts/테스트시드삭제.py --실행 --기대 <미리보기가 찍은 id>   # 실제로 지움
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
import json
import pathlib
import sys
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import text                                          # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from app import config                                               # noqa: E402
from app.db import SessionLocal                                      # noqa: E402
from app.models import ActivityLog                                   # noqa: E402
from scripts.비품들여오기 import 멈춤                                   # noqa: E402
from scripts.재정들여오기 import 사본을_뜬다                            # noqa: E402

# d18a0c1 의 진단 결과(봐둘것 BD-a). **값이 아니라 id 다** — 제목은 저장소에 안 적는다.
확정 = (97, 98, 99, 100, 101, 102)
출처불명 = (4, 5, 13, 17, 18, 19, 26, 31, 37, 44, 64, 65, 92, 94, 95, 96, 99, 100, 101, 102)
대상 = tuple(sorted(set(확정) | set(출처불명)))
# 시드가 돈 그 초(UTC · models._now) — 이 사이에 생기지 않은 줄은 시드가 아니다
시드때 = ("2026-08-29 14:00:36", "2026-08-29 14:00:38")

run걸림표 = (("논의", "discussion_entries", "run_id"),
            ("논의 잇기", "discussion_entry_runs", "run_id"),
            ("첨부", "task_attachments", "run_id"),
            ("확인 요청", "review_requests", "run_id"),
            ("알림 기록", "notification_logs", "run_id"),
            ("회의 항목 전환", "meeting_items", "converted_run_id"),
            ("따라온 논의", "discussion_entries", "carried_from_run_id"))


@dataclass
class 계획:
    지울lib: list[int] = field(default_factory=list)
    지울run: dict[int, list[int]] = field(default_factory=dict)      # lib → run id
    뺀것: dict[int, list[str]] = field(default_factory=dict)         # lib → 까닭
    없는것: list[int] = field(default_factory=list)                   # 이미 지워진 대상

    @property
    def run들(self) -> list[int]:
        return sorted(r for lib in self.지울lib for r in self.지울run[lib])


def _목록(값) -> set[int]:
    if not 값:
        return set()
    return set(json.loads(값) if isinstance(값, str) else 값)


def _in(ids) -> str:
    # 빈 목록을 NULL 로 두면 `not in (NULL)` 이 아무 줄도 안 돌려준다 — 없는 id 로 둔다
    return ",".join(str(int(i)) for i in ids) or "-1"


def 고른다(db: Session, 대상ids=대상) -> 계획:
    """아무것도 안 바꾼다. 미리보기와 실행이 같이 쓴다 — 두 벌이면 보여준 수와 지운 수가 갈린다."""
    q = lambda s: db.execute(text(s)).all()
    판 = 계획()
    줄 = {r[0]: r for r in q("select id, notion_page_id, origin, created_at from task_library "
                              f"where id in ({_in(대상ids)})")}
    판.없는것 = [i for i in 대상ids if i not in 줄]
    for i, nid, origin, 생김 in 줄.values():
        if nid or origin != "history" or not (시드때[0] <= str(생김) < 시드때[1]):
            raise 멈춤(f"라이브러리 {i} 가 시드였다는 흔적과 맞지 않습니다 — 아무것도 안 했습니다.")
    후보 = sorted(줄)
    run들 = {lib: [] for lib in 후보}
    for rid, lib in q(f"select id, library_id from task_runs where library_id in ({_in(후보)})"):
        run들[lib].append(rid)

    # run 에 걸린 것 — 지울 목록과 상관없이 정해진다
    걸림: dict[int, set[str]] = {lib: set() for lib in 후보}
    run의lib = {r: lib for lib, rs in run들.items() for r in rs}
    for 이름, 표, 칸 in run걸림표:
        for (r,) in q(f"select {칸} from {표} where {칸} in ({_in(run의lib)})"):
            걸림[run의lib[r]].add(이름)
    for (r,) in q(f"select target_id from activity_logs where target_type = 'task_run' "
                  f"and target_id in ({_in(run의lib)})"):
        걸림[run의lib[r]].add("활동 기록")
    for (lib,) in q(f"select target_id from activity_logs where target_type = 'task_library' "
                    f"and target_id in ({_in(후보)})"):
        걸림[lib].add("라이브러리 활동 기록")
    for (lib,) in q(f"select id from task_library where id in ({_in(후보)}) "
                    "and rules is not null and trim(rules) != ''"):
        걸림[lib].add("업무 규칙")
    for (값,) in q("select library_ids from draft_submissions"):
        for lib in _목록(값) & set(후보):
            걸림[lib].add("초안 제출")

    남은runs = q("select id, blocked_by_run_ids from task_runs")
    남은libs = q("select id, related_library_ids, prerequisite_library_ids, parent_library_id from task_library")
    지울 = {lib for lib in 후보 if not 걸림[lib]}
    while True:                      # 뺀 것이 대상을 가리키면 그 대상도 빠진다 — 더 안 바뀔 때까지
        지울run = {r for lib in 지울 for r in run들[lib]}
        새로 = set()
        for rid, b in 남은runs:
            if rid in 지울run:
                continue
            for r in _목록(b) & 지울run:
                걸림[run의lib[r]].add("남는 run 의 선행 링크"); 새로.add(run의lib[r])
        for lid, rel, pre, parent in 남은libs:
            if lid in 지울:
                continue
            for lib in _목록(rel) & 지울:
                걸림[lib].add("남는 라이브러리의 관련업무"); 새로.add(lib)
            for lib in _목록(pre) & 지울:
                걸림[lib].add("남는 라이브러리의 선행"); 새로.add(lib)
            if parent in 지울:
                걸림[parent].add("남는 라이브러리의 상위"); 새로.add(parent)
        if not 새로:
            break
        지울 -= 새로

    판.지울lib = sorted(지울)
    판.지울run = {lib: sorted(run들[lib]) for lib in 판.지울lib}
    판.뺀것 = {lib: sorted(걸림[lib]) for lib in 후보 if lib not in 지울}
    return 판


def 센다(db: Session, 지울lib, 지울run) -> dict:
    """DB 에서 다시 센다. **지울 것 밖**의 줄은 수와 id 합 · 산 수로 지문을 떠 전후가 같은지 본다."""
    one = lambda s: db.execute(text(s)).one()
    L, R = _in(지울lib), _in(지울run)
    return {
        "라이브러리": one("select count(*) from task_library")[0],
        "run": one("select count(*) from task_runs")[0],
        "노션 라이브러리": one("select count(*) from task_library where notion_page_id is not null")[0],
        "마법사 제안": one("select count(*) from task_library where origin = 'claude_suggestion'")[0],
        "대상 라이브러리 남음": one(f"select count(*) from task_library where id in ({L})")[0],
        "대상 run 남음": one(f"select count(*) from task_runs where id in ({R})")[0],
        "남길 라이브러리 지문": tuple(one(f"select count(*), coalesce(sum(id),0) from task_library where id not in ({L})")),
        "남길 run 지문": tuple(one("select count(*), coalesce(sum(id),0), coalesce(sum(included),0), "
                                 f"coalesce(sum(library_id),0) from task_runs where id not in ({R})")),
        "회차별 run": tuple(tuple(r) for r in db.execute(text(
            "select retreat_id, count(*), coalesce(sum(included),0) from task_runs group by retreat_id order by retreat_id")).all()),
    }


def 미리보기찍기(db: Session, 판: 계획) -> None:
    rs = 판.run들
    회차별 = db.execute(text(f"select retreat_id, included, count(*) from task_runs where id in ({_in(rs)}) "
                            "group by 1, 2 order by 1, 2")).all()
    print(f"대상 라이브러리 {len(판.지울lib) + len(판.뺀것) + len(판.없는것)} (확정 {len(확정)} · 출처 불명 {len(출처불명)} · 겹침 {len(set(확정) & set(출처불명))})")
    if 판.없는것:
        print(f"  이미 없는 대상 {len(판.없는것)}: {판.없는것}")
    print(f"지울 것: 라이브러리 {len(판.지울lib)} · run {len(rs)}")
    for retreat_id, inc, n in 회차별:
        print(f"  회차 {retreat_id} · {'산' if inc else '뺀'} run {n}")
    print(f"  라이브러리 id: {판.지울lib}")
    print(f"걸린 것이 있어 뺀 것: 라이브러리 {len(판.뺀것)} · run {sum(len(v) for v in _run수(db, 판.뺀것).values())}")
    for lib, 까닭 in 판.뺀것.items():
        print(f"  {lib}: {' · '.join(까닭)}")
    전 = 센다(db, 판.지울lib, rs)
    print(f"안 건드릴 것: 노션 라이브러리 {전['노션 라이브러리']} · 마법사 제안 {전['마법사 제안']} · "
          f"남길 라이브러리 {전['남길 라이브러리 지문'][0]} · 남길 run {전['남길 run 지문'][0]}")


def _run수(db: Session, 뺀것) -> dict:
    out = {lib: [] for lib in 뺀것}
    for rid, lib in db.execute(text(f"select id, library_id from task_runs where library_id in ({_in(뺀것)})")).all():
        out[lib].append(rid)
    return out


def 목록쓰기(db: Session, 판: 계획, 경로: pathlib.Path, *, 실행: bool) -> None:
    """저장소 밖(`data/*.real.*`)에만 쓴다 — 제목이 들어간다."""
    제목 = dict(db.execute(text(f"select id, title from task_library where id in ({_in(판.지울lib + list(판.뺀것))})")).all())
    줄 = [f"# 테스트 시드 삭제 — {'실행' if 실행 else '미리보기'} {dt.datetime.now():%Y-%m-%d %H:%M}", "",
         "봐둘것 BD-a · CLAUDE.md 0장 예외. 지운(미리보기면 지울) 라이브러리와 그 run.", ""]
    for lib in 판.지울lib:
        줄.append(f"- 라이브러리 {lib} · {제목.get(lib, '')} · run {판.지울run[lib]}")
    줄 += ["", "## 걸린 것이 있어 뺀 것", ""]
    for lib, 까닭 in 판.뺀것.items():
        줄.append(f"- 라이브러리 {lib} · {제목.get(lib, '')} · {' · '.join(까닭)}")
    경로.write_text("\n".join(줄) + "\n", encoding="utf-8")


def 지운다(db: Session, 판: 계획) -> None:
    """지우기만 한다 — commit 안 함."""
    db.execute(text(f"delete from task_runs where id in ({_in(판.run들)})"))
    db.execute(text(f"delete from task_library where id in ({_in(판.지울lib)})"))
    db.add(ActivityLog(actor_type="system", action="테스트시드_삭제", target_type="task_library",
                       summary=f"테스트 시드 삭제 — 라이브러리 {len(판.지울lib)} · run {len(판.run들)} (0장 예외 · 봐둘것 BD-a)",
                       after_value={"라이브러리": 판.지울lib, "run": 판.run들}))


def 돌린다(db: Session, *, 실행: bool, 기대: list[int] | None = None, 사본: bool = True,
          목록: pathlib.Path | None = None, 대상ids=대상) -> 계획:
    판 = 고른다(db, 대상ids)
    미리보기찍기(db, 판)
    목록 = 목록 or pathlib.Path(config.DATA_DIR) / "테스트시드삭제.real.md"
    if not 실행:
        목록쓰기(db, 판, 목록, 실행=False)
        print(f"바꾸지 않았습니다. 목록: {목록.parent.name}/{목록.name}")
        if 판.지울lib:
            print(f"실제로 지우려면 이 목록을 확인한 뒤: --실행 --기대 {','.join(map(str, 판.지울lib))}")
        else:
            print("지울 것이 없습니다 — 실행할 것도 없습니다.")
        return 판
    if not 판.지울lib:
        print("지울 것이 없습니다.")
        return 판
    # 사람이 본 미리보기와 견준다 — 같은 프로세스에서 두 번 고르는 것만으로는 그사이 풀린 걸림을 못 본다
    if 기대 is None:
        raise 멈춤("--실행 에는 --기대 로 사람이 본 미리보기의 라이브러리 id 를 줍니다 — 아무것도 안 했습니다.")
    if sorted(기대) != 판.지울lib:
        raise 멈춤(f"지금 지울 목록이 사람이 본 미리보기와 다릅니다(지금 {판.지울lib}) — 아무것도 안 했습니다.")
    전 = 센다(db, 판.지울lib, 판.run들)
    if 사본:
        사본을_뜬다()
    try:
        판2 = 고른다(db, 대상ids)                     # 지우기 직전에 걸린 것을 다시 센다 — 미리보기와 다르면 멈춘다
        if (판2.지울lib, 판2.run들) != (판.지울lib, 판.run들):
            raise 멈춤("지우기 직전에 다시 센 목록이 미리보기와 다릅니다 — 아무것도 안 했습니다.")
        지운다(db, 판)
        db.flush()
        지금 = 센다(db, 판.지울lib, 판.run들)
        바람 = {"라이브러리": 전["라이브러리"] - len(판.지울lib), "run": 전["run"] - len(판.run들),
              "대상 라이브러리 남음": 0, "대상 run 남음": 0}
        for k in ("노션 라이브러리", "마법사 제안", "남길 라이브러리 지문", "남길 run 지문"):
            바람[k] = 전[k]
        틀림 = [k for k, v in 바람.items() if 지금[k] != v]
        if 틀림:
            raise 멈춤(f"지운 뒤 다시 센 수가 계획과 다릅니다({' · '.join(틀림)}) — 되돌렸습니다.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    목록쓰기(db, 판, 목록, 실행=True)
    print("지웠습니다 (건수만):")
    for k, v in 센다(db, 판.지울lib, 판.run들).items():
        print(f"  {k}: {v}")
    return 판


def main() -> int:
    ap = argparse.ArgumentParser(description="운영 DB 에 남은 테스트 시드 업무를 지웁니다 (0장 예외).",
                                 epilog="기본은 미리보기입니다. 실제로 지우려면 --실행 을 붙이세요.")
    ap.add_argument("--실행", action="store_true")
    ap.add_argument("--기대", default=None, help="미리보기가 찍은 지울 라이브러리 id (쉼표로)")
    args = ap.parse_args()
    기대 = None if getattr(args, "기대") is None else [int(x) for x in getattr(args, "기대").split(",") if x.strip()]
    with SessionLocal() as db:
        try:
            돌린다(db, 실행=getattr(args, "실행"), 기대=기대)
            return 0
        except 멈춤 as e:
            print(f"!! {e}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
