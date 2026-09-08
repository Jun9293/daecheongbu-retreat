"""옛말 검사를 검사답게 (+ 배지 · 크기 · 이미지 규칙).

지난 판의 A-18 grep 이 낱말 하나로 찾아 넷을 놓쳤고 보고에는 「0곳」 이
적혔다 — **검사를 했다는 기록이 있는데 검사가 못 본 것이라 안 한 것보다
나쁘다.** 사람이 낱말을 고르는 자리를 없앤다.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import re
import subprocess

from sqlalchemy import select

from app import models
from tests.conftest import app_session, login_as, make_user
from tests.test_stage12 import _세팅, _회의와_항목, _run_of

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = dt.date.today()
D = TODAY + dt.timedelta(days=14)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ════════════════════════════════════════════════════════════════════
# 1. 옛말 검사 — 표기를 여럿 적어 두고 그 전부를 찾는다
# ════════════════════════════════════════════════════════════════════


def test14_s01_옛_표기를_심으면_걸린다(tmp_path):
    """막는 쪽. 지금 저장소에서 0곳인 것과 별개로, **찾는 능력**이 있는지
    합성 파일로 잰다.

    **하나만 보지 않는다** — 첫 표기만 재면 그 하나가 우연히 맞는 동안
    나머지가 다 틀려도 초록이다. 낡은 말마다 하나씩, 전부 잰다.
    """
    stale = _load("check_stale")
    쌍 = stale.읽는다()
    assert 쌍, "옛말 목록이 비었다"
    말별첫표기 = {}
    for 지금말, 표기 in 쌍:
        말별첫표기.setdefault(지금말, 표기)
    assert len(말별첫표기) >= 5, f"낡은 말이 {len(말별첫표기)}가지뿐이다"
    못찾은것 = []
    for 지금말, 표기 in 말별첫표기.items():
        p = tmp_path / "옛글.md"
        p.write_text(f"목록은 {표기} 그렇게 동작합니다", encoding="utf-8")
        걸린것 = stale.찾는다(쌍, [p])
        if not (걸린것 and any(x[3] == 표기 for x in 걸린것)):
            못찾은것.append(지금말)
    assert 못찾은것 == [], f"심어도 못 찾는 말: {못찾은것}"


def test14_s01b_적는_법_예시를_진짜로_읽지_않는다():
    """**도구가 자기 안내문을 데이터로 읽으면** 「막는 쪽」 시험이
    자리표시자(`표기1`)로 통과하고, 보고에 적는 수도 부풀려진다 —
    10장의 「금지하는 것을 설명하려고 스스로 담는다」 가 파일 안 구획에서
    다시 나온 자리다 (검토가 잡았다). 항목은 `---` 아래뿐이다."""
    stale = _load("check_stale")
    표기 = [t for _, t in stale.읽는다()]
    for 자리표시자 in ("표기1", "표기2", "표기3", "<지금 말>", "<YYYY-MM-DD>"):
        assert 자리표시자 not in 표기, f"안내문의 {자리표시자} 를 표기로 읽는다"
    지금말 = {a for a, _ in stale.읽는다()}
    assert "적는 법" not in 지금말 and "무엇을 적는가 — **낱말이 아니라 「낡은 주장」**" not in 지금말


def test14_s02_지금_말은_안_걸린다(tmp_path):
    """뚫리는 쪽. 지금 규칙을 그대로 적은 글이 걸리면 아무도 안 쓴다."""
    stale = _load("check_stale")
    쌍 = stale.읽는다()
    p = tmp_path / "지금글.md"
    p.write_text(
        "행 아무 데나 누르면 그 자리에서 펼쳐집니다. 예외는 「안 여는 자리」\n"
        "목록뿐이고 상태 칸에서는 상태 메뉴가 뜹니다. 주소는 ?task= 입니다.\n"
        "총무팀 일정 화면은 domain/live.SCREEN_TITLE 한 곳에서 이름이 나갑니다.\n",
        encoding="utf-8")
    assert stale.찾는다(쌍, [p]) == []


def test14_s03_옛말_목록이_비면_실패한다(tmp_path, monkeypatch):
    """**아무것도 안 보는 검사는 통과가 아니다** (11-3). check_names 가
    「29개 중 0개를 보며 초록」 을 냈던 그 모양을 되풀이하지 않는다."""
    stale = _load("check_stale")
    빈것 = tmp_path / "옛말.md"
    빈것.write_text("# 옛말\n\n적어 둔 것이 없다\n", encoding="utf-8")
    monkeypatch.setattr(stale, "옛말목록", 빈것)
    monkeypatch.setattr("sys.argv", ["check_stale.py"])
    assert stale.main() == 2


def test14_s04_지난_판이_놓친_넷을_이_도구가_찾는다(tmp_path):
    """1-e — 그때 그 네 줄을 그대로 심어 본다. 사람이 고른 낱말
    (「업무 이름을 누르면」)로는 하나도 안 걸렸던 것들이다."""
    stale = _load("check_stale")
    쌍 = stale.읽는다()
    놓쳤던넷 = {
        "css": "**이름을 누르면 펼쳐진다** — 버튼 줄은 없앴다",
        "drawer": "// 목록이 이름 클릭으로 열며 업무 규칙 탭을 고를 때 쓴다 (4-14)",
        "checks": "// 목록 — 여는 자리(이름·캐럿)도 패널도 아닌 곳이다.",
        "test": "def test7_l01_이름을_눌러_펼친다_버튼_줄은_없다():",
    }
    못찾은것 = []
    for 이름, 줄 in 놓쳤던넷.items():
        p = tmp_path / f"{이름}.md"
        p.write_text(줄, encoding="utf-8")
        if not stale.찾는다(쌍, [p]):
            못찾은것.append(이름)
    assert 못찾은것 == [], f"이 도구도 못 찾는 것: {못찾은것}"


def test14_s05_지금_저장소에는_0곳이다():
    """돌려서 0 인지 — 소스를 읽지 않고 **실제로 실행**한다."""
    r = subprocess.run(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"),
         str(ROOT / "scripts" / "check_stale.py")],
        cwd=ROOT, capture_output=True)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-1500:]


# ════════════════════════════════════════════════════════════════════
# 2. 글자를 찾는 시험 — 남는 것은 왜 남는지 적는다
# ════════════════════════════════════════════════════════════════════


def 배선낱말시험() -> list[tuple[str, str, str]]:
    """JS 의 **여는/거는 배선**(선택자·이벤트)을 낱말로 재는 시험 전부.

    화면·API 를 실제로 부르는 것은 뺀다 — 그건 동작을 잰다. 남는 것이
    「그 낱말이 있으니 그렇게 동작할 것이다」 라고 믿는 시험이고,
    10장이 **다섯 번 당했다**고 적어 둔 자리다.
    """
    import ast

    배선 = re.compile(r"""["'](\.[\w.-]+|\#[\w-]+|addEventListener|click|"""
                     r"""pointerdown|closest\()["']""")
    나온것 = []
    for p in sorted((ROOT / "tests").glob("test_*.py")):
        src = p.read_text(encoding="utf-8")
        for fn in [n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.FunctionDef) and n.name.startswith("test")]:
            seg = ast.get_source_segment(src, fn) or ""
            if "read_text" not in seg or ".js" not in seg:
                continue
            if any(w in seg for w in ("client.", "app_session", "TestClient")):
                continue
            if 배선.search(seg):
                나온것.append((p.name, fn.name, seg))
    return 나온것


def test14_t01_낱말만_재는_시험은_왜_남는지_적혀_있다():
    """**아는 채로 두는 것과 모르는 것은 다르다** (지시문 2-b).

    동작으로 바꿀 수 없는 것(브라우저에서만 일어나는 일)은 남지만, 그
    시험을 읽는 사람이 「이건 동작을 안 잰다」 를 알아야 한다 — 그래야
    초록을 보고 안심하지 않는다.
    """
    안적힌것 = [f"{f}::{n}" for f, n, seg in 배선낱말시험()
              if "낱말만 잰다" not in seg]
    assert 안적힌것 == [], (
        "낱말만 재는 시험에 그 사실이 안 적혀 있다 — 독스트링에 "
        "「**낱말만 잰다** — 동작은 …가 잰다」 를 적으세요: " + str(안적힌것))


def test14_t02_그_표시를_찾는_눈이_실제로_있다():
    """③ 검사가 볼 것을 보고 있나 (11-3) — 센 것이 0이면 성공이 아니다."""
    목록 = 배선낱말시험()
    assert len(목록) >= 3, f"낱말 시험을 {len(목록)}개만 봤다 — 찾는 눈이 좁다"


# ════════════════════════════════════════════════════════════════════
# 4. 목록 배지에 상태 메뉴 — 드로어의 것을 그대로
# ════════════════════════════════════════════════════════════════════


def _리더(name, phone, dept_id):
    from fastapi.testclient import TestClient

    from app.main import app

    make_user(name, phone, "dept_lead", dept_id)
    c = TestClient(app)
    login_as(c, "".join(ch for ch in phone if ch.isdigit()), name=name)
    return c


def test14_b01_배지에서_바꾸면_목록_보드_드로어가_같은_배지다(admin_client):
    """같은 계산(board.paint_of)에서 나와야 한다 — 화면이 저마다 세면
    두 벌이 되고 갈린 쪽을 아무도 눈치채지 못한다 (4-3)."""
    _세팅(admin_client)
    admin_client.post("/board/add/new", json={
        "title": "배지로 바꿔 볼 업무", "department_key": "hongbo",
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})
    run = _run_of("배지로 바꿔 볼 업무")

    res = admin_client.post(f"/board/task/{run.id}/status", json={"status": "진행중"})
    assert res.status_code == 200
    배지 = res.json()["badge"]

    목록 = admin_client.get("/tasks").text
    assert f'<span class="stbadge {배지["cls"]}">{배지["label"]}</span>' in 목록
    보드 = admin_client.get(f"/board/task/{run.id}").json()
    assert 보드["badge"] == 배지


def test14_b02_상태_칸은_행을_열지_않는다():
    """막는 쪽. 상태 칸은 「안 여는 자리」 이고, 대신 그 자리에서 메뉴가
    뜬다 — 두 손이 한 자리에서 부딪히지 않는다.

    **낱말만 잰다** — 실제로 눌러 보는 것은 `docs/checks/drawer.js` 의
    목록 항목이다(그쪽이 브라우저에서 돈다)."""
    js = (ROOT / "app" / "static" / "js" / "tasks.js").read_text(encoding="utf-8")
    코드 = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    코드 = re.sub(r"//[^\n]*", "", 코드)
    assert "'.cell.st" in 코드 or '".cell.st' in 코드      # 안 여는 자리에 든다
    assert "Drawer.statusMenu(" in 코드                    # 그 자리에서 메뉴
    assert "statMenu" not in 코드, "목록이 제 메뉴를 만든다"


def test14_b03_메뉴는_드로어의_것_하나다():
    """새 메뉴를 만들지 않는다 — 고를 수 있는 상태와 색·라벨이 두 벌이
    되면 갈린 쪽을 아무도 눈치채지 못한다.

    **낱말만 잰다** — 「메뉴가 하나인가」 는 코드 모양의 물음이다. 실제로
    떠서 고를 수 있는지는 `docs/checks/drawer.js` 의 목록 항목이 잰다.
    """
    drawer = (ROOT / "app" / "static" / "js" / "drawer.js").read_text(encoding="utf-8")
    tasks = (ROOT / "app" / "static" / "js" / "tasks.js").read_text(encoding="utf-8")
    assert "statusMenu:" in drawer                          # 내보내는 창구
    assert "PICKABLE" not in tasks and "statmenu" not in tasks
    # 바깥 클릭 판정이 이 자리를 안다 — 모르면 메뉴가 뜨자마자 닫힌다
    assert "at('.cell.st.pick')" in drawer


def test14_b04_권한이_없으면_메뉴가_안_뜬다(admin_client):
    """다른 부서 사람에게는 `pick` 이 안 붙는다 — 커서도 호버도 없다.
    **보드가 쓰는 그 문**이라 여기서 다른 규칙을 쓰지 않는다 (2장)."""
    _, depts = _세팅(admin_client)
    admin_client.post("/board/add/new", json={
        "title": "홍보팀 업무", "department_key": "hongbo",
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})
    남 = _리더("찬양 리더", "010-8888-0001", depts[1].id)
    내 = _리더("홍보 리더", "010-8888-0002", depts[0].id)

    with app_session() as db:
        run = db.scalars(select(models.TaskRun).join(models.TaskLibrary)
                         .where(models.TaskLibrary.title == "홍보팀 업무")).one()
    남목록 = 남.get("/tasks").text
    내목록 = 내.get("/tasks").text
    자리 = 남목록.index("홍보팀 업무")
    assert "cell st pick" not in 남목록[자리:자리 + 400]
    자리2 = 내목록.index("홍보팀 업무")
    assert "cell st pick" in 내목록[자리2:자리2 + 400]
    # 서버도 같은 답이다 — 화면만 감추면 눌러서 바꿀 수 있다
    assert 남.post(f"/board/task/{run.id}/status",
                  json={"status": "완료"}).status_code == 403


def test14_b05_칸의_패딩도_같은_자리다():
    """배지 바깥 몇 px 에서 열림과 메뉴가 갈리면 같은 곳을 눌렀는데 다른
    일이 일어난다 — 여는 자리도 메뉴도 **칸(`.cell.st`)** 을 본다.

    **낱말만 잰다** — 몇 px 바깥을 실제로 눌러 보는 것은 브라우저의 일이라
    `docs/checks/drawer.js` 가 칸의 가장자리를 눌러 잰다.
    """
    js = (ROOT / "app" / "static" / "js" / "tasks.js").read_text(encoding="utf-8")
    코드 = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    코드 = re.sub(r"//[^\n]*", "", 코드)
    assert ".stbadge" not in 코드.split("const 안여는곳")[1].split("\n")[0]
    assert "closest('.cell.st.pick')" in 코드


# ════════════════════════════════════════════════════════════════════
# 6. made_from_meeting 좁히기 (AD-d)
# ════════════════════════════════════════════════════════════════════


def test14_m01_뺀_업무와_제목이_같으면_단추가_다시_뜬다(admin_client):
    """`included=false` 는 목록에 없다 (4-14) — 가리키면 눌러도 갈 곳이
    없다. 그러면 「이미 만들었습니다」 가 거짓말이 된다."""
    _세팅(admin_client)
    meeting, _, _ = _회의와_항목(admin_client, None)
    admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new",
                      json={"title": "빼 둘 업무"})
    run = _run_of("빼 둘 업무")
    with app_session() as db:
        db.get(models.TaskRun, run.id).included = False
        db.commit()

    from app.domain import tasks as tasks_domain

    with app_session() as db:
        retreat = db.scalars(select(models.Retreat)).first()
        만든것 = tasks_domain.made_from_meeting(db, retreat, meeting.id)
    assert "빼 둘 업무" not in 만든것

    # 그래서 다시 만들 수 있다 — 새 run 이 선다
    res = admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new",
                            json={"title": "빼 둘 업무"})
    assert res.status_code == 200 and res.json()["already"] is False
    assert res.json()["run_id"] != run.id


def test14_m02_항목_전환으로_만든_것도_센다(admin_client):
    """같은 회의록·같은 제목이면 같은 업무다 — 제안을 눌러 하나 더
    만들면 목록에 같은 이름이 둘 선다."""
    _, depts = _세팅(admin_client)
    meeting, item, _ = _회의와_항목(admin_client, None, content="전환으로 만든 업무")
    admin_client.post(f"/meetings/items/{item.id}/to-task", follow_redirects=True)
    run = _run_of("전환으로 만든 업무")

    res = admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new",
                            json={"title": "전환으로 만든 업무"})
    assert res.status_code == 200
    assert res.json()["already"] is True and res.json()["run_id"] == run.id


def test14_m03_이미_판정은_부서_문_뒤다():
    """AD-c 확인 — 앞에 두면 같은 요청이 만들기 전엔 403, 만든 뒤엔 200 이
    되어 판정이 시점에 따라 갈린다. (지난 판에 옮겼고 여기서 지킨다.)"""
    src = (ROOT / "app" / "routers" / "meetings.py").read_text(encoding="utf-8")
    본문 = src[src.index("def apply_new_task("):]
    본문 = 본문[: 본문.index("\n@router")] if "\n@router" in 본문 else 본문
    assert 본문.index("assert_can_edit_department(") < 본문.index("made_from_meeting(")


# ════════════════════════════════════════════════════════════════════
# 5. 이미지에도 본문 규칙
# ════════════════════════════════════════════════════════════════════


def test14_i01_이미지_확인에_본문_규칙이_있다():
    """11-2 의 「회의록·논의의 줄을 옮겨 적지 않는다」 는 **찍은 화면에도**
    걸린다 — 규칙이 이미지를 비켜 가면 그 길로 그대로 나간다."""
    글 = (ROOT / "docs" / "review" / "이미지-확인.md").read_text(encoding="utf-8")
    assert "회의록" in 글 and "본문" in 글
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    자리 = claude[claude.index("회의록·제안·논의의 줄을"):][:900]
    assert "이미지" in 자리 and "실명만" in 자리
