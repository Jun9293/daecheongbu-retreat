"""보드·달력의 주 영역(<main>)과 phone.js 의 본문 찾기 (2026-09-17 · 봐둘것 BE-a).

보드·달력에 `main` 이 없어 phone.js 가 두 화면에서 거짓으로 실패했고, 그 탓에
「본문의 링크가 덮여 있지 않은가」 가 한 번도 안 재졌다. 사람이 둘 다 고치기로 정했다 —
화면에 `main` 을 두고, 점검도 `main` 하나에만 기대지 않는다.
"""

from __future__ import annotations

import pathlib
import re

from tests.test_board_web import board_data  # noqa: F401 — 픽스처

ROOT = pathlib.Path(__file__).resolve().parent.parent
PHONE = (ROOT / "docs" / "checks" / "phone.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")


def _main_하나(page: str) -> str:
    """주 영역은 하나이고 드로어는 그 밖이다 — 드로어까지 감싸면 주 영역이 패널을 품는다."""
    assert page.count("<main") == 1 and page.count("</main>") == 1
    안 = page[page.index("<main"):page.index("</main>")]
    assert 'id="drawer"' not in 안 and 'id="drawer"' in page
    return 안


def test60_a01_보드의_주_영역이_간트와_좁은_목록을_함께_감싼다(admin_client, board_data):  # noqa: F811
    안 = _main_하나(admin_client.get("/board").text)
    # 목록만 main 으로 바꾸면 넓은 화면에서 주 영역이 숨은 것이 된다 — 둘 다 안에 있어야 한다
    assert 'id="board"' in 안 and 'id="mlist"' in 안 and 'class="toolbar"' in 안


def test60_a02_달력의_주_영역이_격자와_날짜없는_자리를_감싼다(admin_client, board_data):  # noqa: F811
    안 = _main_하나(admin_client.get("/calendar").text)
    assert 'class="calbar"' in 안 and 'id="calswap"' in 안


def test60_a03_주_영역이_body_의_세로_flex_를_물려받는다():
    # 안 물려받으면 간트·달력의 스크롤 자리(flex:1)가 늘지 않아 화면이 잘린다
    m = re.search(r"\.pgmain\{([^}]*)\}", CSS)
    assert m, ".pgmain 규칙이 없다"
    for 조각 in ("flex:1", "min-height:0", "display:flex", "flex-direction:column"):
        assert 조각 in m.group(1)


def test60_b01_phone_js_는_main_을_먼저_보고_없으면_본문_자리를_찾는다():
    m = re.search(r"const 본문후보 = \[([^\]]*)\]", PHONE)
    assert m, "본문후보 목록이 없다"
    후보 = re.findall(r"'([^']+)'", m.group(1))
    assert 후보[0] == "main" and "#mlist" in 후보 and "#calswap" in 후보
    # 판정이 그 목록을 쓰고, main 하나만 집는 옛 줄이 남지 않았다
    assert "본문후보.find(" in PHONE
    assert "document.querySelector('main')" not in PHONE


def test60_b02_본문_링크_고장은_고른_본문_어디에나_심긴다():
    # main 에만 심으면 main 이 없는 화면에서 자가시험이 늘 「못 심음」 이 된다
    assert "스타일('main a{pointer-events:none}')" not in PHONE
    assert "본문후보.map(q => q + ' a')" in PHONE
