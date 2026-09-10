"""도막 4 — 여러 부서·역할.

도막 3 이 「시험이 두 부서를 심는 자리가 0개」 라고 짚은 셋을 둔다 —
두 부서 사람 · 리더 둘 알림 · 소속 없는 일반. 그리고 「표를 읽는 곳은
permissions 하나」 · 「users.department_id 는 0번」 을 시험으로 잰다.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import re

import pytest
from sqlalchemy import func, select, text

from app import models
from app.domain import permissions as perm
from tests.conftest import app_session, login_as, make_user

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = dt.date.today()


@pytest.fixture
def 세부서(admin_client):
    """회차 하나 · 부서 셋(hebron·sketch·koram) · 각 부서 지출 하나."""
    with app_session() as db:
        r = models.Retreat(name="다대다 회차", meal_subsidy_per_person=8000,
                           start_date=TODAY + dt.timedelta(days=30),
                           end_date=TODAY + dt.timedelta(days=33))
        db.add(r); db.flush()
        ids = {"retreat": r.id}
        for i, (key, name) in enumerate((("hebron", "5 헤브론"), ("sketch", "4 스케치"), ("koram", "6 코람데오"))):
            d = models.Department(retreat_id=r.id, key=key, name=name, color_tag="#4A8A5C", sort_order=i)
            db.add(d); db.flush()
            ids[key] = d.id
            e = models.ExpenseEntry(retreat_id=r.id, department_id=d.id, expense_date=TODAY,
                                    amount=1000, subsidy_amount=1000, payer_name="낸 사람")
            db.add(e); db.flush()
            ids[f"entry_{key}"] = e.id
        db.commit()
    admin_client.get(f"/expenses?retreat_id={ids['retreat']}")
    return ids


def _지급(client, entry_id):
    return client.post(f"/expenses/{entry_id}/paid", data={"redirect_to": "/expenses"},
                       follow_redirects=False)


# ── 4-a. 두 부서 사람 ────────────────────────────────────────────

def test25_a01_두_부서_사람은_둘_다_고치고_셋째는_못_고친다(client, 세부서):
    uid = make_user("두 부서", "01066660001", "general",
                    departments=[(세부서["hebron"], perm.LEAD), (세부서["sketch"], perm.MEMBER)])
    login_as(client, "01066660001")
    client.get(f"/expenses?retreat_id={세부서['retreat']}")
    assert _지급(client, 세부서["entry_hebron"]).status_code == 303
    assert _지급(client, 세부서["entry_sketch"]).status_code == 303
    assert _지급(client, 세부서["entry_koram"]).status_code == 403, "셋째 부서를 고쳤다"
    # ③ 화면 판정도 같은 축 — 버튼과 403 이 갈리면 안 된다
    from app.templating import can_edit_dept
    with app_session() as db:
        u = db.get(models.User, uid)
        assert can_edit_dept(u, db.get(models.Department, 세부서["hebron"])) is True
        assert can_edit_dept(u, db.get(models.Department, 세부서["sketch"])) is True
        assert can_edit_dept(u, db.get(models.Department, 세부서["koram"])) is False


def test25_a02_목록과_보드의_기본_범위가_내_부서_전부다(client, 세부서):
    """④ — 두 부서 사람이 목록을 열면 「내 부서」 가 골라져 있고 두 부서 것만 범위다."""
    make_user("두 부서 목록", "01066660002", "general",
              departments=[(세부서["hebron"], perm.MEMBER), (세부서["sketch"], perm.MEMBER)])
    login_as(client, "01066660002")
    page = client.get(f"/tasks?retreat_id={세부서['retreat']}").text
    assert 'value="depts" selected' in page, "내 부서 전부가 기본이 아니다"
    board = client.get(f"/board?retreat_id={세부서['retreat']}").text
    assert 'data-mykeys="hebron,sketch"' in board


# ── 4-b. 리더 둘 알림 ────────────────────────────────────────────

def test25_b01_리더_둘인_부서의_담당자_없는_업무는_둘_다_받는다(세부서):
    """⑤ — 전에는 leads[0] 이라 첫 리더만 받았다."""
    a = make_user("리더 하나", "01066660011", "general", departments=[(세부서["hebron"], perm.LEAD)])
    b = make_user("리더 둘", "01066660012", "general", departments=[(세부서["hebron"], perm.LEAD)])
    c = make_user("팀원", "01066660013", "general", departments=[(세부서["hebron"], perm.MEMBER)])
    from app.domain import notify
    with app_session() as db:
        lib = models.TaskLibrary(title="담당자 없는 업무", kind="main")
        db.add(lib); db.flush()
        run = models.TaskRun(library_id=lib.id, retreat_id=세부서["retreat"],
                             department_id=세부서["hebron"], included=True, status="대기",
                             d_week=1, start_date=TODAY, end_date=TODAY + dt.timedelta(days=7))
        db.add(run); db.commit()
        who = {u.id for u in notify.recipients_for(db, run)}
        assert who == {a, b}, "리더 둘 다 받아야 한다 — 팀원은 아니다"
        assert c not in who
        # ③ 담당자가 있으면 그 사람만
        run.assignee_id = c; db.commit()
        assert {u.id for u in notify.recipients_for(db, run)} == {c}


# ── 4-c. 소속 없는 일반 · admin ─────────────────────────────────

def test25_c01_소속_없는_일반은_편집이_403이고_admin은_전부_된다(client, admin_client, 세부서):
    make_user("소속 없음", "01066660021", "general")
    login_as(client, "01066660021")
    client.get(f"/expenses?retreat_id={세부서['retreat']}")
    assert _지급(client, 세부서["entry_hebron"]).status_code == 403
    page = client.get(f"/expenses?retreat_id={세부서['retreat']}").text
    assert "+ 지출 등록" not in page, "열람 전용에게 등록 단추가 남았다"

    # admin — 소속 없이도, 소속이 있어도 전부
    assert _지급(admin_client, 세부서["entry_koram"]).status_code == 303
    with app_session() as db:
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()
        perm.assign(db, admin, db.get(models.Department, 세부서["hebron"]), perm.LEAD)
        db.commit()
    admin_client.get(f"/expenses?retreat_id={세부서['retreat']}")
    assert _지급(admin_client, 세부서["entry_sketch"]).status_code == 303
    assert _지급(admin_client, 세부서["entry_hebron"]).status_code == 303


# ── 4-d. make_user ───────────────────────────────────────────────

def test25_d01_make_user_가_부서_여럿을_받고_옛_부르기도_통과한다(세부서):
    새 = make_user("여럿", "01066660031", "general",
                   departments=[(세부서["hebron"], perm.LEAD), (세부서["koram"], perm.MEMBER)])
    옛 = make_user("옛 리더", "01066660032", "dept_lead", dept=세부서["sketch"])
    with app_session() as db:
        u = db.get(models.User, 새)
        assert perm.my_dept_keys(u) == {"hebron", "koram"} and perm.lead_keys(u) == {"hebron"}
        o = db.get(models.User, 옛)
        assert o.role == perm.GENERAL and perm.lead_keys(o) == {"sketch"}


# ── 4-e. 옮기는 스크립트 ─────────────────────────────────────────

def test25_e01_옮기는_스크립트가_소속_줄을_만들고_칸을_지운다(client, 세부서, tmp_path, monkeypatch):
    """옛 모양(users.department_id)을 시험 DB 에 만들어 놓고 돌린다."""
    spec = importlib.util.spec_from_file_location("부서옮기기", ROOT / "scripts/부서옮기기.py")
    모듈 = importlib.util.module_from_spec(spec); spec.loader.exec_module(모듈)
    from app.db import engine
    with app_session() as db:
        db.execute(text("ALTER TABLE users ADD COLUMN department_id INTEGER REFERENCES departments(id)"))
        for i, (role, key) in enumerate((("dept_lead", "hebron"), ("member", "sketch"), ("member", "koram")), 1):
            db.execute(text(
                "INSERT INTO users (name, phone_number, role, is_active, department_id, created_at) "
                "VALUES (:n, :p, :r, 1, :d, :t)"),
                {"n": f"옛 {i}", "p": f"0106666004{i}", "r": role, "d": 세부서[key], "t": models._now()})
        db.commit()
        alive = db.execute(select(func.count()).select_from(models.Notification)).scalar_one()
        assert 모듈.칸이있나(db)
        assert len(모듈.옮길것(db)) == 3
        assert db.execute(select(func.count()).select_from(models.User)).scalar_one() >= 4
    # 사본은 시험 폴더로 — 스크립트는 엔진이 쥔 파일(시험 DB)을 뜨고 그 파일을 고친다
    monkeypatch.setattr(모듈.config, "DATA_DIR", tmp_path)
    with app_session() as db:
        n, 사본 = 모듈.옮긴다(db)
    assert n == 3 and 사본.exists()
    with app_session() as db:
        assert not 모듈.칸이있나(db), "칸이 안 지워졌다"
        rows = db.execute(text("select count(*) from user_departments")).scalar_one()
        assert rows == 3
        for i, (key, r) in enumerate((("hebron", perm.LEAD), ("sketch", perm.MEMBER), ("koram", perm.MEMBER)), 1):
            u = db.scalars(select(models.User).where(models.User.name == f"옛 {i}")).one()
            assert u.role == perm.GENERAL and perm.dept_role_of(u, key) == r
        # ③ 표를 다시 만들면서 다른 표의 행이 사라지지 않았다 (CASCADE 가 안 돌았다)
        assert db.execute(select(func.count()).select_from(models.Notification)).scalar_one() == alive
        assert db.execute(text("select count(*) from users")).scalar_one() >= 4


# ── 수용 기준 2 · 3 — 시험으로 잰다 ─────────────────────────────

허용 = {"app/domain/permissions.py", "app/models.py", "scripts/check_dev_db.py"}
# `.departments` 는 회차(`retreat.departments`)·초안·모듈 이름에도 쓰이므로 **사람 쪽만**
# 잡는다 — 주어가 사람을 뜻하는 이름일 때. 새 이름으로 부르면 여기 더한다
표읽기 = re.compile(
    r"UserDepartment\b|user_departments\b|\.dept_role\b"
    r"|\b(?:user|u|person|p|me|actor|assignee|member|lead|leader|who|current_user|admin|target|owner)"
    r"\.departments\b(?!\s*=)")


def _코드만(p: pathlib.Path) -> list[str]:
    """`.py` 는 주석·문자열을 빈칸으로 바꾼 줄들 — 글자를 찾는 시험은 코드와 설명을
    못 가린다(10장). 옮기는 스크립트의 독스트링이 표 이름을 말하는 것은 읽기가 아니다."""
    src = p.read_text(encoding="utf-8")
    if p.suffix != ".py":
        return src.splitlines()
    import io, tokenize
    lines = src.splitlines()
    out = list(lines)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        (r0, c0), (r1, c1) = tok.start, tok.end
        for r in range(r0, r1 + 1):
            line = out[r - 1]
            a = c0 if r == r0 else 0
            b = c1 if r == r1 else len(line)
            out[r - 1] = line[:a] + " " * (b - a) + line[b:]
    return out


# 문자열 안의 날 SQL — 주석·문자열을 걷어내면 이것은 못 본다 (검토가 짚음). 이 저장소는
# 날 SQL 을 실제로 쓴다(`app/db.py` · 옮기기 스크립트)
SQL읽기 = re.compile(r"\b(?:from|join|into|update|table)\s+user_departments\b", re.I)


def _표읽는줄(파일들):
    걸린것 = []
    for p in 파일들:
        rel = p.relative_to(ROOT).as_posix()
        if rel in 허용:
            continue
        원문 = p.read_text(encoding="utf-8").splitlines()
        for i, (줄, 원줄) in enumerate(zip(_코드만(p), 원문), 1):
            if 표읽기.search(줄) or (SQL읽기.search(원줄) and not 원줄.lstrip().startswith("#")):
                걸린것.append(f"{rel}:{i}")
    return 걸린것


def _볼파일():
    return sorted((ROOT / "app").rglob("*.py")) + sorted((ROOT / "scripts").glob("*.py")) \
        + sorted(ROOT.glob("*.py")) \
        + sorted((ROOT / "app/templates").rglob("*.html"))


def test25_f01_user_departments_를_permissions_밖에서_읽는_줄이_0이다():
    assert _표읽는줄(_볼파일()) == []


def test25_f02_표_읽기를_심으면_잡힌다():
    temp = ROOT / "app" / "__stage25_fake_tmp.py"
    try:
        for 줄 in ("rows = db.query(UserDepartment).all()", "for m in user.departments:",
                   "if m.dept_role == 'lead':", "select(user_departments)"):
            temp.write_text(줄 + "\n", encoding="utf-8")
            assert _표읽는줄([temp]) == ["app/__stage25_fake_tmp.py:1"], f"못 잡음: {줄}"
        temp.write_text("for d in retreat.departments:\n", encoding="utf-8")
        assert _표읽는줄([temp]) == [], "회차의 부서 목록은 표 읽기가 아니다"
        temp.write_text('"""user_departments 를 옮긴다"""\n# for m in user.departments\n', encoding="utf-8")
        assert _표읽는줄([temp]) == [], "독스트링·주석은 읽기가 아니다"
        temp.write_text('rows = db.execute(text("select 1 from user_departments"))\n', encoding="utf-8")
        assert _표읽는줄([temp]) == ["app/__stage25_fake_tmp.py:1"], "문자열 안의 날 SQL 을 못 잡음"
    finally:
        temp.unlink()


def test25_g01_users_department_id_가_모델_DB_템플릿_시험에_0번이다():
    assert not hasattr(models.User, "department_id")
    with app_session() as db:
        cols = [r[1] for r in db.execute(text("pragma table_info(users)"))]
    assert "department_id" not in cols
    for p in (ROOT / "app/templates").rglob("*.html"):
        assert "user.department" not in p.read_text(encoding="utf-8"), p
    # 시험 — make_user·User 호출의 department_id 인자 (도막 3 이 44 를 센 그 모양)
    import ast
    걸린것 = []
    for p in sorted((ROOT / "tests").glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
                if name in ("make_user", "User") and any(k.arg == "department_id" for k in node.keywords):
                    걸린것.append(f"{p.name}:{node.lineno}")
    assert 걸린것 == [], 걸린것


# ── 검토자가 짚은 자리 셋 ─────────────────────────────────────────

def test25_h01_같은_키의_지난_회차_소속은_같은_소속이라_떼고_바꾸는_것도_키로_된다(세부서):
    """검토자 probe — 회차 둘에 같은 키(hebron)가 있을 때, 옛 회차 행에 붙은 소속을
    이번 회차 부서 목록으로 `set_memberships` 하면 **떼진다고 말하고 안 떼지던** 것."""
    with app_session() as db:
        old = models.Retreat(name="지난 회차", meal_subsidy_per_person=8000,
                             start_date=TODAY - dt.timedelta(days=400),
                             end_date=TODAY - dt.timedelta(days=397))
        db.add(old); db.flush()
        old_hebron = models.Department(retreat_id=old.id, key="hebron", name="5 헤브론", color_tag="#4A8A5C", sort_order=0)
        db.add(old_hebron); db.flush()
        u = models.User(name="옛 회차 리더", phone_number="01066660071", role="general")
        db.add(u); db.flush()
        perm.assign(db, u, old_hebron, perm.LEAD)
        db.commit()
        uid, old_dept_id = u.id, old_hebron.id

    with app_session() as db:
        u = db.get(models.User, uid)
        new_hebron = db.get(models.Department, 세부서["hebron"])
        # ① 역할을 바꾸면 줄이 둘이 되지 않고 그 줄이 바뀐다 — 읽는 함수들이 같은 답을 낸다
        붙임, 뗌 = perm.set_memberships(db, u, {"hebron": perm.MEMBER}, among=[new_hebron])
        db.commit()
        assert (붙임, 뗌) == (["hebron:member"], [])
        assert len(perm.memberships(u)) == 1
        assert perm.dept_role_of(u, "hebron") == perm.MEMBER
        assert perm.lead_keys(u) == set() and perm.roles_by_key(u) == {"hebron": "member"}
        # ② 비우면 실제로 떼진다
        붙임, 뗌 = perm.set_memberships(db, u, {}, among=[new_hebron])
        db.commit()
        assert (붙임, 뗌) == ([], ["hebron"])
        assert perm.my_dept_keys(u) == set(), "뗐다고 말하고 안 떼졌다"
        assert db.get(models.Department, old_dept_id) is not None    # 부서 행은 그대로


def test25_h02_업무_추가_화면의_담당_부서는_리더인_부서가_골라져_있다(client, 세부서):
    make_user("추가 리더", "01066660072", "general",
              departments=[(세부서["sketch"], perm.MEMBER), (세부서["hebron"], perm.LEAD)])
    login_as(client, "01066660072")
    page = client.get(f"/board/add?retreat_id={세부서['retreat']}").text
    assert 'value="hebron" selected' in page, "리더인 부서가 미리 골라져 있지 않다"
    assert 'value="sketch" selected' not in page


def test25_h03_admin_은_부서_줄이_있어도_받은_요청을_전부_본다(admin_client, 세부서):
    """① — 세는 것(pending_for_user)과 답하는 것(can_respond_to)이 갈리면 배지와 단추가 어긋난다."""
    from app.routers.reviews import can_respond_to, pending_for_user
    with app_session() as db:
        admin = db.scalars(select(models.User).where(models.User.role == perm.ADMIN)).first()
        perm.assign(db, admin, db.get(models.Department, 세부서["hebron"]), perm.MEMBER)
        r = db.get(models.Retreat, 세부서["retreat"])
        for key in ("hebron", "sketch"):
            db.add(models.ReviewRequest(retreat_id=r.id, department_id=세부서[key], status="대기"))
        db.commit()
        got = pending_for_user(db, admin, r)
        assert {x.department.key for x in got} == {"hebron", "sketch"}
        assert all(can_respond_to(db, admin, x) for x in got)
