"""노션 업무 들여오기 마무리 — 뺀 업무로 가는 길과 결산 홈의 한 줄.

들여오기가 옛 업무 102 를 `included=false` 로 내렸다. 보드·목록·달력·홈이
전부 `included` 로 거르므로 그 줄들은 **어느 화면에도 안 뜨는데**, 거기 걸린
논의와 첨부는 그대로 살아 있다 — 가는 길이 없으면 0장이 「다음 담당자에게
전달되는 유일한 경로」 라고 한 그 기록이 사라진 것과 같다.

그리고 끝난 회차에 완료가 0 이면 결산 홈이 「미완료 233건 · 정리 필요」 라고
말하는데, 안 한 것이 아니라 **누른 적이 없는** 것이다 (5-6 의 그 자리).
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest

from app import models
from app.domain import home as home_mod
from app.domain import tasklist
from tests.conftest import app_session, login_as, make_user

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
TASKS_HTML = (ROOT / "app" / "templates" / "tasks.html").read_text(encoding="utf-8")
HOME_HTML = (ROOT / "app" / "templates" / "home.html").read_text(encoding="utf-8")

TODAY = dt.date(2026, 7, 1)


def _민낯(글: str) -> str:
    """주석을 걷어낸 CSS — 찾는 말이 설명글에 있으면 시험이 거짓말을 한다 (10장)."""
    return re.sub(r"/\*.*?\*/", "", 글, flags=re.S)


def _민낯진자(글: str) -> str:
    """주석(`{# … #}`)을 걷어낸 화면.

    **이 시험이 그 함정을 한 번 밟았다** — 분기를 `{% if False %}` 로 망가뜨려
    놓고도 초록이었다: 찾던 `home.carried_only` 가 바로 위 **주석**에 있었다
    (10장 · 네 번 당한 그것). 고장을 심어 보지 않았으면 몰랐을 자리다.
    """
    return re.sub(r"\{#.*?#\}", "", 글, flags=re.S)


def _업무(db, retreat, title, *, included=True, status="대기", dept_key=None):
    lib = models.TaskLibrary(
        title=title, kind="main", default_department_key=dept_key or "",
        related_department_keys=[], related_library_ids=[],
        date_anchor="week", default_d_week=13, default_offset_days=0,
        default_span_days=6)
    db.add(lib)
    db.flush()
    dept = None
    if dept_key:
        dept = next(d for d in retreat.departments if d.key == dept_key)
    run = models.TaskRun(
        library_id=lib.id, retreat_id=retreat.id, included=included, d_week=13,
        department_id=dept.id if dept else None,
        start_date=dt.date(2026, 5, 24), end_date=dt.date(2026, 5, 31),
        status=status)
    db.add(run)
    db.flush()
    return run


# ════════════════════════════════════════════════════════════════════
# 1. 뺀 업무를 늘어놓는 자리 (목록 화면 아래)
# ════════════════════════════════════════════════════════════════════


def test58_a01_뺀_것만_그_자리에_서고_하는_업무는_안_선다(db, sample_retreat):
    """**두 목록이 서로를 안 넘본다.** 뺀 줄이 보통 목록에 섞이면 안 하기로
    한 업무가 할 일처럼 보이고, 반대로 하는 업무가 저 아래 접힌 상자에 들어가면
    아무도 안 본다."""
    산것 = _업무(db, sample_retreat, "포스터 제작")
    뺀것 = _업무(db, sample_retreat, "작년 현수막 재활용", included=False)
    db.commit()

    view = tasklist.build(db, sample_retreat, today=TODAY)
    assert [r["run_id"] for r in view.excluded_rows] == [뺀것.id]
    보통 = [r["run_id"] for r in view.rows + view.done_rows]
    assert 산것.id in 보통 and 뺀것.id not in 보통


def test58_a02_상태_칩은_뺀_목록을_안_거른다(db, sample_retreat):
    """상태 칩은 **하는 업무**를 가르는 축이고(4-3), 안 하기로 한 것은 그 축
    밖이다. 「대기」 를 골랐다고 뺀 목록이 비면 그 길이 필터 하나로 사라진다."""
    뺀것 = _업무(db, sample_retreat, "작년 현수막 재활용", included=False, status="대기")
    _업무(db, sample_retreat, "포스터 제작", status="완료")
    db.commit()

    for state in ("", "done", "wait"):
        view = tasklist.build(db, sample_retreat, today=TODAY, state=state)
        assert [r["run_id"] for r in view.excluded_rows] == [뺀것.id], \
            f"상태 {state!r} 에서 뺀 목록이 달라졌다"


def test58_a03_부서_범위는_두_목록이_같이_따른다(db, sample_retreat):
    """부서 드롭다운이 곧 범위다 (4-14). 두 목록이 다른 범위를 쓰면 화면이
    무엇을 보여 주고 있는지 말해 주지 못한다."""
    홍보 = _업무(db, sample_retreat, "뺀 홍보 업무", included=False, dept_key="hongbo")
    _업무(db, sample_retreat, "뺀 찬양 업무", included=False, dept_key="chanyang")
    db.commit()

    전체 = tasklist.build(db, sample_retreat, today=TODAY, dept="all")
    assert len(전체.excluded_rows) == 2
    한팀 = tasklist.build(db, sample_retreat, today=TODAY, dept="hongbo")
    assert [r["run_id"] for r in 한팀.excluded_rows] == [홍보.id]
    내부서 = tasklist.build(db, sample_retreat, today=TODAY, dept="depts",
                         my_keys={"chanyang"})
    assert [r["title"] for r in 내부서.excluded_rows] == ["뺀 찬양 업무"]


def test58_a03b_소속_외는_보통_행처럼_흐리다(db, sample_retreat):
    """1장 확정 사항 「소속 외 표시 — 숨기지 않고 흐리게」. 바로 위 목록의 남의
    부서 행은 흐린데 여기만 선명하면 한 화면이 두 규칙을 쓴다(커밋 전 검토 G2).
    총무팀(dim=False)은 전부 선명하다."""
    _업무(db, sample_retreat, "뺀 홍보 업무", included=False, dept_key="hongbo")
    _업무(db, sample_retreat, "뺀 찬양 업무", included=False, dept_key="chanyang")
    _업무(db, sample_retreat, "산 홍보 업무", dept_key="hongbo")
    db.commit()

    리더 = tasklist.build(db, sample_retreat, today=TODAY, dept="all", my_keys={"chanyang"})
    흐림 = {r["title"]: r["dim"] for r in 리더.excluded_rows}
    assert 흐림 == {"뺀 홍보 업무": True, "뺀 찬양 업무": False}
    # 보통 행과 같은 판단이다
    assert [r["dim"] for r in 리더.rows] == [True]
    총무 = tasklist.build(db, sample_retreat, today=TODAY, dept="all",
                        my_keys={"chanyang"}, dim=False)
    assert not any(r["dim"] for r in 총무.excluded_rows)


def test58_a03c_정렬_단추를_같이_따른다(db, sample_retreat):
    """이름순을 골랐는데 뺀 목록만 날짜순이면 그 단추가 화면의 절반에만 걸린다."""
    for 이름 in ("나 업무", "가 업무", "다 업무"):
        _업무(db, sample_retreat, 이름, included=False)
    db.commit()
    올림 = tasklist.build(db, sample_retreat, today=TODAY, sort="name", dir="asc")
    assert [r["title"] for r in 올림.excluded_rows] == ["가 업무", "나 업무", "다 업무"]
    내림 = tasklist.build(db, sample_retreat, today=TODAY, sort="name", dir="desc")
    assert [r["title"] for r in 내림.excluded_rows] == ["다 업무", "나 업무", "가 업무"]


def test58_a04_배지를_안_붙인다(db, sample_retreat):
    """안 하기로 한 업무에 「지연」 은 재촉이고, 그 배지는 이 자리에서 아무
    뜻도 없다 — 4-3 의 배지는 **하는 업무**의 표현이다."""
    _업무(db, sample_retreat, "작년 현수막 재활용", included=False)
    db.commit()
    (줄,) = tasklist.build(db, sample_retreat, today=TODAY).excluded_rows
    assert "badge" not in 줄 and "dday" not in 줄


def test58_a05_새_화면을_안_만들고_그_드로어로_간다():
    """**새 화면을 만들지 않는다** — 누르면 `?task=` 로 그 드로어가 열린다
    (보드·달력과 같은 한 벌 · 4-9). 행이 목록에 없어도 열린다: 드로어는 요소가
    아니라 서버 응답으로 그린다."""
    글 = _민낯진자(TASKS_HTML)
    자리 = 글[글.index("view.excluded_rows"):]
    assert 'href="/tasks?task={{ row.run_id }}"' in 자리
    # 목록 행이 쓰는 번호·메타 칩을 그대로 쓴다 — 두 벌을 만들지 않는다
    assert 'class="runno"' in 자리 and 'class="deptchip"' in 자리
    # 라우트를 새로 판 곳이 없다
    routers = (ROOT / "app" / "routers" / "tasks.py").read_text(encoding="utf-8")
    assert "excluded" not in routers, "뺀 업무 전용 라우트가 생겼다"


def test58_a05b_실제로_그려진_목록에_그_자리가_있다(admin_client):
    """**pytest 는 화면을 못 본다**(10장) — 구조가 실어 보낸 것을 화면이
    안 그리면 도메인 시험은 초록이고 사람은 아무 데도 못 간다."""
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회", start_date=dt.date.today() - dt.timedelta(days=3),
            end_date=dt.date.today() + dt.timedelta(days=3))
        db.add(retreat)
        db.flush()
        db.add(models.Department(retreat_id=retreat.id, key="chongmu",
                                 name="총무팀", sort_order=0))
        db.flush()
        뺀것 = _업무(db, retreat, "작년 현수막 재활용", included=False)
        산것 = _업무(db, retreat, "포스터 제작")
        db.commit()
        뺀id, 산id = 뺀것.id, 산것.id

    page = admin_client.get("/tasks").text
    assert "이번 회차에서 뺀 업무 1건" in page
    assert f'href="/tasks?task={뺀id}"' in page
    assert f'href="/tasks?task={산id}"' not in page, "하는 업무가 뺀 목록에 섰다"
    # 소속 외 흐림이 화면까지 닿는다 — 부서 없는 업무는 총무팀 소관이라 관리자에게 선명
    assert 'class="lexrow"' in page and 'class="lexrow dim"' not in page


def test58_a05c_부서_리더에게는_남의_부서_줄이_흐리게_그려진다(admin_client):
    """관리자는 전부 선명해서 **흐림이 화면까지 닿는지는 리더로만 잴 수 있다**
    (11-3 의 「두 계정」 과 같은 까닭 — 고장을 심어 보니 관리자로는 안 잡혔다)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회", start_date=dt.date.today() - dt.timedelta(days=3),
            end_date=dt.date.today() + dt.timedelta(days=3))
        db.add(retreat)
        db.flush()
        for i, key in enumerate(("hongbo", "chanyang")):
            db.add(models.Department(retreat_id=retreat.id, key=key, name=key, sort_order=i))
        db.flush()
        남의것 = _업무(db, retreat, "뺀 홍보 업무", included=False, dept_key="hongbo")
        내것 = _업무(db, retreat, "뺀 찬양 업무", included=False, dept_key="chanyang")
        내부서 = next(d.id for d in retreat.departments if d.key == "chanyang")
        db.commit()
        남id, 내id = 남의것.id, 내것.id
    make_user("찬양 리더", "01033334444", role="dept_lead", dept=내부서)
    리더 = TestClient(app)
    login_as(리더, "01033334444")

    page = 리더.get("/tasks?dept=all").text
    assert f'class="lexrow dim" href="/tasks?task={남id}"' in page
    assert f'class="lexrow" href="/tasks?task={내id}"' in page


def test58_a06_글자가_눈금에서_나오고_좁은_화면에서_접힌다():
    """**CSS 만 본다** — 글자 단(4-0 의 14px 하한)과 820px 아래의 `flex-wrap`.
    375px 에서 실제로 잰 값은 보고 4장이고 이 시험이 대신하지 않는다.
    눈금 밖 숫자는 `tests/test_typescale.py` 가 따로 잰다."""
    민낯 = _민낯(CSS)
    for sel, 단 in ((".lexrow .nm", "--fz-md"), (".lexcl .hint", "--fz-md"),
                    (".lexcl > summary", "--fz-base")):
        m = re.search(re.escape(sel) + r"\{([^{}]*)\}", 민낯)
        assert m, f"{sel} 규칙이 없다"
        assert f"font-size:var({단})" in m.group(1).replace(" ", ""), \
            f"{sel} 이 {단} 이 아니다"
    # 좁은 화면에서 메타가 이름 아래로 내려간다 — 한 줄에 우겨넣지 않는다
    좁은쪽 = 민낯[민낯.index("@media (max-width:820px)"):]
    assert ".lexrow{flex-wrap:wrap" in 좁은쪽.replace(" ", "")


# ════════════════════════════════════════════════════════════════════
# 2. 결산 홈의 한 줄 — 5-6 이 프로그램표에서 한 것과 같은 결
# ════════════════════════════════════════════════════════════════════


def _결산홈() -> str:
    """결산 홈의 업무 칸 — **주석을 걷어낸** 화면에서 잘라 온다."""
    글 = _민낯진자(HOME_HTML)
    return 글[글.index("미지급 환급"):글.index("예산 집행률")]


def _사람(db):
    user = models.User(name="테스터", phone_number="", role="admin")
    db.add(user)
    db.flush()
    return user


@pytest.mark.parametrize("완료있음,기대", [(False, True), (True, False)])
def test58_b01_끝난_회차에_완료가_0이면_다른_문구다(db, sample_retreat, 완료있음, 기대):
    """근거는 **종료된 회차 + 완료 0건** 둘뿐이다 (5-6). 완료가 하나라도
    생기면 그때부터 보통의 「미완료 N건」 으로 돌아온다."""
    _업무(db, sample_retreat, "업무 하나")
    if 완료있음:
        _업무(db, sample_retreat, "끝낸 업무", status="완료")
    db.commit()
    뒷날 = sample_retreat.end_date + dt.timedelta(days=1)

    view = home_mod.build(db, sample_retreat, _사람(db), today=뒷날)
    assert view.over is True
    assert view.carried_only is 기대


def test58_b02_진행_중인_회차는_그대로다(db, sample_retreat):
    """2027 처럼 아직 안 끝난 회차는 건드리지 않는다 — 완료가 0 인 것이
    거기서는 **아직 안 한 것**이라 정상이다."""
    _업무(db, sample_retreat, "업무 하나")
    db.commit()
    view = home_mod.build(db, sample_retreat, _사람(db),
                          today=sample_retreat.start_date - dt.timedelta(days=30))
    assert view.over is False and view.carried_only is False


def test58_b03_업무가_아예_없으면_아무_말도_안_한다(db, sample_retreat):
    """`live.carried_only` 가 프로그램이 없으면 False 인 것과 같다 — 옮겨온
    것이 없는데 「옮겨온 것입니다」 라고 말하면 거짓이다."""
    뒷날 = sample_retreat.end_date + dt.timedelta(days=1)
    view = home_mod.build(db, sample_retreat, _사람(db), today=뒷날)
    assert view.over is True and view.carried_only is False


def test58_b04_화면이_두_갈래를_다_그린다():
    """한 갈래만 그리면 나머지 갈래가 빈 칸이 된다 — Jinja 는 없는 이름을
    빈 것으로 그려서 아무 오류도 안 난다 (departments_of 에서 겪은 그것)."""
    자리 = _결산홈()
    assert "{% if home.carried_only %}" in 자리, "판정이 분기에 안 걸려 있다"
    assert "home.total" in 자리 and "옮겨온 업무라 완료 표시가 없습니다" in 자리
    assert "home.open_task_count" in 자리 and "정리 필요" in 자리
    assert "{% else %}" in 자리, "갈래가 하나뿐이다"


@pytest.mark.parametrize("완료있음,볼말,안볼말", [
    (False, "옮겨온 업무라 완료 표시가 없습니다", "정리 필요"),
    (True, "정리 필요", "옮겨온 업무라 완료 표시가 없습니다"),
])
def test58_b04b_실제로_그려진_화면이_갈린다(admin_client, 완료있음, 볼말, 안볼말):
    """**글자가 파일에 있는 것과 화면에 그려지는 것은 다르다** — 위의 b04 는
    분기를 통째로 죽여 놓아도(`{% else %}{% if False %}`) 초록이었다.
    pytest 는 화면을 못 본다는 그 자리라(10장) 실제로 받아서 본다."""
    어제 = dt.date.today() - dt.timedelta(days=1)
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회", start_date=어제 - dt.timedelta(days=3),
            end_date=어제, meal_subsidy_per_person=8_000)
        db.add(retreat)
        db.flush()
        db.add(models.Department(retreat_id=retreat.id, key="chongmu",
                                 name="총무팀", sort_order=0))
        db.flush()
        _업무(db, retreat, "옮겨온 업무")
        if 완료있음:
            _업무(db, retreat, "끝낸 업무", status="완료")
        db.commit()

    page = admin_client.get("/").text
    assert "수련회가 끝났습니다" in page, "결산 홈이 아니다"
    assert 볼말 in page and 안볼말 not in page


def test58_b05_판정이_도메인에_있고_화면이_다시_안_가른다():
    """화면이 상태를 다시 가르면 두 벌이 되고 갈린 쪽을 아무도 눈치채지
    못한다 (4-3 의 배지와 같은 자리)."""
    src = (ROOT / "app" / "domain" / "home.py").read_text(encoding="utf-8")
    assert "def carried_only(" in src
    자리 = _결산홈()
    assert "== 0" not in 자리 and "home.done" not in 자리, "화면이 다시 센다"


# ════════════════════════════════════════════════════════════════════
# 3. 뺀 업무 드로어의 한 줄 (2026-09-16 마무리 판)
# ════════════════════════════════════════════════════════════════════


def test58_c01_드로어_응답이_뺀_것과_산_것을_가른다(admin_client):
    """**같은 판에서 둘 다 연다** — 뺀 업무는 `included` 가 거짓, 산 업무는 참.
    열리는 것 자체도 본다 — 뺀 업무라고 드로어가 막히면 목록 아래 상자가 갈 곳이 없다.
    고치는 것도 막지 않는다(사람이 정함): 뺀 업무의 상태를 바꿀 수 있다."""
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회", start_date=dt.date.today() - dt.timedelta(days=3),
            end_date=dt.date.today() + dt.timedelta(days=3))
        db.add(retreat)
        db.flush()
        db.add(models.Department(retreat_id=retreat.id, key="chongmu",
                                 name="총무팀", sort_order=0))
        db.flush()
        뺀id = _업무(db, retreat, "뺀 업무", included=False).id
        산id = _업무(db, retreat, "산 업무").id
        db.commit()

    뺀 = admin_client.get(f"/board/task/{뺀id}")
    산 = admin_client.get(f"/board/task/{산id}")
    assert 뺀.status_code == 200 and 산.status_code == 200
    assert 뺀.json()["included"] is False
    assert 산.json()["included"] is True
    # 고치는 길은 열려 있다
    res = admin_client.post(f"/board/task/{뺀id}/status", json={"status": "완료"})
    assert res.status_code == 200, res.text


def test58_c02_드로어가_그_값으로만_그_줄을_켠다():
    """줄은 **처음에 숨어 있고**(산 업무를 열었을 때 안 뜬다), JS 는 서버의
    `included` 하나로 켠다 — 화면이 다시 가르지 않는다(4-3 과 같은 자리).
    주석을 걷어내고 본다(10장 — 이 판에서 한 번 밟았다)."""
    html = _민낯진자((ROOT / "app" / "templates" / "partials" / "drawer.html")
                   .read_text(encoding="utf-8"))
    m = re.search(r'<div[^>]*id="dexcl"[^>]*>([^<]*)</div>', html)
    assert m, "드로어에 그 줄이 없다"
    assert " hidden" in m.group(0), "처음부터 보인다 — 산 업무에도 뜬다"
    assert m.group(1).strip() == "이번 회차에서 뺀 업무입니다"
    # 칩 아래 · 제목 위 — 아래쪽 진단 패널·옮긴 자리 줄과 안 겹치는 자리
    assert html.index('id="dkick"') < html.index('id="dexcl"') < html.index('id="dtitle"')

    from tests.test_stage15 import _코드
    js = _코드(ROOT / "app" / "static" / "js" / "drawer.js")
    assert re.search(r"\$\('dexcl'\)", js), "JS 가 그 줄을 안 만진다"
    assert "d.included !== false" in js, "서버 값으로 가르지 않는다"
    css = _민낯(CSS)
    m = re.search(r"\.dexcl\{([^{}]*)\}", css)
    assert m and "font-size:var(--fz-md)" in m.group(1).replace(" ", ""), "14px 하한이 아니다"
