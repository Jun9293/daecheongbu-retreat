"""사람이 2026-09-24 에 정한 넷 — 목업 확정분 1단계 뒤처리 (CLAUDE.md 4-9 · 4-0).

넷 다 **권한 쪽**이다.

| 정한 것 | 어디서 재나 |
|---|---|
| ① 목업과 다르게 둔 세 자리는 4-0 눈금을 따른다 | 아래 `가` (값은 `test_stage64` 가 이미 잰다 — 여기는 **결정이 한 곳에만 적혔는가**) |
| ② 화면 점검은 되돌릴 수 없는 자국을 안 남긴다 | 아래 `나` |
| ③ 관련팀 알림에서 열람 전용을 거른다 | 아래 `다` |
| ④ `dedupe_key` 에 저장 식별값이 들어간다 | 아래 `라` |

**막는 쪽과 막히면 안 되는 쪽을 함께 잰다** (11-3) — ③ 은 「열람 전용은 안
받는다」 만이 아니라 「나머지는 받는다」 를 함께 재야 거르는 규칙이 너무 넓어진
것을 잡는다. ④ 도 「같은 저장은 한 번」 과 「다른 저장은 다시 간다」 가 짝이다.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest

from app import models
from tests.conftest import app_session

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
목업 = (ROOT / "docs" / "mockups" / "목업확정-2026-09-23.md").read_text(encoding="utf-8")
점검 = (ROOT / "docs" / "checks" / "drawer.js").read_text(encoding="utf-8")
라우터 = (ROOT / "app" / "routers" / "board.py").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "js" / "drawer.js").read_text(encoding="utf-8")


@pytest.fixture()
def 업무(admin_client):
    """관련팀 알림을 보낼 업무 하나 + 부서 둘(스케치 · 헤브론)."""
    with app_session() as db:
        열림 = dt.date.today() + dt.timedelta(days=30)
        r = models.Retreat(name="2026 여름수련회 Belong", start_date=열림,
                           end_date=열림 + dt.timedelta(days=2))
        db.add(r)
        db.flush()
        부서 = {}
        for i, (키, 이름, 색) in enumerate([("sketch", "4 스케치", "#B95A83"),
                                          ("hebron", "5 헤브론", "#4A8A5C")]):
            d = models.Department(retreat_id=r.id, key=키, name=이름,
                                  color_tag=색, sort_order=i)
            db.add(d)
            db.flush()
            부서[키] = d.id
        lib = models.TaskLibrary(title="포스터 제작", kind="main",
                                 default_department_key="sketch",
                                 related_department_keys=[], related_library_ids=[],
                                 date_anchor="week", default_d_week=6,
                                 default_offset_days=0, default_span_days=3)
        db.add(lib)
        db.flush()
        run = models.TaskRun(library_id=lib.id, retreat_id=r.id, included=True,
                             department_id=부서["sketch"], d_week=6,
                             start_date=dt.date.today(),
                             end_date=dt.date.today() + dt.timedelta(days=3),
                             status="대기", run_no=1)
        db.add(run)
        db.commit()
        return {"retreat": r.id, "run": run.id, "부서": 부서}


def 사람을붙인다(부서id: int, 이름: str, 번호: str, role: str) -> int:
    """그 부서에 계정 하나. `role` 이 `viewer` 면 열람 전용이다 (4-12)."""
    with app_session() as db:
        u = models.User(name=이름, phone_number=번호, role=role)
        db.add(u)
        db.flush()
        db.add(models.UserDepartment(user_id=u.id, department_id=부서id,
                                     dept_role="member"))
        db.commit()
        return u.id


def 알린다(client, run_id, keys, save_id="s65aaaaaaaaa"):
    몸 = {"keys": keys}
    if save_id is not None:
        몸["save_id"] = save_id
    return client.post(f"/board/task/{run_id}/related-departments/notify", json=몸)


def 그함수() -> str:
    """`notify_related_departments` 의 몸 전부.

    **글자 수로 자르지 않는다** — 4000자로 잘라 두었더니 그 함수가 이미
    4051자여서 끝 51자가 밖이었다(2026-09-24 검토가 잼). 「없다」 를 재는
    단언은 안 보는 만큼 조용히 약해지므로, **다음 정의까지**로 자른다.
    """
    at = 라우터.index("def notify_related_departments")
    끝 = 라우터.index("\nclass ", at)
    return 라우터[at:끝]


def 알림수(uid: int, run_id: int, key: str, save_id: str) -> int:
    with app_session() as db:
        return db.query(models.Notification).filter(
            models.Notification.user_id == uid,
            models.Notification.dedupe_key == f"related:{run_id}:{key}:{save_id}",
        ).count()


# ── 가. ① 목업과 다르게 둔 자리 (2026-09-24 사람이 정함) ──────────────

def test65_a01_결정_문장은_기준_문서_한_곳이다():
    """**값을 두 곳에 적으면 한쪽만 고쳐진다.** 목업 파일은 가리키기만 한다.

    **낱말만 잰다** — 실제 값이 그 자리에 있는지는 `test_stage64` 와
    `test_typescale` 이 잰다. 여기는 **정한 것이 적혔는가**만 본다.
    """
    at = DOC.index("세 자리는 목업을 안 따르고 4-0 의 눈금을 따릅니다")
    # **줄바꿈을 지우고 본다** — 문서는 줄을 접어 쓰므로 글자 그대로 찾으면
    # 마침 줄 끝에 걸린 말만 조용히 못 찾는다 (10장의 그 함정)
    자리 = " ".join(DOC[at:at + 1200].split())
    assert "2026-09-24 사람이 정함" in 자리
    for 무엇 in ("사이드바 항목", "꺼진 상태 칸", "모서리"):
        assert 무엇 in 자리, f"{무엇} 자리가 결정 표에 없다"
    assert "예외를 파면 다음 예외의 근거" in 자리, "왜 눈금 쪽인지가 안 적혀 있다"


def test65_a02_목업_파일은_가리키기만_한다():
    """세 자리마다 꼬리가 달리고, **거기서 값을 다시 정하지 않는다.**"""
    꼬리 = [줄 for 줄 in 목업.split("\n") if "2026-09-24" in 줄]
    assert len(꼬리) >= 3, f"꼬리가 셋보다 적다: {len(꼬리)}"
    for 줄 in 꼬리:
        assert "CLAUDE.md" in 줄 or "까닭은" in 줄 or "4-0" in 줄, \
            f"어디를 보라는 말이 없는 꼬리: {줄[:40]}"
    # 목업이 적은 옛 값은 **지우지 않는다** — 무엇을 안 따랐는지가 거기 있다
    assert "항목 13px" in 목업 and "흐린 글자 500" in 목업 and "모서리 6px" in 목업


# ── 나. ② 화면 점검은 자국을 안 남긴다 ───────────────────────────────

def test65_b01_기준_문서가_그_규칙을_들고_있다():
    """규칙이 점검 스크립트 주석에만 있으면, 다음 점검을 짤 때 안 읽는다."""
    at = DOC.index("화면 점검은 되돌릴 수 없는 자국을 남기는 누름을 하지 않습니다")
    자리 = DOC[at:at + 900]
    assert "2026-09-24 사람이 정함" in 자리
    assert "startedAt" in 자리 and "되돌려도 안 지워집니다" in 자리
    assert "pytest 가 잽니다" in 자리, "서버 쪽은 무엇이 재는지가 안 적혀 있다"


def test65_b02_점검이_꺼진_칸을_안_누른다():
    """막는 쪽. 되돌리면 `started_at` 이 남는다 (8장).

    **낱말만 잰다** — 실제로 눌러 보는 것은 그 스크립트 자신이고, 이것은
    「그 줄이 되살아나지 않는가」 를 본다.
    """
    자리 = 점검[점검.index("const 켠칸"):][:700]
    assert "!b.classList.contains('on')" not in 자리, "꺼진 칸을 골라 누른다"
    assert "classList.contains('on')" in 자리


# ── 다. ③ 열람 전용은 안 받는다 ──────────────────────────────────────

def test65_c01_열람_전용은_안_받고_나머지는_받는다(admin_client, 업무):
    """**둘을 함께 잰다** — 거르는 규칙이 너무 넓어지면 아무도 안 받는다."""
    보는이 = 사람을붙인다(업무["부서"]["hebron"], "정하윤", "01000000011", "viewer")
    일하는이 = 사람을붙인다(업무["부서"]["hebron"], "최도현", "01000000012", "general")

    r = 알린다(admin_client, 업무["run"], ["hebron"], "c01aaaaaaaaa")
    assert r.status_code == 200, r.text
    assert r.json()["sent"] == ["hebron"], r.json()

    assert 알림수(일하는이, 업무["run"], "hebron", "c01aaaaaaaaa") == 1, "일반이 못 받았다"
    assert 알림수(보는이, 업무["run"], "hebron", "c01aaaaaaaaa") == 0, "열람 전용이 받았다"


def test65_c02_전원_열람_전용인_팀은_못_간_쪽이다(admin_client, 업무):
    """**「받을 사람 없음」 은 못 간 쪽이다** (사람이 정한 그 자리).

    「보냄」 이라고 적으면 아무도 안 봤다는 사실이 사라진다 (4-11).
    """
    사람을붙인다(업무["부서"]["hebron"], "정하윤", "01000000013", "viewer")

    r = 알린다(admin_client, 업무["run"], ["hebron"], "c02aaaaaaaaa")
    assert r.status_code == 200, r.text
    답 = r.json()
    assert 답["sent"] == [] and 답["already"] == []
    assert len(답["failed"]) == 1 and 답["failed"][0]["key"] == "hebron"
    assert 답["failed"][0]["why"], "까닭이 비어 있다"


def test65_c03_판정을_새로_짓지_않는다():
    """위험 점검과 **같은 자리**를 부른다 — 두 벌이면 갈린 쪽을 아무도 모른다.

    **낱말만 잰다** — 실제로 걸러지는지는 `test65_c01` 이 잰다.
    """
    자리 = 그함수()
    assert "department_members(db, dept.id)" in 자리, "그 부서 사람을 다른 길로 찾는다"
    assert "is_readonly" not in 자리, "열람 전용 판정을 이 자리에서 다시 짓는다"
    assert "열람전용으로_거른_사람" in 자리, "몇 명을 걸렀는지 로그에 안 남는다"


# ── 라. ④ 저장 식별값 ────────────────────────────────────────────────

def test65_d01_다시_저장하고_다시_체크하면_다시_간다(admin_client, 업무):
    """**막히면 안 되는 쪽.** 사람이 팝업에서 체크하는 것은 그때마다 하는
    판단이라 막을 이유가 없다 — 막는 것은 같은 저장이 겹칠 때뿐이다.
    """
    받는이 = 사람을붙인다(업무["부서"]["hebron"], "최도현", "01000000014", "general")
    for 표 in ("d01firstsave", "d01secondsave"):
        r = 알린다(admin_client, 업무["run"], ["hebron"], 표)
        assert r.status_code == 200, r.text
        assert r.json()["sent"] == ["hebron"], f"{표} 에서 안 갔다: {r.json()}"
        assert 알림수(받는이, 업무["run"], "hebron", 표) == 1

    with app_session() as db:
        전체 = db.query(models.Notification).filter(
            models.Notification.user_id == 받는이,
            models.Notification.kind == "관련팀",
        ).count()
    assert 전체 == 2, f"두 번 저장했는데 알림이 {전체}건이다"


def test65_d02_식별값이_없으면_거절하고_아무것도_안_만든다(admin_client, 업무):
    """**막는 쪽.** 그리고 **아무것도 만들기 전에** 거절한다 — 뒤에서 보면
    앞의 몇 팀은 이미 알림이 선 뒤에 400 이 나가, 화면은 「못 보냈다」 인데
    알림함에는 서 있게 된다.
    """
    받는이 = 사람을붙인다(업무["부서"]["hebron"], "최도현", "01000000015", "general")
    for 나쁜값 in (None, "", "짧음", "안 되는 글자!", "x" * 65):
        r = 알린다(admin_client, 업무["run"], ["hebron"], 나쁜값)
        assert r.status_code == 400, f"{나쁜값!r} 인데 통과했다: {r.status_code}"
        assert "저장 식별값" in r.json().get("detail", ""), r.text

    with app_session() as db:
        수 = db.query(models.Notification).filter(
            models.Notification.user_id == 받는이,
            models.Notification.kind == "관련팀",
        ).count()
    assert 수 == 0, f"거절했는데 알림이 {수}건 섰다"


def test65_d03_거절해도_저장된_관련팀은_그대로다(admin_client, 업무):
    """알림이 거절돼도 **관련팀은 흔들리지 않는다.**

    저장과 알림은 갈린 두 단계이고(4-9), 이 엔드포인트는 **관련팀을 쓰지
    않는다** — 그래서 400 이 나가도 저장된 값이 바뀔 자리가 없다. 구조로
    막은 것이지 되돌린 것이 아니다.
    """
    r = admin_client.post(f"/board/task/{업무['run']}/related-departments",
                          json={"keys": ["hebron"]})
    assert r.status_code == 200, r.text
    전 = r.json()["related_department_keys"]

    assert 알린다(admin_client, 업무["run"], ["hebron"], None).status_code == 400

    r = admin_client.get(f"/board/task/{업무['run']}")
    assert r.json()["related_department_keys"] == 전, "거절 뒤에 관련팀이 바뀌었다"
    # 구조로 막았다는 것 — 이 엔드포인트에 관련팀을 쓰는 줄이 없다
    자리 = 그함수()
    assert "related_department_keys =" not in 자리
    assert "related_departments =" not in 자리


def test65_d04_결과_문구가_세_갈래다():
    """보냄 / 이미 알림 / 못 보냄 — **안 간 것을 갔다고 적지 않는다** (4-11).

    **낱말만 잰다** — 실제 갈래는 `test65_d01`·`test64_e02`·`test64_e03` 이 잰다.
    """
    자리 = JS[JS.index("function 결과를보인다"):][:1400]
    for 말 in ("보냄", "이미 알림", "못 보냄", "보내지 않음"):
        assert 말 in 자리, f"결과 줄에 「{말}」 갈래가 없다"
    assert "already_names" in 자리, "이미 간 팀을 서버에서 안 받아 쓴다"


def test65_d05_화면이_저장마다_식별값을_만들고_단추를_잠근다():
    """**저장이 끝난 자리에서** 만든다 — 팝업 안에서 만들면 돌아가기로 닫고
    다시 열 때마다 새 값이 되어, 같은 저장의 두 번째 누름을 못 막는다.

    **낱말만 잰다** — 실제로 잠기는지는 `docs/checks/drawer.js` 가 브라우저에서 잰다.
    """
    assert "function 저장표만든다" in JS
    저장자리 = JS[JS.index("$('relpicksave').onclick"):JS.index("function 저장표만든다")]
    assert "저장표만든다()" in 저장자리, "저장이 끝난 자리에서 안 만든다"
    팝업 = JS[JS.index("function 알릴팀을고른다"):JS.index("function 결과를보인다")]
    assert "저장표만든다" not in 팝업, "팝업 안에서 새로 만든다"
    assert "save_id: 저장표" in 팝업, "식별값을 안 실어 보낸다"
    assert "보내는중" in 팝업 and "go.disabled = true" in 팝업, "확정 단추를 안 잠근다"


# ── 마. 커밋 전 검토가 짚어 고친 것 ───────────────────────────────────

def test65_e01_받을_사람이_나뿐이면_이미_알림이_아니다(admin_client, 업무):
    """**처음 보내는데 「이미 알림」 이라고 말하면 안 된다.**

    `notify` 는 `exclude_user_id` 로 누른 사람을 빼는데, 그 팀의 받을 사람이
    나 하나면 만든 것이 0 이 되어 「이미 알림」 갈래로 떨어졌다 — 겹친 것이
    아니라 **보낼 데가 없는 것**이다. 4-11 의 「안 간 것을 갔다고 적지
    않는다」 와 같은 결의 거짓말이 반대 방향으로 난다 (2026-09-24 검토가 잡음).
    """
    with app_session() as db:
        me = db.query(models.User).filter(models.User.role == "admin").first()
        db.add(models.UserDepartment(user_id=me.id,
                                     department_id=업무["부서"]["hebron"],
                                     dept_role="member"))
        db.commit()

    r = 알린다(admin_client, 업무["run"], ["hebron"], "e01onlymeee")
    assert r.status_code == 200, r.text
    답 = r.json()
    assert 답["already"] == [], "처음인데 「이미 알림」 이라고 말한다"
    assert 답["sent"] == [], "아무한테도 안 갔는데 「보냄」 이라고 말한다"
    assert len(답["failed"]) == 1 and 답["failed"][0]["key"] == "hebron"


def test65_e02_불투명_판정이_두_방향으로_안_샌다():
    """점검의 불투명 판정 — **막는 쪽이 살아 있어야 한다.**

    `color-mix` 를 못 읽어 거짓 실패를 내던 것을 넓히면서, 넓힌 쪽이
    반대로 새면 「반투명인데 통과」 가 된다. 퍼센트 알파(`/ 50%`)를
    `parseFloat` 로만 읽으면 50 이 되어 불투명으로 세고, 못 읽은 값을
    통과로 두면 「아무것도 안 보는 검사」 가 된다 (11-3).

    **낱말만 잰다** — 실제 판정은 브라우저의 계산값으로 돌아간다.
    """
    자리 = 점검[점검.index("const 불투명 = el =>"):][:900]
    assert "endsWith('%')" in 자리, "퍼센트 알파를 안 읽는다"
    assert "Number.isFinite(a) && a >= 1" in 자리, "못 읽은 값을 통과로 둔다"
    assert "!Number.isFinite(a) || a >= 1" not in 자리, "읽기 실패가 통과가 된다"


def test65_e03_관련팀_저장_단추도_잠근다():
    """알림 확정만 잠그면 짝이 안 맞는다 — 겹쳐 누르면 저장이 둘 나가고
    저장 식별값도 둘이 생긴다 (2026-09-24 검토가 잡음).

    **실패하면 되돌린다** — 안 되돌리면 한 번 실패한 사람이 다시 못 누른다.

    **낱말만 잰다** — 실제로 잠기는지는 브라우저의 일이다.
    """
    자리 = JS[JS.index("$('relpicksave').onclick"):JS.index("function 저장표만든다")]
    assert "저장중" in 자리, "저장 단추에 잠금이 없다"
    assert "저장중 = false" in 자리, "실패했을 때 안 되돌린다"
