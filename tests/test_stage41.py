"""회차를 넘나드는 자리 — **회차 A 를 고치면 B 가 안 바뀌는가** (2026-09-12).

이 저장소의 사고는 거의 다 이 자리에서 났습니다 — 비고가 품목에 붙어 회차를
넘어 샜고(4-18 · 도막 4), 약 묶음이 회차별로 갈렸고, 부서 행은 회차마다 따로
서며(2장), 개회일을 바꾸면 백 건이 함께 움직입니다(6-4). 회차가 둘이고 곧
셋이 되므로 그 갈림을 시험으로 붙듭니다.

**먼저 가릅니다 — 안 갈라 두고 재면 맞는 것을 틀렸다고 말합니다.**

| 회차마다 따로 서야 하는 것 | 회차를 넘어 공유되는 것 |
|---|---|
| `EquipmentRun` — 수량·위치·묶음·비고·체크·`included` | `EquipmentItem` — 품목 이름·팀 키 |
| `TaskRun` — 날짜·상태·담당자·번호·`included` | `TaskLibrary` — 제목·규칙·선후행·기본 D-주차 |
| `Department` 행 — 회차마다 새로 선다 | **부서 키**와 그 키에 붙은 소속(`user_departments` · 4-12) |
| `Program` · `ProgramItem` — 프로그램표와 체크 | (프로그램표는 복사해 오는 것이지 공유가 아니다 — 5-5) |

**오른쪽 칸을 「안 바뀌어야 한다」 로 재지 않습니다.** 그것이 바뀌는 것은
고장이 아니라 정해진 모양이고, 그렇게 재면 제목을 고치는 기능이 빨개집니다.
그래서 이 파일은 **양쪽을 다 잽니다** — 갈려야 할 것이 갈리는지, 공유돼야
할 것이 공유된 채로 남는지.

**쓰는 길은 자리마다 다르고, 어디가 어느 길인지 적습니다.**

| 길 | 어디 |
|---|---|
| 화면이 쓰는 엔드포인트 (`?retreat_id=`) | `a01` · `b01` · `b02` · `c01` · `d01` |
| 도메인 함수 | `a02`(품목 이름) · `b03`(`library.reschedule`) · `c02`(`permissions.assign`) |

엔드포인트로 가면 **「어느 회차를 고르는가」 까지** 재집니다(`app/deps.py` 의
`resolve_retreat` 와 라우터의 회차 대조). 도메인으로 가면 그 자리는 안
재집니다 — 예를 들어 `b03` 은 화면의 길이 설정의 회차 수정 POST 인데 도메인
함수를 바로 부르므로 **라우터가 회차를 제대로 넘기는지는 이 줄이 안 봅니다.**
처음에 머리말이 「전부 엔드포인트」 라고 적혀 있었는데 실제보다 넓은 말이라
고쳤습니다(2026-09-13 커밋 전 검토).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app import models
from app.domain import permissions as perm
from app.domain import staff_sheet
from tests.conftest import app_session

A열림 = dt.date(2026, 8, 21)
B열림 = dt.date(2027, 8, 20)


@pytest.fixture
def 두회차(admin_client):
    """회차 둘이 **같은 품목·같은 라이브러리·같은 부서 키**를 쓴다.

    공유되는 것을 실제로 공유시켜 두지 않으면 「안 바뀐다」 만 재게 되어,
    공유가 끊기는 고장(그쪽도 똑같이 비쌉니다)을 한 번도 안 봅니다.
    """
    with app_session() as db:
        방 = {}
        for 이름, 열림 in [("A", A열림), ("B", B열림)]:
            회차 = models.Retreat(
                name=f"{열림.year} 여름수련회", start_date=열림,
                end_date=열림 + dt.timedelta(days=2))
            db.add(회차)
            db.flush()
            방[이름] = 회차
            for 순서, (키, 부서이름) in enumerate(
                    [("chongmuM", "1 총무M"), ("hebron", "5 헤브론")]):
                db.add(models.Department(
                    retreat_id=회차.id, key=키, name=부서이름, sort_order=순서))
        db.flush()

        # ── 품목은 하나, run 은 회차마다 (4-18)
        품목 = models.EquipmentItem(team_key="hebron", name="릴선")
        db.add(품목)
        db.flush()
        비품 = {}
        for 이름 in ("A", "B"):
            run = models.EquipmentRun(
                retreat_id=방[이름].id, item_id=품목.id, group_name="음향",
                quantity="2개", location="창고", note="", checked=False,
                included=True, sort_order=0)
            db.add(run)
            db.flush()
            비품[이름] = run.id

        # ── 라이브러리는 하나, run 은 회차마다 (6-1)
        라이브러리 = models.TaskLibrary(
            title="음향 점검", kind="main", default_department_key="hebron",
            date_anchor="week", default_d_week=5, default_offset_days=0,
            default_span_days=7, rules="해마다 같은 방식으로 한다")
        db.add(라이브러리)
        db.flush()
        업무 = {}
        for 번호, 이름 in enumerate(("A", "B"), start=1):
            열림 = 방[이름].start_date
            run = models.TaskRun(
                library_id=라이브러리.id, retreat_id=방[이름].id, included=True,
                run_no=번호,
                department_id=db.scalars(
                    select(models.Department.id).where(
                        models.Department.retreat_id == 방[이름].id,
                        models.Department.key == "hebron")).first(),
                d_week=5, start_date=열림 - dt.timedelta(days=30),
                end_date=열림 - dt.timedelta(days=23), status="대기")
            db.add(run)
            db.flush()
            업무[이름] = run.id

        # ── 프로그램표는 회차마다 따로 선다 (5-1 · 5-5)
        항목 = {}
        for 이름 in ("A", "B"):
            프로그램 = models.Program(
                retreat_id=방[이름].id, day="1일차", start_time="18:00",
                name="음향 및 무대설치", host="헤브론", audience="staff",
                track="main", sort_order=0)
            db.add(프로그램)
            db.flush()
            it = models.ProgramItem(
                program_id=프로그램.id, phase="pre", part_key="헤브론",
                assignee_name="전체", text="케이블 포설", scope="team", sort_order=0)
            db.add(it)
            db.flush()
            항목[이름] = it.id

        db.commit()
        return {
            "회차": {k: v.id for k, v in 방.items()},
            "품목": 품목.id, "비품": 비품, "라이브러리": 라이브러리.id,
            "업무": 업무, "항목": 항목,
        }


def _비품(run_id: int):
    with app_session() as db:
        return db.get(models.EquipmentRun, run_id)


def _업무(run_id: int):
    with app_session() as db:
        return db.get(models.TaskRun, run_id)


# ────────────────────────────────────────────────────────── 비품 (4-18)


def test41_a01_비품은_회차마다_따로_선다(admin_client, 두회차):
    """A 의 수량·위치·체크·`included` 를 고쳐도 B 의 run 은 그대로다.

    **이것이 도막 4 에서 실제로 샌 자리입니다** — 비고가 품목(라이브러리 층)에
    붙어 있어 한 회차에서 적은 말이 다음 회차에 그대로 따라갔습니다.
    """
    A, B = 두회차["회차"]["A"], 두회차["회차"]["B"]
    runA, runB = 두회차["비품"]["A"], 두회차["비품"]["B"]
    전 = _비품(runB)
    앞수량, 앞위치, 앞체크, 앞포함 = 전.quantity, 전.location, 전.checked, 전.included

    r = admin_client.post(f"/equipment/{runA}/edit?retreat_id={A}",
                          data={"quantity": "네 개", "location": "무대 뒤"},
                          follow_redirects=False)
    assert r.status_code in (302, 303), r.text
    admin_client.post(f"/equipment/{runA}/toggle?retreat_id={A}", follow_redirects=False)
    admin_client.post(f"/equipment/{runA}/include?retreat_id={A}", follow_redirects=False)

    앞 = _비품(runA)
    assert (앞.quantity, 앞.location, 앞.checked, 앞.included) == ("네 개", "무대 뒤", True, False), \
        "A 쪽이 안 바뀌었다 — 이 시험이 무엇을 재는지부터 틀렸다"

    뒤 = _비품(runB)
    assert 뒤.quantity == 앞수량, "A 의 수량을 고쳤는데 B 가 따라 바뀌었다"
    assert 뒤.location == 앞위치, "A 의 위치를 고쳤는데 B 가 따라 바뀌었다"
    assert 뒤.checked == 앞체크, "A 를 체크했는데 B 도 체크됐다"
    assert 뒤.included == 앞포함, "A 에서 뺐는데 B 에서도 빠졌다"


def test41_a02_품목은_회차를_넘어_공유된다(admin_client, 두회차):
    """**이쪽은 「안 바뀐다」 로 재면 안 되는 자리입니다** (수용 기준 다).

    품목 이름은 라이브러리 층이라 회차를 넘어 하나입니다 — 두 회차의 run 이
    같은 품목을 가리키고, 이름을 고치면 두 화면이 함께 새 이름을 보입니다.
    """
    A, B = 두회차["회차"]["A"], 두회차["회차"]["B"]
    runA, runB = _비품(두회차["비품"]["A"]), _비품(두회차["비품"]["B"])
    assert runA.item_id == runB.item_id == 두회차["품목"], \
        "회차마다 품목이 복제되면 「지난 회차의 그 품목」 을 알아볼 열쇠가 없다"

    with app_session() as db:
        db.get(models.EquipmentItem, 두회차["품목"]).name = "릴선 30m"
        db.commit()

    for 회차 in (A, B):
        화면 = admin_client.get(f"/equipment?retreat_id={회차}")
        assert 화면.status_code == 200
        assert "릴선 30m" in 화면.text, f"회차 {회차} 화면에 바뀐 품목 이름이 없다"


# ────────────────────────────────────────────────────────── 업무 (6-1 · 6-4)


def test41_b01_업무의_실행_기록은_회차마다_따로_선다(admin_client, 두회차):
    """상태·날짜는 `TaskRun` 의 것이다 — A 를 고쳐도 B 는 그대로."""
    A = 두회차["회차"]["A"]
    runA, runB = 두회차["업무"]["A"], 두회차["업무"]["B"]
    전 = _업무(runB)
    앞상태, 앞시작, 앞끝 = 전.status, 전.start_date, 전.end_date

    r = admin_client.post(f"/board/task/{runA}/status?retreat_id={A}",
                          json={"status": "진행중"})
    assert r.status_code == 200, r.text
    새시작 = (A열림 - dt.timedelta(days=40)).isoformat()
    r = admin_client.post(f"/board/task/{runA}/dates?retreat_id={A}",
                          json={"start": 새시작, "end": 새시작})
    assert r.status_code == 200, r.text

    앞 = _업무(runA)
    assert 앞.status == "진행중" and 앞.start_date.isoformat() == 새시작

    뒤 = _업무(runB)
    assert 뒤.status == 앞상태, "A 의 상태를 바꿨는데 B 도 바뀌었다"
    assert (뒤.start_date, 뒤.end_date) == (앞시작, 앞끝), \
        "A 의 날짜를 옮겼는데 B 도 움직였다"


def test41_b02_라이브러리는_회차를_넘어_공유된다(admin_client, 두회차):
    """제목은 라이브러리에 붙는다 (4-9) — **공유되는 것이 맞다.**

    다만 그때도 **그 회차의 실행 기록(날짜·상태)은 그대로**여야 한다
    (6-6 의 「지난 회차의 실행 기록 날짜는 건드리지 않는다」).
    """
    A = 두회차["회차"]["A"]
    runA, runB = 두회차["업무"]["A"], 두회차["업무"]["B"]
    전 = _업무(runB)
    앞상태, 앞시작 = 전.status, 전.start_date

    r = admin_client.post(f"/board/task/{runA}/title?retreat_id={A}",
                          json={"title": "음향 점검과 리허설"})
    assert r.status_code == 200, r.text

    with app_session() as db:
        뒤 = db.get(models.TaskRun, runB)
        assert 뒤.library.title == "음향 점검과 리허설", \
            "제목이 라이브러리에 안 붙었다 — 회차를 넘으면 같은 업무의 이름이다"
        assert (뒤.status, 뒤.start_date) == (앞상태, 앞시작), \
            "제목만 고쳤는데 지난 회차의 실행 기록이 함께 움직였다"


def test41_b03_개회일을_바꾸면_그_회차만_움직인다(admin_client, 두회차):
    """6-4 의 재계산은 **그 회차의 run** 만 다시 센다.

    개회일 하나를 고치면 백 건이 함께 움직이는 자리라, 그 백 건이 옆 회차로
    넘어가면 아무도 눈치채지 못한다.
    """
    from app.domain import library as lib

    A, B = 두회차["회차"]["A"], 두회차["회차"]["B"]
    A앞 = _업무(두회차["업무"]["A"]).start_date
    runB전 = _업무(두회차["업무"]["B"])
    앞시작, 앞끝 = runB전.start_date, runB전.end_date

    with app_session() as db:
        회차A = db.get(models.Retreat, A)
        회차A.start_date = A열림 + dt.timedelta(days=7)
        회차A.end_date = 회차A.start_date + dt.timedelta(days=2)
        lib.reschedule(db, 회차A)
        db.commit()

    # **아래 두 줄은 한 벌이다** — 「A 가 움직였다」 를 안 세우면
    # 「B 가 안 움직였다」 는 늘 초록이다 (커밋 전 검토가 잡았다).
    assert _업무(두회차["업무"]["A"]).start_date != A앞, \
        "A 의 개회일을 이레 옮겼는데 A 의 업무가 안 움직였다 — 이러면 아래 줄은 " \
        "아무것도 안 재는 줄이 된다 (재계산이 통째로 안 돌아도 초록이다)"
    runB = _업무(두회차["업무"]["B"])
    assert (runB.start_date, runB.end_date) == (앞시작, 앞끝), \
        "A 의 개회일을 옮겼는데 B 의 업무 날짜가 함께 움직였다"


# ────────────────────────────────────────────────────────── 부서 (2장 · 4-12)


def test41_c01_부서_행은_회차마다_따로_선다(admin_client, 두회차):
    """A 에 부서를 더해도 B 의 목록은 그대로다."""
    from app.domain.departments import departments_of

    A, B = 두회차["회차"]["A"], 두회차["회차"]["B"]
    with app_session() as db:
        앞A = len(departments_of(db, A))
        앞B = [d.key for d in departments_of(db, B)]

    r = admin_client.post(f"/departments/create?retreat_id={A}",
                          data={"name": "9 새친구팀", "color_tag": "#A98A1E"},
                          follow_redirects=False)
    assert r.status_code in (302, 303), r.text

    with app_session() as db:
        뒤A = [d.name for d in departments_of(db, A)]
        뒤B = [d.key for d in departments_of(db, B)]
    assert len(뒤A) == 앞A + 1 and "9 새친구팀" in 뒤A
    assert 뒤B == 앞B, "A 에 부서를 더했는데 B 의 부서 목록이 함께 바뀌었다"


def test41_c02_소속은_키에_붙어_회차를_넘는다(admin_client, 두회차):
    """**이쪽도 「안 바뀐다」 로 재면 안 됩니다** (수용 기준 다).

    부서 행은 회차마다 따로 서지만 소속은 **키**에 붙습니다 — 그래서 A 에서
    헤브론에 넣은 사람은 B 에서도 헤브론입니다. id 로 붙이면 새 회차가 열리는
    순간 모든 부서 리더가 자기 부서 업무조차 못 고칩니다(2장).
    """
    A, B = 두회차["회차"]["A"], 두회차["회차"]["B"]
    with app_session() as db:
        사람 = models.User(name="헤브론 리더", phone_number="01077778888",
                          role="general")
        db.add(사람)
        db.flush()
        A헤브론 = db.scalars(select(models.Department).where(
            models.Department.retreat_id == A,
            models.Department.key == "hebron")).first()
        perm.assign(db, 사람, A헤브론, "lead")
        db.commit()
        사람_id = 사람.id

    with app_session() as db:
        사람 = db.get(models.User, 사람_id)
        B헤브론 = db.scalars(select(models.Department).where(
            models.Department.retreat_id == B,
            models.Department.key == "hebron")).first()
        assert A헤브론.id != B헤브론.id, "부서 행이 회차마다 따로 서지 않으면 이 시험은 뜻이 없다"
        assert "hebron" in perm.my_dept_keys(사람), "소속이 키에 안 붙었다"
        assert perm.is_lead_of(사람, B헤브론.key), \
            "A 에서 준 소속이 B 에서 끊겼다 — 새 회차가 열리면 자기 부서를 못 고친다"


# ────────────────────────────────────────────────────────── 봉사팀 (5-8)


def test41_d01_프로그램표와_체크는_회차마다_따로_선다(admin_client, 두회차):
    """A 의 항목을 체크해도 B 의 항목은 안 눌린다. 표도 각자 자기 것만."""
    A, B = 두회차["회차"]["A"], 두회차["회차"]["B"]
    itemA, itemB = 두회차["항목"]["A"], 두회차["항목"]["B"]

    r = admin_client.post(f"/live/item/{itemA}/check?retreat_id={A}",
                          json={"done": True})
    assert r.status_code == 200, r.text

    with app_session() as db:
        assert db.get(models.ProgramItem, itemA).done_at is not None
        assert db.get(models.ProgramItem, itemB).done_at is None, \
            "A 에서 체크했는데 B 의 같은 항목도 눌렸다"

        표A = staff_sheet.build(db, db.get(models.Retreat, A))
        표B = staff_sheet.build(db, db.get(models.Retreat, B))
    assert "음향 및 무대설치" in str(표A) and "음향 및 무대설치" in str(표B)
    # 표는 **회차의 개회일에서** 일자의 날짜를 센다 (5-1). 두 표의 일자
    # 라벨이 같으면 한쪽이 남의 회차를 그리고 있다는 뜻이다.
    라벨A = [d["label"] for d in 표A["days"]]
    라벨B = [d["label"] for d in 표B["days"]]
    assert 라벨A and 라벨B, "표가 일자를 하나도 안 그렸다 — 이 시험이 아무것도 못 본다"
    assert 라벨A != 라벨B, \
        f"두 회차의 봉사자 시간표가 같은 날짜를 그린다 — 회차를 안 가리고 있다 ({라벨A})"
    assert 표A["retreat"] != 표B["retreat"]
