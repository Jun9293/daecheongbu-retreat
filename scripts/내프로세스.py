"""멈출 프로세스를 고른다 — **작업 폴더가 이 저장소 안인 것만** (CLAUDE.md 11-3).

## 왜 있나

2026-09-13 에 이 창이 고치기 전 코드로 돌던 제 시험을 멈추려고, 명령줄에
`-m pytest` 가 든 프로세스를 **기계 전체에서** 골라 멈췄습니다. 다른 프로젝트
창의 pytest 와 셸까지 함께 멈췄습니다(봐둘것 AZ-e). 같은 날 앞머리의 사고
(시험이 운영 DB 를 비움)와 **같은 모양**입니다 — 내 것만 골라야 하는데 범위를
안 좁혔습니다. conftest 가 「이 DB 가 시험용 임시 폴더 안인가」 를 보게 한 것처럼,
여기서는 **「이 프로세스의 작업 폴더가 이 저장소 안인가」** 를 봅니다.

## 무엇으로 가르나

명령줄 무늬는 **고르는** 데만 쓰고, **가르는** 것은 작업 폴더(cwd)입니다.
실행 파일 경로로 가르지 않습니다 — 이 저장소의 `.venv` 로 다른 폴더(worktree)에서
도는 시험도 있었고, 그 반대도 됩니다. 작업 폴더를 못 읽는 프로세스(권한)는
**내 것이 아닌 쪽**에 둡니다 — 모르는 것을 멈추는 쪽으로 틀리면 되돌릴 수 없습니다.

**이 도구 자신과 그것을 부른 셸·런처는 뺍니다** — 무늬가 그 명령줄에도 들어 있기 때문입니다.
**이 저장소 안에서 다른 창이 도는 것은 못 가릅니다** — 작업 폴더가 같기 때문입니다.
그래서 멈추기 전에 고른 것을 늘 찍습니다.

    .venv\\Scripts\\python.exe scripts/내프로세스.py "-m pytest"          # 고르기만
    .venv\\Scripts\\python.exe scripts/내프로세스.py "-m pytest" --멈춤   # 고른 것만 멈춘다
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import psutil

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _안인가(폴더: str | None, 뿌리: pathlib.Path) -> bool:
    if not 폴더:
        return False
    try:
        return pathlib.Path(폴더).resolve().is_relative_to(뿌리)
    except (OSError, ValueError):
        return False


def _나와조상() -> set[int]:
    """이 도구 자신과 그것을 부른 쪽 전부 — 셸 · `.venv` 런처 · 그 위.

    **무늬는 명령줄 인자로 들어가므로 부른 쪽 명령줄에 늘 들어 있고, 그 셸의 작업
    폴더도 이 저장소다.** 빼지 않으면 `--멈춤` 이 그 명령을 친 셸과 런처를 멈춘다 —
    커밋 전 검토가 무늬 하나로 돌려 셸 셋과 런처가 「이 저장소 안」 으로 뜨는 것을 봤다.
    """
    나 = psutil.Process()
    return {나.pid} | {p.pid for p in 나.parents()}


def 훑는다(무늬: str) -> list[dict]:
    """명령줄에 무늬가 든 프로세스 **전부** — 가르기 전의 목록(자기와 조상은 뺀다)."""
    if not 무늬.strip():
        raise ValueError("무늬가 비었습니다 — 빈 무늬는 기계의 모든 프로세스를 고릅니다")
    뺄것 = _나와조상()
    나온것 = []
    for p in psutil.process_iter(["pid", "cmdline"]):
        if p.info["pid"] in 뺄것:
            continue
        명령줄 = " ".join(p.info["cmdline"] or [])
        if 무늬 not in 명령줄:
            continue
        try:
            폴더 = p.cwd()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            폴더 = None
        # 훑을 때의 Process 를 함께 넘긴다 — 멈출 때 PID 로 다시 만들면 그사이 그 PID 가
        # 다른 프로세스로 다시 쓰였을 때 엉뚱한 것을 멈춘다(psutil 이 만든 때를 견준다)
        나온것.append({"pid": p.info["pid"], "cwd": 폴더, "cmdline": 명령줄, "proc": p})
    return 나온것


def 고른다(무늬: str, 뿌리: pathlib.Path = ROOT) -> tuple[list[dict], list[dict]]:
    """(내 것, 내 것이 아닌 것) — 작업 폴더가 `뿌리` 안이면 내 것."""
    뿌리 = pathlib.Path(뿌리).resolve()
    내것, 남의것 = [], []
    for 줄 in 훑는다(무늬):
        (내것 if _안인가(줄["cwd"], 뿌리) else 남의것).append(줄)
    return 내것, 남의것


def 멈춘다(줄들: list[dict], 기다림: float = 5.0) -> list[int]:
    """고른 PID 만 멈춘다. 멈춘 PID 를 돌려준다."""
    procs = []
    for 줄 in 줄들:
        try:
            p = 줄.get("proc") or psutil.Process(줄["pid"])
            p.terminate()
            procs.append(p)
        except psutil.NoSuchProcess:
            continue
    _, 남음 = psutil.wait_procs(procs, timeout=기다림)
    for p in 남음:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    return [p.pid for p in procs]


def main() -> int:
    ap = argparse.ArgumentParser(description="작업 폴더가 이 저장소 안인 프로세스만 고르고 멈춘다")
    ap.add_argument("무늬", help="명령줄에 들어 있는 글자 (빈 값은 거절)")
    ap.add_argument("--멈춤", action="store_true", help="고른 것만 멈춘다")
    a = ap.parse_args()
    내것, 남의것 = 고른다(a.무늬)
    print(f"이 저장소 안 ({ROOT}) — {len(내것)}개")
    for 줄 in 내것:
        print(f"  {줄['pid']:>6}  {줄['cmdline'][:120]}")
    print(f"밖이거나 작업 폴더를 못 읽음 — {len(남의것)}개 (건드리지 않습니다)")
    for 줄 in 남의것:
        print(f"  {줄['pid']:>6}  {줄['cwd'] or '(못 읽음)'}")
    if a.멈춤:
        멈춘것 = 멈춘다(내것)
        print(f"멈췄습니다: {멈춘것 or '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
