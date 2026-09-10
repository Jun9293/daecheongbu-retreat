"""UI 개편 단계 3 — 목록(4-14) · 저장 '지연' 제거(4-3) · 논의 걸린 곳(4-9) ·
달력 partial(4-13) · 마법사 행 공용 partial(6-6).

값을 시험에 박지 않는다 (11-3) — 문서가 말할 값 대신 값끼리 맞는지를 본다.
막는 코드에는 막히는 쪽 시험이 함께 있다.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest
from sqlalchemy import select, text

from app import models
from app.domain import board as board_domain
from app.domain import discussion, home as home_domain, tasklist
from tests.conftest import app_session, login_as, make_user, legacy_user

TODAY = dt.date.today()
ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(*parts) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def _no_comments_jinja(src: str) -> str:
    return re.sub(r"\{#.*?#\}", "", src, flags=re.S)


# ════════════════════════════════════════════════════════════════════
# 1-a. 붉은 글자 토큰 하나
# ════════════════════════════════════════════════════════════════════


def test_a01_붉은_글자_토큰이_하나다():
    """--st-late-fg 와 --now-ink 는 값을 따로 갖지 않고 --red-ink 를 가리킨다.
    옛 둘째 값(#A3423B)은 0곳이다 (4-0)."""
    css = _read("app", "static", "css", "retreat.css")
    assert "#A3423B" not in css, "옛 둘째 붉은 값이 남아 있다"
    assert css.count("--red-ink:#A33F38") == 1
    assert "--st-late-fg:var(--red-ink)" in css
    assert "--now-ink:var(--red-ink)" in css


# ════════════════════════════════════════════════════════════════════
# 1-b. 저장 '지연' 제거 (4-3)
# ════════════════════════════════════════════════════════════════════


def test_b01_저장_상태는_셋뿐이다():
    assert models.RUN_STATUSES == ("대기", "진행중", "완료")


@pytest.fixture
def world(admin_client):
    """회차 둘 + 부서(키 있음) + 업무 몇 개. 날짜는 오늘 기준 상대값."""
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회 Belong",
            start_date=TODAY + dt.timedelta(days=40),
            end_date=TODAY + dt.timedelta(days=43),
        )
        other_retreat = models.Retreat(
            name="2027 겨울수련회",
            start_date=TODAY + dt.timedelta(days=200),
            end_date=TODAY + dt.timedelta(days=203),
        )
        db.add_all([retreat, other_retreat])
        db.flush()
        chongmu = models.Department(
            retreat_id=retreat.id, key="chongmuM", name="1 총무M",
            color_tag="#2F4858", sort_order=0)
        hebron = models.Department(
            retreat_id=retreat.id, key="hebron", name="5 헤브론",
            color_tag="#4A8A5C", sort_order=1)
        # 다른 회차에도 같은 키의 부서 — 소속 비교가 id 면 여기서 무너진다 (2장)
        hebron2 = models.Department(
            retreat_id=other_retreat.id, key="hebron", name="5 헤브론",
            color_tag="#4A8A5C", sort_order=0)
        db.add_all([chongmu, hebron, hebron2])
        db.flush()

        runs = {}

        def run(title, *, start, end, status="대기", dept=chongmu, r=retreat):
            lib = models.TaskLibrary(title=title, kind="main", default_d_week=5)
            db.add(lib)
            db.flush()
            row = models.TaskRun(
                library_id=lib.id, retreat_id=r.id, included=True,
                department_id=dept.id, d_week=5,
                start_date=start, end_date=end, status=status)
            db.add(row)
            db.flush()
            runs[title] = row.id
            return row

        run("지난 마감", start=TODAY - dt.timedelta(days=9),
            end=TODAY - dt.timedelta(days=2))                      # 계산 지연
        run("한참 뒤 마감", start=TODAY + dt.timedelta(days=3),
            end=TODAY + dt.timedelta(days=14))                     # 대기
        run("진행중인 것", start=TODAY - dt.timedelta(days=1),
            end=TODAY + dt.timedelta(days=6), status="진행중")
        run("끝낸 것", start=TODAY - dt.timedelta(days=20),
            end=TODAY - dt.timedelta(days=8), status="완료")       # 완료 · 마감 지남
        run("헤브론 일", start=TODAY, end=TODAY + dt.timedelta(days=4), dept=hebron)
        run("겨울 준비", start=TODAY + dt.timedelta(days=100),
            end=TODAY + dt.timedelta(days=110), dept=hebron2, r=other_retreat)
        db.commit()
        ids = {
            "retreat": retreat.id, "other_retreat": other_retreat.id,
            "chongmu": chongmu.id, "hebron": hebron.id, "hebron2": hebron2.id,
            "runs": runs,
        }
    # admin 이 이 회차를 보게 한다
    admin_client.get(f"/board?retreat_id={ids['retreat']}")
    return ids


def test_b02_서버가_지연을_거절한다(admin_client, world):
    """막는 쪽: '지연' 은 저장값이 아니다 (4-3) → 400.
    막히면 안 되는 쪽: 셋은 그대로 받는다."""
    run_id = world["runs"]["한참 뒤 마감"]
    rejected = admin_client.post(f"/board/task/{run_id}/status", json={"status": "지연"})
    assert rejected.status_code == 400

    ok = admin_client.post(f"/board/task/{run_id}/status", json={"status": "진행중"})
    assert ok.status_code == 200
    assert ok.json()["badge"] == {"label": "진행중", "cls": "prog"}


def test_b03_저장돼_있던_지연은_앱이_뜰_때_한_번_대기가_된다(world):
    """옮기기 전 행을 만들어 놓고 마이그레이션을 두 번 돌린다 —
    두 번 떠도 두 번 바꾸지 않는다. 바뀐 것은 ActivityLog 에 남는다."""
    from app import db as db_module

    run_id = world["runs"]["한참 뒤 마감"]
    with app_session() as db:
        db.execute(text("UPDATE task_runs SET status='지연' WHERE id=:id"), {"id": run_id})
        db.commit()

    def log_rows():
        with app_session() as db:
            return db.scalars(
                select(models.ActivityLog).where(
                    models.ActivityLog.summary == "저장 지연 → 대기 (계산값으로 전환)",
                    models.ActivityLog.target_id == run_id,
                )
            ).all()

    db_module._convert_stored_late()
    with app_session() as db:
        assert db.get(models.TaskRun, run_id).status == "대기"
    assert len(log_rows()) == 1

    db_module._convert_stored_late()      # 두 번째 — 아무 일도 없어야 한다
    assert len(log_rows()) == 1


def test_b04_상태_입력_선택지에_지연이_없다():
    """0번에서 찾은 자리 전부 — 드로어의 상태 칩 메뉴(drawer.js)와
    옛 폼 셀렉트(지운 템플릿들)."""
    js = _read("app", "static", "js", "drawer.js")
    m = re.search(r"PICKABLE\s*=\s*\[([^\]]*)\]", js)
    assert m, "고를 수 있는 상태 목록(PICKABLE)이 없다"
    assert "지연" not in m.group(1)
    assert "PICKABLE.map" in js, "메뉴가 그 목록에서 안 나온다"
    # 옛 폼 셀렉트가 있던 템플릿은 지웠다 (4-14)
    assert not (ROOT / "app" / "templates" / "task_detail.html").exists()
    macros = _read("app", "templates", "partials", "macros.html")
    assert "status-select" not in macros


# ════════════════════════════════════════════════════════════════════
# 1-c. 배지 판정 한 곳 (board.paint_of)
# ════════════════════════════════════════════════════════════════════


def test_c01_홈_목록_보드가_같은_run_에_같은_배지를_단다(world):
    """세 화면이 전부 board.paint_of 의 badge 를 받는다 — 값끼리 견준다."""
    with app_session() as db:
        retreat = db.get(models.Retreat, world["retreat"])
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()

        home = home_domain.build(db, retreat, admin, today=TODAY)
        lst = tasklist.build(db, retreat, today=TODAY, my_keys=None)
        board = board_domain.build(db, retreat, today=TODAY)

        by_row = {r["run_id"]: r["badge"] for r in lst.rows + lst.done_rows}
        board_status = {r["run_id"]: r["status"]
                        for d in board["departments"]
                        for r in d["rows"] if not r["ghost"]}

        for title, want in (("지난 마감", "지연"), ("한참 뒤 마감", "대기"),
                            ("진행중인 것", "진행중"), ("끝낸 것", "완료")):
            run_id = world["runs"][title]
            run = db.get(models.TaskRun, run_id)
            paint = board_domain.paint_of(run, TODAY)
            assert paint["badge"]["label"] == want, title
            assert by_row[run_id] == paint["badge"], f"목록이 다르다: {title}"
            assert board_status[run_id] == want, f"보드가 다르다: {title}"
            if run_id in home.badges:
                assert home.badges[run_id] == paint["badge"], f"홈이 다르다: {title}"


def test_c02_홈_목록_템플릿에_상태_분기가_없다():
    """화면이 상태를 다시 가르면 두 벌이 된다 (4-3). 낱말 검사 — 주석 제외.
    비교식과 배지 클래스 직접 조합이 둘 다 없어야 한다."""
    for name in ("home.html", "tasks.html"):
        src = _no_comments_jinja(_read("app", "templates", name))
        assert not re.search(r"==\s*['\"](대기|진행중|완료|지연)['\"]", src), name
        assert not re.search(r"stbadge (wait|prog|late|done)", src), (
            f"{name}: 배지 클래스를 화면이 직접 정하고 있다"
        )


# ════════════════════════════════════════════════════════════════════
# 1-d + 2. 목록 (4-14)
# ════════════════════════════════════════════════════════════════════


def test_d01_retreat_id_로_회차가_전환된다(admin_client, world):
    """알림 1,483건이 전부 /tasks?retreat_id=N 이다 — 이 길이 끊기면 알림이
    끊긴다 (4-11)."""
    page = admin_client.get(f"/tasks?retreat_id={world['other_retreat']}")
    assert page.status_code == 200
    assert "2027 겨울수련회" in page.text
    assert "겨울 준비" in page.text
    # 전환이 저장된다 — 다음 요청도 그 회차다
    again = admin_client.get("/tasks")
    assert "2027 겨울수련회" in again.text


def test_l01_지연_칩은_계산값이다(world):
    """마감이 미래인 행은 지연으로 세지 않는다 — 저장값이 아니라 overdue_of."""
    with app_session() as db:
        retreat = db.get(models.Retreat, world["retreat"])
        view = tasklist.build(db, retreat, today=TODAY, my_keys=None)
        runs = db.scalars(select(models.TaskRun).where(
            models.TaskRun.retreat_id == retreat.id, models.TaskRun.included)).all()
        # 값끼리 맞는지 본다 — 숫자를 박지 않는다 (11-3)
        assert view.state_counts["late"] == sum(
            1 for r in runs if board_domain.overdue_of(r, TODAY))
        assert sum(view.state_counts.values()) == view.total
    # 지연 필터에는 마감 미래 행이 없다
    with app_session() as db:
        retreat = db.get(models.Retreat, world["retreat"])
        late = tasklist.build(db, retreat, today=TODAY, my_keys=None, state="late")
        titles = [r["title"] for r in late.rows]
        assert "지난 마감" in titles and "한참 뒤 마감" not in titles


def test_l02_완료에_DN_이_없다(admin_client, world):
    """완료 행에는 D+N 을 붙이지 않는다 (4-14). 붙는 쪽(미완료 지연)도 함께
    잰다 — 막는 쪽만 보면 검사가 빈다."""
    with app_session() as db:
        retreat = db.get(models.Retreat, world["retreat"])
        view = tasklist.build(db, retreat, today=TODAY, my_keys=None)
    done = next(r for r in view.done_rows if r["title"] == "끝낸 것")
    assert done["dday"] is None                       # 마감이 지났어도
    late = next(r for r in view.rows if r["title"] == "지난 마감")
    assert late["dday"] == "D+2"                      # 미완료에는 붙는다

    page = admin_client.get(f"/tasks?retreat_id={world['retreat']}").text
    done_at = page.index("끝낸 것")
    row_html = page[done_at:page.index("lslot", done_at)]
    assert "D+" not in row_html


def test_l03_삭제_단추가_없다():
    """목록에도 드로어에도 삭제는 없다 (4-9 · 0장). 주석은 걷고 본다 (10장)."""
    for name in ("tasks.html", "partials/drawer.html", "partials/taskrow.html"):
        src = _no_comments_jinja(_read("app", "templates", *name.split("/")))
        assert "삭제" not in src, f"{name} 에 삭제가 있다"


def test_l04_목록의_상세는_드로어_한_벌이다(admin_client, world):
    """같은 Jinja partial · 같은 JS · 같은 엔드포인트 (4-14)."""
    page = admin_client.get(f"/tasks?retreat_id={world['retreat']}").text
    assert page.count('id="drawer"') == 1             # partials/drawer.html
    # 배지가 태그로 그려진다 — Markup 이 섞이면 글자 그대로 찍힌다 (실제로 그랬다)
    assert '<span class="stbadge' in page
    assert "&lt;span" not in page
    # 정적 주소는 내용 해시가 붙는다 (11-2) — 이름만 본다
    assert re.search(r"js/drawer\.[0-9a-f]*\.?js", page)
    assert re.search(r"js/tasks\.[0-9a-f]*\.?js", page)
    # 화면 다듬기 판에서 버튼 줄이 빠지고 **업무 이름을 눌러** 연다 (4-14) —
    # 여는 자리는 행의 이름과 오른쪽 끝 캐럿이다
    assert 'class="cell caretc"' in page
    assert "lopen" not in page and "lfoot" not in page
    # tasks.js 는 제 주소를 만들지 않는다 — 요청은 전부 drawer.js 가
    # 보드와 같은 주소(/board/task/…)로 보낸다
    tjs = _read("app", "static", "js", "tasks.js")
    assert "fetch(" not in tjs
    djs = _read("app", "static", "js", "drawer.js")
    assert "/board/task/" in djs
    # 진단 패널도 같은 partial 안에 있다 (4-10)
    drawer = _read("app", "templates", "partials", "drawer.html")
    assert 'id="diag"' in drawer


def test_l05_task_파라미터로_그_행이_펼쳐진_채_열린다(admin_client, world):
    run_id = world["runs"]["끝낸 것"]                  # 완료 접힘 안의 행
    page = admin_client.get(
        f"/tasks?retreat_id={world['retreat']}&task={run_id}").text
    assert f'data-open-task="{run_id}"' in page
    assert "<details class=\"ldone\" open>" in page   # 접힘을 서버가 미리 편다
    # 열려던 행이 접힘 밖이면 접힘은 접힌 채다
    open_id = world["runs"]["한참 뒤 마감"]
    page2 = admin_client.get(
        f"/tasks?retreat_id={world['retreat']}&task={open_id}").text
    assert "<details class=\"ldone\" open>" not in page2
    # 펼침·스크롤은 tasks.js 의 openFromUrl 이 맡는다
    tjs = _read("app", "static", "js", "tasks.js")
    assert "openFromUrl" in tjs and "scrollIntoView" in tjs


def test_l06_옛_상세_주소는_목록으로_301_이고_행은_남는다(admin_client, world):
    with app_session() as db:
        retreat_id = world["retreat"]
        for i in range(3):
            db.add(models.Task(retreat_id=retreat_id, title=f"옛 할 일 {i}",
                               blocked_by_task_ids=[], related_department_ids=[]))
        db.commit()
        before = len(db.scalars(select(models.Task)).all())
        first = db.scalars(select(models.Task)).first().id

    r = admin_client.get(f"/tasks/{first}", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/tasks"
    assert admin_client.get("/tasks").status_code == 200
    with app_session() as db:
        assert len(db.scalars(select(models.Task)).all()) == before


def test_l07_시작일_순_정렬과_완료_접힘(admin_client, world):
    with app_session() as db:
        retreat = db.get(models.Retreat, world["retreat"])
        view = tasklist.build(db, retreat, today=TODAY, my_keys=None)
        starts = []
        for row in view.rows:
            run = db.get(models.TaskRun, row["run_id"])
            starts.append(run.start_date)
    assert starts == sorted(starts)                   # 시작일 순 (4-14 · 6-6)
    page = admin_client.get(f"/tasks?retreat_id={world['retreat']}").text
    assert f"완료 {len(view.done_rows)}건 보기" in page


def test_l08_흐림은_부서_키로_가른다(world, client):
    """소속이 **다른 회차의** 같은 키 부서여도 내 부서 행은 선명하다 (2장)."""
    with app_session() as db:
        retreat = db.get(models.Retreat, world["retreat"])
        # 겨울 회차의 헤브론(hebron2)에 묶인 리더 — 키는 같은 hebron 이다
        lead = legacy_user(db, name="헤브론 리더", phone_number="01099998888",
                           role="dept_lead", dept=world["hebron2"])
        db.add(lead)
        db.commit()
        view = tasklist.build(db, retreat, today=TODAY, my_keys={"hebron"})
        by_title = {r["title"]: r["dim"] for r in view.rows + view.done_rows}
        # 총무팀은 전부 선명하다 — 홈·옛 화면과 같은 규칙 (4-15)
        admin_view = tasklist.build(db, retreat, today=TODAY,
                                    my_keys={"hebron"}, dim=False)
        admin_dim = {r["title"]: r["dim"] for r in admin_view.rows + admin_view.done_rows}
    assert by_title["헤브론 일"] is False              # 같은 키 → 선명
    assert by_title["지난 마감"] is True               # 다른 키 → 흐림
    assert not any(admin_dim.values()), "총무팀에게 흐린 행이 있다"


# ════════════════════════════════════════════════════════════════════
# 3. 논의 걸린 곳 (4-9)
# ════════════════════════════════════════════════════════════════════


def _entry_of(run_id):
    with app_session() as db:
        return db.scalars(
            select(models.DiscussionEntryRun).where(
                models.DiscussionEntryRun.run_id == run_id)
        ).all()


def test_e01_링크_행이_없는_논의만_한_번_옮긴다(world):
    from app import db as db_module

    run_id = world["runs"]["한참 뒤 마감"]
    with app_session() as db:
        db.add(models.DiscussionEntry(_legacy_run_id=run_id, authored_at=TODAY,
                                      body="옛 모양 그대로의 논의"))
        db.commit()

    db_module._link_discussion_runs()
    assert len(_entry_of(run_id)) == 1
    db_module._link_discussion_runs()                 # 두 번 떠도
    assert len(_entry_of(run_id)) == 1


def _py_code_only(src: str) -> str:
    """주석·독스트링·문자열을 걷어낸다 — 글자를 찾는 시험은 코드와 설명을 못
    가린다 (10장). 규칙을 설명한 주석이 제 검사에 걸리면 안 된다."""
    src = re.sub(r'("""|\'\'\')(?:.|\n)*?\1', '""', src)
    src = re.sub(r"#[^\n]*", "", src)
    src = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", src)
    return src


def test_e02_runId_를_읽는_코드가_0곳이다():
    """걸린 곳의 유일한 출처는 링크 표다 (4-9). 예외는 **옮기는 코드 한 곳**
    (db._link_discussion_runs 의 SQL 문자열)뿐이다.

    낱말 grep 은 변수 이름으로 뚫린다 — 검토에서 `e.run_id` 한 곳이 실제로
    빠져나갔다. 그래서 **속성 이름 자체를 바꿔** 읽기를 구조로 막는다:
    `entry.run_id` 는 AttributeError 다. 여기서는 그 구조가 서 있는지와,
    쓰기용 새 이름(_legacy_run_id)이 정해진 자리 밖으로 안 새는지를 본다."""
    # 1) 읽을 속성이 아예 없다 — 어떤 변수 이름으로도 못 읽는다
    assert not hasattr(models.DiscussionEntry, "run_id")
    with pytest.raises(AttributeError):
        models.DiscussionEntry(_legacy_run_id=1, body="x").run_id  # noqa: B018

    # 2) 쓰기용 이름은 정해진 자리(정의 + 만드는 곳 셋 + 시드)에만 있다
    allowed = {"models.py", "board.py", "library.py", "meetings.py"}
    hits = []
    checked = 0
    for path in (ROOT / "app").rglob("*.py"):
        checked += 1
        src = _py_code_only(path.read_text(encoding="utf-8"))
        for m in re.finditer(r"_legacy_run_id\s*(=?)", src):
            if path.name not in allowed:
                hits.append(f"{path.name}: {m.group(0)}")
            elif path.name != "models.py" and m.group(1) != "=":
                hits.append(f"{path.name}: 쓰기(=)가 아닌 참조")
    assert checked > 10, "아무것도 안 본 검사는 통과가 아니다 (11-3)"
    assert hits == [], f"_legacy_run_id 가 새어 나간 곳: {hits}"

    # 3) 옮기는 곳(예외)은 실제로 있다 — 아무것도 안 보는 검사가 아니다
    db_src = _read("app", "db.py")
    assert "_link_discussion_runs" in db_src and "e.run_id" in db_src
    # 걷어내기가 걸러야 할 것을 실제로 남기는지도 본다 (막는 쪽 시험)
    assert re.search(r"_legacy_run_id\s*=?", _py_code_only("x = e._legacy_run_id"))


def test_e03_걸린_곳이_줄에_실린다(admin_client, world):
    """한 곳뿐이면 화면이 조용하도록 runs 가 하나고, 둘에 걸면 「여기」 와
    상대 업무 이름이 함께 나간다 (4-9)."""
    a, b = world["runs"]["한참 뒤 마감"], world["runs"]["진행중인 것"]
    made = admin_client.post(f"/board/task/{a}/discussion",
                             json={"body": "명찰 사이즈 논의"})
    assert made.status_code == 200
    row = made.json()["discussions"][-1]
    assert [x["here"] for x in row["runs"]] == [True]  # 한 곳 — 여기뿐

    with app_session() as db:
        entry = db.get(models.DiscussionEntry, row["id"])
        discussion.attach(db, entry, db.get(models.TaskRun, b))
        db.commit()

    for run_id, other_title in ((a, "진행중인 것"), (b, "한참 뒤 마감")):
        detail = admin_client.get(f"/board/task/{run_id}").json()
        got = next(x for x in detail["discussions"] if x["id"] == row["id"])
        assert len(got["runs"]) == 2
        here = next(x for x in got["runs"] if x["here"])
        there = next(x for x in got["runs"] if not x["here"])
        assert here["run_id"] == run_id
        assert there["title"] == other_title


def test_e04_마지막_한_곳은_떼지_못한다(admin_client, world):
    a, b = world["runs"]["한참 뒤 마감"], world["runs"]["진행중인 것"]
    entry_id = admin_client.post(f"/board/task/{a}/discussion",
                                 json={"body": "떼기 시험"}).json()["discussions"][-1]["id"]

    # 막는 쪽 — 한 곳뿐일 때는 400
    blocked = admin_client.post(f"/board/task/{a}/discussion/{entry_id}/detach")
    assert blocked.status_code == 400

    with app_session() as db:
        entry = db.get(models.DiscussionEntry, entry_id)
        discussion.attach(db, entry, db.get(models.TaskRun, b))
        db.commit()

    ok = admin_client.post(f"/board/task/{a}/discussion/{entry_id}/detach")
    assert ok.status_code == 200
    assert all(x["id"] != entry_id for x in ok.json()["discussions"])  # 이쪽에서 사라짐
    other = admin_client.get(f"/board/task/{b}").json()
    assert any(x["id"] == entry_id for x in other["discussions"])      # 저쪽엔 남음
    with app_session() as db:
        # 지운 것이 아니라 뗀 것이다 — 행이 detached_at 을 달고 남는다
        link = db.scalars(select(models.DiscussionEntryRun).where(
            models.DiscussionEntryRun.entry_id == entry_id,
            models.DiscussionEntryRun.run_id == a)).one()
        assert link.detached_at is not None
        logged = db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "논의_떼기",
            models.ActivityLog.target_id == entry_id)).all()
        assert len(logged) == 1


def test_e05_제안_반영은_본문_한_행에_링크_N행이다(admin_client, world):
    """업무 둘에 걸린 제안을 반영하면 DiscussionEntry 한 행 + 링크 행 둘,
    출처(source_meeting_id)가 그 회의록을 가리킨다 (4-9)."""
    a, b = world["runs"]["한참 뒤 마감"], world["runs"]["진행중인 것"]
    with app_session() as db:
        meeting = models.Meeting(
            retreat_id=world["retreat"], title="8월 총무팀 회의",
            meeting_date=dt.date(2026, 8, 9), body="명찰 관련 논의")
        db.add(meeting)
        db.commit()
        meeting_id = meeting.id
        before_entries = len(db.scalars(select(models.DiscussionEntry)).all())

    r = admin_client.post(f"/meetings/{meeting_id}/suggestions/apply",
                          json={"run_ids": [a, b]})
    assert r.status_code == 200
    entry_id = r.json()["entry_id"]

    with app_session() as db:
        assert len(db.scalars(select(models.DiscussionEntry)).all()) == before_entries + 1
        links = db.scalars(select(models.DiscussionEntryRun).where(
            models.DiscussionEntryRun.entry_id == entry_id)).all()
        assert sorted(l.run_id for l in links) == sorted([a, b])
        assert db.get(models.DiscussionEntry, entry_id).source_meeting_id == meeting_id

    detail = admin_client.get(f"/board/task/{a}").json()
    got = next(x for x in detail["discussions"] if x["id"] == entry_id)
    assert got["source"] == {"meeting_id": meeting_id, "label": "8/9 회의"}


def test_e04b_권한_없는_사람은_떼지_못한다(admin_client, world, client):
    """떼기도 「그 업무를 고칠 수 있는 사람」 의 일이다 (4-9) — 막는 쪽."""
    a = world["runs"]["한참 뒤 마감"]                  # 총무M 부서의 업무
    entry_id = admin_client.post(f"/board/task/{a}/discussion",
                                 json={"body": "권한 시험"}).json()["discussions"][-1]["id"]
    make_user("헤브론 부원", "01077770001", "member", dept=world["hebron"])
    login_as(client, "01077770001")
    client.get(f"/board?retreat_id={world['retreat']}")   # 같은 회차를 본다
    assert client.post(
        f"/board/task/{a}/discussion/{entry_id}/detach"
    ).status_code == 403


def test_e05b_빈_run_ids_는_400_이다(admin_client, world):
    """걸 곳 없이 반영하면 붙을 곳 없는 논의가 된다 — 막는 쪽."""
    with app_session() as db:
        meeting = models.Meeting(retreat_id=world["retreat"], title="빈 반영 시험",
                                 meeting_date=dt.date(2026, 8, 10), body="본문")
        db.add(meeting)
        db.commit()
        meeting_id = meeting.id
    assert admin_client.post(f"/meetings/{meeting_id}/suggestions/apply",
                             json={"run_ids": []}).status_code == 400


def test_e06_경고와_출처_문구가_화면에_있다():
    """고치기 전 「업무 N곳에 걸린 논의입니다」 · 「직접 적음」 · 떼기 (4-9)."""
    js = _read("app", "static", "js", "drawer.js")
    assert "곳에 걸린 논의입니다" in js
    assert "직접 적음" in js
    assert "여기서 떼기" in js and "data-detach" in js


# ════════════════════════════════════════════════════════════════════
# 4. 마법사 3단계 행 = 목록과 같은 partial (6-6 · 4-14)
# ════════════════════════════════════════════════════════════════════


def test_m01_마법사_행이_같은_partial_에서_나온다(admin_client, world):
    open_date = (TODAY + dt.timedelta(days=90)).isoformat()
    data = admin_client.post("/setup/preview", json={"open_date": open_date}).json()
    assert data["items"], "라이브러리가 비어 시험이 헛돈다"
    for item in data["items"]:
        assert 'class="trow' in item["row_html"], item["title"]
        assert '<span class="box">' in item["row_html"]     # 체크박스만 마법사의 것
    # 마법사 JS 는 행 모양을 더 이상 직접 만들지 않는다
    sjs = _read("app", "static", "js", "setup.js")
    assert '<span class="main">' not in sjs
    assert "row_html" in sjs
    # 목록도 같은 partial 을 쓴다
    tasks_tpl = _read("app", "templates", "tasks.html")
    assert 'from "partials/taskrow.html" import taskrow' in tasks_tpl
    setup_src = _read("app", "routers", "setup.py")
    assert "partials/taskrow.html" in setup_src


# ════════════════════════════════════════════════════════════════════
# 5. 달력 — partial · 드로어 유지 (4-13)
# ════════════════════════════════════════════════════════════════════


def test_f01_전체_페이지와_partial_이_같은_것을_그린다(admin_client, world):
    """같은 달을 두 길로 받아 **출력이 같은지** 본다 — 같은 _view · 같은
    partial 이면 격자 HTML 이 그대로 일치한다."""
    q = "month=2026-10-01&scope=all&only_open=0"
    full = admin_client.get(f"/calendar?{q}").text
    part = admin_client.get(f"/calendar/partial?{q}").text.strip()
    assert 'id="calgrid"' in part
    assert part in full, "전체 페이지의 격자와 partial 의 격자가 다르다"
    # partial 에는 격자 밖 것이 없다 — 갈아 끼워도 나머지 DOM 이 그대로다
    for outside in ('class="calbar"', 'id="drawer"', "calundated", "sidenav"):
        assert outside not in part, f"partial 에 격자 밖 것이 있다: {outside}"
    assert full.count('id="calgrid"') == 1


def test_f02_달_넘기기가_격자만_갈아_끼운다():
    """**낱말만 잰다** — 달이 실제로 미끄러지고 드로어가 살아 있는지는
    `docs/checks/drawer.js` 의 달력 판이 브라우저에서 잰다 (4-13)."""
    js = _read("app", "static", "js", "calendar.js")
    assert "/calendar/partial" in js
    assert "replaceState" in js
    assert "old.replaceWith(next)" in js               # #calgrid 교체
    assert "Drawer.close" not in js                    # 드로어는 건드리지 않는다
    # 휠 — 누적 ±120 · 이동 후 350ms 무시 · 격자 위에서만
    assert "120" in js and "350" in js
    assert ".calwrap" in js
    assert "prefers-reduced-motion" in js


def test_f03_화살표가_partial_로_간다(world):
    tpl = _read("app", "templates", "calendar.html")
    assert 'data-nav="prev"' in tpl and 'data-nav="next"' in tpl
    # href 는 남는다 — 자바스크립트가 죽었을 때의 길
    assert re.search(r'data-nav="prev" href="/calendar\?month=', tpl)
