"""3단계 — 보드를 목업 D · F 로 (구간 다섯 · 후속 칸 · 접힘 · 합침 · 팝업).

| 무엇을 재나 | 어디 |
|---|---|
| 구간이 다섯이고 칸에서 세어 만든다 | `가` |
| 후속 칸 — 최소 3 · 최대 D+26주 · 늦은 쪽까지 | `나` |
| 접힘과 합침 — **합친 바는 끌 수 없다** | `다` |
| 날짜 없는 업무는 바를 안 그리고 점선 표시를 둔다 | `라` |
| 축 상한 밖 바는 `→` 와 **실제 날짜**를 말한다 | `마` |
| 팝업의 한 줄을 만드는 곳이 하나다 | `바` |
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest

from app import models
from app.domain import board as board_view
from app.domain import dweek
from tests.conftest import app_session

ROOT = pathlib.Path(__file__).resolve().parents[1]
보드JS = (ROOT / "app" / "static" / "js" / "board.js").read_text(encoding="utf-8")
팝업JS = (ROOT / "app" / "static" / "js" / "taskpop.js").read_text(encoding="utf-8")
조각 = (ROOT / "app" / "templates" / "board.html").read_text(encoding="utf-8")

OPEN = dt.date(2026, 8, 21)
CLOSE = dt.date(2026, 8, 23)


def 축(*, first_week: int = 13, after: int = dweek.MIN_AFTER_WEEKS) -> board_view.Axis:
    return board_view.Axis(OPEN, CLOSE, first_week, after_weeks=after)


# ── 가. 구간 다섯 ───────────────────────────────────────────────────

def test72_a01_구간이_다섯이다():
    keys = [s["key"] for s in 축(first_week=20).sections()]
    assert keys == ["plan", "prep", "d2", "retreat", "after"]


def test72_a02_기획과_준비는_한_자리가_가른다():
    a = 축(first_week=20)
    assert a.section_of_week(dweek.PLANNING_UNTIL_D_WEEK + 1) == "plan"
    assert a.section_of_week(dweek.PLANNING_UNTIL_D_WEEK) == "prep"


def test72_a03_기획이_없으면_그_구간도_없다():
    """**빈 구간을 만들지 않는다** — 칸에서 세어 만들기 때문이다."""
    keys = [s["key"] for s in 축(first_week=13).sections()]
    assert "plan" not in keys
    assert keys == ["prep", "d2", "retreat", "after"]


def test72_a04_구간의_칸_수를_따로_적지_않는다():
    """`sections` 가 `headers` 에서 세므로 둘이 갈릴 수가 없다."""
    a = 축(first_week=20)
    assert sum(s["span"] for s in a.sections()) == len(a.headers()) == a.total


# ── 나. 후속 칸 ─────────────────────────────────────────────────────

def test72_b01_후속_칸이_수련회_바로_뒤에_선다():
    a = 축()
    assert a.column_of(CLOSE) == a.retreat_column
    assert a.column_of(CLOSE + dt.timedelta(days=1)) == a.retreat_column + 1


def test72_b02_최소와_최대가_있다():
    """마감으로만 정하면 폐회 직후 회차에서 축이 한 칸에 멈춘다 — 그러면
    「오늘」 단추가 **옮길 오늘 선이 축에 없다**."""
    assert board_view._after_weeks(CLOSE, [], CLOSE) == dweek.MIN_AFTER_WEEKS
    많이 = 축(after=999)
    assert len(많이.after_sundays) == dweek.LAST_AFTER_WEEK


def test72_b03_오늘과_마감_중_늦은_쪽까지_간다():
    class 가짜:
        def __init__(self, end):
            self.start_date = end
            self.end_date = end

    늦은마감 = CLOSE + dt.timedelta(days=70)
    오늘 = CLOSE + dt.timedelta(days=7)
    n1 = board_view._after_weeks(CLOSE, [가짜(늦은마감)], 오늘)
    # 마감이 훨씬 뒤 → 마감이 이긴다
    assert n1 >= 10
    # 오늘이 훨씬 뒤 → 오늘이 이긴다 (마감이 하나도 없어도)
    먼오늘 = CLOSE + dt.timedelta(days=84)
    assert board_view._after_weeks(CLOSE, [], 먼오늘) >= 12


def test72_b04_오늘이_축_밖이면_오늘_선을_안_그린다():
    """`column_of` 는 **범위 밖도 가까운 쪽 끝에 붙이므로**(9장) 그것만으로는
    「오늘이 축에 있다」 를 알 수 없다 — 그대로 그리면 회차가 한참 지난 뒤에도
    오늘 선이 마지막 칸에 붙어 거짓말을 한다."""
    a = 축()
    아주뒤 = a.after_sundays[-1] + dt.timedelta(days=90)
    assert board_view._축안에(a, 아주뒤) is False
    assert board_view._축안에(a, OPEN) is True


# ── 다. 접힘과 합침 ─────────────────────────────────────────────────

def 하위(a, z, title, run_id, **덮어쓰기):
    row = {"col_start": a, "col_end": z, "title": title, "run_id": run_id,
           "status": "대기", "kind": "sub", "background": "#fff", "border": "#000",
           "owner_color": "#123", "meta_line": f"{title} 메타", "undated": False,
           "beyond": False}
    row.update(덮어쓰기)
    return row


def test72_c01_같은_칸의_하위끼리_바_하나로_합친다():
    lanes = board_view.collapsed_lanes([하위(1, 3, "가", 1), 하위(1, 3, "나", 2)])
    assert len(lanes) == 1 and len(lanes[0]) == 1
    바 = lanes[0][0]
    assert 바["title"] == "가, 나"
    assert 바["merged"] is True
    # **합친 바에는 `data-run` 이 없다** — 그것이 「못 끈다」 의 구조다
    assert 바["run_id"] is None
    assert 바["run_ids"] == "1 2"


def test72_c02_일부만_겹치면_줄을_더한다():
    """겹친 채로 그리면 뒤엣것이 앞엣것을 덮어 **있는 업무가 사라진다.**"""
    lanes = board_view.collapsed_lanes([하위(1, 4, "가", 1), 하위(2, 6, "나", 2)])
    assert len(lanes) == 2


def test72_c03_안_겹치면_같은_줄에_넣는다():
    lanes = board_view.collapsed_lanes([하위(1, 3, "가", 1), 하위(3, 5, "나", 2)])
    assert len(lanes) == 1 and len(lanes[0]) == 2


def test72_c04_날짜_없는_하위는_눕히지_않는다():
    """놓을 칸이 없다 — 점선 표시가 그 자리를 대신한다."""
    lanes = board_view.collapsed_lanes([하위(1, 2, "없", 1, undated=True)])
    assert lanes == []


def test72_c05_합친_바는_끌_수_없다():
    """**막는 쪽**이다 (2026-09-23 사람이 정함). 끄는 자리가 `.bar[data-run]`
    을 찾으므로 `data-run` 이 없는 합친 바에서는 애초에 시작하지 않는다."""
    assert "closest('.bar[data-run]')" in 보드JS
    # 화면도 합친 바에는 그 속성을 안 단다
    assert "{% if b.run_id %} data-run=" in 조각


def test72_c06_합친_바도_연결선이_찾을_수_있다():
    """합친 바가 그 run 들의 **유일한 산 자리**다 — 안 보면 연결선이 숨은
    바에서 출발해 아무 데도 안 그려진다 (4-5)."""
    assert 'data-runs~="${runId}"' in 보드JS


# ── 라. 날짜 없는 업무 ──────────────────────────────────────────────

@pytest.fixture
def 회차(admin_client):
    with app_session() as db:
        r = models.Retreat(name="2026 여름수련회 Belong", start_date=OPEN, end_date=CLOSE)
        db.add(r)
        db.flush()
        db.add(models.Department(retreat_id=r.id, key="chongmu", name="1 총무팀",
                                 sort_order=0))
        db.commit()
        return r.id


def test72_d01_날짜_없는_업무는_바가_아니라_점선_표시다(회차, admin_client):
    """전에는 `start_date or open_date` 라 **수련회 칸에 보통 바**가 섰다 —
    거기 실제로 잡힌 업무와 구별이 안 됐다 (봐둘것 BJ-d)."""
    res = admin_client.post("/board/add/new", json={
        "title": "날짜 없는 업무", "department_key": "chongmu", "kind": "main"})
    assert res.status_code == 200, res.text
    화면 = admin_client.get("/board").text
    assert "날짜 없음 · 누르면 드로어에서 날짜를 정합니다" in 화면

    # **그 줄에 바가 없는 것까지 잰다** — 전에는 `"nodate" in 자리` 하나였고
    # 독스트링이 말한 「바가 없다」 를 **어디서도 안 쟀다**(커밋 전 검토).
    # 그 줄만 잘라 본다: 다음 `<div class="row` 앞까지가 그 행이다
    # **그 줄에 바가 없는 것까지 잰다** — 전에는 `"nodate" in 자리` 하나였고
    # 독스트링이 말한 「바가 없다」 를 **어디서도 안 쟀다**(커밋 전 검토).
    # 그 줄만 잘라 본다 — 제목 앞의 `<div class="row` 부터 다음 행 앞까지
    제목자리 = 화면.index("날짜 없는 업무")
    시작 = 화면.rindex('<div class="row ', 0, 제목자리)
    그줄 = 화면[시작:]
    # 마지막 행이면 다음 행이 없다 — 그때는 시트 끝까지 본다
    다음 = 그줄.find('<div class="row ', 10)
    if 다음 < 0:
        다음 = 그줄.find('</div>', 그줄.find('class="lane"'))
    그줄 = 그줄[:다음]
    assert "날짜 없는 업무" in 그줄
    assert 'class="nodate"' in 그줄
    assert 'class="bar ' not in 그줄, "날짜가 없는데 바가 그려졌다"


def test72_d02_도메인이_그_줄에_undated_를_단다(회차, admin_client):
    admin_client.post("/board/add/new", json={
        "title": "날짜 없는 업무", "department_key": "chongmu", "kind": "main"})
    with app_session() as db:
        r = db.get(models.Retreat, 회차)
        view = board_view.build(db, r)
    줄 = [row for blk in view["departments"] for row in blk["rows"]
          if row["title"] == "날짜 없는 업무"]
    assert 줄 and 줄[0]["undated"] is True


# ── 마. 축 상한 밖 ──────────────────────────────────────────────────

def test72_e01_상한_밖은_마지막_칸에_붙되_그렇다고_말한다():
    a = 축()
    먼날 = a.after_sundays[-1] + dt.timedelta(days=60)
    assert a.column_of(먼날) == a.total       # 가까운 쪽 끝 (9장)
    assert a.beyond_of(먼날) is True          # 그 칸이 마감이 아니다


def test72_e02_화면이_그_바에_화살표를_단다():
    assert '{%- if row.beyond %}<span class="beyond"' in 조각


def test72_e03_상한_밖_바는_제목이_안_끊겨도_팝업을_연다():
    """그러지 않으면 그 업무의 **실제 날짜를 말할 자리가 어디에도 없다** (4-1)."""
    assert "const 축밖 = !!el.querySelector('.beyond');" in 보드JS
    assert "if (!끊김 && !합침 && !축밖) return null;" in 보드JS


# ── 바. 팝업 ───────────────────────────────────────────────────────

def test72_f01_팝업의_한_줄을_만드는_곳이_하나다(회차):
    """보드와 달력이 같은 부품을 쓴다 — 화면마다 조립하면 두 벌이 된다."""
    with app_session() as db:
        r = db.get(models.Retreat, 회차)
        dept = r.departments[0]
        lib = models.TaskLibrary(title="포스터", kind="main",
                                 default_department_key=dept.key)
        db.add(lib)
        db.flush()
        run = models.TaskRun(library_id=lib.id, retreat_id=r.id, department_id=dept.id,
                             start_date=dt.date(2026, 8, 1), end_date=dt.date(2026, 8, 5),
                             status="대기", run_no=1)
        db.add(run)
        db.commit()
        줄 = board_view.popup_meta(run, dt.date(2026, 7, 1))
    assert "2026-08-01 – 2026-08-05" in 줄
    assert "1 총무팀" in 줄


def test72_f02_하루짜리는_한_날짜만_적는다(회차):
    with app_session() as db:
        r = db.get(models.Retreat, 회차)
        dept = r.departments[0]
        lib = models.TaskLibrary(title="하루", kind="main", default_department_key=dept.key)
        db.add(lib)
        db.flush()
        run = models.TaskRun(library_id=lib.id, retreat_id=r.id, department_id=dept.id,
                             start_date=dt.date(2026, 8, 1), end_date=dt.date(2026, 8, 1),
                             status="대기", run_no=1)
        db.add(run)
        db.commit()
        줄 = board_view.popup_meta(run, dt.date(2026, 7, 1))
    assert 줄.startswith("2026-08-01 · ")


def test72_f03_지연이면_며칠인지_적는다(회차):
    """바에는 `!` 하나뿐이라(4-1) **며칠인지는 팝업이 말한다.**"""
    with app_session() as db:
        r = db.get(models.Retreat, 회차)
        dept = r.departments[0]
        lib = models.TaskLibrary(title="늦음", kind="main", default_department_key=dept.key)
        db.add(lib)
        db.flush()
        run = models.TaskRun(library_id=lib.id, retreat_id=r.id, department_id=dept.id,
                             start_date=dt.date(2026, 8, 1), end_date=dt.date(2026, 8, 1),
                             status="대기", run_no=1)
        db.add(run)
        db.commit()
        줄 = board_view.popup_meta(run, dt.date(2026, 8, 6))
    assert "지연 5일" in 줄


def test72_f04_팝업은_보드와_달력이_같은_부품이다():
    assert "window.TaskPop" in 팝업JS
    # 달력에서만 「상세 열기」 — 보드에는 스크롤해서 갈 자리가 있다
    assert "opts && opts.상세열기" in 팝업JS
    assert "상세 열기" in 팝업JS


def test72_f05_originOf_가_팝업_자리를_안다():
    """모르면 팝업을 만지는 순간 「바깥 클릭」 이 되어 드로어가 닫힌다.

    **낱말만 잰다** — 동작은 `docs/checks/drawer.js` 가 잰다(갈래 ㉔ 이 그
    자리를 실제로 눌러 드로어가 열린 채인지 본다). 여기서 붙드는 것은
    **그 자리가 두 곳에 다 적혀 있는가** 뿐이다.
    """
    drawer = (ROOT / "app" / "static" / "js" / "drawer.js").read_text(encoding="utf-8")
    assert "taskpop: at('.taskpop')," in drawer
    assert "어느쪽이든('taskpop')" in drawer


def _코드만(js: str) -> str:
    """주석을 걷어낸 코드. **글자를 찾는 시험은 코드와 설명을 못 가린다**(10장) —
    이 파일들은 「저것과 다른 부품이다」 를 주석으로 설명하므로 그 이름을 담는다."""
    import re as _re
    js = _re.sub(r"/\*.*?\*/", "", js, flags=_re.S)
    return _re.sub(r"(?<![:\w])//.*", "", js)


def test72_f06_팝업은_업무_추가_팝업과_다른_부품이다():
    """`data-addpop` 은 업무를 **만드는 폼**이고 이것은 **읽는 카드**다."""
    assert "addpop" not in _코드만(팝업JS)
    추가JS = (ROOT / "app" / "static" / "js" / "board_add.js").read_text(encoding="utf-8")
    assert "taskpop" not in _코드만(추가JS)


# ── 사. 그 밖에 목업이 정한 것 ─────────────────────────────────────

def test72_g01_지연은_바_글자_앞_느낌표_하나다():
    """「지연 n일」 은 바가 좁을수록 제목을 밀어낸다 (4-1).

    **바 매크로만 본다** — 좁은 폭의 목록 행(`.mrow`)은 바가 아니라 목록
    항목이고, 거기에는 옆에서 제목을 밀어낼 바가 없다(9장의 그 화면).
    """
    바자리 = 조각[조각.index("{% macro bar(row)"):조각.index("{% macro pup(")]
    # 바 매크로와 접힌 줄의 lanebar 둘 다 `!` 를 쓴다
    assert 바자리.count('<span class="flag">!</span>') == 2
    # **글자 배지가 남아 있지 않다** — 조건절의 `'지연'` 은 판정이지 화면 글이 아니다.
    # 좁은 폭의 목록(`.mlist`)은 **바가 아니라 목록 항목**이라 이 규칙 밖이다 —
    # 거기에는 옆에서 제목을 밀어낼 바가 없다(9장의 그 화면)
    보드자리 = 조각[:조각.index('<div class="mlist"')]
    assert 'class="flag">지연' not in 보드자리


def test72_g02_부서_줄은_완료_n분의_n_건과_지연만_적는다():
    """완료 막대는 **완료를 눈에 띄게 하는 것**이라 4-3 과 반대로 간다."""
    assert "완료 {{ dept.done }}/{{ dept.count }}건" in 조각
    assert "지연 {{ dept.late }}건" in 조각


def test72_g03_범례에_지연이_있고_순서가_목업대로다():
    자리 = 조각[조각.index('class="legend"'):조각.index("</div>", 조각.index('class="legend"'))]
    순서 = [x for x in ("Main", "하위", "일정", "완료", "지연", "관련업무", "연결선")
          if x in 자리]
    assert 순서 == ["Main", "하위", "일정", "완료", "지연", "관련업무", "연결선"]


def test72_g04_펼침_상태는_기기에_남는다():
    """서버는 늘 접힌 채로 낸다 — 남은 값을 서버가 모르므로 펼친 채로 내면
    접어 둔 사람의 화면이 한 번 깜빡인다 (4-1)."""
    assert "localStorage" in 보드JS and "dcb.board.open." in 보드JS
    assert "' folded' if row.sub_count" in 조각


def test72_g05_접기_손잡이는_행을_열지_않는다():
    """둘 다 `.lc[data-go]` 안이라 그냥 두면 **행을 여는 쪽이 먼저 돈다** —
    같은 요소의 리스너는 등록 순서대로 불려 `stopPropagation` 으로는 못 막는다."""
    assert "const 보드안여는곳 = '.fold, .subn';" in 보드JS
    assert "if (e.target.closest(보드안여는곳)) return;" in 보드JS


def test72_g06_고스트_줄은_접힘_고리에_안_걸린다():
    """**고스트도 `depth=1` 이지만 접힌 Main 의 하위가 아니다** — 남의 부서
    업무다(4-4). `data-parent` 를 달면 그 부서의 **마지막 Main 을 접을 때
    그 뒤에 이어진 고스트 줄까지 함께 숨는다**(고스트가 마지막 하위 바로 뒤에
    온다). 화면에서 실제로 그 자리를 밟았다 — 31줄이 전부 그 표시를 달고 있었다.
    """
    assert "{%- if row.depth and not row.ghost %} data-parent=" in 조각
    # 접고 펴는 고리가 그 표시로 멈춘다 — 표시가 없으면 거기서 선다
    assert "next.classList.contains('sub') && next.dataset.parent" in 보드JS


# ── 아. 커밋 전 검토가 짚은 자리 ────────────────────────────────────

def test72_d03_좁은_폭_목록도_날짜_없는_묶음을_따로_낸다(회차, admin_client):
    """**넓은 폭만 고치고 좁은 폭을 놓칠 뻔했다** — 봐둘것 BJ-d 가 `make_row`
    **와** `_by_week` 둘을 적어 두었는데 앞엣것만 고치고 닫았다고 적었다.
    좁은 폭에서는 날짜 없는 업무가 「수련회 기간」 에 개회일을 달고 섰다.
    """
    admin_client.post("/board/add/new", json={
        "title": "날짜 없는 업무", "department_key": "chongmu", "kind": "main"})
    with app_session() as db:
        r = db.get(models.Retreat, 회차)
        view = board_view.build(db, r)
    묶음 = {g["key"]: g for g in view["mobile_groups"]}
    assert "nodate" in 묶음, "날짜 없는 업무가 따로 안 묶인다"
    assert 묶음["nodate"]["label"] == "날짜 없는 업무"
    그줄 = 묶음["nodate"]["rows"][0]
    # **없으면 없다고 낸다** — 개회일로 채우면 화면이 「8/21」 이라고 적는다
    assert 그줄["start"] is None and 그줄["end"] is None
    # 수련회 묶음에는 안 섞인다
    assert all(x["title"] != "날짜 없는 업무"
               for g in view["mobile_groups"] if g["key"] != "nodate"
               for x in g["rows"])


def test72_h01_마법사_칸에는_후속이_안_섞인다():
    """보드의 축이 뒤로 늘어난 것이 **업무를 놓을 칸**까지 따라오면
    「수련회 기간 · 8/30」 이라는 거짓 이름의 칸이 생긴다 (봐둘것 BJ-g)."""
    slots = board_view.planning_slots(OPEN, CLOSE)
    assert [x for x in slots if x["kind"] == "after"] == []
    assert sum(1 for x in slots if x["label"].startswith("수련회 기간")) == 1


def test72_h02_연결_강조가_합친_바를_본다():
    """합친 바가 그 run 들의 **유일한 산 자리**다 — 안 보면 `anchor` 가 숨은
    바에만 붙어 `offsetParent` 걸러내기에서 빠지고 **선이 통째로 안 그려진다.**
    4-5 는 「관련 업무가 하나도 없어도 선택 표시는 반드시 나타나야 한다」 다.
    """
    assert "sheet.querySelectorAll('.bar[data-run], .bar[data-runs]')" in 보드JS
    assert "ids.includes(Number(runId))" in 보드JS


def test72_h03_상위_Main_을_함께_편다():
    """4-7 의 그 차례다 — 부서만 펴면 하위가 **여전히 접힌 줄 안**에 있다."""
    assert "if (위 && 위.classList.contains('folded')) 접거나편다(위, true);" in 보드JS


def test72_h04_필터가_접힌_줄의_바에도_걸린다():
    """눕는 바는 Main **행 안**이라 `.row` 훑기가 안 닿는다 — 안 걸면
    「미완료만」 을 켜도 완료된 하위 바가 남는다 (4-8)."""
    assert "sheet.querySelectorAll('.bar.sl').forEach(bar =>" in 보드JS
    assert "bar.hidden = !남길까;" in 보드JS


def test72_h05_팝업_한_줄을_짓는_코드가_화면에_없다():
    """**`data-pop` 을 다는 곳이 합친 바뿐이라 끊긴 바는 JS 쪽을 타고 있었다** —
    「되돌림」 이라고 적어 두었지만 주 경로였다. 이제 보통 바도 단다.
    """
    # 보통 바 매크로도 `data-pop` 을 단다
    바자리 = 조각[조각.index("{% macro bar(row)"):조각.index("{% macro lanebar(")]
    assert "data-pop=" in 바자리
    # 화면에는 문장을 **짓는** 코드가 없다 — 주석을 걷어내고 본다(10장)
    코드 = _코드만(보드JS)
    for 짓는말 in ("'날짜 없음'", "join(' · ')", "overdue_days ?"):
        assert 짓는말 not in 코드, f"화면이 팝업 문장을 다시 짓는다 ({짓는말})"


def test72_h06_손가락_기기에서_둘째_탭이_흘러간다():
    """**첫 탭이 팝업이고 두 번째 탭이 드로어다** (4-1). 전에는 늘
    `stopPropagation()` 을 걸어 드로어를 여는 리스너가 **영영 안 돌았다** —
    몇 번을 탭해도 팝업만 다시 떴다.
    """
    assert "let 팝업띄운바 = null;" in 보드JS
    assert "if (팝업띄운바 === 대상) {" in 보드JS


def test72_h07_수련회_면이_머리부터_끝까지다():
    """목업 D — 머리만 칠하면 본문에서 그 기간이 어디인지 안 보인다."""
    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    assert ".retreatband{" in css
    assert "background:var(--span-retreat)" in css.split(".retreatband{")[1][:200]
    assert '<div class="retreatband"' in 조각
    assert "수련회띠를놓는다" in 보드JS
