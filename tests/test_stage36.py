"""2027 회차를 만드는 길 · 단추 어휘 · 안내 글자 급 (2026-09-11).

| 잰 것 | 어디 |
|---|---|
| 가 | 회차를 만들면 부서 행이 **그 회차에** 선다 — 남의 회차 것이 안 딸려 온다 |
| 나 | 새 회차에 붙여도 옛 회차의 소속이 안 바뀐다 |
| 다 | 회차를 만드는 **화면의 길**이 실제로 있는가 — 끝까지 간다 |
| 라·바 | 어휘와 글자 급은 **브라우저에서 뽑은 값**으로 봅니다 — 여기가 아닙니다 |

**라)·마)·바)는 이 파일이 재지 않습니다.** 지시가 「브라우저에서 실제로 뽑은
값으로 견준다 · CSS 파일을 읽어 견주지 않는다」 이므로, 그것은 화면을 열어
재고 보고에 적습니다. 여기서는 **화면이 그 자리를 그리는지**만 봅니다 —
클래스가 빠지면 브라우저에서 잴 것 자체가 없어지기 때문입니다.

**합성 자료만 씁니다** — 운영 DB 는 시험이 열지 않습니다. 사람 이름은 가명입니다.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.domain import permissions as perm
from app.models import Department, Retreat, User
from tests.conftest import app_session

올해 = dt.date(2027, 8, 20)


def _회차들() -> list[tuple[int, str]]:
    with app_session() as db:
        return [(r.id, r.name) for r in db.scalars(select(Retreat).order_by(Retreat.id)).all()]


@pytest.fixture
def 지난회차(admin_client):
    """2026 회차 하나 — 부서 아홉이 선 채로. 새 회차가 물려받을 바탕입니다."""
    from app.domain.library import DEPARTMENT_MASTER

    with app_session() as db:
        retreat = Retreat(name="2026 여름수련회", start_date=dt.date(2026, 8, 21),
                          end_date=dt.date(2026, 8, 23))
        db.add(retreat)
        db.flush()
        for i, (key, name, color) in enumerate(DEPARTMENT_MASTER):
            db.add(Department(retreat_id=retreat.id, key=key, name=name,
                              color_tag=color, sort_order=i))
        db.commit()
        return retreat.id


# ── 다) 회차를 만드는 길이 화면에 있는가 ──────────────────────────────

def test36_a01_회차를_만드는_길은_마법사_하나다(admin_client, 지난회차):
    """다) **화면의 길을 실제로 열어 끝까지 갑니다.**

    봅니다 — ① 설정 › 회차에서 **그 길로 가는 자리**가 화면에 있는가
    ② 그 화면이 열리는가 ③ 거기서 **끝까지 가면 회차가 실제로 서는가**
    ④ 만든 뒤 그 회차로 갈 자리를 돌려주는가.

    **없는데 있다고 적지 않기 위해** ① 을 함께 봅니다 — 엔드포인트만
    있고 그것을 누를 자리가 없으면 그것은 「화면의 길」 이 아닙니다
    (`POST /retreats/create` 가 실제로 그런 자리입니다 — `a02`).
    """
    글 = admin_client.get("/settings/retreats").text
    assert 'href="/setup"' in 글, "① 회차를 만드는 자리가 화면에 없다"

    assert admin_client.get("/setup").status_code == 200, "② 마법사가 안 열린다"

    앞 = len(_회차들())
    답 = admin_client.post("/setup/create", json={
        "name": "2027 여름수련회",
        "open_date": 올해.isoformat(),
        "close_date": (올해 + dt.timedelta(days=2)).isoformat(),
        "meal_subsidy": 8000,
        "department_keys": [k for k, _, _ in _부서목록()],
        "selected": [],
        "adopted": [],
        "new_departments": [],
    })
    assert 답.status_code == 200, f"③ 끝까지 못 갔다: {답.status_code} {답.text[:200]}"
    새회차 = 답.json()["retreat_id"]
    assert len(_회차들()) == 앞 + 1, "③ 회차가 안 섰다"
    assert f"retreat_id={새회차}" in 답.json()["redirect"], "④ 갈 자리를 안 준다"


def _부서목록():
    from app.domain.library import DEPARTMENT_MASTER

    return DEPARTMENT_MASTER


def test36_a02_화면_없는_엔드포인트를_길로_세지_않는다():
    """다) 곁가지 — **엔드포인트가 있는 것과 화면의 길이 있는 것은 다릅니다.**

    `POST /retreats/create` 는 회차를 만들 수 있고 복제까지 되지만,
    **그것을 누를 자리가 화면에 없습니다.** 옛 사용자 POST 가 그렇게
    남아 단계 2 에서 지워진 것과 같은 모양입니다(14장의 그 표).

    봅니다 — ① 화면(템플릿)과 화면 스크립트 어디에도 그 주소가 없는가
    ② 그런데 라우터에는 있는가(둘 다 봐야 「지금은 화면이 없다」 가
    참인 말이 됩니다) ③ 마법사 쪽 주소는 **화면에 있는가**(있어야
    ① 이 「아무것도 못 찾는 검사」 가 아닙니다).
    """
    import pathlib

    뿌리 = pathlib.Path(__file__).resolve().parent.parent
    화면 = [p for p in (뿌리 / "app/templates").rglob("*.html")]
    화면 += [p for p in (뿌리 / "app/static/js").rglob("*.js")]
    글들 = {p: p.read_text(encoding="utf-8") for p in 화면}

    부른곳 = [p.name for p, g in 글들.items() if "/retreats/create" in g]
    assert 부른곳 == [], f"① 화면에 그 주소가 생겼다: {부른곳} — 이 시험을 고쳐라"

    라우터 = (뿌리 / "app/routers/settings.py").read_text(encoding="utf-8")
    assert '"/retreats/create"' in 라우터, "② 엔드포인트가 없어졌다면 ① 은 공짜다"

    마법사 = [p.name for p, g in 글들.items() if '"/setup"' in g or "'/setup'" in g]
    assert 마법사, "③ 아무 화면도 못 읽었다 — ① 이 공짜로 참이다"


# ── 가) 부서 행이 그 회차에 선다 ──────────────────────────────────────

def test36_b01_새_회차의_부서는_그_회차의_것이다(admin_client, 지난회차):
    """가) **둘을 같은 판에서 봅니다.**

    봅니다 — ① 새 회차에 부서 행이 서는가 ② **키가 그대로 따라오는가**
    (2장 — 키가 회차를 넘어 같은 부서임을 알아보는 유일한 근거입니다)
    ③ **옛 회차의 부서 행이 그대로 남아 있는가**(옮겨 가면 지난 회차의
    업무가 부서를 잃습니다) ④ **새 회차의 부서 행이 옛 것과 다른 행인가**
    — id 가 같으면 「물려받았다」 가 아니라 「같은 것을 가리킨다」 입니다.
    """
    with app_session() as db:
        옛부서 = {(d.key, d.id) for d in db.scalars(
            select(Department).where(Department.retreat_id == 지난회차)).all()}
    assert 옛부서, "바탕이 비었다"

    답 = admin_client.post("/setup/create", json={
        "name": "2027 여름수련회",
        "open_date": 올해.isoformat(),
        "close_date": (올해 + dt.timedelta(days=2)).isoformat(),
        "meal_subsidy": 8000,
        "department_keys": [k for k, _, _ in _부서목록()],
        "selected": [], "adopted": [], "new_departments": [],
    })
    새회차 = 답.json()["retreat_id"]

    with app_session() as db:
        새부서 = db.scalars(select(Department)
                          .where(Department.retreat_id == 새회차)).all()
        지금옛것 = {(d.key, d.id) for d in db.scalars(
            select(Department).where(Department.retreat_id == 지난회차)).all()}

    assert 새부서, "① 새 회차에 부서가 안 섰다"
    assert {d.key for d in 새부서} == {k for k, _ in 옛부서}, "② 키가 안 따라왔다"
    assert 지금옛것 == 옛부서, "③ 옛 회차의 부서 행이 바뀌었다"
    assert {d.id for d in 새부서}.isdisjoint({i for _, i in 옛부서}), \
        "④ 같은 행을 두 회차가 가리킨다"


# ── 나) 새 회차에 붙여도 옛 소속이 안 바뀐다 ──────────────────────────

def test36_c01_새_회차에_붙여도_옛_회차의_소속이_그대로다(admin_client, 지난회차):
    """나) **둘을 같은 판에서 봅니다** — 옛 소속이 그대로인가, 새 회차에서도 서는가.

    사역자 열 분이 붙을 자리라 이것이 이 판의 핵심입니다. 그런데 재 보니
    **줄이 하나뿐입니다** — 4-12 가 정한 대로 `assign` 이 **키로 맞춰**
    같은 키의 다른 회차 부서 행을 같은 소속으로 봅니다. 그래서 회차를
    새로 열어도 **다시 붙일 일이 없습니다.**

    봅니다 — ① 옛 회차에 붙인 줄이 그대로 있는가 ② 새 회차 부서로 또
    붙여도 **줄이 안 느는가**(키로 맞추므로) ③ 그래서 새 회차에서도 그
    사람이 선교사회인가 ④ **다른 키로 붙이면 줄이 느는가** — 안 그러면
    ② 가 「아무것도 안 하는 것」 과 구별되지 않습니다.
    """
    from app.models import UserDepartment

    uid = _사람하나("정하윤", "01033330001")

    def 줄들():
        with app_session() as db:
            return {(r.user_id, r.department_id) for r in db.scalars(
                select(UserDepartment).where(UserDepartment.user_id == uid)).all()}

    with app_session() as db:
        옛선교 = db.scalars(select(Department).where(
            Department.retreat_id == 지난회차, Department.key == "seongyo")).first()
        perm.assign(db, db.get(User, uid), 옛선교, perm.MEMBER)
        db.commit()
    옛줄 = 줄들()
    assert len(옛줄) == 1, f"바탕이 이상하다: {옛줄}"

    답 = admin_client.post("/setup/create", json={
        "name": "2027 여름수련회",
        "open_date": 올해.isoformat(),
        "close_date": (올해 + dt.timedelta(days=2)).isoformat(),
        "meal_subsidy": 8000,
        "department_keys": [k for k, _, _ in _부서목록()],
        "selected": [], "adopted": [], "new_departments": [],
    })
    새회차 = 답.json()["retreat_id"]

    with app_session() as db:
        새선교 = db.scalars(select(Department).where(
            Department.retreat_id == 새회차, Department.key == "seongyo")).first()
        perm.assign(db, db.get(User, uid), 새선교, perm.MEMBER)
        db.commit()

    assert 줄들() == 옛줄, "①② 옛 줄이 바뀌었거나 같은 키로 줄이 하나 더 생겼다"
    with app_session() as db:
        assert sorted(perm.my_dept_keys(db.get(User, uid))) == ["seongyo"],             "③ 새 회차에서 그 사람이 선교사회가 아니다"

    # ④ 같은 키라서 안 는 것이지, 붙이는 것이 아무 일도 안 하는 것이 아니다
    with app_session() as db:
        새헤브론 = db.scalars(select(Department).where(
            Department.retreat_id == 새회차, Department.key == "hebron")).first()
        perm.assign(db, db.get(User, uid), 새헤브론, perm.MEMBER)
        db.commit()
    assert len(줄들()) == len(옛줄) + 1, "④ 다른 키인데도 줄이 안 늘었다"
    with app_session() as db:
        assert sorted(perm.my_dept_keys(db.get(User, uid))) == ["hebron", "seongyo"]


def test36_c02_2026_에_붙인_사람은_2027_에서도_그_부서다(admin_client, 지난회차):
    """나) 곁가지 — **지시 1-a 의 까닭을 실제로 재 봅니다.**

    지시는 「2026 에 붙이면 2027 을 열 때 열 명을 다시 붙여야 한다」 를
    2027 을 지금 만드는 까닭으로 들었습니다. **재 보니 그렇지 않습니다** —
    소속은 회차가 아니라 **키**에 붙습니다(4-12). 2026 의 선교사회에 붙인
    사람은 2027 을 연 뒤에도 선교사회입니다.

    봅니다 — ① 2026 에만 붙인 사람이 ② 2027 을 연 뒤 **아무것도 안 했는데**
    그 회차의 화면에서 선교사회로 보이는가 ③ 그 회차의 부서 행을 키로
    찾아 실제로 이어지는가 ④ 안 붙인 사람은 안 보이는가(② 가 「누구나
    통과」 가 아님).
    """
    붙인이 = _사람하나("최도현", "01033330002")
    안붙인이 = _사람하나("박서진", "01033330003")
    with app_session() as db:
        옛선교 = db.scalars(select(Department).where(
            Department.retreat_id == 지난회차, Department.key == "seongyo")).first()
        perm.assign(db, db.get(User, 붙인이), 옛선교, perm.MEMBER)
        db.commit()

    답 = admin_client.post("/setup/create", json={
        "name": "2027 여름수련회",
        "open_date": 올해.isoformat(),
        "close_date": (올해 + dt.timedelta(days=2)).isoformat(),
        "meal_subsidy": 8000,
        "department_keys": [k for k, _, _ in _부서목록()],
        "selected": [], "adopted": [], "new_departments": [],
    })
    새회차 = 답.json()["retreat_id"]

    # ②③ **새 회차 쪽으로는 아무것도 안 했습니다.** 그 회차의 선교사회 업무를
    # 하나 세우고 **화면이 담당자로 누구를 내주는지**를 봅니다 — 4-14 의 그
    # 자리이고, 사역자가 실제로 걸릴 자리이기도 합니다
    run_id = _업무하나(새회차, "seongyo")
    이름들 = {p["name"] for p in
            admin_client.get(f"/board/task/{run_id}").json()["candidates"]}
    assert "최도현" in 이름들, "②③ 2027 업무의 담당자 후보에 안 뜬다"
    assert "박서진" not in 이름들, "④ 안 붙인 사람까지 뜬다"


def _업무하나(retreat_id: int, key: str) -> int:
    from app.models import TaskLibrary, TaskRun

    with app_session() as db:
        dept = db.scalars(select(Department).where(
            Department.retreat_id == retreat_id, Department.key == key)).first()
        lib = TaskLibrary(title="성찬 준비", kind="main", default_department_key=key)
        db.add(lib)
        db.flush()
        run = TaskRun(library_id=lib.id, retreat_id=retreat_id,
                      department_id=dept.id, run_no=1)
        db.add(run)
        db.commit()
        return run.id


def _사람하나(이름: str, 번호: str) -> int:
    with app_session() as db:
        사람 = User(name=이름, phone_number=번호, role="general")
        db.add(사람)
        db.commit()
        return 사람.id


# ── 라·바) 브라우저가 잴 것이 화면에 있는가 ───────────────────────────

def test36_d01_화면이_잴_자리를_그린다(admin_client):
    """라·바) **여기서 어휘를 견주지 않습니다** — 지시가 브라우저에서 뽑은
    값으로 견주라고 했고, 그 값은 보고에 있습니다.

    이 시험이 보는 것은 **잴 것이 화면에 있는가** 하나입니다. 클래스가
    빠지면 브라우저에서 잴 대상 자체가 없어져, 보고의 값이 「안 재고 적은
    것」 이 됩니다.

    봅니다 — ① 단추가 이 페이지의 어휘(`sbtn p`)를 밝히는가 ② 경고 한 줄이
    `.hint` 가 아니라 **자기 자리**에 있는가 ③ 그 페이지의 다른 `.hint` 는
    그대로 남아 있는가(바) 의 「둘을 같은 판에서」) ④ 비밀번호 칸이 여전히
    `type=password` 인가(마) 를 재는 규칙이 그 선택자에 걸립니다).
    """
    from app.domain import login as 로그인

    uid = _나(admin_client)
    with app_session() as db:
        로그인.비밀번호를정한다(db, db.get(User, uid), "지어낸비밀번호36", 첫판=False)

    글 = admin_client.get("/settings").text
    자리 = 글[글.index('action="/settings/password"'):]
    자리 = 자리[:자리.index("</div>\n    {% endif %}") if "{% endif %}" in 자리 else len(자리)]

    assert 'class="sbtn p" type="submit">바꾸기' in 글, "① 단추가 어휘를 안 밝힌다"
    assert '<div class="pwwarn">' in 글, "② 경고가 자기 자리에 없다"
    assert "로그아웃해 주세요" in 글.split('class="pwwarn"')[1][:120], \
        "② 그 자리에 든 말이 다르다"
    assert 글.count('class="hint"') >= 2, "③ 그 페이지의 다른 안내가 사라졌다"
    assert '<div class="hint">규칙은 길이 하나뿐입니다.' in 글, \
        "③ 같은 카드의 나머지 안내까지 옮겨졌다"
    assert 'type="password" id="mypw"' in 글, "④ 잴 선택자가 바뀌었다"


def _나(admin_client) -> int:
    with app_session() as db:
        return db.scalars(select(User).order_by(User.id)).first().id
