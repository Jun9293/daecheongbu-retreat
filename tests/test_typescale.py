"""글자 눈금과 달력의 부서 고르기 (CLAUDE.md 4-0 · 4-13 · 9장).

**왜 눈금인가.** 크기가 24가지로 흩어져 286곳에 숫자로 박혀 있었다.
"전반적으로 작다" 는 말을 듣고 값을 하나씩 올리면 **다음에 또 어딘가만
작다** — 실제로 그렇게 굴러왔다. 그래서 `--fz` 하나가 전부를 정하게 하고,
이 시험이 **숫자가 다시 새어 들어오는 것**을 막는다.
"""

from __future__ import annotations

import pathlib
import re

CSS_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "retreat.css"
CSS = CSS_PATH.read_text(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent

# 눈금. 작은 것부터 — 시험이 "위계가 있는가" 를 이 차례로 견준다
단 = ["--fz-xs", "--fz-sm", "--fz-md", "--fz-base",
     "--fz-lg", "--fz-xl", "--fz-2xl", "--fz-3xl", "--fz-4xl"]


def _민낯() -> str:
    """주석을 걷어낸 CSS. **찾는 말이 설명글에 있으면 시험이 거짓말을 한다** —
    이 프로젝트가 네 번 당한 그것이다 (10장)."""
    return re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def 선언(sel: str) -> str:
    """그 선택자의 규칙 하나. **선택자가 정확히 그것인 규칙**을 찾는다.

    앞글자만 맞춰 찾으면 `body` 가 `html,body{height:100%}` 에 걸려
    **엉뚱한 규칙을 잰다** — 실제로 그래서 "본문이 눈금을 안 쓴다" 는
    거짓 실패가 났다. 쉼표로 나눈 선택자 목록에 정확히 들어 있어야 한다.
    """
    import re as _r

    본문 = _민낯()
    for m in _r.finditer(r"([^{}]+)\{([^{}]*)\}", 본문):
        고른것 = [" ".join(x.split()) for x in m.group(1).split(",")]
        if sel in 고른것 and "font-size" in m.group(2) or (sel in 고른것 and sel == ":root"):
            return m.group(2)
    for m in _r.finditer(r"([^{}]+)\{([^{}]*)\}", 본문):
        if sel in [" ".join(x.split()) for x in m.group(1).split(",")]:
            return m.group(2)
    raise AssertionError(f"{sel} 규칙이 없다")


def 단번호(sel: str) -> int:
    m = re.search(r"font-size:\s*var\((--fz[\w-]*)\)", 선언(sel))
    assert m, f"{sel} 이 눈금을 안 쓴다"
    return 단.index(m.group(1))


# ── 1. 크기는 눈금에서만 나온다 ──────────────────────────────────────


def test_ts_01_숫자로_박힌_크기가_없다():
    """**하나씩 올리면 다음에 또 어딘가만 작다.** 숫자를 못 쓰게 한다."""
    남은것 = re.findall(r"font-size:\s*([0-9.]+px)", _민낯())
    assert not 남은것, f"눈금 밖의 숫자 크기가 남아 있다: {sorted(set(남은것))}"


def test_ts_01b_눈금이_하나에서_나온다():
    뿌리 = 선언(":root")
    assert "--fz:15px" in 뿌리.replace(" ", ""), "기준 크기가 없다"
    for 이름 in 단[:1] + 단[1:]:
        if 이름 == "--fz-base":
            continue
        assert f"{이름}:calc(var(--fz)" in 뿌리.replace(" ", "") or f"{이름}:var(--fz)" in 뿌리.replace(" ", ""), \
            f"{이름} 이 기준에서 안 나온다"


# ── 2 · 3. 하한이 둘이다 ─────────────────────────────────────────────


def test_ts_02_본문_목록_사이드바가_하한_아래로_안_내려간다():
    """혼자 뜻을 지는 글자의 하한은 **14px**(`--fz-md`)이다."""
    하한 = 단.index("--fz-md")
    자리 = {
        "body": "본문",
        ".sidenav nav a": "사이드바 링크",
        ".sidenav .navlabel": "사이드바 묶음 제목",
        ".sidefoot": "사이드바 아래",
        ".whoami": "사이드바의 사용자",
        ".lc": "왼쪽 업무명",
        ".row.sub .lc": "왼쪽 하위 업무명",
        ".bar": "보드의 바",
        ".bar.s": "보드의 하위 바",
        ".bar.sch": "보드의 일정 칩",
        ".cal-dot": "달력의 점",
        ".cal-d": "달력의 날짜",
        ".cal-wd": "달력의 요일 머리",
        ".cal-more": "달력의 외 N건",
        ".mrow .nm": "좁은 화면의 업무명",
        ".mgroup > h3": "좁은 화면의 부서 제목",
        ".toolbar": "위쪽 도구줄",
        ".chip": "상태 칩",
    }
    작은것 = {이름: sel for sel, 이름 in 자리.items() if 단번호(sel) < 하한}
    assert not 작은것, f"목록 하한(14px) 아래인 곳: {작은것}"


def test_ts_03_보조_글자가_12px_아래로_안_내려간다():
    """가장 작은 단이 12px 이고, 그보다 작은 단은 없다."""
    뿌리 = 선언(":root").replace(" ", "")
    assert "--fz-xs:calc(var(--fz)-3px)" in 뿌리, "가장 작은 단이 12px 이 아니다"
    # 눈금 밖으로 더 작게 내려가는 길이 없다
    assert not re.search(r"--fz-[\w-]*:\s*calc\(var\(--fz\)\s*-\s*(?:[4-9]|\d\d)px\)", 선언(":root"))


# ── 4. 위계는 남는다 ─────────────────────────────────────────────────


def test_ts_04_위계가_유지된다():
    """다 같은 크기가 되면 무엇이 중요한지 사라진다."""
    assert 단번호(".dtitle") > 단번호("body"), "상세 패널 제목이 본문보다 크지 않다"
    assert 단번호("body") > 단번호(".log .d"), "논의 날짜가 본문과 같은 크기다"
    assert 단번호(".sidenav nav a") > 단번호(".sidenav .navlabel"), \
        "사이드바 링크와 묶음 제목이 같은 크기다"
    assert 단번호(".mrow .nm") > 단번호(".mrow .meta"), "좁은 화면의 이름과 메타가 같다"
    # 실제로 여러 단이 쓰인다 — 눈금만 만들고 한 단만 쓰면 위계가 없다
    쓰인것 = set(re.findall(r"font-size:\s*var\((--fz[\w-]*)\)", _민낯()))
    assert len(쓰인것) >= 5, f"눈금이 {len(쓰인것)}단만 쓰인다"


# ── 5. 간격도 함께 ───────────────────────────────────────────────────


def test_ts_05_줄_간격도_함께_올렸다():
    """**글자만 키우고 줄 간격이 그대로면 더 답답해진다.**"""
    body = 선언("body")
    m = re.search(r"line-height:\s*([\d.]+)", body)
    assert m and float(m.group(1)) >= 1.6, f"본문 줄 간격이 그대로다: {body}"


def test_ts_06_칸_높이도_함께_올렸고_이유가_적혔다():
    """바 안에 14px 글자가 들어가는데 높이가 그대로면 위아래가 붙는다.

    **재서 판단한 것을 남긴다** — 다음 사람이 "왜 이 값인가" 를 물을 자리다.
    """
    뿌리 = 선언(":root").replace(" ", "")
    assert "--h-main:38px" in 뿌리 and "--h-sub:33px" in 뿌리 and "--h-team:42px" in 뿌리
    assert ".bar.m{height:26px}" in CSS.replace(" ", "")
    # 왜 이 값인지가 주석에 있다 (숫자와 함께)
    at = CSS.index("--h-team:42px")
    설명 = CSS[max(0, at - 500):at]
    assert "접어 보는 화면" in 설명 and "스크롤" in 설명


# ── 8 · 9. 흐림은 옆에 값이 있는 자리에만 ────────────────────────────


# **흐림이 맞는 자리.** 개수·아이콘·속성 라벨, 그리고 *흐린 것이 곧 뜻*인 것.
흐려도_되는곳 = {
    ".sidenav .wip", ".ctl label", ".row.team .lc .caret", ".row.team .lc .ct",
    ".bar.ghost .txt.spill", ".bar.ghost", ".mgroup > h3 .n", ".dmeta dt",
    ".pill .span", ".dtabs .n", ".log s", ".dclose", ".fitem .more",
    ".fitem.link .ext", ".linkform .lbl", ".upnow .top .x", ".field label",
    ".card h3 .n", ".tchip .x", ".libsec > h3 .n", ".libsec > h3 em",
    ".subrow .branch", ".editbtn", ".trow.off .nm", ".draftrow .n", ".retired",
    ".prow .ind", ".dg-b li .ic", ".railadd", ".ph-h .n", ".sg-h .n",
    ".item.on .txt", ".item.on .txt .lead", ".item .scopeswap", ".item .itemdel",
    ".itemadd", ".c-note > .cx", ".sheetform .frow > label", ".sheetform legend",
    ".cal-cell.out .cal-d", ".cal-dot.done .cal-t", ".calday-d i",
    ".mt-one-meta label",
}


def test_ts_08_흐림이_혼자_뜻을_지는_글자에_안_쓰인다():
    """`--ink-3` 은 흰 바탕에서 3.84:1 — 9장의 4.5:1 을 넘기지 않는다.

    **토큰을 올리지 않는다.** 올리면 보조와 구별이 사라져 위계가 무너진다.
    자리마다 옮긴다.
    """
    민낯 = _민낯()
    쓴곳 = [" ".join(m.group(1).split())
           for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", 민낯)
           if re.search(r"(^|[;\s])color:\s*var\(--ink-3\)", m.group(2))]
    새어든것 = [x for x in 쓴곳 if x not in 흐려도_되는곳]
    assert not 새어든것, f"혼자 뜻을 지는데 흐림이다: {새어든것}"


def test_ts_09_사이드바_묶음_제목이_읽힌다():
    """`실무`·`회차 준비` — **옆에 값이 없다.** 11px `--ink-3` 이었다."""
    label = 선언(".sidenav .navlabel")
    assert "var(--ink-2)" in label and "var(--ink-3)" not in label
    assert 단번호(".sidenav .navlabel") >= 단.index("--fz-md")


# ── 10 ~ 14. 달력의 부서 고르기 ──────────────────────────────────────


def test_ts_11_보드와_달력이_같은_것을_쓴다():
    """**새로 만들지 않았다.** 두 벌이 되면 한쪽만 고쳐진다."""
    매크로 = ROOT / "app" / "templates" / "partials" / "deptpick.html"
    assert 매크로.exists(), "고르는 자리가 한 곳에 없다"
    글 = 매크로.read_text(encoding="utf-8")
    assert "macro deptpick(" in 글
    assert "d.key" in 글, "부서를 키로 안 쓴다 (2장)"

    for 화면 in ("board.html", "calendar.html"):
        본문 = (ROOT / "app" / "templates" / 화면).read_text(encoding="utf-8")
        assert 'from "partials/deptpick.html" import deptpick' in 본문, f"{화면} 이 안 쓴다"
        assert "deptpick(" in 본문
    # 보드에 옛 목록이 남아 있지 않다
    board = (ROOT / "app" / "templates" / "board.html").read_text(encoding="utf-8")
    assert "<option value=\"all\">전체</option>" not in board, "보드에 옛 목록이 남았다"


def test_ts_12_고른_부서가_주소에_남는다():
    """새로고침해도, 달을 넘겼다 와도 유지된다 (4-13)."""
    js = (ROOT / "app" / "static" / "js" / "calendar.js").read_text(encoding="utf-8")
    자리 = js[js.index("scopePick"):js.index("const dots =")]
    assert "location.href" in 자리
    assert "month: bar.dataset.month" in 자리, "보던 달을 안 들고 간다"
    assert "only_open" in 자리, "미완료만 을 안 들고 간다"
    assert "scope: scopePick.value" in 자리

    # 달을 넘기는 링크도 지금 값을 달고 다닌다
    cal = (ROOT / "app" / "templates" / "calendar.html").read_text(encoding="utf-8")
    assert 'set keep = "scope=" ~ cal.scope' in cal


def test_ts_14_좁은_화면도_같은_것을_본다():
    """주 목록은 같은 `cal.weeks` 를 그린다 — 거르는 곳이 하나다."""
    cal = (ROOT / "app" / "templates" / "calendar.html").read_text(encoding="utf-8")
    격자 = cal.index('<table class="cal-grid">')
    목록 = cal.index('<div class="calweeks">')
    assert cal.count("for week in cal.weeks") == 2, "격자와 주 목록이 같은 것을 안 쓴다"
    assert 격자 < 목록
    # 고르는 칸은 둘 위에 하나뿐이다
    assert cal.count("deptpick(") == 1
