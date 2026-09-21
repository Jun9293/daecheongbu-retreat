# -*- coding: utf-8 -*-
"""**사람이 로그인해 준 창 없이** 화면을 그려 본다 (CLAUDE.md 11-2 · 11-3 2단계).

로그인을 안 하는 것이 아니다 — 아래 조건 둘을 채운 자리에서 **스스로**
들어간다. 11-2 가 막는 것은 「도는 서버의 로그인 칸에 값을 넣는 것」 이다.

**왜 이것이 규칙 안인가.** 11-2 는 「이 창은 로그인 칸에 비밀번호를 넣지
않는다 — 운영이든 개발이든」 이라고 정하고, 대상이 아닌 것을 **조건 둘**로
가른다 — ① 앱을 **그 자리에서 만들고**(도는 서버에 안 붙고) ② 값이
**저장소에 적힌 지어낸 것**이면 대상이 아니다. 이 스크립트가 그 둘을 함께
만족한다:

① `TestClient` 로 앱을 이 프로세스 안에서 만든다. 8000(운영)에도
   8001(개발)에도 붙지 않는다.
② 아래 `지어낸비번` 은 **이 파일에 평문으로 적힌 개발 전용 고정값**이다.
   운영과 아무 상관이 없다 — 운영 계정의 비밀번호가 아니고, 운영 DB 를
   열지도 않는다. 시드 사본에 이 값을 **덮어쓴 뒤** 그것으로 들어간다.
   `tests/conftest.py` 의 `login_as` 와 같은 자리다.

**운영은 열지 않는다.** 여는 것은 개발 시드(`%TEMP%\\dcb-dev\\app.db`)의
**사본**이고, 사본은 임시 폴더에 만든 뒤 그대로 둔다(원본을 안 건드린다).
운영 경로를 가리키면 아무것도 안 하고 멈춘다.

**CSS 는 도는 서버에서 받는다.** 뽑은 HTML 의 `/static` 을 `--정적` 주소로
바꿔 두므로, **방금 재시작한 그 서버가 내려 주는 파일**로 화면이 그려진다 —
11-3 2단계의 「돌고 있는 서버에서 확인한 것만 확인」 을 지키는 자리다.

    .venv\\Scripts\\python.exe scripts\\화면확인용렌더.py --나갈곳 data\\화면.real.d
    .venv\\Scripts\\python.exe scripts\\화면확인용렌더.py --나갈곳 data\\화면.real.d --길 /budget /expenses

나온 HTML 은 정적 파일이라 아무 정적 서버로나 열어 보면 된다.
**JS 가 서버를 부르는 자리(드로어 · 상태 메뉴 · 달력 달 넘기기)는 안 돈다** —
그것까지 보려면 사람이 로그인한 창이 필요하다.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

# **개발 전용 고정값.** 운영과 무관하고 저장소에 적혀 있다 — 11-2 의 조건 ②.
지어낸비번 = "화면확인용-개발전용-1234"
지어낸아이디머리 = "화면확인용"

기본길 = [
    ("홈", "/"),
    ("목록", "/tasks"),
    ("예산", "/budget"),
    ("지출", "/expenses"),
    ("보드", "/board"),
    ("달력", "/calendar"),
]


def 운영경로인가(p: pathlib.Path) -> bool:
    """`data/` 아래면 운영이다 — `seed.py` 의 그 판단과 같은 잣대."""
    try:
        return p.resolve().is_relative_to((ROOT / "data").resolve())
    except (OSError, ValueError):
        return False


def 시드경로() -> pathlib.Path:
    """`scripts/devserve.bat` 이 쓰는 개발 데이터 폴더."""
    return pathlib.Path(os.environ.get("TEMP", "")) / "dcb-dev" / "app.db"


def 사본을연다(시드: pathlib.Path) -> pathlib.Path:
    if 운영경로인가(시드):
        raise SystemExit(f"운영 데이터 폴더를 가리킵니다 — 아무것도 안 합니다: {시드}")
    if not 시드.exists():
        raise SystemExit(
            f"개발 시드가 없습니다: {시드}\n"
            "  scripts\\devserve.bat 을 한 번 돌리거나 seed.py 로 만드세요."
        )
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="dcb-render-"))
    # **파일 복사가 아니라 `VACUUM INTO` 다** (11-2) — 개발 서버가 같은 파일을
    # 쓰는 중이면 반쯤 쓰인 페이지가 섞이고, 그 파일은 **열어 보기 전까지
    # 멀쩡해 보인다.** 렌더라 손해는 작지만 규칙이 이미 글로 있다
    with sqlite3.connect(시드) as con:
        con.execute("VACUUM INTO ?", (str(tmp / "render.db"),))
    return tmp


def 문을연다(db, 로그인, User):
    """시드에 있는 계정 하나에 **이 파일의 지어낸 값**을 덮어쓰고 그 아이디를 돌려준다."""
    사람 = db.query(User).filter(User.role == "admin").first() or db.query(User).first()
    if 사람 is None:
        raise SystemExit("시드에 계정이 하나도 없습니다")
    사람.login_id = f"{지어낸아이디머리}{사람.id}"
    로그인.비밀번호를정한다(db, 사람, 지어낸비번)
    사람.must_change_password = False
    db.commit()
    return 사람.login_id


def 게이트를지난다(폴더: pathlib.Path) -> None:
    """`check_dev_db` 를 사본에 대고 한 번 돌린다.

    **스크린샷을 만드는 길이 둘이 됐다.** `devserve.bat` 은 서버를 띄우기 전에
    그 검사를 부르는데, 이 스크립트는 같은 개발 DB 를 열어 화면 HTML 을 만드는
    둘째 길이다 — 안 걸면 「…할 때만」 규칙이 그 '언제' 가 아닌 때에 뚫린다
    (11-2 · 다시 보기가 짚었다).
    """
    import subprocess

    풀 = dict(os.environ, DCB_DATA_DIR=str(폴더))
    난것 = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_dev_db.py")],
                        env=풀, capture_output=True, text=True, errors="replace")
    if 난것.returncode != 0:
        print(난것.stdout)
        raise SystemExit("개발 DB 검사에 걸렸습니다 — 화면을 그리지 않습니다 (11-2)")


def 돌린다(나갈곳: pathlib.Path, 길들, 정적: str) -> int:
    tmp = 사본을연다(시드경로())
    게이트를지난다(tmp)
    os.environ["DCB_DATABASE_URL"] = f"sqlite:///{tmp / 'render.db'}"
    os.environ["DCB_DATA_DIR"] = str(tmp)
    os.environ["DCB_SECRET_KEY"] = "화면확인용-개발전용-서명키"
    sys.path.insert(0, str(ROOT))

    from fastapi.testclient import TestClient

    from app.db import SessionLocal, engine
    from app.domain import login as 로그인
    from app.main import app
    from app.models import User

    with SessionLocal() as db:
        아이디 = 문을연다(db, 로그인, User)

    나갈곳.mkdir(parents=True, exist_ok=True)
    탈 = 0
    with TestClient(app) as c:
        r = c.post("/login", data={"login_id": 아이디, "password": 지어낸비번},
                   follow_redirects=False)
        if r.status_code != 303:
            raise SystemExit(f"로그인이 안 됩니다: {r.status_code}")
        for 이름, 길 in 길들:
            res = c.get(길)
            html = res.text.replace('href="/static/', f'href="{정적}/static/')
            html = html.replace('src="/static/', f'src="{정적}/static/')
            (나갈곳 / f"{이름}.html").write_text(html, encoding="utf-8")
            표 = "OK" if res.status_code == 200 else f"!! {res.status_code}"
            if res.status_code != 200:
                탈 += 1
            print(f"  {이름:6} {표:6} {len(html):>8,}자")
    print(f"나간 곳: {나갈곳}")
    # **사본을 남기지 않는다.** 개발 DB 에 실명이 있던 날이면 그것이 몇 벌씩
    # %TEMP% 에 쌓인다 — 게이트가 막는 그 자료가 게이트 뒤에 남는 꼴이다
    # (다시 보기가 아홉 벌을 세어 짚었다). VAPID 키도 같이 사라진다.
    # **연결을 먼저 닫는다** — 윈도우는 열린 파일을 안 지워 주고,
    # `ignore_errors` 로 덮으면 「지웠습니다」 가 거짓말이 된다
    engine.dispose()
    shutil.rmtree(tmp, ignore_errors=True)
    if tmp.exists():
        print(f"!! DB 사본을 못 지웠습니다 — 직접 지우세요: {tmp}")
    else:
        print("DB 사본은 지웠습니다 (원본은 안 건드렸습니다)")
    return 탈


def main() -> int:
    ap = argparse.ArgumentParser(description="사람이 로그인해 준 창 없이 화면을 그려 본다 (11-2)")
    ap.add_argument("--나갈곳", default="data/화면.real.d",
                    help="HTML 을 쓸 폴더. 기본 이름은 `data/*.real.*` 라 gitignore 가 막는다")
    ap.add_argument("--길", nargs="*", default=None,
                    help="그릴 주소들. 안 주면 홈 → 목록 → 예산 → 지출 → 보드 → 달력")
    ap.add_argument("--정적", default="http://127.0.0.1:8000",
                    help="정적 파일을 받아 올 곳 — **도는 서버**여야 11-3 2단계가 된다")
    a = ap.parse_args()
    길들 = [(x.strip("/").replace("/", "_") or "홈", x) for x in a.길] if a.길 else 기본길
    return 돌린다(pathlib.Path(a.나갈곳), 길들, a.정적.rstrip("/"))


if __name__ == "__main__":
    raise SystemExit(main())
