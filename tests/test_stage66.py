"""1단계 남은 것 닫는 판 — 사람이 2026-09-24 에 정한 넷 (CLAUDE.md 4-9 · 11-3).

| 정한 것 | 어디서 재나 |
|---|---|
| ① 화면 문구는 한 말 · 사정은 로그만 팀별로 | 아래 `가` |
| ② `docs/인계.md` 는 넷만 두고 나머지는 얼린다 | 아래 `나` |
| ③ 새 판 확인은 내용 비교로만 | 아래 `다` |
| ④ 「남은 것」 표에는 이어받을 것만 | 아래 `나` |

**막는 쪽과 막히면 안 되는 쪽을 함께 잰다** (11-3) — ① 은 「로그가 가른다」 만이
아니라 **「화면은 안 가른다」** 를 함께 재야 뜻이 산다.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest

from app import models
from tests.conftest import app_session

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
인계 = (ROOT / "docs" / "인계.md").read_text(encoding="utf-8")
지난 = (ROOT / "docs" / "인계-지난.md").read_text(encoding="utf-8")
봐둘것 = (ROOT / "docs" / "봐둘것.md").read_text(encoding="utf-8")


@pytest.fixture()
def 업무(admin_client):
    """부서 둘 — 스케치(담당) · 헤브론(관련팀으로 쓸 자리)."""
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


def 알린다(client, run_id, keys, save_id):
    return client.post(f"/board/task/{run_id}/related-departments/notify",
                       json={"keys": keys, "save_id": save_id})


# ── 가. ① 화면은 한 말 · 로그만 가른다 ───────────────────────────────

def test66_a01_두_사정이_로그에는_다르게_찍힌다(admin_client, 업무, capfd):
    """**소속이 아예 없음**과 **전원 열람 전용**은 총무팀이 할 일이 다르다 —
    사람을 붙이는 것과 권한을 바꾸는 것. 로그가 그 둘을 갈라 준다.
    """
    r = 알린다(admin_client, 업무["run"], ["hebron"], "a01noonesss")
    assert r.status_code == 200, r.text
    빈팀 = capfd.readouterr().out
    assert "hebron:못감(소속없음,거른사람=0)" in 빈팀, 빈팀

    with app_session() as db:
        u = models.User(name="정하윤", phone_number="01000000021", role="viewer")
        db.add(u)
        db.flush()
        db.add(models.UserDepartment(user_id=u.id,
                                     department_id=업무["부서"]["hebron"],
                                     dept_role="member"))
        db.commit()

    r = 알린다(admin_client, 업무["run"], ["hebron"], "a01viewersx")
    assert r.status_code == 200, r.text
    전원열람 = capfd.readouterr().out
    assert "hebron:못감(전원열람전용,거른사람=1)" in 전원열람, 전원열람


def test66_a02_화면_문구는_두_경우가_같다(admin_client, 업무):
    """**막히면 안 되는 쪽** — 화면에 사정을 가려 적으면 그 팀의 소속 구성이
    드러난다. 응답은 두 경우가 **같은 한 말**이어야 한다.
    """
    r = 알린다(admin_client, 업무["run"], ["hebron"], "a02emptyaa")
    빈팀 = r.json()["failed"][0]

    with app_session() as db:
        u = models.User(name="최도현", phone_number="01000000022", role="viewer")
        db.add(u)
        db.flush()
        db.add(models.UserDepartment(user_id=u.id,
                                     department_id=업무["부서"]["hebron"],
                                     dept_role="member"))
        db.commit()

    r = 알린다(admin_client, 업무["run"], ["hebron"], "a02viewerbb")
    전원열람 = r.json()["failed"][0]

    assert 빈팀["why"] == 전원열람["why"], "화면 문구가 두 사정을 가른다"
    assert 빈팀["name"] == 전원열람["name"]


def test66_a03_로그에_이름과_아이디를_안_적는다(admin_client, 업무, capfd):
    """로그도 새는 자리다 (11-2). 팀 키 · 사정 · 수만 적는다."""
    with app_session() as db:
        u = models.User(name="남시우", phone_number="01000000023",
                        role="general", login_id="namsiwoo")
        db.add(u)
        db.flush()
        db.add(models.UserDepartment(user_id=u.id,
                                     department_id=업무["부서"]["hebron"],
                                     dept_role="member"))
        db.commit()

    알린다(admin_client, 업무["run"], ["hebron"], "a03namelog")
    출력 = capfd.readouterr().out
    assert "hebron:보냄" in 출력, 출력
    assert "남시우" not in 출력, "로그에 이름이 있다"
    assert "namsiwoo" not in 출력, "로그에 아이디가 있다"


def test66_a04_팀마다_한_조각씩_적는다(admin_client, 업무, capfd):
    """**합으로만 적으면** 팀이 둘 이상일 때 어느 팀에서 몇을 걸렀는지
    되짚을 수 없다 (2026-09-24 사람이 정함).
    """
    알린다(admin_client, 업무["run"], ["hebron", "sketch"], "a04twoteams")
    출력 = capfd.readouterr().out
    assert "hebron:" in 출력 and "sketch:" in 출력, 출력
    assert "열람전용으로_거른_사람=" not in 출력, "팀을 안 가르고 합으로 적는다"


def test66_a05_셋째_사정도_따로_적힌다(admin_client, 업무, capfd):
    """갈래가 셋인데 **둘만 재면** 셋째는 한 번도 안 밟힌다 (11-3 — 막는 코드에는
    막히는 쪽 시험이 함께 있어야 한다. 2026-09-24 검토가 짚었다).

    셋째는 「그 팀의 받을 사람이 누른 사람뿐」 이다 — 소속이 있고 열람 전용도
    아닌데 자기 자신이라 갈 데가 없다. 앞의 둘과 달리 **총무팀이 고칠 것이 없어서**
    사정을 가르는 뜻이 있다.
    """
    with app_session() as db:
        # `admin_client` 가 만드는 그 사람이다 (conftest 의 `login_as`)
        나 = db.query(models.User).filter_by(phone_number="01011112222").one()
        db.add(models.UserDepartment(user_id=나.id,
                                     department_id=업무["부서"]["hebron"],
                                     dept_role="member"))
        db.commit()

    r = 알린다(admin_client, 업무["run"], ["hebron"], "a05onlyme01")
    출력 = capfd.readouterr().out

    assert r.json()["failed"], "누른 사람뿐인데 보냈다고 한다"
    assert "누른사람뿐" in 출력, 출력
    assert "소속없음" not in 출력 and "전원열람전용" not in 출력, "사정을 잘못 가른다"


# ── 나. ②·④ 인계는 두 파일 · 표에는 이어받을 것만 ────────────────────

def test66_b01_인계는_넷만_둔다():
    """H1 · 맨 위 갱신 하나 · 남은 단계 줄 · 「남은 것」 표.

    **옛 갱신이 남아 있으면** 「새 채팅이 먼저 읽는다」 고 스스로 적은 파일이
    서로 반대를 말한다 — 2026-09-24 에 실제로 그랬다.
    """
    assert 인계.startswith("# 대청부 수련회 시스템 — 미결 목록")
    assert "그 전 갱신:" not in 인계, "옛 갱신 블록이 남아 있다"
    assert len([l for l in 인계.split("\n") if l.startswith("갱신:")]) == 1
    assert "남은 단계는" in 인계
    assert "남은 것 — 한 자리에 모음" in 인계


def test66_b02_지난_기록이_얼려_있고_검사가_뺀다():
    """못 고치는 글이라 낡은 말이 그대로 있다 — 그것이 그때의 사실이다."""
    assert 지난.startswith("# 대청부 수련회 시스템 — 인계 지난 기록")
    assert "얼린 기록이라 고치지 않는다" in 지난
    assert "자기 갱신을 여기에 쓰지 않는다" in 지난
    넘김 = (ROOT / "docs" / "옛말-넘김.txt").read_text(encoding="utf-8")
    assert "docs/인계-지난.md" in 넘김, "옛말 검사가 얼린 글을 본다"
    assert "docs/인계.md |" not in 넘김, "살아 있는 인계까지 넘겼다"


def test66_b03_표의_기준이_표_위에_적혀_있다():
    """기준이 어디에도 없으면 다음 판이 또 봐 둘 것을 올린다."""
    at = 인계.index("남은 것 — 한 자리에 모음")
    위 = 인계[:at]
    assert "다음 판이 이어받아야 할 것만" in 위
    assert "봐 둘 것 후보는" in 위 and "봐둘것.md" in 위


def test66_b04_규약은_기준_문서_한_곳에_있다():
    """두 곳에 적으면 갈린다 — 인계 파일은 자기 머리말로 그것을 말하고,
    **규약의 정본은 CLAUDE.md** 다."""
    at = DOC.index("**인계는 두 파일입니다**")
    자리 = " ".join(DOC[at:at + 1400].split())
    assert "2026-09-24 사람이 정함" in 자리
    assert "인계-지난.md" in 자리 and "얼립니다" in 자리
    assert "다음 판이 그 줄을" in 자리, "누가 옮기는지가 안 적혀 있다"
    assert "이어받아야 할 것만" in 자리, "표의 기준이 안 적혀 있다"


# ── 다. ③ 새 판 확인은 내용 비교로만 ─────────────────────────────────

def test66_c01_11_3_이_내용_비교를_박는다():
    """상태 코드로 세면 **늘 통과**한다 — 틀린 해시도 200 이다."""
    at = DOC.index("**자산이 새 판인지는 받아서 내용을 견줍니다**")
    자리 = " ".join(DOC[at:at + 700].split())
    assert "2026-09-24 사람이 정함" in 자리
    assert "SHA-256" in 자리
    assert "증거로 쓰지 않습니다" in 자리
    assert "아무 8자리나 붙여도 200" in 자리, "왜 증거가 못 되는지가 없다"


def test66_c02_봐둘것_둘이_닫혔다():
    """닫고도 안 적으면 다음 사람이 열린 줄 알고 다시 본다 (11-3 3단계)."""
    for 이름 in ("### BI-c.", "### BI-d."):
        at = 봐둘것.index(이름)
        머리 = 봐둘것[at:봐둘것.index("\n", at)]
        assert "처리함" in 머리 and "정할 것 없음" in 머리, 머리


# ── 라. 7 — 자가시험이 판 안에 끝나게 ─────────────────────────────────

점검JS = (ROOT / "docs" / "checks" / "drawer.js").read_text(encoding="utf-8")


def test66_d01_고장이_걸려야_할_항목까지만_돈다():
    """고장마다 점검을 **통째로** 다시 돌면 한 화면에 수십 분이 걸린다
    (2026-09-24 판이 목록 40분 · 달력 24분을 돌고도 못 끝냈다).

    고장 하나는 **한 항목**을 걸리게 하려고 심는 것이라, 그 항목이 ✗ 가
    된 뒤의 나머지는 그 고장에 대해 아무것도 말해 주지 않는다.

    **낱말만 잰다** — 실제로 빨라지는지는 브라우저에서 잰다.
    """
    assert "const 점검 = async (옵션 = {}) => {" in 점검JS, "점검이 옵션을 안 받는다"
    자리 = 점검JS[점검JS.index("const 잰다 = (ok,"):][:600]
    assert "옵션.멈춤" in 자리 and "throw 멈춤표" in 자리, "찾던 ✗ 에서 안 멈춘다"
    # **일부러 멈춘 것과 죽은 것을 가른다** — 안 가르면 자기 신호를 고장으로 읽는다
    assert "if (e === 멈춤표)" in 점검JS, "멈춤을 「끝까지 못 돌았다」 로 센다"


def test66_d02_짝은_한_표에만_있다():
    """고장과 걸려야 할 항목의 짝은 `고장들` 의 `나와야` 하나가 든다 —
    표를 따로 두면 둘이 갈리고 갈린 쪽을 아무도 눈치채지 못한다.
    """
    자리 = 점검JS[점검JS.index("const 멈춤 = "):][:400]
    assert "g.나와야" in 자리, "짝을 다른 데서 가져온다"
    assert "g.건너뜀나와야 || g.완주못함" in 자리, \
        "끝까지 봐야 판정이 서는 갈래에까지 멈춤을 건다"


def test66_d03_두_칸으로_센다():
    """**안 심음 통과 / 심음 실패가 둘 다 맞을 때만** 잡은 것이다.
    한 칸만 보면 짝이 틀려도 거짓으로 통과한다 (2026-09-24 사람이 정함).
    """
    자리 = 점검JS[점검JS.index("**두 칸을 적는다**"):][:1100]
    assert "안심음:" in 자리 and "심음:" in 자리, "두 칸이 아니다"
    assert "잡았나: 잡혔나 && 깨끗.실패.length === 0" in 자리, \
        "한 칸만 보고 잡았다고 센다"
    assert "걸린초" in 자리, "갈래마다 걸린 시간을 안 낸다"


def test66_d04_불투명_판정에도_고장이_있다():
    """막는 코드를 고친 판에는 **그 막는 쪽 시험**이 함께 있어야 한다 (11-3).

    2026-09-24 에 불투명 판정을 넓혔는데 그 판정에는 심는 고장이 없었다
    (앞 판 검토의 [봐8ㄷ]).
    """
    at = 점검JS.index("㉑ 왼쪽 라벨 열이 반투명")
    자리 = 점검JS[at - 200:at + 600]
    assert "화면: '보드'" in 자리, "어느 화면에서 심는지가 없다"
    assert "왼쪽 라벨 열 배경이 반투명" in 자리, "걸려야 할 항목이 안 적혀 있다"
    assert "rgba(255,255,255,.5)" in 자리, "진짜로 반투명하게 안 만든다"


def test66_b05_인계에서_사라진_갱신은_지난에_있다():
    """**옮기는 것과 덮어쓰는 것을 가르는 유일한 자리다.**

    2026-09-24 에 한 판이 `인계.md` 의 맨 위 갱신을 지난 쪽으로 **옮기는 대신
    덮어써** 한 블록(열세 줄)을 통째로 잃었다. 그때 초록이던 시험들이 못 잡은
    까닭은 **둘 다 한쪽만 봤기** 때문이다 — `b01` 은 「인계.md 에 옛 갱신이
    없는가」 를, `test23_i02` 는 「지난.md 에 할 것이 있는가」 를 본다.
    **「저쪽으로 갔는가」 를 보는 자리가 없었다.**

    날짜를 글로 박지 않는다 — 판마다 낡는다. 지난 쪽에 **갱신 블록이 하나라도
    쌓여 있고** 그 가운데 가장 나중 것이 지금 인계.md 의 갱신보다 앞서면 된다.
    """
    지난갱신 = [l for l in 지난.split("\n") if l.startswith("갱신:")]
    assert len(지난갱신) >= 2, "옮겨 온 갱신이 쌓이지 않는다 — 덮어쓰고 있다"

    지금 = [l for l in 인계.split("\n") if l.startswith("갱신:")][0]
    assert 지금 not in 지난, "지금 갱신이 벌써 지난 쪽에도 있다 — 두 벌이다"
    # 맨 위가 가장 나중 것이다 (지난.md 머리가 정한 순서)
    assert 지난.index(지난갱신[0]) < 지난.index(지난갱신[1]), "새 것이 위가 아니다"


def test66_d05_평소_점검은_멈춤_없이_돈다():
    """`test19_s05` 는 「평소 점검에 `자가시험` 이라는 **글자**가 없는가」 를 본다.
    이 판이 만든 진짜 위험은 반대쪽이다 — **평소 점검이 `멈춤` 을 들고 도는 것.**
    들고 돌면 첫 실패에서 멈춰 나머지를 안 재고도 「완주」 가 뜬다.
    2026-09-24 검토가 짚었다.
    """
    본문 = (ROOT / "docs" / "checks" / "drawer.js").read_text(encoding="utf-8")
    부름 = [l.strip() for l in 본문.split("\n") if "점검(" in l and "const 점검" not in l]
    # 인자를 주는 부름은 자가시험 안에만 있어야 한다
    인자준것 = [l for l in 부름 if "점검()" not in l]
    assert 부름, "점검을 부르는 자리가 없다"
    assert any("점검()" in l for l in 부름), "평소 점검이 인자 없이 도는 자리가 없다"
    for l in 인자준것:
        assert "멈춤" in l, f"자가시험 밖에서 인자를 준다: {l}"


def test66_d06_멈춘_판과_끝까지_돈_판이_갈린다():
    """멈춘 판도 `완주: true` 다 — 「그 자리를 찾았다」 는 뜻이라 그렇다.
    그런데 **나머지 항목은 안 잰 것**이고, 멈춤 줄은 `·` 로 시작해 건너뜀 수에
    섞인다. 표에 `완주` 만 있으면 둘을 못 가른다 (2026-09-24 검토).
    """
    본문 = (ROOT / "docs" / "checks" / "drawer.js").read_text(encoding="utf-8")
    assert "멈춤함 = true" in 본문, "멈춘 것을 따로 적지 않는다"
    assert "멈춤함, 실패:" in 본문, "점검이 그 값을 안 돌려준다"
    assert "멈췄나: !!판.멈춤함" in 본문, "자가시험 표에 그 칸이 없다"

