"""상위-하위를 화면이 받아낸다 — 채우기(`--실행`) 전에 화면부터 (2026-09-17 · 봐둘것 BF-a).

사람이 정한 넷:
① 화면을 먼저 고치고 채운다
② 부서가 다른 하위는 자기 부서 블록의 머리 줄로 두고 「↑ 상위 · 상위 부서」 를 보조 급으로
③ 목록의 「↑ 상위」 를 누르면 상위의 상세가 열린다(행으로 옮기지 않음)
④ 부서가 다른 하위는 「+ 업무 추가」 · 마법사 · 초안에서 부모를 따라 자동으로 안 들어온다

값은 전부 지어낸 것이다.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest
from sqlalchemy import select

from app import models
from app.domain import board as board_view
from app.domain import library as lib_domain
from tests.conftest import app_session

OPEN = dt.date(2026, 8, 21)


def _lib(db, 제목, kind, 키, 부모=None, 주=6):
    lib = models.TaskLibrary(title=제목, kind=kind, default_department_key=키,
                             parent_library_id=부모.id if 부모 else None,
                             related_department_keys=[], related_library_ids=[],
                             date_anchor="week", default_d_week=주, default_offset_days=0,
                             default_span_days=3)
    db.add(lib)
    db.flush()
    return lib


@pytest.fixture
def 계층(admin_client):
    """스케치 Main 아래에 같은 부서 하위 · 다른 부서 하위 · 부서 없는 하위, 부서 없는 Main 아래 스케치 하위.
    `parents=False` 면 같은 모양에서 상위만 비운다(지금 운영 모양)."""
    def 만든다(parents=True, runs_for=None):
        with app_session() as db:
            r = models.Retreat(name="2026 여름수련회 Belong", start_date=OPEN, end_date=OPEN + dt.timedelta(days=2))
            db.add(r)
            db.flush()
            depts = {}
            for i, (k, n, c) in enumerate([("sketch", "4 스케치", "#B95A83"), ("chongmuM", "1 총무M", "#2F4858")]):
                depts[k] = models.Department(retreat_id=r.id, key=k, name=n, color_tag=c, sort_order=i)
                db.add(depts[k])
            db.flush()
            m1 = _lib(db, "포스터 제작", "main", "sketch", 주=10)
            m2 = _lib(db, "부서 없는 큰일", "main", None, 주=9)
            p = (lambda x: x) if parents else (lambda x: None)
            libs = {
                "m1": m1, "m2": m2,
                "s1": _lib(db, "포스터 확정", "sub", "sketch", p(m1)),
                "x1": _lib(db, "포스터 의뢰서", "sub", "chongmuM", p(m1)),
                "n1": _lib(db, "포스터 부착", "schedule", None, p(m1)),
                "y1": _lib(db, "스케치 몫", "sub", "sketch", p(m2)),
            }
            ids = {}
            for 이름, lib in libs.items():
                if runs_for is not None and 이름 not in runs_for:
                    continue
                d = depts.get(lib.default_department_key)
                run = models.TaskRun(library_id=lib.id, retreat_id=r.id, included=True,
                                     department_id=d.id if d else None, d_week=lib.default_d_week,
                                     start_date=OPEN - dt.timedelta(days=30), end_date=OPEN - dt.timedelta(days=28),
                                     status="대기", run_no=len(ids) + 1)
                db.add(run)
                db.flush()
                ids[이름] = run.id
            db.commit()
            return {"retreat": r.id, "lib": {k: v.id for k, v in libs.items()}, "run": ids}
    return 만든다


def _보드(db, retreat_id):
    return board_view.build(db, db.get(models.Retreat, retreat_id), today=OPEN - dt.timedelta(days=60))


def _줄(판, 블록키):
    return next(b for b in 판["departments"] if b["key"] == 블록키)["rows"]


# ── 1. 보드 ──────────────────────────────────────────────────────────

def test62_a01_부서가_다른_하위는_자기_부서의_머리_줄로_서고_상위를_붙인다(계층):
    x = 계층()
    with app_session() as db:
        판 = _보드(db, x["retreat"])
    스케치, 총무 = _줄(판, "sketch"), _줄(판, "chongmuM")
    # 같은 부서 하위는 상위 아래 트리(depth 1) · 상위 표시는 안 붙는다
    s1 = next(r for r in 스케치 if r["run_id"] == x["run"]["s1"])
    assert s1["depth"] == 1 and s1["parent"] is None
    # 부서가 다른 하위는 자기 부서(총무M)의 머리 줄 · 상위 제목과 상위 부서
    x1 = next(r for r in 총무 if r["run_id"] == x["run"]["x1"])
    assert x1["depth"] == 0
    assert x1["parent"]["title"] == "포스터 제작" and x1["parent"]["other_dept"]
    assert x1["parent"]["dept_name"] and x1["parent"]["dept_color"] == "#B95A83"
    assert x1["parent"]["run_id"] == x["run"]["m1"]
    # 상위 쪽 블록에는 트리로 안 나온다
    assert x["run"]["x1"] not in [r["run_id"] for r in 스케치]


def test62_a02_상위에_부서가_없으면_담당_없음_을_붙인다(계층):
    x = 계층()
    with app_session() as db:
        판 = _보드(db, x["retreat"])
    y1 = next(r for r in _줄(판, "sketch") if r["run_id"] == x["run"]["y1"])
    assert y1["depth"] == 0 and y1["parent"]["dept_name"] is None and y1["parent"]["other_dept"]
    # 부서 없는 하위는 「담당 없음」 블록에 서고 상위(스케치)를 붙인다
    n1 = next(r for r in _줄(판, "__none__") if r["run_id"] == x["run"]["n1"])
    assert n1["parent"]["title"] == "포스터 제작" and n1["parent"]["other_dept"]


def test62_a03_채운_뒤에도_보드에_선_산_run_수가_그대로다(계층):
    x = 계층()
    with app_session() as db:
        판 = _보드(db, x["retreat"])
    선것 = [r["run_id"] for b in 판["departments"] for r in b["rows"]]
    assert sorted(선것) == sorted(x["run"].values()), "보드에서 사라지거나 두 번 선 업무가 있다"


def test62_a04_상위의_run_이_이번_회차에_없어도_하위가_선다(계층):
    x = 계층(runs_for={"s1", "x1", "m2", "y1"})       # m1 의 run 이 없다
    with app_session() as db:
        판 = _보드(db, x["retreat"])
    s1 = next(r for r in _줄(판, "sketch") if r["run_id"] == x["run"]["s1"])
    assert s1["depth"] == 0 and s1["parent"]["run_id"] is None and s1["parent"]["title"] == "포스터 제작"
    # 상위 run 이 없으면 부서를 모른다 — 「담당 없음」 이라고 하지 않는다(커밋 전 검토)
    assert not s1["parent"]["other_dept"] and not s1["parent"]["no_dept"]
    x1 = next(r for r in _줄(판, "chongmuM") if r["run_id"] == x["run"]["x1"])
    assert x1["parent"]["other_dept"] and not x1["parent"]["no_dept"] and x1["parent"]["dept_name"] is None
    선것 = [r["run_id"] for b in 판["departments"] for r in b["rows"]]
    assert sorted(선것) == sorted(x["run"].values())


def test62_a04b_상위_run_이_없으면_화면에_부서_꼬리가_안_선다(계층, admin_client):
    계층(runs_for={"s1", "x1", "n1", "m2", "y1"})     # m1 의 run 이 없다 · y1 의 상위 m2 는 부서 없는 run
    for 주소 in ("/board", "/tasks?dept=all"):
        page = admin_client.get(주소).text
        # 담당 없음 꼬리는 상위 run 이 있고 부서가 없는 y1 에만 선다
        assert page.count('class="pdept">담당 없음</span>') >= 1, 주소
        assert page.count('↑ 포스터 제작 <span class="pdept">') == 0, 주소


def test62_a05_상위가_비어_있으면_화면이_그대로다(계층, admin_client):
    """지금 운영 모양(상위 전부 비어 있음) — 그릴 상위가 없으니 표시도 없다."""
    x = 계층(parents=False)
    with app_session() as db:
        판 = _보드(db, x["retreat"])
    assert all(r["parent"] is None and r["depth"] == 0 for b in 판["departments"] for r in b["rows"])
    for 주소 in ("/board", "/tasks?dept=all"):
        assert 'class="pup"' not in admin_client.get(주소).text, 주소


def test62_a06_보드_화면이_상위를_그린다(계층, admin_client):
    x = 계층()
    page = admin_client.get("/board").text
    assert '<span class="pup" title="상위: 포스터 제작">↑ 포스터 제작' in page
    assert '<span class="pdept"><i style="background:#B95A83"></i>' in page
    assert re.search(r'class="pdept">담당 없음</span>', page)


def test62_a07_달력_툴팁에_상위가_한_줄_붙는다(계층):
    x = 계층()
    with app_session() as db:
        run = db.get(models.TaskRun, x["run"]["x1"])
        글 = board_view.paint_of(run, OPEN)["tooltip"]
        assert "상위: 포스터 제작" in 글
        m1 = db.get(models.TaskRun, x["run"]["m1"])
        assert "상위" not in board_view.paint_of(m1, OPEN)["tooltip"]


# ── 2. 목록 · 드로어 ─────────────────────────────────────────────────

def test62_b01_목록_행에_상위_단추가_선다(계층, admin_client):
    x = 계층()
    page = admin_client.get("/tasks?dept=all").text
    단추 = re.search(r'<button type="button" class="pup" data-parent="(\d+)"[^>]*>↑ 포스터 제작'
                   r' <span class="pdept"><i style="background:#B95A83"></i>', page)
    assert 단추 and int(단추.group(1)) == x["run"]["m1"]
    # 태그가 글자로 찍히지 않는다(Markup 이 섞여 이스케이프되는 사고)
    assert "&lt;span" not in page
    # 같은 부서 하위(s1)도 목록에서는 상위를 단다 — 목록은 평평해 트리가 없다. 부서 표시는 안 붙는다
    assert re.search(r'data-parent="\d+"[^>]*>↑ 포스터 제작</button>', page)


def test62_b02_목록의_상위_단추는_행을_안_열고_상위를_옆에_연다():
    import pathlib
    js = (pathlib.Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "tasks.js").read_text(encoding="utf-8")
    assert "button" in re.search(r"const 안여는곳 = '([^']*)'", js).group(1)
    assert "button.pup[data-parent]" in js and "Drawer.open(상위.dataset.parent)" in js
    assert "옆에열기 ? null : slotOf(runId)" in js


def test62_b03_드로어가_상위를_연결_카드_모양으로_준다(계층, admin_client):
    x = 계층()
    d = admin_client.get(f"/board/task/{x['run']['x1']}").json()
    assert d["parent"]["run_id"] == x["run"]["m1"] and d["parent"]["title"] == "포스터 제작"
    assert d["parent"]["color"] and d["parent"]["kind_label"]
    d = admin_client.get(f"/board/task/{x['run']['m1']}").json()
    assert d["parent"] is None and d["parent_title"] is None


# ── 3. 「+ 업무 추가」 · 마법사 · 초안 ───────────────────────────────

def test62_c01_업무_추가는_부서가_다른_하위를_안_딸려_넣고_후보에_남긴다(계층, admin_client):
    x = 계층(runs_for=set())                      # 이번 회차에 아무것도 없음
    page = admin_client.get("/board/add").text
    assert "포스터 의뢰서" in page, "부서가 다른 하위가 후보에 없다"
    assert "포스터 확정" not in page, "같은 부서 하위는 부모를 따라가므로 후보가 아니다"
    res = admin_client.post("/board/add/existing", json={"library_ids": [x["lib"]["m1"]]})
    assert res.status_code == 200, res.text
    with app_session() as db:
        들어온 = set(db.scalars(select(models.TaskRun.library_id).where(
            models.TaskRun.retreat_id == x["retreat"], models.TaskRun.included)))
    assert 들어온 == {x["lib"]["m1"], x["lib"]["s1"]}, "부서가 다른 하위가 딸려 들어왔다"
    res = admin_client.post("/board/add/existing", json={"library_ids": [x["lib"]["x1"]]})
    assert res.status_code == 200, res.text
    with app_session() as db:
        assert db.scalar(select(models.TaskRun.id).where(
            models.TaskRun.retreat_id == x["retreat"], models.TaskRun.library_id == x["lib"]["x1"]))


def test62_c02_마법사는_부서가_다른_하위를_부모와_함께_안_넣는다(계층):
    x = 계층()
    with app_session() as db:
        새 = lib_domain.create_retreat(db, name="2027 여름", open_date=dt.date(2027, 8, 20),
                                      close_date=dt.date(2027, 8, 22), meal_subsidy=8000,
                                      department_keys=["sketch", "chongmuM"],
                                      selected_library_ids={x["lib"]["m1"]})
        db.commit()
        든것 = set(db.scalars(select(models.TaskRun.library_id).where(
            models.TaskRun.retreat_id == 새.id, models.TaskRun.included)))
    assert x["lib"]["s1"] in 든것, "같은 부서 하위가 부모를 안 따라왔다"
    assert x["lib"]["x1"] not in 든것 and x["lib"]["n1"] not in 든것, "부서가 다른 하위가 딸려 왔다"


def test62_c03_마법사와_초안에서_부서가_다른_하위를_따로_고른다(계층):
    x = 계층()
    with app_session() as db:
        목록 = lib_domain.catalog(db, open_date=dt.date(2027, 8, 20))
        줄 = {r["library_id"]: r for r in 목록}
        # 고르는 단위로 선다 — 초안은 이 목록을 부서 키로 거른다(routers/drafts.py)
        assert x["lib"]["x1"] in 줄 and 줄[x["lib"]["x1"]]["department_key"] == "chongmuM"
        assert 줄[x["lib"]["x1"]]["parent_title"] == "포스터 제작"
        assert x["lib"]["s1"] not in 줄
        assert [c["library_id"] for c in 줄[x["lib"]["m1"]]["children"]] == [x["lib"]["s1"]]
        assert lib_domain.top_owner(db)[x["lib"]["x1"]] == x["lib"]["x1"]
        assert lib_domain.top_owner(db)[x["lib"]["s1"]] == x["lib"]["m1"]
        새 = lib_domain.create_retreat(db, name="2027 여름", open_date=dt.date(2027, 8, 20),
                                      close_date=dt.date(2027, 8, 22), meal_subsidy=8000,
                                      department_keys=["sketch", "chongmuM"],
                                      selected_library_ids={x["lib"]["x1"]})
        db.commit()
        든것 = set(db.scalars(select(models.TaskRun.library_id).where(
            models.TaskRun.retreat_id == 새.id, models.TaskRun.included)))
    assert 든것 == {x["lib"]["x1"]}


def test62_c04_마법사_편집은_지금_상위를_고른_채로_연다():
    import pathlib
    js = (pathlib.Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "setup.js").read_text(encoding="utf-8")
    assert "if (item.parent_id) { paintParentPicker(); $('tParent').value = item.parent_id; }" in js
    assert "i.task_kind === 'main' || i.task_kind === 'sub'" in js


def test62_c05_필수_일괄_저장은_부서가_다른_하위를_받는다(계층, admin_client):
    """마법사와 설정 목록이 그 하위를 고르는 칸으로 세우므로, 저장도 받아야 한다 — 안 받으면 켜고 저장해도 조용히 무시된다."""
    x = 계층()
    res = admin_client.post("/library/required/bulk",
                            data={"library_ids": [x["lib"]["x1"], x["lib"]["s1"]]}, follow_redirects=False)
    assert res.status_code in (302, 303), res.text
    with app_session() as db:
        assert db.get(models.TaskLibrary, x["lib"]["x1"]).always_required
        # 같은 부서 하위는 상위를 따라가므로 여전히 건너뛴다
        assert not db.get(models.TaskLibrary, x["lib"]["s1"]).always_required


def test62_c06_마법사_줄에_상위가_보인다(계층, admin_client):
    x = 계층()
    res = admin_client.post("/setup/preview",
                            json={"open_date": "2027-08-20", "department_keys": ["sketch", "chongmuM"]})
    assert res.status_code == 200, res.text
    줄 = {i["id"]: i for i in res.json()["items"]}
    assert "↑ 포스터 제작" in 줄[str(x["lib"]["x1"])]["row_html"]
    assert "↑" not in 줄[str(x["lib"]["m1"])]["row_html"]
    import pathlib
    draft = (pathlib.Path(__file__).resolve().parent.parent / "app" / "templates" / "draft.html").read_text(encoding="utf-8")
    assert "'↑ ' ~ item.parent_title" in draft


def _바(page: str, run_id: int) -> str:
    """그 줄 **자신의** 바 클래스.

    **접힌 Main 아래 눕는 바(`.bar.sl`)를 빼야 한다**(2026-09-25 3단계) —
    하위가 하나면 그 바에도 같은 `data-run` 이 붙어서, 그냥 찾으면 그쪽이
    먼저 잡히고 `sl` 이 나온다. 여기서 보려는 것은 **하위 줄이 어떤 모양으로
    그려지나** 이지 접힌 줄에 눕는 모양이 아니다.
    """
    for m in re.finditer(r'<div class="bar ([^"]*)"[^>]*data-run="%d"' % run_id, page, re.S):
        cls = " ".join(m.group(1).split())
        if not cls.startswith("sl "):
            return cls
    raise AssertionError(f"run {run_id} 의 바가 없다")


def _줄급(page: str, run_id: int) -> str:
    m = re.search(r'<div class="row ([^"]*)"\s+data-of="[^"]*" data-run="%d"' % run_id, page)
    assert m, f"run {run_id} 의 줄이 없다"
    return m.group(1).split()[0]


def _줄클래스(page: str, run_id: int) -> str:
    m = re.search(r'<div class="row ([^"]*)"\s+data-of="[^"]*" data-run="%d"' % run_id, page)
    assert m, f"run {run_id} 의 줄이 없다"
    return m.group(1)


def test62_a08_머리_줄로_선_하위는_얇은_바로_그린다(계층, admin_client):
    """굵은 Main 모양이면 최상위 업무로 읽힌다(사람이 정함 2026-09-17) — 분류로도 가른다."""
    x = 계층()
    # 노션 속성이 빈 채 앱에 main 으로 들어간 하위 — 분류만 보면 굵게 남는다
    with app_session() as db:
        총무 = db.scalar(select(models.Department).where(
            models.Department.retreat_id == x["retreat"], models.Department.key == "chongmuM"))
        k1 = _lib(db, "속성 빈 하위", "main", "chongmuM", db.get(models.TaskLibrary, x["lib"]["m1"]))
        run = models.TaskRun(library_id=k1.id, retreat_id=x["retreat"], included=True, department_id=총무.id,
                             d_week=6, start_date=OPEN - dt.timedelta(days=30),
                             end_date=OPEN - dt.timedelta(days=28), status="대기", run_no=99)
        db.add(run)
        db.commit()
        x["run"]["k1"] = run.id
    page = admin_client.get("/board").text
    # 부서가 다른 하위(x1 · k1) · 상위가 부서 없는 하위(y1)는 머리 줄이지만 하위 모양
    for 이름 in ("x1", "y1", "k1"):
        assert _바(page, x["run"][이름]).startswith("s "), 이름
        assert _줄급(page, x["run"][이름]) == "sub", 이름
        # 트리 들여쓰기는 안 한다 — 바로 위 Main 의 하위로 읽히지 않게
        assert "headsub" in _줄클래스(page, x["run"][이름]), 이름
    assert "headsub" not in _줄클래스(page, x["run"]["s1"])
    import pathlib
    css = (pathlib.Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert re.search(r"\.row\.sub\.headsub \.lc\{padding-left:30px\}", css), "머리 줄 하위의 들여쓰기 규칙이 없다"
    # 진짜 Main 은 굵은 바 · 트리 아래 하위는 전처럼 얇은 바 · 일정은 칩 그대로
    assert _바(page, x["run"]["m1"]).startswith("m ") and _줄급(page, x["run"]["m1"]) == "main"
    assert _바(page, x["run"]["s1"]).startswith("s ")
    assert _바(page, x["run"]["n1"]).startswith("sch ")
    # 좁은 폭 행도 같은 값(row.child)을 쓴다 — 진짜 Main 만 sub 가 안 붙는다
    좁은 = {rid: cls for cls, rid in re.findall(r'class="mrow([^"]*)"[^>]*data-run="(\d+)"', page)}
    assert " sub" in 좁은[str(x["run"]["k1"])] and " sub" in 좁은[str(x["run"]["x1"])]
    assert " sub" not in 좁은[str(x["run"]["m1"])]
