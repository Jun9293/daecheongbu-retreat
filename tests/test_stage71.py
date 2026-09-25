"""2단계 뒷정리 — 업무 추가 팝업에서 **날짜 없이** 업무를 만든다 (봐둘것 BJ-c 를 닫는다).

**안 고른 것과 잘못 고른 것은 다르다** (2026-09-25 사람이 정함). 안 고르면 날짜 없는
업무가 되고, 그런 업무는 달력이 「날짜가 없는 업무 N건」 으로 따로 모아 둔다(4-13) —
회의 항목 전환이 마감 없는 항목을 그대로 넘기는 것과 **같은 함수 · 같은 규칙**이다(12장).

| 무엇을 재나 | 어디 |
|---|---|
| 날짜 없이 저장되고, 만들어진 업무에 날짜가 없다 | `가` |
| 그 업무가 달력의 「날짜가 없는 업무」 로 선다 (4-13) | `나` |
| **막는 쪽은 그대로 막힌다** — 꼴이 틀린 값 · 마감이 시작보다 앞 | `다` |
| 두 길이 같은 함수를 지난다 · 화면이 빈 글자를 안 보낸다 | `라` |
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from sqlalchemy import select

from app import models
from tests.conftest import app_session

ROOT = pathlib.Path(__file__).resolve().parents[1]
라우터 = (ROOT / "app" / "routers" / "board.py").read_text(encoding="utf-8")
팝업JS = (ROOT / "app" / "static" / "js" / "board_add.js").read_text(encoding="utf-8")
회의라우터 = (ROOT / "app" / "routers" / "meetings.py").read_text(encoding="utf-8")

OPEN = dt.date(2026, 7, 20)


@pytest.fixture
def 회차(admin_client):
    """앱이 쓰는 그 엔진에 회차 하나."""
    with app_session() as db:
        r = models.Retreat(name="2026 여름수련회 Belong",
                           start_date=OPEN, end_date=OPEN + dt.timedelta(days=3))
        db.add(r)
        db.flush()
        db.add(models.Department(retreat_id=r.id, key="chongmu", name="1 총무팀", sort_order=0))
        db.commit()
        return r.id


def 만든다(client, **덮어쓰기):
    몸 = {"title": "날짜 안 고른 업무", "department_key": "chongmu", "kind": "main"}
    몸.update(덮어쓰기)
    return client.post("/board/add/new", json=몸)


def 그업무(lib_id: int) -> models.TaskRun:
    with app_session() as db:
        return db.scalars(select(models.TaskRun)
                          .where(models.TaskRun.library_id == lib_id)).one()


# ── 가. 날짜 없이 저장된다 ───────────────────────────────────────────

def test71_a01_날짜를_안_보내도_만들어진다(회차, admin_client):
    res = 만든다(admin_client)
    assert res.status_code == 200, res.text
    run = 그업무(res.json()["library_id"])
    assert run.start_date is None and run.end_date is None


def test71_a02_빈_글자를_보내도_같다(회차, admin_client):
    """옛 화면이 아직 빈 글자를 보낼 수 있다 — 그것도 「안 고른 것」 이다."""
    res = 만든다(admin_client, start="", end="")
    assert res.status_code == 200, res.text
    assert 그업무(res.json()["library_id"]).start_date is None


def test71_a03_상대_위치를_지어내지_않는다(회차, admin_client):
    """날짜가 없으면 라이브러리의 D-주차도 없다 — 있으면 개회일이 바뀔 때
    **없던 날짜를 얻는다**(6-4 의 「켠 채 날짜가 빈 업무」)."""
    res = 만든다(admin_client)
    with app_session() as db:
        lib = db.get(models.TaskLibrary, res.json()["library_id"])
        assert lib.default_d_week is None


def test71_a04_활동_기록이_안_터지고_그렇다고_적는다(회차, admin_client):
    res = 만든다(admin_client)
    assert res.status_code == 200
    with app_session() as db:
        로그 = db.scalars(select(models.ActivityLog)
                         .where(models.ActivityLog.action == "업무_신규생성")).all()
    assert 로그 and "날짜 없음" in (로그[-1].summary or "")


# ── 나. 달력이 그 업무를 따로 모은다 (4-13) ──────────────────────────

def test71_b01_달력의_날짜_없는_업무로_선다(회차, admin_client):
    res = 만든다(admin_client, title="달력에서 찾을 업무")
    assert res.status_code == 200
    화면 = admin_client.get("/calendar?scope=all").text
    assert "날짜가 없는 업무" in 화면
    # 그 자리에 실제로 이 업무가 들어 있다 — 건수만 보면 0건이어도 지나간다
    자리 = 화면[화면.index("날짜가 없는 업무"):]
    assert "달력에서 찾을 업무" in 자리[:4000]
    assert "보드에서 기간을 정해 주세요" in 자리[:4000]


def test71_b02_날짜가_있으면_그_자리에_안_선다(회차, admin_client):
    res = 만든다(admin_client, title="날짜 있는 업무", start="2026-07-10")
    assert res.status_code == 200
    화면 = admin_client.get("/calendar?month=2026-07&scope=all").text
    앞 = 화면[:화면.index("날짜가 없는 업무")] if "날짜가 없는 업무" in 화면 else 화면
    assert "날짜 있는 업무" in 앞, "날짜가 있는데 「날짜 없는 업무」 쪽으로 갔다"


# ── 다. 막는 쪽 — 여기는 그대로 막힌다 ──────────────────────────────

def test71_c01_꼴이_틀린_날짜는_그대로_막힌다(회차, admin_client):
    res = 만든다(admin_client, start="2026-13-40")
    assert res.status_code == 400
    assert "기간을 다시 골라주세요." in res.json()["detail"]


def test71_c02_마감이_시작보다_앞서면_막힌다(회차, admin_client):
    res = 만든다(admin_client, start="2026-07-10", end="2026-07-01")
    assert res.status_code == 400
    assert "마감이 시작보다" in res.json()["detail"]


def test71_c03_마감만_보내면_시작은_빈_채로_남는다(회차, admin_client):
    """**「그 날 하루」 가 아니다** — 시작은 비고 마감만 들어간다.

    `create_run` 의 `end = end or start` 에는 거울이 없어서, start 만 빈 채로
    run 이 섭니다. 그 run 을 읽는 네 자리가 서로 다른 말을 합니다 —
    달력은 마감에 점 하나, 보드는 개회일부터 마감까지 긴 바, 드로어는 둘 다
    없음, 활동 기록은 「날짜 없음」.

    **화면에서는 안 닿습니다** — `DatePick` 이 늘 둘 다 채웁니다. 그래서
    지금 새는 곳은 없고, **이 시험은 지금 코드가 무엇을 하는지만** 붙듭니다.
    하루로 볼지 막을지는 사람이 정할 것으로 올렸습니다(2026-09-25 · 봐둘것 BJ-e).
    """
    res = 만든다(admin_client, end="2026-07-11")
    assert res.status_code == 200, res.text
    run = 그업무(res.json()["library_id"])
    assert run.end_date == dt.date(2026, 7, 11)
    assert run.start_date is None, "시작이 마감으로 채워졌다면 네 자리를 다시 봐야 한다"


def test71_c04_이름이_비면_그대로_막힌다(회차, admin_client):
    """날짜를 풀었다고 다른 검증까지 풀리지 않는다."""
    assert 만든다(admin_client, title="   ").status_code == 400


def test71_c05_하위인데_상위가_없으면_그대로_막힌다(회차, admin_client):
    assert 만든다(admin_client, kind="sub").status_code == 400


# ── 라. 두 길이 한 함수를 지나고, 화면이 빈 글자를 안 보낸다 ────────

def test71_d01_회의_항목_전환과_같은_함수다():
    """두 벌이 되면 한쪽만 「날짜 없음」 을 알게 된다."""
    assert "tasks_domain.create_run(" in 라우터
    assert "tasks_domain.create_run(" in 회의라우터
    assert "start=item.due_date" in 회의라우터, "전환이 마감을 그대로 넘기지 않는다"


def test71_d02_화면은_안_고른_날짜를_안_보낸다():
    """빈 글자를 보내면 서버가 「꼴이 틀린 값」 으로 읽는다."""
    assert "start: 날짜.dataset.start || null," in 팝업JS
    assert "end: 날짜.dataset.end || null," in 팝업JS


def test71_d03_라우터가_안_고른_것과_잘못_고른_것을_가른다():
    assert "dt.date.fromisoformat(payload.start) if payload.start else None" in 라우터
    # 그 문구는 남는다 — 뜻만 좁아졌다(꼴이 틀린 값)
    assert "기간을 다시 골라주세요." in 라우터
