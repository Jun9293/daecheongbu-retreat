"""화면 손보기 · 두 번 만들기 막기 (+ 파싱 한 곳으로).

쓰면서 걸린 셋(회의록 작성란 · 목록 필터 · 행 열기)과 지난 판이 남긴
셋(AC-a 두 번 만들기 · AC-b 파싱 세 벌 · AC-d 부서 없는 업무의 문)을
함께 닫는다.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

from sqlalchemy import select

from app import models
from app.domain import suggest as suggest_mod
from tests.conftest import app_session, login_as, make_user
from tests.test_stage12 import _세팅, _회의와_항목, _run_of

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = dt.date.today()
D = TODAY + dt.timedelta(days=14)

JS = ROOT / "app" / "static" / "js"
CSS = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")


def _decl(sel: str) -> str:
    """그 선택자의 선언부 — 주석은 걷어낸다 (글자를 찾는 시험의 그 함정)."""
    body = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    at = body.index(sel + "{")
    return body[at + len(sel) + 1: body.index("}", at)]


# ════════════════════════════════════════════════════════════════════
# 1. 회의록 작성란 — 손잡이 없이 내용만큼 길어진다
# ════════════════════════════════════════════════════════════════════


def test13_w01_작성란에_손잡이가_없다():
    """CSS 에 resize 손잡이가 없다. 최소 높이는 그대로 — 빈 회의록이
    갑자기 한 줄짜리가 되면 적을 자리가 없어 보인다."""
    d = _decl(".mt-one-body")
    assert "resize:none" in d
    assert "resize:vertical" not in d
    assert "min-height:340px" in d


def test13_w02_내용만큼_길어지는_코드가_한_곳이고_켜는_곳에만_붙는다():
    """높이를 scrollHeight 로 잡고, `data-autogrow` 를 단 칸에만 붙는다.
    논의 입력칸(드로어 안)은 켜지 않는다 — 패널이 통째로 길어진다."""
    js = (JS / "listinput.js").read_text(encoding="utf-8")
    assert "scrollHeight" in js
    assert "data-autogrow" in js
    # 테두리를 더한다 — border-box 라 안 더하면 1px 스크롤이 남는다
    assert "offsetHeight - box.clientHeight" in js
    # 붙여넣기·지우기까지 한 이벤트로
    assert "'input'" in js
    html = (ROOT / "app" / "templates" / "meeting_detail.html").read_text(encoding="utf-8")
    assert "data-autogrow" in html
    drawer = (ROOT / "app" / "templates" / "partials" / "drawer.html").read_text(
        encoding="utf-8")
    assert "data-autogrow" not in drawer, "논의 입력칸에는 켜지 않는다"


# ════════════════════════════════════════════════════════════════════
# 2. 목록 필터 — 부서 드롭다운이 곧 범위다
# ════════════════════════════════════════════════════════════════════


def _목록(client, qs=""):
    r = client.get("/tasks" + qs)
    assert r.status_code == 200
    return r.text


def _업무둘(admin_client, depts):
    admin_client.post("/board/add/new", json={
        "title": "홍보 포스터", "department_key": "hongbo",
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})
    admin_client.post("/board/add/new", json={
        "title": "찬양 콘티", "department_key": "chanyang",
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})


def test13_f01_내_부서_전체_칩이_없다(admin_client):
    _, depts = _세팅(admin_client)
    _업무둘(admin_client, depts)
    html = _목록(admin_client)
    # 칩 줄에 그 두 글자가 없다 — 드롭다운이 그 일을 한다
    assert ">내 부서<" not in html
    assert "scope=mine" not in html and "scope=all" not in html
    assert 'id="ldept"' in html


def test13_f02_드롭다운으로_내_부서를_고르면_옛_내_부서와_같다(admin_client):
    """같은 결과 = 같은 행. 옛 주소(?scope=mine)와 새 주소(?dept=키)를
    나란히 받아 견준다."""
    _, depts = _세팅(admin_client)
    _업무둘(admin_client, depts)
    from fastapi.testclient import TestClient

    from app.main import app

    make_user("홍보 리더", "01077770101", "dept_lead", depts[0].id)
    c = TestClient(app)
    login_as(c, "01077770101", name="홍보 리더")

    새 = _목록(c, "?dept=hongbo")
    옛 = _목록(c, "?scope=mine")           # 옛 주소가 살아 있다 (2-d)
    for html in (새, 옛):
        assert "홍보 포스터" in html and "찬양 콘티" not in html
    # 옛 주소도 드롭다운에 그 부서가 골라진 채로 온다
    assert 'value="hongbo" selected' in 옛


def test13_f03_상태_건수는_고른_부서_안에서_센다(admin_client):
    """드롭다운이 범위이므로 상태 칩의 수도 그 안이다 — 「홍보팀 · 대기 1」.
    부서 건수는 반대로 **전체**에서 센다: 다른 부서로 옮겨 갈 수 있어야 한다."""
    _, depts = _세팅(admin_client)
    _업무둘(admin_client, depts)
    from app.domain import tasklist

    with app_session() as db:
        retreat = db.scalars(select(models.Retreat)).first()
        전체 = tasklist.build(db, retreat, today=TODAY, my_key=None, dim=False)
        하나 = tasklist.build(db, retreat, today=TODAY, my_key=None, dim=False,
                            dept="hongbo")
    assert 전체.state_counts["wait"] == 2
    assert 하나.state_counts["wait"] == 1                 # 고른 부서 안에서
    assert {d["key"] for d in 하나.dept_counts} == {"hongbo", "chanyang"}


def test13_f04_정렬_단추가_상태_칩보다_작다():
    """크기는 눈금에서 끌어온다 — 배지가 쓰는 장식 단(--fz-xs)이고
    새 값을 만들지 않는다 (4-0)."""
    단 = ["--fz-xs", "--fz-sm", "--fz-md", "--fz-base",
         "--fz-lg", "--fz-xl", "--fz-2xl", "--fz-3xl", "--fz-4xl"]
    번호 = lambda sel: 단.index(                                   # noqa: E731
        re.search(r"font-size:var\((--fz[\w-]*)\)", _decl(sel)).group(1))
    assert 번호(".tlist .lsort .chip") < 번호(".tlist .chip")


# ════════════════════════════════════════════════════════════════════
# 3. 행 아무 데나 눌러 열기 — 목록은 「안 여는 자리」 다
# ════════════════════════════════════════════════════════════════════


def test13_r01_안_여는_자리_목록이지_여는_자리_목록이_아니다():
    """새 요소가 생기면 **열림 쪽이 기본**이어야 한다 — 그러려면 코드가
    「무엇이 열리는가」 가 아니라 「무엇이 안 열리는가」 를 적어야 한다.

    **낱말만 잰다** — 행을 눌러 실제로 열리는지는 브라우저에서만 잴 수
    있어 `docs/checks/drawer.js` 의 목록 항목이 잰다(「행의 빈 곳(메타)을
    눌러도 열림」·「상태 칸을 눌러도 그 행이 안 열림」). 여기서는 **규칙이
    어느 모양으로 적혀 있는지**를 본다 — 여는 자리를 세어 두면 칸이 하나
    늘 때마다 그 목록을 고쳐야 하고, 안 고치면 그 칸만 조용히 죽는다.
    """
    js = (JS / "tasks.js").read_text(encoding="utf-8")
    assert "안여는곳" in js
    # 예외는 **바꿀 수 있는** 상태 칸뿐이다 — 못 바꾸는 사람에게는 그
    # 칸도 행의 다른 곳과 같다(4-14). 넓게 두면 그 사람에게만 행
    # 오른쪽 끝이 죽은 면이 되고 화면에는 아무 표시도 나지 않는다
    assert ".cell.st.pick" in js
    # 이름·캐럿만 여는 옛 규칙이 남아 있지 않다
    코드 = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    코드 = re.sub(r"//[^\n]*", "", 코드)
    assert "'.nm, .caretc'" not in 코드
    # 커서도 행 전체에 (3-b) — 바꿀 수 있는 칸만 그 자리의 커서다
    assert "cursor:pointer" in _decl(".trow.lrow")
    assert "cursor:pointer" in _decl(".trow.lrow .cell.st.pick")
    assert "cursor" not in _decl(".trow.lrow .cell.st"), \
        "못 바꾸는 칸에 따로 커서를 주면 행과 다르게 보인다"


def test13_r01b_행_안은_바깥이_아니다():
    """여는 자리인지와 「바깥 클릭인지」 는 다른 물음이다. 안 여는
    자리(상태 칸)를 눌렀다고 열려 있던 패널이 닫히면, 아무 일도 안
    하려던 손이 보던 것을 잃는다 — 점검에서 실제로 그렇게 걸렸다.

    **낱말만 잰다** — 두 판정이 한 몸인지는 코드 모양의 문제라 여기서
    보고, 실제로 안 닫히는지는 `docs/checks/drawer.js` 의 목록 항목이
    브라우저에서 잰다(그때 이 고장이 잡혔다).
    """
    js = (JS / "tasks.js").read_text(encoding="utf-8")
    코드 = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    코드 = re.sub(r"//[^\n]*", "", 코드)
    m = re.search(r"isTaskClick:\s*(.+)", 코드)
    assert m and "여는자리" not in m.group(1), "여는 자리와 바깥 판정이 한 몸이다"
    assert ".trow.lrow" in m.group(1)


def test13_r02_점검_스크립트가_행_전체를_여는_자리로_본다():
    """drawer.js 목록 점검이 이름이 아니라 행을 연다 (3-d)."""
    chk = (ROOT / "docs" / "checks" / "drawer.js").read_text(encoding="utf-8")
    assert "'.trow.lrow .nm'" not in chk          # 옛 여는 자리
    assert "행의 빈 곳(메타)을 눌러도 열림" in chk
    # 상태 칸은 안 여는 자리이고 그 자리에서 메뉴가 뜬다 (4-14 · 14판)
    assert "를 눌러도 그 행이 안 열림" in chk
    assert "메뉴가 권한과 어긋남" in chk


# ════════════════════════════════════════════════════════════════════
# 4. 두 번 만들기 막기 (AC-a)
# ════════════════════════════════════════════════════════════════════


def test13_d01_두_번_불러도_업무는_하나다(admin_client):
    """화면은 단추를 감추지만 새로 고치면 되살아난다 — **서버가 막는다.**"""
    _세팅(admin_client)
    meeting, _, _ = _회의와_항목(admin_client, None)
    몸 = {"title": "영상 콘티 확정", "department": None, "parent_run_id": None}
    첫 = admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new", json=몸)
    둘 = admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new", json=몸)
    assert 첫.status_code == 둘.status_code == 200
    assert 첫.json()["already"] is False and 둘.json()["already"] is True
    assert 첫.json()["run_id"] == 둘.json()["run_id"]      # 그 업무를 가리킨다
    with app_session() as db:
        runs = db.scalars(
            select(models.TaskRun).join(models.TaskLibrary)
            .where(models.TaskLibrary.title == "영상 콘티 확정")).all()
    assert len(runs) == 1


def test13_d02_새로_고쳐도_단추가_안_뜬다(admin_client):
    """제안 목록이 그 제안에 만든 업무를 실어 보낸다 — 화면은 단추 대신
    링크를 그린다. **저장하지 않고 (출처, 제목)으로 센다**: 본문이 바뀌면
    suggest_json 이 새로 쓰이므로 거기 적어 두면 사라진다."""
    import json

    from app.routers.meetings import body_hash

    _세팅(admin_client)
    meeting, _, _ = _회의와_항목(admin_client, None)
    with app_session() as db:
        m = db.get(models.Meeting, meeting.id)
        m.suggest_state = "됨"
        m.suggest_note = "문장|읽었습니다"
        # 지문을 맞춰 둔다 — 안 맞으면 「본문이 바뀐 것」 으로 읽혀 다시
        # 걸리고, 그때 목록이 비는 것은 이 시험이 재려는 것이 아니다
        m.suggest_hash = body_hash(m)
        m.suggest_json = json.dumps([{
            "kind": "new", "text": "새 업무로 만듭니다 — 영상 콘티 확정",
            "why": "회의에 할 일로 나왔습니다", "title": "영상 콘티 확정",
        }], ensure_ascii=False)
        db.commit()

    첫목록 = admin_client.get(f"/meetings/{meeting.id}/suggestions").json()
    assert 첫목록["items"][0]["made_run_id"] is None       # 아직 안 만들었다

    admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new",
                      json={"title": "영상 콘티 확정"})
    다시 = admin_client.get(f"/meetings/{meeting.id}/suggestions").json()
    run = _run_of("영상 콘티 확정")
    assert 다시["items"][0]["made_run_id"] == run.id       # 단추 대신 링크
    assert 다시["items"][0]["made_run_no"] == run.run_no


def test13_d03_링크가_그_업무로_간다():
    """만들었는데 어디 있는지 모르면 만들지 않은 것과 같다 — 화면이
    /tasks?task= 로 잇는다 (4-14)."""
    js = (JS / "meeting.js").read_text(encoding="utf-8")
    assert "made_run_id" in js
    assert "이미 만들었습니다" in js
    assert "/tasks?task=" in js


# ════════════════════════════════════════════════════════════════════
# 5. 부서 없는 업무의 문을 하나로 (AC-d)
# ════════════════════════════════════════════════════════════════════


def _리더(name, phone, dept_id):
    from fastapi.testclient import TestClient

    from app.main import app

    make_user(name, phone, "dept_lead", dept_id)
    c = TestClient(app)
    login_as(c, "".join(ch for ch in phone if ch.isdigit()), name=name)
    return c


def test13_g01_비관리자가_보드에서_부서_없이_만들_수_있다(admin_client):
    """부서 없는 업무는 아직 누구 일인지 안 정해진 것이다 — 그것을 만드는
    데 관리자를 요구하면 「나중에 정하자」 를 적을 수 없다."""
    _, depts = _세팅(admin_client)
    리더 = _리더("홍보 리더", "010-7777-0201", depts[0].id)
    r = 리더.post("/board/add/new", json={
        "title": "누가 할지 아직", "department_key": None,
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})
    assert r.status_code == 200
    assert _run_of("누가 할지 아직").department_id is None


def test13_g02_다른_부서_키로는_여전히_막힌다(admin_client):
    """부서가 적혀 있을 때만 키를 본다 — 넓힌 것은 「부서 없음」 하나다."""
    _, depts = _세팅(admin_client)
    리더 = _리더("홍보 리더", "010-7777-0202", depts[0].id)
    r = 리더.post("/board/add/new", json={
        "title": "남의 부서 것", "department_key": "chanyang",
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})
    assert r.status_code == 403
    with app_session() as db:
        assert db.scalars(
            select(models.TaskLibrary)
            .where(models.TaskLibrary.title == "남의 부서 것")).first() is None


def test13_g03_세_길이_같은_판정이다(admin_client):
    """보드 · 항목 전환 · 제안 반영 — 같은 입력(부서 없음, 편집자)에 셋 다
    만들어진다. 길마다 다르면 「이 화면에서는 되는데 저기서는 안 된다」 가
    된다."""
    _, depts = _세팅(admin_client)
    리더 = _리더("찬양 리더", "010-7777-0203", depts[1].id)
    meeting, item, _ = _회의와_항목(리더, None, content="부서 미정 항목")

    보드 = 리더.post("/board/add/new", json={
        "title": "보드 부서없음", "department_key": None,
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})
    전환 = 리더.post(f"/meetings/items/{item.id}/to-task", follow_redirects=False)
    제안 = 리더.post(f"/meetings/{meeting.id}/suggestions/apply-new",
                  json={"title": "제안 부서없음"})

    assert 보드.status_code == 200 and 전환.status_code == 303 and 제안.status_code == 200
    with app_session() as db:
        for 제목 in ("보드 부서없음", "부서 미정 항목", "제안 부서없음"):
            run = db.scalars(
                select(models.TaskRun).join(models.TaskLibrary)
                .where(models.TaskLibrary.title == 제목)).one()
            assert run.department_id is None


# ════════════════════════════════════════════════════════════════════
# 6. 파싱 한 곳으로 (AC-b)
# ════════════════════════════════════════════════════════════════════


def test13_n01_쪽지를_읽는_규칙이_하나다():
    """세 자리(제안 화면 · 논의 반영 · 새 업무 반영)가 같은 함수를 부른다."""
    src = (ROOT / "app" / "routers" / "meetings.py").read_text(encoding="utf-8")
    코드 = re.sub(r'""".*?"""', "", src, flags=re.S)
    코드 = re.sub(r"#[^\n]*", "", 코드)
    assert 'partition("|")' not in 코드, "쪽지를 라우터에서 직접 쪼갠다"
    assert 코드.count("쪽지읽기(") >= 3


def test13_n02_구분자가_없으면_방식을_모르는_것이다():
    """옛 쪽지·오류 문구는 `방식|말` 이 아니다. 앞부분을 방식으로 읽으면
    화면이 「분석하지 못했습니다… 로 골랐습니다」 라고 말하게 된다."""
    assert suggest_mod.쪽지읽기("문장|읽었습니다") == ("문장", "읽었습니다")
    assert suggest_mod.쪽지읽기("분석하지 못했습니다 — Timeout") == (
        "", "분석하지 못했습니다 — Timeout")
    assert suggest_mod.쪽지읽기(None) == ("", "")
    assert suggest_mod.낱말로_물러섰나("낱말|아직") is True
    assert suggest_mod.낱말로_물러섰나("문장|읽었습니다") is False


def test13_n03_형식을_바꾸면_세_자리가_따라온다(admin_client, monkeypatch):
    """읽는 규칙을 한 곳에서 바꾸면(여기서는 감싸서 표식을 심는다) 세
    자리가 전부 따라온다 — s02 와 같은 증명이다."""
    _, depts = _세팅(admin_client)
    meeting, _, _ = _회의와_항목(admin_client, None)
    with app_session() as db:
        m = db.get(models.Meeting, meeting.id)
        m.suggest_state = "됨"
        m.suggest_note = "문장|읽었습니다"
        m.suggest_json = "[]"
        db.commit()
    admin_client.post("/board/add/new", json={
        "title": "논의 걸 업무", "department_key": "hongbo",
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})
    run = _run_of("논의 걸 업무")

    monkeypatch.setattr(suggest_mod, "쪽지읽기", lambda note: ("한곳표식", "말표식"))

    # ① 제안 화면
    본 = admin_client.get(f"/meetings/{meeting.id}/suggestions").json()
    assert 본["how"] == "한곳표식" and 본["note"] == "말표식"
    # ② 논의 반영 ③ 새 업무 반영 — 활동기록에 그 방식이 남는다
    admin_client.post(f"/meetings/{meeting.id}/suggestions/apply",
                      json={"run_ids": [run.id]})
    admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new",
                      json={"title": "표식 업무"})
    with app_session() as db:
        말들 = [a.summary for a in db.scalars(
            select(models.ActivityLog).where(
                models.ActivityLog.action.in_(
                    ("회의록_제안_반영", "회의록_새업무_반영"))))]
    assert len(말들) == 2 and all("한곳표식" in s for s in 말들)


# ════════════════════════════════════════════════════════════════════
# 7-a. 개수를 문서·주석에 박지 않는다 (AC-c)
# ════════════════════════════════════════════════════════════════════


def test13_c01_만들기와_파싱_자리를_세어_두지_않는다():
    """「셋」 처럼 세어 둔 말은 넷이 되는 날 숫자만 낡는다 (10장).

    **낱말 둘만 보지 않는다** — 처음에 `"만들기 셋"`·`"남긴 셋"` 만
    보다가 「셋 다」·「세 곳」 을 놓쳤다(검토가 잡았다). 세는 말
    자체를 목록으로 두고, 그 말이 **이 판이 한 곳으로 모은 것들**
    가까이에 나오면 걸린다.
    """
    센말 = ["셋", "세 곳", "세 자리", "세 벌", "네 곳", "넷"]
    주제 = ["create_run", "라이브러리+run", "만드는 곳", "쪽지", "파싱", "쪼갰"]
    나쁜곳 = []
    for 이름, 글 in [
        ("domain/tasks.py", (ROOT / "app" / "domain" / "tasks.py").read_text(encoding="utf-8")),
        ("domain/suggest.py", (ROOT / "app" / "domain" / "suggest.py").read_text(encoding="utf-8")),
        ("CLAUDE.md", (ROOT / "CLAUDE.md").read_text(encoding="utf-8")),
    ]:
        for 번호, 줄 in enumerate(글.split("\n"), 1):
            if any(w in 줄 for w in 센말) and any(t in 줄 for t in 주제):
                나쁜곳.append(f"{이름}:{번호} {줄.strip()[:60]}")
    assert 나쁜곳 == [], f"자리를 세어 둔 곳: {나쁜곳}"


def test13_c02_세는_말을_심으면_걸린다():
    """③ 검사가 볼 것을 실제로 보나 (11-3). 위 시험이 0을 세고 초록을
    내는 것이 아님을 잰다."""
    센말 = ["셋", "세 곳", "세 자리", "세 벌", "네 곳", "넷"]
    주제 = ["create_run", "라이브러리+run", "만드는 곳", "쪽지", "파싱", "쪼갰"]
    걸릴줄 = "전에는 쪽지를 쪼갰던 곳이 세 곳이었다"
    assert any(w in 걸릴줄 for w in 센말) and any(t in 걸릴줄 for t in 주제)
    안걸릴줄 = "만드는 곳은 create_run 하나다"
    assert not (any(w in 안걸릴줄 for w in 센말) and any(t in 안걸릴줄 for t in 주제))
