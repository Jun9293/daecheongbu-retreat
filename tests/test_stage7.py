"""화면 다듬기 판 — 목록·달력·재정·진행·회의록 (+ 마무리 후속 1-b·1-d).

새 기능이 아니라 쓰면서 걸린 것을 고친 판이다. 막는 코드마다 막히는 쪽과
뚫리는 쪽을 함께 잰다.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest
from sqlalchemy import select

from app import models
from app.domain.budget import build_budget_summary, no_receipt_entries, refund_entries
from tests.conftest import app_session, login_as, make_user

TODAY = dt.date.today()
ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")


@pytest.fixture
def money_retreats(admin_client):
    """지난 회차(부서 A행) + 이번 회차(부서 B행 + 지출 하나) — 1-b·1-d 용."""
    with app_session() as db:
        old = models.Retreat(name="돈 지난 회차", start_date=TODAY - dt.timedelta(days=400),
                             end_date=TODAY - dt.timedelta(days=397))
        db.add(old)
        db.flush()
        old_dept = models.Department(retreat_id=old.id, key="hebron",
                                     name="5 헤브론", color_tag="#4A8A5C", sort_order=0)
        db.add(old_dept)

        cur = models.Retreat(name="돈 이번 회차", meal_subsidy_per_person=8000,
                             start_date=TODAY + dt.timedelta(days=30),
                             end_date=TODAY + dt.timedelta(days=33))
        db.add(cur)
        db.flush()
        dept = models.Department(retreat_id=cur.id, key="hebron",
                                 name="5 헤브론", color_tag="#4A8A5C", sort_order=0)
        db.add(dept)
        db.flush()
        entry = models.ExpenseEntry(
            retreat_id=cur.id, department_id=dept.id,
            expense_date=TODAY, amount=10_000, subsidy_amount=10_000,
            payer_name="박민준")
        db.add(entry)
        # 예산 표의 구분·항목 행 시험용 — 한 구분에 항목 둘 (4-c)
        db.add_all([
            models.BudgetCategory(retreat_id=cur.id, level1="홍보", level2="포스터",
                                  level3="인쇄물", planned_amount=300_000, sort_order=0),
            models.BudgetCategory(retreat_id=cur.id, level1="홍보", level2="굿즈",
                                  level3="명찰 키트", planned_amount=900_000, sort_order=1),
        ])
        db.commit()
        return {"old_dept": old_dept.id, "retreat": cur.id,
                "dept": dept.id, "entry": entry.id}


# ════════════════════════════════════════════════════════════════════
# 1-b. 지출의 부서는 이 회차의 행이어야 한다
# ════════════════════════════════════════════════════════════════════


def test7_b01_다른_회차의_부서_행으로는_지출을_못_붙인다(admin_client, money_retreats):
    admin_client.get(f"/board?retreat_id={money_retreats['retreat']}")
    denied = admin_client.post("/expenses/create", data={
        "amount": "5000", "department_id": str(money_retreats["old_dept"]),
    })
    assert denied.status_code == 400                     # 막는 쪽

    ok = admin_client.post("/expenses/create", data={
        "amount": "5000", "department_id": str(money_retreats["dept"]),
    }, follow_redirects=True)
    assert ok.status_code == 200                         # 이 회차의 행은 통과


# ════════════════════════════════════════════════════════════════════
# 1-d. 지출 취소 — 지우지 않는다 (0장 · 7-4)
# ════════════════════════════════════════════════════════════════════


def test7_d01_취소는_행을_남기고_합계에서_뺀다(admin_client, money_retreats):
    rid, eid = money_retreats["retreat"], money_retreats["entry"]
    admin_client.get(f"/board?retreat_id={rid}")

    with app_session() as db:
        retreat = db.get(models.Retreat, rid)
        before = build_budget_summary(db, retreat=retreat)
        assert before.uncategorized_spent == 10_000
        rows_before = db.scalar(select(models.ExpenseEntry.id).where(
            models.ExpenseEntry.retreat_id == rid)) is not None

    r = admin_client.post(f"/expenses/{eid}/cancel", follow_redirects=True)
    assert r.status_code == 200

    with app_session() as db:
        retreat = db.get(models.Retreat, rid)
        entry = db.get(models.ExpenseEntry, eid)
        assert entry is not None and entry.canceled_at is not None   # 행이 남는다
        after = build_budget_summary(db, retreat=retreat)
        assert after.uncategorized_spent == 0            # 집행액이 줄었다
        # 환급·영수증 경고에서도 빠진다 — 홈 숫자와 같은 정의 (4-15)
        assert refund_entries(db, retreat) == []
        assert no_receipt_entries(db, retreat) == []
        # ActivityLog 에 남는다
        acted = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "지출_취소",
            models.ActivityLog.target_id == eid)).first()
        assert acted is not None

    # 취소 행은 「전체」 에 남고 챙길 일 필터에는 안 나온다
    page = admin_client.get("/expenses")
    assert "취소됨" in page.text and "되살리기" in page.text
    unpaid = admin_client.get("/expenses?filter=unpaid")
    assert "취소됨" not in unpaid.text

    # 되살리기 — 같은 단추의 토글
    r = admin_client.post(f"/expenses/{eid}/cancel", follow_redirects=True)
    assert r.status_code == 200
    with app_session() as db:
        retreat = db.get(models.Retreat, rid)
        entry = db.get(models.ExpenseEntry, eid)
        assert entry.canceled_at is None
        assert build_budget_summary(db, retreat=retreat).uncategorized_spent == 10_000


def test7_d03_회차_상세의_지출_완료_숫자도_취소를_뺀다(admin_client, money_retreats):
    """settings 의 「지출 완료 N건 · X원」 — summary 는 빼는데 이 둘만 품으면
    같은 화면의 두 숫자가 갈린다 (검토자 고쳐야 함 1)."""
    from app.routers.settings import _expense_stats

    rid, eid = money_retreats["retreat"], money_retreats["entry"]
    with app_session() as db:
        assert _expense_stats(db, rid) == (1, 10_000)

    admin_client.get(f"/board?retreat_id={rid}")
    admin_client.post(f"/expenses/{eid}/cancel", follow_redirects=True)
    with app_session() as db:
        assert _expense_stats(db, rid) == (0, 0)          # 취소 행이 안 낀다


def test7_d02_삭제_단추가_화면에_없다():
    """옛 「삭제」 가 남으면 0장과 부딪힌다 — 취소·되살리기만 있다."""
    html = (ROOT / "app" / "templates" / "expenses.html").read_text(encoding="utf-8")
    assert "/delete" not in html
    assert "/cancel" in html and "되살리기" in html


# ════════════════════════════════════════════════════════════════════
# 3. 달력 — 달 전환이 위아래로 미끄러진다 (4-13)
# ════════════════════════════════════════════════════════════════════


def test7_c01_달_전환이_위아래_미끄럼이다():
    """새 격자를 먼저 붙이고 둘을 함께 옮긴 뒤 옛것을 뗀다 — 깜빡임 없음."""
    js = (ROOT / "app" / "static" / "js" / "calendar.js").read_text(encoding="utf-8")
    assert "slideSwap" in js and "translateY" in js
    assert "duration: 280" in js                          # 250~300ms 안
    # 새 격자 먼저, 옛것은 겹쳐 두고 — 갈아 끼우는 순간이 화면에 없다
    assert js.index("old.replaceWith(next)") < js.index("swap.appendChild(old)")
    # reduced-motion 이면 움직임 없이 바로 바뀐다 — 전환 시간 0
    assert "prefers-reduced-motion" in js
    reduce_branch = js.index("if (!swap || !dir || reduce || !next.animate)")
    assert reduce_branch < js.index("const from = dir === 'next'")
    # 휠과 화살표가 같은 길(goMonth)로 간다 — partial fetch·replaceState 유지
    assert js.count("goMonth(") >= 3
    assert "replaceState" in js and "/calendar/partial?" in js


def test7_c02_드로어는_전환_자리_밖에_있다():
    """전환 중에도 ?task= 드로어가 살아 있으려면 드로어가 calswap 밖이어야 한다."""
    html = (ROOT / "app" / "templates" / "calendar.html").read_text(encoding="utf-8")
    grid_at = html.index('{% include "partials/calendar_grid.html" %}')
    assert html.index('id="calswap"') < grid_at \
        < html.index("</div>", grid_at) \
        < html.index('{% include "partials/drawer.html" %}')


# ════════════════════════════════════════════════════════════════════
# 2. 목록 — 행 클릭 · 정렬 · 부서 드롭다운 · 배지 자리 (4-14)
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def list_retreat(admin_client):
    """정렬·필터를 잴 수 있는 최소 목록 — 부서 둘 · 업무 셋."""
    with app_session() as db:
        retreat = models.Retreat(name="목록 회차",
                                 start_date=TODAY + dt.timedelta(days=60),
                                 end_date=TODAY + dt.timedelta(days=63))
        db.add(retreat)
        db.flush()
        hebron = models.Department(retreat_id=retreat.id, key="hebron",
                                   name="5 헤브론", color_tag="#4A8A5C", sort_order=0)
        sketch = models.Department(retreat_id=retreat.id, key="sketch",
                                   name="4 스케치", color_tag="#B95A83", sort_order=1)
        db.add_all([hebron, sketch])
        db.flush()

        def task(title, *, start, dept, no):
            lib = models.TaskLibrary(title=title, kind="main", default_d_week=5)
            db.add(lib)
            db.flush()
            run = models.TaskRun(
                library_id=lib.id, retreat_id=retreat.id, included=True,
                department_id=dept.id, d_week=5, run_no=no,
                start_date=start, end_date=start + dt.timedelta(days=7),
                status="대기")
            db.add(run)

        task("나중 업무", start=TODAY + dt.timedelta(days=20), dept=hebron, no=1)
        task("가장 이른 업무", start=TODAY + dt.timedelta(days=5), dept=sketch, no=2)
        task("다음 업무", start=TODAY + dt.timedelta(days=10), dept=hebron, no=3)
        db.commit()
        return retreat.id


def _titles(page_text: str) -> list[str]:
    """행 순서대로 제목만 — 화면이 그린 순서가 곧 정렬이다."""
    return re.findall(r'<span class="nm"><span class="runno">\d+</span>([^<\n]+)',
                      page_text)


def test7_l01_행을_눌러_펼친다_버튼_줄은_없다(admin_client, list_retreat):
    admin_client.get(f"/board?retreat_id={list_retreat}")
    page = admin_client.get("/tasks")
    assert page.status_code == 200
    # 버튼 줄이 없다 — 행 전체가 그 일을 하고 캐럿이 상태를 보인다 (4-14)
    assert "lopen" not in page.text and "lfoot" not in page.text
    assert 'class="cell caretc"' in page.text and "▸" in page.text
    # ?task= 는 그대로다 (보드·달력과 같은 이름 — 알림 바로가기)
    with app_session() as db:
        run = db.scalars(select(models.TaskRun).where(
            models.TaskRun.retreat_id == list_retreat)).first()
    opened = admin_client.get(f"/tasks?task={run.id}")
    assert f'data-open-task="{run.id}"' in opened.text
    # **여는 길을 재는 것은 여기가 아니다.** 전에는 `".nm" in js` 로 쟀는데
    # 그 글자는 meta()·onTitle() 도 쓰므로 여는 규칙을 어떻게 바꿔도
    # 초록이었다(10장 — 글자를 찾는 시험). 여는 규칙은 stage13 의
    # r01·r01b 가 「안 여는 자리」 로 재고, 여기서는 탭만 본다.
    js = (ROOT / "app" / "static" / "js" / "tasks.js").read_text(encoding="utf-8")
    assert "selectTab('rules')" in js and "lopen" not in js


def test7_l02_정렬_두_축과_방향(admin_client, list_retreat):
    admin_client.get(f"/board?retreat_id={list_retreat}")

    base = admin_client.get("/tasks")                    # 기본 — 시작일 오름
    assert _titles(base.text)[:3] == ["가장 이른 업무", "다음 업무", "나중 업무"]
    # 기본 정렬에서 「날짜」 를 누르면 내림으로 — 누를 때마다 오름 ↔ 내림
    assert "sort=date&dir=desc" in base.text

    down = admin_client.get("/tasks?sort=date&dir=desc")
    assert _titles(down.text)[:3] == ["나중 업무", "다음 업무", "가장 이른 업무"]
    assert "sort=date&dir=asc" in down.text              # 한 번 더 누르면 오름

    named = admin_client.get("/tasks?sort=name&dir=asc")
    assert _titles(named.text)[:3] == ["가장 이른 업무", "나중 업무", "다음 업무"]

    weird = admin_client.get("/tasks?sort=???&dir=???")  # 모르는 값 — 기본으로
    assert _titles(weird.text)[:3] == ["가장 이른 업무", "다음 업무", "나중 업무"]


def test7_l03_부서_드롭다운이_키로_거른다(admin_client, list_retreat):
    admin_client.get(f"/board?retreat_id={list_retreat}")
    page = admin_client.get("/tasks")
    # 드롭다운 하나 — 값은 부서 **키**다 (2장). 부서 칩 줄은 없다
    assert 'id="ldept"' in page.text
    assert 'value="hebron"' in page.text and 'value="sketch"' in page.text

    only = admin_client.get("/tasks?dept=sketch")
    assert _titles(only.text) == ["가장 이른 업무"]


# ════════════════════════════════════════════════════════════════════
# 4. 재정 — 여백 · 등록 버튼 · 구분/항목 행 (7장)
# ════════════════════════════════════════════════════════════════════


def test7_f01_재정_여백이_다른_화면과_같다():
    """지출·예산이 정의 안 된 settingwrap 을 써서 본문이 사이드바에 붙었다.

    기준은 다른 화면들이 쓰는 `.setting` — padding 20px 24px (<820px 14px),
    retreat.css 의 그 규칙 하나다. 눈대중이 아니라 같은 클래스를 쓴다.
    """
    for name in ("expenses.html", "budget.html"):
        html = (ROOT / "app" / "templates" / name).read_text(encoding="utf-8")
        assert '<main class="setting finwrap">' in html
        assert "settingwrap" not in html
    assert re.search(r"\.setting\{[^}]*padding:20px 24px", CSS)


def test7_f02_등록_폼은_접힌_채_시작하고_버튼으로_열린다(admin_client, money_retreats):
    admin_client.get(f"/board?retreat_id={money_retreats['retreat']}")
    # 필터에 걸린 행이 0건이어도 접혀 있다 — 전에는 이때 저절로 펼쳐졌다
    page = admin_client.get("/expenses?filter=meal")
    assert '<details class="addbox" id="addbox">' in page.text
    assert 'id="addbox" open' not in page.text
    assert "btnlike" in page.text and "+ 지출 등록" in page.text
    assert "다음 영수증 번호" in page.text                # 버튼 옆에 그대로
    js = (ROOT / "app" / "static" / "js" / "expenses.js").read_text(encoding="utf-8")
    assert "exp-close" in js                              # 닫기 단추


def test7_f03_예산_구분_행과_항목_라벨이_갈린다(admin_client, money_retreats):
    """UI 정리 판 1 에서 항목 별도 줄이 없어졌다 — 첫 세부항목 줄의 라벨이다 (1-c)."""
    admin_client.get(f"/board?retreat_id={money_retreats['retreat']}")
    page = admin_client.get("/budget")
    assert 'class="l1row"' in page.text and 'class="l2row"' not in page.text
    assert page.text.count('class="itemlbl"') == 2          # 항목(포스터·굿즈)마다 하나
    # 4-0 의 색만 쓴다 — 구분은 완료 배지 채움, 항목 라벨은 보조색 글자
    assert re.search(r"\.fintbl tr\.l1row td\{[^}]*background:var\(--st-done-bg\)[^}]*font-weight:600", CSS)
    assert re.search(r"\.budtbl \.itemlbl\{[^}]*color:var\(--ink-2\)", CSS)


# ════════════════════════════════════════════════════════════════════
# 5. 회의록 — 본문 최대 폭 없음 (9장)
# ════════════════════════════════════════════════════════════════════


def test7_m01_회의록_본문에_최대_폭이_없다():
    """9장이 「본문에 최대 폭을 두지 않는다」 로 정했는데 이 화면만 900px 였다.

    1920px 에서 본문이 창 끝까지 가는 것은 max-width 가 없다는 것과 같다 —
    회의록 계열(.mt-*)에 max-width 숫자 규칙이 하나도 없어야 한다.
    """
    for m in re.finditer(r"\.mt-[\w-]+[^{]*\{([^}]*)\}", CSS):
        assert "max-width" not in m.group(1), m.group(0)


# ════════════════════════════════════════════════════════════════════
# 6. 수련회 진행 — 이름 한 곳 · 구역 띠 · 할 일 글자 (5장)
# ════════════════════════════════════════════════════════════════════


def test7_p01_사이드바와_화면_제목이_같은_한_곳에서_나온다(admin_client, money_retreats):
    from app.domain.live import SCREEN_TITLE

    assert SCREEN_TITLE == "총무팀 일정"
    base = (ROOT / "app" / "templates" / "retreat_base.html").read_text(encoding="utf-8")
    live = (ROOT / "app" / "templates" / "live.html").read_text(encoding="utf-8")
    assert "{{ live_title }}" in base and "{{ live_title }}" in live
    assert "진행 화면" not in base                        # 옛 이름이 안 남았다
    admin_client.get(f"/board?retreat_id={money_retreats['retreat']}")
    page = admin_client.get("/live")
    assert page.status_code == 200
    assert page.text.count("총무팀 일정") >= 2            # 사이드바 + 화면 제목


def test7_p02_할_일_글자가_잉크색이다():
    """시간별 할 일(.pgm .nm)은 --ink, 시각(.pgm .t)은 보조 — 할 일이 앞에 온다."""
    assert re.search(r"\.pgm \.nm\{[^}]*color:var\(--ink\)", CSS)
    assert ".pgm.done .nm{color" not in CSS               # 지나간 것도 흐리지 않는다
    assert re.search(r"\.pgm \.t\{[^}]*color:var\(--ink-2\)", CSS)


def test7_p03_구역_제목_띠와_여백():
    assert re.search(r"\.ph-h\{[^}]*background:var\(--st-done-bg\)", CSS)
    assert re.search(r"\.ph-h h2\{[^}]*font-weight:600", CSS)
    assert ".phase{margin-bottom:36px}" in CSS


def test7_l04_좁은_화면에서_배지가_아래로():
    """<820px 에서 메타·배지가 이름 아래로 내려간다 (4-14) — CSS 로 잰다."""
    block_at = CSS.index("좁은 화면 — 메타와 배지가 이름 아래로")
    media_at = CSS.rindex("@media (max-width:820px)", 0, block_at)
    narrow = CSS[media_at:block_at + 600]
    assert ".trow.lrow{flex-wrap:wrap" in narrow          # 배지 칸이 다음 줄로
    assert ".trow.lrow .main{flex:1 1 100%" in narrow     # 이름 줄이 한 줄을 다 쓴다
    # 넓은 화면 기본은 이름 오른쪽 메타 — 한 줄이다
    assert ".trow.lrow .main{display:flex;align-items:center" in CSS
