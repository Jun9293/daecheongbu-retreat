"""회의록을 **문장으로 읽는다** (CLAUDE.md 회의록 5단계).

**실제 API 를 부르지 않는다.** 시험이 네트워크에 기대면 키가 없는 곳에서
빨개지고, 있는 곳에서는 돌 때마다 값이 나가며, 대답이 매번 달라 무엇을
지키는지 알 수 없게 된다. 그래서 `분석(부르기=...)` 으로 **가짜 대답**을
넣고, 우리 쪽 판단만 시험한다 —

  · 그 회의 날의 상태만 보내는가 (5번)
  · 2차를 언제 부르는가 (7번)
  · 판정 단어가 우리 문장에 남는가 (13번)
  · 사람 평가가 제안에 인용되는가 (20번)
  · 키가 없을 때 낱말로 물러서고 **그렇다고 말하는가** (2·15번)

**시험 자료에 실명이 없다** (11-2).
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest
from sqlalchemy import select

from app import models
from app.domain import llm as llm_mod
from app.domain import suggest as S
from tests.conftest import app_session

ROOT = pathlib.Path(__file__).resolve().parent.parent


class 가짜대답:
    """`llm.대답` 과 같은 자리만 흉내 낸다."""

    def __init__(self, text: str, 원: float = 12.0, model: str = "가짜모델"):
        self.text = text
        self.원 = 원
        self.달러 = 원 / 1400
        self.model = model
        self.in_tokens = 0
        self.out_tokens = 0


def 부르기를(*대답들, 기록=None):
    """차례대로 답하는 가짜 호출자. 마지막 것을 계속 되쓴다."""
    남 = list(대답들)

    def call(system, user, **kw):
        if 기록 is not None:
            기록.append({"system": system, "user": user})
        return 남.pop(0) if len(남) > 1 else 남[0]

    return call


@pytest.fixture
def 회차(admin_client):
    """회차 하나 + 업무 셋. 하나는 **회의 뒤에 끝난 것**이다 (5번 시험용)."""
    with app_session() as db:
        r = models.Retreat(name="시험 회차", start_date=dt.date(2026, 8, 21),
                           end_date=dt.date(2026, 8, 23))
        db.add(r)
        db.flush()
        dept = models.Department(retreat_id=r.id, key="sketch", name="4 스케치")
        db.add(dept)
        db.flush()
        상위 = models.TaskLibrary(title="명찰 제작", kind="main", default_d_week=6)
        db.add(상위)
        db.flush()
        하위 = models.TaskLibrary(title="명찰 스트랩 발주", kind="sub",
                                parent_library_id=상위.id, default_d_week=5)
        먼것 = models.TaskLibrary(title="포스터 시안", kind="main", default_d_week=8)
        db.add_all([하위, 먼것])
        db.flush()
        runs = []
        for lib, 시작, 끝, 착수, 완료 in (
            (상위, dt.date(2026, 7, 1), dt.date(2026, 7, 20), None, None),
            (하위, dt.date(2026, 7, 5), dt.date(2026, 7, 15),
             dt.date(2026, 6, 1), None),
            # **회의(6/1) 뒤에 끝났다.** 그날 기준으로는 완료가 아니다
            (먼것, dt.date(2026, 6, 10), dt.date(2026, 6, 30),
             dt.date(2026, 5, 20), dt.date(2026, 7, 9)),
        ):
            run = models.TaskRun(library_id=lib.id, retreat_id=r.id, included=True,
                                 department_id=dept.id, d_week=5,
                                 start_date=시작, end_date=끝, status="완료",
                                 started_at=착수, completed_at=완료)
            db.add(run)
            runs.append(run)
        db.flush()
        m = models.Meeting(retreat_id=r.id, title="6월 회의",
                           meeting_date=dt.date(2026, 6, 1),
                           body="명찰 스트랩을 어디서 살지 정했습니다.\n"
                                "- 큐시트 만들기로 함")
        db.add(m)
        db.commit()
        return {"retreat_id": r.id, "meeting_id": m.id,
                "run_ids": [x.id for x in runs]}


def _열기(회차):
    db = app_session().__enter__()
    r = db.get(models.Retreat, 회차["retreat_id"])
    m = db.get(models.Meeting, 회차["meeting_id"])
    return db, r, m


# ── 1 ~ 3. 키 ────────────────────────────────────────────────────────


def test_llm_01_키가_data_아래에_있고_gitignore_에_걸린다():
    """공개 저장소다 — 한 번 올라가면 지우고 커밋해도 히스토리에 남는다."""
    from app import config

    # 시험은 `DCB_DATA_DIR` 로 딴 폴더를 쓴다 — **이름이 아니라 어느 폴더에
    # 붙어 있는지**를 본다. 운영에서 그 폴더가 `data/` 다
    assert llm_mod.KEY_PATH.name == "anthropic_key.txt"
    assert llm_mod.KEY_PATH.parent == config.DATA_DIR
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/anthropic_key.txt" in ignore

    import subprocess

    r = subprocess.run(["git", "check-ignore", "data/anthropic_key.txt"],
                       cwd=ROOT, capture_output=True)
    assert r.returncode == 0, "git 이 실제로 무시하지 않는다"


def test_llm_02_키가_없어도_화면이_살아_있고_그렇다고_말한다(회차, monkeypatch):
    """**조용히 안 되는 것이 가장 나쁘다.** 낱말로 물러서되 그렇다고 적는다."""
    monkeypatch.setattr(llm_mod, "read_key", lambda: None)
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m)
    finally:
        db.close()
    assert 결과.방식 == "낱말"
    assert "아직 연결되지 않았습니다" in 결과.말
    assert 결과.실패 is False, "키가 없는 것은 실패가 아니라 아직 안 한 것이다"


def test_llm_03_키_넣는_법이_클릭_단위로_적혔다():
    doc = (ROOT / "docs" / "배포-안내.md").read_text(encoding="utf-8")
    장 = doc[doc.index("## 14."):]
    assert "console.anthropic.com" in 장
    assert "anthropic_key.txt" in 장, "파일 이름이 없다"
    assert "data" in 장 and "메모장" in 장, "어디에 어떻게 넣는지가 없다"
    assert "다시 켭니다" in 장 or "다시 켜" in 장, "재시작하라는 말이 없다"
    # 4번 — 만료. **없으면 없다고 적어야 한다** (그날 조용히 고장 난다)
    assert "만료" in 장
    assert "401" in 장, "키가 죽었을 때 무엇이 보이는지 없다"


# ── 4 ~ 6. 업무 목록 ─────────────────────────────────────────────────


def test_llm_04_목록에_이름_부서_상위_속성_기간_상태가_있다(회차):
    db, r, m = _열기(회차)
    try:
        줄들 = S.catalog(S.board_as_of(db, r, dt.date(2026, 6, 1))).splitlines()
    finally:
        db.close()
    하위줄 = next(x for x in 줄들 if "명찰 스트랩 발주" in x)
    assert "4 스케치" in 하위줄, "부서가 없다"
    assert "하위(상위: 명찰 제작)" in 하위줄, "속성·상위가 없다"
    assert "2026-07-05~2026-07-15" in 하위줄, "기간이 없다"
    assert 하위줄.rstrip().endswith("진행중"), "상태가 없다"
    assert 하위줄.startswith("["), "run_id 가 앞에 없다"


def test_llm_05_그_회의_시점의_상태만_쓴다(회차):
    """**뒤엣것을 보면 잘 맞히는 것처럼 보인다.** 7/9 에 끝난 업무가
    6/1 회의에서 끝난 것으로 보이면 안 된다."""
    db, r, m = _열기(회차)
    try:
        그날 = {x.title: x.status for x in S.board_as_of(db, r, dt.date(2026, 6, 1))}
        나중 = {x.title: x.status for x in S.board_as_of(db, r, dt.date(2026, 8, 1))}
        # 저장된 status 는 셋 다 '완료' 다 — 그것을 읽으면 안 된다
        저장된 = {x.status for x in db.scalars(
            select(models.TaskRun).where(models.TaskRun.retreat_id == r.id))}
    finally:
        db.close()
    assert 저장된 == {"완료"}
    assert 그날["포스터 시안"] == "진행중", "그날엔 아직 안 끝났다"
    assert 나중["포스터 시안"] == "완료"
    # **날짜가 하나도 없으면 '대기' 가 아니라 `None`(모름)이다** (6-9).
    # 옮겨 온 자료가 그래서 96건 전부 '대기' 로 나갔고, 8월에 끝난 일도
    # '대기' 로 보였다 — 모델은 그것을 "아직 안 한 일" 로 읽는다
    assert 그날["명찰 제작"] is None, "모르는데 '대기' 라고 한다"


def test_llm_06_목록_크기를_재고_그_값이_실제와_같다(회차):
    """6번 — 실제로 몇 글자인지 **재서 보고한다.** 재는 길이 있어야 재고,
    그 값이 실제로 보낸 것과 같아야 보고가 뜻을 갖는다."""
    db, r, m = _열기(회차)
    try:
        목록 = S.catalog(S.board_as_of(db, r, dt.date(2026, 6, 1)))
        결과 = S.분석(db, retreat=r, meeting=m,
                   부르기=부르기를(가짜대답('{"결정사항":[],"논의후보":[],"새업무":[]}')))
    finally:
        db.close()
    assert 결과.글자수 > 0
    assert 결과.글자수 == len(목록)


# ── 7 · 8. 두 번 부르기 ──────────────────────────────────────────────


def test_llm_07_논의_이력이_없으면_2차를_안_부른다(회차):
    기록 = []
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(
            db, retreat=r, meeting=m,
            부르기=부르기를(가짜대답(json.dumps(
                {"결정사항": [], "새업무": [],
                 "논의후보": [{"run_id": 회차["run_ids"][1], "왜": "스트랩 얘기입니다"}]},
                ensure_ascii=False)), 기록=기록))
    finally:
        db.close()
    assert len(기록) == 1, "볼 것이 없는데 2차를 불렀다"
    assert 결과.부른횟수 == 1
    assert "지난 논의가 없어" in 결과.말, "왜 안 불렀는지가 없다"


def test_llm_07b_논의_이력이_있으면_2차를_부른다(회차):
    with app_session() as db:
        db.add(models.DiscussionEntry(run_id=회차["run_ids"][1],
                                      authored_at=dt.date(2026, 5, 1),
                                      body="지난번에 스트랩 견적을 받았습니다"))
        db.commit()
    기록 = []
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(
            db, retreat=r, meeting=m,
            부르기=부르기를(
                가짜대답(json.dumps(
                    {"결정사항": [], "새업무": [],
                     "논의후보": [{"run_id": 회차["run_ids"][1], "왜": "스트랩 얘기"}]},
                    ensure_ascii=False)),
                가짜대답(json.dumps(
                    {"논의": [{"run_id": 회차["run_ids"][1],
                             "왜": "지난 견적 얘기를 이어서 하고 있습니다"}]},
                    ensure_ascii=False)),
                기록=기록))
    finally:
        db.close()
    assert len(기록) == 2, "2차를 안 불렀다"
    assert "지난 논의" in 기록[1]["user"], "2차에 논의 이력을 안 보냈다"
    assert 결과.부른횟수 == 2
    논의 = [x for x in 결과.제안들 if x.kind == "discussion"]
    assert 논의 and "견적" in 논의[0].why, "2차의 판단이 안 쓰였다"


def test_llm_07c_2차_규칙이_글로_적혀_있다():
    import inspect

    doc = inspect.getdoc(S._2차를_부르나) or ""
    assert "언제 2차를 부르는가" in doc
    assert "이력" in doc


def test_llm_08_값을_잰다(회차):
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(
            db, retreat=r, meeting=m,
            부르기=부르기를(가짜대답('{"결정사항":[],"논의후보":[],"새업무":[]}', 원=17.5)))
    finally:
        db.close()
    assert 결과.원 == pytest.approx(17.5)
    assert "원" in 결과.말, "값이 화면 문구에 없다"


# ── 9 ~ 12. 무엇을 내는가 ────────────────────────────────────────────


def _세가지(회차, **덮기):
    답 = {
        "결정사항": [{"인용": "- 명찰 스트랩은 파란색으로 한다",
                  "무엇": "명찰 스트랩 색을 파란색으로 정했습니다"}],
        "논의후보": [{"run_id": 회차["run_ids"][1], "왜": "스트랩을 어디서 살지 정하는 얘기입니다"}],
        "새업무": [{"제목": "큐시트 제작", "왜": "회의에서 만들기로 했는데 목록에 없습니다",
                 "상위_run_id": 회차["run_ids"][0], "부서": "4 스케치"}],
    }
    답.update(덮기)
    return 가짜대답(json.dumps(답, ensure_ascii=False))


def test_llm_09_결정사항이_회의록_줄을_그대로_인용한다(회차):
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m, 부르기=부르기를(_세가지(회차)))
    finally:
        db.close()
    결정 = [x for x in 결과.제안들 if x.kind == "decision"]
    assert 결정, "결정사항이 없다"
    assert 결정[0].quote == "- 명찰 스트랩은 파란색으로 한다", "인용이 다듬어졌다"


def test_llm_10_논의_근거가_낱말이_아니라_문장이다(회차):
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m, 부르기=부르기를(_세가지(회차)))
    finally:
        db.close()
    논의 = [x for x in 결과.제안들 if x.kind == "discussion"]
    assert 논의
    왜 = 논의[0].why
    # 낱말 겹침 판의 근거는 `'전달' 이(가) 함께 나옵니다 (겹친 낱말 2개)` 였다
    assert "겹친 낱말" not in 왜 and "함께 나옵니다" not in 왜
    assert len(왜) >= 12 and " " in 왜, "낱말 나열이지 문장이 아니다"


def test_llm_11_새_업무_제목이_다듬어진다(회차):
    """`05.24 #7` 의 실패 — 회의록 문장을 그대로 제목으로 썼다."""
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m, 부르기=부르기를(_세가지(회차)))
    finally:
        db.close()
    새것 = [x for x in 결과.제안들 if x.kind == "new"]
    assert 새것
    assert 새것[0].title == "큐시트 제작"
    assert 새것[0].title not in (m.body or ""), "회의록 문장을 그대로 썼다"


def test_llm_12_새_업무에_상위와_부서가_함께_나온다(회차):
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m, 부르기=부르기를(_세가지(회차)))
    finally:
        db.close()
    새것 = [x for x in 결과.제안들 if x.kind == "new"][0]
    assert 새것.parent_title == "명찰 제작"
    assert 새것.department == "4 스케치"


# ── 13 · 14. 지키는 것 ───────────────────────────────────────────────


def test_llm_13_판정_단어가_우리_문장에_없다(회차):
    """4-10 조건 7 — 코드가 판정에 안 넣어도 사람은 판정으로 읽는다."""
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m, 부르기=부르기를(_세가지(
            회차,
            새업무=[{"제목": "큐시트 제작 완료", "왜": "진행 불가로 보입니다"}])))
    finally:
        db.close()
    새것 = [x for x in 결과.제안들 if x.kind == "new"][0]
    for w in S.판정단어:
        assert w not in 새것.title
        assert w not in 새것.why


def test_llm_14_할_말이_없으면_빈_목록이다(회차):
    """조건 4 — 억지로 만들면 근거 없는 제안이 된다. 50건 중 24건이 이렇다."""
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m,
                   부르기=부르기를(가짜대답('{"결정사항":[],"논의후보":[],"새업무":[]}')))
    finally:
        db.close()
    assert 결과.제안들 == []
    assert 결과.방식 == "문장", "빈 목록을 실패로 취급했다"


# ── 15. 죽어도 화면이 산다 ───────────────────────────────────────────


def test_llm_15_API_가_죽으면_낱말로_물러서고_말한다(회차):
    """**빈 목록으로 두지 않는다.** 그러면 '할 말이 없다'(14번의 정상)와
    구별되지 않는다 — 구별되지 않는 실패가 가장 비싸다."""
    def 터진다(system, user, **kw):
        raise llm_mod.LlmUnavailable("응답이 500 입니다")

    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m, 부르기=터진다)
    finally:
        db.close()
    assert 결과.방식 == "낱말"
    assert 결과.실패 is True
    assert "500" in 결과.말 and "낱말" in 결과.말


def test_llm_15b_오류_본문을_화면에_그대로_붙이지_않는다():
    """오류 본문에 키가 되비쳐 오는 일이 있고, 이 말은 화면에 뜬다."""
    src = (ROOT / "app" / "domain" / "llm.py").read_text(encoding="utf-8")
    자리 = src[src.index("if r.status_code != 200:"):src.index("data = r.json()")]
    assert "r.text" not in 자리, "응답 본문을 그대로 붙였다"


# ── 16 ~ 18. 언제 부르는가 ───────────────────────────────────────────


def test_llm_16_저장이_분석을_기다리지_않는다():
    """분석은 뒤에서 돈다 — 기다리게 하면 저장이 고장난 줄 안다."""
    src = (ROOT / "app" / "routers" / "meetings.py").read_text(encoding="utf-8")
    assert "BackgroundTasks" in src
    assert "background.add_task(분석_한번" in src
    # 저장 경로가 직접 부르지 않는다
    자리 = src[src.index("def update_meeting("):src.index("def delete_meeting(")]
    assert "suggest_full(" not in 자리, "저장이 분석을 직접 불렀다"


def test_llm_17_본문이_안_바뀌면_다시_부르지_않는다(회차):
    """오타 하나 고칠 때마다 돈이 나가면 아무도 안 고친다."""
    from app.routers.meetings import body_hash, 분석_걸어둔다

    class 가짜백그라운드:
        def __init__(self):
            self.걸린것 = []

        def add_task(self, fn, *a, **kw):
            self.걸린것.append((fn, a))

    db, r, m = _열기(회차)
    try:
        m.suggest_hash = body_hash(m)
        db.commit()
        bg = 가짜백그라운드()
        분석_걸어둔다(bg, m, db)
        assert bg.걸린것 == [], "같은 본문인데 또 걸었다"
        m.body = (m.body or "") + "\n- 한 줄 더"
        db.commit()
        bg2 = 가짜백그라운드()
        분석_걸어둔다(bg2, m, db)
        # **적는 동안에는 안 부른다** — 걸어 두기만 하고 잠잠해지면 돈다
        assert bg2.걸린것 == [], "저장하자마자 불렀다"
        assert m.suggest_state == "기다림"
        assert m.suggest_due_at is not None
    finally:
        db.close()


def test_llm_17b_낱말로_물러선_것은_키가_생기면_다시_읽는다(회차):
    """**두 가지를 한꺼번에 지킨다.**

    지문을 안 남기면 볼 때마다 "본문이 바뀐 것" 으로 읽혀 다시 돌고,
    화면이 **영원히 '읽는 중'** 이다 (브라우저에서 실제로 그랬다).
    그렇다고 지문만 남기면 키를 넣은 뒤에도 옛 결과가 남아 **영영 문장으로
    안 읽는다.** 그래서 지문은 언제나 남기고, 낱말로 물러선 것은
    **키가 생겼을 때만** 다시 읽는다.
    """
    from app.routers.meetings import body_hash, 다시_읽어야_하나

    db, r, m = _열기(회차)
    try:
        m.suggest_hash = body_hash(m)
        m.suggest_note = "낱말|아직 연결되지 않았습니다"
        db.commit()
        import app.domain.llm as L

        본래 = L.read_key
        try:
            L.read_key = lambda: None
            assert 다시_읽어야_하나(m) is False, "키도 없는데 또 부른다"
            L.read_key = lambda: "sk-ant-가짜"
            assert 다시_읽어야_하나(m) is True, "키가 생겼는데 안 읽는다"
        finally:
            L.read_key = 본래
        # 문장으로 읽은 것은 키가 있어도 다시 안 읽는다
        m.suggest_note = "문장|읽었습니다"
        db.commit()
        assert 다시_읽어야_하나(m) is False
    finally:
        db.close()


def test_llm_18_실패하면_다시_시도할_수_있다(회차, admin_client):
    src = (ROOT / "app" / "static" / "js" / "meeting.js").read_text(encoding="utf-8")
    assert "mt-retry" in src and "다시 시도" in src
    assert "/suggestions/rerun" in src
    res = admin_client.post(f"/meetings/{회차['meeting_id']}/suggestions/rerun")
    assert res.status_code == 200


# ── 19 · 20. 사람 평가 ───────────────────────────────────────────────


평가본문 = ("- 정하윤 : 경험 INFP\n"
        "\t- 비품관리 경험, 시키는거 잘함, 체력 약함\n"
        "- 명찰 스트랩 발주 건 논의\n")


@pytest.fixture
def 평가회의(회차):
    with app_session() as db:
        m = db.get(models.Meeting, 회차["meeting_id"])
        m.body = 평가본문
        db.commit()
    return 회차


def test_llm_19_사람_평가가_든_회의록에_표시가_남는다(평가회의, admin_client):
    res = admin_client.get(f"/meetings/{평가회의['meeting_id']}/suggestions")
    assert res.status_code == 200
    assert res.json()["people_notes"], "표시가 없다"
    js = (ROOT / "app" / "static" / "js" / "meeting.js").read_text(encoding="utf-8")
    assert "사람에 대한 평가" in js, "화면에 안 보인다"


def test_llm_20_그_대목이_제안에_인용되지_않는다(평가회의):
    """**보내는 것과 남기는 것은 다르다.** 논의로 남으면 회차를 볼 수 있는
    누구나 보게 된다 (4-9)."""
    db, r, m = _열기(평가회의)
    try:
        결과 = S.분석(db, retreat=r, meeting=m, 부르기=부르기를(가짜대답(json.dumps({
            "결정사항": [{"인용": "\t- 비품관리 경험, 시키는거 잘함, 체력 약함",
                      "무엇": "역할을 나눴습니다"}],
            "논의후보": [{"run_id": 평가회의["run_ids"][1],
                     "왜": "정하윤은 체력 약함이라 스트랩 발주를 맡깁니다"}],
            "새업무": [{"제목": "체력 약함 정리", "왜": "회의에 나왔습니다"}],
        }, ensure_ascii=False))))
    finally:
        db.close()
    assert 결과.사람평가, "평가 줄을 못 짚었다"
    for x in 결과.제안들:
        붙인것 = " ".join(filter(None, [x.text, x.why, x.quote, x.title]))
        assert "체력 약함" not in 붙인것, f"평가가 제안에 남았다: {붙인것}"
    assert not [x for x in 결과.제안들 if x.kind == "decision"], \
        "평가를 인용한 결정사항이 그대로 나왔다"


# ── 21 · 22. 견주기 ──────────────────────────────────────────────────


def test_llm_21_표본_네_회의를_다시_내는_길이_있다():
    src = (ROOT / "scripts" / "suggest_sample.py").read_text(encoding="utf-8")
    for 제목 in ("26.03.29 (1차)", "26.05.24", "26.07.05", "26.08.09"):
        assert 제목 in src, f"표본에서 {제목} 이 빠졌다"
    # **키가 없으면 아무것도 안 쓴다.** 낱말로 물러선 것을 2판이라 적으면
    # 견주는 두 숫자가 같은 방식의 것이 되어 아무것도 재지 못한다
    assert "raise SystemExit(2)" in src
    # **네트워크가 끊겨 낱말로 물러선 것도 2판이라고 적으면 안 된다.**
    # 키만 보던 것으로는 부족했다 — 실제로 그렇게 적힌 적이 있다
    assert 'r.방식 != "문장"' in src and "raise SystemExit(3)" in src

    문서 = (ROOT / "docs" / "review" / "제안-2판.md").read_text(encoding="utf-8")
    assert "비율" in 문서
    assert "마땅히 나왔어야 하는데" in 문서, "놓친 것을 묻는 칸이 없다"


def test_llm_22_성적표에_놓친_것_칸이_생겼다():
    """**맞은 비율만 세면 적게 내는 쪽으로 점수를 올릴 수 있다.**"""
    문서 = (ROOT / "docs" / "review" / "제안-성적표.md").read_text(encoding="utf-8")
    assert "놓친 것" in 문서
    assert "마땅히 나왔어야 하는데" in 문서
    src = (ROOT / "scripts" / "suggest_sample.py").read_text(encoding="utf-8")
    assert "마땅히 나왔어야 하는데 안 나온 것이 있나요?" in src


# ── 창구가 하나인가 ──────────────────────────────────────────────────


def test_llm_23_API_로_나가는_문이_하나다():
    """두 벌이 되면 키를 읽는 법·모델·요금이 갈리고, **갈린 쪽을 아무도
    눈치채지 못한다.**"""
    나온것 = sorted(
        str(p.relative_to(ROOT)).replace("\\", "/")
        for d in ("app", "scripts")
        for p in (ROOT / d).rglob("*.py")
        if "api.anthropic.com" in p.read_text(encoding="utf-8", errors="ignore"))
    assert 나온것 == ["app/domain/llm.py"], f"주소가 여러 곳에 있다: {나온것}"


# ── 채점을 덮어쓰지 못하게 막는가 (2026-09-04) ────────────────────────
#
# **가드는 통과하는 쪽만 시험돼 있었다.** 실제로 채워 넣고 돌려 보니 셋 중
# 둘만 잡았다 — 마크다운 3열 행은 `split("|")` 이 4개가 아니라 **5개**인데
# 4로 세어 「놓친 것」 표를 놓쳤다. **조용히 절반만 지키는 가드가 가장
# 위험하다**: 있는 줄 알고 안심한다. 그래서 막히는 쪽을 시험한다.

def _스크립트():
    import importlib.util
    스펙 = importlib.util.spec_from_file_location(
        "_ss", ROOT / "scripts" / "suggest_sample.py")
    모듈 = importlib.util.module_from_spec(스펙)
    스펙.loader.exec_module(모듈)
    return 모듈


# 사람이 채울 수 있는 자리마다 하나씩. **자리가 늘면 여기 한 줄 더한다.**
#
# **목록은 여기 한 벌뿐이다.** 2026-09-04 에 같은 목록을
# `tests/test_check_names.py` 에 한 벌 더 만들었고, 늘어난 자리
# (「03.29 #1 자리」)가 새 벌에만 들어가 **`test_가드_03` 이 보증한다고
# 적어 둔 「자리마다 빠짐없이」 가 사실이 아니게 됐다.** 그때 새 벌의
# 주석은 "exit 4·5 는 손 실행으로만 확인됐다 · import_programs.py 는
# 시험이 있는데 여기만 없었다" 였는데 **사실이 아니었다** —
# `test_가드_02`·`test_가드_03` 이 이미 단언하고 있었다.
# **"없었다" 가 아니라 "못 봤다" 다.** 그래서 다시 한 벌로 모았다.
채운자리 = [
    ("판정 칸",     "| 논의 | 「가」 (run 1) | 왜 | O | |"),
    ("X 이유 칸",   "| 논의 | 「가」 (run 1) | 왜 | | 다른업무 |"),
    ("놓친 것 줄",  "**마땅히 나왔어야 하는데 안 나온 것이 있나요?**  O / X  → O"),
    ("놓친 것 표",  "| 26.05.24 | O | 톡방광고 담당자 |"),
    ("X 이유 표",   "| `할일아님` | 2 |"),
    ("03.29 #1 자리", "→ `다른업무` / `할일아님` / `중복` / `기타` 중: 다른업무"),
]


@pytest.mark.parametrize("이름,줄", 채운자리, ids=[x[0] for x in 채운자리])
def test_가드_01_채운_자리를_저마다_잡는다(이름, 줄):
    """자리마다 **실제로 거부되는지** 본다. 한 자리라도 새면 그 자리의
    판정이 조용히 지워진다."""
    찾음 = _스크립트().채운곳(줄)
    assert 찾음, f"{이름} 이 채워졌는데 못 잡았다: {줄!r}"


def test_가드_02_안_채운_파일은_덮인다(tmp_path):
    """**과하게 걸려 정작 다시 못 내면 그것도 고장이다.**"""
    ss = _스크립트()
    빈것 = "\n".join([
        "| 종류 | 무엇을 하자는 것 | 근거 / 인용 | 판정 | X 이유 |",
        "|---|---|---|---|---|",
        "| 논의 | 「가」 (run 1) | 왜 | | |",
        "**마땅히 나왔어야 하는데 안 나온 것이 있나요?**  O / X  → ",
        "| 26.05.24 | | |",
        "| `할일아님` | |",
        # **안 채운 모양도 넣는다.** 이 자리를 고친 계기가 정확히
        # 과잉 차단이었다 — 사람이 채운 적 없는데 `--replace` 가
        # 막혔다. 막히는 쪽만 시험하면 그 방향이 안 지켜진다
        "→ `다른업무` / `할일아님` / `중복` / `기타` 중: ______",
    ])
    assert ss.채운곳(빈것) == [], "안 채운 파일을 채웠다고 본다"
    p = tmp_path / "빈것.md"
    p.write_text(빈것, encoding="utf-8")
    ss.막는다(p, replace=True)              # 안 막아야 한다
    with pytest.raises(SystemExit) as e:
        ss.막는다(p, replace=False)         # --replace 없으면 막아야 한다
    assert e.value.code == 5


def test_가드_03_자리마다_빠짐없이_걸린다(tmp_path):
    """**"적어도 한 곳" 이 아니라 "자리마다" 를 본다.**

    한 덩어리로 넣고 "뭔가 잡혔다" 로만 보면, 새 표를 더하고 가드에 안
    넣어도 앞의 자리가 잡혀서 통과한다. 자리를 **줄 번호로** 견주므로
    빠뜨린 표의 줄이 안 잡히고, 그 이름이 그대로 실패 문구에 나온다.
    """
    ss = _스크립트()
    글 = "\n".join(줄 for _, 줄 in 채운자리)
    찾음 = ss.채운곳(글)
    잡힌줄 = {int(x.split("줄")[0]) for x in 찾음}
    안잡힌것 = [이름 for i, (이름, _) in enumerate(채운자리, 1)
              if i not in 잡힌줄]
    assert not 안잡힌것, f"가드가 이 자리를 안 지킨다: {안잡힌것}"
    assert len(찾음) == len(채운자리), (
        f"{len(채운자리)}자리를 채웠는데 {len(찾음)}곳만 잡았다: {찾음}")
    p = tmp_path / "채운것.md"
    p.write_text(글, encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        ss.막는다(p, replace=True)          # --replace 로도 막아야 한다
    assert e.value.code == 4


def test_가드_04_모르는_종류를_표에_찍지_않는다():
    """모르는 종류를 제안처럼 찍으면 `제안줄인가()` 가 못 알아보고,
    그러면 **덮어쓰기 가드가 그 줄의 판정을 지키지 않는다.**"""
    ss = _스크립트()
    class 가짜:
        kind, text, why = "더있음", "이름이 겹치는 업무가 7건 더 있습니다", ""
    with pytest.raises(ValueError) as e:
        ss.한줄(가짜())
    assert "더있음" in str(e.value)
    # 그리고 **세는 곳도 같은 목록을 본다**
    assert ss.센다([가짜()]) == 0
    assert set(ss.제안종류.values()) == {"결정사항", "논의", "새 업무"}
    for 이름 in ss.제안종류.values():
        assert ss.제안줄인가(f"| {이름} | 가 | 나 | | |"), 이름
    assert not ss.제안줄인가("| 더있음 | 가 | 나 | | |")


def test_가드_05_도출된_판정은_지키지_않는다():
    """`O(도출)` 은 성적표에서 기계적으로 나온 것이라 다시 만들 수 있다.
    사람이 손으로 적은 것만 지킨다 — 안 그러면 영영 다시 못 낸다."""
    ss = _스크립트()
    assert ss.채운곳("| 논의 | 「가」 (run 1) | 왜 | O(도출) | |") == []
    assert ss.채운곳("| 논의 | 「가」 (run 1) | 왜 | O | |")


def test_가드_06_대조표는_사람이_채운_것이_아니다():
    """「2판과의 대조」 표의 둘째 칸은 **스크립트가 적은 것**이다.
    모양만 보면 「놓친 것」 표와 같아서(`| 26.xx | a | b |`), 오인하면
    영영 못 덮는다 — 표 머리를 보고 가른다."""
    ss = _스크립트()
    글 = ("| 회의 | 1판이 맞힌 것 (도출) | 2판에도 있나 |\n"
          "| 26.05.24 | 논의 · 「가」 (run 1) | |")
    assert ss.채운곳(글) == [], "스크립트가 적은 칸을 사람 몫으로 봤다"
    assert ss.채운곳(글 + "\n| 26.08.09 | 논의 · 「나」 (run 2) | O |")


# ── 낱말 겹침은 결정적인가 (2026-09-04) ──────────────────────────────
#
# "낱말 겹침은 결정적이고 Claude 를 부르지 않는다 — 보드와 회의록이
# 그대로면 같은 것이 나온다" 가 **1판 목록을 다시 낼 수 있는 근거**다.
# 그 말이 세 곳에 적혀 있었는데(`suggest_sample.py` 머리말 · 성적표 ·
# CLAUDE.md) **그것을 보는 시험이 하나도 없었다.**
#
# 실제로는 `sorted(..., key=len)` 이라 길이가 같은 낱말끼리 set 순서를
# 따라가 **실행마다 갈렸다.** 돌릴 때마다 뜻 없는 diff 가 났다.

def test_겹침_01_같은_길이의_낱말도_순서가_정해져_있다():
    from app.domain.suggest import 겹침
    글, 이름 = "가나 다라 마바 사아", "사아 마바 다라 가나"
    _, 낱말 = 겹침(글, 이름)
    assert 낱말 == sorted(낱말), f"같은 길이끼리 순서가 안 정해져 있다: {낱말}"


def test_겹침_02_해시씨앗을_바꿔도_같은_결과다():
    """**같은 프로세스 안에서는 set 순서가 고정된다.** 그래서 다른
    프로세스로 여러 씨앗을 돌려야 갈리는 것이 보인다."""
    import json
    import os
    import subprocess
    import sys as _sys

    코드 = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from app.domain.suggest import 겹침\n"
        "글 = '가나 다라 마바 사아 자차 카타 파하'\n"
        "이름 = '파하 카타 자차 사아 마바 다라 가나'\n"
        "import json; print(json.dumps(겹침(글, 이름)[1], ensure_ascii=False))\n"
        % str(ROOT)
    )
    나온것 = set()
    for 씨앗 in ("0", "1", "2", "3", "4"):
        환경 = {**os.environ, "PYTHONHASHSEED": 씨앗, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([_sys.executable, "-c", 코드], capture_output=True,
                           text=True, encoding="utf-8", env=환경, cwd=str(ROOT))
        assert r.returncode == 0, r.stderr[:300]
        나온것.add(json.dumps(json.loads(r.stdout.strip()), ensure_ascii=False))
    assert len(나온것) == 1, f"해시 씨앗마다 결과가 갈린다: {나온것}"


def test_가드_07_공개본이_채워져_있으면_돈을_쓰기_전에_멈춘다(tmp_path, monkeypatch):
    """**소스를 읽지 않고 실제로 부른다.**

    전에는 소스 글자의 *자리*만 봤다 — 찾는 문자열이
    `"막는다(공개곳[out.name]"` 까지라 둘째 인자를 `True` 로 되돌려도
    통과했다. **고친 고장을 지키는 단언이 하나도 없었다.**
    10장이 네 번 당했다고 적어 둔 그 모양이다.
    """
    ss = _스크립트()
    실명본 = tmp_path / "제안-2판.real.md"
    공개본 = tmp_path / "제안-2판.md"
    monkeypatch.setitem(ss.공개곳, 실명본.name, 공개본)

    # ① 공개본에 사람이 채운 것이 있으면 — .real 이 없어도 막는다
    공개본.write_text("| 논의 | 「가」 (run 1) | 왜 | O | |", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        ss.막는다(ss.공개곳[실명본.name], replace=True)
    assert e.value.code == 4

    # ② 안 채웠는데 `--replace` 가 없으면 **무엇을 덮는지 말하고** 멈춘다.
    #    전에는 `replace=True` 가 박혀 있어 이 갈래가 아예 안 걸렸다 —
    #    `.real` 이 없고 공개본만 있을 때 말없이 덮였다
    공개본.write_text("| 논의 | 「가」 (run 1) | 왜 | | |", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        ss.막는다(ss.공개곳[실명본.name], replace=False)
    assert e.value.code == 5

    # ③ `--replace` 를 주면 덮는다 — 과하게 걸려도 고장이다
    ss.막는다(ss.공개곳[실명본.name], replace=True)


def test_가드_07b_공개본_검사에_replace_를_그대로_넘긴다(tmp_path, monkeypatch, capsys):
    """`main` 이 공개본 가드를 부를 때 `args.replace` 를 그대로
    넘기는지 — `True` 를 박아 두면 「이미 있는 것을 덮게 됩니다」 갈래가
    영영 안 걸린다. **실제로 `main()` 을 부른다.**
    """
    import sys as _sys
    ss = _스크립트()
    실명본 = tmp_path / "제안-1판.real.md"
    공개본 = tmp_path / "제안-1판.md"
    공개본.write_text("| 논의 | 「가」 (run 1) | 왜 | | |", encoding="utf-8")
    monkeypatch.setitem(ss.공개곳, 실명본.name, 공개본)
    monkeypatch.setattr(_sys, "argv",
                        ["suggest_sample.py", "--retreat", "없는회차",
                         "--낱말", "--공개", "--out", str(실명본)])
    with pytest.raises(SystemExit) as e:
        ss.main()
    말 = capsys.readouterr().out
    # `--replace` 를 안 줬으므로 **덮게 되는 것을 말하고** 멈춰야 한다.
    # `replace=True` 가 박혀 있으면 이 검사를 그냥 지나쳐 회차를 찾다가
    # 다른 곳에서 죽는다
    assert e.value.code == 5, f"공개본 가드를 지나쳤다: {말[-300:]}"
    assert "덮게 됩니다" in 말, 말[-300:]


def test_가드_07c_공개본_검사가_키_검사보다_앞이다(tmp_path, monkeypatch, capsys):
    """**소스를 읽지 않고 순서를 잰다.**

    전에는 `main()` 소스에서 `.index()` 로 자리를 견줬다 — 코드가
    어떻게 생겼는지를 본 것이지 무엇을 하는지가 아니다.

    실제로 재는 방법: **키를 없애고** 공개본에 사람이 채운 것을 둔 채
    부른다. 공개본 검사가 앞이면 **가드(4)** 로 멈추고, 뒤집히면
    **키 오류(2)** 가 난다. 두 숫자가 순서를 그대로 말한다.

    순서가 왜 중요한가 — 키 검사가 앞이면 키가 있는 사람은 그냥
    지나가서, **돈을 다 쓰고 `.real` 을 덮은 뒤에** 멈춘다.
    그때 「아무것도 쓰지 않았습니다」 가 거짓말이 된다.
    """
    import sys as _sys
    import types
    ss = _스크립트()
    실명본 = tmp_path / "제안-2판.real.md"      # 없다 — 앞의 가드는 지나간다
    공개본 = tmp_path / "제안-2판.md"
    공개본.write_text("| 논의 | 「가」 (run 1) | 왜 | O | |", encoding="utf-8")
    monkeypatch.setitem(ss.공개곳, 실명본.name, 공개본)
    # **키를 없앤다.** `--낱말` 을 쓰면 키 검사 자체를 건너뛰어
    # 순서를 잴 수 없다 — 두 검사가 다 도는 길로 부른다
    monkeypatch.setattr(ss.llm_mod, "상태",
                        lambda: types.SimpleNamespace(ok=False, 말="시험"))
    monkeypatch.setattr(_sys, "argv",
                        ["suggest_sample.py", "--retreat", "없는회차",
                         "--공개", "--out", str(실명본)])
    with pytest.raises(SystemExit) as e:
        ss.main()
    말 = capsys.readouterr().out
    assert e.value.code == 4, (
        f"키 검사가 먼저 걸렸다 — 공개본 검사가 뒤에 있다: {말[-300:]}")
    assert "아무것도 쓰지 않았습니다" in 말, 말[-300:]
    assert not 실명본.exists(), "멈추기 전에 .real 을 썼다"


# ── 증감말() — 한 번도 실행된 적 없던 갈래들 ────────────────────────
#
# 「합계는 같은데 회의별로 갈렸다」 갈래가 만들어진 뒤 **한 번도 실행되지
# 않았다.** 대응표 겹침 거절 경로가 `NameError` 였던 것과 같은 자리다.

def _묶음(*값):
    import types
    def 회의(제목, d, disc, new):
        r = types.SimpleNamespace(제안들=[types.SimpleNamespace(kind=k)
                                       for k in ["decision"] * d
                                       + ["discussion"] * disc + ["new"] * new])
        return (types.SimpleNamespace(title=제목), r)
    return [회의(*x) for x in 값]


def test_증감_01_합계는_같은데_회의별로_갈리면_낸다():
    """**합계만 같고 회의별로 크게 갈렸을 때가 바로 그 경고가 필요한
    때다** — 전에는 그때 문단이 통째로 사라졌다."""
    ss = _스크립트()
    # 논의 합계는 13 그대로, 05.24 가 -2 · 08.09 가 +2
    줄 = ss.증감말(_묶음(("26.03.29 (1차)", 1, 1, 1), ("26.05.24", 5, 3, 5),
                     ("26.07.05", 1, 4, 0), ("26.08.09", 5, 5, 2)))
    글 = "\n".join(줄)
    assert 줄, "합계가 같다고 문단이 통째로 사라졌다"
    assert "그대로인데 회의별로는 갈렸습니다" in 글, 글
    assert "26.05.24" in 글 and "26.08.09" in 글


def test_증감_02_논의만_보고_판단하지_않는다():
    """**넣는 조건과 판단하는 값이 같아야 한다.**

    넣는 조건은 (논의, 새 업무) 둘 다인데 판단은 논의만 봤다 —
    논의 3→3 · 새 업무 2→4 인 회의에 「늘었」 이 안 붙었다.

    전에는 `"반대로" not in 글` 로 봤는데 **그 낱말은 코드가 내는
    글에 들어갈 길이 하나도 없었다** — 주석과 이 독스트링에만
    있어서, 고장이 살아 있어도 초록이었다 (10장).
    그래서 **값이 아니라 갈래**를 본다.
    """
    ss = _스크립트()
    줄 = ss.증감말(_묶음(("26.03.29 (1차)", 1, 1, 1), ("26.05.24", 5, 5, 5),
                     ("26.07.05", 1, 4, 0), ("26.08.09", 5, 3, 4)))
    그줄 = next((x for x in 줄 if x.startswith("26.08.09")), None)
    assert 그줄, f"바뀐 회의가 목록에 없다: {줄}"
    # 논의는 3→3 으로 그대로이고 새 업무만 2→4 다 — 합으로 보면 「늘었」
    assert "늘었" in 그줄, f"논의만 보고 판단했다: {그줄}"
    assert "줄었" not in 그줄, f"합이 +2 인데 줄었다고 한다: {그줄}"


def test_증감_03_전부_늘어났으면_줄어든_것을_말하지_않는다():
    ss = _스크립트()
    줄 = ss.증감말(_묶음(("26.03.29 (1차)", 1, 3, 3), ("26.05.24", 5, 7, 7),
                     ("26.07.05", 1, 6, 2), ("26.08.09", 5, 5, 4)))
    글 = "\n".join(줄)
    assert 줄, "늘어나기만 했다고 문단이 사라졌다"
    assert "줄어든 것이" not in 글, f"전부 늘었는데 「줄어든 것이」 가 나왔다: {글}"


def test_증감_04_아무것도_안_바뀌면_안_낸다():
    """**과하게 내도 고장이다.** 할 말이 없으면 빈 값을 낸다."""
    ss = _스크립트()
    assert ss.증감말(_묶음(("26.03.29 (1차)", 1, 1, 1), ("26.05.24", 5, 5, 5),
                       ("26.07.05", 1, 4, 0), ("26.08.09", 5, 3, 2))) == []


def test_증감_05_회의가_빠지면_그렇게_말한다():
    """**이 갈래가 만들어진 뒤 한 번도 안 돌고 있었다.**

    `test_증감_01~04` 가 넷 다 표본 네 회의를 모두 넣어서다. 처음 도는
    때는 표본 하나가 `! 회의록 없음` 으로 건너뛰는 때 — **그때가 그
    문장이 필요한 때다.** 안 읽은 것이 아니라 안 낸 것인데 「줄었다」 로
    말하면 이 문단의 물음이 흐려진다.
    """
    ss = _스크립트()
    줄 = ss.증감말(_묶음(("26.03.29 (1차)", 1, 0, 0), ("26.05.24", 5, 1, 3),
                     ("26.08.09", 5, 5, 4)))          # 07.05 를 뺐다
    글 = "\n".join(줄)
    assert "빠졌습니다" in 글, f"빠진 회의를 말하지 않는다: {글}"
    assert "26.07.05" in 글, f"어느 회의가 빠졌는지 말하지 않는다: {글}"
    assert "든 회의만" in 글, "센 범위를 밝히지 않는다"
    # **든 회의만 센다** — 03.29·05.24·08.09 의 1판 논의는 1+5+3 = 9
    assert "9 " in 글, f"빠진 회의까지 세고 있다: {글}"
    assert "13" not in 글.split("빠졌습니다")[-1], (
        f"고정값 13 을 그대로 쓴다: {글}")
