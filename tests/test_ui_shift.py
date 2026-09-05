"""UI 전환 (CLAUDE.md 4장 UI 방향) · 배포 안내 · 자가진단. 수용 기준 1~7, 15~17.

화면이 실제로 어떻게 보이는지는 `docs/checks/drawer.js` 를 브라우저에서 돌려
확인한다. 여기서 지키는 것은 **글로 못 박은 규칙이 파일에서 지워지지 않았는가** 다 —
목업이 옛 화면으로 남거나, 상단 탭 줄이 슬그머니 돌아오거나, 부서 색이 다시 면을
채우기 시작하면 여기서 걸린다.

네트워크에 나가지 않는다.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOCKUPS = ROOT / "docs" / "mockups"
CSS = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
SHELL = (ROOT / "app" / "templates" / "retreat_base.html").read_text(encoding="utf-8")
BOARD = (ROOT / "app" / "templates" / "board.html").read_text(encoding="utf-8")

MOCKUP_FILES = ("retreat-board-v4.html", "retreat-live.html", "retreat-setup.html")


def mockup(name: str) -> str:
    return (MOCKUPS / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- 1. 목업


@pytest.mark.parametrize("name", MOCKUP_FILES)
def test_01_목업이_새_방향으로_다시_만들어졌고_옛_화면이_없다(name):
    """CLAUDE.md 15장이 목업부터 읽으라고 하므로, 목업이 옛 화면이면
    앞으로 모든 작업이 옛 기준에서 시작한다."""
    text = mockup(name)

    # 새 팔레트
    assert "#37352F" in text, "잉크 색이 새 값이 아니다"
    assert "rgba(55,53,47,.09)" in text, "헤어라인 선이 아니다"
    assert "#F7F7F5" in text, "사이드바 면 색이 없다"
    assert "#2383E2" in text and "#C4554D" in text, "선택·지연 색이 새 값이 아니다"

    # 옛 팔레트가 남아 있지 않다
    for old in ("#F2F4F3", "#141917", "#DDE2DE", "#C8442E", "#1668E3"):
        assert old not in text, f"옛 색 {old} 가 남아 있다"

    # 시스템 폰트 — 웹폰트를 받아오지 않는다
    assert "IBM Plex" not in text
    assert "fonts.googleapis.com" not in text
    assert "Segoe UI" in text and "Malgun Gothic" in text


# ---------------------------------------------------------------- 2·3. 사이드바


@pytest.mark.parametrize("name", MOCKUP_FILES)
def test_02_목업에_상단_탭_줄이_없고_사이드바가_있다(name):
    text = mockup(name)
    assert 'role="tablist"' not in text, "상단 탭 줄이 남아 있다"
    assert 'id="sidenav"' in text
    assert 'id="sidetoggle"' in text
    assert 'id="sideedge"' in text


def test_02b_앱에도_상단_탭_줄이_없고_사이드바로_모든_화면에_간다():
    assert "nav class=\"tabs\"" not in SHELL and "nav.tabs" not in SHELL
    assert 'id="sidenav"' in SHELL

    # 탭 줄에 있던 곳은 전부 사이드바에 있다.
    # `수련회 진행` 은 5장 스펙대로 다시 만들면서 /schedule → /live 로 옮겼다.
    for href in ("/board", "/live", "/meetings", "/budget",
                 "/library", "/setup", "/admin/users"):
        assert f"'{href}'" in SHELL or f'"{href}"' in SHELL, f"{href} 로 갈 수 없다"

    # 마법사도 같은 사이드바를 쓴다 — 화면 이동 수단이 이것뿐이다
    setup = (ROOT / "app" / "templates" / "setup.html").read_text(encoding="utf-8")
    assert 'id="sidenav"' in setup and 'id="sidetoggle"' in setup


def test_03_사이드바는_접힌_채로_시작하고_토글과_가장자리_호버로_열린다():
    # 기본이 접힘 — .sidenav 는 화면 밖에 있고, 여는 것은 .peek 와 body.sidepin 뿐
    assert re.search(r"\.sidenav\{[^}]*transform:translateX\(-100%\)", CSS)
    assert re.search(r"\.sidenav\.peek\{[^}]*transform:none", CSS)
    assert re.search(r"body\.sidepin \.sidenav\{[^}]*transform:none", CSS)
    # 고정하면 본문이 밀리고, 들춰 보는 것은 겹쳐 뜬다 (본문을 밀지 않는다)
    assert re.search(r"body\.sidepin\{padding-left:var\(--sw\)", CSS)
    assert "box-shadow:2px 0 16px" in CSS

    js = (ROOT / "app" / "static" / "js" / "sidenav.js").read_text(encoding="utf-8")
    assert "mouseenter" in js and "sidepin" in js
    # 한 번도 켠 적 없으면 접힘이다
    # 저장된 고정 여부는 **첫 그림 전에** 읽는다. 그린 뒤에 붙이면 화면을
    # 옮길 때마다 사이드바와 본문이 밀려 들어온다.
    shell = (ROOT / "app" / "templates" / "retreat_base.html").read_text(encoding="utf-8")
    assert "localStorage.getItem('dcb.sidepin')" in shell
    assert 'saved === "1"' not in js, "아직 그린 뒤에 붙인다"


# ---------------------------------------------------------------- 4. 가로 격자선


def test_04_가로_격자선이_없고_세로선만_남는다():
    lane = re.search(r"\n\.lane\{([^}]*)\}", CSS).group(1)
    assert "border-bottom" not in lane

    # 행에 가로선을 다시 그리지 않는다
    assert ".row.main .lane,.row.sub .lane{border-bottom" not in CSS
    assert re.search(r"\.lc\{[^}]*border-bottom", CSS) is None

    # 세로선은 남는다
    assert ".gridlines i{" in CSS and "border-right:1px solid var(--rule)" in CSS
    assert ".gl{border-right:1px solid var(--rule)" in CSS


@pytest.mark.parametrize("name", MOCKUP_FILES[:1])
def test_04b_목업에도_가로_격자선이_없다(name):
    text = mockup(name)
    assert ".row.main .lane,.row.sub .lane{border-bottom" not in text
    assert "가로 격자선을 넣지 않는다" in text


# ---------------------------------------------------------------- 5. 부서 색


def test_05_부서_색이_면을_채우지_않고_점과_테두리에만_쓰인다():
    from app.domain import board as board_view

    # 어떤 상태에서도 배경이 팀 색에서 파생되지 않는다
    for status in ("대기", "진행중", "완료", "지연"):
        bg, border = board_view.bar_style(status, "#B95A83", kind="main", ghost=False)
        assert not bg.startswith("rgb("), f"{status} 배경이 팀 색 틴트다"
        assert "B95A83" not in bg.upper(), f"{status} 배경에 팀 색이 들어갔다"
    # 테두리에는 쓴다 — 대기·진행중은 팀 색이 온다
    assert board_view.bar_style("대기", "#B95A83", kind="main", ghost=False)[1] == "#B95A83"
    assert board_view.bar_style("진행중", "#B95A83", kind="main", ghost=False)[1] == "#B95A83"

    # 화면 쪽도 팀 색 틴트로 면을 채우지 않는다
    assert "--teamt" not in BOARD and "--rowt" not in BOARD and "--lct" not in BOARD
    assert "var(--teamt" not in CSS and "var(--rowt" not in CSS and "var(--lct" not in CSS
    # 왼쪽 점 · 진행중 마개 · 부서 칩의 점 — 팀 색이 오는 세 자리
    assert re.search(r"\.row\.team \.lc \.sw\{[^}]*border-radius:50%", CSS)
    assert ".bar.진행중::after" in CSS and "background:var(--team" in CSS
    assert ".chip.solid::before" in CSS


# ---------------------------------------------------------------- 6. 상태 4종


def test_06_상태_4종이_구분되고_완료가_눈에_띄지_않는다():
    from app.domain import board as board_view

    styles = {
        s: board_view.bar_style(s, "#B95A83", kind="main", ghost=False)
        for s in ("대기", "진행중", "완료", "지연")
    }
    # 넷이 서로 다르다 (진행중은 배경이 같아도 왼쪽 마개로 갈린다)
    assert len({(bg, bd) for bg, bd in styles.values()}) == 4

    done_bg, done_border = styles["완료"]
    late_bg, late_border = styles["지연"]
    # 완료는 회색 — 팀 색도 붉은색도 아니다. 시선은 미완료로 가야 한다
    assert done_bg == board_view.BAR_DONE[0] and done_border == board_view.BAR_DONE[1]
    assert done_bg != late_bg
    # 지연은 붉은 테두리 + 배지
    assert late_border == board_view.BAR_LATE[1]
    assert 'class="flag">지연' in BOARD
    assert ".bar.late .flag{" in CSS
    # 완료는 글자까지 흐리게
    assert ".bar.완료{color:var(--ink-2)}" in CSS


# ---------------------------------------------------------------- 7. 속성 값


def test_07_상세_패널의_속성_값이_평소엔_글자_호버시_배경이다():
    # 라벨 88px + 값 두 칸
    assert "grid-template-columns:88px minmax(0,1fr)" in CSS
    meta = re.search(r"\.dmeta dt\{([^}]*)\}", CSS).group(1)
    assert "var(--ink-3)" in meta, "라벨이 흐림 색이 아니다"

    pill = re.search(r"\n\.pill\{([^}]*)\}", CSS).group(1)
    assert "border:1px solid transparent" in pill, "평소에 테두리가 보이면 입력 폼으로 읽힌다"
    assert re.search(r"\.pill:hover\{background:var\(--hover\)\}", CSS)

    # 제목 25px/600
    title = re.search(r"\.dtitle\{([^}]*)\}", CSS).group(1)
    # 크기는 눈금에서 끌어온다 (`--fz-4xl` = 26px). 숫자로 박아 두면
    # 다음에 전체를 키울 때 여기만 남는다
    assert "font-size:var(--fz-4xl)" in title and "font-weight:600" in title

    # 탭은 밑줄 없는 글자, 활성만 아래 선
    assert re.search(r"\.dtabs button\{[^}]*border-bottom:2px solid transparent", CSS)
    assert re.search(r"\.dtabs button\[aria-selected=true\]\{[^}]*border-bottom-color:var\(--ink\)", CSS)

    # 진단 패널은 회색 블록(노션 콜아웃)
    assert re.search(r"\.dg-h\{[^}]*background:var\(--side\)", CSS)
    assert re.search(r"\.dg-b\{[^}]*background:var\(--side\)", CSS)


# ---------------------------------------------------------------- 15. 환영 알림


def test_15_환영_알림이_스스로_사라지고_눌러서도_닫힌다():
    """서버가 쿠키로 한 번 보내고 마는 배너라, 아무도 지우지 않으면 계속 떠 있었다."""
    js = (ROOT / "app" / "static" / "js" / "flash.js").read_text(encoding="utf-8")

    assert "LINGER" in js and re.search(r"var LINGER = \d+", js)
    assert "setTimeout(function () { dismiss(el); }, LINGER)" in js   # 시간이 지나면
    assert 'addEventListener("click", function () { dismiss(el); })' in js  # 눌러서도

    # 두 화면이 같은 한 벌을 쓴다 — 예전에는 app.js 안에만 있어서 보드 쪽은 안 사라졌다
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert "flash.js" in base and "flash.js" in SHELL
    app_js = (ROOT / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "flash.style.opacity" not in app_js, "app.js 에 옛 사본이 남아 있다"


# ---------------------------------------------------------------- 16. 자가진단


def test_16_자가진단의_바깥_접속_확인이_브라우저처럼_묻는다():
    """Cloudflare 가 urllib 의 기본 헤더를 막아 403 을 돌려준다 —
    멀쩡한 서버를 자가진단이 문제라고 말하는 셈이었다."""
    from scripts import healthcheck

    assert healthcheck.BROWSER_UA.startswith("Mozilla/5.0")
    assert "Python-urllib" not in healthcheck.BROWSER_UA

    import inspect

    source = inspect.getsource(healthcheck.check_tunnel)
    assert '"User-Agent": BROWSER_UA' in source
    assert '"403" in str(exc)' in source, "403 일 때 무엇 때문인지 말하지 않는다"


def test_16b_주소를_주지_않으면_네트워크에_나가지_않는다():
    from scripts import healthcheck

    ok, message = healthcheck.check_tunnel(None)
    assert ok is True
    assert "건너뜁니다" in message


# ---------------------------------------------------------------- 17. 배포 안내


def test_17_배포_안내에_cloudflared_서비스_등록_실제_절차가_들어갔다():
    """`service install` 만 하면 종료 코드 1067 로 곧바로 죽는다."""
    guide = (ROOT / "docs" / "배포-안내.md").read_text(encoding="utf-8")

    section = guide[guide.index("### 8-3."):guide.index("## 9.")]
    assert "1067" in section
    assert "LocalSystem" in section
    assert r"C:\Windows\System32\config\systemprofile\.cloudflared" in section
    # **`.exe` 까지 본다** (11-2) — PowerShell 에서 `sc` 는 `Set-Content`
    # 별칭이라, `.exe` 가 빠지면 화면에 아무것도 안 나오고 `config` 라는
    # 파일이 생긴다. 8-3 의 핵심 줄이라 조용히 틀리면 서비스가 1067 로 죽는다.
    assert "sc.exe config Cloudflared binPath=" in section
    assert "--config" in section
    assert "net stop Cloudflared" in section and "net start Cloudflared" in section
    assert "sc.exe query Cloudflared" in section
    assert "CONNECTOR ID" in section

    # 막혔을 때에도 1067 항목이 있다
    stuck = guide[guide.index("## 11. 막혔을 때"):guide.index("## 12.")]
    assert "1067" in stuck


def test_18_다시_켜기_절차가_포트를_쥔_프로세스를_끝낸다():
    """`Stop-ScheduledTask` 는 **작업만** 멈추고 그 아래 파이썬을 끝내지 않는다.

    포트는 계속 열려 있어서 겉으로는 재시작된 것처럼 보이는데 어제 뜬
    프로세스가 그대로 답한다 — 2026-09-02 에 그것으로 새 화면 + 옛 코드가
    짝지어져 상세 패널이 `Drawer is not defined` 로 안 열렸다.
    """
    guide = (ROOT / "docs" / "배포-안내.md").read_text(encoding="utf-8")
    section = guide[guide.index("## 12. 고친 것을 반영하려면"):guide.index("## 13.")]

    # 포트를 쥔 것을 실제로 찾아서 끝낸다
    assert "Get-NetTCPConnection -LocalPort" in section
    assert "Stop-Process" in section and "-Force" in section
    # 작업을 먼저 멈춘다 — 안 그러면 "실패하면 다시 시작" 이 되살린다
    assert section.index("Stop-ScheduledTask") < section.index("Stop-Process")
    assert "다시 시작" in section

    # **성공은 PID 가 바뀌는 것으로 적는다.** 포트로는 알 수 없다
    assert "이렇게 나오면 성공" in section
    assert "PID 가 바뀌었습니다" in section
    assert "포트가 열려 있는 것으로는" in section

    # 처음 하는 사람 기준 — 관리자 권한과 손으로 하는 순서도 있다
    assert "관리자 권한으로 실행" in section
    assert "손으로 하려면" in section

    # 왜 이 장이 생겼는지 (다음 사람이 지우지 않게)
    assert "Drawer is not defined" in section

    # 서버가 떠 있나 항목에서 이리로 보낸다 — HTML 이 나와도 옛 코드일 수 있다
    stuck = guide[guide.index("## 11. 막혔을 때"):guide.index("## 12.")]
    assert "12장" in stuck

    # 기준 문서에도 같은 사실이 적혀 있다
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "작업만 멈추고" in claude and "PID 가 바뀌었는지" in claude

    # 백업 대상에 업로드 폴더가 들어갔다
    routine = guide[guide.index("## 12."):]
    assert "uploads" in routine
