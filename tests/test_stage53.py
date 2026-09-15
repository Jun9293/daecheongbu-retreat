"""개발과 운영의 세션 쿠키 이름을 가른다 (CLAUDE.md 11-2 · 2026-09-15 사람이 정함).

쿠키는 포트가 아니라 호스트에 붙어서 같은 이름이면 같은 브라우저에서 한쪽에 로그인하는 순간 다른 쪽이 풀린다.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

from app import config

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test53_a01_개발_서버는_운영과_다른_쿠키_이름을_건다():
    bat = (ROOT / "scripts" / "devserve.bat").read_text(encoding="cp949")
    m = re.search(r"^set DCB_SESSION_COOKIE=(\S+)\s*$", bat, re.M)
    assert m, "devserve.bat 이 세션 쿠키 이름을 안 건다"
    assert m.group(1) != "dcb_session", "개발 쿠키 이름이 운영 기본값과 같다"
    # 서버를 띄우는 줄보다 앞에 걸려야 그 서버가 받는다
    assert bat.index(m.group(0)) < bat.index("uvicorn")


def test53_a02_환경변수가_있으면_그_이름_없으면_기본값(tmp_path):
    def 이름(extra: dict) -> str:
        env = {k: v for k, v in os.environ.items() if k != "DCB_SESSION_COOKIE"}
        env.update({"DCB_DATA_DIR": str(tmp_path), "DCB_SECRET_KEY": "test-only", **extra})
        return subprocess.check_output([sys.executable, "-c", "from app import config; print(config.SESSION_COOKIE)"],
                                       cwd=ROOT, env=env, text=True).strip()
    assert 이름({}) == "dcb_session", "운영 기본값이 바뀌면 로그인된 세션이 끊긴다"
    assert 이름({"DCB_SESSION_COOKIE": "other_cookie"}) == "other_cookie"


def test53_a03_쿠키_이름은_한_곳에서만_정한다():
    """set · delete · get 이 같은 이름을 쓰도록 — 글자로 적힌 쿠키 이름이 config 밖에 없다."""
    걸린 = [p for p in (ROOT / "app").rglob("*.py")
            if p.name != "config.py" and "dcb_session" in p.read_text(encoding="utf-8")]
    assert not 걸린, 걸린
    assert config.SESSION_COOKIE
