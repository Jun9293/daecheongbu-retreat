"""회의록 옮기기와 시뮬레이션 (CLAUDE.md 회의록 1·3·4단계).

**시험 자료에 실명이 없다.** 실제 회의록에는 실명이 그대로 들어 있어서
`data/notion-meetings/` 는 저장소에 두지 않는다. 여기 붙인 것은 **실제 원본과
같은 모양으로 지어낸 것**이고 이름은 전부 가명이다 (11-2).
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from sqlalchemy import select

from app import models
from app.domain.meeting_import import cut, people_notes
from app.domain.suggest import board_as_of, simulate, suggest, 판정단어
from tests.conftest import app_session

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 실제 원본과 **같은 함정들**을 담은 가짜 페이지.
#   · `<details><summary>` 안의 날짜
#   · 문장 속 빨간 굵은 강조 (`정해야함`)
#   · 회의 **안에** 중첩된 날짜 토글 (`26.04.22 1차 구상안`)
#   · 날짜 없는 덩어리 (`특정일 없음`)
#   · 형광펜
#   · 사람 평가 (MBTI · `체력 약함`)
샘플 = """---
notion_title: 시험용 회의록
---
## 행사 개요
[표: 주제 · 장소 · 일시]
## 논의 내용
<span color="red">**26.07.26**</span>
- 구매목록 취합
	- <span color="yellow_bg">시설에 대걸레 있는지 문의</span>
- 중그룹 상품 - <span color="red">**정해야함**</span> - 박민준
<span color="red">**26.07.25 (행정팀)**</span>
- <span color="yellow_bg">시설에 대걸레 있는지 문의</span>
<span color="red">**26.06.21**</span>
- 정하윤 : 경험 INFP
	- 비품관리 경험, 시키는거 잘함, 체력 약함
- 최도현 ENFJ
	- 적응잘함, 사람챙기기 잘함
<details>
<summary><span color="red">**26.04.22 (4차 확정)**</span></summary>
	- 주제 확정
	<details>
	<summary><span color="red">**26.04.22 1차 구상안**</span> ⇒ 나중에 다시 본다</summary>
		- 도면 확인
	</details>
</details>
---
<span color="red">**모임 전 수시로 정리한 내용들 (특정일 없음)**</span>
- 역할분담 정리
"""


@pytest.fixture()
def 잘린것():
    return cut(샘플, source="시험용")


@pytest.fixture()
def 회차와업무(admin_client):
    """회차 하나 + 업무 하나. **이름은 가명이다** (11-2)."""
    with app_session() as db:
        retreat = models.Retreat(name="시험 회차", start_date=dt.date(2026, 8, 21),
                                 end_date=dt.date(2026, 8, 23))
        db.add(retreat)
        db.flush()
        lib = models.TaskLibrary(title="GBS 교재 출력·제작", kind="main", default_d_week=5)
        db.add(lib)
        db.flush()
        run = models.TaskRun(library_id=lib.id, retreat_id=retreat.id, included=True,
                             d_week=5, start_date=dt.date(2026, 8, 1),
                             end_date=dt.date(2026, 8, 10), status="대기")
        db.add(run)
        db.commit()
        return {"retreat_id": retreat.id, "run_id": run.id, "title": lib.title}


# ── 3. 회의가 날짜별로 잘린다 ────────────────────────────────────────


def test_x_03_회의가_날짜별로_잘린다(잘린것):
    회의들, _ = 잘린것
    날짜 = [m.date for m in 회의들 if m.date]
    assert dt.date(2026, 7, 26) in 날짜
    assert dt.date(2026, 7, 25) in 날짜
    assert dt.date(2026, 6, 21) in 날짜
    assert dt.date(2026, 4, 22) in 날짜


def test_x_03b_문장_속_강조는_회의가_아니다(잘린것):
    """`정해야함` 은 빨간 굵은 글씨지만 강조일 뿐이다. 잘리면 그 회의가
    두 동강 나는데, **잘못 잘린 것은 눈에 안 띈다.**"""
    회의들, _ = 잘린것
    assert not any("정해야함" in m.heading for m in 회의들)
    # 그 줄은 7/26 회의의 **본문**으로 들어가 있어야 한다
    칠월 = next(m for m in 회의들 if m.date == dt.date(2026, 7, 26))
    assert "정해야함" in 칠월.body


def test_x_03c_회의_안에_중첩된_날짜는_자르지_않는다(잘린것):
    """**실제로 걸렸던 버그다.** `26.04.22 1차 구상안` 은 4월 22일 회의 안에
    접어 둔 토글인데, 처음에는 그것까지 잘려서 4월 22일 회의가 두 개가 됐다."""
    회의들, _ = 잘린것
    사월 = [m for m in 회의들 if m.date == dt.date(2026, 4, 22)]
    assert len(사월) == 1, "4월 22일 회의가 두 개로 쪼개졌다"
    assert "도면 확인" in 사월[0].body, "중첩된 토글의 내용이 사라졌다"


# ── 4. 날짜 없는 덩어리가 버려지지 않는다 ─────────────────────────────


def test_x_04_날짜_없는_덩어리가_버려지지_않는다(잘린것):
    """**여기가 정확히 놓치는 지점이다.** 실제 원본에서는 총무팀 역할분담이
    통째로 이 덩어리 안에 들어 있다 — 버리면 그게 통째로 사라진다."""
    회의들, _ = 잘린것
    없는날 = [m for m in 회의들 if m.date is None]
    assert len(없는날) == 1
    assert "특정일 없음" in 없는날[0].heading
    assert "역할분담 정리" in 없는날[0].body


# ── 5. 형광펜이 살아서 들어간다 (추측이라고 말한다) ──────────────────


def test_x_05_형광펜이_살아서_들어간다(잘린것):
    회의들, _ = 잘린것
    칠월 = next(m for m in 회의들 if m.date == dt.date(2026, 7, 26))
    assert any("대걸레" in h for h in 칠월.highlights)


def test_x_05b_형광펜의_뜻이_추측이라고_적혀_있다():
    """**노션에 규칙이 적혀 있지 않다.** 같은 문장이 7/25 와 7/26 에 같은
    색으로 두 번 나온 것에서 '안 끝난 것' 으로 읽은 것이다."""
    from app.domain import meeting_import

    assert "추측" in (meeting_import.__doc__ or "")
    본문 = (ROOT / "scripts" / "import_meetings.py").read_text(encoding="utf-8")
    assert "⟨미완료?⟩" in 본문, "물음표가 붙어야 추측인 줄 안다"
    assert "추측" in 본문


# ── 6 · 7. 사람 평가는 짚어만 준다 ───────────────────────────────────


def test_x_06_사람_평가_대목이_따로_짚인다(잘린것):
    회의들, _ = 잘린것
    유월 = next(m for m in 회의들 if m.date == dt.date(2026, 6, 21))
    짚은것 = " ".join(유월.people_sure + 유월.people_maybe)
    assert "INFP" in 짚은것 and "체력 약함" in 짚은것


def test_x_07_자동으로_빼지_않는다(잘린것):
    """**기계는 사람 평가와 업무 메모를 가릴 수 없다** — `재정에 익숙` 은
    평가이고 `재정 담당 …` 은 업무다. 그래서 짚어만 주고 사람이 정한다."""
    회의들, _ = 잘린것
    유월 = next(m for m in 회의들 if m.date == dt.date(2026, 6, 21))
    # 본문에 그대로 남아 있다 — 빼는 것은 사람이 --skip 으로 한다
    assert "INFP" in 유월.body
    본문 = (ROOT / "scripts" / "import_meetings.py").read_text(encoding="utf-8")
    assert "--skip" in 본문, "사람이 뺄 길이 없다"
    assert "자동으로 빼지 않았습니다" in 본문


# ── 8. CLAUDE.md 에 규칙이 적혔다 ────────────────────────────────────


def test_x_08_사람_평가는_넣지_않는다가_적혔다():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    at = text.index("## 9. UI 공통 규칙")
    section = text[at : text.index("## 10.", at)]
    assert "사람에 대한 평가는 이 시스템에 넣지 않습니다" in section
    assert "업무 지식" in section, "0장과 어떻게 다른지가 없다"
    assert "전사" in section, "나중에 전사 파일을 넣을 때의 기준이라는 말이 없다"


# ── 2. --apply 없이는 보여만 준다 ────────────────────────────────────


def test_x_02_apply_없이는_보여만_준다():
    본문 = (ROOT / "scripts" / "import_meetings.py").read_text(encoding="utf-8")
    assert "if not args.apply:" in 본문
    at = 본문.index("if not args.apply:")
    블록 = 본문[at : at + 220]
    assert "preview(" in 블록 and "return 0" in 블록
    assert "아무것도 넣지 않았습니다" in 본문
    # 이미 있으면 그냥 덮지 않는다 (5-5 와 같은 규칙)
    assert "--replace 를 붙여주세요" in 본문


# ── 13 · 14. --until 과 그 시점의 보드 ───────────────────────────────


def test_x_13_until_로_그_날짜까지만_고른다():
    from scripts.import_meetings import pick
    from app.domain.meeting_import import 회의 as 회의클래스

    것들 = [
        회의클래스(source="s", heading="a", date=dt.date(2026, 5, 1), body="x"),
        회의클래스(source="s", heading="b", date=dt.date(2026, 7, 1), body="x"),
        회의클래스(source="s", heading="c", date=None, body="x"),
    ]
    고른것 = pick(것들, until=dt.date(2026, 6, 30), include_undated=False)
    assert [m.heading for m in 고른것] == ["a"]
    # 날짜 없는 것은 **언제 적은 것인지 모른다.** 아는 척하지 않는다
    고른것 = pick(것들, until=dt.date(2026, 6, 30), include_undated=True)
    assert [m.heading for m in 고른것] == ["a", "c"]
    # --until 이 없으면 전부
    assert len(pick(것들, until=None, include_undated=False)) == 3


def test_x_14_그_시점의_보드는_상태를_담지_않는다(회차와업무):
    """**가리는 것은 존재가 아니라 상태다.** 8월의 완료 여부를 6월 제안에
    쓰면 이미 끝난 일을 알고 제안하는 것이고, 그러면 잘 맞히는 것처럼 보인다.

    `TaskRun` 을 그대로 넘기지 않는 것이 요점이다 — 넘기면 부르는 쪽이
    `.status` 를 볼 수 있고, 볼 수 있으면 언젠가 본다.
    """
    with app_session() as db:
        retreat = db.get(models.Retreat, 회차와업무["retreat_id"])
        rows = board_as_of(db, retreat, dt.date(2026, 6, 30))
    assert rows, "그때도 보드에는 업무가 있다 — 아직 시작 안 했을 뿐이다"
    for r in rows:
        assert not hasattr(r, "status")
        assert not hasattr(r, "completed_at")
        assert not hasattr(r, "started_at")


# ── 15 ~ 18. 제안 ────────────────────────────────────────────────────


def test_x_15_제안이_새_업무와_논의_둘로_나온다():
    import inspect
    from app.domain import suggest as mod

    doc = mod.__doc__ or ""
    assert "새 업무" in doc and "논의" in doc
    src = inspect.getsource(mod)
    assert "'new'" in src and "'discussion'" in src


def test_x_16_논의_제안에_왜_그_업무인지가_붙는다(회차와업무):
    """**둘째가 더 어렵다** — 250건 중 하나를 고르는 일이고, 틀리면 남의
    회의 내용이 엉뚱한 업무에 남는다 (6-3)."""
    with app_session() as db:
        retreat = db.get(models.Retreat, 회차와업무["retreat_id"])
        m = models.Meeting(retreat_id=retreat.id, title="시험 회의",
                           meeting_date=dt.date(2026, 6, 1),
                           body=회차와업무["title"] + " 를 논의함")
        db.add(m)
        db.commit()
        것들 = suggest(db, retreat=retreat, meeting=m, as_of=dt.date(2026, 6, 1))
    assert 것들, "이름이 그대로 든 회의록인데 제안이 없다"
    for x in 것들:
        assert x.why, "왜 그 업무인지가 없다"
        assert x.evidence, "근거가 비었다"
        assert x.run_id and x.run_title


def test_x_17_판정_단어가_출력에_없다(회차와업무):
    """4-10 조건 7 — 코드가 판정에 안 넣어도 사람은 판정으로 읽는다."""
    with app_session() as db:
        retreat = db.get(models.Retreat, 회차와업무["retreat_id"])
        m = models.Meeting(retreat_id=retreat.id, title="진행 불가 라고 적힌 회의",
                           meeting_date=dt.date(2026, 6, 1),
                           body=회차와업무["title"] + " 완료 진행 가능")
        db.add(m)
        db.commit()
        것들 = suggest(db, retreat=retreat, meeting=m, as_of=dt.date(2026, 6, 1))
    assert 것들, "제안이 없으면 이 시험이 아무것도 안 지킨다"
    # **사람이 쓴 제목은 그대로 둔다** — 조건 7 이 막는 것은 우리가 판정을
    # 내리는 것이지 남의 글을 검열하는 것이 아니다 (test_y_02).
    # 그래서 **우리가 지어낸 부분**만 본다.
    for x in 것들:
        지어낸것 = x.text.replace("진행 불가 라고 적힌 회의", "")
        for 말 in 판정단어:
            assert 말 not in 지어낸것, f"우리 문장에 판정 단어 '{말}'"


def test_x_18_할_말이_없으면_빈_목록(회차와업무):
    """억지로 만들면 근거 없는 제안이 된다 (4-10 조건 4)."""
    with app_session() as db:
        retreat = db.get(models.Retreat, 회차와업무["retreat_id"])
        m = models.Meeting(retreat_id=retreat.id, title="빈 회의",
                           meeting_date=dt.date(2026, 6, 1), body="")
        db.add(m)
        db.commit()
        assert suggest(db, retreat=retreat, meeting=m) == []


def test_x_04b_창구가_한_곳이다():
    """회의록 화면에서 부르든 채팅으로 부르든 **읽고 제안하는 길은 한 곳**이다.
    두 벌이 되면 이 프로젝트가 다섯 번 고쳐 온 그 모양이 다시 난다."""
    import app.domain.suggest as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert src.count("def suggest(") == 1
    # `simulate` 도 그 하나를 부른다 — 따로 계산하지 않는다
    at = src.index("def simulate(")
    assert "suggest(db," in src[at:]


# ── 20. 되돌릴 수 있다 ───────────────────────────────────────────────


def test_x_20_옮긴_것을_묶음으로_되돌릴_수_있다():
    """26년은 **끝난 실제 회차**다. 개발 중 넣은 것이 6-2 자동 분류의
    입력값이 되면 안 되므로 골라 낼 수 있어야 한다."""
    본문 = (ROOT / "scripts" / "import_meetings.py").read_text(encoding="utf-8")
    assert "def undo(" in 본문
    assert "--undo" in 본문
    assert "import_batch" in 본문
    # 넣고 나면 되돌리는 법을 화면에 알려 준다 — 모르면 없는 것과 같다
    assert "되돌리려면" in 본문


# ── 21. 시험 자료에 실명이 없다 ──────────────────────────────────────


def test_x_21_시험_자료에_실명이_없다():
    """저장소는 공개다 (11-2). 실제 회의록에는 실명이 그대로 들어 있어서
    `data/notion-meetings/` 는 저장소에 두지 않는다."""
    import json

    표 = ROOT / "data" / "anonymize-map.json"
    if not 표.exists():
        pytest.skip("대응표가 없다")
    실명 = [p[0] for p in json.loads(표.read_text(encoding="utf-8"))["names"]]
    나 = pathlib.Path(__file__).read_text(encoding="utf-8")
    import re

    for n in 실명:
        assert not re.search(r"(?<![0-9A-Za-z가-힣])" + re.escape(n)
                             + r"(?![0-9A-Za-z가-힣])", 나), f"실명 {n}"

    # 원본 폴더는 무시 목록에 있다
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/notion-meetings/" in ignore


# ── 19. 고른 것만 반영되고 출처가 남는다 ─────────────────────────────


def test_x_19_고른_것만_반영되고_출처가_남는다(admin_client, 회차와업무):
    """**아무것도 자동으로 반영되지 않는다.** 사람이 하나씩 고른다.

    고른 것에는 **출처 회의록**이 남고 `ActivityLog` 에 `actor_type='claude'`
    로 기록된다 — 나중에 "이건 누가 넣었지" 를 물을 수 있어야 하고,
    개발 중 넣은 것을 골라 낼 수 있어야 한다.
    """
    run_id = 회차와업무["run_id"]
    with app_session() as db:
        m = models.Meeting(retreat_id=회차와업무["retreat_id"],
                           title="6월 회의", meeting_date=dt.date(2026, 6, 1),
                           body=회차와업무["title"] + " 일정 논의")
        db.add(m)
        db.commit()
        meeting_id = m.id
        # 아직 아무것도 안 골랐으므로 논의가 없다
        assert db.scalars(select(models.DiscussionEntry)
                          .where(models.DiscussionEntry.run_id == run_id)).all() == []

    보임 = admin_client.get(f"/meetings/{meeting_id}/suggestions").json()
    assert not 보임["failed"]
    assert 보임["items"], "제안이 없으면 고를 것도 없다"
    for x in 보임["items"]:
        assert x["why"], "왜 그 업무인지가 없다"

    # **고른 것 하나만** 반영한다
    res = admin_client.post(f"/meetings/{meeting_id}/suggestions/apply",
                            json={"run_id": run_id})
    assert res.status_code == 200

    with app_session() as db:
        논의 = db.scalars(select(models.DiscussionEntry)
                        .where(models.DiscussionEntry.run_id == run_id)).all()
        assert len(논의) == 1, "고른 하나만 들어가야 한다"
        # 출처가 남는다
        assert "회의록" in 논의[0].body and "6월 회의" in 논의[0].body
        assert "2026-06-01" in 논의[0].body

        기록 = db.scalars(select(models.ActivityLog)
                        .where(models.ActivityLog.action == "회의록_제안_반영")).all()
        assert len(기록) == 1
        assert 기록[0].actor_type == "claude", "누가 넣었는지가 남아야 한다"


def test_x_19b_실패해도_회의록_화면은_살아_있다():
    """4-10 조건 8 — 제안이 비는 것으로 끝나야 한다. 여기서 터져서
    회의록 본문을 못 보게 되면 안 된다."""
    본문 = (ROOT / "app" / "routers" / "meetings.py").read_text(encoding="utf-8")
    at = 본문.index("def meeting_suggestions(")
    블록 = 본문[at : 본문.index("\n@router", at)]
    assert "except Exception" in 블록 and '"items": []' in 블록

    js = (ROOT / "app" / "static" / "js" / "meeting.js").read_text(encoding="utf-8")
    assert "catch" in js
    assert "회의록은 그대로 보실 수 있습니다" in js


def test_x_19c_아무것도_자동으로_반영되지_않는다():
    """`GET` 은 보여만 주고, 넣는 것은 사람이 누르는 `POST` 뿐이다."""
    본문 = (ROOT / "app" / "routers" / "meetings.py").read_text(encoding="utf-8")
    at = 본문.index("def meeting_suggestions(")
    보여주는곳 = 본문[at : 본문.index("\n@router", at)]
    for 쓰는말 in ("db.add(", "db.commit()"):
        assert 쓰는말 not in 보여주는곳, f"보여주기만 해야 하는데 {쓰는말} 가 있다"


# ══════════════════════════════════════════════════════════════════════
# 리뷰에서 나온 것 (1~14)
# ══════════════════════════════════════════════════════════════════════


# ── 1. 새 업무 제안이 나온다 ─────────────────────────────────────────


def test_y_01_새_업무_제안이_나온다(회차와업무):
    """문서가 "두 가지를 낸다" 고 해 놓고 `kind='new'` 를 한 번도 안 만들고
    있었다. **문서가 앞서가면 안 된다.**"""
    with app_session() as db:
        retreat = db.get(models.Retreat, 회차와업무["retreat_id"])
        m = models.Meeting(
            retreat_id=retreat.id, title="6월 회의",
            meeting_date=dt.date(2026, 6, 1),
            body="- 시설에 대걸레 있는지 쓸수 있는지 문의\n"
                 "- 카드키 보관함 3d 프린트 요청\n")
        db.add(m)
        db.commit()
        것들 = suggest(db, retreat=retreat, meeting=m, as_of=dt.date(2026, 6, 1))
    새것 = [x for x in 것들 if x.kind == "new"]
    assert 새것, "새 업무 제안이 하나도 안 나온다"
    for x in 새것:
        # **근거를 함께 낸다** — 보드에 없다는 것을 무엇으로 판단했는지 (6-3)
        assert "겹치지 않습니다" in x.why
        assert "보드" in x.why
        assert x.run_id is None, "새 업무인데 붙일 업무가 있다"


# ── 2 · 3. 사람의 원문을 뭉개지 않는다 ───────────────────────────────


def test_y_02_회의_제목의_완료가_뭉개지지_않는다(회차와업무):
    """4-10 조건 7 이 막는 것은 **우리가 판정을 내리는 것**이지, 사람이 쓴
    글에서 그 낱말을 지우는 것이 아니다. 회의 제목이
    `26.08.16 최종패킹 완료` 면 그 `완료` 는 그 사람의 말이다."""
    with app_session() as db:
        retreat = db.get(models.Retreat, 회차와업무["retreat_id"])
        m = models.Meeting(retreat_id=retreat.id,
                           title="26.08.16 최종패킹 완료",
                           meeting_date=dt.date(2026, 6, 1),
                           body=회차와업무["title"] + " 를 논의함")
        db.add(m)
        db.commit()
        것들 = suggest(db, retreat=retreat, meeting=m, as_of=dt.date(2026, 6, 1))
    논의 = [x for x in 것들 if x.kind == "discussion"]
    assert 논의
    for x in 논의:
        assert "26.08.16 최종패킹 완료" in x.text, "사람이 쓴 제목이 뭉개졌다"
        assert "…" not in x.text.split(" 의 내용을")[0]


def test_y_02b_우리가_지어낸_문장에는_판정_단어가_없다():
    """원문은 그대로 두되 **우리 문장에는 여전히 안 나온다.**"""
    from app.domain.suggest import 판정단어_뺀다

    assert "완료" not in 판정단어_뺀다("완료 되었습니다")
    src = pathlib.Path(
        __import__("app.domain.suggest", fromlist=["x"]).__file__
    ).read_text(encoding="utf-8")
    # 제목을 거르지 않는 것이 요점이다
    assert "meeting.title + 판정단어_뺀다" in src


# ── 4. N+1 이 없다 ───────────────────────────────────────────────────


def test_y_04_board_as_of_에_N_플러스_1_이_없다():
    """직접 `select(TaskRun)` 을 하면 `library`·`department` 를 건건이 읽는다 —
    실제로 업무 96건에 107쿼리였다. `load_runs` 가 셋을 미리 붙여 온다."""
    import inspect

    from app.domain import suggest as mod

    src = inspect.getsource(mod.board_as_of)
    # **독스트링을 걷어내고 본다.** "직접 select(TaskRun) 하면 N+1 이 난다" 는
    # 설명글에 걸려서, 고쳐 놓고도 안 고친 것으로 판정했다.
    # getdoc() 은 들여쓰기를 편 것이라 원문과 안 맞는다 — 따옴표로 자른다
    몸통 = src.split('"""')[-1]
    assert "board_domain.load_runs" in 몸통
    assert "select(TaskRun)" not in 몸통, "다시 직접 조회한다"

    # `load_runs` 가 정말 미리 붙여 오는지도 확인한다 — 거기가 바뀌면
    # 이 함수도 조용히 N+1 로 돌아간다
    from app.domain import board as board_mod

    붙임 = inspect.getsource(board_mod.load_runs)
    for 관계 in ("TaskRun.library", "TaskRun.department"):
        assert f"joinedload({관계})" in 붙임, f"{관계} 를 미리 안 붙여 온다"


# ── 5 ~ 8. 조용히 지나가는 것을 만들지 않는다 ────────────────────────


def test_y_05_본문_안의_날짜같은_줄을_말한다():
    """**반대쪽이 위험하다.** 날짜인데 `_RED` 가 못 찾으면(색이 다르거나
    자릿수가 다르면) **아무 경고 없이 앞 회의에 흡수된다.**"""
    글 = """<span color="red">**26.07.26**</span>
- 구매목록 취합
**26.07.20** 색 없이 적힌 날짜
26.7.5 자릿수가 다른 날짜
"""
    회의들, 걸린 = cut(글, source="시험용")
    assert len(회의들) == 1, "자르면 안 된다 — 말만 한다"
    날짜줄 = [g for g in 걸린 if g.kind == "날짜같은줄"]
    assert len(날짜줄) == 2, [g.text for g in 걸린]
    # **글머리표 줄은 제목이 아니다.** `- 26.7.5 …` 는 그냥 항목이라 안 잡는다 —
    # 다 잡으면 경고가 시끄러워져서 사람이 안 읽는다
    for g in 날짜줄:
        assert g.붙은곳 == "26.07.26", "어느 회의에 붙었는지 말해야 한다"


def test_y_06_못_알아본_제목의_내용이_어디_갔는지_말한다():
    """지금은 제목만 알려주고 내용이 어디 갔는지는 말하지 않았다."""
    글 = """<span color="red">**26.07.26**</span>
- 첫 줄
<span color="red">**그냥 강조한 제목입니다**</span>
- 이 줄은 어디로 갔나
"""
    _, 걸린 = cut(글, source="시험용")
    안본 = [g for g in 걸린 if g.kind == "안본제목"]
    assert 안본, "회의로 안 본 빨간 줄을 말하지 않는다"
    assert 안본[0].붙은곳 == "26.07.26"


def test_y_07_첫_회의_앞_머리말이_조용히_버려지지_않는다():
    """머리말에 "조용히 버리지 않는다" 고 적어 놓고 `continue` 로 버리고
    있었다. 버린다면 **무엇을 버렸는지 말해야** 한다."""
    글 = """## 행사 개요
주제 BELONG
<span color="red">**26.07.26**</span>
- 첫 줄
"""
    회의들, 걸린 = cut(글, source="시험용")
    assert len(회의들) == 1
    머리 = [g for g in 걸린 if g.kind == "머리말"]
    assert 머리, "머리말을 버렸다고 말하지 않는다"
    assert "2줄" in 머리[0].text


def test_y_08_빈자리가_날짜_없는_덩어리와_구별된다():
    """`26.00.00` 은 템플릿의 빈 칸이지 회의가 아니다. 날짜 없는 덩어리와
    같은 칸에 두면 사람이 구별할 수 없다."""
    글 = """<span color="red">**26.00.00**</span>
<span color="red">**모임 전 수시로 정리한 내용들 (특정일 없음)**</span>
- 진짜 내용
"""
    회의들, 걸린 = cut(글, source="시험용")
    빈것 = [m for m in 회의들 if m.empty_slot]
    덩어리 = [m for m in 회의들 if m.date is None and not m.empty_slot]
    assert len(빈것) == 1 and len(덩어리) == 1
    assert [g for g in 걸린 if g.kind == "빈자리"], "빈 칸이라고 말하지 않는다"

    본문 = (ROOT / "scripts" / "import_meetings.py").read_text(encoding="utf-8")
    assert "템플릿의 빈 칸" in 본문, "미리보기가 구별해 보여주지 않는다"


# ── 9. 형광펜의 근거를 세어 적었다 ───────────────────────────────────


def test_y_09_형광펜의_근거를_세어_적었다():
    """물음표는 맞지만 **근거가 대걸레 한 줄**이었다. 세어 보니 22개 중
    두 번 이상 나온 것은 2개뿐이다 — 사실대로 적는다."""
    from app.domain import meeting_import

    doc = meeting_import.__doc__ or ""
    assert "근거가 약하다" in doc
    assert "22개" in doc and "20개" in doc and "2개뿐" in doc

    본문 = (ROOT / "scripts" / "import_meetings.py").read_text(encoding="utf-8")
    assert "두 번 이상 나온 것" in 본문, "미리보기가 세어 보여주지 않는다"


# ── 10. 짚은 것이 두 칸으로 나뉜다 ───────────────────────────────────


def test_y_10_짚은_것이_두_칸으로_나뉜다(잘린것):
    """한 목록에 200줄이면 사람이 안 읽는다. 안 읽으면 짚어 준 것이
    없는 것과 같다."""
    회의들, _ = 잘린것
    유월 = next(m for m in 회의들 if m.date == dt.date(2026, 6, 21))
    assert 유월.people_sure, "MBTI 칸이 비었다"
    assert 유월.people_maybe, "잘함·못함 칸이 비었다"
    # 같은 줄이 두 칸에 겹쳐 나오지 않는다
    assert not (set(유월.people_sure) & set(유월.people_maybe))
    assert all("INFP" in x or "ENFJ" in x or any(
        k in x for k in ("ISFJ", "ISTP", "ESFJ", "INFJ", "ISTFP")) 
        for x in 유월.people_sure)

    본문 = (ROOT / "scripts" / "import_meetings.py").read_text(encoding="utf-8")
    assert "거의 확실" in 본문 and "볼 만함" in 본문


# ── 11. 무엇으로 골랐는지 화면이 말한다 ──────────────────────────────


def test_y_11_무엇으로_골랐는지_화면이_말한다():
    """감추지 않는다. 위험한 것은 틀린 제안이 아니라 **사람이 처음에 세우는
    기대**다 — "읽고 제안했다" 로 읽히면 몇 번 엉뚱한 것을 보고 다시 안 쓴다.
    한 번 잃으면 안 돌아온다 (6-3)."""
    view = (ROOT / "app" / "templates" / "meeting_detail.html").read_text(encoding="utf-8")
    assert "회의록과 이름이 겹치는 업무입니다" in view
    assert "아직 내용을 읽지는 않습니다" in view
    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    assert ".mt-sug-how{" in css, "그 문장이 화면에 안 보인다"


# ── 12 · 13. 22/27 이 무엇을 잰 것인지 · 성적표 ──────────────────────


def test_y_12_22대27_이_무엇을_잰_것인지_적혔다():
    """같은 낱말로 뽑고 같은 낱말로 채점하면 높게 나오는 것이 당연하다."""
    표 = (ROOT / "docs" / "review" / "제안-성적표.md").read_text(encoding="utf-8")
    assert "22 / 27" in 표 or "22/27" in 표
    assert "어휘가 반복된다" in 표 or "어휘를 씁니다" in 표
    assert "증거가 아닙니다" in 표


def test_y_13_사람이_채울_성적표가_있다():
    표 = (ROOT / "docs" / "review" / "제안-성적표.md").read_text(encoding="utf-8")
    assert "사람이 채웁니다" in 표
    assert "O / X / ?" in 표 or "**O**" in 표
    assert "--undo" in 표, "채운 뒤 지우는 법이 없다"
    # 다음에 견줄 기준이라는 것이 적혀 있다
    assert "다시 채웁니다" in 표


# ── 14. as_of 를 왜 받아만 두는지 ────────────────────────────────────


def test_y_14_as_of_를_왜_받아만_두는지_적혔다():
    """머리말이 길게 설명하는 것과 코드가 하는 일이 달랐다."""
    import inspect

    from app.domain import suggest as mod

    doc = inspect.getdoc(mod.board_as_of) or ""
    assert "받아 두고 쓰지 않는다" in doc
    assert "의식하고 넘기게" in doc, "왜 남겨 두는지가 없다"
