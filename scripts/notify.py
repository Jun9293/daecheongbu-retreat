"""하루 한 번 알림 묶음을 보낸다 (CLAUDE.md 4-11).

작업 스케줄러가 아침에 이 파일을 부른다. 스케줄러를 앱 안에 넣지 않는 이유는
앱이 시간을 재기 시작하면 껐다 켤 때마다 동작이 달라지기 때문이다.

    .venv\\Scripts\\python.exe scripts/notify.py
    .venv\\Scripts\\python.exe scripts/notify.py --preview   (보내지 않고 보기만)
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글·기호가 깨지지 않게 한다.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, init_db                         # noqa: E402
from app.domain import notify                                    # noqa: E402
from app.push import push_enabled                                # noqa: E402


def main() -> int:
    preview = "--preview" in sys.argv
    init_db()

    with SessionLocal() as db:
        if preview:
            digests = notify.build_digests(db)
            if not digests:
                print("오늘 보낼 것이 없습니다. (없으면 보내지 않습니다)")
                return 0
            print(f"오늘 {len(digests)}명에게 "
                  f"{sum(len(d.items) for d in digests)}건 — 보내지는 않았습니다.\n")
            for digest in digests:
                print(f"[{digest.user_name}] {digest.title()}")
                for line in digest.body().splitlines():
                    print(f"   {line}")
                print()
            return 0

        if not push_enabled():
            print("VAPID 키가 없어 푸시가 꺼져 있습니다. 아무것도 보내지 않았습니다.")
            return 1

        result = notify.run_digests(db)

    if not result["recipients"]:
        print("오늘 보낼 것이 없습니다.")
        return 0
    print(f"{result['recipients']}명 중 {result['sent']}명에게 보냈습니다 "
          f"({result['items']}건).")
    if result["skipped"]:
        print(f"  {result['skipped']}명은 보낼 곳이 없어 기록하지 않았습니다 "
              "— 내일 다시 후보가 됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
