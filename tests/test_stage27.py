"""UI 정리 판 2 — 봉사팀 여백 8px · /draft 팀원 · 회의록 폼 접기 · 끝난 회차의 알림 · 배지 = 화면."""

from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest
from sqlalchemy import select

from app import models
from app.domain import permissions as perm
from app.domain import staff_sheet as ss
from app.notifications import badge_unread_count, run_risk_scan, unread_count
from tests.conftest import app_session, login_as, make_user

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = dt.date.today()
CSS = (ROOT / "app/static/css/retreat.css").read_text(encoding="utf-8")


# ── 1. 봉사팀 여백 8px — 구조 상수와 CSS 가 같은 값 ──────────────────────

def test27_a01_여백은_8px_이고_구조_상수가_같은_값이다():
    assert ss.CELL_PAD_PX == 17 and ss.CELL_VPAD_PX == 12
    i = CSS.index(".cx{"); block = CSS[i:CSS.index("}", i)]
    m = re.search(r"padding:(\d+)px (\d+)px", block)
    assert m and int(m.group(2)) * 2 + 1 == ss.CELL_PAD_PX and int(m.group(1)) * 2 == ss.CELL_VPAD_PX


# ── 2. /draft — 팀원도 채우고 제출한다 ───────────────────────────────────

@pytest.fixture
def 초안(admin_client):
    from app.domain import drafts as draft_domain
    with app_session() as db:
        r = models.Retreat(name="초안 회차", start_date=dt.date(2026, 8, 21), end_date=dt.date(2026, 8, 23))
        db.add(r); db.flush()
        ids = {"retreat": r.id}
        for i, (key, name) in enumerate((("hebron", "5 헤브론"), ("sketch", "4 스케치"))):
            d = models.Department(retreat_id=r.id, key=key, name=name, color_tag="#888", sort_order=i)
            db.add(d); db.flush(); ids[key] = d.id
        draft_domain.open_draft(db, name="다음 회차", open_date=dt.date(2026, 8, 21),
                                close_date=dt.date(2026, 8, 23), meal_subsidy=8000,
                                department_keys=["hebron", "sketch"])
    return ids


def test27_b01_팀원이_자기_부서_칸을_채우고_제출한다(client, 초안):
    make_user("헤브론 팀원", "01077770201", "general", departments=[(초안["hebron"], perm.MEMBER)])
    login_as(client, "01077770201")
    page = client.get("/draft").text
    assert "5 헤브론" in page and "data-can-edit" not in page.split("<main", 1)[0]
    saved = client.post("/draft/hebron/save", json={"library_ids": [], "adopted": [], "note": "팀원이 적음", "submit": False})
    assert saved.status_code == 200 and saved.json()["state"] == "작성중"
    done = client.post("/draft/hebron/save", json={"library_ids": [], "adopted": [], "note": "", "submit": True})
    assert done.status_code == 200 and done.json()["progress"]["submitted"] == 1
    # ② 남의 부서 칸은 여전히 막힌다
    assert client.post("/draft/sketch/save", json={"library_ids": [], "adopted": [], "note": "", "submit": True}).status_code == 403


# ── 3. 회의록 — 폼은 접혀 있고 끝 칸에 말이 있다 ────────────────────────

def test27_c01_만들기_폼은_접힌_단추이고_목록이_그_아래_바로_온다(admin_client):
    with app_session() as db:
        r = models.Retreat(name="회의록 회차", start_date=TODAY + dt.timedelta(days=30),
                           end_date=TODAY + dt.timedelta(days=33))
        db.add(r); db.flush()
        db.add(models.Meeting(retreat_id=r.id, title="첫 회의", meeting_date=TODAY,
                              attendee_names=["가", "나", "다"], body="1. 안건"))
        db.commit(); rid = r.id
    admin_client.get(f"/board?retreat_id={rid}")
    page = admin_client.get("/meetings").text
    box = page.index('<details class="addbox mt-addbox" id="addbox">')
    assert "<details class=\"addbox mt-addbox\" id=\"addbox\" open" not in page, "접힌 채 시작해야 한다"
    assert "+ 회의록 만들기" in page and box < page.index('class="mt-list"')
    assert "참석 3명" in page, "끝 칸에 「참석 N명」 이 없다"
    assert 'src="/static/js/meetings.' in page


def test27_c02_노션에서_옮긴_것은_그렇게_읽힌다(admin_client):
    with app_session() as db:
        r = models.Retreat(name="회의록 회차2", start_date=TODAY + dt.timedelta(days=30),
                           end_date=TODAY + dt.timedelta(days=33))
        db.add(r); db.flush()
        db.add(models.Meeting(retreat_id=r.id, title="옮긴 회의", meeting_date=TODAY, origin="노션",
                              source_ref="page-1", body="x"))
        db.commit(); rid = r.id
    admin_client.get(f"/board?retreat_id={rid}")
    page = admin_client.get("/meetings").text
    assert "노션에서 옮김" in page and ">옮김<" not in page


# ── 4. 끝난 회차의 알림 · 배지 = 화면 ───────────────────────────────────

def _회차와_할일(db, *, start, end, name, due=None):
    r = models.Retreat(name=name, start_date=start, end_date=end)
    db.add(r); db.flush()
    d = models.Department(retreat_id=r.id, key="hebron", name="5 헤브론", color_tag="#4A8A5C", sort_order=0)
    db.add(d); db.flush()
    who = models.User(name="담당", phone_number="0107777" + str(r.id).zfill(4), role="general")
    db.add(who); db.flush()
    perm.assign(db, who, d, perm.LEAD)
    db.add(models.Task(retreat_id=r.id, title="기한 지난 할 일", department_id=d.id, assignee_id=who.id,
                       due_date=due or (TODAY - dt.timedelta(days=3)), status="대기",
                       blocked_by_task_ids=[], related_department_ids=[]))
    db.commit()
    return r.id, who.id


def test27_d01_끝난_회차에는_위험_점검이_알림을_만들지_않는다(admin_client):
    with app_session() as db:
        end = TODAY - dt.timedelta(days=17)
        rid, uid = _회차와_할일(db, start=TODAY - dt.timedelta(days=20), end=end, name="끝난 회차",
                               due=end - dt.timedelta(days=1))
        r = db.get(models.Retreat, rid)
        assert run_risk_scan(db, retreat=r, today=TODAY) == 0
        assert unread_count(db, db.get(models.User, uid)) == 0
        # 저장된 상태가 아니라 날짜에서 — 같은 자료가 폐회 당일(아직 진행 중)이면 생긴다
        assert run_risk_scan(db, retreat=r, today=end) > 0


def test27_d02_진행_중인_회차에는_지금과_같이_생긴다(admin_client):
    with app_session() as db:
        rid, uid = _회차와_할일(db, start=TODAY + dt.timedelta(days=20), end=TODAY + dt.timedelta(days=23), name="진행 회차")
        r = db.get(models.Retreat, rid)
        assert run_risk_scan(db, retreat=r, today=TODAY) > 0
        assert unread_count(db, db.get(models.User, uid)) > 0
        # 폐회 다음 날부터 멎는다 (4-15 의 경계와 같다) — 이미 만든 건 그대로 남는다 (0장)
        assert run_risk_scan(db, retreat=r, today=r.end_date + dt.timedelta(days=1)) == 0


def test27_d03_배지와_화면의_안_읽은_수가_같다(client, admin_client):
    from app.templating import _badge_counts
    with app_session() as db:
        rid, uid = _회차와_할일(db, start=TODAY + dt.timedelta(days=20), end=TODAY + dt.timedelta(days=23), name="배지 회차")
        who = db.get(models.User, uid)
        who.phone_number = "01077770301"
        # 들어오기 전에 쌓인 것 둘 — 배지에도 줄에도 안 세고, 모두 읽음은 지운다
        old = models._now() - dt.timedelta(days=3)
        for i in range(2):
            db.add(models.Notification(user_id=uid, retreat_id=rid, kind="지연", title=f"옛 {i}", dedupe_key=f"옛:{i}", created_at=old))
        who.first_seen_at = models._now() - dt.timedelta(hours=1)
        db.commit()
        r = db.get(models.Retreat, rid)
        run_risk_scan(db, retreat=r, today=TODAY)              # 들어온 뒤의 것
        n_badge = _badge_counts({"user": who, "retreat": r})["unread_count"]
        n_line = badge_unread_count(db, who, rid)
        n_all = unread_count(db, who, retreat_id=rid)
        assert n_badge == n_line > 0 and n_all == n_line + 2
    login_as(client, "01077770301")
    page = client.get(f"/notifications?retreat_id={rid}").text
    assert f"안 읽은 알림 {n_line}건" in page and f"{n_all}건을 함께 읽음 처리합니다" in page
    # 사이드바 배지 = 안 읽은 알림 + 답 대기 요청 (4-0). 요청이 없으니 배지 = 줄의 수
    import re as _re
    badge = _re.search(r'class="badge"[^>]*>\s*(\d+)', page)
    assert badge and int(badge.group(1)) == n_badge == n_line
    # 모두 읽음은 전부 지운다 — 줄이 말한 그 수다
    client.post("/notifications/read-all", follow_redirects=False)
    with app_session() as db:
        assert unread_count(db, db.get(models.User, uid), retreat_id=rid) == 0


def test27_d04_끝난_뒤_쌓인_알림_수를_줄에_적는다(client, admin_client):
    with app_session() as db:
        rid, uid = _회차와_할일(db, start=TODAY - dt.timedelta(days=20), end=TODAY - dt.timedelta(days=17), name="끝난 회차2")
        who = db.get(models.User, uid); who.phone_number = "01077770302"
        who.first_seen_at = models._now() - dt.timedelta(days=30)
        after = models._now() - dt.timedelta(days=5)          # 폐회 뒤
        before = dt.datetime.combine(TODAY - dt.timedelta(days=19), dt.time())   # 폐회 전
        db.add(models.Notification(user_id=uid, retreat_id=rid, kind="지연", title="뒤", dedupe_key="뒤", created_at=after))
        db.add(models.Notification(user_id=uid, retreat_id=rid, kind="지연", title="전", dedupe_key="전", created_at=before))
        db.commit()
    login_as(client, "01077770302")
    page = client.get(f"/notifications?retreat_id={rid}").text
    assert "안 읽은 알림 2건" in page and "그중 수련회가 끝난 뒤 쌓인 1건" in page
