"""자가진단 — 배포한 뒤 "왜 안 되지" 를 혼자 좁혀 보기 위한 것.

무엇이 문제인지 한국어로 말한다. 넷 중 하나라도 아니면 종료 코드 1.

    .venv\\Scripts\\python.exe scripts/healthcheck.py
    .venv\\Scripts\\python.exe scripts/healthcheck.py https://내-주소
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글·기호가 깨지지 않게 한다.
# 여기서 터지면 "무엇이 문제인지 말해주는 스크립트" 가 자기 때문에 죽는다.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

OK, BAD = "[정상]", "[문제]"


def check_db() -> tuple[bool, str]:
    try:
        from sqlalchemy import func, select

        from app.db import SessionLocal
        from app.models import Retreat, TaskLibrary

        with SessionLocal() as db:
            retreats = db.scalar(select(func.count()).select_from(Retreat))
            libraries = db.scalar(select(func.count()).select_from(TaskLibrary))
    except Exception as exc:                                     # noqa: BLE001
        return False, f"DB 를 열지 못했습니다 — {exc}"
    if not libraries:
        return False, "업무 라이브러리가 비어 있습니다. seed.py 를 한 번 돌려주세요."
    return True, f"DB 정상 — 회차 {retreats}개 · 업무 라이브러리 {libraries}건"


def check_vapid() -> tuple[bool, str]:
    try:
        from app.push import push_enabled
    except Exception as exc:                                     # noqa: BLE001
        return False, f"푸시 모듈을 불러오지 못했습니다 — {exc}"
    if not push_enabled():
        return False, (
            "VAPID 키가 준비되지 않아 푸시가 꺼져 있습니다. "
            "data/vapid_private.pem 을 확인하세요 (푸시를 아직 안 쓰신다면 넘어가도 됩니다)."
        )
    return True, "푸시 준비됨 — VAPID 키가 있습니다"


def check_admin() -> tuple[bool, str]:
    try:
        from sqlalchemy import select

        from app.db import SessionLocal
        from app.models import User

        with SessionLocal() as db:
            admins = list(
                db.scalars(select(User).where(User.role == "admin", User.is_active))
            )
    except Exception as exc:                                     # noqa: BLE001
        return False, f"계정을 확인하지 못했습니다 — {exc}"
    if not admins:
        return False, (
            "총무팀(관리자) 계정이 없습니다. 아래로 하나 만드세요:\n"
            '        python scripts/create_admin.py "이름" 01012345678'
        )
    return True, f"관리자 {len(admins)}명 — {', '.join(a.name for a in admins)}"


def check_tunnel(url: str | None) -> tuple[bool, str]:
    if not url:
        return True, "터널 주소를 넣지 않아 건너뜁니다 (주소를 인자로 주면 확인합니다)"
    try:
        import urllib.request

        request = urllib.request.Request(url.rstrip("/") + "/login", method="GET")
        with urllib.request.urlopen(request, timeout=10) as response:
            code = response.status
    except Exception as exc:                                     # noqa: BLE001
        return False, (
            f"바깥에서 {url} 에 닿지 않습니다 — {exc}\n"
            "        cloudflared 가 돌고 있는지, 주소가 맞는지 확인하세요."
        )
    if code != 200:
        return False, f"{url} 이 {code} 를 돌려줍니다. 앱이 떠 있는지 확인하세요."
    return True, f"바깥에서 {url} 에 닿습니다"


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else None
    checks = [
        ("데이터베이스", check_db()),
        ("웹 푸시(VAPID)", check_vapid()),
        ("관리자 계정", check_admin()),
        ("바깥에서 접속", check_tunnel(url)),
    ]

    print("대청부 수련회 시스템 — 자가진단\n")
    bad = 0
    for label, (ok, message) in checks:
        mark = OK if ok else BAD
        print(f"  {mark} {label}\n        {message}")
        if not ok:
            bad += 1
    print()
    if bad:
        print(f"{bad}가지가 아직 준비되지 않았습니다. 위의 안내대로 하나씩 맞춰주세요.")
        return 1
    print("전부 정상입니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
