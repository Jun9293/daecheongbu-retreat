"""목업 확정분 1단계 — 사이드바와 드로어 (2026-09-23 · CLAUDE.md 4-0 · 4-9).

값의 정본은 `docs/mockups/목업확정-2026-09-23.md` 의 A(사이드바)·B(드로어)다.
여기서 재는 것은 **그 값이 실제로 그 자리에 있는가**와, 새로 생긴 동작이
**막혀야 할 때 막히고 막히면 안 될 때 통과하는가** 다 (11-3 의 그 셋).

**목업을 안 따른 자리는 여기서도 잰다.** 안 따른 것이 세 자리인데(사이드바
글자 크기 · 꺼진 상태 칸의 색 · 달력 팝업의 모서리) 셋 다 **4-0 의 하한과
눈금**에 걸려서다. 그 사실을 시험이 들고 있지 않으면 다음 사람이 「목업대로
안 했네」 하고 되돌린다 — 되돌리는 순간 `test_typescale` 이 빨개지고, 그때는
왜 그런지가 아무 데도 안 적혀 있다.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import pytest

from app import models
from tests.conftest import app_session

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
CSS = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "js" / "drawer.js").read_text(encoding="utf-8")
PICK = (ROOT / "app" / "static" / "js" / "datepick.js").read_text(encoding="utf-8")
DRAWER = (ROOT / "app" / "templates" / "partials" / "drawer.html").read_text(encoding="utf-8")
목업 = (ROOT / "docs" / "mockups" / "목업확정-2026-09-23.md").read_text(encoding="utf-8")

OPEN = dt.date(2026, 8, 21)


def 민낯(글: str) -> str:
    """주석을 걷은 것 — **글자를 찾는 시험은 코드와 설명을 못 가린다** (10장).

    `/* */` 만 걷으면 `//` 줄 주석이 남는다. 실제로 이 파일을 쓰면서 그 틈으로
    한 번 빨개졌다: 「드로어가 이제 이 메뉴를 안 연다」 고 설명한 주석이
    금지한 이름을 담고 있었다.
    """
    글 = re.sub(r"/\*.*?\*/", "", 글, flags=re.S)
    return re.sub(r"(^|\s)//.*", "", 글)


def 선언(sel: str) -> str:
    본문 = 민낯(CSS)
    at = 본문.index(sel + "{")
    return 본문[at + len(sel) + 1 : 본문.index("}", at)]


# ── 가. 사이드바 (목업 A) ──────────────────────────────────────────────

def test64_a01_사이드바_폭은_토큰_하나이고_목업_값이다():
    """폭 176px · 머리줄 52px (목업 A). **박는 것은 토큰이고 쓰는 자리는 var 다** —
    두 곳에 적으면 한쪽만 고쳐진다 (9장이 숫자를 안 적는 이유)."""
    뿌리 = 민낯(CSS)[민낯(CSS).index(":root{"):]
    assert "--sw:176px" in 뿌리.replace(" ", ""), "사이드바 폭이 목업 A 의 176px 이 아니다"
    assert "--side-head:52px" in 뿌리.replace(" ", ""), "머리줄 높이가 목업 A 의 52px 이 아니다"
    # 쓰는 자리는 토큰을 부른다
    assert "width:var(--sw)" in 선언(".sidenav").replace(" ", "")
    assert "height:var(--side-head)" in 선언(".sidenav .brand").replace(" ", "")


def test64_a02_안쪽_여백과_항목_여백과_하위_들여쓰기가_목업이다():
    """안쪽 여백 14px 8px · 항목 여백 5px 8px · 하위 왼쪽 18px (목업 A)."""
    assert "padding:14px 8px 8px" in 선언(".sidenav")
    assert "padding:5px 8px" in 선언(".sidenav nav .g,.sidenav nav .single")
    assert "margin-left:18px" in 선언(".sidenav .subs")


def test64_a03_현재_항목은_accent_면에_accent_글자다():
    """목업 A — 현재 항목 accent-soft 면 + accent 글자 600."""
    홑 = 선언(".sidenav nav .single[aria-current=page]").replace(" ", "")
    하위 = 선언(".sidenav .subs .n[aria-current=page]").replace(" ", "")
    assert "background:var(--accent-soft)" in 홑 and "color:var(--accent)" in 홑
    assert "background:var(--accent-soft)" in 하위 and "color:var(--accent)" in 하위
    assert "font-weight:600" in 하위
    # 홑 항목은 `.single` 이 이미 600 이다 — 두 번 적지 않는다
    assert "font-weight:600" in 선언(".sidenav nav .g,.sidenav nav .single")


def test64_a04_글자_크기를_목업대로_안_내린_까닭이_적혀_있다():
    """목업 A 는 항목 13 · 묶음 제목 12 인데 **눈금의 목록 단에 둔다** (4-0).

    사이드바 항목은 혼자 뜻을 지는 글자라 하한이 걸린다 — `test_typescale` 의
    `ts_02`·`ts_09` 가 그 자리를 이름으로 잡고 있다. **왜 안 따랐는지를 그 자리에
    적어 두지 않으면** 다음 사람이 목업만 보고 되돌리고, 그때 빨개지는 시험이
    까닭을 말해 주지 않는다.
    """
    자리 = CSS[CSS.index("/* 급을 셋으로 가른다"):CSS.index(".sidenav nav .g,")]
    assert "목업 A" in 자리 and "하한" in 자리, "안 따른 까닭이 그 자리에 없다"
    # 그리고 실제로 눈금을 쓴다 — 숫자로 박혀 있지 않다
    assert "font-size:var(--fz-md)" in 선언(".sidenav nav .g,.sidenav nav .single")
    assert "font-size:var(--fz-md)" in 선언(".sidenav .subs .n")


def test64_a05_좁은_화면_갈래가_그대로다():
    """1280px 갈래 · 가장자리 띠 · 호버 없는 기기 — 폭만 바꿨지 길은 안 건드렸다.

    2026-09-12 에 휴대폰에서 이동 수단이 통째로 없어진 적이 있다 (4-0).
    """
    본문 = 민낯(CSS)
    assert "min-width:1280px" in 본문      # 펼침 고정이 그 폭에서 걸린다
    assert "body.sidepin .sidenav{transform:none" in 본문.replace("  ", " ")
    assert ".sidenav.peek{transform:none" in 본문
    assert "@media (hover:none){.sideedge{display:none}}" in 본문
    assert "@media (hover:none) and (pointer:coarse){body{cursor:pointer}}" in 본문


# ── 나. 드로어 폭 (목업 B) ─────────────────────────────────────────────

def test64_b01_폭_범위는_한_곳이고_목업_값이다():
    """기본 460 · 360~760 (목업 B). **범위를 정하는 곳은 `폭한계` 하나다** —
    CSS 에도 적으면 끌 때와 되돌릴 때가 갈린다."""
    m = re.search(r"const 폭한계 = \{최소: (\d+), 최대: (\d+), 기본: (\d+)\}", JS)
    assert m, "폭한계를 못 찾았다"
    assert (int(m.group(1)), int(m.group(2)), int(m.group(3))) == (360, 760, 460)
    # `--dw` 기본값이 그 기본과 같아야 한다 — 갈리면 열자마자 폭이 튄다
    assert "--dw:460px" in 민낯(CSS).replace(" ", "")
    # CSS 는 범위를 안 적는다
    drawer = 선언(".drawer")
    assert "min-width" not in drawer and "max-width" not in drawer, \
        "폭의 범위가 CSS 에도 적혀 있다 — 두 곳이 되면 갈린다"


def test64_b02_범위_밖의_남은_값을_범위_안으로_되돌린다():
    """기기에 남긴 값이 숫자가 아니거나 범위 밖이면 **범위 안으로 되돌린다** (목업 B).

    조용히 무시하면 옛 폭이 남은 사람만 화면이 다르게 뜨고 왜인지 알 수 없다.
    """
    # 되돌리는 셈을 그대로 옮겨 잰다 — 창이 넉넉할 때
    def 민다(w, 창=1600, 최소=360, 최대=760, 본문최소=360):
        위 = max(최소, min(최대, 창 - 본문최소))
        return round(max(최소, min(위, w)))

    assert 민다(100) == 360, "너무 작은 값이 최소로 안 올라온다"
    assert 민다(9999) == 760, "너무 큰 값이 최대로 안 내려온다"
    assert 민다(460) == 460, "범위 안의 값이 흔들린다"
    # 창이 좁으면 본문이 남을 만큼만 — 「밀고 들어온다」 가 「덮는다」 가 되면 안 된다
    assert 민다(760, 창=900) == 540, "좁은 창에서 본문 자리를 안 남긴다"
    assert 민다(760, 창=500) == 360, "아주 좁아도 최소 아래로는 안 내려간다"
    # 숫자가 아닌 값은 기본으로 — 코드가 그렇게 적혀 있는가
    assert "Number.isFinite(v)" in JS, "남은 값이 숫자인지 안 본다"


def test64_b03_드로어는_밀고_들어오고_닫힐_때도_다시_잰다():
    """겹치지 않고 밀고 들어온다 (4-9) — 열 때만이 아니라 **닫을 때도** 다시 잰다.

    닫히면 본문이 넓어지는데 좌표가 좁았던 폭으로 남으면 보드의 격자와 드래그가
    어긋난다 (9장의 격자 좌표).
    """
    assert "body.dopen{padding-right:var(--dw)}" in 민낯(CSS).replace(" ", "")
    닫는곳 = JS[JS.index("function closeDrawer()"):JS.index("function selectTab")]
    assert "afterLayout" in 닫는곳, "닫을 때 다시 재지 않는다"
    # 창 크기가 바뀔 때도 — 폭을 다시 밀고 좌표도 다시 잰다
    assert "addEventListener('resize'" in JS and "afterLayout" in JS


def test64_b04_좁은_화면과_목록의_붙박이는_그대로다():
    """820px 아래 규칙과 목록의 `.drawer.inline` 은 지금 동작을 지킨다 (4-9 · 4-14)."""
    본문 = 민낯(CSS)
    assert ".drawer{width:100%" in 본문.replace("  ", " "), "좁은 화면에서 전체를 안 덮는다"
    assert ".drawer.inline{position:static" in 본문
    assert "body.dopen:has(.drawer.inline){padding-right:0}" in 본문.replace(" ", "")


# ── 다. 상태 세 칸 버튼 (목업 B) ──────────────────────────────────────

@pytest.fixture
def 업무(admin_client):
    """드로어가 열 수 있는 업무 하나. `status` 를 바꿔 가며 쓴다."""
    with app_session() as db:
        # **아직 안 끝난 회차여야 한다** — 끝난 회차에는 지연이 없다 (4-10 · overdue_of).
        # 그래서 개회일을 오늘보다 뒤로 둔다: 마감만 지난 업무를 만들 수 있다
        열림 = dt.date.today() + dt.timedelta(days=30)
        r = models.Retreat(name="2026 여름수련회 Belong", start_date=열림,
                           end_date=열림 + dt.timedelta(days=2))
        db.add(r)
        db.flush()
        d = models.Department(retreat_id=r.id, key="sketch", name="4 스케치",
                              color_tag="#B95A83", sort_order=0)
        db.add(d)
        db.flush()
        lib = models.TaskLibrary(title="포스터 제작", kind="main", default_department_key="sketch",
                                 related_department_keys=[], related_library_ids=[],
                                 date_anchor="week", default_d_week=6, default_offset_days=0,
                                 default_span_days=3)
        db.add(lib)
        db.flush()
        run = models.TaskRun(library_id=lib.id, retreat_id=r.id, included=True,
                             department_id=d.id, d_week=6,
                             start_date=dt.date.today() - dt.timedelta(days=10),
                             end_date=dt.date.today() - dt.timedelta(days=3),
                             status="대기", run_no=1)
        db.add(run)
        db.commit()
        return {"retreat": r.id, "run": run.id, "dept": d.id}


def test64_c01_세_칸_버튼이_있고_메뉴를_안_연다():
    """고를 것이 셋뿐이라 메뉴를 펼칠 이유가 없다 (4-9 · 목업 B).

    **고를 수 있는 상태와 라벨은 여전히 한 곳(`PICKABLE`·`STATUS`)에서 나온다** —
    목록의 상태 칸은 그 메뉴를 그대로 쓴다(4-14). 갈린 것은 펼치는 모양뿐이다.
    """
    assert "class=\"statseg\"" in JS and "PICKABLE.map" in JS
    # 드로어는 이제 그 메뉴를 안 연다 — 칩 id 가 사라졌다
    assert "statchip" not in 민낯(JS), "드로어가 아직 상태 메뉴를 연다"
    # 목록은 그대로 쓴다
    assert "statusMenu: (el, runId) => statMenu(el, runId)" in JS
    # 바깥 클릭 판정에서도 그 자리를 뺐다 — `#drawer` 안이라 위에서 이미 안다
    origin = JS[JS.index("function originOf(target)"):JS.index("function originOf(target)") + 1200]
    assert "#statchip" not in origin


def test64_c02_켜진_칸과_꺼진_칸이_갈린다():
    """켜진 칸 accent 면 + 700 + 점, 꺼진 칸은 회색 점 (목업 B).

    **점 색을 인라인 `background` 로 주지 않는다** — 인라인은 껐다는 규칙을 이겨서
    꺼진 칸까지 상태색이 된다. `--dot` 로 받고 켜고 끄는 것은 CSS 가 가른다.
    """
    on = 선언(".statseg button.on").replace(" ", "")
    assert "background:var(--accent-soft)" in on and "font-weight:700" in on
    assert "background:var(--rule-2)" in 선언(".statseg .cv").replace(" ", "")
    assert "background:var(--dot,currentColor)" in 선언(".statseg button.on .cv").replace(" ", "")
    assert "--dot:${esc(STATUS[key].color)}" in JS, "점 색을 --dot 으로 안 넘긴다"
    assert 'style="background:${esc(STATUS[key].color)}"' not in JS.split("statseg")[1][:600]


def test64_c03_저장된_지연은_아무것도_안_켜고_한_줄로_말한다(admin_client, 업무):
    """4-3 이 저장값에서 걷어냈지만 **남아 있으면 그대로 보인다** (4-9).

    말없이 「대기」 를 켜면 화면이 저장된 값을 고쳐 보여주는 것이 된다.
    """
    with app_session() as db:
        run = db.get(models.TaskRun, 업무["run"])
        run.status = "지연"          # 앱이 뜰 때 되돌리기 전의 옛 행을 흉내낸다
        db.commit()
    r = admin_client.get(f"/board/task/{업무['run']}", headers={"Accept": "application/json"})
    assert r.status_code == 200
    assert r.json()["status"] == "지연", "서버가 저장값을 고쳐 보낸다"
    # 화면은 그 값을 셋 중 하나로 못 켜고, 그 사실을 한 줄로 말한다
    assert 'id="dstale"' in DRAWER
    자리 = JS[JS.index("const 저장된 = d.status"):JS.index("if (d.can_edit) $('statseg')")]
    assert "PICKABLE.includes(저장된)" in 자리, "판정을 저장값으로 안 한다"
    assert "d.badge" not in 자리, "배지로 가르면 기한 지난 멀쩡한 업무가 이 줄을 단다"


def test64_c04_저장_중에는_다시_못_누르고_실패하면_되돌린다():
    """두 번 누르면 두 번 저장되고 늦게 온 답이 이겨 화면과 DB 가 갈린다 (5-0).

    실패하면 **이전 칸으로 되돌리고 화면에 말한다** — 조용히 삼키면 바꾼 줄 안다.
    """
    자리 = JS[JS.index("async function 칸을누른다"):JS.index("/* 상태를 바꾸면")]
    assert "if (상태저장중" in 자리, "저장 중에 다시 누르는 것을 안 막는다"
    assert "b.disabled = true" in 자리
    assert "catch (err)" in 자리 and "이전" in 자리, "실패해도 안 되돌린다"
    assert "finally" in 자리, "실패한 뒤 다시 누를 수 없게 잠긴 채로 남는다"
    # `setStatus` 는 **던진다** — 안 던지면 부른 쪽이 실패를 알 수 없다
    st = JS[JS.index("async function setStatus"):JS.index("async function setStatus") + 900]
    assert "throw Object.assign" in st, "실패를 삼켜서 되돌릴 수가 없다"
    # 메뉴 쪽은 되돌릴 칸이 없으므로 받아 둔다 — 안 받으면 처리 안 된 거절이 남는다
    assert ".catch(() => {})" in JS


# ── 라. 날짜 달력 팝업 (목업 B) ───────────────────────────────────────

def test64_d01_달력_팝업은_드로어_밖에서도_부를_수_있다():
    """2단계 업무 추가가 **같은 부품**을 쓴다 (4-9 · 6-7).

    두 벌이 되면 고르는 차례와 맞바꿈이 두 곳에서 갈린다.
    """
    assert "window.DatePick = {open," in PICK
    assert "datepick.js" not in JS, "드로어 안에 또 만들지 않았는가"
    for f in ["board.html", "calendar.html", "tasks.html"]:
        글 = (ROOT / "app" / "templates" / f).read_text(encoding="utf-8")
        assert "js/datepick.js" in 글, f"{f} 가 그 부품을 안 싣는다"
        # **`<script>` 자리로 잰다** — 글자로 찾으면 설명 주석이 먼저 걸린다.
        # 실제로 calendar.html 의 머리말이 그 이름을 담고 있어 한 번 빨개졌다 (10장)
        태그 = re.findall(r"""<script src="\{\{ static\('js/([\w.]+)'\)""", 글)
        assert "datepick.js" in 태그 and "drawer.js" in 태그, f"{f} 의 script 줄을 못 읽었다"
        assert 태그.index("datepick.js") < 태그.index("drawer.js"), \
            f"{f} 에서 drawer.js 보다 늦게 실린다 — 열 때 없다"


def test64_d02_고르는_차례와_맞바꿈이_목업대로다():
    """시작 → 마감 → (둘 다면) 시작부터 다시. 시작보다 앞을 누르면 맞바꾼다 (목업 B)."""
    자리 = PICK[PICK.index("function 날을눌렀다"):PICK.index("function open(")]
    assert "!start || (start && end)" in 자리, "둘 다 고른 뒤 다시 누르면 시작부터가 아니다"
    assert "v < start" in 자리 and "상태.end = start" in 자리, "맞바꾸지 않는다"


def test64_d03_안내_줄_셋이_목업_그대로다():
    """목업 B 의 세 줄 — 시작 전 · 마감 전 · 다 고른 뒤."""
    assert "시작일을 누르세요." in PICK
    assert "마감일을 누르세요 — 같은 날을 한 번 더 누르면 하루 업무입니다." in PICK
    assert "하루 업무" in PICK and "일간 기간 업무" in PICK
    # 그 문구가 목업 파일에 실제로 있는 말인가 — 지어내지 않았다
    assert "시작일을 누르세요." in 목업


def test64_d04_저장을_눌러야_반영되고_실패하면_안_닫힌다():
    """「저장」 을 눌러야 반영되고 시작일이 없으면 흐려진다 (목업 B).

    **실패하면 안 닫는다** — 닫으면 고쳐진 줄 알고 넘어간다 (5-0).
    전에는 칸 하나씩 고르는 즉시 저장해서, 기간을 줄이는 동안 마감이 시작보다
    앞서는 순간이 생기고 그 사이에 닫으면 그대로 남았다.
    """
    assert "dpsave" in PICK and "if (!상태.start) return" in PICK
    assert "btn.disabled = true" in PICK, "저장 중에 다시 누를 수 있다"
    assert "if (됐나 === false)" in PICK and "저장하지 못했습니다" in PICK
    # 드로어는 이제 칸 두 개로 즉시 저장하지 않는다
    assert "id=\"dstart\"" not in JS and "id=\"dend\"" not in JS
    assert "start.onchange = saveDates" not in JS


def test64_d05_기간_줄이_목업대로_말한다(admin_client, 업무):
    """「기간」(같은 날이면 「날짜」) + 날짜 + n일간/하루, 지연이면 앞에 「마감 n일 지남」.

    **며칠 늦었는지는 서버가 센다** (4-3) — 화면이 다시 세면 두 벌이 된다.
    """
    r = admin_client.get(f"/board/task/{업무['run']}", headers={"Accept": "application/json"})
    답 = r.json()
    # **배지 안이 아니라 따로 실어 보낸다** — 배지에 칸을 늘렸더니 배지를 통째로
    # 견주는 시험이 곧바로 빨개졌다(2026-09-23 · 검토가 잡음). 그 값은 이미
    # `paint_of` 의 `overdue_days` 라, 배지에도 넣으면 한 값이 두 자리에 있게 된다
    assert 답["overdue_days"] > 0, "기한이 지난 업무인데 0 이다"
    assert "late_days" not in 답["badge"], "배지에 칸을 늘렸다"
    assert "마감 ${늦음}일 지남" in JS
    assert "d.overdue_days" in JS, "화면이 날짜를 다시 센다"
    assert "기간라벨" in JS and "'날짜'" in JS


# ── 마. 관련팀 저장 → 알림 (목업 B) ───────────────────────────────────

def test64_e01_저장이_먼저이고_알림이_그다음이다():
    """관련팀은 **저장하는 즉시 지정된다** — 알림은 알리기만 한다 (4-9 · 목업 B).

    한 단추에 묶으면 알리기 싫어서 저장을 안 하게 되고, 그러면 관련팀이 비어
    4-4 의 고스트 바와 4-10 의 근거가 함께 빈다.
    """
    자리 = JS[JS.index("$('relpicksave').onclick"):JS.index("function 알릴팀을고른다")]
    저장 = 자리.index("/related-departments")
    알림 = 자리.index("알릴팀을고른다")
    assert 저장 < 알림, "알림을 저장보다 먼저 묻는다"
    설명 = JS[JS.index("function 알릴팀을고른다"):JS.index("function 결과를보인다")]
    assert "관련팀은 알림과 상관없이 저장하는 즉시 지정되어" in 설명
    assert "알림 없이 저장" in 설명, "하나도 안 고르고 넘어가는 길이 없다"


def test64_e02_알림_일부가_실패하면_결과에_적는다(admin_client, 업무):
    """**조용히 삼키지 않는다** — 간 팀과 못 간 팀을 나눠 돌려준다 (5-1 의 그 자리).

    사람이 아무도 없는 팀은 「보냄」 이 아니라 **못 간 것**이다. 다 됐다고 말해
    놓고 절반만 가면 보낸 사람은 갔다고 믿는다.
    """
    r = admin_client.post(
        f"/board/task/{업무['run']}/related-departments/notify",
        json={"keys": ["sketch"], "save_id": "e02aaaaaaaaa"},
    )
    assert r.status_code == 200, r.text
    답 = r.json()
    # 이 회차의 스케치에는 (관리자 말고) 사람이 없다 — 못 간 쪽에 이름과 까닭이 온다
    assert 답["sent"] == [] and len(답["failed"]) == 1
    assert 답["failed"][0]["name"] == "4 스케치" and 답["failed"][0]["why"]
    # 화면도 그것을 「알림」 줄에 적는다
    assert "못 보냄" in JS


def test64_e03_같은_저장을_두_번_눌러도_한_통만_선다(admin_client, 업무):
    """`dedupe_key` 가 (업무, 팀, **저장 식별값**) 셋이다 (2026-09-24 사람이 정함).

    같은 저장을 두 번 누르거나 재시도하면 식별값이 같으므로 한 통만 선다.
    **다른 저장이면 다시 간다** — 그쪽은 `test65_d01` 이 잰다.

    **그리고 두 번째는 「보냄」 이 아니라 「이미 알림」 이다** (4-11 — 「보냈는가」
    를 부풀리지 않는다). 처음에는 둘 다 `sent` 로 세어, 아무것도 안 갔는데
    화면이 「보냄」 이라고 말했다(2026-09-23 검토가 잡음)."""
    with app_session() as db:
        # 스케치에 사람을 하나 붙인다
        u = models.User(name="정하윤", phone_number="01000000001", role="general")
        db.add(u)
        db.flush()
        db.add(models.UserDepartment(user_id=u.id, department_id=업무["dept"], dept_role="member"))
        db.commit()
        uid = u.id
    답들 = []
    for _ in range(2):   # **같은 식별값** — 두 번 누른 것과 같다
        r = admin_client.post(
            f"/board/task/{업무['run']}/related-departments/notify",
            json={"keys": ["sketch"], "save_id": "e03samesave"},
        )
        assert r.status_code == 200, r.text
        답들.append(r.json())
    assert 답들[0]["sent"] == ["sketch"] and 답들[0]["already"] == []
    assert 답들[1]["sent"] == [] and 답들[1]["already"] == ["sketch"],         "두 번째인데 「보냄」 이라고 말한다 — 안 간 것을 갔다고 적으면 안 된다"
    assert 답들[1]["already_names"], "화면이 쓸 이름이 없다"
    with app_session() as db:
        수 = db.query(models.Notification).filter(
            models.Notification.user_id == uid,
            models.Notification.dedupe_key == f"related:{업무['run']}:sketch:e03samesave",
        ).count()
    assert 수 == 1, f"같은 저장을 두 번 눌렀더니 알림이 {수}건이다"


def test64_e04_모르는_부서_키는_거절한다(admin_client, 업무):
    """셋 중 둘만 가면 보낸 사람은 셋 다 갔다고 믿는다 (5-1 · 같은 규칙)."""
    r = admin_client.post(
        f"/board/task/{업무['run']}/related-departments/notify",
        json={"keys": ["없는팀"], "save_id": "e04aaaaaaaaa"},
    )
    assert r.status_code == 400


def test64_e05_결과는_세_줄이고_더_적지_않는다():
    """관련팀 / 알림 / 업무 목록 — `+`/`−` 도 「무엇이 바뀌었다」 도 초록 안내도 없다.

    그 셋이 이미 그것을 말한다. 같은 사실을 두 곳에 적으면 갈린다.
    """
    자리 = JS[JS.index("function 결과를보인다"):]
    자리 = 자리[:자리.index("\n}") + 2]
    assert "관련팀을 저장했습니다" in 자리
    for 줄 in ["<dt>관련팀</dt>", "<dt>알림</dt>", "<dt>업무 목록</dt>"]:
        assert 줄 in 자리
    assert "위 팀들의 업무 목록에 추가됨" in 자리
    # 세 줄 말고 더 안 적는다
    assert 자리.count("<dt>") == 3, "결과 표에 줄이 더 있다"


# ── 바. 진단 한 줄 (목업 B) ───────────────────────────────────────────

def test64_f01_진단은_한_줄이고_눌러서_편다():
    """평소에는 한 줄 — 색 점 + 판정 이름 + 첫 근거 + 캐럿 (4-9 · 목업 B).

    근거가 대여섯 줄이라 늘 펼쳐 두면 아래의 「+ 하위 업무 추가」 가 밀린다.
    """
    assert 'id="dgB" hidden' in DRAWER, "접힌 채로 시작하지 않는다"
    assert 'id="dgOne"' in DRAWER and 'aria-expanded="false"' in DRAWER
    assert "$('dgH').onclick" in JS
    # **판정과 근거는 4-10 그대로다** — 여기서 문장을 새로 짓지 않는다
    앞 = JS.index("const 첫근거 =")
    자리 = JS[앞:JS.index("const rows =", 앞)]
    assert "첫근거.text" in 자리 and "g.summary" in 자리
    assert "판정" not in 자리.replace("판정 중", ""), "화면이 판정 문구를 지어낸다"


def test64_f02_펼치면_근거_전체가_그대로다():
    """접는 것은 **보이는 만큼**이고 판정·근거는 4-10 그대로다."""
    자리 = JS[JS.index("function renderDiag"):JS.index("// '다시 분석'")]
    assert "g.verdict" in 자리 and "g.reasons" in 자리 and "g.summary" in 자리


# ── 사. --row-line 토큰 ───────────────────────────────────────────────

def test64_g01_row_line_토큰이_섰고_넘김에서_빠졌다():
    """앞 판이 규칙만 적고 넘겨 둔 토큰이다 (4-0 · `docs/이름-넘김.txt`).

    **쓰는 자리는 보드를 다시 그리는 단계다** — 그동안 죽은 토큰으로 안 걸리게
    `test_stage63` 이 이름과 까닭을 하나 들고 있다.
    """
    assert "--row-line:#ECEDF1" in 민낯(CSS).replace(" ", "")
    넘김 = (ROOT / "docs" / "이름-넘김.txt").read_text(encoding="utf-8")
    assert "--row-line" not in 넘김, "토큰을 만들었는데 넘김에 남아 있다"
    s63 = (ROOT / "tests" / "test_stage63.py").read_text(encoding="utf-8")
    assert "아직안쓰는토큰" in s63 and "--row-line" in s63


# ── 아. 커밋 전 검토가 짚어 고친 것 ───────────────────────────────────

def test64_h01_달력_팝업은_스크롤하면_닫는다():
    """목록의 상태 메뉴와 **같은 규약의 나머지 절반**이다 (4-14).

    처음에는 「화면 밖으로 안 나간다」 만 가져오고 주석에는 「같은 규약」 이라고
    적었다 — `position:fixed` 라 안 닫으면 팝업만 제자리에 남고, 목록에서는
    행 안의 드로어와 함께 페이지가 스크롤하므로 **엉뚱한 자리에서 날짜를
    고치게 된다.**

    **낱말만 잰다** — 실제로 스크롤해서 닫히는지는 브라우저의 일이라
    `docs/checks/drawer.js` 가 잰다.
    """
    dp = 민낯((ROOT / "app" / "static" / "js" / "datepick.js").read_text(encoding="utf-8"))
    for 무늬 in ("addEventListener('scroll'", "addEventListener('resize'",
                "removeEventListener('scroll'", "removeEventListener('resize'"):
        assert 무늬 in dp, f"{무늬} 가 없다 — 열고 닫는 짝이 맞아야 한다"


def test64_h02_점검이_업무_상태를_바꿔_놓지_않는다():
    """`started_at` 은 「되돌려도 지우지 않는다」 (8장) — 점검이 꺼진 칸을
    누르면 그 업무가 **영구히** 「착수함」 이 되고 4-10 의 판정과 4-11 의
    「방치」 알림이 함께 달라진다. 세 화면 · 두 계정 · 자가시험이면 한 번
    돌릴 때 스무 번 넘게 눌린다.

    그래서 **지금 켜진 칸을 다시 누른다** — 같은 자리를 재되 자국이 안 남는다.
    """
    점검 = (ROOT / "docs" / "checks" / "drawer.js").read_text(encoding="utf-8")
    자리 = 점검[점검.index("const 켠칸"):][:700]
    assert "classList.contains('on')" in 자리
    assert "!b.classList.contains('on')" not in 자리, "꺼진 칸을 눌러 상태를 바꾼다"
    assert "started_at" in 자리 or "started_at" in 점검[max(0, 점검.index("const 켠칸") - 900):], \
        "왜 켜진 칸을 누르는지가 그 자리에 안 적혀 있다"
