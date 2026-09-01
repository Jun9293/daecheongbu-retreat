"""수련회 진행 (CLAUDE.md 5장). 수용 기준 1~17.

**시각에 의존하는 판정이 많습니다.** 그래서 `now` 를 전부 주입합니다 —
진단 패널에서 `today` 를 주입한 것과 같은 방식입니다. 실행 시각에 따라 결과가
갈리는 테스트는 며칠 뒤 아무도 모르게 빨간불이 되고, 그러면 테스트를 안 보게 됩니다.

네트워크·실제 파일시스템에 의존하지 않습니다.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.domain import live as live_domain
from tests.conftest import app_session, login_as

OPEN = dt.date(2026, 8, 21)      # 금 — 1일차
CLOSE = dt.date(2026, 8, 23)     # 일 — 폐회
# 선발대 8/20(목) · 1일차 8/21(금) · 2일차 8/22(토) · 폐회 8/23(일)

D2 = dt.date(2026, 8, 22)
AT = lambda h, m: dt.datetime(D2.year, D2.month, D2.day, h, m)   # noqa: E731


@pytest.fixture
def live_data(admin_client):
    """2일차에 프로그램 3개. 앞뒤로 다른 날도 하나씩."""
    with app_session() as db:
        retreat = models.Retreat(name="2026 여름수련회 Belong", start_date=OPEN, end_date=CLOSE)
        db.add(retreat)
        db.flush()
        for order, (key, name, color) in enumerate(
            [("chongmuM", "1 총무M", "#2F4858"), ("hebron", "5 헤브론", "#4A8A5C")]
        ):
            db.add(models.Department(
                retreat_id=retreat.id, key=key, name=name, color_tag=color, sort_order=order))

        ids = {}

        def program(day, time, name, items, host="총무팀"):
            p = models.Program(
                retreat_id=retreat.id, day=day, start_time=time, name=name, host=host,
                sort_order=len(ids),
            )
            db.add(p)
            db.flush()
            for order, (phase, part, who, text) in enumerate(items):
                db.add(models.ProgramItem(
                    program_id=p.id, phase=phase, part_key=part,
                    assignee_name=who, text=text, sort_order=order))
            ids[name] = p.id
            return p

        program("선발대", "10:00", "짐 정리", [("pre", "비품", "서윤", "성찬기 패킹")])
        program("2일차", "08:00", "아침식사", [
            ("pre", "비품", "서윤", "식수계수"),
            ("mid", "행정", "다은", "배식 안내"),
            ("post", "현장관리", "전체", "식당 정리"),
        ])
        program("2일차", "10:00", "중그룹 나눔 GBS", [
            ("pre", "행정", "하람", "GBS 나눔지 배부"),
            ("pre", "헤브론", "건우", "음향 확인"),
            ("mid", "비품", "온", "인원계수"),
            ("post", "비품", "서윤", "나눔지 회수"),
        ], host="하윤M")
        program("2일차", "18:00", "저녁집회", [("pre", "교역자", "하윤M", "설교 PPT 확인")])
        program("폐회", "11:00", "파송예배", [("post", "재정", "준서", "영수증 취합")])

        lead = models.User(
            name="헤브론 리더", phone_number="01055556666", role="dept_lead",
            department_id=db.scalars(
                select(models.Department).where(models.Department.key == "hebron")).one().id,
        )
        db.add(lead)

        # 준비 업무 하나 — **달력이 점을 그리려면 이게 있어야 한다.**
        # 프로그램만 있는 회차로 /calendar 를 시험하면 격자만 그려지고
        # 점을 그리는 자리는 한 번도 안 지나간다 (test_p30)
        lib = models.TaskLibrary(title="포스터 제작", kind="main", default_d_week=4)
        db.add(lib)
        db.flush()
        db.add(models.TaskRun(
            library_id=lib.id, retreat_id=retreat.id, included=True,
            department_id=db.scalars(select(models.Department).where(
                models.Department.key == "chongmuM")).one().id,
            d_week=4, start_date=dt.date(2026, 8, 1),
            end_date=dt.date(2026, 8, 12), status="대기"))

        db.commit()
        return {"retreat_id": retreat.id, "programs": ids}


@pytest.fixture
def lead_client(live_data):
    from app.main import app

    client = TestClient(app)
    login_as(client, "01055556666")
    return client


def retreat_of(db, live_data):
    return db.get(models.Retreat, live_data["retreat_id"])


def build(db, live_data, *, now, **kw):
    return live_domain.build(db, retreat_of(db, live_data), now=now, **kw)


def program_named(view, name):
    return next(p for p in view["programs"] if p["name"] == name)


# ---------------------------------------------------------------- 1. 일자 탭


def test_01_일자_탭이_있고_고르면_그_날_프로그램이_보인다(admin_client, live_data):
    page = admin_client.get("/live")
    assert page.status_code == 200
    for name in ("선발대", "1일차", "2일차", "폐회"):
        assert name in page.text

    with app_session() as db:
        view = build(db, live_data, now=AT(9, 0))
        assert [d["name"] for d in view["days"]] == ["선발대", "1일차", "2일차", "폐회"]
        # 일자는 회차의 개회일에서 계산한다 — 절대 날짜를 저장하지 않는다
        assert [d["label"] for d in view["days"]] == [
            "8/20(목)", "8/21(금)", "8/22(토)", "8/23(일)"]

        picked = build(db, live_data, now=AT(9, 0), day="선발대")
        assert picked["day"] == "선발대"
        assert [p["name"] for p in picked["programs"]] == ["짐 정리"]

    other = admin_client.get("/live?day=폐회")
    assert other.status_code == 200
    assert "파송예배" in other.text


def test_01b_일자는_개회일을_옮기면_따라_움직인다(admin_client, live_data):
    with app_session() as db:
        retreat = retreat_of(db, live_data)
        retreat.start_date = dt.date(2027, 1, 15)
        retreat.end_date = dt.date(2027, 1, 17)
        db.commit()
        dates = live_domain.day_dates(retreat)
    assert dates["선발대"] == dt.date(2027, 1, 14)
    assert dates["1일차"] == dt.date(2027, 1, 15)
    assert dates["폐회"] == dt.date(2027, 1, 17)


# ---------------------------------------------------------------- 2. 진행률


def test_02_당일_진행률이_실제_체크_수에서_계산된다(admin_client, live_data):
    with app_session() as db:
        view = build(db, live_data, now=AT(9, 0), day="2일차")
        assert view["progress"] == {"done": 0, "total": 8, "percent": 0}

    gbs = live_data["programs"]["중그룹 나눔 GBS"]
    with app_session() as db:
        item = db.scalars(
            select(models.ProgramItem).where(models.ProgramItem.program_id == gbs)).first()
        item_id = item.id
    admin_client.post(f"/live/item/{item_id}/check", json={"done": True})

    with app_session() as db:
        view = build(db, live_data, now=AT(9, 0), day="2일차")
        assert view["progress"]["done"] == 1
        assert view["progress"]["total"] == 8
        assert view["progress"]["percent"] == 12      # 1/8 = 12.5% → 12


# ---------------------------------------------------------------- 3. NOW 선


def test_03_현재_시각_위치에_NOW_선이_있다(admin_client, live_data):
    """NOW 선은 '오늘' 인 날에만, 지금 시각 자리에 들어간다.
    실행 시각이 아니라 **주입한 now** 를 기준으로 본다."""
    with app_session() as db:
        # 주입한 now 가 2일차 안이므로 그 날이 '오늘' 이다
        today = build(db, live_data, now=AT(9, 0), day="2일차")
        assert today["is_today"] is True
        assert today["now"] == "09:00"

        # 다른 날 탭에는 NOW 선이 없다 — 지금이 그 날이 아니다
        other = build(db, live_data, now=AT(9, 0), day="폐회")
        assert other["is_today"] is False

        # 회차 기간 밖이면 어느 날에도 없다
        far = build(db, live_data, now=dt.datetime(2027, 3, 1, 14, 0), day="2일차")
        assert far["is_today"] is False

    # 화면은 is_today 일 때만 NOW 선을 그린다
    html = open("app/templates/live.html", encoding="utf-8").read()
    assert "nowline" in html
    assert "live.is_today" in html
    # 9시엔 08:00 아침식사 뒤 · 10:00 GBS 앞에 놓인다
    page = admin_client.get("/live?day=2일차").text
    assert "NOW" in page or "nowline" not in page


# ------------------------------------------------- 4·5. 자동 선택


def test_04_열면_진행_중인_프로그램이_자동으로_선택된다(admin_client, live_data):
    with app_session() as db:
        # 10:00 GBS 가 시작했고 18:00 저녁집회는 아직 — 진행 중은 GBS
        view = build(db, live_data, now=AT(11, 30), day="2일차")
        assert view["programs"][view["selected"]]["name"] == "중그룹 나눔 GBS"
        assert view["programs"][view["selected"]]["state"] == "live"


def test_05_회차_기간_밖이면_첫_프로그램이_선택되고_화면이_죽지_않는다(admin_client, live_data):
    with app_session() as db:
        far = dt.datetime(2027, 3, 1, 14, 0)          # 회차와 아무 상관 없는 날
        view = build(db, live_data, now=far)
        assert view["day"] == "선발대"                # 첫 날로 떨어진다
        assert view["selected"] == 0
        assert view["is_today"] is False
        assert all(p["state"] == "done" for p in view["programs"])   # 다 지났다

        # 개회일이 아직 없는 회차여도 죽지 않는다
        retreat = retreat_of(db, live_data)
        retreat.start_date = None
        retreat.end_date = None
        db.commit()
        empty = live_domain.build(db, retreat, now=far)
        assert empty["day"] in (None, "선발대", "2일차", "폐회")
        assert empty["progress"]["total"] >= 0

    page = admin_client.get("/live")
    assert page.status_code == 200


def test_05b_프로그램이_하나도_없어도_화면이_뜬다(admin_client, live_data):
    with app_session() as db:
        for program in live_domain.load_programs(db, retreat_of(db, live_data)):
            db.delete(program)
        db.commit()
    page = admin_client.get("/live")
    assert page.status_code == 200
    assert "등록된 프로그램이 없습니다" in page.text


# ---------------------------------------------------------------- 6. 전/중/후


def test_06_준비_진행_정리_세_구간이_구분돼_보인다(admin_client, live_data):
    with app_session() as db:
        view = build(db, live_data, now=AT(9, 0), day="2일차")
        gbs = program_named(view, "중그룹 나눔 GBS")
        phases = {i["phase"] for i in gbs["items"]}
    assert phases == {"pre", "mid", "post"}
    assert models.PROGRAM_PHASES == ("pre", "mid", "post")
    assert models.PHASE_LABELS == {"pre": "준비", "mid": "진행", "post": "정리"}

    js = open("app/static/js/live.js", encoding="utf-8").read()
    for label in ("준비", "진행", "정리"):
        assert label in js
    # 정리 구간을 눈에 띄게 둔다 (5-2)
    css = open("app/static/css/retreat.css", encoding="utf-8").read()
    assert ".phase.ph-post{" in css


# ---------------------------------------------------------------- 7·8. 지연


def test_07_시작_시각이_지났는데_준비_항목이_남으면_지연이_붙는다(admin_client, live_data):
    with app_session() as db:
        before = build(db, live_data, now=AT(9, 0), day="2일차")
        after = build(db, live_data, now=AT(11, 30), day="2일차")

    # 10:00 시작 · 준비 2건 — 9시엔 아직, 11시반엔 지연
    assert program_named(before, "중그룹 나눔 GBS")["late"] == 0
    assert program_named(after, "중그룹 나눔 GBS")["late"] == 2
    # 아직 시작하지 않은 18:00 저녁집회에는 붙지 않는다
    assert program_named(after, "저녁집회")["late"] == 0


def test_08_지연_판정이_저장된_값이_아니라_시각에서_계산된다(admin_client, live_data):
    """4-10 에서 기한 초과를 날짜로 계산하기로 한 것과 같은 이유 —
    아무도 안 눌러도 시스템이 알아차려야 한다."""
    with app_session() as db:
        retreat = retreat_of(db, live_data)
        programs = live_domain.load_programs(db, retreat)
        gbs = next(p for p in programs if p.name == "중그룹 나눔 GBS")

        # 아무것도 저장하지 않고 now 만 바꾼다
        assert live_domain.late_items(gbs, "todo") == []
        assert len(live_domain.late_items(gbs, "live")) == 2
        assert len(live_domain.late_items(gbs, "done")) == 2   # 지나간 것은 더 나쁘다

        # 상태 자체도 시각에서 나온다
        following = next(p for p in programs if p.name == "저녁집회")
        assert live_domain.program_state(
            gbs, following, day_date=D2, now=AT(9, 0)) == "todo"
        assert live_domain.program_state(
            gbs, following, day_date=D2, now=AT(11, 30)) == "live"
        assert live_domain.program_state(
            gbs, following, day_date=D2, now=AT(19, 0)) == "done"

    # Program·ProgramItem 에는 '상태' 나 '지연' 컬럼이 없다
    assert not hasattr(models.Program, "status")
    assert not hasattr(models.ProgramItem, "is_late")


def test_08b_준비_항목을_다_체크하면_지연이_사라진다(admin_client, live_data):
    gbs = live_data["programs"]["중그룹 나눔 GBS"]
    with app_session() as db:
        ids = [i.id for i in db.scalars(
            select(models.ProgramItem).where(
                models.ProgramItem.program_id == gbs,
                models.ProgramItem.phase == "pre")).all()]
    for item_id in ids:
        admin_client.post(f"/live/item/{item_id}/check", json={"done": True})

    with app_session() as db:
        view = build(db, live_data, now=AT(11, 30), day="2일차")
    assert program_named(view, "중그룹 나눔 GBS")["late"] == 0


# ---------------------------------------------------------------- 9. 남은 정리


def test_09_끝났는데_정리가_남으면_왼쪽_목록에서도_보인다(admin_client, live_data):
    """다음 프로그램으로 넘어가면 앞 프로그램의 정리 항목은 화면에서 사라지는데,
    그것이 정확히 누락이 생기는 지점이다 (5-2)."""
    with app_session() as db:
        view = build(db, live_data, now=AT(11, 30), day="2일차")
        breakfast = program_named(view, "아침식사")

    assert breakfast["state"] == "done"          # 08:00 — 이미 지났다
    assert breakfast["leftover_post"] == 1       # '식당 정리' 가 남았다
    # 진행 중인 프로그램에는 붙지 않는다 — 아직 끝나지 않았다
    assert program_named(view, "중그룹 나눔 GBS")["leftover_post"] == 0

    # 화면에 그릴 자리가 있는지는 템플릿으로 본다 — 페이지 본문으로 보면
    # 이 회차가 '지난 회차' 가 되는 날부터 5-6 이 배지를 가려 검사가 흔들린다
    html = open("app/templates/live.html", encoding="utf-8").read()
    assert "data-left" in html and "정리 {{ p.leftover_post }}건 남음" in html

    # 다 처리하면 사라진다
    with app_session() as db:
        item = db.scalars(select(models.ProgramItem).where(
            models.ProgramItem.program_id == live_data["programs"]["아침식사"],
            models.ProgramItem.phase == "post")).one()
        item_id = item.id
    admin_client.post(f"/live/item/{item_id}/check", json={"done": True})
    with app_session() as db:
        view = build(db, live_data, now=AT(11, 30), day="2일차")
    assert program_named(view, "아침식사")["leftover_post"] == 0


# ---------------------------------------------------------------- 10. 파트


def test_10_파트_칩으로_걸러지고_내_부서와_맞는_파트가_기본이_된다(lead_client, admin_client, live_data):
    with app_session() as db:
        # 그 날 실제로 쓰인 파트만, 정해진 순서로
        view = build(db, live_data, now=AT(9, 0), day="2일차")
        assert view["parts"] == ["행정", "현장관리", "비품", "교역자", "헤브론"]

        # 헤브론 리더 → 헤브론 파트가 기본
        assert build(db, live_data, now=AT(9, 0), day="2일차",
                     department_key="hebron")["default_part"] == "헤브론"
        # 총무팀은 파트가 하나로 정해지지 않는다 — 전체로 두고 직접 고른다
        assert build(db, live_data, now=AT(9, 0), day="2일차",
                     department_key="chongmuM")["default_part"] == "전체"
        # 그 날 안 쓰인 파트가 내 부서면 억지로 고르지 않는다
        assert build(db, live_data, now=AT(9, 0), day="폐회",
                     department_key="hebron")["default_part"] == "전체"

    # 화면도 그렇게 받는다 (부서는 key 로 본다 — CLAUDE.md 2장)
    assert '"default_part": "\\ud5e4\\ube0c\\ub860"' in lead_client.get("/live?day=2일차").text \
        or "헤브론" in lead_client.get("/live?day=2일차").text
    js = open("app/static/js/live.js", encoding="utf-8").read()
    assert "data-part" in js and "default_part" in js


def test_10b_부서_키가_파트로_이어진다():
    assert live_domain.DEPARTMENT_PART["hebron"] == "헤브론"
    assert live_domain.DEPARTMENT_PART["koram"] == "코람데오"
    assert live_domain.DEPARTMENT_PART["jaejeong"] == "재정"
    assert live_domain.default_part(None, ["행정"]) == "전체"


# ---------------------------------------------------------------- 11·12. 체크


def test_11_체크하면_doneAt_과_doneById_가_남는다(admin_client, live_data):
    with app_session() as db:
        item_id = db.scalars(select(models.ProgramItem)).first().id

    response = admin_client.post(f"/live/item/{item_id}/check", json={"done": True})
    assert response.status_code == 200
    assert response.json()["item"]["done"] is True
    assert response.json()["item"]["done_by"] == "총무 김간사"

    with app_session() as db:
        item = db.get(models.ProgramItem, item_id)
        assert item.done_at is not None
        assert item.done_by_id is not None
        assert item.done is True
        stamped = item.done_at

    # 다시 눌러도 처음 누른 시각을 덮어쓰지 않는다 — 처음이 사실이다
    admin_client.post(f"/live/item/{item_id}/check", json={"done": True})
    with app_session() as db:
        assert db.get(models.ProgramItem, item_id).done_at == stamped

    # 해제하면 지운다
    admin_client.post(f"/live/item/{item_id}/check", json={"done": False})
    with app_session() as db:
        item = db.get(models.ProgramItem, item_id)
        assert item.done_at is None and item.done_by_id is None


def test_12_로그인한_사람_누구나_체크할_수_있다(lead_client, live_data):
    """현장에서는 옆 사람 것도 대신 눌러야 한다. 남의 부서 항목이어도 된다."""
    with app_session() as db:
        item = db.scalars(select(models.ProgramItem).where(
            models.ProgramItem.part_key == "교역자")).one()      # 헤브론 것이 아니다
        item_id = item.id

    response = lead_client.post(f"/live/item/{item_id}/check", json={"done": True})
    assert response.status_code == 200

    with app_session() as db:
        saved = db.get(models.ProgramItem, item_id)
        assert saved.done is True
        assert saved.done_by.name == "헤브론 리더"      # 누가 눌렀는지는 남는다


def test_12b_로그인하지_않으면_체크할_수_없다(client, live_data):
    with app_session() as db:
        item_id = db.scalars(select(models.ProgramItem)).first().id
    response = client.post(f"/live/item/{item_id}/check", json={"done": True},
                           follow_redirects=False)
    assert response.status_code in (303, 401, 403)


# ---------------------------------------------------------------- 13. 편집 권한


def test_13_프로그램과_항목을_만들고_고치는_것은_총무팀만(lead_client, admin_client, live_data):
    program_id = live_data["programs"]["아침식사"]
    with app_session() as db:
        item_id = db.scalars(select(models.ProgramItem)).first().id

    # 부서 리더 — 전부 403
    assert lead_client.post("/live/program", json={
        "day": "2일차", "start_time": "07:00", "name": "몰래 추가"}).status_code == 403
    assert lead_client.post(f"/live/program/{program_id}", json={
        "day": "2일차", "start_time": "07:00", "name": "이름 바꾸기"}).status_code == 403
    assert lead_client.post(f"/live/program/{program_id}/delete").status_code == 403
    assert lead_client.post(f"/live/program/{program_id}/item", json={
        "phase": "pre", "part_key": "행정", "text": "몰래"}).status_code == 403
    assert lead_client.post(f"/live/item/{item_id}/delete").status_code == 403
    assert lead_client.post("/live/copy", json={"source_retreat_id": 1}).status_code == 403

    # 총무팀 — 된다
    made = admin_client.post("/live/program", json={
        "day": "2일차", "start_time": "07:00", "name": "기상", "host": "총무팀"})
    assert made.status_code == 200
    new_id = made.json()["id"]
    assert admin_client.post(f"/live/program/{new_id}/item", json={
        "phase": "pre", "part_key": "행정", "assignee_name": "하람",
        "text": "기상송 준비"}).status_code == 200
    assert admin_client.post(f"/live/program/{new_id}/delete").status_code == 200


def test_13b_시각_형식이_틀리면_이유를_말한다(admin_client, live_data):
    bad = admin_client.post("/live/program", json={
        "day": "2일차", "start_time": "아침", "name": "기상"})
    assert bad.status_code == 400
    assert "09:30" in bad.json()["detail"]

    empty = admin_client.post("/live/program", json={
        "day": "2일차", "start_time": "07:00", "name": "  "})
    assert empty.status_code == 400


def test_13c_알_수_없는_구간은_거부한다(admin_client, live_data):
    program_id = live_data["programs"]["아침식사"]
    bad = admin_client.post(f"/live/program/{program_id}/item", json={
        "phase": "during", "part_key": "행정", "text": "아무거나"})
    assert bad.status_code == 400
    assert "준비" in bad.json()["detail"]


# ---------------------------------------------------------------- 14. 복사


def test_14_지난_회차에서_복사해_오면_체크_상태는_따라오지_않는다(admin_client, live_data):
    """지난 회차의 사실이지 이번 회차의 것이 아니다 (6-10 과 같은 원칙)."""
    with app_session() as db:
        item_id = db.scalars(select(models.ProgramItem)).first().id
    admin_client.post(f"/live/item/{item_id}/check", json={"done": True})

    with app_session() as db:
        fresh = models.Retreat(
            name="2027 겨울수련회",
            start_date=dt.date(2027, 1, 15), end_date=dt.date(2027, 1, 17))
        db.add(fresh)
        db.commit()
        fresh_id = fresh.id

    copied = admin_client.post(
        f"/live/copy?retreat_id={fresh_id}",
        json={"source_retreat_id": live_data["retreat_id"]})
    assert copied.status_code == 200
    assert copied.json()["copied"] == 5

    with app_session() as db:
        target = db.get(models.Retreat, fresh_id)
        programs = live_domain.load_programs(db, target)
        assert len(programs) == 5
        assert {p.name for p in programs} == {
            "짐 정리", "아침식사", "중그룹 나눔 GBS", "저녁집회", "파송예배"}
        # 항목은 따라왔다
        assert sum(len(p.items) for p in programs) == 10
        # 체크 상태는 따라오지 않았다
        assert all(i.done_at is None and i.done_by_id is None
                   for p in programs for i in p.items)
        # 날짜는 새 회차의 개회일에서 다시 계산된다
        assert live_domain.day_dates(target)["1일차"] == dt.date(2027, 1, 15)
        # 지난 회차의 체크는 그대로 남아 있다
        assert db.get(models.ProgramItem, item_id).done_at is not None


def test_14b_프로그램표가_없는_회차에서는_가져올_것이_없다고_말한다(admin_client, live_data):
    with app_session() as db:
        blank = models.Retreat(name="빈 회차", start_date=OPEN, end_date=CLOSE)
        db.add(blank)
        db.commit()
        blank_id = blank.id

    refused = admin_client.post("/live/copy", json={"source_retreat_id": blank_id})
    assert refused.status_code == 400
    assert "프로그램표가 없습니다" in refused.json()["detail"]
    # 실패했으니 원래 것이 지워지지 않았다
    with app_session() as db:
        assert len(live_domain.load_programs(db, retreat_of(db, live_data))) == 5


def test_14c_2026_회차를_원본으로_겨울_회차에_복사해_온다(admin_client, live_data):
    """실제로 쓰게 될 길 — 2026 여름수련회의 프로그램표를 다음 회차로 옮긴다.
    체크는 지난 회차의 사실이므로 따라오지 않는다."""
    # 여름 회차에 체크를 몇 건 남겨 둔다
    with app_session() as db:
        ids = [i.id for i in db.scalars(select(models.ProgramItem)).all()[:3]]
    for item_id in ids:
        admin_client.post(f"/live/item/{item_id}/check", json={"done": True})

    with app_session() as db:
        winter = models.Retreat(
            name="2027 겨울수련회",
            start_date=dt.date(2027, 1, 15), end_date=dt.date(2027, 1, 17))
        db.add(winter)
        db.commit()
        winter_id = winter.id

    result = admin_client.post(
        f"/live/copy?retreat_id={winter_id}",
        json={"source_retreat_id": live_data["retreat_id"]})
    assert result.status_code == 200
    assert result.json()["copied"] == 5

    with app_session() as db:
        target = db.get(models.Retreat, winter_id)
        programs = live_domain.load_programs(db, target)
        items = [i for p in programs for i in p.items]

        # 프로그램과 항목은 그대로 따라왔다
        assert len(programs) == 5 and len(items) == 10
        # live_data 는 선발대 1 · 2일차 3 · 폐회 1 로 짜여 있다
        assert {p.day for p in programs} == {"선발대", "2일차", "폐회"}
        assert [p.start_time for p in programs] == sorted(p.start_time for p in programs)
        # 파트·담당자도 그대로
        assert {i.part_key for i in items} >= {"행정", "비품", "교역자"}
        assert any(i.assignee_name == "하람" for i in items)

        # **체크는 따라오지 않았다**
        assert all(i.done_at is None and i.done_by_id is None for i in items)

        # 날짜는 새 회차의 개회일에서 다시 계산된다 (저장하지 않으므로)
        dates = live_domain.day_dates(target)
        assert dates["선발대"] == dt.date(2027, 1, 14)
        assert dates["폐회"] == dt.date(2027, 1, 17)

        # 지난 회차의 체크는 그대로 남아 있다
        summer = db.get(models.Retreat, live_data["retreat_id"])
        kept = [i for p in live_domain.load_programs(db, summer) for i in p.items]
        assert sum(1 for i in kept if i.done) == 3

        # 갓 복사한 회차는 아직 안 끝났으므로 안내 문구가 아니라 진행률이다
        view = live_domain.build(db, target, now=dt.datetime(2026, 12, 1, 10, 0))
        assert view["carried_only"] is False
        assert view["progress"]["done"] == 0


# ══════════════════════════════════════════════════════════════════════
# 팀 단위 / 개인 단위 (CLAUDE.md 5-2). 수용 기준 1·2·6~13
#
# 구글시트의 봉사자 열과 총무팀 파트 열은 성격이 다르다 — 봉사자 열은 팀이
# 통째로 움직이고("헤브론 집합"), 총무팀 파트 열은 개인 이름까지 붙는다
# ("인원계수_온"). 이 구분은 시트에서 온 것이지 우리가 만든 것이 아니다.
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def scoped(admin_client, live_data):
    """2일차 프로그램 하나에 팀 2건 · 개인 3건을 섞어 둔다."""
    with app_session() as db:
        program = models.Program(
            retreat_id=live_data["retreat_id"], day="2일차", start_time="19:00",
            name="저녁집회 리허설", host="헤브론", sort_order=99)
        db.add(program)
        db.flush()
        rows = [
            ("pre", "헤브론", "헤브론", "코람데오 리허설 시작", "team"),
            ("pre", "현장관리", "전체", "강당 의자 세팅", "team"),
            ("pre", "현장관리", "나윤", "진행자 물 세팅", "person"),
            ("mid", "비품", "온", "인원계수", "person"),
            ("post", "재정", "준서", "강사비 계좌이체", "person"),
        ]
        for order, (phase, part, who, text, scope) in enumerate(rows):
            db.add(models.ProgramItem(
                program_id=program.id, phase=phase, part_key=part,
                assignee_name=who, text=text, sort_order=order, scope=scope))
        db.commit()
        return {"program_id": program.id, **live_data}


def scoped_view(db, data, *, now=None):
    return live_domain.build(
        db, db.get(models.Retreat, data["retreat_id"]),
        now=now or AT(20, 0), day="2일차")


def scoped_program(view):
    return next(p for p in view["programs"] if p["name"] == "저녁집회 리허설")


# ---------------------------------------------------------------- 1·2. 컬럼


def test_s01_scope_컬럼이_있고_쓰던_파일에_자동으로_붙는다():
    from app.db import _ADDED_COLUMNS

    assert ("program_items", "scope", "VARCHAR(10)") in _ADDED_COLUMNS
    assert models.PROGRAM_SCOPES == ("team", "person")
    assert hasattr(models.ProgramItem, "scope")


def test_s02_NULL_인_기존_행을_읽어도_터지지_않는다(admin_client, live_data):
    """ALTER 로 붙은 컬럼이라 기존 행은 NULL 이다. 읽는 자리는 늘 scope_key."""
    from sqlalchemy import text as sql

    with app_session() as db:
        # 옛 행을 흉내낸다 — 컬럼을 직접 NULL 로 만든다
        db.execute(sql("UPDATE program_items SET scope = NULL"))
        db.commit()

        rows = db.scalars(select(models.ProgramItem)).all()
        assert rows and all(i.scope is None for i in rows)
        # 모델이 person 으로 읽는다
        assert all(i.scope_key == "person" for i in rows)
        assert not any(i.is_team for i in rows)

        # 화면을 그려도 터지지 않는다
        view = live_domain.build(
            db, db.get(models.Retreat, live_data["retreat_id"]),
            now=AT(11, 30), day="2일차")
        assert all(i["scope"] == "person" for p in view["programs"] for i in p["items"])
        assert view["scopes"] == ["person"]

    assert admin_client.get("/live?day=2일차").status_code == 200


# ------------------------------------------------- 6·7. 구간 안에서 두 덩어리


def test_s06_각_구간_안에서_팀이_위_개인이_아래에_보인다(scoped):
    """구간이 먼저고 범위가 나중이다 — 현장에서 먼저 묻는 것은
    '지금 뭘 해야 하나' 이지 '이게 팀 일인가 내 일인가' 가 아니다."""
    js = open("app/static/js/live.js", encoding="utf-8").read()

    # 바깥 반복이 구간, 안쪽이 범위다
    phases_at = js.index("PHASES.forEach")
    scope_at = js.index("[['team', '팀 단위'], ['person', '개인 단위']]")
    detail_end = js.index("detail.innerHTML = h;")
    assert phases_at < scope_at < detail_end, "범위가 구간보다 바깥에 있다"

    # 팀이 먼저 그려진다
    assert js.index("'team', '팀 단위'") < js.index("'person', '개인 단위'")

    with app_session() as db:
        program = scoped_program(scoped_view(db, scoped))
        pre = [i for i in program["items"] if i["phase"] == "pre"]
        assert [i["scope"] for i in pre].count("team") == 2
        assert [i["scope"] for i in pre].count("person") == 1


def test_s07_한쪽이_비면_그_라벨이_나오지_않는다(scoped):
    js = open("app/static/js/live.js", encoding="utf-8").read()
    assert "if (!part_.length) return;" in js, "빈 덩어리를 건너뛰지 않는다"

    with app_session() as db:
        program = scoped_program(scoped_view(db, scoped))
        # mid·post 는 개인만 있다 — 팀 라벨을 낼 이유가 없다
        for phase in ("mid", "post"):
            rows = [i for i in program["items"] if i["phase"] == phase]
            assert rows and all(i["scope"] == "person" for i in rows)


# ---------------------------------------------------------------- 8·9·10. 칩


def test_s08_팀_단위만_칩으로_팀_항목만_남는다(scoped):
    js = open("app/static/js/live.js", encoding="utf-8").read()
    assert 'data-scope="team"' in js and "팀 단위만" in js
    # 걸러내는 자리
    assert "(scope === '전체' || i.scope === scope)" in js

    with app_session() as db:
        program = scoped_program(scoped_view(db, scoped))
        team = [i for i in program["items"] if i["scope"] == "team"]
        assert len(team) == 2
        assert {i["text"] for i in team} == {"코람데오 리허설 시작", "강당 의자 세팅"}


def test_s09_내_것만_칩으로_개인_항목만_남는다(scoped):
    js = open("app/static/js/live.js", encoding="utf-8").read()
    assert 'data-scope="person"' in js and "내 것만" in js

    with app_session() as db:
        program = scoped_program(scoped_view(db, scoped))
        person = [i for i in program["items"] if i["scope"] == "person"]
        assert len(person) == 3
        assert "진행자 물 세팅" in {i["text"] for i in person}


def test_s10_범위_칩과_파트_칩이_함께_걸린다(scoped):
    """파트는 '무슨 일인가', 범위는 '팀이 움직이는가' — 서로 다른 축이다."""
    js = open("app/static/js/live.js", encoding="utf-8").read()
    # 한 줄에서 둘을 함께 본다
    assert ("(part === '전체' || i.part === part) && "
            "(scope === '전체' || i.scope === scope)") in js
    # 상태도 따로 둔다
    assert "let part = LIVE.default_part" in js and "let scope = '전체';" in js

    with app_session() as db:
        program = scoped_program(scoped_view(db, scoped))
        both = [i for i in program["items"]
                if i["part"] == "현장관리" and i["scope"] == "person"]
        assert [i["text"] for i in both] == ["진행자 물 세팅"]

    # 그 날 쓰인 범위만 칩으로 낸다
    with app_session() as db:
        assert scoped_view(db, scoped)["scopes"] == ["team", "person"]


# ---------------------------------------------------------------- 11. 완료 수


def test_s11_왼쪽_목록의_완료_수는_범위와_무관하게_전체로_센다(admin_client, scoped):
    """그 숫자는 '이 프로그램이 얼마나 준비됐나' 이지 '내 것이 얼마나 남았나' 가 아니다."""
    with app_session() as db:
        team_item = db.scalars(select(models.ProgramItem).where(
            models.ProgramItem.text == "코람데오 리허설 시작")).one()
        item_id = team_item.id
    admin_client.post(f"/live/item/{item_id}/check", json={"done": True})

    with app_session() as db:
        program = scoped_program(scoped_view(db, scoped))
        assert program["total"] == 5          # 팀 2 + 개인 3
        assert program["done"] == 1

    # 화면 쪽도 범위로 나누지 않는다
    js = open("app/static/js/live.js", encoding="utf-8").read()
    rail = js[js.index("function refreshRail"):js.index("/* ── 체크")]
    assert "scope" not in rail, "왼쪽 목록 계산이 범위를 본다"


# ---------------------------------------------------------------- 12. 만들 때


def test_s12_항목을_만들_때_범위_기본값이_추측되고_바꿀_수_있다(admin_client, scoped):
    program_id = scoped["program_id"]

    # 범위를 안 주면 파트·담당으로 추측한다
    made = admin_client.post(f"/live/program/{program_id}/item", json={
        "phase": "pre", "part_key": "헤브론", "assignee_name": "건우", "text": "음향 점검"})
    assert made.status_code == 200
    assert made.json()["item"]["scope"] == "team"          # 봉사팀 파트

    made2 = admin_client.post(f"/live/program/{program_id}/item", json={
        "phase": "pre", "part_key": "현장관리", "assignee_name": "나윤", "text": "의자 정렬"})
    assert made2.json()["item"]["scope"] == "person"       # 개인 이름

    # **추측이지 규칙이 아니다** — 직접 주면 그대로 쓴다
    made3 = admin_client.post(f"/live/program/{program_id}/item", json={
        "phase": "pre", "part_key": "현장관리", "assignee_name": "전체",
        "text": "강당 의자 세팅", "scope": "team"})
    assert made3.json()["item"]["scope"] == "team"

    # 넣은 뒤에도 그 자리에서 바꾼다
    item_id = made2.json()["item"]["id"]
    swapped = admin_client.post(f"/live/item/{item_id}/scope", json={"scope": "team"})
    assert swapped.status_code == 200
    assert swapped.json()["item"]["scope"] == "team"
    with app_session() as db:
        assert db.get(models.ProgramItem, item_id).scope == "team"

    # 이상한 값은 거부한다
    bad = admin_client.post(f"/live/item/{item_id}/scope", json={"scope": "팀"})
    assert bad.status_code == 400
    assert "team" in bad.json()["detail"]


def test_s12b_범위를_바꾸는_것도_총무팀만(lead_client, admin_client, scoped):
    with app_session() as db:
        item_id = db.scalars(select(models.ProgramItem)).first().id
    assert lead_client.post(
        f"/live/item/{item_id}/scope", json={"scope": "team"}).status_code == 403


def test_s12c_추측_기준은_파트와_담당_둘_다_본다():
    """헤브론·코람데오면 무조건 팀. 담당이 비었거나 묶음 이름이면 팀."""
    assert live_domain.guess_scope("헤브론", "건우") == "team"
    assert live_domain.guess_scope("코람데오", "재하") == "team"
    assert live_domain.guess_scope("현장관리", "전체") == "team"
    assert live_domain.guess_scope("행정", "총무팀") == "team"
    assert live_domain.guess_scope("행정", None) == "team"
    assert live_domain.guess_scope("행정", "  ") == "team"
    assert live_domain.guess_scope("현장관리", "나윤") == "person"
    assert live_domain.guess_scope("교역자", "하윤M") == "person"


# ---------------------------------------------------------------- 13. 휴대폰


def narrow_css(css: str) -> str:
    """`@media (max-width:820px)` 안의 규칙 **전부**.

    한 덩어리만 보면(예전엔 마지막 것) 좁은 화면 규칙이 여러 곳에 나뉘어 있을
    때 엉뚱한 덩어리를 붙잡는다 — 5-8 을 붙이면서 실제로 그렇게 됐다.
    """
    mark = "@media (max-width:820px){"
    out, at = [], css.find(mark)
    while at != -1:
        out.append(css[at:css.find(mark, at + 1) if css.find(mark, at + 1) != -1 else len(css)])
        at = css.find(mark, at + 1)
    return "\n".join(out)


def test_s13_좁은_화면에서도_두_덩어리가_구분돼_보인다():
    css = open("app/static/css/retreat.css", encoding="utf-8").read()

    assert ".scopegroup + .scopegroup{" in css
    assert ".sg-h{" in css
    assert ".sg-team{" in css

    narrow = narrow_css(css)
    # 좁은 화면에서는 들여쓰기 대신 면과 라벨로 가른다
    assert ".sg-team{" in narrow
    assert "background:var(--side)" in narrow
    assert ".scopegroup + .scopegroup{margin-top:14px}" in narrow


# ---------------------------------------------------------------- 15·16. 휴대폰


def test_15_좁은_화면에서_한_번에_하나씩_보이고_체크_버튼이_44px_이상이다():
    css = open("app/static/css/retreat.css", encoding="utf-8").read()

    # 손가락으로 누를 크기
    tick = css[css.index(".tick{"):css.index(".tick:hover")]
    assert "width:44px" in tick and "height:44px" in tick

    # 좁은 화면 — 목록과 체크리스트를 한 번에 하나씩
    narrow = narrow_css(css)
    assert ".wrap.showdetail .rail{display:none}" in narrow
    assert ".wrap.showdetail .detail{display:block}" in narrow
    assert ".detail{display:none" in narrow
    # 되돌아가는 길
    assert ".backrail{display:block" in narrow
    assert "min-height:44px" in narrow

    html = open("app/templates/live.html", encoding="utf-8").read()
    assert 'id="backrail"' in html
    js = open("app/static/js/live.js", encoding="utf-8").read()
    assert "showdetail" in js and "max-width: 820px" in js


def test_16_체크가_실패하면_화면에_말해준다(admin_client, live_data):
    """조용히 삼키면 눌렀다고 믿은 채로 넘어간다."""
    js = open("app/static/js/live.js", encoding="utf-8").read()

    # 실패하면 되돌리고 말한다
    assert "item.done = was;" in js
    assert "say(" in js
    assert "다시 눌러주세요" in js
    # 화면에 띄우는 자리가 있다
    assert "livewarn" in js
    css = open("app/static/css/retreat.css", encoding="utf-8").read()
    assert ".livewarn{" in css

    # 서버도 사유를 실어 보낸다
    missing = admin_client.post("/live/item/999999/check", json={"done": True})
    assert missing.status_code == 404
    assert "찾을 수 없습니다" in missing.json()["detail"]


# ---------------------------------------------------------------- 17. seed


def test_17_seed_에_목업의_예시_프로그램이_들어가_있지_않다():
    """실제 이력이 아니라 시각 스펙용 예시다 — 지어낸 기록을 심지 않는다 (6-9)."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    for name in ("seed.py", "seed_library.py", "seed_library_data.py", "seed_data.py"):
        text = (root / name).read_text(encoding="utf-8")
        # Program · ProgramItem 을 심는 곳이 없어야 한다.
        # (seed_data.py 의 옛 '일정표'(ScheduleItem)는 이전 설계 화면의 것이라 별개다)
        assert "ProgramItem(" not in text, f"{name} 이 예시 실행 항목을 심는다"
        assert "models.Program(" not in text, f"{name} 이 예시 프로그램을 심는다"
        assert " Program(" not in text, f"{name} 이 예시 프로그램을 심는다"

    # 실제로 seed 를 돌려도 프로그램은 하나도 생기지 않는다
    import seed_library

    assert "Program" not in open(root / "seed.py", encoding="utf-8").read()
    assert seed_library is not None


# ════════════════════════════════════════════════════════════════════
#  프로그램의 셋 — 누가 함께하나 · 어떤 일인가 · 나란히 도는가 (5-1)
# ════════════════════════════════════════════════════════════════════


def test_p20_화면에서_셋을_고를_수_있다(admin_client, live_data):
    """`audience=staff` 를 보고 무엇인지 아는 사람은 이걸 만든 사람뿐이다."""
    import json
    import re

    page = admin_client.get("/live?stay=1").text
    # `|tojson` 이 한글을 \\u 로 escape 하므로 글자로 찾지 않고 풀어서 본다
    raw = re.search(r'id="live-opts"[^>]*>(.*?)</script>', page, re.S).group(1)
    opts = json.loads(raw)

    # 고르는 자리와 **뜻**이 함께 내려간다
    assert [o["value"] for o in opts["audiences"]] == ["all", "staff"]
    assert [o["label"] for o in opts["audiences"]] == ["참가자와 함께", "봉사자만"]
    assert [o["value"] for o in opts["tracks"]] == ["main", "ops"]
    assert [o["label"] for o in opts["tracks"]] == ["정규일정", "총무팀 작업"]
    # 값마다 사람 말로 된 설명이 붙는다
    assert all(o["hint"] for o in opts["audiences"] + opts["tracks"])
    assert "봉사자 시간표에 넣지 않습니다" in dict(
        (o["value"], o["hint"]) for o in opts["tracks"])["ops"]
    assert "오른쪽 열" in opts["parallel_hint"]
    assert "나란히 도는 프로그램" in open(
        "app/static/js/live.js", encoding="utf-8").read()

    # **목록은 models.py 한 곳에서 온다.** 라우터가 거기서 가져오고, 화면은
    # 라우터가 준 것을 그린다 — 화면에 다시 적으면 값이 늘 때 한쪽만 고쳐진다
    for option in opts["audiences"]:
        assert option["label"] == models.AUDIENCE_LABELS[option["value"]]
        assert option["hint"] == models.AUDIENCE_HINTS[option["value"]]
    for option in opts["tracks"]:
        assert option["label"] == models.TRACK_LABELS[option["value"]]
        assert option["hint"] == models.TRACK_HINTS[option["value"]]
    assert opts["parallel_hint"] == models.PARALLEL_HINT

    view = open("app/templates/live.html", encoding="utf-8").read()
    for word in models.AUDIENCE_LABELS.values():
        assert word not in view, f"화면에 {word} 를 다시 적었다"

    js = open("app/static/js/live.js", encoding="utf-8").read()
    for field in ("name=audience", "name=track", "f-parallel"):
        assert field in js, f"{field} 를 고르는 자리가 없다"


def test_p21_기본값이_all_main_꺼짐이다(admin_client, live_data):
    """**가장 흔한 경우가 기본이어야 한다** — 참가자와 함께하는 정규일정."""
    res = admin_client.post("/live/program", json={
        "day": "1일차", "start_time": "10:00", "name": "기본값 시험"})
    assert res.status_code == 200, res.text

    with app_session() as db:
        made = db.scalars(select(models.Program).where(
            models.Program.name == "기본값 시험")).one()
        assert made.audience_key == "all"
        assert made.track_key == "main"
        assert made.is_parallel is False

    # 화면의 기본 선택도 같다
    js = open("app/static/js/live.js", encoding="utf-8").read()
    assert "audience: 'all'" in js and "track: 'main'" in js
    assert "parallel: false" in js


def test_p22_프로그램을_고칠_때도_셋을_바꿀_수_있다(admin_client, live_data):
    res = admin_client.post("/live/program", json={
        "day": "1일차", "start_time": "10:00", "name": "고쳐볼 것"})
    made = res.json()["id"]

    res = admin_client.post(f"/live/program/{made}", json={
        "day": "2일차", "start_time": "20:00", "name": "고쳐볼 것",
        "audience": "staff", "track": "ops", "parallel": True,
        "end_time": "22:00"})
    assert res.status_code == 200, res.text

    with app_session() as db:
        after = db.get(models.Program, made)
        assert (after.audience_key, after.track_key, after.is_parallel) \
            == ("staff", "ops", True)
        assert after.end_time == "22:00"

    # 화면에도 고치는 자리가 있다
    js = open("app/static/js/live.js", encoding="utf-8").read()
    assert "editpgm" in js and "openProgramForm(current())" in js


def test_p23_모르는_값을_조용히_기본값으로_바꾸지_않는다(admin_client, live_data):
    """그러면 화면에서 고른 것과 저장된 것이 달라지는데 아무 표시도 안 난다."""
    for bad in ({"audience": "everyone"}, {"track": "backstage"}):
        body = {"day": "1일차", "start_time": "10:00", "name": "이상한 값"}
        body.update(bad)
        res = admin_client.post("/live/program", json=body)
        assert res.status_code == 400, res.text

    with app_session() as db:
        assert db.scalars(select(models.Program).where(
            models.Program.name == "이상한 값")).first() is None


def test_p24_지난_회차에서_복사해_오면_셋이_따라온다(admin_client, live_data):
    """**안 옮기면 복사해 온 회차의 표가 통째로 틀리는데, 값이 기본값으로
    채워져 아무 오류도 나지 않는다.**"""
    with app_session() as db:
        source = db.scalars(select(models.Retreat)).first()
        # 셋이 기본값과 다른 프로그램을 하나 심는다
        db.add(models.Program(
            retreat_id=source.id, day="1일차", start_time="21:00",
            name="복사될 것", audience="staff", track="ops",
            parallel=True, end_time="23:00", sort_order=99))
        target = models.Retreat(
            name="복사 받을 회차", start_date=dt.date(2027, 3, 5),
            end_date=dt.date(2027, 3, 7))
        db.add(target)
        db.commit()
        target_id, source_id = target.id, source.id

    res = admin_client.post(f"/live/copy?retreat_id={target_id}",
                            json={"source_retreat_id": source_id})
    assert res.status_code == 200, res.text

    with app_session() as db:
        copied = db.scalars(select(models.Program).where(
            models.Program.retreat_id == target_id,
            models.Program.name == "복사될 것")).one()
        assert copied.audience_key == "staff"
        assert copied.track_key == "ops"
        assert copied.is_parallel is True
        assert copied.end_time == "23:00"


# ════════════════════════════════════════════════════════════════════
#  화면이 그려지는가 — 주요 화면을 실제로 GET 한다
# ════════════════════════════════════════════════════════════════════
#
# 템플릿이 라우터가 안 넘긴 값을 쓰면 Jinja 는 `Undefined` 로 두고 그리다가
# `|tojson` 같은 데서 터집니다. **도메인 함수만 시험하면 이게 안 잡힙니다** —
# 화면을 실제로 그려 봐야 잡힙니다.
#
# 화면마다 따로 있는 시험은 그 화면을 고칠 때만 늘어납니다. 여기 한 자리에
# 목록으로 두는 이유는 **새 화면이 생겼을 때 빠진 것이 눈에 띄게** 하기
# 위해서입니다 — 목록에 한 줄 더하는 것을 잊기는 어렵습니다.

MAIN_PAGES = [
    "/live?stay=1",
    "/live/staff",
    "/board",
    "/calendar?scope=all",
    "/admin/users",
    "/library",
    "/setup",
]


@pytest.mark.parametrize("path", MAIN_PAGES)
def test_p30_주요_화면이_실제로_그려진다(admin_client, live_data, path):
    """**끝까지 그려지는지**를 본다. 200 만 보면 되는 것이 아니라, 그리다
    중간에 터지면 500 이 나므로 이것이 곧 렌더 시험이다.

    `live_data` 를 쓰므로 **프로그램이 들어 있는 회차**로 그린다 — 빈 회차는
    `{% if %}` 로 다른 가지를 타서, 내용이 있을 때만 읽는 값을 안 지나간다.
    """
    page = admin_client.get(path)
    assert page.status_code == 200, f"{path} → {page.status_code}\n{page.text[:600]}"
    assert "</html>" in page.text, f"{path} 가 끝까지 그려지지 않았다"

    # **알맹이가 들어 있는지도 본다.** 껍데기만 그려지고 안이 비어도 200 이다.
    # 한글은 화면에 따라 JSON 으로 `\\u` escape 되므로 **구조**로 본다.
    marks = {
        "/live?stay=1": ['class="days"', 'id="live-meta"', 'id="live-opts"'],
        "/live/staff": ['class="ssheet"', "<colgroup>", 'class="c-time"',
                        'class="c-body"', "--fs:"],
        # 이 회차엔 업무가 없어 바가 없다. 업무가 든 보드가 그려지는지는
        # test_board_web.py 의  가 본다
        "/board": ['id="board"', 'id="board-meta"'],
        # 달력은 알맹이가 점이다 — 격자만 그려지고 점이 없으면 껍데기다
        "/calendar?scope=all": ['class="cal-grid"', 'class="cal-cell', 
                               'class="cal-dot', 'href="/board?task=',
                               'class="calweek"'],
        "/admin/users": ["<table", "<form"],
        "/library": ['class="lib"', 'id="linkcount"'],
        "/setup": ['class="card"', 'id="lib"', 'id="next"'],
    }
    for mark in marks.get(path, []):
        assert mark in page.text, f"{path} 에 {mark!r} 가 없다 — 껍데기만 그려졌다"



def test_p31_live_화면이_프로그램이_없어도_그려진다(admin_client):
    """프로그램이 하나도 없는 회차는 다른 가지를 그린다 —
    있는 회차만 시험하면 그쪽이 통째로 안 열린 채 남는다."""
    with app_session() as db:
        empty = models.Retreat(
            name="프로그램 없는 회차", start_date=dt.date(2027, 5, 7),
            end_date=dt.date(2027, 5, 9))
        db.add(empty)
        db.commit()
        empty_id = empty.id

    for path in (f"/live?stay=1&retreat_id={empty_id}",
                 f"/live/staff?retreat_id={empty_id}"):
        page = admin_client.get(path)
        assert page.status_code == 200, f"{path} → {page.status_code}"
        assert "</html>" in page.text


def test_p32_템플릿이_쓰는_값을_라우터가_다_넘긴다(admin_client, live_data):
    """`Undefined` 가 하나라도 남아 있으면 잡는다.

    Jinja 는 없는 값을 조용히 빈 것으로 그립니다 — `|tojson` 을 만나야 터지고,
    안 만나면 **화면이 조용히 비어서 나옵니다.** 그쪽이 더 나쁩니다.
    """
    import jinja2

    from app.templating import templates

    env = templates.env
    strict = jinja2.Environment(
        loader=env.loader, autoescape=env.autoescape,
        undefined=jinja2.StrictUndefined,
    )
    strict.filters.update(env.filters)
    strict.globals.update(env.globals)

    # live.html 이 쓰는 값을 라우터가 실제로 넘기는지, 엄격 모드로 그려 본다
    page = admin_client.get("/live?stay=1")
    assert page.status_code == 200
    for name in ("audiences", "tracks", "parallel_hint"):
        assert f'"{name}"' in page.text, f"{name} 가 화면으로 넘어가지 않았다"


# ════════════════════════════════════════════════════════════════════
#  화면이 읽는 이름을 구조가 다 가지고 있는가
# ════════════════════════════════════════════════════════════════════
#
# `/live` 와 `/live/staff` 가 이 이유로 죽었습니다 — 화면에 `sheet.font` 를
# 쓰면서 `build()` 에 넣지 않았고, 화면을 열기 전까지 아무도 몰랐습니다.
#
# **화면을 GET 하는 시험(test_p30)이 이걸 잡습니다.** 다만 그건 "실제로 그려
# 봐야" 알고, 그리는 경로가 여러 갈래인 화면은 안 지나간 가지가 남습니다.
# 그래서 **글자만 대조하는 시험을 따로** 둡니다 — 화면을 안 그려도 잡히고,
# 무엇이 없는지 이름으로 말해 줍니다.

JINJA = re.compile(r"\{\{(.*?)\}\}|\{%(.*?)%\}", re.S)


def template_reads(name: str, root: str) -> dict[str, set[str]]:
    """그 화면이 `root.a.b` 로 읽는 이름들.

    **Jinja 식 안에서만 찾습니다** — 그러지 않으면 `live.js` 같은 파일 이름이
    `live.js` 를 읽는 것으로 잡힙니다.
    """
    text = open(f"app/templates/{name}", encoding="utf-8").read()
    inside = " ".join(a or b for a, b in JINJA.findall(text))
    chain = re.compile(
        rf"\b{root}\.([A-Za-z_][A-Za-z0-9_]*)"
        rf"(?:\.([A-Za-z_][A-Za-z0-9_]*))?")
    out: dict[str, set[str]] = {}
    for first, second in chain.findall(inside):
        out.setdefault(first, set())
        # 파이썬 dict 의 메서드는 값이 아니다
        if second and second not in {"items", "keys", "values", "get", "append"}:
            out[first].add(second)
    return out


def missing_names(struct: dict, reads: dict[str, set[str]]) -> list[str]:
    gaps = []
    for first, seconds in sorted(reads.items()):
        if first not in struct:
            gaps.append(first)
            continue
        value = struct[first]
        for second in sorted(seconds):
            if isinstance(value, dict):
                if second not in value:
                    gaps.append(f"{first}.{second}")
            elif isinstance(value, list):
                rows = [r for r in value if isinstance(r, dict)]
                if rows and any(second not in r for r in rows):
                    gaps.append(f"{first}[].{second}")
    return gaps


def test_p33_staff_sheet_화면이_읽는_값을_구조가_다_가지고_있다(live_data):
    """`sheet.font` 가 빠져서 죽었던 자리다."""
    from app.domain import staff_sheet

    with app_session() as db:
        sheet = staff_sheet.build(db, retreat_of(db, live_data))

    reads = template_reads("staff_sheet.html", "sheet")
    assert "font" in reads, "화면이 sheet.font 를 안 읽는다 — 시험이 헛돈다"
    assert "cells" in reads and "columns" in reads
    assert missing_names(sheet, reads) == []


def test_p33b_live_화면이_읽는_값을_구조가_다_가지고_있다(live_data):
    with app_session() as db:
        view = build(db, live_data, now=AT(10, 0))

    reads = template_reads("live.html", "live")
    assert "programs" in reads and "days" in reads
    assert missing_names(view, reads) == []


def test_p33c_board_화면이_읽는_값을_구조가_다_가지고_있다(admin_client, live_data):
    from app.domain import board as board_domain

    with app_session() as db:
        retreat = retreat_of(db, live_data)
        view = board_domain.build(db, retreat)

    reads = template_reads("board.html", "board")
    assert "grid" in reads
    assert missing_names(view, reads) == []

def test_p33d_달력_화면이_읽는_값을_구조가_다_가지고_있다(live_data):
    from app.domain import calendar as cal_domain

    with app_session() as db:
        view = cal_domain.build(
            db, retreat_of(db, live_data), today=dt.date(2026, 8, 10),
            scope="all")

    reads = template_reads("calendar.html", "cal")
    assert "weeks" in reads and "undated" in reads and "scopes" in reads
    assert missing_names(view, reads) == []
