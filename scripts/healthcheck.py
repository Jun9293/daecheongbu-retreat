"""자가진단 — 배포한 뒤 "왜 안 되지" 를 혼자 좁혀 보기 위한 것.

무엇이 문제인지 한국어로 말한다. 하나라도 아니면 종료 코드 1.

    .venv\\Scripts\\python.exe scripts/healthcheck.py

주소를 안 주면 `DCB_BASE_URL`(없으면 config 기본값)을 씁니다.
다른 주소를 보려면 뒤에 붙이세요.
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

from app import config                                           # noqa: E402

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


def check_secret_key() -> tuple[bool, str]:
    """세션 키가 고정인가 — 재시작해도 같은 값이 나오는가.

    이것이 흔들리면 증상은 "앱을 재시작할 때마다 로그인이 풀린다" 이고,
    다른 곳 어디에도 표시가 나지 않는다. 그래서 따로 물어본다.
    """
    try:
        from app.config import (
            SECRET_KEY_FINGERPRINT,
            SECRET_KEY_PATH,
            SECRET_KEY_SOURCE,
            secret_key_fingerprint,
        )
    except Exception as exc:                                     # noqa: BLE001
        return False, f"세션 키를 확인하지 못했습니다 — {exc}"

    import os

    if os.environ.get("DCB_SECRET_KEY"):
        return True, (
            f"환경변수로 고정돼 있습니다 (지문 {SECRET_KEY_FINGERPRINT}).\n"
            "        이 환경변수가 없어지면 전원이 로그아웃되니 함께 관리하세요."
        )

    if not SECRET_KEY_PATH.exists():
        return False, (
            f"세션 키 파일이 없습니다: {SECRET_KEY_PATH}\n"
            "        재시작할 때마다 새 키가 만들어져 전원이 로그아웃됩니다."
        )

    # 파일을 다시 읽어 같은 값이 나오는지 — 재시작을 흉내 낸다
    try:
        again = SECRET_KEY_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:                                       # noqa: BLE001
        return False, (
            f"세션 키 파일을 읽지 못합니다: {SECRET_KEY_PATH}\n"
            f"        {exc}\n"
            "        권한을 확인하세요. 못 읽으면 매번 새 키가 만들어집니다."
        )
    if not again:
        return False, (
            f"세션 키 파일이 비어 있습니다: {SECRET_KEY_PATH}\n"
            "        지우고 앱을 한 번 켜면 새로 만듭니다 (한 번은 로그아웃됩니다)."
        )
    if secret_key_fingerprint(again) != SECRET_KEY_FINGERPRINT:
        return False, (
            "지금 쓰는 키와 파일의 키가 다릅니다.\n"
            f"        {SECRET_KEY_SOURCE}\n"
            "        재시작하면 로그인이 풀립니다."
        )

    # 쓸 수 있는지도 본다 — 지금은 읽히지만 다음에 못 쓰면 그때 조용히 바뀐다
    writable = os.access(SECRET_KEY_PATH, os.W_OK)
    note = "" if writable else (
        "\n        ! 이 파일에 쓸 수 없습니다. 권한을 확인해두세요."
    )
    return True, (
        f"고정돼 있습니다 — {SECRET_KEY_PATH.name} · 지문 {SECRET_KEY_FINGERPRINT}\n"
        "        재시작한 뒤 이 지문이 같으면 로그인이 유지됩니다." + note
    )


def folder_size(path: pathlib.Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for one in path.rglob("*"):
        try:
            if one.is_file():
                total += one.stat().st_size
        except OSError:
            continue
    return total


def check_disk() -> tuple[bool, str]:
    """디스크가 조용히 차지 않게 한다 (CLAUDE.md 4-9).

    첨부 상한을 200MB 로 올린 뒤로 이것이 현실이 됐다. 지금까지는 찰 때까지
    받다가 **어느 날 아무 설명 없이** 실패했다 — 되짚을 근거가 화면 어디에도
    없는 종류의 실패다. 거절이 시작되기 전에 여기서 먼저 말한다.
    """
    try:
        import shutil

        from app.config import (
            DISK_FREE_FLOOR_BYTES,
            DISK_FREE_WARN_BYTES,
            UPLOAD_DIR,
        )

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(UPLOAD_DIR)
        used = folder_size(UPLOAD_DIR)
        backups = folder_size(config.DATA_DIR / "backups")
    except Exception as exc:                                     # noqa: BLE001
        return False, f"디스크를 확인하지 못했습니다 — {exc}"

    def mb(size: int) -> str:
        if size >= 1024 ** 3:
            return f"{size / 1024 ** 3:,.1f}GB"
        return f"{size / 1024 ** 2:,.0f}MB"

    detail = (
        f"남은 공간 {mb(usage.free)} / 전체 {mb(usage.total)}\n"
        f"        올라온 파일 {mb(used)} · 백업 {mb(backups)}"
    )

    if usage.free < DISK_FREE_FLOOR_BYTES:
        return False, (
            f"{detail}\n"
            f"        여유가 {mb(DISK_FREE_FLOOR_BYTES)} 아래입니다 — "
            "**지금 파일을 올리면 거절됩니다.**\n"
            "        data/backups 의 오래된 것을 지우거나 다른 곳으로 옮기세요."
        )
    if usage.free < DISK_FREE_WARN_BYTES:
        return False, (
            f"{detail}\n"
            f"        여유가 {mb(DISK_FREE_WARN_BYTES)} 아래입니다. "
            f"{mb(DISK_FREE_FLOOR_BYTES)} 밑으로 내려가면 올리기가 막힙니다.\n"
            "        지금 치워 두면 막히기 전에 끝납니다."
        )
    return True, detail


def check_admin() -> tuple[bool, str]:
    """관리자 계정이 있는가, 그리고 **같은 이름이 여럿이지는 않은가.**

    중복은 조용한 문제가 아니다 — 총무팀 에스컬레이션이 admin 전원에게 가므로
    같은 사람에게 알림이 여러 번 가고, 담당자를 고를 때 같은 이름이 여럿 뜬다.
    예전에는 이 상태에서 [정상] 이 떴다. 그래서 따로 센다.
    """
    try:
        from collections import Counter

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
            '        python scripts/create_admin.py "이름" <연락처>'
        )

    counted = Counter(a.name.strip() for a in admins)
    listed = ", ".join(
        f"{name}({n})" if n > 1 else name for name, n in counted.most_common()
    )
    duplicated = [name for name, n in counted.items() if n > 1]

    if duplicated:
        return False, (
            f"관리자 {len(admins)}명 — {listed}\n"
            "        같은 이름이 여럿입니다. scripts/merge_users.py 로 확인하세요.\n"
            "        중복 계정에는 알림이 그 수만큼 갑니다."
        )
    return True, f"관리자 {len(admins)}명 — {listed}"


# Cloudflare 는 봇으로 보이는 요청을 앞단에서 막는다. urllib 의 기본 헤더
# (`Python-urllib/3.x`) 로 가면 앱까지 닿지도 못하고 403 이 돌아오는데,
# 같은 주소를 브라우저로 열면 멀쩡하다 — 자가진단이 멀쩡한 서버를 문제라고
# 말하는 셈이다. 일반 브라우저와 같은 User-Agent 로 물어본다.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def check_tunnel(url: str | None) -> tuple[bool, str]:
    if not url:
        return True, "터널 주소를 넣지 않아 건너뜁니다 (주소를 인자로 주면 확인합니다)"
    try:
        import urllib.request

        request = urllib.request.Request(
            url.rstrip("/") + "/login",
            method="GET",
            headers={
                "User-Agent": BROWSER_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            code = response.status
    except Exception as exc:                                     # noqa: BLE001
        extra = ""
        if "403" in str(exc):
            extra = (
                "\n        403 이면 Cloudflare 가 이 요청을 앞에서 막은 것입니다 — "
                "브라우저로 열어 확인해보세요."
            )
        return False, (
            f"바깥에서 {url} 에 닿지 않습니다 — {exc}\n"
            "        cloudflared 가 돌고 있는지, 주소가 맞는지 확인하세요." + extra
        )
    if code != 200:
        return False, f"{url} 이 {code} 를 돌려줍니다. 앱이 떠 있는지 확인하세요."
    return True, f"바깥에서 {url} 에 닿습니다"


def main() -> int:
    # 주소를 손으로 적게 하지 않는다 — 초대 링크와 같은 곳에서 가져온다
    url = sys.argv[1] if len(sys.argv) > 1 else config.BASE_URL
    checks = [
        ("데이터베이스", check_db()),
        ("웹 푸시(VAPID)", check_vapid()),
        ("세션 키가 고정인가", check_secret_key()),
        ("디스크 여유", check_disk()),
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
