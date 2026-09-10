"""목록에 적는 것을 잊어도 잡히게 (+ 4-0 · 메뉴 · 되살리기).

지난 판이 옛말 검사를 만들고도 **자기가 바꾼 말을 목록에 안 적어** 못
잡혔다(G-1). 목록에 적는 것을 사람이 잊으면 도구가 없는 것과 같다 —
목록에 기대지 않는 **둘째 축**을 둔다: 문서가 이름한 것이 실재하는가.
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
JS = ROOT / "app" / "static" / "js"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _코드(path: pathlib.Path) -> str:
    """주석을 걷어낸 JS — 글자를 찾는 시험의 그 함정 (10장).

    **`#` 로 시작하는 줄을 지우지 않는다.** 파이썬 주석 규칙을 그대로
    옮기면 `at('#statchip')` 같은 선택자가 통째로 사라져, 있는 것을
    없다고 말한다 — 실제로 한 번 그랬다.
    """
    글 = path.read_text(encoding="utf-8")
    글 = re.sub(r"/\*.*?\*/", "", 글, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", "", 글)


# ════════════════════════════════════════════════════════════════════
# 1. 둘째 축 — 문서가 이름한 것이 실재하는가
# ════════════════════════════════════════════════════════════════════


def test15_n01_문서에만_있는_이름을_심으면_걸린다():
    """막는 쪽. **옛말 목록에 기대지 않는다** — 이름이 바뀌면 적어 두지
    않아도 걸리는 것이 이 축의 값이다.

    심는 이름은 **글자로 적지 않고 이어 붙여 만든다.** 이 파일도 코드라,
    없다고 주장할 이름을 그대로 적으면 그 순간 코드에 있는 이름이 되어
    **스스로를 통과시킨다** — 10장의 「도구는 자기가 금지하는 것을
    설명하려고 담게 된다」 가 시험 안에서 다시 나오는 자리다.
    """
    named = _load("check_named")
    경로, 글, 모양 = named.저장소글()
    없는이름 = "없는" + "이름" + "_zqx"
    없는것 = named.없는것(
        {없는이름: "식별자",
         "app/domain/없는파일.py": "경로",
         ".없는선택자-xyz": "선택자"},
        경로, 글, 모양)
    assert {t for t, _ in 없는것} == {
        없는이름, "app/domain/없는파일.py", ".없는선택자-xyz"}


def test15_n02_실재하는_이름은_안_걸린다():
    """뚫리는 쪽. 지금 있는 것이 걸리면 아무도 안 쓴다."""
    named = _load("check_named")
    경로, 글, 모양 = named.저장소글()
    assert named.없는것(
        {"보조급자리": "식별자", "create_run": "식별자",
         "app/domain/tasks.py": "경로", ".cell.st.pick": "선택자"},
        경로, 글, 모양) == []


def test15_n03_식별자는_코드에서만_찾는다():
    """**문서까지 뒤지면 이 검사가 잡으려던 것을 못 잡는다** — 다른 문서가
    그 이름을 한 번 적어 둔 것만으로 「있다」 가 된다. 실제로 지워진
    이름 하나가 **옛말 목록에 적혀 있다는 이유로** 통과했다.

    이름 하나를 심어 재지 않는다 — 심은 이름은 이 시험 자신이 담게 되어
    (이 파일도 코드다) 무엇을 재는지 흐려진다. **닿는 파일의 확장자**를
    직접 본다.
    """
    named = _load("check_named")
    경로, _글, _모양 = named.저장소글()
    본것 = {p.suffix.lower() for p in named.코드파일(경로)}
    assert 본것 <= named.코드꼴, f"코드 아닌 것을 본다: {본것 - named.코드꼴}"
    assert ".md" not in 본것 and ".txt" not in 본것
    # 그리고 실제로 문서를 하나라도 빼고 있다 — 0개를 빼면 뺐다는 말이 뜻이 없다
    assert any(x.endswith(".md") for x in 경로)


def test15_n04_지금은_0곳이다():
    """소스를 읽지 않고 **실제로 돌린다.**"""
    r = subprocess.run(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"),
         str(ROOT / "scripts" / "check_named.py")],
        cwd=ROOT, capture_output=True)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-1500:]


def test15_n06_알려진_이름이_알려진_축으로_모인다():
    """③ 검사가 볼 것을 보고 있나 (11-3) — **수집 단계**를 잰다.

    n01·n02 는 `없는것()` 에 dict 를 손으로 넣으므로 정규식이 상해도
    초록이다(검토가 짚음). 개수 문턱(0개)만으로는 363이 3이 되어도
    지나간다 — `test14_t02` 가 `>= 3` 을 버린 그 이유가 여기 그대로
    남아 있었다. 그래서 **문서가 실제로 이름한 것을 축까지 견준다.**
    """
    named = _load("check_named")
    이름 = named.이름들()
    바라는것 = {
        "app/domain/tasks.py": "경로",
        "partials/drawer.html": "경로",      # 앞을 줄여 적은 자리
        "create_run": "식별자",
        "보조급자리": "식별자",              # 한 낱말 한글도 본다
        "originOf": "식별자",                # 캠멜이라고 버리지 않는다
        ".cell.st.pick": "선택자",
        "--fz": "토큰",
    }
    틀린것 = {t: (이름.get(t), 축) for t, 축 in 바라는것.items() if 이름.get(t) != 축}
    assert 틀린것 == {}, f"수집이 샜다 (지금 축, 바라는 축): {틀린것}"


def test15_n05_아무것도_안_보면_실패한다(tmp_path, monkeypatch):
    """센 것이 0이면 성공이 아니라 실패다 (11-3)."""
    named = _load("check_named")
    빈것 = tmp_path / "CLAUDE.md"
    빈것.write_text("# 아무 이름도 없는 문서\n\n산문뿐입니다.\n", encoding="utf-8")
    monkeypatch.setattr(named, "문서", 빈것)
    monkeypatch.setattr("sys.argv", ["check_named.py"])
    assert named.main() == 2


# ════════════════════════════════════════════════════════════════════
# 2·3. 4-0 이 정본 · 상태 메뉴 마무리
# ════════════════════════════════════════════════════════════════════


def test15_d01_4_0_이_하한_셋을_말한다():
    """4-0 은 눈금의 정본이다 — 4-14·CSS·시험과 다른 말을 하면 안 된다.

    없어진 이름은 **이어 붙여** 만든다. 글자로 적으면 옛말 검사가 이
    파일을 붙잡는다 — 그 이름을 옛말 목록에 적어 두었기 때문이다.
    """
    글 = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    자리 = 글[글.index("**하한이"):][:1200]
    assert "하한이 셋" in 자리
    assert "보조는 13px" in 자리 and "장식은 **12px**" in 자리
    assert "보조급자리" in 자리
    assert ("장식이어도" + "_되는곳") not in 자리


def test15_m01_드로어_칩도_목록과_같은_길이다():
    """같은 메뉴를 여는 두 자리의 규약이 갈린 채로 두지 않는다 (W-4).
    전파를 막으면 「여기가 바깥인가」 를 아는 곳이 둘이 된다.

    **낱말만 잰다** — 실제로 안 닫히는지는 `docs/checks/drawer.js` 가
    브라우저에서 잰다."""
    코드 = _코드(JS / "drawer.js")
    칩줄 = [줄 for 줄 in 코드.split("\n") if "statchip').onclick" in 줄]
    assert 칩줄 and "stopPropagation" not in 칩줄[0]
    assert "at('.cell.st.pick')" in 코드          # originOf 가 안다


def test15_m02_메뉴가_화면_안에_묶인다():
    """가로·세로 둘 다. 한쪽만 잡으면 나머지로 넘친다 (W-2).
    어림값이 아니라 **실제 크기**로 잰다."""
    코드 = _코드(JS / "drawer.js")
    # 자리 잡는 곳은 `메뉴를띄운다` 하나다 — 상태 메뉴와 담당자 메뉴(4-14)가
    # 그것을 같이 쓴다. 두 벌로 두면 한쪽만 화면 안에 묶인다
    자리 = 코드[코드.index("function 메뉴를띄운다"):][:1400]
    assert "offsetWidth" in 자리 and "offsetHeight" in 자리
    assert "innerWidth" in 자리 and "innerHeight" in 자리
    # **띄운 뒤에 잰다** — 숨은 채로 재면 0 이 나와 어림값으로 떨어지고,
    # 그러면 실제 크기로 잰다는 말이 뜻을 잃는다
    assert 자리.index("classList.add('on')") < 자리.index("offsetWidth")
    assert "Math.min" in 자리 and "Math.max" in 자리


def test15_m03_스크롤하면_닫는다():
    """`position:fixed` 라 메뉴만 화면에 남으면 안 보이는 행의 상태를
    바꾸게 된다 (W-3).

    **낱말만 잰다** — 실제로 스크롤해서 닫히는지는 브라우저의 일이라
    돌고 있는 서버에서 손으로 쟀다(최근.md 3장의 표)."""
    코드 = _코드(JS / "drawer.js")
    assert "addEventListener('scroll'" in 코드
    assert "addEventListener('resize'" in 코드


def test15_m04_못_바꾸는_사람에게는_그_칸도_행을_연다(admin_client):
    """예외는 「누르면 뭔가 되는 것」 이지 「누를 수 없는 사람에게도
    예외」 가 아니다 — `pick` 이 없으면 그 칸은 행의 다른 곳과 같다."""
    _, depts = _세팅(admin_client)
    admin_client.post("/board/add/new", json={
        "title": "남의 부서 업무", "department_key": "hongbo",
        "kind": "main", "start": D.isoformat(), "end": D.isoformat()})
    from fastapi.testclient import TestClient

    from app.main import app

    make_user("찬양 리더", "01099990001", "dept_lead", depts[1].id)
    남 = TestClient(app)
    login_as(남, "01099990001", name="찬양 리더")
    html = 남.get("/tasks?dept=all").text      # 기본은 내 부서 전부다 (④)
    자리 = html.index("남의 부서 업무")
    assert "cell st pick" not in html[자리:자리 + 400]

    # 안 여는 자리는 `.cell.st.pick` 뿐이라, pick 이 없으면 행이 열린다
    코드 = _코드(JS / "tasks.js")
    안여는곳 = [줄 for 줄 in 코드.split("\n") if "안여는곳 =" in 줄][0]
    assert ".cell.st.pick" in 안여는곳
    assert ".cell.st," not in 안여는곳, "바꿀 수 없는 칸까지 예외로 둔다"


# ════════════════════════════════════════════════════════════════════
# 4. 되살리기
# ════════════════════════════════════════════════════════════════════


def _뺀업무를만든다(admin_client, 제목="빼 둘 업무"):
    _세팅(admin_client)
    meeting, _, _ = _회의와_항목(admin_client, None)
    admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new",
                      json={"title": 제목})
    run = _run_of(제목)
    with app_session() as db:
        db.get(models.TaskRun, run.id).included = False
        db.commit()
    return meeting, run


def test15_r01_뺀_업무를_되살리면_목록에_다시_선다(admin_client):
    meeting, run = _뺀업무를만든다(admin_client)
    assert "빼 둘 업무" not in admin_client.get("/tasks").text

    res = admin_client.post(f"/meetings/{meeting.id}/suggestions/restore",
                            json={"run_id": run.id})
    assert res.status_code == 200 and res.json()["run_id"] == run.id
    with app_session() as db:
        assert db.get(models.TaskRun, run.id).included is True
    assert "빼 둘 업무" in admin_client.get("/tasks").text


def test15_r02_뺐다_되살려도_라이브러리가_하나다(admin_client):
    """새로 만들면 같은 제목의 라이브러리가 둘이 되어 6-2 의 실행 이력이
    갈린다 — 그래서 뺀 것도 세고 되살린다 (W-6)."""
    meeting, run = _뺀업무를만든다(admin_client, "이력 갈릴 업무")
    with app_session() as db:
        전 = len(db.scalars(select(models.TaskLibrary)
                           .where(models.TaskLibrary.title == "이력 갈릴 업무")).all())
    # 제안을 다시 눌러도 새로 만들지 않는다 — 뺀 것도 세기 때문
    res = admin_client.post(f"/meetings/{meeting.id}/suggestions/apply-new",
                            json={"title": "이력 갈릴 업무"})
    assert res.json()["already"] is True and res.json()["run_id"] == run.id
    admin_client.post(f"/meetings/{meeting.id}/suggestions/restore",
                      json={"run_id": run.id})
    with app_session() as db:
        후 = db.scalars(select(models.TaskLibrary)
                       .where(models.TaskLibrary.title == "이력 갈릴 업무")).all()
        runs = db.scalars(select(models.TaskRun)
                          .where(models.TaskRun.library_id == 후[0].id)).all()
    assert 전 == len(후) == 1, "같은 제목의 라이브러리가 둘이다"
    assert len(runs) == 1, "실행 이력이 두 줄로 갈렸다"


def test15_r03_화면이_뺀_업무를_그렇게_말한다(admin_client):
    """단추 대신 「빼 둔 업무입니다」 와 되살리기 — 목록에 없는 것을
    「이미 만들었습니다」 로 가리키면 눌러도 갈 곳이 없다."""
    import json

    from app.routers.meetings import body_hash

    meeting, run = _뺀업무를만든다(admin_client, "빼 둔 제안")
    with app_session() as db:
        m = db.get(models.Meeting, meeting.id)
        m.suggest_state = "됨"
        m.suggest_note = "문장|읽었습니다"
        m.suggest_hash = body_hash(m)
        m.suggest_json = json.dumps([{
            "kind": "new", "text": "새 업무로 만듭니다 — 빼 둔 제안",
            "why": "회의에 할 일로 나왔습니다", "title": "빼 둔 제안"}],
            ensure_ascii=False)
        db.commit()
    본 = admin_client.get(f"/meetings/{meeting.id}/suggestions").json()["items"][0]
    assert 본["made_run_id"] == run.id and 본["made_excluded"] is True

    js = _코드(JS / "meeting.js")
    assert "빼 둔 업무입니다" in (JS / "meeting.js").read_text(encoding="utf-8")
    assert "data-restore" in js and "suggestions/restore" in js


# ════════════════════════════════════════════════════════════════════
# 5. 진단 패널 — 다른 업무를 바꿔도 열린 판정을 다시 받는다
# ════════════════════════════════════════════════════════════════════


def test15_g01_다른_업무를_바꿔도_열린_판정을_다시_받는다():
    """A 를 연 채 A 의 선행 B 를 바꾸면 A 의 판정이 흔들린다 (4-10) —
    안 받으면 「진행 불가 — 선행 미완료」 가 그대로 남는다.

    **낱말만 잰다** — 화면이 다시 그리는 것은 브라우저의 일이라
    `docs/checks/drawer.js` 가 잰다."""
    코드 = _코드(JS / "drawer.js")
    자리 = 코드[코드.index("async function setStatus"):][:1200]
    assert "refreshDiag(runId)" in 자리          # 열린 것이 바뀐 것일 때
    assert "refreshDiag(detail.run_id)" in 자리  # 아닐 때도 판정은 받는다
