"""2단계 — 업무 추가를 팝업으로 (CLAUDE.md 6-7 · 목업 C).

**엔드포인트 규약은 안 바뀐다** — `/board/add` 도 `/board/add/existing` 도
`/board/add/new` 도 그대로다. 바뀐 것은 **어떻게 여는가**와 **날짜를 무엇으로
고르는가** 둘이다. 그래서 여기서 재는 것도 그 둘과, 그 둘이 기대는 구조다.

| 무엇을 재나 | 어디 |
|---|---|
| 옛 주소가 그대로 살아 있고 조각 주소가 같은 몸통을 낸다 | `가` |
| 날짜 드롭다운이 사라지고 **같은 달력 부품**을 쓴다 | `나` |
| 여는 자리 둘 — 보드의 링크와 달력 날짜 칸의 「+」 | `다` |
| 팝업이 `body` 아래 뜨는 값을 `originOf` 가 안다 | `라` |
| 점검이 **아무것도 저장하지 않는다** (10장) | `마` |

화면에서 실제로 눌러 본 것은 보고 3~5장에 있다 — 여기는 그 구조가 다시
무너지지 않게 붙드는 자리다.
"""

from __future__ import annotations

import pathlib
import re

import datetime as dt

import pytest

from app import models
from tests.conftest import app_session

ROOT = pathlib.Path(__file__).resolve().parents[1]
조각 = (ROOT / "app" / "templates" / "partials" / "addpop.html").read_text(encoding="utf-8")
옛화면 = (ROOT / "app" / "templates" / "board_add.html").read_text(encoding="utf-8")
격자 = (ROOT / "app" / "templates" / "partials" / "calendar_grid.html").read_text(encoding="utf-8")
보드화면 = (ROOT / "app" / "templates" / "board.html").read_text(encoding="utf-8")
달력화면 = (ROOT / "app" / "templates" / "calendar.html").read_text(encoding="utf-8")
팝업JS = (ROOT / "app" / "static" / "js" / "board_add.js").read_text(encoding="utf-8")
드로어JS = (ROOT / "app" / "static" / "js" / "drawer.js").read_text(encoding="utf-8")
달력JS = (ROOT / "app" / "static" / "js" / "calendar.js").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
점검JS = (ROOT / "docs" / "checks" / "drawer.js").read_text(encoding="utf-8")
폰JS = (ROOT / "docs" / "checks" / "phone.js").read_text(encoding="utf-8")
라우터 = (ROOT / "app" / "routers" / "board.py").read_text(encoding="utf-8")


# ── 가. 옛 주소와 조각 주소가 **같은 몸통**을 낸다 ───────────────────

@pytest.fixture
def 회차(admin_client):
    """앱이 쓰는 그 엔진에 회차 하나 — `/board/add` 는 회차가 없으면 404 다."""
    with app_session() as db:
        r = models.Retreat(name="2026 여름수련회 Belong",
                           start_date=dt.date(2026, 7, 20), end_date=dt.date(2026, 7, 23))
        db.add(r)
        db.flush()
        db.add(models.Department(retreat_id=r.id, key="chongmu", name="1 총무팀", sort_order=0))
        db.commit()
        return r.id


def test70_a01_옛_주소는_그대로_살아_있다(회차, admin_client):
    """`/board/add` 는 규약이다 — 자바스크립트가 죽었을 때의 길이기도 하다."""
    page = admin_client.get("/board/add")
    assert page.status_code == 200
    assert "data-add-root" in page.text, "옛 화면이 팝업과 같은 몸통을 안 쓴다"


def test70_a02_조각_주소가_같은_몸통을_낸다(회차, admin_client):
    조각응답 = admin_client.get("/board/add/form")
    assert 조각응답.status_code == 200
    몸통 = 조각응답.text
    assert "data-add-root" in 몸통
    # 조각이므로 껍데기가 딸려 오면 안 된다 — 팝업 안에 사이드바가 들어간다
    assert "<html" not in 몸통.lower() and "sidenav" not in 몸통


def test70_a03_몸통을_만드는_곳은_하나다():
    """두 라우트가 저마다 후보를 모으면 한쪽에만 업무가 빠진다."""
    assert 라우터.count("def _add_form_context(") == 1
    assert 라우터.count("_add_form_context(db, user, retreat)") == 2


def test70_a04_구역_순서는_새_업무_만들기가_위다():
    자리 = [m.start() for m in re.finditer(r"<h3>(새 업무 만들기|라이브러리에서 넣기)</h3>", 조각)]
    이름 = re.findall(r"<h3>(새 업무 만들기|라이브러리에서 넣기)</h3>", 조각)
    assert 이름 == ["새 업무 만들기", "라이브러리에서 넣기"], f"구역 순서가 뒤집혔다: {이름}"
    assert len(자리) == 2


def test70_a05_옛_화면은_조각을_include_한다():
    """몸통을 두 벌로 적으면 한쪽에만 칸이 생긴다."""
    assert 'include "partials/addpop.html"' in 옛화면
    assert "라이브러리에서 넣기" not in 옛화면, "옛 화면이 몸통을 또 적고 있다"


# ── 나. 날짜 — 드롭다운을 걷고 **같은 달력 부품**을 쓴다 ─────────────

def test70_b01_날짜_드롭다운이_사라졌다():
    for 옛것 in ('id="nstart"', 'id="nend"'):
        assert 옛것 not in 조각, f"{옛것} 가 남아 있다 — 달력 부품으로 바꿨다"
    assert 'id="ndates"' in 조각 and 'id="ncalbtn"' in 조각


def test70_b02_비면_그렇다고_적는다():
    assert "날짜 없음 — 달력 버튼으로 고르기" in 조각


def test70_b03_달력을_새로_만들지_않는다():
    """`DatePick` 하나를 부른다 — 두 벌이면 고르는 차례가 갈린다 (4-9)."""
    assert "window.DatePick.open(" in 팝업JS
    for 만드는말 in ("dpgrid", "dpsave", "createElement('table')"):
        assert 만드는말 not in 팝업JS, f"팝업이 달력을 스스로 그리려 한다 ({만드는말})"


def test70_b04_팝업은_그_엔드포인트로_보낸다():
    """2단계가 정한 규약 — **여는 방식만 바뀌었지 저장 경로는 그대로다**(6-7).

    **날짜를 어떻게 읽는지는 여기서 안 본다.** 전에는 이 시험이
    「서버는 ISO 를 그대로 받는다」 였는데, 그 단언 둘이 3단계 뒷정리 뒤
    `test71_d03` 과 **글자까지 같아졌다** — 같은 사실이 두 곳이면 갈린다
    (2026-09-25 두 번째 검토). 날짜 쪽은 `tests/test_stage71.py` 가 지고,
    여기는 이 판이 실제로 붙든 것(저장 경로)만 짚는다.
    """
    assert "/board/add/new" in 팝업JS
    assert "/board/add/existing" in 팝업JS
    assert "/board/add/form" in 팝업JS, "몸통을 받아 가는 곳이 바뀌었다"


def test70_b05_까닭_글은_템플릿이_들고_JS_가_지우지_않는다():
    """끌 때 글자까지 지우면 다시 켰을 때 **빈 줄**이 뜬다 (실제로 그랬다)."""
    assert "업무 이름을 적어 주세요." in 조각
    assert "하위 업무는 상위 업무를 골라야 합니다." in 조각
    assert "업무 이름을 적어 주세요." not in 팝업JS, "같은 말을 JS 에 또 적었다"
    assert "if (typeof 글 === 'string') el.textContent = 글;" in 팝업JS


# ── 다. 여는 자리 둘 ─────────────────────────────────────────────────

def test70_c01_보드의_여는_자리는_href_를_남긴다():
    """자바스크립트가 죽었을 때의 길이다 — 달력 점의 `href` 와 같은 자리(4-13)."""
    m = re.search(r'<a class="addlink"[^>]*>', 보드화면)
    assert m, "보드에 여는 자리가 없다"
    assert 'href="/board/add"' in m.group(0) and "data-addpop" in m.group(0)


def test70_c02_달력_날짜_칸에_더하기가_있다():
    assert 격자.count("calplus") == 2, "넓은 화면과 좁은 목록 둘 다에 있어야 한다"
    assert "data-addpop-date=" in 격자
    # 이 달 밖 칸에는 안 단다 — 점도 거기엔 안 놓는다 (4-13)
    assert "{% if cell.in_month and user and not is_readonly(user) %}" in 격자


def test70_c03_격자를_그리는_두_길이_다_user_를_받는다():
    """조각만 `user` 를 안 넘기면 달을 넘긴 뒤에 「+」 가 통째로 사라진다."""
    달력라우터 = (ROOT / "app" / "routers" / "calendar.py").read_text(encoding="utf-8")
    assert '"partials/calendar_grid.html", {"cal": view, "user": user}' in 달력라우터


def test70_c04_여는_것은_위임으로_받는다():
    """달 격자는 통째로 갈아 끼워진다 — 칸마다 걸면 달을 넘긴 뒤에 죽는다."""
    assert "document.addEventListener('click', e => {" in 팝업JS
    assert "closest('[data-addpop]')" in 팝업JS


def test70_c05_달력은_보던_달을_잃지_않는다():
    """페이지를 다시 그리면 달·범위 칩·미완료만이 처음으로 돌아간다 (4-13)."""
    assert "window.업무추가.다시그린다 = () => {" in 달력JS
    assert "goMonth(g.dataset.month)" in 달력JS
    # 그 자리를 끼우려면 팝업 파일이 **먼저** 실려야 한다
    실린자리 = lambda 이름: 달력화면.index(f"static('js/{이름}')")
    assert 실린자리("board_add.js") < 실린자리("calendar.js")


# ── 라. `body` 아래 뜨는 것을 바깥 클릭 판정이 안다 ──────────────────

def test70_d01_originOf_가_팝업을_안다():
    """모르면 팝업을 만지는 순간 드로어가 닫힌다 — 달력 팝업이 실제로 그랬다."""
    assert "addpop: at('.addpop')," in 드로어JS
    닫는줄 = re.search(r"if \(어느쪽이든\('drawer'\)[^;]*\) return;", 드로어JS, re.S)
    assert 닫는줄 and "addpop" in 닫는줄.group(0)


def test70_d02_팝업은_바깥_클릭으로_안_닫힌다():
    """닫는 길은 × 와 Esc 둘이다. 바깥 클릭까지 넣으면 업무를 고르려고
    뒤의 목록을 누르는 순간 적던 것이 사라진다."""
    assert "el.querySelector('.apx').onclick = 닫는다;" in 팝업JS
    assert "e.key !== 'Escape'" in 팝업JS
    # **기간 달력이 떠 있으면 그쪽 차례다** — 둘 다 window 에서 받는다(커밋 전 검토 F6)
    assert "window.DatePick.isOpen()) return;" in 팝업JS
    assert "e.stopPropagation();" in 팝업JS


def test70_d03_모서리는_눈금_둘뿐이다():
    """목업의 10px 을 그대로 쓰면 한 화면에 4·8·10 이 함께 뜬다 (4-0)."""
    팝업CSS = re.search(r"\.addpop\{[^}]*\}", CSS)
    assert 팝업CSS and "var(--r-lg)" in 팝업CSS.group(0)
    assert "border-radius:10px" not in 팝업CSS.group(0)


def test70_d04_좁은_화면에서_폭이_줄어든다():
    """640 을 그대로 두면 휴대폰에서 가로가 잘린다."""
    팝업CSS = re.search(r"\.addpop\{[^}]*\}", CSS)
    assert "width:min(640px,calc(100vw - 16px))" in 팝업CSS.group(0)


def test70_d05_열_때_아래가_화면_밖으로_안_나간다():
    """목업의 「위 70px」 과 「최대 높이 = 화면 − 40」 은 낮은 창에서 함께
    성립하지 않는다 — 70 + (높이−40) 이 화면을 넘는다. 들어가면 70 을 그대로
    쓰고 안 들어갈 때만 올린다."""
    assert "Math.max(0, innerHeight - el.offsetHeight - 20)" in 팝업JS
    팝업CSS = re.search(r"\.addpop\{[^}]*\}", CSS)
    assert "max-height:calc(100vh - 40px)" in 팝업CSS.group(0)


# ── 마. 점검은 **아무것도 저장하지 않는다** (10장) ───────────────────

def test70_e01_점검은_라이브러리_추가를_누르지_않는다():
    """누르면 업무가 생기고 **그것은 지울 길이 없다** (0장).
    고른 수와 단추가 켜지는 것까지만 잰다."""
    구역 = 점검JS[점검JS.index("업무 추가 팝업 (6-7"):]
    구역 = 구역[: 구역.index("안 잰 것을 안 잰 것으로")]
    assert "#addExisting" in 구역, "그 단추를 아예 안 보면 켜지는지도 모른다"
    assert "addExisting').click()" not in 구역, "점검이 실제로 저장을 눌렀다"


def test70_e02_새_업무_만들기는_빈_채로만_누른다():
    구역 = 점검JS[점검JS.index("업무 추가 팝업 (6-7"):]
    구역 = 구역[: 구역.index("안 잰 것을 안 잰 것으로")]
    누름 = 구역.index("q('#addNew').click()")
    비움 = 구역.index("q('#ntitle').value = ''")
    assert 비움 < 누름, "이름을 채운 채로 눌렀다 — 업무가 생긴다"


def test70_e03_갈래_넷이_새로_생겼고_답은_하나씩이다():
    for 이름 in ("㉒ 업무 추가", "㉓ 업무 추가", "㉔ 업무 추가", "㉕ 달력 — 날짜 칸의 +"):
        assert f"{{갈래: '{이름}" in 점검JS, f"{이름} 갈래가 없다"
    # 갈래마다 기다리는 답은 하나여야 한다 (test19_s01 과 같은 규칙)
    for 조각글 in 점검JS.split("{갈래: '")[1:]:
        if "심는다:" not in 조각글[:3000]:
            continue                      # 고장 표가 아니라 진행 표시의 그 줄이다
        자리 = 조각글[: 조각글.index("심는다:")]
        assert len(re.findall(r"(?:나와야|건너뜀나와야|끝상태):", 자리)) == 1


def test70_e04_뒷정리가_팝업도_닫는다():
    """열린 채로 두면 **다음 갈래가 통째로 흔들린다** (2026-09-24 의 그 자리)."""
    뒷정리 = 점검JS[점검JS.index("const 뒷정리 = async () =>"):]
    뒷정리 = 뒷정리[: 뒷정리.index("const 자가시험")]
    assert "#addpop .apx" in 뒷정리, "뒷정리가 팝업을 안 닫는다"
    assert "남.push('업무 추가 팝업')" in 뒷정리, "닫혔는지 재지 않는다"


def test70_e05_휴대폰_폭은_폰_점검이_잰다():
    """넓은 창에서는 640 이 맞는 값이라 그쪽 점검이 재면 늘 통과한다."""
    assert "업무 추가 팝업이 이 폭에서 가로로 잘린다" in 폰JS
    assert "'.addpop{width:640px!important;left:0!important}'" in 폰JS


def test70_e06_갈래를_골라_돌_수_있고_골랐으면_말한다():
    """한 갈래가 10분까지 간다 — 새로 더한 갈래만 재는 길이 없으면
    한 판에 안 들어가고, 골랐다는 말이 없으면 「전부 쟀다」 로 읽힌다."""
    assert "window.__갈래고름" in 점검JS
    assert "고른갈래: 고름 || undefined" in 점검JS
    assert "const 잰갈래 = 돌갈래.length - 못심은갈래;" in 점검JS
