"""조용히 사라지는 길 막기 — 회의 항목 → 할 일 전환이 보이는 업무를 만든다.

옛 Task 를 만들던 시절에는 전환한 항목이 어느 화면에도 안 나타났다 —
옛 /tasks 화면을 걷어낸 뒤(14장) Task 표는 아무 화면도 안 읽는다.
막는 쪽이 아니라 **보이는 쪽을 잰다** (지시문 1-e).

번호 마무리(2번)도 여기 있다 — 하이픈 지역번호의 원표기가 두 검사에 다
걸리는지, swap 이 번호 변형(3-4-4)도 바꾸는지.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import sqlite3

from sqlalchemy import select

from app import models
from tests.conftest import app_session
from tests.test_web_flows import _create_departments, _create_retreat

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = dt.date.today()


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _회의와_항목(admin_client, dept_id, due=None):
    admin_client.post(
        "/meetings/create",
        data={"title": "주간 점검 회의", "meeting_date": TODAY.isoformat(),
              "attendees": "", "body": "논의", "link_retreat": "retreat"},
        follow_redirects=True,
    )
    with app_session() as db:
        meeting = db.scalars(select(models.Meeting)).one()
    admin_client.post(
        f"/meetings/{meeting.id}/items",
        data={"kind": "액션아이템", "content": "현수막 시안 확정",
              "department_id": str(dept_id),
              "due_date": due.isoformat() if due else ""},
        follow_redirects=True,
    )
    with app_session() as db:
        item = db.scalars(select(models.MeetingItem)).one()
    return meeting, item


# ════════════════════════════════════════════════════════════════════
# 1-e. 전환하면 보인다 — 막는 쪽이 아니라 보이는 쪽
# ════════════════════════════════════════════════════════════════════


def test11_t01_전환하면_목록에_보이고_드로어로_간다(admin_client):
    """할 일로 넘기면 (1) 응답이 그 업무의 드로어(/tasks?task=)로 보내고
    (2) /tasks 목록 HTML 에 제목이 실제로 있다. 옛 Task 행 수는 안 는다."""
    _create_retreat(admin_client)
    depts = _create_departments(admin_client, ["홍보팀"])
    _, item = _회의와_항목(admin_client, depts[0].id, due=TODAY + dt.timedelta(days=7))
    with app_session() as db:
        옛task수 = len(db.scalars(select(models.Task)).all())

    res = admin_client.post(f"/meetings/items/{item.id}/to-task",
                            follow_redirects=False)
    assert res.status_code in (302, 303)
    with app_session() as db:
        run = db.scalars(select(models.TaskRun)).one()
        assert f"/tasks?task={run.id}" in res.headers["location"]
        # 옛 Task 행 수 불변 (1-d — 옮기지도, 새로 만들지도 않는다)
        assert len(db.scalars(select(models.Task)).all()) == 옛task수

    목록 = admin_client.get("/tasks", follow_redirects=True)
    assert 목록.status_code == 200
    assert "현수막 시안 확정" in 목록.text     # 보이는 쪽


def test11_t02_출처가_그_회의록을_가리킨다(admin_client):
    _create_retreat(admin_client)
    depts = _create_departments(admin_client, ["홍보팀"])
    meeting, item = _회의와_항목(admin_client, depts[0].id)

    admin_client.post(f"/meetings/items/{item.id}/to-task", follow_redirects=True)
    with app_session() as db:
        run = db.scalars(select(models.TaskRun)).one()
        assert run.source_meeting_id == meeting.id
        assert db.get(models.MeetingItem, item.id).converted_run_id == run.id
        # 날짜 없는 항목은 날짜를 지어내지 않는다 — 달력의 「날짜 없는
        # 업무」 로 모여 사람이 정한다 (4-13)
        assert run.start_date is None and run.end_date is None


def test11_t03_옛_Task_로_전환됐던_항목은_다시_만들지_않는다(admin_client):
    """옛 길로 이미 전환된 항목(converted_task_id)에 새 run 을 만들면 같은
    항목의 할 일이 둘이 된다 — 막고, 그 사실을 말한다."""
    _create_retreat(admin_client)
    depts = _create_departments(admin_client, ["홍보팀"])
    _, item = _회의와_항목(admin_client, depts[0].id)
    with app_session() as db:
        옛 = models.Task(retreat_id=db.scalars(select(models.Retreat)).first().id,
                        title="옛 길의 할 일", status="대기",
                        blocked_by_task_ids=[], related_department_ids=[])
        db.add(옛)
        db.flush()
        db.get(models.MeetingItem, item.id).converted_task_id = 옛.id
        db.commit()

    admin_client.post(f"/meetings/items/{item.id}/to-task", follow_redirects=True)
    with app_session() as db:
        assert db.scalars(select(models.TaskRun)).all() == []


# ════════════════════════════════════════════════════════════════════
# 수용 3. 옛 Task 를 만드는 코드가 앱에 없다 (0-a 와 견줌)
# ════════════════════════════════════════════════════════════════════


def 생성자리(src: str, 이름: str = "Task") -> list[int]:
    """`이름(` 생성 호출이 선 줄들 — **주석·문자열을 걷어내고** 본다.

    글자를 찾는 시험은 코드와 설명을 못 가린다(10장 — 네 번 당한 자리).
    토큰으로 보면 주석에 「옛 Task() 를 만들지 않는다」 라고 적어도 안
    걸리고, 실제 생성 호출만 걸린다. class 정의는 앞 토큰이 class 라
    제외한다. test_stage12 의 「만드는 곳은 한 곳」 grep 도 이것을 쓴다."""
    import io
    import tokenize

    줄들: list[int] = []
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    for i, t in enumerate(toks):
        if t.type != tokenize.NAME or t.string != 이름:
            continue
        앞 = toks[i - 1] if i else None
        뒤 = toks[i + 1] if i + 1 < len(toks) else None
        if 앞 is not None and 앞.type == tokenize.NAME and 앞.string == "class":
            continue
        if 뒤 is not None and 뒤.type == tokenize.OP and 뒤.string == "(":
            줄들.append(t.start[0])
    return 줄들


def _옛Task생성자리(src: str) -> list[int]:
    return 생성자리(src, "Task")


def test11_g01_옛_Task_를_만드는_코드가_앱에_없다():
    """0-a 전수는 둘이었다 — app/routers/meetings.py 의 전환 라우트와
    seed.py 의 데모 시드. 라우트는 TaskRun 으로 바뀌어 앱 런타임 경로는
    0곳이다. seed.py 는 화면에서 닿지 않는 개발용 데모 자료라 남긴다 —
    옛 표의 행은 남긴다 (0장)."""
    나쁜곳 = []
    for p in (ROOT / "app").rglob("*.py"):
        for 번호 in _옛Task생성자리(p.read_text(encoding="utf-8")):
            나쁜곳.append(f"{p.name}:{번호}")
    assert 나쁜곳 == [], f"옛 Task 를 만드는 곳: {나쁜곳}"


def test11_g02_주석과_문자열은_걸리지_않고_생성은_걸린다():
    """막는 검사의 세 벌(11-3) — 막혀야 할 것(생성 호출)이 막히고,
    막히면 안 되는 것(주석·문자열·class 정의)이 통과하고, 검사가 실제로
    보고 있다(빈 소스는 0)."""
    주석뿐 = "# 옛 Task() 를 만들지 않는다\n말 = '여기 Task( 는 글자다'\n"
    assert _옛Task생성자리(주석뿐) == []
    assert _옛Task생성자리("class Task(Base):\n    pass\n") == []
    걸림 = _옛Task생성자리("# Task( 설명\nt = Task(retreat_id=1)\n")
    assert 걸림 == [2]
    assert _옛Task생성자리("t = models.Task(x)\n") == [1]


# ════════════════════════════════════════════════════════════════════
# 2-a. 하이픈 지역번호를 대응표에 넣으면 원표기가 두 검사 다 걸린다
# ════════════════════════════════════════════════════════════════════


def test11_p01_하이픈_지역번호_원표기가_두_검사_다_걸린다(tmp_path):
    """합성 대응표로 규칙 자체를 잰다 — 번호변형들 이 원표기를 늘 보존하므로
    (검토자 3번 반영), 11자리가 아닌 하이픈 표기도 그 모양 그대로 걸린다."""
    맵 = tmp_path / "map.json"
    맵.write_text(json.dumps({
        "names": [["가나다", "마바사"]],
        "phones": [["02-123-4567", "02-987-6543"]],
    }, ensure_ascii=False), encoding="utf-8")
    cn = _load("check_names")
    dev = _load("check_dev_db")
    cn._anon.MAP_PATH = 맵
    dev._anon.MAP_PATH = 맵

    실명 = cn._anon.표기들()
    assert "02-123-4567" in 실명            # 원표기 보존 (2-a)

    p = tmp_path / "글.md"
    p.write_text("사무실 번호는 02-123-4567 입니다", encoding="utf-8")
    assert cn.찾는다(실명, [p])              # 문서 검사 — 걸린다
    p.write_text("사무실 번호는 02-987-6543 입니다", encoding="utf-8")
    assert not cn.찾는다(실명, [p])          # 가명 원표기 — 통과

    db = tmp_path / "one.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE meetings (body TEXT)")
    con.execute("INSERT INTO meetings VALUES ('사무실 번호는 02-123-4567 입니다')")
    con.commit()
    con.close()
    assert dev.실명이있나(db)                # 게이트 — 같은 문자열에 같은 판정


# ════════════════════════════════════════════════════════════════════
# 2-b. swap 이 번호 변형도 바꾼다 — 미리보기와 --apply 는 같은 함수다
# ════════════════════════════════════════════════════════════════════


def test11_p02_swap_이_3_4_4_실번호를_바꾼다():
    """미리보기(무인자)와 --apply 는 둘 다 swap() 하나를 지난다(anonymize.py
    main) — 함수가 바꾸면 미리보기에 나오고 --apply 로 바뀐다. 합성 번호로
    잰다. 모양은 보존된다 — 3-4-4 는 가명의 3-4-4 로."""
    anon = _load("anonymize")
    phones = [("01012345678", "01087654321")]

    글, n = anon.swap("연락처 010-1234-5678 입니다", names=[], phones=phones)
    assert n == 1 and "010-8765-4321" in 글 and "1234-5678" not in 글

    # 숫자 그대로 형과 공백 형도
    글, n = anon.swap("연락처 01012345678 · 010 1234 5678", names=[], phones=phones)
    assert n == 2 and "01087654321" in 글 and "010 8765 4321" in 글

    # 문서(.md)는 입력 불가능한 자리표시 모양으로 (기존 규칙 그대로)
    글, n = anon.swap("연락처 010-1234-5678", doc=True, names=[], phones=phones)
    assert n == 1 and anon.DOC_PHONE in 글
