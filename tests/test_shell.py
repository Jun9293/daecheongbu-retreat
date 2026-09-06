"""새 껍데기 (UI 개편 단계 1) — 사이드바 B안 · 토큰 · 설정 탭 여섯.

기준은 CLAUDE.md 3장·4-0·4-17 이다. 값은 시험에 박지 않고 **문서에서 읽어**
CSS 와 견준다 (11-3 — 문서의 값을 시험에 박지 않는다).
"""

from __future__ import annotations

import pathlib
import re

from tests.conftest import app_session, login_as

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
SHELL = (ROOT / "app" / "templates" / "retreat_base.html").read_text(encoding="utf-8")
DOC = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- 1. 토큰


def _css_token(name: str) -> str:
    """`--name:값` 을 찾아 var() 를 끝까지 푼다 — 한 곳(:root)만 본다."""
    value = None
    m = re.search(rf"--{re.escape(name)}\s*:\s*([^;}}]+)", CSS)
    assert m, f"--{name} 토큰이 retreat.css 에 없다"
    value = m.group(1).strip()
    seen = 0
    while value.startswith("var(") and seen < 5:
        inner = value[4:-1].strip().lstrip("-")
        m = re.search(rf"--{re.escape(inner)}\s*:\s*([^;}}]+)", CSS)
        assert m, f"var(--{inner}) 가 가리키는 토큰이 없다"
        value = m.group(1).strip()
        seen += 1
    return value.upper()


def test_s01_배지_토큰이_문서의_표와_같다():
    """CLAUDE.md 4-0 의 상태 배지 표(상태 | 채움 | 글자)를 그대로 읽어 견준다."""
    at = DOC.index("**상태 배지 = 옅은 채움 + 진한 글자.**")
    section = DOC[at : at + 800]
    rows = re.findall(r"\|\s*(대기|진행중|지연|완료)\s*\|\s*`(#[0-9A-Fa-f]{6})`\s*\|\s*`(#[0-9A-Fa-f]{6})`\s*\|", section)
    assert len(rows) == 4, "문서의 배지 표를 읽지 못했다 — 아무것도 안 보는 검사는 통과가 아니다"

    key = {"대기": "wait", "진행중": "prog", "지연": "late", "완료": "done"}
    for status, bg, fg in rows:
        assert _css_token(f"st-{key[status]}-bg") == bg.upper(), f"{status} 채움이 문서와 다르다"
        assert _css_token(f"st-{key[status]}-fg") == fg.upper(), f"{status} 글자가 문서와 다르다"


def test_s02_accent_와_카드가_문서와_같고_옛_선택_파랑은_흡수됐다():
    m = re.search(r"\*\*accent `(#[0-9A-Fa-f]{6})`\*\*", DOC)
    assert m, "문서에서 accent 값을 읽지 못했다"
    accent = m.group(1).upper()
    assert _css_token("accent") == accent
    # 기존 선택 파랑은 accent 로 흡수 — --link 가 accent 를 가리킨다 (4-0)
    assert _css_token("link") == accent, "--link 가 아직 옛 선택 파랑이다"
    assert _css_token("card") == "#FFFFFF"


# ---------------------------------------------------------------- 2. 사이드바 구조


def test_s03_그룹_제목은_링크이고_첫_하위로_간다():
    """3장 — 그룹 제목을 누르면 그 그룹의 첫 하위로 간다."""
    groups = re.findall(r'<a class="g" href="([^"]+)"[^>]*>.*?([가-힣 ]+)</a>', SHELL)
    names = {name.strip(): href for href, name in groups}
    assert names.get("수련회 준비") == "/tasks"
    assert names.get("수련회 진행") == "/live"
    assert names.get("재정") == "/budget"
    # 그룹이 <div> 로 남아 있지 않다
    assert '<div class="g"' not in SHELL and 'class="navgroup"' not in SHELL


def test_s04_선택_표시는_하위에만_붙는다():
    """그룹 요소에는 활성 상태가 없다 — 둘 다 칠하면 어디 있는지 두 번 말한다."""
    for m in re.finditer(r'<a class="g"[^>]*>', SHELL):
        assert "aria-current" not in m.group(0), "그룹 제목에 활성 표시가 붙어 있다"
    # CSS 에도 .g 활성 규칙이 없다
    assert not re.search(r"\.g\[aria-current", CSS)
    # 하위에는 있다
    assert re.search(r'class="n" href="/tasks"[^>]*aria-current', SHELL.replace("\n", " ")) or \
        "{% if active_tab == 'tasks' %}aria-current" in SHELL


def test_s05_사이드바에_없는_것들():
    """새 회차 만들기 · 라이브러리 · 작업 파일은 사이드바에 없다 (3장)."""
    for href in ('"/setup"', '"/library"', '"/settings/library"', '"/files"',
                 '"/admin/users"', '"/admin/notify/preview"'):
        assert href not in SHELL, f"{href} 가 아직 사이드바에 있다"


def test_s06_구조가_3장_순서다():
    order = ["홈", "회의록", "수련회 준비", "목록", "보드", "달력",
             "수련회 진행", "진행 화면", "봉사자 시간표", "재정", "예산", "지출",
             "알림", "체크리스트", "설정"]
    nav = SHELL[SHELL.index("<nav>") : SHELL.index("</nav>")]
    text = re.sub(r"<svg.*?</svg>", "", nav, flags=re.S)
    pos = -1
    for label in order:
        at = text.find(label, pos + 1)
        assert at > pos, f"'{label}' 이 순서대로 없다"
        pos = at


# ---------------------------------------------------------------- 3·5. 폭과 고정


def test_s07_본문에_최대_폭이_없다():
    """9장 — 사이드바를 뺀 창 폭 전부가 본문이다."""
    assert "max-width:1000px" not in CSS, ".wiz .pane 에 최대 폭이 남아 있다"
    setting = re.search(r"\n\.setting\{([^}]*)\}", CSS).group(1)
    assert "max-width" not in setting
    # 지표 4칸은 grid 로 늘어난다
    assert re.search(r"\.kpis\{[^}]*repeat\(4,1fr\)", CSS)


def test_s08_1280_기준_펼침_고정():
    """≥1280 펼침 고정(본문이 밀린다), 그 아래 접힘 + 호버. 고정은 기기에 남는다."""
    # 고정의 효과(본문 밀기·펼침)는 1280 미디어 안에만 있다
    assert re.search(r"@media \(min-width:1280px\)\{\s*body\.sidepin\{padding-left:var\(--sw\)", CSS)
    assert re.search(r"@media \(min-width:1280px\)\{\s*body\.sidepin \.sidenav\{[^}]*transform:none", CSS)
    # 부팅 스크립트 — 저장값이 없으면 1280 이상에서 펼침이 기본
    assert "localStorage.getItem('dcb.sidepin')" in SHELL
    assert "window.innerWidth >= 1280" in SHELL
    js = (ROOT / "app" / "static" / "js" / "sidenav.js").read_text(encoding="utf-8")
    assert "localStorage.setItem" in js, "고정 여부가 기기에 남지 않는다"
    assert "window.innerWidth >= 1280" in js, "1280 아래에서 들춰 보기가 막힌다"


# ---------------------------------------------------------------- 6·7. 카드와 배지


def _luminance(hexcolor: str) -> float:
    r, g, b = (int(hexcolor[i : i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_s13_배지_글자가_채움_위에서_4_5를_넘긴다():
    """9장 — 회차 목록에서 배지가 혼자 뜻을 진다. 값은 문서의 표에서 읽는다."""
    at = DOC.index("**상태 배지 = 옅은 채움 + 진한 글자.**")
    rows = re.findall(
        r"\|\s*(대기|진행중|지연|완료)\s*\|\s*`(#[0-9A-Fa-f]{6})`\s*\|\s*`(#[0-9A-Fa-f]{6})`\s*\|",
        DOC[at : at + 800],
    )
    assert len(rows) == 4, "문서의 배지 표를 읽지 못했다"
    for status, bg, fg in rows:
        r = _ratio(fg, bg)
        assert r >= 4.5, f"{status} 배지 글자 대비 {r:.2f} — 4.5 미만"


def test_s14_사용자_카드_세_줄이_꺾이지_않는다():
    """1-h — 이름 · 역할 · 부서 각 한 줄. 240px 에서 nowrap + 말줄임."""
    foot = SHELL[SHELL.index('class="sidefoot"') : SHELL.index("</aside>")]
    # 세 줄: 이름(b) + 역할(small) + 부서(small)
    assert foot.count("<small>") == 2 and "<b>{{ user.name }}</b>" in foot
    assert "side_dept_name" in foot
    # 로그아웃은 카드에 없다 — 설정 › 내 정보에만 (4-17)
    assert "/logout" not in foot
    settings_tpl = (ROOT / "app" / "templates" / "settings.html").read_text(encoding="utf-8")
    assert '"/logout"' in settings_tpl
    # 꺾이지 않는다 — nowrap + 넘침 처리, 칸은 줄어들 수 있어야 한다(min-width:0)
    who = re.search(r"\.sidefoot \.who b,\.sidefoot \.who small\{([^}]*)\}", CSS).group(1)
    assert "white-space:nowrap" in who and "text-overflow:ellipsis" in who
    assert re.search(r"\.sidefoot \.who\{[^}]*min-width:0", CSS)
    # 사이드바 폭이 목업과 같은 240px 이다 (9장)
    assert "--sw:240px" in CSS


def test_s09b_배지가_0건이면_없고_생기면_수가_보인다(admin_client):
    """글자 검사만 두면 안 된다 (10장) — 실제 렌더링으로 잰다."""
    from app.models import Notification, User

    page = admin_client.get("/settings").text
    assert 'class="badge"' not in page, "0건인데 배지가 있다"

    with app_session() as db:
        me = db.query(User).one()
        db.add(Notification(user_id=me.id, kind="테스트", title="시험",
                            dedupe_key="test-badge-1"))
        db.commit()
    page = admin_client.get("/settings").text
    assert '<span class="badge">1</span>' in page, "안 읽은 알림이 배지에 안 나온다"


def test_s09_사용자_카드와_알림_배지():
    foot = SHELL[SHELL.index('class="sidefoot"') :]
    assert "user.name" in foot and "ROLE_LABELS" in foot
    # 부서는 키로 — templating 이 회차의 같은 키 부서로 바꿔 준다 (2장)
    assert "side_dept_name" in foot
    templating = (ROOT / "app" / "templating.py").read_text(encoding="utf-8")
    assert "department_key_of" in templating
    # 배지 = 안 읽은 알림 + 대기 요청, 0이면 없음
    assert "unread_count" in SHELL and "pending_review_count" in SHELL
    assert "{% if nav_badge %}" in SHELL, "배지가 0건에도 나온다"


# ---------------------------------------------------------------- 9·10. 설정 탭과 옛 주소


def _lead_client(admin_client):
    """부서 리더 계정으로 로그인한 별도 클라이언트."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.models import User

    with app_session() as db:
        lead = User(name="박리더", phone_number="01077778888", role="dept_lead")
        db.add(lead)
        db.commit()
    lead_client = TestClient(app)
    login_as(lead_client, "01077778888")
    return lead_client


def test_s10_설정_탭_여섯_앞_둘은_누구나_넷은_admin_만(admin_client):
    admin_client.post(
        "/retreats/create",
        data={"name": "탭 시험 회차", "start_date": "2026-08-21", "end_date": "2026-08-23",
              "meal_subsidy_per_person": 8000, "clone_from": ""},
        follow_redirects=True,
    )
    with app_session() as db:
        from app.models import Retreat

        retreat_id = db.query(Retreat).filter_by(name="탭 시험 회차").one().id

    # 회차 상세는 이번 단계에서 계산이 가장 많은 새 화면이다 — 스모크로 지킨다
    everyone = ["/settings", "/settings/retreats", f"/settings/retreats/{retreat_id}"]
    admin_only = ["/settings/departments", "/admin/users", "/settings/library", "/settings/checkup"]

    for path in everyone + admin_only:
        assert admin_client.get(path).status_code == 200, f"admin: {path}"
    assert admin_client.get("/settings/retreats/99999").status_code == 404

    lead = _lead_client(admin_client)
    for path in everyone:
        assert lead.get(path).status_code == 200, f"lead: {path}"
    for path in admin_only:
        assert lead.get(path).status_code in (403, 404), f"lead 가 {path} 를 연다"


def test_s11_옛_주소들(admin_client):
    admin_client.post(
        "/retreats/create",
        data={"name": "옛 주소 시험", "start_date": "2026-08-21", "end_date": "2026-08-23",
              "meal_subsidy_per_person": 8000, "clone_from": ""},
        follow_redirects=True,
    )
    r = admin_client.get("/library", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/settings/library"
    assert admin_client.get("/more").status_code == 404
    r = admin_client.get("/schedule", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/live/staff"
    # 체크리스트가 새 껍데기다
    page = admin_client.get("/checklists")
    assert page.status_code == 200 and 'id="sidenav"' in page.text


def test_s12_목업이_문서의_토큰과_같다():
    """retreat-shell.html 은 새 껍데기의 시각 스펙이다 — 값이 갈리면 목업이 옛 기준이 된다."""
    mock = (ROOT / "docs" / "mockups" / "retreat-shell.html").read_text(encoding="utf-8")
    m = re.search(r"\*\*accent `(#[0-9A-Fa-f]{6})`\*\*", DOC)
    assert m and m.group(1).upper() in mock.upper()
    assert '<a class="g"' in mock and '<div class="g"' not in mock
