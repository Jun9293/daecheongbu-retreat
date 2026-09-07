"""UI 개편 마무리 — 미룬 것 닫기.

부서 비교를 키로(U-a) · 실명이 이미지로 새는 길 막기(U-e) ·
환급 판정 좁히기(U-b) · U-c · U-d. 막는 코드마다 막히는 쪽 시험이 함께 있다.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import re
import sqlite3

import pytest
from sqlalchemy import select

from app import models
from app.domain import budget as budget_domain
from tests.conftest import app_session, login_as, make_user

TODAY = dt.date.today()
ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ════════════════════════════════════════════════════════════════════
# 1. 부서 비교를 키로 (U-a)
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def two_retreats(admin_client):
    """지난 회차(hebron 행 A) + 이번 회차(hebron·sketch 행 B) + 지출 하나.

    받는 사람의 소속은 **지난 회차의** hebron 행이다 — 2장이 경고한 그 자리.
    """
    with app_session() as db:
        old = models.Retreat(name="지난 회차", start_date=TODAY - dt.timedelta(days=400),
                             end_date=TODAY - dt.timedelta(days=397))
        db.add(old)
        db.flush()
        old_hebron = models.Department(retreat_id=old.id, key="hebron",
                                       name="5 헤브론", color_tag="#4A8A5C", sort_order=0)
        db.add(old_hebron)
        db.flush()

        cur = models.Retreat(name="이번 회차", meal_subsidy_per_person=8000,
                             start_date=TODAY + dt.timedelta(days=30),
                             end_date=TODAY + dt.timedelta(days=33))
        db.add(cur)
        db.flush()
        hebron = models.Department(retreat_id=cur.id, key="hebron",
                                   name="5 헤브론", color_tag="#4A8A5C", sort_order=0)
        sketch = models.Department(retreat_id=cur.id, key="sketch",
                                   name="4 스케치", color_tag="#B95A83", sort_order=1)
        db.add_all([hebron, sketch])
        db.flush()

        entry = models.ExpenseEntry(
            retreat_id=cur.id, department_id=hebron.id,
            expense_date=TODAY, amount=10_000, subsidy_amount=10_000)
        db.add(entry)
        db.commit()
        ids = {"old_hebron": old_hebron.id, "retreat": cur.id,
               "hebron": hebron.id, "sketch": sketch.id, "entry": entry.id}
    lead = make_user("옛 소속 리더", "01077770001", "dept_lead",
                     department_id=ids["old_hebron"])
    ids["lead"] = lead
    return ids


def test6_k01_다른_회차_소속이_같은_키_부서_지출을_만진다(client, two_retreats):
    """등록 · 지급 전환 · 영수증 붙이기 전부 200 — id 비교면 셋 다 403 이었다."""
    login_as(client, "01077770001")
    client.get(f"/board?retreat_id={two_retreats['retreat']}")

    made = client.post("/expenses/create", data={
        "amount": "5000", "department_id": str(two_retreats["hebron"]),
    }, follow_redirects=True)
    assert made.status_code == 200

    paid = client.post(f"/expenses/{two_retreats['entry']}/paid",
                       data={"redirect_to": "/expenses"}, follow_redirects=True)
    assert paid.status_code == 200

    receipt = client.post(f"/expenses/{two_retreats['entry']}/receipts",
                          data={"memo": "결산 파일에 별첨"}, follow_redirects=True)
    assert receipt.status_code == 200


def test6_k02_다른_키_부서는_여전히_403(client, two_retreats):
    login_as(client, "01077770001")
    client.get(f"/board?retreat_id={two_retreats['retreat']}")
    denied = client.post("/expenses/create", data={
        "amount": "5000", "department_id": str(two_retreats["sketch"]),
    })
    assert denied.status_code == 403


def test6_k03_화면_버튼도_같은_축이다(two_retreats):
    """can_edit_dept(화면)와 assert_can_edit_department(서버)가 같은 판정 —
    갈리면 버튼은 뜨는데 403 이 난다."""
    from app.templating import can_edit_dept

    with app_session() as db:
        lead = db.get(models.User, two_retreats["lead"])
        hebron = db.get(models.Department, two_retreats["hebron"])
        sketch = db.get(models.Department, two_retreats["sketch"])
        assert can_edit_dept(lead, hebron) is True     # 같은 키 — 버튼이 보인다
        assert can_edit_dept(lead, sketch) is False    # 다른 키
        assert can_edit_dept(lead, None) is False      # 부서 미지정 = 총무팀 소관


def test6_k04_새_회차를_열어도_부서_리더가_자기_지출을_만든다(client, admin_client, two_retreats):
    """2장이 경고한 자리를 실제로 밟는다 — 마법사의 create_retreat 로 회차를
    새로 만들고, 옛 소속 리더가 그 회차에서 지출을 등록한다."""
    from app.domain.library import create_retreat

    with app_session() as db:
        retreat = create_retreat(
            db, name="더 새 회차",
            open_date=TODAY + dt.timedelta(days=200),
            close_date=TODAY + dt.timedelta(days=203),
            meal_subsidy=8000,
            department_keys=["hebron", "sketch"],
            selected_library_ids=set(),
        )
        db.commit()
        new_id = retreat.id
        new_hebron = db.scalar(select(models.Department.id).where(
            models.Department.retreat_id == new_id,
            models.Department.key == "hebron"))
        assert new_hebron is not None

    login_as(client, "01077770001")
    client.get(f"/board?retreat_id={new_id}")
    made = client.post("/expenses/create", data={
        "amount": "7000", "department_id": str(new_hebron),
    }, follow_redirects=True)
    assert made.status_code == 200
    with app_session() as db:
        entry = db.scalars(select(models.ExpenseEntry).where(
            models.ExpenseEntry.retreat_id == new_id)).one()
        assert entry.department_id == new_hebron


# 남은 부서 id 비교의 전수 — (파일, 줄, 식): 왜 남는지. 새 비교가 생기거나
# 이 자리들이 움직이면 목록과 어긋나 k05 가 빨개진다 — 그때 다시 본다 (V-c).
ID_비교_허용: dict[tuple[str, int, str], str] = {
    # 키 없는 부서(구설계 데이터)의 되돌림 — None==None 통과 방지
    ("app/domain/permissions.py", 47, "user_department_id == target_department_id"):
        "키가 없을 때만 오는 id 되돌림 경로",
    ("app/notifications.py", 86, "User.department_id == department_id"):
        "department_members 의 키 없는 부서 되돌림",
    ("app/routers/reviews.py", 60, "ReviewRequest.department_id == user.department_id"):
        "키 없는 부서 소속의 받은 요청 조회 되돌림",
    ("app/routers/reviews.py", 80, "user.department_id == target.id"):
        "키 없는 부서 되돌림 (응답 권한)",
    # 같은 회차 안의 데이터 행 집계·조인 — 사람 소속 판정이 아니다
    ("app/domain/board.py", 471, "r.department_id == dept.id"):
        "회차 안 run 을 부서 행별로 묶는 집계",
    ("app/routers/expenses.py", 140, "ExpenseEntry.department_id == my_dept"):
        "my_dept 는 키로 찾은 이번 회차 부서 행 id — 직전 입력값 집계",
    ("app/routers/reviews.py", 56, "Department.id == ReviewRequest.department_id"):
        "요청 행에 부서 행을 붙이는 조인",
    ("app/routers/settings.py", 167, "User.department_id == d.id"):
        "회차 부서별 인원수 집계 (키 없는 부서 되돌림 포함)",
    ("app/routers/settings.py", 419, "Task.department_id == department_id"):
        "옛 Task 표의 회차 데이터 집계",
    ("app/routers/settings.py", 424, "ExpenseEntry.department_id == department_id"):
        "회차 지출의 부서별 집계",
}
ID_비교_패턴 = re.compile(
    r"[\w.]*department_id\s*==\s*[\w.()\[\]]+|[\w.]+\s*==\s*[\w.]*department_id")


def _id_비교_전수() -> list[tuple[str, int, str]]:
    """app/**/*.py 의 부서 id `==` 비교 전부 — (파일, 줄, 정규화한 식)."""
    나온것 = []
    for path in pathlib.Path(ROOT, "app").rglob("*.py"):
        상대 = str(path.relative_to(ROOT)).replace("\\", "/")
        for 줄번호, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            for hit in ID_비교_패턴.findall(line):
                나온것.append((상대, 줄번호, " ".join(hit.split()).rstrip(")],:")))
    return 나온것


def test6_k05_소속_판정의_id_비교가_0곳이다():
    """키를 쓸 수 있는데 id 로 견주는 소속 판정이 없다 (2장).

    남은 id 비교는 전부 키 없는 부서 되돌림이거나 회차 안 데이터 집계·조인 —
    그 자리를 파일·줄·이유로 적어 둔다. 새 비교가 생기면 목록에 없어 빨개진다.
    """
    남은것 = [자리 for 자리 in _id_비교_전수() if 자리 not in ID_비교_허용]
    assert 남은것 == [], f"목록에 없는 부서 id 비교: {남은것}"
    # 검사가 볼 것을 실제로 보고 있다 — 센 것이 0이면 성공이 아니라 실패 (11-3)
    assert len(_id_비교_전수()) == len(ID_비교_허용)


def test6_k05b_새_id_비교를_심으면_잡힌다(tmp_path):
    """막는 코드의 막히는 쪽 — 가짜 id 비교 한 줄이 전수에 잡힌다 (1-c)."""
    temp = ROOT / "app" / "__stage6_fake_tmp.py"
    temp.write_text("ok = user.department_id == target.department_id\n", encoding="utf-8")
    try:
        걸린것 = [자리 for 자리 in _id_비교_전수()
                if 자리[0] == "app/__stage6_fake_tmp.py"]
        assert 걸린것 == [("app/__stage6_fake_tmp.py", 1,
                        "user.department_id == target.department_id")]
        assert 걸린것[0] not in ID_비교_허용          # 목록에 없으니 k05 가 빨개진다
    finally:
        temp.unlink()


# ════════════════════════════════════════════════════════════════════
# 2. 실명이 이미지로 새는 길 (U-e)
# ════════════════════════════════════════════════════════════════════


def _map_or_skip():
    anon = _load("anonymize")
    try:
        return anon.load_map()[0]
    except SystemExit:
        pytest.skip("대응표가 없다 — 새로 받은 사본에서는 잴 실명이 없다")


def _fake_db(tmp_path, payer: str) -> pathlib.Path:
    db_path = tmp_path / "app.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE IF NOT EXISTS expense_entries (payer_name TEXT)")
    con.execute("DELETE FROM expense_entries")
    con.execute("INSERT INTO expense_entries VALUES (?)", (payer,))
    con.commit()
    con.close()
    return db_path


def test6_g01_실명_DB_면_devserve_검사가_멈춘다(tmp_path):
    names = _map_or_skip()
    dev = _load("check_dev_db")
    real = next(n for n, _ in names if len(n) >= 2)   # 경계 오탐이 없는 표기로

    걸림 = dev.실명이있나(_fake_db(tmp_path, real))
    assert 걸림.get("expense_entries.payer_name") == 1   # 막는 쪽

    # **이름은 찍지 않는다** — 걸린 수만 담는다
    assert real not in str(걸림)


def test6_g02_가명이면_통과하고_낱말_속_이름은_안_걸린다(tmp_path):
    names = _map_or_skip()
    dev = _load("check_dev_db")
    real, fake = next((n, f) for n, f in names if len(n) >= 2)

    assert dev.실명이있나(_fake_db(tmp_path, fake)) == {}          # 가명 — 통과
    # 낱말에 붙은 것은 이름이 아니다 (anonymize 의 경계 규칙 그대로)
    assert dev.실명이있나(_fake_db(tmp_path, f"가{real}나")) == {}
    assert dev.실명이있나(_fake_db(tmp_path, real + "M")) == {"expense_entries.payer_name": 1}
    # `M` 뒤에 조사가 붙어도 이름이다 — 11-2 에서 실제로 샌 모양 (`◯◯M으로`)
    assert dev.실명이있나(_fake_db(tmp_path, real + "M으로 정함")) == {"expense_entries.payer_name": 1}


def test6_g05_깨진_대응표는_통과가_아니라_멈춤이다(tmp_path, monkeypatch):
    """게이트가 조용히 꺼진 채 초록을 내면 「0개를 보며 초록」(11-3)이다."""
    _map_or_skip()
    dev = _load("check_dev_db")

    def 거절():
        raise SystemExit("깨진 대응표")
    monkeypatch.setattr(dev._anon, "load_map", 거절)
    with pytest.raises(SystemExit):                     # 삼키지 않는다
        dev.실명이있나(_fake_db(tmp_path, "아무개"))

    monkeypatch.setattr(dev._anon, "load_map", lambda: ([], {}))
    with pytest.raises(SystemExit):                     # 빈 목록도 통과가 아니다
        dev.실명이있나(_fake_db(tmp_path, "아무개"))


def test6_g03_확인_안_된_이미지는_check_names_가_막는다(tmp_path):
    cn = _load("check_names")

    # 순수 함수 — 확인 파일에 경로·해시가 둘 다 있어야 통과 (막는 쪽)
    목록 = [("docs/review/새것.png", "abc123def456")]
    assert cn.미확인이미지(목록, "") == ["docs/review/새것.png (해시 abc123def456)"]
    assert cn.미확인이미지(목록, "docs/review/새것.png | abc123def456 | 봤음") == []
    # **내용만 바뀌어도 걸린다** — 확인 파일의 해시가 옛것이면 확인 안 된 것 (1-a)
    assert cn.미확인이미지(목록, "docs/review/새것.png | 000000000000 | 봤음") == [
        "docs/review/새것.png (해시 abc123def456)"]

    # 저장소 통합 — 임시 이미지를 만들면 이미지목록() 이 잡고 검사가 1 로 끝난다
    temp = ROOT / "docs" / "review" / "__stage6_test_tmp.png"
    temp.write_bytes(b"\x89PNG\r\n\x1a\n")
    try:
        경로들 = [상대 for 상대, _ in cn.이미지목록()]
        assert "docs/review/__stage6_test_tmp.png" in 경로들
        assert cn.이미지검사() == 1                     # 막는 쪽 — 0 이 아니다
    finally:
        temp.unlink()
    assert "docs/review/__stage6_test_tmp.png" not in [상대 for 상대, _ in cn.이미지목록()]

    # 기존 이미지 전부가 확인 파일과 해시까지 일치한다 — 지금 상태가 통과다
    assert cn.이미지검사() == 0


def test6_g03b_막히는_쪽이_콘솔에서도_말을_한다():
    """실패 안내문의 「—」 가 cp949 콘솔에서 UnicodeEncodeError 로 죽어
    첫 줄만 찍히던 것 — 막는 검사가 말을 못 하면 막히는 쪽이 사람에게
    안 보인다 (11-3). 파이프(cp949)로 실제 프로세스를 돌려 잰다."""
    import os
    import subprocess

    temp = ROOT / "docs" / "review" / "__stage6_cp949_tmp.png"
    temp.write_bytes(b"\x89PNG\r\n\x1a\n")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
    try:
        r = subprocess.run(
            [str(ROOT / ".venv" / "Scripts" / "python.exe"),
             str(ROOT / "scripts" / "check_names.py")],
            capture_output=True, cwd=ROOT, env=env, timeout=120)
    finally:
        temp.unlink()
    assert r.returncode == 1                              # 막는 쪽 — 여전히 막는다
    assert b"UnicodeEncodeError" not in r.stderr          # 죽지 않고
    assert "__stage6_cp949_tmp".encode("cp949") in r.stdout   # 무엇이 막았는지 말한다


def test6_g04_devserve_가_검사를_지나서만_뜬다():
    bat = (ROOT / "scripts" / "devserve.bat").read_bytes().decode("cp949")
    assert "check_dev_db.py" in bat
    at_check = bat.index("check_dev_db.py")
    at_serve = bat.index("uvicorn")
    assert at_check < at_serve                          # 뜨기 전에 검사한다
    assert "errorlevel 1 exit /b 1" in bat.replace("if ", "")


# ════════════════════════════════════════════════════════════════════
# 3. 환급 판정 좁히기 (U-b) — 넷
# ════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("payer, refund", [
    ("수련회계좌", False),    # 표기 그대로
    ("수련회 계좌", False),   # 변형 표기 — 공백을 지우고 견준다
    ("", False),             # 빈 값 — 지출자를 안 적은 것이지 개인이 아니다
    ("박민준", True),        # 사람 이름(가명) — 환급 대상
])
def test6_r01_환급_판정_넷(payer, refund):
    entry = models.ExpenseEntry(payer_name=payer or None)
    assert budget_domain.is_refund_target(entry) is refund


def test6_r02_지출자_채우기_단추가_있다():
    html = (ROOT / "app" / "templates" / "expenses.html").read_text(encoding="utf-8")
    assert 'id="payer-fill"' in html
    js = (ROOT / "app" / "static" / "js" / "expenses.js").read_text(encoding="utf-8")
    assert "payer-fill" in js


# ════════════════════════════════════════════════════════════════════
# 4. U-c · U-d
# ════════════════════════════════════════════════════════════════════


def test6_u01_refunds_301_이_쿼리를_안_버린다(admin_client, two_retreats):
    r = admin_client.get(f"/refunds?retreat_id={two_retreats['retreat']}",
                         follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == (
        f"/expenses?filter=refund&retreat_id={two_retreats['retreat']}")
    # 쿼리가 없으면 그대로
    bare = admin_client.get("/refunds", follow_redirects=False)
    assert bare.headers["location"] == "/expenses?filter=refund"


def test6_u02_부제_없는_화면에_빈_점이_안_남는다(admin_client, two_retreats):
    page = admin_client.get("/board/task/999999")      # 404 화면
    assert page.status_code == 404
    assert "<em>· </em>" not in page.text and "<em>·</em>" not in page.text
