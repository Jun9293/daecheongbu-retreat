"""내 정보에서 본인이 비밀번호를 바꾸기 · 사역자 계정을 받을 준비 (2026-09-11).

| 잰 것 | 어디 |
|---|---|
| 가·나·다 | `/settings` 의 그 자리 — 바뀌는가 · 막히는가 · 안 보이는가 |
| 라 | 판정이 한 곳인가 — **코드에서 끌어내** 견준다 |
| 마 | 활동 기록에 변경은 남고 값은 안 남는가 |
| 바 | 사역자 열 명을 만드는 길이 끊기지 않는가 |

**합성 자료만 씁니다** — 운영 DB 는 시험이 열지 않습니다. 사람 이름은 가명이고
비밀번호도 지어낸 값입니다.

각 독스트링에 **그 줄이 실제로 무엇을 보는지** 적습니다 — 막혀야 할 것이
막히는가 · 막히면 안 되는 것이 통과하는가 · 검사가 볼 것을 보고 있는가(11-3).
"""

from __future__ import annotations

import ast
import pathlib
import re
import urllib.parse

import pytest
from sqlalchemy import select

from app.domain import login as 로그인
from app.models import ActivityLog, Department, Retreat, User
from tests.conftest import app_session

ROOT = pathlib.Path(__file__).resolve().parent.parent

지어낸값 = "지어낸비밀번호35"
새값 = "새로지어낸값35"


def _나() -> int:
    """지금 들어와 있는 사람(= 처음 만들어진 총무팀 계정)의 id."""
    with app_session() as db:
        return db.scalars(select(User).order_by(User.id)).first().id


def _안내(답) -> str:
    """리다이렉트가 실어 보낸 1회성 안내 — 쿠키에 있지 본문에 있지 않다."""
    return urllib.parse.unquote(답.headers.get("set-cookie", ""))


@pytest.fixture
def 선교사회(admin_client):
    """부서가 선 회차 하나 — 사역자가 붙을 자리."""
    with app_session() as db:
        retreat = Retreat(name="2027 여름수련회")
        db.add(retreat)
        db.flush()
        for i, (key, name) in enumerate(
                [("chongmu", "1 총무팀"), ("seongyo", "3 선교사회")]):
            db.add(Department(retreat_id=retreat.id, key=key, name=name, sort_order=i))
        db.commit()
        return retreat.id


# ── 가) 바꾼 값으로 다시 들어와지고 옛 값은 죽는다 ────────────────────

def test35_a01_내_정보에서_바꾼_값으로_다시_들어와진다(admin_client):
    """가) **둘을 같은 판에서 봅니다.**

    「새 값이 된다」 와 「옛 값이 죽는다」 는 다른 사실입니다. 앞만 보면
    **둘 다 통하는** 상태를 통과시키는데, 그때 옛 값을 아는 사람이 계속
    들어올 수 있고 화면에는 아무 표시도 안 납니다.

    봅니다 — ① 바꾸는 것이 되는가 ② **새 값으로 실제로 들어와지는가**
    ③ **옛 값은 막히는가** ④ 이 기기의 로그인은 그대로인가(바꾸자마자
    쫓겨나면 사람이 무슨 일이 났는지 모릅니다).
    """
    from fastapi.testclient import TestClient

    from app.main import app

    uid = _나()
    with app_session() as db:
        사람 = db.get(User, uid)
        사람.login_id = "nayun"
        로그인.비밀번호를정한다(db, 사람, 지어낸값, 첫판=False)

    답 = admin_client.post("/settings/password",
                          data={"password": 새값, "password2": 새값},
                          follow_redirects=False)
    assert 답.status_code == 303 and 답.headers["location"] == "/settings"
    # ④ 이 기기는 그대로 — 세션 쿠키를 안 건드린다
    assert admin_client.get("/settings", follow_redirects=False).status_code == 200

    새창 = TestClient(app)
    assert 새창.post("/login", data={"login_id": "nayun", "password": 새값},
                    follow_redirects=False).status_code == 303, "② 새 값으로 못 들어온다"
    다른창 = TestClient(app)
    assert 다른창.post("/login", data={"login_id": "nayun", "password": 지어낸값},
                     follow_redirects=False).status_code == 401, "③ 옛 값이 아직 통한다"


def test35_a02_바꾸면_첫_비밀번호_상태가_풀린다(admin_client):
    """가) 곁가지 — 첫 비밀번호로 들어온 사람이 바꾸면 그 표시가 내려갑니다.

    봅니다 — ① 바꾸기 전에는 참인가(그래야 이 줄이 뜻을 가집니다)
    ② 첫 비밀번호 화면에서 바꾼 뒤 거짓인가 ③ **내 정보에서 또 바꿔도
    참으로 되돌아가지 않는가**(`첫판` 기본값이 뒤집히면 바꿀 때마다 잠깁니다).
    """
    uid = _나()
    with app_session() as db:
        로그인.비밀번호를정한다(db, db.get(User, uid), 지어낸값, 첫판=True)
    with app_session() as db:
        assert db.get(User, uid).must_change_password, "① 첫판인데 표시가 없다"

    # 첫 비밀번호인 채로는 다른 화면이 안 열리므로(4-12) 그 화면을 지난다
    admin_client.post("/password", data={"password": 새값, "password2": 새값})
    with app_session() as db:
        assert not db.get(User, uid).must_change_password, "② 바꿨는데 표시가 남았다"

    admin_client.post("/settings/password",
                      data={"password": 지어낸값, "password2": 지어낸값})
    with app_session() as db:
        assert not db.get(User, uid).must_change_password, "③ 내 정보에서 바꿨더니 잠겼다"


# ── 나) 막히는 쪽과 안 막히는 쪽 ──────────────────────────────────────

def test35_b01_짧거나_다른_값은_거절하고_그때_안_바뀐다(admin_client):
    """나) **같은 판에서 넷을 봅니다.**

    봅니다 — ① 두 번 적은 값이 다르면 거절 ② `MIN_LENGTH` 아래면 거절
    ③ 그 둘 다 **비밀번호가 실제로 안 바뀌었는가**(거절해 놓고 바꾸면 더
    나쁩니다) ④ **규칙 안 값은 지나가는가** — 막기만 하면 문이 닫힌 것과
    같습니다.
    """
    uid = _나()
    with app_session() as db:
        로그인.비밀번호를정한다(db, db.get(User, uid), 지어낸값, 첫판=False)
    with app_session() as db:
        앞 = db.get(User, uid).password_hash

    짧은값 = "a" * (로그인.MIN_LENGTH - 1)
    for 값, 둘째 in ((새값, 새값 + "x"), (짧은값, 짧은값)):
        admin_client.post("/settings/password", data={"password": 값, "password2": 둘째})
        with app_session() as db:
            assert db.get(User, uid).password_hash == 앞, f"③ 거절했는데 바뀌었다: {값!r}"

    admin_client.post("/settings/password", data={"password": 새값, "password2": 새값})
    with app_session() as db:
        assert db.get(User, uid).password_hash != 앞, "④ 규칙 안 값이 막혔다"


# ── 다) 비밀번호가 없는 계정에는 안 보인다 ────────────────────────────

def test35_c01_비밀번호가_없으면_그_자리가_안_보이고_서버도_막는다(admin_client):
    """다) **둘을 같은 판에서 봅니다** — 없을 때와 있을 때.

    봅니다 — ① 없으면 화면에 그 자리가 없는가 ② **있으면 보이는가**(안 보면
    「늘 안 보인다」 와 구별되지 않습니다) ③ 화면만 감춘 것이 아니라 **서버도
    막는가** ④ 막으면서 무엇을 해야 하는지 말하는가.
    """
    uid = _나()
    with app_session() as db:
        사람 = db.get(User, uid)
        사람.password_hash = None
        사람.must_change_password = False
        db.commit()

    assert 'action="/settings/password"' not in admin_client.get("/settings").text, \
        "① 바꿀 것이 없는데 자리가 있다"

    답 = admin_client.post("/settings/password",
                          data={"password": 새값, "password2": 새값},
                          follow_redirects=False)
    with app_session() as db:
        assert db.get(User, uid).password_hash is None, "③ 서버가 안 막았다"
    assert "총무팀" in _안내(답), "④ 무엇을 해야 하는지 안 말한다"

    with app_session() as db:
        로그인.비밀번호를정한다(db, db.get(User, uid), 지어낸값, 첫판=False)
    assert 'action="/settings/password"' in admin_client.get("/settings").text, \
        "② 있는데도 자리가 안 보인다"


# ── 라) 판정이 한 곳 ──────────────────────────────────────────────────

def test35_d01_두_화면이_같은_판정을_부른다():
    """라) **코드에서 끌어내 견줍니다** — 손으로 적은 목록과 견주지 않습니다.

    봅니다 — ① 판정 함수가 `domain/login` 에 하나인가 ② **두 라우터가 그것을
    부르는가**(파일을 파서로 읽어 **호출 노드**의 이름만 모읍니다) ③ 그 자리에서
    **직접 다시 가르지 않는가**(길이를 거기서 또 보면 두 벌이 됩니다)
    ④ 읽은 파일이 실제로 무언가를 담고 있었나(빈 집합이면 ② 가 거짓으로 통과).

    낱말로 찾지 않는 까닭은 이 독스트링이 그 이름을 담고 있어서입니다(10장).
    """
    로그인글 = (ROOT / "app/domain/login.py").read_text(encoding="utf-8")
    assert 로그인글.count("\ndef 바꿔도되나(") == 1, "① 판정이 하나가 아니다"

    부른곳 = {}
    for rel in ("app/routers/login.py", "app/routers/settings.py"):
        나무 = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        부른곳[rel] = {
            n.func.attr for n in ast.walk(나무)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
    for rel, 이름들 in 부른곳.items():
        assert 이름들, f"④ {rel} 에서 아무 호출도 못 읽었다"
        assert "바꿔도되나" in 이름들, f"② {rel} 이 판정을 안 부른다"
        assert "비밀번호를정한다" in 이름들, f"② {rel} 이 저장을 안 부른다"
        글 = (ROOT / rel).read_text(encoding="utf-8")
        assert "너무짧나" not in 글, f"③ {rel} 이 판정을 또 한다"


# ── 마) 기록에 변경은 남고 값은 안 남는다 ─────────────────────────────

def test35_e01_기록에_변경은_남고_값은_안_남는다(admin_client):
    """마) **기록을 실제로 읽습니다.**

    봅니다 — ① 바꾼 뒤 그 이름의 기록이 한 줄 느는가 ② 두 화면이 같은
    이름으로 남기는가(둘 다 `바꾼_행위` 로 세므로, 갈리면 ① 이 0 이 됩니다)
    ③ **어느 칸에도 값이 없는가**(요약·전·후를 다 훑습니다).
    """
    uid = _나()
    with app_session() as db:
        로그인.비밀번호를정한다(db, db.get(User, uid), 지어낸값, 첫판=False)

    def 줄들():
        with app_session() as db:
            rows = db.scalars(select(ActivityLog)
                              .where(ActivityLog.action == 로그인.바꾼_행위)).all()
            return [f"{r.summary} {r.before_value} {r.after_value}" for r in rows]

    앞 = len(줄들())
    admin_client.post("/settings/password", data={"password": 새값, "password2": 새값})
    글 = 줄들()
    assert len(글) == 앞 + 1, "① 기록이 안 늘었다"
    합 = "\n".join(글)
    assert 새값 not in 합 and 지어낸값 not in 합, "③ 기록에 값이 남았다"


# ── 바) 사역자 열 명을 만드는 길 ──────────────────────────────────────

가명 = ["정하윤", "최도현", "박서진", "남시우", "노서윤",
       "김태경", "이한결", "오지우", "류가온", "임세라"]


def test35_f01_열_명을_한_화면에서_만들고_아이디와_비밀번호까지_준다(admin_client, 선교사회):
    """바) **실제로 열 명을 만듭니다** — 끊기는 자리가 있으면 그 자리에서 섭니다.

    봅니다 — ① 만들기가 열 번 다 되는가 ② 부서가 **키로** 붙는가(2장)
    ③ 아이디가 그 자리에서 함께 들어가는가 ④ 첫 비밀번호 발급이 열 번 다
    되는가 ⑤ 그 값이 **각자 다른가**(같으면 한 사람 것을 다른 사람이 압니다)
    ⑥ 맨 위의 셈이 남은 사람을 맞게 세는가.

    **가명을 씁니다.** 실제 사역자 이름은 저장소에 안 적습니다.
    """
    from app.domain import permissions as perm

    만든이 = []
    for i, 이름 in enumerate(가명):
        답 = admin_client.post(
            "/admin/users/new",
            data={"name": 이름, "phone_number": f"0106666{i:04d}",
                  "login_id": f"sanyeo{i:02d}", "role": "general",
                  "dept_seongyo": "member"},
            follow_redirects=False)
        assert 답.status_code == 303, f"① {i + 1}번째에서 끊겼다"
        with app_session() as db:
            사람 = db.scalars(select(User).where(User.name == 이름)).first()
            assert 사람 is not None, f"① {이름} 이 안 만들어졌다"
            assert 사람.login_id == f"sanyeo{i:02d}", "③ 아이디가 같이 안 들어갔다"
            assert "seongyo" in perm.my_dept_keys(사람), "② 부서가 키로 안 붙었다"
            만든이.append(사람.id)

    값들 = set()
    for uid in 만든이:
        낸다 = admin_client.post(f"/admin/users/{uid}/password", follow_redirects=False)
        assert 낸다.status_code == 303 and "k=" in 낸다.headers["location"], \
            f"④ id {uid} 에서 발급이 끊겼다"
        보임 = admin_client.get(낸다.headers["location"])
        m = re.search(r'id="firstpw" readonly value="([^"]+)"', 보임.text)
        assert m, f"④ id {uid} 의 값이 화면에 없다"
        값들.add(m.group(1))
    assert len(값들) == len(만든이), "⑤ 같은 값이 두 사람에게 나갔다"

    글 = admin_client.get("/admin/users").text
    assert "아이디 없는 사람 0명" in 글, "⑥ 아이디 없는 사람이 남았다고 센다"
    assert "비밀번호 안 받은 사람 0명" in 글, "⑥ 비밀번호를 다 줬는데 남았다고 센다"


def test35_f02_사람이_스물이_되어도_화면이_읽힌다(admin_client, 선교사회):
    """바) **수가 두 배가 되는 자리 셋**을 실제로 열어 봅니다 (지시 3-d).

    봅니다 — ① 설정 › 사용자가 그 수를 다 그리는가 ② 업무 목록(담당자를
    고르는 자리)이 열리는가 ③ 봉사자 시간표가 열리는가 — 하나가 500 이면
    그 화면에서 막힙니다.

    **고치는 것은 이 판이 아닙니다** — 잰 값만 보고에 적습니다.
    """
    for i, 이름 in enumerate(가명):
        admin_client.post("/admin/users/new",
                          data={"name": 이름, "phone_number": f"0107777{i:04d}",
                                "login_id": f"jikwon{i:02d}", "role": "general",
                                "dept_seongyo": "member"},
                          follow_redirects=False)
    with app_session() as db:
        전체 = len(db.scalars(select(User)).all())
    assert 전체 == len(가명) + 1, f"미리 만든 수가 다르다: {전체}"

    목록 = admin_client.get("/admin/users")
    assert 목록.status_code == 200
    assert 목록.text.count('name="login_id"') >= 전체, "① 사람을 다 안 그린다"

    for 자리 in ("/tasks", "/live/staff"):
        답 = admin_client.get(자리)
        assert 답.status_code == 200, f"{자리} 가 {답.status_code}"

    # ② **담당자를 고르는 자리**는 목록이 아니라 이 응답입니다(4-14) — 행에
    # 명단을 실어 보내지 않고 서버가 한 번에 줍니다. 그 명단이 수를 타고
    # 자라는 자리라, **몇 명이 실리고 그동안 질의가 몇 번 도는지**를 잽니다.
    # **고치는 것은 이 판이 아닙니다** — 잰 값만 보고에 적습니다.
    run_id = _업무하나(선교사회)
    사람수, 명단수, 질의수 = _고르는자리(admin_client, run_id)
    assert 명단수 == 전체, f"② 고를 사람이 {명단수}명 — {전체}명이어야 한다"

    # **두 배로 늘려 한 번 더 잽니다** — 한 점만 재면 「두 배가 되면 어떤가」 는
    # 잰 값이 아니라 짐작입니다. 자라는 모양이 보고에 들어갈 값입니다.
    for i, 이름 in enumerate(가명):
        admin_client.post("/admin/users/new",
                          data={"name": f"{이름} 둘", "phone_number": f"0107778{i:04d}",
                                "login_id": f"jikwonb{i:02d}", "role": "general",
                                "dept_seongyo": "member"},
                          follow_redirects=False)
    사람수2, 명단수2, 질의수2 = _고르는자리(admin_client, run_id)
    assert 사람수2 == 사람수 * 2 - 1, f"두 배로 안 늘었다: {사람수} → {사람수2}"
    assert 명단수2 == 사람수2, "② 늘린 사람이 고르는 자리에 안 뜬다"
    print(f"[잰 값] 고르는 자리 — 사람 {사람수}명 질의 {질의수}번"
          f" · 사람 {사람수2}명 질의 {질의수2}번")


def _고르는자리(client, run_id: int) -> tuple[int, int, int]:
    """(그때의 사람 수, 고를 사람 수, 그 한 요청이 돈 질의 수)."""
    from sqlalchemy import event

    from app.db import engine

    셈 = []

    def 센다(*a):
        셈.append(1)

    with app_session() as db:
        사람수 = len(db.scalars(select(User)).all())
    event.listen(engine, "before_cursor_execute", 센다)
    try:
        답 = client.get(f"/board/task/{run_id}")
    finally:
        event.remove(engine, "before_cursor_execute", 센다)
    assert 답.status_code == 200, f"담당자 고르는 자리가 {답.status_code}"
    return 사람수, len(답.json()["candidates"]), len(셈)


def _업무하나(retreat_id: int) -> int:
    """선교사회 업무 한 건 — 담당자 고르는 자리를 열 근거."""
    from app.models import Department, TaskLibrary, TaskRun

    with app_session() as db:
        dept = db.scalars(select(Department).where(
            Department.retreat_id == retreat_id, Department.key == "seongyo")).first()
        lib = TaskLibrary(title="성찬 준비", kind="main", default_department_key="seongyo")
        db.add(lib)
        db.flush()
        run = TaskRun(library_id=lib.id, retreat_id=retreat_id,
                      department_id=dept.id, run_no=1)
        db.add(run)
        db.commit()
        return run.id
