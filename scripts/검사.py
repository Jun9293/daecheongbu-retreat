# -*- coding: utf-8 -*-
"""커밋 전에 도는 **글 검사** 전부 — 부르는 자리는 여기 하나다 (11-3).

11-3 1단계에는 사람이 하는 것도 남아 있습니다(`git status` 로 `data/`·
`testdata/`·`link.txt` 훑기 등). **「전부」 라고 넓게 말하면 문이 다
닫힌 것으로 읽히므로** 여기서 도는 것은 「글을 보는 검사」 라고
적습니다 — 검토-원칙 7 의 반대편입니다.

## 왜 하나로 모으는가

검사가 셋이 됐다(`check_names` · `check_stale` · `check_named`). 11-3 이
셋을 각각 이름으로 적어 두었는데, **넷째가 생기면 11-3 을 고쳐야 하고
안 고치면 그 검사만 조용히 안 돌게 됩니다.** 실제로 옛말 검사를 만든
판이 그 목록을 지시문마다 옮겨 적다가 하나를 빠뜨렸습니다.

**사람이 셋을 기억하지 않게 합니다.** 여기에 더하면 11-3 은 그대로입니다.

## 무엇을 도는가

| 검사 | 무엇을 잡나 |
|---|---|
| `check_names` | 실명·장소·연락처가 공개 저장소로 나가는 것 (11-2) |
| `check_stale` | **주장**이 낡은 것 — 사람이 적은 옛말 목록으로 (11-3) |
| `check_named` | **이름**이 낡은 것 — 목록에 기대지 않는 둘째 축 (11-3) |

**하나라도 0 이 아니면 전체가 0 이 아닙니다.** 그리고 **끝까지 다
돌립니다** — 첫 실패에서 멈추면 한 번에 하나씩만 알게 되어, 고치고
다시 돌리기를 되풀이하게 됩니다.

    .venv\\Scripts\\python.exe scripts/검사.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

여기 = pathlib.Path(__file__).resolve().parent
ROOT = 여기.parent

# **여기에 더하면 11-3 은 그대로다.** 그것이 이 파일의 이유다.
#
# `check_dev_db` 는 여기 없다 — 그건 devserve 앞의 입구이고 보는 것이
# 커밋 내용이 아니라 **개발 DB** 다(11-2). 커밋 문에 끼우면 「커밋할
# 것이 깨끗한데 개발 DB 때문에 빨갛다」 가 된다
검사들 = ("check_names", "check_stale", "check_named")


def 돌린다(이름: str) -> int:
    # **flush 한다.** 부모의 stdout 은 파이프·리다이렉트일 때 블록
    # 버퍼가 되고 자식은 그 fd 에 바로 쓴다 — 안 비우면 머리 셋이 맨
    # 뒤로 몰려 「check_names 는 아무 말도 안 했다」 로 읽힌다.
    # 11-3 이 이 결과를 보고에 적으라고 하는데, 보고에 붙일 때가 바로
    # 파이프로 넘기는 때다 (검토가 짚었다)
    print(f"\n━━━ {이름} ━━━", flush=True)
    r = subprocess.run([sys.executable, str(여기 / f"{이름}.py")], cwd=ROOT)
    return r.returncode


def main() -> int:
    결과 = {이름: 돌린다(이름) for 이름 in 검사들}
    print("\n━━━ 모아서 ━━━")
    for 이름, 값 in 결과.items():
        print(f"  {'통과' if 값 == 0 else '실패'}  {이름} (exit {값})")
    빨간것 = [이름 for 이름, 값 in 결과.items() if 값 != 0]
    if 빨간것:
        print(f"\n!! {len(빨간것)}개가 빨갛습니다: {' · '.join(빨간것)}")
        return 1
    print("\n전부 통과했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
