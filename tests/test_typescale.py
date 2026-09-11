"""글자 눈금과 달력의 부서 고르기 (CLAUDE.md 4-0 · 4-13 · 9장).

**왜 눈금인가.** 크기가 24가지로 흩어져 곳곳에 숫자로 박혀 있었다
(2026-09-03 에 세어 봤다 — 4-0).
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
        ".sidenav nav .g": "사이드바 그룹 제목",
        ".sidenav .subs .n": "사이드바 하위",
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


# **보조 급의 자리** — 옆이나 아래가 뜻의 절반을 지는 조작·메타.
# 하한은 보조 단(13px)이고 그 아래로는 안 내려간다. 4-0 의 눈금이
# 보조를 「메타·날짜·작성자·부속 숫자」 로 두었으므로, 그 성격의 자리는
# 여기서 잰다 — **장식 단(12px)으로 흘러내리지 않게 하는 것**이 목적이다.
보조급자리 = {
    ".tlist .lsort .chip":
        "목록의 정렬 토글 — 누르면 그 아래 목록이 곧바로 그 순서가 되고, "
        "지금 축과 방향은 화살표가 보인다. 무엇을 볼지(상태 칩 14px)가 "
        "먼저고 순서는 그다음이라 한 급 아래다 (4-14)",
    ".budtbl .itemlbl":
        "예산 표의 항목 라벨 — 묶음 이름이고 내용은 그 아래 세부항목 줄들이 "
        "진다(이름·수치). 구분 제목(14px 600)과 세부항목(14px) 사이의 급이라 "
        "한 급 아래다 (7-3 · UI 정리 판 1)",
}


def test_ts_02b_보조_급_자리가_장식_단으로_안_내려간다():
    """급을 낮추더라도 **바닥이 있다.** 자리마다 왜 보조인지 적어 두고
    (「옆이 뜻의 절반을 지는가」 는 기계가 못 가른다), 그보다 더 내려가면
    빨개진다. 적어 둔 것이 실제로 그 단인지도 함께 본다 —
    ③ 검사가 볼 것을 보고 있나 (11-3)."""
    보조 = 단.index("--fz-sm")
    for sel, 이유 in 보조급자리.items():
        assert 단번호(sel) == 보조, f"{sel} 이 보조 단(13px)이 아니다"
        assert len(이유) > 30, f"{sel} 의 이유가 비었다"
        assert 단번호(sel) < 단번호(".chip"), f"{sel} 이 상태 칩보다 작지 않다"


# **급을 올린 자리** — 4-0 이 내린 자리(흐림·보조)를 이름으로 적어 두는 것과
# 같은 이유로 올린 자리도 적는다. 산문으로만 두면 **둘째 자리가 조용히 생기는
# 것을 아무도 못 본다**(2026-09-11 검토가 「선례를 불러 놓고 선례의 절반만
# 가져왔다」 고 짚은 자리). 올리는 데는 까닭이 있어야 하고, 그 까닭은 「이
# 문장이 없으면 지금 할 수 있는 전부가 없어진다」 쯤이어야 한다.
제목태그 = {"h1", "h2", "h3", "h4", "h5", "h6"}

# **눈금이 이미 본문 단에 두기로 한 요소.** 4-0 의 표가 본문 단을
# 「body·입력·논의·왼쪽 라벨」 로 적었으므로, 입력칸과 표가 그 단인 것은
# **올린 것이 아니라 제자리**다.
눈금이정한요소 = {"input", "select", "textarea", "table", "td", "th"}


def _요소인가(마지막: str, 목록: set[str]) -> bool:
    """선택자 끝이 그 요소인가 — `input[type=password]` 같은 꼴도 본다."""
    이름 = 마지막.split("[")[0].split(":")[0].split(".")[0]
    return 이름 in 목록


# **급을 올린 자리** — 4-0 이 내린 자리(흐림·보조)를 이름으로 적어 두는 것과
# 같은 이유로 올린 자리도 적는다. 산문으로만 두면 **둘째 자리가 조용히 생기는
# 것을 아무도 못 본다**(2026-09-11 검토). 올리는 데는 까닭이 있어야 하고,
# 그 까닭은 「이 문장이 없으면 지금 할 수 있는 전부가 없어진다」 쯤이어야 한다.
#
# **여기 드는 것은 「원래 장식·보조 자리인데 올린 것」 뿐이다.** 구조가
# 원래 그 급인 것(제목·지표 숫자·섹션 이름 …)은 아래 `눈금이정한자리` 로
# 따로 간다 — 섞으면 이 목록이 설정 페이지의 크기 목록이 되어 뜻을 잃는다
# (2026-09-12 검토가 짚은 자리).
올린자리 = {
    ".fld .pwwarn":
        "설정 › 내 정보의 「남의 기기에서 쓰고 나면 로그아웃한다」 — 지금 "
        "비밀번호를 안 묻기로 한 대가를 화면에서 감당하는 문장이다(4-17 · "
        "봐둘것 AS-a). 막는 것이 아니라 아는 사람을 늘리는 것이 지금 할 수 "
        "있는 전부인데, 그 전부가 장식 단에 있으면 안 읽힌다 (2026-09-11)",
}

# **구조가 원래 그 급인 자리.** 올린 것이 아니라 4-0 의 눈금이 그렇게
# 정한 것들이다. **제목과 입력칸·표는 여기 없다** — 요소 이름(`제목태그` ·
# `눈금이정한요소`)으로 이미 거르므로, 여기 또 적으면 두 곳이 같은 일을
# 하고 한쪽만 고쳐진다. 여기 적는 까닭은 **빼 두기 위해서가 아니라 세어 두기
# 위해서**다 — 목록에 없는 새 자리가 본문 단 이상이면 둘 중 어느 쪽인지
# 사람이 한 번 보게 된다.
눈금이정한자리 = {
    ".kv": "두 칸 정의 표의 값 — 값이 곧 내용이라 목록 단이다 (4-9)",
    ".secttl": "구역 이름 — 카드 안의 작은 제목",
    ".lead": "그 화면이 무엇인지 한 줄로 여는 글 — 제목 바로 아래 급",
    ".alert": "경고 띠 — 화면 맨 위에서 혼자 뜻을 진다",
    ".stabs a": "설정 탭 줄 — 이동하는 자리라 본문 급",
    ".kpi .v": "지표 칸의 큰 숫자 — 4-0 의 제목 급 토큰을 쓰는 표시 자리다. "
               "홈·예산·지출도 같은 것을 쓴다",
    ".find": "찾는 칸 옆의 입력 — 입력 급 (4-0 의 본문 단)",
    ".btn.sm": "작은 단추 — 누르는 자리라 목록 급이다",
    "button.btn": "단추 — 누르는 자리라 본문 급이다",
    ".retired": "반납한 연락처 표기 — 표 안의 값 급 (4-12)",
    ".loginform button:not(.sbtn)":
        "로그인 화면의 단추 — 그 화면에서는 이것 하나가 할 일의 전부다. "
        "설정의 단추는 `sbtn` 을 밝혀 이 규칙을 비켜 간다 (2026-09-12)",
}


def _설정화면의_클래스() -> set[str]:
    """**설정 탭 전부**가 쓰는 클래스. 화면에서 읽는다 — 손으로 적으면
    탭이 하나 늘 때 목록만 낡는다(10장).

    처음에는 `settings.html` 하나만 읽어서, 이름은 「페이지 전체」 인데
    실제로는 카드 한 장이었다 — 2026-09-12 검토가 짚었다. 회차 상세의
    `.kpi .v` 가 그 틈으로 빠져 있었다.
    """
    화면 = list((ROOT / "app" / "templates").glob("settings*.html"))
    화면 += [ROOT / "app" / "templates" / "partials" / "settings_tabs.html",
            ROOT / "app" / "templates" / "admin_users.html"]
    쓰는것: set[str] = set()
    for f in 화면:
        if not f.exists():
            continue
        for m in re.finditer(r'class="([^"{}]+)"', f.read_text(encoding="utf-8")):
            쓰는것.update(m.group(1).split())
    return 쓰는것


def test_ts_02c_급을_올린_자리가_목록에_있다():
    """**올린 자리도 목록이 지킵니다** — 내린 자리와 같은 방식.

    범위는 **설정 탭 전부**입니다(내 정보 · 회차 관리 · 회차 상세 · 부서 ·
    점검 · 사용자 · 탭 줄). 처음에는 카드 하나만, 그다음에는 템플릿 하나만
    봐서 **다른 탭에서 급을 올리면 안 걸렸습니다.**

    「이 화면에 걸리는 규칙인가」 는 **화면이 쓰는 클래스**로 가릅니다 —
    선택자에 나오는 클래스가 전부 그 화면들에 있으면 이 페이지의 것입니다.
    `.calundated .hint` 처럼 같은 `.hint` 를 쓰는 남의 화면은 대상이
    아닙니다.

    봅니다 — ① 적어 둔 자리가 실제로 본문 단(14px) 이상인가 ② 까닭이
    적혀 있는가 ③ **CSS 에서 끌어낸 것이 두 목록 안에만 있는가** — 어느
    탭에 새 자리가 생겨도 걸립니다 ④ `.hint` 는 장식 단 그대로인가
    ⑤ 두 목록이 **서로 겹치지 않는가**(같은 자리가 「올린 것」 이면서
    「원래 그 급」 일 수 없습니다) ⑥ 실제로 읽은 것이 넉넉한가.

    **제목과 입력칸·표는 요소 이름으로 걸러집니다** — 4-0 의 눈금이 이미
    그 급에 두기로 한 것들이라 거기 있는 것은 올린 것이 아닙니다.
    **단추와 지표 숫자는 안 거릅니다** — 크기를 고를 여지가 있는 자리라
    이름으로 적어 둡니다.
    """
    본문 = 단.index("--fz-md")
    적은것 = {**올린자리, **눈금이정한자리}
    assert len(적은것) == len(올린자리) + len(눈금이정한자리), \
        "⑤ 두 목록에 같은 자리가 들어 있다"
    for sel, 이유 in 적은것.items():
        assert 단번호(sel) >= 본문, f"① {sel} 이 본문 단(14px)에 못 미친다"
        assert len(이유) > 5, f"② {sel} 의 까닭이 비었다"
    for sel, 이유 in 올린자리.items():
        assert len(이유) > 30, f"② 올린 자리 {sel} 의 까닭이 너무 짧다"
    assert 단번호(".fld .hint") < 본문, "④ .hint 가 함께 올라갔다"

    쓰는클래스 = _설정화면의_클래스()
    assert {"fld", "hint", "pwwarn", "kpi", "stabs"} <= 쓰는클래스, "⑥ 화면을 못 읽었다"

    본것, 올린것 = 0, set()
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _민낯()):
        크기 = re.search(r"font-size:\s*var\((--fz[\w-]*)\)", m.group(2))
        if not 크기:
            continue
        for sel in (" ".join(x.split()) for x in m.group(1).split(",")):
            이름 = set(re.findall(r"\.([\w-]+)", sel))
            if not 이름 or not 이름 <= 쓰는클래스:
                continue
            마지막 = sel.rsplit(" ", 1)[-1]
            if _요소인가(마지막, 제목태그) or _요소인가(마지막, 눈금이정한요소):
                continue
            본것 += 1
            if 단.index(크기.group(1)) >= 본문:
                올린것.add(sel)

    assert 본것 >= 15, f"⑥ 설정 탭의 자리를 {본것}개만 읽었다 — 검사가 새고 있다"
    assert 올린것 <= set(적은것), (
        f"③ 목록에 없는 자리가 본문 단 이상이다: {sorted(올린것 - set(적은것))}")
    assert set(적은것) <= 올린것, (
        f"③ 목록에만 있고 지금 화면에는 안 걸리는 자리: {sorted(set(적은것) - 올린것)}")


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
    # 사이드바의 위계는 크기가 아니라 색·굵기·들여쓰기다 (4-0 B안) —
    # 그룹은 잉크 600, 하위는 보조색. 둘 다 목록 하한(14px)이다.
    assert "font-weight:600" in 선언(".sidenav nav .g").replace(" ", "")
    assert "var(--ink-2)" in 선언(".sidenav .subs .n")
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
    ".dtabs .n", ".log s", ".dclose", ".fitem .more",
    ".fitem.link .ext", ".linkform .lbl", ".upnow .top .x", ".field label",
    ".card h3 .n", ".tchip .x", ".libsec > h3 .n", ".libsec > h3 em",
    ".subrow .branch", ".editbtn", ".trow.off .nm", ".draftrow .n", ".retired",
    ".prow .ind", ".dg-b li .ic", ".railadd", ".ph-h .n", ".sg-h .n",
    ".item.on .txt", ".item.on .txt .lead", ".item .scopeswap", ".item .itemdel",
    ".itemadd", ".c-note > .cx", ".sheetform .frow > label", ".sheetform legend",
    ".cal-cell.out .cal-d", ".cal-dot.done .cal-t", ".calday-d i",
    ".mt-one-meta label",
    # 새 껍데기 (단계 1) — 값 옆의 장식, 그리고 흐린 것이 곧 뜻인 것
    ".stabs .adm", ".kpi .v small", ".setting th", ".tickrow.done .ticklabel",
    # 회차 드롭다운의 ▾ — 옆의 회차 이름이 뜻을 다 진다 (단계 2)
    ".sidenav .pick .caret",
    # 목록의 완료 접힘 캐럿(▸) — 옆의 「완료 N건 보기」 가 뜻을 다 진다 (단계 3)
    ".ldone > summary::before",
    # 단계 4 — 드로어 머리 정의 표·연결 카드·목록 행·확인 요청·회의록 고르기.
    # 전부 옆의 값이 뜻을 다 지는 장식이다: 번호는 옆의 제목이(4-14),
    # 「라이브러리에서」·「(선택)」 은 옆의 값·라벨이, 「기간 N일」 은 옆의
    # 시작–마감이 지고, 나머지는 글자가 아니라 기호다(– · 화살표 · ▸ · 구분점).
    ".dtitle .runno", ".runno", ".mt-pick .mt-no",       # 번호 (옆이 제목)
    ".mt-sug-made .mt-no",                               # 〃 (이미 만든 제안의 링크)
    ".dmeta dd .fromlib",                                 # 상위 값 옆 「라이브러리에서」
    ".dmeta dd .mark",                                    # 호버 표식 ∨ · ✎
    ".dmeta dd .dates .sep", ".dmeta dd .dates .span",    # – 와 「기간 N일」
    ".relcard .rh .arrow", ".relcard .rh .n",             # 방향 기호와 건수
    ".trow.lrow .caret",                                  # ▸ — 행 오른쪽 끝 (4-14)
    ".budtbl .fold",                                      # 예산 구분 접기 ▾ — 옆의 구분 이름이 뜻을 진다 (UI 정리 판 1)
    ".revform .lbl .opt2",                                # 라벨 옆 「(선택)」
    # 단계 5 — 재정 표와 로그인 전 화면
    ".fintbl th",                                         # 표 머리 라벨 — 값이 아래 (속성 라벨 자리)
    ".barecard .bigcode",                                 # 404 같은 코드 — 옆의 문장이 뜻을 진다
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


def test_ts_09_사이드바_그룹_제목이_읽힌다():
    """그룹 제목을 흐림색으로 두면 제목이 아니라 장식으로 읽힌다 (4-0 B안).
    지금은 잉크 600 이다 — 홑 항목과 같은 급."""
    label = 선언(".sidenav nav .g")
    assert "var(--ink)" in label and "var(--ink-3)" not in label
    assert 단번호(".sidenav nav .g") >= 단.index("--fz-md")


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
    """주 목록은 같은 `cal.weeks` 를 그린다 — 거르는 곳이 하나다.
    격자는 partial 로 나갔다 (4-13) — 전체 페이지와 /calendar/partial 이 같은 것."""
    grid = (ROOT / "app" / "templates" / "partials" / "calendar_grid.html").read_text(
        encoding="utf-8")
    격자 = grid.index('<table class="cal-grid">')
    목록 = grid.index('<div class="calweeks">')
    assert grid.count("for week in cal.weeks") == 2, "격자와 주 목록이 같은 것을 안 쓴다"
    assert 격자 < 목록
    # 고르는 칸은 둘 위에 하나뿐이다 — 달과 무관해서 partial 밖에 있다
    cal = (ROOT / "app" / "templates" / "calendar.html").read_text(encoding="utf-8")
    assert cal.count("deptpick(") == 1
    assert grid.count("deptpick(") == 0
