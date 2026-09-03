"""첫 실제 결과가 기준선보다 나빴던 이유 (CLAUDE.md 4-10 · 6-9).

**무슨 일이 있었나.** 키를 넣고 처음 돌린 `26.08.09` 가 빈 목록이었다 —
낱말 겹침이 5개 중 4개를 맞힌 회의인데. 답 원문을 받아 보니

    stop_reason: max_tokens · output_tokens 4000 (그중 thinking 3042)
    "왜": "홍보영상의 8/9, 8/16 공개 일정과 쇼츠 2개 공유 방   ← 문장 한가운데

**답은 왔는데 잘려서 못 읽은 것**이었다. 잘린 JSON 은 `{}` 가 되고 화면에는
"낼 것을 찾지 못했습니다" 가 떴다 — 모델이 판단해서 없는 것과 **같은 모양**.
보고서가 "구별되지 않는 실패가 가장 비싸다" 고 적어 둔 바로 그 자리다.

여기 시험은 그 셋을 지킨다 — 잘린 것을 알아보는가 · 모르는 상태를 주장하지
않는가 · 적는 동안 부르지 않는가. **실제 API 는 부르지 않는다.**
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

from app import models
from app.domain import llm as llm_mod
from app.domain import suggest as S
from tests.conftest import app_session
from tests.test_suggest_llm import 가짜대답, 부르기를, _열기, 회차  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ── 4. 답은 왔는데 못 읽은 경우를 `실패` 로 나눈다 ───────────────────


def test_re_04_잘린_답을_실패로_나눈다(회차):
    """**모델이 없다고 한 것과 우리가 못 읽은 것은 다른 일이다.**"""
    잘린것 = 가짜대답('{"결정사항": [{"인용": "- 승합차 몇개 필요한지", "왜": "승합차 대수를 정')
    잘린것.stop_reason = "max_tokens"
    잘린것.thinking_tokens = 3042
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m, 부르기=부르기를(잘린것))
    finally:
        db.close()
    assert 결과.실패 is True, "잘린 답을 '할 말이 없다' 로 삼켰다"
    assert "잘렸" in 결과.말
    assert "3,042" in 결과.말, "생각에 얼마를 썼는지가 없다"
    # **빈 목록으로 두지 않는다** — 낱말로 물러선다.
    # (이 시험 자료로는 낱말도 낼 것이 없을 수 있다. 지켜야 할 것은
    #  "물러섰다는 사실과 그 까닭이 남는가" 이지 개수가 아니다)
    assert 결과.방식 == "낱말"


def test_re_04b_JSON_이_아닌_답도_실패다(회차):
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m,
                   부르기=부르기를(가짜대답("죄송합니다. 답을 드릴 수 없습니다.")))
    finally:
        db.close()
    assert 결과.실패 is True
    assert "읽지 못했습니다" in 결과.말


def test_re_04c_진짜_빈_답은_실패가_아니다(회차):
    """조건 4 — 할 말이 없으면 빈 목록이 **정상**이다. 50건 중 24건이 그렇다."""
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m,
                   부르기=부르기를(가짜대답('{"결정사항":[],"논의후보":[],"새업무":[]}')))
    finally:
        db.close()
    assert 결과.실패 is False and 결과.방식 == "문장" and 결과.제안들 == []


def test_re_04d_상한이_생각까지_감당한다():
    """생각에 3,042 를 쓰고 남은 958 로 답을 쓰다 말았다."""
    assert llm_mod.MAX_TOKENS >= 8000, "생각 몫을 빼면 답이 또 잘린다"
    src = (ROOT / "app" / "domain" / "llm.py").read_text(encoding="utf-8")
    assert "stop_reason" in src and "thinking_tokens" in src
    assert "잘렸나" in src, "왜 멈췄는지를 알아보는 길이 없다"


# ── 5. 걸러서 빈 것도 그렇다고 말한다 ───────────────────────────────


def test_re_05_걸러서_빈_것도_말한다(회차):
    """**조용히 사라지면 "할 말이 없다" 와 구별되지 않는다.**"""
    with app_session() as db:
        m = db.get(models.Meeting, 회차["meeting_id"])
        m.body = ("- 정하윤 : 경험 INFP\n"
                  "\t- 비품관리 경험, 시키는거 잘함, 체력 약함\n")
        db.commit()
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m, 부르기=부르기를(가짜대답(json.dumps({
            "결정사항": [{"인용": "\t- 비품관리 경험, 시키는거 잘함, 체력 약함",
                      "무엇": "역할을 나눴습니다"}],
            "논의후보": [], "새업무": [],
        }, ensure_ascii=False))))
    finally:
        db.close()
    assert 결과.제안들 == [], "평가가 그대로 나왔다"
    assert 결과.걸러낸것, "무엇을 걸렀는지 안 남겼다"
    assert "사람 평가가 섞여" in 결과.말, "화면이 왜 비었는지 말하지 않는다"


def test_re_05b_없는_번호도_말한다(회차):
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m, 부르기=부르기를(가짜대답(json.dumps({
            "결정사항": [], "새업무": [],
            "논의후보": [{"run_id": 999999, "왜": "없는 업무입니다"}],
        }, ensure_ascii=False))))
    finally:
        db.close()
    assert 결과.제안들 == []
    assert "목록에 없는 번호" in 결과.말


# ── 6. 모르는 상태를 '대기' 라고 말하지 않는다 ──────────────────────


def test_re_06_모르는_상태를_주장하지_않는다(회차):
    """`started_at`·`completed_at` 이 비면 **모르는 것**이다.

    옮겨 온 자료는 그 둘이 비어 96건이 전부 '대기' 로 나갔다. 구별에
    기여하지 않으면서 토큰만 먹고, **8월에 끝난 일도 '대기' 로 보인다.**
    """
    with app_session() as db:
        for run in db.query(models.TaskRun).filter_by(retreat_id=회차["retreat_id"]):
            run.started_at = None
            run.completed_at = None
            run.status = "완료"          # 오늘의 값 — 이것을 읽으면 안 된다
        db.commit()
    db, r, m = _열기(회차)
    try:
        rows = S.board_as_of(db, r, dt.date(2026, 6, 1))
        목록 = S.catalog(rows)
    finally:
        db.close()
    assert all(x.status is None for x in rows), "모르는데 '대기' 라고 한다"
    assert "· 대기" not in 목록, "목록에 '대기' 가 나간다"
    # **빠진 것이 곧 '모름'** 이라는 뜻을 한 줄로 밝힌다
    assert "모르는 것" in 목록 and "아직 안 한 일이라는 뜻이 아닙니다" in 목록


def test_re_06b_아는_상태는_그대로_적는다(회차):
    """날짜가 있으면 아는 것이다 — 빼면 안 된다."""
    db, r, m = _열기(회차)
    try:
        줄들 = S.catalog(S.board_as_of(db, r, dt.date(2026, 6, 1))).splitlines()
    finally:
        db.close()
    붙은것 = [x for x in 줄들 if x.startswith("[") and
            x.rstrip().endswith(("대기", "진행중", "완료"))]
    assert 붙은것, "아는 상태까지 빼 버렸다"


# ── 8. 잰 토큰을 남긴다 ─────────────────────────────────────────────


def test_re_08_잰_토큰을_남긴다(회차):
    """어림한 37~43원이 실제로는 113원이었다 — 세 배다."""
    답 = 가짜대답('{"결정사항":[],"논의후보":[],"새업무":[]}', 원=113.0)
    답.in_tokens, 답.out_tokens, 답.thinking_tokens = 6815, 4000, 3042
    db, r, m = _열기(회차)
    try:
        결과 = S.분석(db, retreat=r, meeting=m, 부르기=부르기를(답))
    finally:
        db.close()
    assert 결과.입력토큰 == 6815 and 결과.출력토큰 == 4000
    assert 결과.생각토큰 == 3042
    assert "6,815/4,000" in 결과.말, "화면에 잰 토큰이 없다"

    # 저장도 한다 — 나중에 되짚어 볼 수 있어야 한다
    src = (ROOT / "app" / "routers" / "meetings.py").read_text(encoding="utf-8")
    assert "meeting.suggest_tokens" in src


def test_re_09_문서의_추정이_실측으로_바뀌었다():
    """**추정이 남아 있으면 다음 사람이 그 숫자로 판단한다.**"""
    # **찾는 말이 설명글에 있으면 시험이 거짓말을 한다** — 10장이 네 번
    # 당했다고 적은 그것에 다섯 번째로 걸렸다. `llm.py` 의 머리말은 "옛 어림이
    # 왜 틀렸는지" 를 적으려고 그 숫자를 **일부러** 인용한다. 코드만 본다.
    import ast

    소스 = (ROOT / "app" / "domain" / "llm.py").read_text(encoding="utf-8")
    나무 = ast.parse(소스)
    for 마디 in ast.walk(나무):
        if isinstance(마디, ast.Constant) and isinstance(마디.value, str):
            소스 = 소스.replace(마디.value, "")
    assert "0.6~0.75" not in 소스, "코드가 옛 어림을 쓴다"

    안내글 = (ROOT / "docs" / "배포-안내.md").read_text(encoding="utf-8")
    쓰는자리 = 안내글[안내글.index("### 14-5"):]
    assert "0.6~0.75 토큰으로 보면" not in 쓰는자리, "안내에 옛 어림이 남았다"
    안내 = (ROOT / "docs" / "배포-안내.md").read_text(encoding="utf-8")
    장 = 안내[안내.index("## 14."):]
    assert "실제로 잰" in 장 or "실측" in 장
    assert "thinking" in 장 or "생각" in 장, "값의 대부분이 어디로 가는지 없다"


# ── 10 · 11. 적는 동안은 부르지 않는다 ──────────────────────────────


def test_re_10_저장_뒤_잠잠할_때_부른다(회차):
    """오타 세 번 고치면 세 번 부르던 것을 멈춘다."""
    from app.routers.meetings import 분석_걸어둔다, 때가_됐나

    class 가짜백그라운드:
        def __init__(self): self.걸린것 = []
        def add_task(self, fn, *a, **kw): self.걸린것.append(fn)

    db, r, m = _열기(회차)
    try:
        bg = 가짜백그라운드()
        분석_걸어둔다(bg, m, db)
        assert bg.걸린것 == [], "저장하자마자 불렀다"
        assert m.suggest_state == "기다림"
        assert m.suggest_due_at is not None and not 때가_됐나(m)

        # 때가 되면 돈다
        m.suggest_due_at = dt.datetime.now() - dt.timedelta(seconds=1)
        db.commit()
        assert 때가_됐나(m)
    finally:
        db.close()


def test_re_11_지금_받는_길이_있다(회차, admin_client):
    """**기다리는 길만 있으면 안 된다.**"""
    from app.routers.meetings import 분석_걸어둔다

    class 가짜백그라운드:
        def __init__(self): self.걸린것 = []
        def add_task(self, fn, *a, **kw): self.걸린것.append(fn)

    db, r, m = _열기(회차)
    try:
        bg = 가짜백그라운드()
        분석_걸어둔다(bg, m, db, 지금=True)
        assert len(bg.걸린것) == 1, "지금 눌러도 기다린다"
        assert m.suggest_state == "도는중"
    finally:
        db.close()

    js = (ROOT / "app" / "static" / "js" / "meeting.js").read_text(encoding="utf-8")
    assert "지금 읽기" in js
    assert "다 적으신 뒤 읽습니다" in js, "왜 기다리는지 화면이 말하지 않는다"
    res = admin_client.post(f"/meetings/{회차['meeting_id']}/suggestions/rerun")
    assert res.status_code == 200


# ── 12. 물러선 제안을 반영하면 그 사실이 남는다 ─────────────────────


def test_re_12_어떤_방식으로_고른_것인지_남는다(회차, admin_client):
    """낱말로 물러선 것과 문장을 읽고 고른 것이 둘 다 `claude` 다 —
    **이것이 없으면 나중에 구별되지 않는다.**"""
    with app_session() as db:
        m = db.get(models.Meeting, 회차["meeting_id"])
        m.suggest_note = "낱말|아직 연결되지 않았습니다"
        db.commit()
    admin_client.post(f"/meetings/{회차['meeting_id']}/suggestions/apply",
                      json={"run_id": 회차["run_ids"][1]})
    with app_session() as db:
        기록 = db.query(models.ActivityLog).filter_by(
            action="회의록_제안_반영").order_by(models.ActivityLog.id.desc()).first()
    assert 기록 is not None
    assert "낱말" in (기록.summary or ""), f"방식이 안 남았다: {기록.summary}"
    assert (기록.after_value or {}).get("고른방식") == "낱말"
