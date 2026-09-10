"""사용 준비 — 첫 사람들이 들어오기 전에.

지금까지 잰 것은 **화면이 규칙대로 도는가**였다. 이 판이 재는 것은 다르다 —
**아무것도 모르는 사람이 처음 열었을 때 무엇이 보이는가.**

운영 DB 를 세어 보니 셋이 나왔다(수는 `docs/review/최근.md`) — 계정 대부분이
링크를 못 받았고, 알림이 사람마다 세 자리로 쌓였고, 이번 회차 업무에 담당자가
하나도 없다. 앞의 둘은 **첫 화면이 밀린 것으로 보이는** 문제이고, 뒤엣것은
**내 할 일이 영영 비는** 문제다.

시험은 셋이 한 벌이다 (11-3) — ① 걸려야 할 것이 걸리는가 ② **안 걸려야 할
것이 통과하는가** ③ 검사가 볼 것을 보고 있는가.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest
from sqlalchemy import select

from app import models
from app.notifications import MANY_UNREAD, notify, system_unread_count
from tests.conftest import app_session, login_as, make_user

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = dt.date.today()


@pytest.fixture
def world(admin_client):
    """진행 중 회차 + 부서 둘 + 업무 셋 (담당자 없음)."""
    with app_session() as db:
        retreat = models.Retreat(
            name="2027 여름수련회",
            start_date=TODAY + dt.timedelta(days=40),
            end_date=TODAY + dt.timedelta(days=43),
        )
        db.add(retreat)
        db.flush()
        chongmu = models.Department(retreat_id=retreat.id, key="chongmuM",
                                    name="1 총무M", color_tag="#2F4858", sort_order=0)
        hebron = models.Department(retreat_id=retreat.id, key="hebron",
                                   name="5 헤브론", color_tag="#4A8A5C", sort_order=1)
        db.add_all([chongmu, hebron])
        db.flush()
        runs = {}

        def run(title, no, dept):
            lib = models.TaskLibrary(title=title, kind="main", default_d_week=5)
            db.add(lib)
            db.flush()
            row = models.TaskRun(
                library_id=lib.id, retreat_id=retreat.id, included=True,
                department_id=dept.id, d_week=5, run_no=no,
                start_date=TODAY + dt.timedelta(days=no),
                end_date=TODAY + dt.timedelta(days=no + 6), status="대기")
            db.add(row)
            db.flush()
            runs[title] = row.id

        run("명찰 제작", 1, chongmu)
        run("스트랩 발주", 2, chongmu)
        run("헤브론 장비", 3, hebron)
        db.commit()
        ids = {"retreat": retreat.id, "chongmu": chongmu.id, "hebron": hebron.id,
               "chongmu_key": "chongmuM", "runs": runs}
    admin_client.get(f"/board?retreat_id={ids['retreat']}")
    return ids


def _admin(db) -> models.User:
    return db.scalars(select(models.User).where(models.User.role == "admin")).first()


# ════════════════════════════════════════════════════════════════════
# 1. 첫 화면에서 압도되지 않게
# ════════════════════════════════════════════════════════════════════


def _쌓는다(db, user, retreat_id, n, *, 언제=None):
    """안 읽은 알림 n건. 시각을 주면 그때 온 것으로 남긴다."""
    for i in range(n):
        notify(db, users=[user], retreat_id=retreat_id, kind="지연",
               title=f"밀린 것 {i}", dedupe_key=f"많음-{i}")
    if 언제 is not None:
        db.query(models.Notification).update({models.Notification.created_at: 언제})
        db.commit()


def test22_a01_많으면_모두_읽음_줄이_커진다(admin_client, world):
    """**첫 화면이 밀린 목록으로 보이면 사람은 그 화면을 다시 안 연다.**
    그때 필요한 것은 「어디부터 볼까」 가 아니라 한 번에 지우는 자리다.

    ② **안 걸려야 할 것도 잰다** — 경계 아래에서는 크게 내지 않는다.
    한쪽만 재면 「늘 크게」 를 통과로 읽는다."""
    with app_session() as db:
        _쌓는다(db, _admin(db), world["retreat"], MANY_UNREAD)
    page = admin_client.get(f"/notifications?retreat_id={world['retreat']}").text
    assert f"안 읽은 알림 {MANY_UNREAD}건" in page
    assert re.search(r'class="nallread many"', page), "많은데 크게 안 낸다"


def test22_a02_적으면_커지지_않되_지우는_자리는_있다(admin_client, world):
    """경계 아래. **「모두 읽음」 은 그래도 목록 위에 있다** — 칩 줄 끝에
    있던 시절에는 고르는 것들 사이에 섞여 안 보였다 (4-16)."""
    with app_session() as db:
        _쌓는다(db, _admin(db), world["retreat"], MANY_UNREAD - 1)
    page = admin_client.get(f"/notifications?retreat_id={world['retreat']}").text
    assert f"안 읽은 알림 {MANY_UNREAD - 1}건" in page
    assert 'class="nallread"' in page, "지우는 자리가 없어졌다"
    assert "nallread many" not in page, "경계 아래인데 크게 낸다"
    assert '/notifications/read-all' in page


def test22_a03_경계는_한_곳에서_온다():
    """화면에 숫자를 박으면 고칠 때 두 곳이 갈립니다 (10장).

    **보는 자리를 그 줄로 좁힙니다** — 파일 전체에서 「50」 을 찾으면
    나중에 누가 폭에 150px 을 넣었다고 빨개집니다(재는 것과 상관없는
    이유로 빨개지는 시험은 사람이 읽지 않고 고칩니다).

    **경계 자체는 a01·a02 가 잽니다** — 템플릿에 40 을 박으면 a02 가
    빨개집니다. 이 줄은 「그 값이 어디서 오는가」 만 봅니다.
    """
    html = (ROOT / "app/templates/notifications.html").read_text(encoding="utf-8")
    글 = re.sub(r"\{#[\s\S]*?#\}", "", html)
    줄 = [x for x in 글.splitlines() if "nallread" in x]
    assert 줄, "「모두 읽음」 줄을 못 찾았다 — 이름이 바뀌었나"
    한줄 = " ".join(줄)
    assert "many_unread" in 한줄, "경계를 다른 데서 가져온다"
    assert not re.search(r"\d", 한줄), f"그 줄에 수가 박혀 있다: {한줄.strip()}"


def test22_b01_처음_들어온_사람에게는_배지가_없다(client, world):
    """**들어오자마자 275 를 보면 시스템이 밀린 것으로 읽힌다** — 그건 그
    사람이 놓친 것이 아니라 그 사람이 없던 동안 쌓인 것이다 (4-16).

    ③ **검사가 볼 것을 보고 있는가** — 배지가 0 인 것이 「알림이 없어서」
    가 아님을 함께 잰다: 같은 판에서 알림 화면은 그 수를 그대로 말한다."""
    lead_id = make_user("부서 리더", "01077770001", "dept_lead",
                        dept=world["chongmu"])
    with app_session() as db:
        lead = db.get(models.User, lead_id)
        assert lead.first_seen_at is None, "아직 안 들어온 계정이다"
        _쌓는다(db, lead, world["retreat"], 3,
               언제=dt.datetime.now() - dt.timedelta(days=1))

    login_as(client, "01077770001")
    page = client.get(f"/notifications?retreat_id={world['retreat']}").text
    # 배지는 0 — 사이드바에 수가 안 붙는다
    with app_session() as db:
        lead = db.get(models.User, lead_id)
        assert lead.first_seen_at is not None, "들어온 때를 안 찍었다"
        assert system_unread_count(db, lead) == 0
    # 그런데 알림 화면은 감추지 않는다 — 세는 자리가 다른 것이다
    assert "안 읽은 알림 3건" in page


def test22_b02_들어온_뒤에_온_것은_센다(client, world):
    """② 안 걸려야 할 것이 통과하는가 — 안 그러면 배지가 영영 0 이다."""
    lead_id = make_user("나중 리더", "01077770002", "dept_lead",
                        dept=world["chongmu"])
    login_as(client, "01077770002")
    client.get(f"/board?retreat_id={world['retreat']}")
    with app_session() as db:
        lead = db.get(models.User, lead_id)
        assert lead.first_seen_at is not None
        _쌓는다(db, lead, world["retreat"], 2)
        assert system_unread_count(db, lead) == 2


# ════════════════════════════════════════════════════════════════════
# 2. 자기 일을 찾을 수 있게
# ════════════════════════════════════════════════════════════════════


def test22_c01_내_할_일이_비면_다음_할_일을_가리킨다(client, world):
    """담당자가 없는 업무는 **아무 화면에도 안 뜨는데, 그게 정확히 놓치는
    지점**이다 (달력의 「날짜 없는 업무」 와 같은 자리 · 4-13)."""
    make_user("총무 리더", "01077770003", "dept_lead",
              dept=world["chongmu"])
    login_as(client, "01077770003")
    page = client.get(f"/?retreat_id={world['retreat']}").text
    # 부서마다 한 줄 — 「<부서>에 담당자 없는 업무 N건」 (도막 4)
    assert "에 담당자 없는 업무 2건" in page, "내 부서 것만 센다(헤브론 1건 제외)"
    assert "담당자 없는 업무 1건" not in page
    assert f'href="/tasks?dept={world["chongmu_key"]}"' in page


def test22_c02_담당자가_붙으면_그_줄이_사라진다(client, admin_client, world):
    """② 늘 뜨는 줄이면 아무것도 안 재는 것이다 — 다 붙이면 없어져야 한다."""
    lead_id = make_user("총무 리더2", "01077770004", "dept_lead",
                        dept=world["chongmu"])
    for title in ("명찰 제작", "스트랩 발주"):
        res = admin_client.post(f"/board/task/{world['runs'][title]}/assignee",
                                json={"user_id": lead_id})
        assert res.status_code == 200, res.text
    login_as(client, "01077770004")
    page = client.get(f"/?retreat_id={world['retreat']}").text
    assert "내 부서에 담당자 없는 업무" not in page


def test22_c03_내_할_일이_있으면_그_줄이_없다(client, admin_client, world):
    """② **안 뜨는 쪽을 재지 않으면 「늘 뜬다」 를 통과로 읽는다.**
    c02 는 세는 값이 0 이 돼서 사라진 것이라 이 축을 안 잽니다 — 검토가
    짚은 자리입니다. 여기서는 **담당자 없는 업무를 그대로 둔 채** 마감이
    오늘인 내 업무를 하나 만들어, 「내 할 일」 이 차면 안내가 사라지는지
    봅니다."""
    lead_id = make_user("총무 리더3", "01077770010", "dept_lead",
                        dept=world["chongmu"])
    with app_session() as db:
        lib = models.TaskLibrary(title="오늘까지 할 것", kind="main", default_d_week=1)
        db.add(lib)
        db.flush()
        db.add(models.TaskRun(
            library_id=lib.id, retreat_id=world["retreat"], included=True,
            department_id=world["chongmu"], d_week=1, run_no=9,
            start_date=TODAY, end_date=TODAY, status="대기", assignee_id=lead_id))
        db.commit()
    login_as(client, "01077770010")
    page = client.get(f"/?retreat_id={world['retreat']}").text
    assert "오늘까지 할 것" in page, "내 할 일이 실제로 찼는지부터 본다"
    assert "내 부서에 담당자 없는 업무" not in page, "비지 않았는데 안내가 뜬다"


def test22_d01_목록에서_담당자를_그_자리에서_고른다(admin_client, world):
    """드로어를 안 열고 바꾼다 (4-14). **새 메뉴를 만들지 않는다** —
    고를 사람과 저장하는 길이 두 벌이 되면 갈린 쪽을 아무도 눈치채지 못한다."""
    run_id = world["runs"]["명찰 제작"]
    who = make_user("총무 사람", "01077770005", "member",
                    dept=world["chongmu"])
    page = admin_client.get(f"/tasks?retreat_id={world['retreat']}").text
    assert "deptchip asg none pick" in page, "고를 수 있는 칸으로 안 나온다"

    # 고를 사람은 서버가 준다 — 그 부서와 총무팀 (4-9)
    detail = admin_client.get(f"/board/task/{run_id}",
                              headers={"Accept": "application/json"}).json()
    assert who in [p["id"] for p in detail["candidates"]]

    res = admin_client.post(f"/board/task/{run_id}/assignee", json={"user_id": who})
    assert res.status_code == 200
    assert res.json()["assignee"] == "총무 사람"
    with app_session() as db:
        assert db.get(models.TaskRun, run_id).assignee_id == who


def test22_d02_다른_부서_업무는_403(client, world):
    """권한은 상태와 같다 — **그 문 하나다** (4-14). 부서는 키로 본다 (2장)."""
    make_user("헤브론 리더", "01077770006", "dept_lead",
              dept=world["hebron"])
    login_as(client, "01077770006")
    client.get(f"/board?retreat_id={world['retreat']}")
    res = client.post(f"/board/task/{world['runs']['명찰 제작']}/assignee",
                      json={"user_id": None})
    assert res.status_code == 403
    # ② 자기 부서 것은 통과한다 — 전부 막으면 시험이 아무것도 안 잰다
    ok = client.post(f"/board/task/{world['runs']['헤브론 장비']}/assignee",
                     json={"user_id": None})
    assert ok.status_code == 200


def test22_d03_못_고치는_사람에게는_메뉴가_안_뜬다(client, world):
    """**서버가 다시 본다** — 화면만 감춘 것이 아니다. 그리고 그 칸은
    예외가 아니라 행의 다른 곳과 같다: 메뉴 대신 행이 열린다 (4-14)."""
    make_user("헤브론 리더2", "01077770007", "dept_lead",
              dept=world["hebron"])
    login_as(client, "01077770007")
    page = client.get(f"/tasks?retreat_id={world['retreat']}&dept=all").text
    # 헤브론 행 하나는 고를 수 있고, 총무 행 둘은 못 고른다
    assert page.count("asg none pick") == 1, "못 고치는 행까지 고를 수 있게 나온다"
    assert page.count('class="deptchip asg none"') == 2

    js = (ROOT / "app/static/js/tasks.js").read_text(encoding="utf-8")
    assert ".asg.pick" in js, "안 여는 자리에 담당자 칸이 없다"
    # 안 여는 자리 목록에 든 것만 예외다 — `pick` 없는 칸은 행을 연다
    자리 = re.search(r"const 안여는곳 = '([^']+)'", js).group(1)
    assert ".asg.pick" in 자리 and ".asg," not in 자리 + ","


def test22_d04_메뉴는_한_벌이다():
    """상태와 담당자가 **같은 것을 띄운다** — 뜨는 자리·닫히는 규칙·바깥
    클릭 판정이 두 벌이 되면 한쪽만 고쳐진다 (4-14).

    **낱말만 잰다** — 동작은 브라우저에서만 일어난다(메뉴가 실제로 뜨고
    화면 안에 묶이는지). 그것은 `docs/checks/drawer.js` 와 이 판의
    실측(`docs/review/최근.md`)이 잰다."""
    js = (ROOT / "app/static/js/drawer.js").read_text(encoding="utf-8")
    js = re.sub(r"/\*[\s\S]*?\*/", "", js)
    js = re.sub(r"(?<!:)//[^\n]*", "", js)
    assert js.count("function 메뉴를띄운다") == 1
    for 이름 in ("function statMenu", "async function assigneeMenu"):
        자리 = js[js.index(이름):js.index(이름) + 900]
        assert "메뉴를띄운다" in 자리, f"{이름} 가 제 메뉴를 따로 띄운다"
    # 바깥 클릭 판정이 담당자 칸을 알아야 뜨자마자 안 닫힌다
    assert ".asg.pick" in js[js.index("function originOf"):][:700]


# ════════════════════════════════════════════════════════════════════
# 3. 회의록에서 업무로 가는 입구
# ════════════════════════════════════════════════════════════════════


def test22_e01_회의록_상세에_제안_자리가_있다():
    """**회의록에서 업무로 가는 길은 제안 흐름 하나다** (12장). 그 자리가
    화면에 없으면 길이 없는 것과 같다.

    **낱말만 잰다** — 동작은 브라우저가 잰다: 실제로 눌러 목록이 그려지는
    것까지 본 결과가 `docs/review/최근.md` 0-(d) 에 있다. 여기서는
    「그 자리가 화면에 있는가」 만 본다."""
    html = (ROOT / "app/templates/meeting_detail.html").read_text(encoding="utf-8")
    assert 'class="mt-sug"' in html
    js = (ROOT / "app/static/js/meeting.js").read_text(encoding="utf-8")
    assert "업무로 만들기" in js and "suggestions/apply-new" in js

    # **이번 판이 더한 것은 「위에서 가리키는 줄」 이다** — 그 자리는 본문
    # 아래라 긴 회의록에서는 화면 밖이었다(0-(d) 실측). 위의 둘은 전부터
    # 있던 것이라, 그것만 재면 이 판이 더한 것을 아무도 안 지킨다
    assert 'class="mt-tosug"' in html and 'href="#mt-sug"' in html
    assert 'id="mt-sug"' in html, "가리키는 곳이 없다"
    assert "hidden" in html[html.index("mt-tosug"):html.index("mt-tosug") + 200],         "낼 것이 없어도 뜬다 — 눌러 봐야 빈 자리면 다음부터 안 누른다"
    자리 = js[js.index("function 가리킨다"):js.index("function 가리킨다") + 400]
    assert "data.items" in 자리, "수를 목록과 다른 데서 센다"
    assert "링크.hidden = !n" in 자리, "낼 것이 없을 때 감추지 않는다"


# ════════════════════════════════════════════════════════════════════
# 4. 링크 보내기 준비
# ════════════════════════════════════════════════════════════════════


def test22_f01_안_받은_사람_수가_맨_위에_있다(admin_client, world):
    """열아홉 명에게 차례로 보내는 일이라, 목록을 훑어 세는 것은 사람이
    할 일이 아니다 (4-12). **수는 세어서 낸다** — 화면이 다시 세지 않는다."""
    make_user("아직 안 보낸 사람", "01077770008", "member")
    page = admin_client.get("/admin/users").text
    # 관리자 자신은 들어왔고(로그인했다), 방금 만든 사람은 안 받았다
    assert "링크 안 받은 사람 1명" in page
    assert "들어온 사람 1명" in page
    assert '<span class="tag done">들어옴</span>' in page


def test22_f02_보냈지만_안_들어온_사람은_따로_센다(admin_client, world):
    """② **「보냈는데 아직 안 들어온 사람」 은 「안 보낸 사람」 과 다른
    일이다** — 앞은 기다리는 것이고 뒤는 보내는 것이다. 한 칸에 담으면
    누구에게 보내야 하는지가 안 보인다 (4-12)."""
    person = make_user("보낸 사람", "01077770009", "member")
    admin_client.post(f"/admin/users/{person}/invite", follow_redirects=False)
    page = admin_client.get("/admin/users").text
    assert "링크 안 받은 사람 0명" in page
    assert "보냈고 아직 안 들어옴 1명" in page


def test22_f04_들어온_사람에게_다시_보낸_링크도_보인다(admin_client, world):
    """**기기를 잃으면 재발급합니다** (4-12). 그때 그 사람은 「들어옴」 인
    동시에 「살아 있는 링크가 있는」 사람이라, 하나로 끊으면 **그 링크가
    언제까지인지가 화면에서 사라집니다** — 검토가 짚은 자리입니다."""
    page = admin_client.get("/admin/users").text
    assert '<span class="tag done">들어옴</span>' in page
    assert "까지</span>" not in page.split('들어옴</span>')[1].split("</td>")[0]

    with app_session() as db:
        me = _admin(db).id
    admin_client.post(f"/admin/users/{me}/invite", follow_redirects=False)
    page = admin_client.get("/admin/users").text
    칸 = page.split('들어옴</span>')[1].split("</td>")[0]
    assert "까지</span>" in 칸, "들어온 사람의 살아 있는 링크가 안 보인다"


def test22_f03_안내문_초안이_있고_실명이_없다():
    """링크와 함께 보낼 글이다. **실명·연락처를 안 넣는다** (11-2) —
    저장소는 공개다."""
    p = ROOT / "docs" / "초대-안내문.md"
    assert p.exists(), "안내문 초안이 없다"
    글 = p.read_text(encoding="utf-8")
    assert "한 번만" in 글, "링크가 한 번만 열린다는 말이 없다"
    assert "총무팀" in 글, "안 되면 누구에게 말할지가 없다"
    assert re.search(r"01[016-9][-\s]?\d{3,4}[-\s]?\d{4}", 글) is None, "번호가 들어 있다"
