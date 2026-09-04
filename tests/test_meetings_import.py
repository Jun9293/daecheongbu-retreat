"""회의록 옮기기와 시뮬레이션 (CLAUDE.md 회의록 1·3·4단계).

**시험 자료에 실명이 없다.** 실제 회의록에는 실명이 그대로 들어 있어서
`data/notion-meetings/` 는 저장소에 두지 않는다. 여기 붙인 것은 **실제 원본과
같은 모양으로 지어낸 것**이고 이름은 전부 가명이다 (11-2).
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re

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



def 제안받기(client, meeting_id, 최대=4):
    """제안을 **끝날 때까지** 물어본다 — 화면이 하는 것과 같다.

    회의록을 저장하거나 처음 열면 분석은 **뒤에서 돈다**(회의록 5단계).
    첫 응답은 빈 목록이라, 한 번만 물어보고 "제안이 없다" 고 하면 **틀린
    것을 잰다.**

    **이제 첫 상태는 `기다림` 이다** — 적는 동안에는 안 부르고 3분쯤
    잠잠해지면 돈다. 시험이 3분을 기다릴 수는 없으므로 화면의 `지금 읽기`
    와 같은 길(`/suggestions/rerun`)로 당겨 온다.
    """
    data = client.get(f"/meetings/{meeting_id}/suggestions").json()
    if data.get("state") == "기다림":
        client.post(f"/meetings/{meeting_id}/suggestions/rerun")
    for _ in range(최대):
        data = client.get(f"/meetings/{meeting_id}/suggestions").json()
        if data.get("state") not in ("도는중", "기다림"):
            return data
    return data


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


def test_x_14_그_시점의_보드는_그날의_상태만_담는다(회차와업무):
    """**가리는 것은 존재가 아니라 상태다.** 8월의 완료 여부를 6월 제안에
    쓰면 이미 끝난 일을 알고 제안하는 것이고, 그러면 잘 맞히는 것처럼 보인다.

    처음에는 상태를 **아예 안 담았다**("담으면 본다"). 문장으로 읽는 판
    (회의록 5단계)에서 상태가 필요해졌는데, **저장된 `status` 를 담으면
    안 된다** — 그건 오늘의 값이다. 그래서 `started_at`·`completed_at`
    날짜에서 **그날의 상태를 다시 계산한다**. 규칙이 "안 담는다" 에서
    "그날 것만 담는다" 로 바뀌었고, 이 시험도 그렇게 바뀌었다.

    `TaskRun` 을 그대로 넘기지 않는 것은 그대로다 — 넘기면 부르는 쪽이
    `.status` 를 볼 수 있고, 볼 수 있으면 언젠가 본다.
    """
    with app_session() as db:
        retreat = db.get(models.Retreat, 회차와업무["retreat_id"])
        run = db.get(models.TaskRun, 회차와업무["run_id"])
        run.status = "완료"                 # 오늘의 값 — 이것을 보면 안 된다
        run.completed_at = dt.date(2026, 8, 10)
        run.started_at = dt.date(2026, 8, 1)
        db.commit()
        그날 = board_as_of(db, retreat, dt.date(2026, 6, 30))
        나중 = board_as_of(db, retreat, dt.date(2026, 8, 15))
    assert 그날, "그때도 보드에는 업무가 있다 — 아직 시작 안 했을 뿐이다"
    for r in 그날:
        # 날짜 자체는 넘기지 않는다 — 넘기면 부르는 쪽이 다시 계산한다
        assert not hasattr(r, "completed_at")
        assert not hasattr(r, "started_at")
    assert 그날[0].status == "대기", "8월에 끝난 것을 6월에 알고 있다"
    assert 나중[0].status == "완료"


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

    보임 = 제안받기(admin_client, meeting_id)
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
    회의록 본문을 못 보게 되면 안 된다.

    **막는 자리가 옮겨졌다** (회의록 5단계). 전에는 화면이 부를 때 그 자리에서
    제안을 만들었으므로 `GET` 이 감쌌다. 이제는 **뒤에서 도는 분석**이 만들고
    `GET` 은 쌓인 것을 낼 뿐이라, 터질 수 있는 자리가 그쪽이다 —
    거기서 조용히 끝나면 화면은 **영원히 '읽는 중'** 이다.
    """
    본문 = (ROOT / "app" / "routers" / "meetings.py").read_text(encoding="utf-8")
    at = 본문.index("def 분석_한번(")
    도는곳 = 본문[at : 본문.index("\ndef ", at + 5)]
    assert "except Exception" in 도는곳, "터지면 아무 표시도 안 남는다"
    assert '"실패"' in 도는곳, "실패를 상태로 남기지 않는다"

    at = 본문.index("def meeting_suggestions(")
    내는곳 = 본문[at : 본문.index("\n@router", at)]
    assert "except Exception" in 내는곳, "쌓인 것을 읽다가 터지면 화면이 빈다"

    js = (ROOT / "app" / "static" / "js" / "meeting.js").read_text(encoding="utf-8")
    assert "catch" in js
    assert "회의록은 그대로 보실 수 있습니다" in js


def test_x_19c_아무것도_자동으로_반영되지_않는다(admin_client, 회차와업무):
    """**보는 것만으로는 아무것도 남지 않는다.** 넣는 것은 사람이 누르는
    `POST` 뿐이다.

    글자로 세는 대신 **실제로 열어 보고 논의가 생겼는지** 본다 — `GET` 이
    이제 분석을 걸어 두느라 상태를 쓰기 때문에, "쓰는 말이 있나" 로는
    이 규칙을 못 지킨다. 지켜야 할 것은 *논의가 안 생기는 것*이다.
    """
    run_id = 회차와업무["run_id"]
    with app_session() as db:
        m = models.Meeting(retreat_id=회차와업무["retreat_id"],
                           title="6월 회의", meeting_date=dt.date(2026, 6, 1),
                           body=회차와업무["title"] + " 일정 논의")
        db.add(m)
        db.commit()
        meeting_id = m.id

    제안받기(admin_client, meeting_id)          # 몇 번을 봐도
    제안받기(admin_client, meeting_id)

    with app_session() as db:
        남은것 = db.scalars(select(models.DiscussionEntry)
                          .where(models.DiscussionEntry.run_id == run_id)).all()
    assert 남은것 == [], "보기만 했는데 논의가 남았다"


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
    js = (ROOT / "app" / "static" / "js" / "meeting.js").read_text(encoding="utf-8")
    assert "회의록과 이름이 겹치는 업무입니다. 내용을 읽지는 않았습니다." in js
    assert "회의 내용을 읽고 골랐습니다." in js, "문장으로 읽었을 때의 말이 없다"

    # **문구를 화면(템플릿)에 박아 두지 않는다** (회의록 5단계).
    # 문장으로 읽었는지 낱말로 물러섰는지는 그때그때 다르다 — 박아 두면
    # **물러섰는데도 "읽었습니다" 라고 적히거나** 그 반대가 된다
    view = (ROOT / "app" / "templates" / "meeting_detail.html").read_text(encoding="utf-8")
    for 박힌말 in ("아직 내용을 읽지는 않습니다", "낱말이 겹치는 정도로 골랐고"):
        assert 박힌말 not in view, "옛 문구가 화면에 박혀 있다"

    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    assert ".mt-sug-how{" in css, "그 문장이 화면에 안 보인다"


# ── 12 · 13. 22/27 이 무엇을 잰 것인지 · 성적표 ──────────────────────


def test_y_12_22대27_이_무엇을_잰_것인지_적혔다():
    """같은 낱말로 뽑고 같은 낱말로 채점하면 높게 나오는 것이 당연하다."""
    표 = (ROOT / "docs" / "review" / "제안-성적표.md").read_text(encoding="utf-8")
    assert "22 / 27" in 표 or "22/27" in 표
    assert "어휘가 반복된다" in 표 or "어휘를 씁니다" in 표
    assert "증거가 아닙니다" in 표


def _성적표() -> str:
    return (ROOT / "docs" / "review" / "제안-성적표.md").read_text(encoding="utf-8")


def test_y_13_사람이_채울_성적표의_틀이_있다():
    """**틀만 본다. 값을 박지 않는다.**

    전에는 여기서 `"14/20"` 을 찾았다. 그래서 성적표의 산수를 바로잡는 순간
    이 시험이 빨개졌고, **고치는 것을 막았다** — 지키려던 것은 "사람이 채울
    성적표가 있는가" 였지 그 숫자가 얼마인가가 아니었다.

    값이 서로 맞는지는 아래 `test_y_13b` 가 본다. 그쪽은 문서에서 읽어
    견주므로 숫자가 바뀌어도 따라간다.
    """
    표 = _성적표()
    assert "**O**" in 표, "판정 표기가 없다"
    assert "X" in 표 and "?" in 표, "O·X·? 셋을 설명하지 않는다"
    assert "--undo" in 표, "채운 뒤 지우는 법이 없다"
    assert "놓친 것" in 표, "적게 내는 쪽으로 점수를 올릴 수 있다"
    # **표본은 박는다.** 표본이 바뀌면 판끼리 견줄 수 없다 (성적표의 「표본」)
    for 제목 in ("26.03.29 (1차)", "26.05.24", "26.07.05", "26.08.09"):
        assert 제목 in 표, f"표본에서 {제목} 이 빠졌다"


def test_y_13b_성적표의_숫자끼리_맞는다():
    """**이 어긋남을 사람이 눈으로 찾았다.** 논의를 13 으로 고치면서 합계만
    20 으로 남아 `14/20 (70%)` 이 표와 맞지 않았는데, 그때 있던 시험은
    잡기는커녕 고치는 것을 막았다. 문서가 자기 자신과 어긋나는 것은
    **세기만 하면 되므로** 시험이 할 일이다.
    """
    표 = _성적표()

    # ① 회의별 a/b 를 더하면 합계 줄과 같은가
    회의별 = re.findall(r"^\| 26\.\d\d\.\d\d \| (\d+)/(\d+) \| (?:(\d+)/(\d+)|—) \|$",
                     표, re.M)
    assert 회의별, "결과 표의 회의 줄을 못 읽었다"
    논의맞 = sum(int(a) for a, _, _, _ in 회의별)
    논의전 = sum(int(b) for _, b, _, _ in 회의별)
    새맞 = sum(int(c) for _, _, c, _ in 회의별 if c)
    새전 = sum(int(d) for _, _, _, d in 회의별 if d)

    합계줄 = re.search(r"^\| \*\*합계\*\* \| \*\*(\d+)/(\d+) [^|]*\| \*\*(\d+)/(\d+) [^|]*\|$",
                    표, re.M)
    assert 합계줄, "결과 표의 합계 줄을 못 읽었다"
    assert (논의맞, 논의전) == (int(합계줄[1]), int(합계줄[2])), (
        f"논의 합계가 회의별과 다르다: 회의별 {논의맞}/{논의전} · 합계줄 {합계줄[1]}/{합계줄[2]}")
    assert (새맞, 새전) == (int(합계줄[3]), int(합계줄[4])), (
        f"새 업무 합계가 회의별과 다르다: 회의별 {새맞}/{새전} · 합계줄 {합계줄[3]}/{합계줄[4]}")

    # ② 논의 분모 + 새 업무 분모 = 전체 분모인가
    전체 = re.search(r"\*\*전체 (\d+)/(\d+) \((\d+)%\)\*\*", 표)
    assert 전체, "전체 줄을 못 읽었다"
    assert int(전체[1]) == 논의맞 + 새맞, (
        f"전체 분자 {전체[1]} 가 논의 {논의맞} + 새 업무 {새맞} 와 다르다")
    assert int(전체[2]) == 논의전 + 새전, (
        f"전체 분모 {전체[2]} 가 논의 {논의전} + 새 업무 {새전} 와 다르다")
    # **반올림이다.** 14/21 = 66.7 이고 문서는 67% 로 적는다 — 버림으로
    # 세면 66 이 나와, 맞는 문서를 틀렸다고 한다
    assert int(전체[3]) == round(int(전체[1]) * 100 / int(전체[2])), "전체 비율이 안 맞는다"

    # ③ 「틀린 것 N개」 의 N 이 그 표의 줄 수와 같은가
    제목 = re.search(r"## 틀린 것 (\S+) 개", 표)
    assert 제목, "「틀린 것」 절 제목을 못 읽었다"
    한글수 = {"셋": 3, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9}
    적힌수 = 한글수.get(제목[1])
    assert 적힌수, f"「틀린 것 {제목[1]}개」 의 수를 못 읽었다"
    줄수 = len(re.findall(r"^\| \d\d\.\d\d \| \d+ \| ", 표, re.M))
    assert 적힌수 == 줄수, f"「틀린 것 {제목[1]}개」 인데 표에는 {줄수}줄이다"

    # ④ 「읽은 것」 의 분모가 틀린 것의 수와 같은가
    읽은것 = re.search(r"\*\*(\S+) 중 넷이 같은 모양입니다\*\*", 표)
    assert 읽은것, "「읽은 것」 첫 문장을 못 읽었다"
    assert 한글수.get(읽은것[1]) == 줄수, (
        f"「읽은 것」 은 {읽은것[1]} 인데 틀린 것은 {줄수}개다")


def test_y_13c_스크립트의_사본이_성적표와_맞는다():
    """**정본은 성적표이고 스크립트는 사본이다.**

    `suggest_sample.py` 가 1판 성적을 사본으로 들고 있다 — 채점표에 찍고,
    회의별로 견주는 데 쓴다. 둘이 갈리면 **다시 낸 목록이 엉뚱한 것과
    견줘지는데 아무 표시도 나지 않는다.**

    `test_y_13b` 는 문서 안의 일관성만 보므로 이 둘이 갈려도 못 잡는다.
    """
    import importlib.util
    스펙 = importlib.util.spec_from_file_location(
        "_ss_y13c", ROOT / "scripts" / "suggest_sample.py")
    ss = importlib.util.module_from_spec(스펙)
    스펙.loader.exec_module(ss)
    표 = _성적표()

    # ① 회의별 — 성적표 「표본」 절의 표가 정본이다
    적힌것 = {제목: (int(논의), int(새것)) for 제목, 논의, 새것 in re.findall(
        r"^\| \d{4}-\d\d-\d\d `([^`]+)` \| [^|]*\| (\d+) \| (\d+) \|$",
        표, re.M)}
    assert 적힌것, "성적표의 「표본」 표를 못 읽었다"
    assert ss.일판회의별 == 적힌것, (
        f"**성적표가 정본입니다. 스크립트의 사본을 맞추세요** — "
        f"일판회의별이 성적표와 다르다 — "
        f"스크립트 {ss.일판회의별} · 성적표 {적힌것}")

    # ② 종류별 — 결과 표의 합계 줄이 정본이다
    합계줄 = re.search(
        r"^\| \*\*합계\*\* \| \*\*(\d+)/(\d+)[^|]*\| \*\*(\d+)/(\d+)[^|]*\|$",
        표, re.M)
    assert 합계줄, "결과 표의 합계 줄을 못 읽었다"
    assert ss.일판 == {"논의": (int(합계줄[1]), int(합계줄[2])),
                     "새 업무": (int(합계줄[3]), int(합계줄[4]))}, (
        f"**성적표가 정본입니다. 스크립트의 사본을 맞추세요** — "
        f"일판이 성적표와 다르다: {ss.일판}")

    # ③ 전체
    전체 = re.search(r"\*\*전체 (\d+)/(\d+) \(\d+%\)\*\*", 표)
    assert 전체, "전체 줄을 못 읽었다"
    assert ss.일판합계 == (int(전체[1]), int(전체[2])), (
        f"**성적표가 정본입니다. 스크립트의 사본을 맞추세요** — "
        f"일판합계가 성적표와 다르다: {ss.일판합계}")


def test_y_13d_도출한_O_가_성적표의_맞은_수와_맞는다():
    """**O 는 사람이 적은 것이 아니라 X 를 뺀 나머지다.**

    성적표가 틀린 일곱을 번호로 짚었으므로 나머지가 O 인 것은 도출된다.
    그 도출이 맞으려면 **대조할 수 있는 회의의 맞은 수 합**과 같아야 한다.

    대조 불가인 회의 몫을 **코드에 박지 않는다** — `제안-1판.md` 의 대조
    표에서 어느 회의가 빠졌는지 읽어, 성적표의 그 회의 맞은 수를 뺀다.
    박아 두면 다음에 다른 회의가 빠질 때 조용히 틀린다.
    """
    import importlib.util
    스펙 = importlib.util.spec_from_file_location(
        "_ss_y13d", ROOT / "scripts" / "suggest_sample.py")
    ss = importlib.util.module_from_spec(스펙)
    스펙.loader.exec_module(ss)
    표 = _성적표()
    # **공개본이 없을 수 있다.** 아직 가명을 못 정한 이름이 남아 있으면
    # `docs/review/` 에 올리지 않는다 — 실명을 아는 채로 공개 저장소에
    # 넣지 않는다 (11-2). 그때는 `data/` 의 원본으로 본다.
    공개본 = ROOT / "docs" / "review" / "제안-1판.md"
    원본 = ROOT / "data" / "제안-1판.real.md"
    쓸것 = 공개본 if 공개본.exists() else 원본
    if not 쓸것.exists():
        pytest.skip("제안-1판 목록이 아직 없다 — scripts/suggest_sample.py --낱말")
    일판 = 쓸것.read_text(encoding="utf-8")

    # ① 대조 표에서 **쓸 수 없는 회의**를 읽는다 (박지 않는다)
    못쓰는회의 = re.findall(r"^\| (\S[^|]*?) \|[^|]*\|[^|]*\| \*\*다름",
                        일판, re.M)
    못쓰는회의 = [x.strip() for x in 못쓰는회의]

    # ② 성적표의 회의별 맞은 수 (결과 표)
    맞은수 = {}
    for 제목, 논의맞, 새맞 in re.findall(
            r"^\| (26\.\d\d\.\d\d) \| (\d+)/\d+ \| (?:(\d+)/\d+|—) \|$",
            표, re.M):
        맞은수[제목] = int(논의맞) + int(새맞 or 0)
    assert 맞은수, "성적표의 결과 표를 못 읽었다"

    # ③ 쓸 수 있는 회의의 맞은 수 합
    def 짧게(제목):
        return 제목.split(" (")[0]
    못쓰는짧은 = {짧게(x) for x in 못쓰는회의}
    기대 = sum(v for k, v in 맞은수.items() if k not in 못쓰는짧은)

    # ④ 문서가 적어 둔 도출된 O 의 수
    적힌O = re.search(r"^\| 합계 \| \d+ \| \d+ \| \*\*(\d+)\*\* \|$", 일판, re.M)
    assert 적힌O, "제안-1판.md 의 도출 표 합계 줄을 못 읽었다"
    assert int(적힌O[1]) == 기대, (
        f"도출된 O 가 {적힌O[1]} 인데, 성적표에서 대조 불가 회의"
        f"({sorted(못쓰는짧은)})를 뺀 맞은 수는 {기대} 다")

    # ⑤ 실제로 표에 찍힌 O(도출) 줄 수도 같아야 한다
    찍힌O = len(re.findall(r"\| O\(도출\) \|", 일판))
    assert 찍힌O == 기대, f"O(도출) 줄이 {찍힌O}개인데 {기대}개여야 한다"
    # ⑥ 대조 칸도 같은 수다
    대조줄 = len(re.findall(r"^\| 26\.[^|]*\| (?:논의|새 업무|결정사항) · [^|]*\| \|$",
                         일판, re.M))
    assert 대조줄 == 기대, f"대조 칸이 {대조줄}줄인데 {기대}줄이어야 한다"


# ── 14. as_of 를 왜 받아만 두는지 ────────────────────────────────────


def test_y_14_as_of_가_무엇을_하는지_적혔다():
    """머리말이 길게 설명하는 것과 코드가 하는 일이 달랐다.

    전에는 `as_of` 를 **받아만 두고** 아무 데도 안 썼다. 지금은 쓴다 —
    **상태를 그날로 되돌린다.** 설명도 그렇게 바뀌어야 한다."""
    import inspect

    from app.domain import suggest as mod

    doc = inspect.getdoc(mod.board_as_of) or ""
    assert "존재를 가리는 데 쓰지 않는다" in doc
    assert "상태를 그날로 되돌리는 것" in doc, "as_of 가 무엇을 하는지 없다"
    assert "받아 두고 쓰지 않는다" not in doc, "옛말이 남아 있다"


# ══════════════════════════════════════════════════════════════════════
# 두 번째 리뷰 (1~13)
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture()
def 짧은업무(admin_client):
    """**이름이 짧은 업무** 하나. 그물이 기울어 있으면 여기 걸린다 —
    `선발대 운영`(2낱말) 과 `선발대 점심 주문 준비`(4낱말)는 한 낱말만
    겹쳐서, 고치기 전에는 **보드에 있는데 새 업무로** 나왔다."""
    with app_session() as db:
        retreat = models.Retreat(name="짧은 회차", start_date=dt.date(2026, 8, 21),
                                 end_date=dt.date(2026, 8, 23))
        db.add(retreat)
        db.flush()
        for 제목 in ("선발대 운영", "포토존", "명찰 제작", "교재 제작",
                    "출력물 제작", "비품 제작", "영상 제작"):
            lib = models.TaskLibrary(title=제목, kind="main", default_d_week=5)
            db.add(lib)
            db.flush()
            db.add(models.TaskRun(library_id=lib.id, retreat_id=retreat.id,
                                  included=True, d_week=5,
                                  start_date=dt.date(2026, 8, 1),
                                  end_date=dt.date(2026, 8, 10), status="대기"))
        db.commit()
        return retreat.id


def _제안(retreat_id: int, body: str, title: str = "시험 회의"):
    with app_session() as db:
        retreat = db.get(models.Retreat, retreat_id)
        m = models.Meeting(retreat_id=retreat.id, title=title,
                           meeting_date=dt.date(2026, 6, 1), body=body)
        db.add(m)
        db.commit()
        return suggest(db, retreat=retreat, meeting=m, as_of=dt.date(2026, 6, 1))


# ── 1 · 2. 새 업무의 근거를 바꾼다 ───────────────────────────────────


def test_z_01_새_업무에_가장_가까운_기존_업무가_함께_나온다(짧은업무):
    """전에는 `evidence` 가 **그 줄 자신의 낱말**이라 아무것도 증명하지
    않았다. 사람이 한눈에 "이건 있는 거네" 를 알 수 있어야 한다."""
    것들 = _제안(짧은업무, "- 선발대 점심 주문 준비\n")
    새것 = [x for x in 것들 if x.kind == "new"]
    if not 새것:
        return                       # 걸러졌으면 그것도 맞다 (아래 시험이 본다)
    for x in 새것:
        assert "가장 가까운 것" in x.why or "한 낱말도 겹치지 않습니다" in x.why
        if "가장 가까운 것" in x.why:
            assert "「" in x.why and "겹친 낱말" in x.why


def test_z_02_보드_전체_낱말과도_견준다(짧은업무):
    """줄의 낱말이 **전부 보드 어딘가에 이미 있으면** 새 업무가 아닐
    가능성이 크다."""
    # `제작` · `교재` 둘 다 보드에 있다 → 새 업무로 내지 않는다
    것들 = _제안(짧은업무, "- 교재 제작 준비\n")
    assert not [x for x in 것들 if x.kind == "new"], \
        "낱말이 전부 보드에 있는데 새 업무로 냈다"

    import inspect

    from app.domain import suggest as mod

    # 낱말 겹침은 이제 **물러설 자리**라 `낱말제안` 으로 옮겼다 (5단계)
    src = inspect.getsource(mod.낱말제안)
    assert "말낱말 <= 보드전체" in src


def test_z_02b_마크업이_새어_나오지_않는다():
    """`04.22 1차 구상안** ⇒ …` 처럼 `**` 가 그대로 붙어 나왔다."""
    from app.domain.suggest import 할일줄

    for 말 in 할일줄("**시설 대걸레 문의**\n~~취소된 것 확인~~\n"):
        assert "**" not in 말 and "~~" not in 말


def test_z_02c_가운데_있는_말은_할_일이_아니다():
    """`외부강사 섭외의 경우 진행해보면서 대안 설정이 계속 필요할 것으로
    예상됨` 은 할 일이 아니라 의견이다. **꼬리에 있어야** 한다."""
    from app.domain.suggest import 할일줄

    말들 = 할일줄(
        "- 세미나실 셀프조작 가능여부 확인 필요\n"
        "- 외부강사 섭외의 경우 진행해보면서 대안 설정이 계속 필요할 것으로 예상됨\n")
    assert any("세미나실" in x for x in 말들)
    assert not any("예상됨" in x for x in 말들)


# ── 5 ~ 7. 논의 제안의 하한과 빈 목록 ────────────────────────────────


def test_z_05_흔한_낱말만으로는_논의_제안이_안_된다(짧은업무):
    """`제작` 은 이 보드에서 업무 이름 다섯 개에 나온다. 그런 낱말만으로
    겹친 것은 관계를 말해 주지 않는다."""
    from app.domain.suggest import 흔한낱말, board_as_of

    with app_session() as db:
        retreat = db.get(models.Retreat, 짧은업무)
        rows = board_as_of(db, retreat, dt.date(2026, 6, 1))
    assert "제작" in 흔한낱말(rows), "흔한 낱말을 못 골라낸다"


def test_z_07_빈_목록이_실제로_나온다(짧은업무):
    """4-10 조건 4. 회의 50건에서 24건이 빈 목록이었다 — **하한이 아무
    일도 안 하는 것이 아니다.**"""
    것들 = _제안(짧은업무, "- 오늘 날씨가 좋았습니다\n")
    assert [x for x in 것들 if x.kind == "discussion"] == []


def test_z_07b_잘렸으면_잘렸다고_말한다(짧은업무):
    """조용히 자르지 않는다. 걸린 것이 더 있다는 사실을 말한다."""
    것들 = _제안(짧은업무, "- 명찰 제작 교재 제작 출력물 제작 비품 제작 영상 제작 포토존 선발대 운영\n")
    더 = [x for x in 것들 if x.kind == "더있음"]
    논의 = [x for x in 것들 if x.kind == "discussion"]
    assert len(논의) <= 5
    if 더:
        assert "더 있습니다" in 더[0].text


# ── 8. 형광펜에 뜻을 붙이지 않는다 ───────────────────────────────────


def test_z_08_형광펜이_뜻을_주장하지_않는다():
    """`⟨미완료?⟩` 는 물음표가 있어도 뜻을 주장한다 — 나중에 읽는 사람은
    물음표를 안 읽고 "미완료" 만 읽는다. 근거는 2/20 이다."""
    from scripts.import_meetings import mark_highlights

    나온것 = mark_highlights('<span color="yellow_bg">대걸레 문의</span>')
    assert "⟨형광펜⟩" in 나온것
    assert "미완료" not in 나온것

    본문 = (ROOT / "scripts" / "import_meetings.py").read_text(encoding="utf-8")
    assert "⟨미완료?⟩" not in 본문.replace("처음에는 `⟨미완료?⟩` 였는데", "")

    from app.domain import meeting_import

    doc = meeting_import.__doc__ or ""
    assert "뜻을 붙이지 않는다" in doc
    assert "6-9" in doc, "왜 사실만 남기는지가 없다"


# ── 9. 말한 것에 대한 판정을 적어 둔다 ───────────────────────────────


def test_z_09_날짜같은줄_2건의_판정이_적혔다():
    """**경고는 판정이 적히는 순간 제 몫을 다한다** — 다음에 돌릴 때 같은
    두 줄을 또 들여다볼 이유가 없다."""
    import inspect

    from app.domain import meeting_import

    # 판정은 **자르는 함수** 옆에 있어야 한다 — 다음에 돌릴 때 읽는 자리다
    doc = inspect.getdoc(meeting_import.cut) or ""
    assert "이미 본 것" in doc
    assert "26.04.22 1차 구상안" in doc and "26.05.17" in doc
    assert "접어 둔 토글" in doc and "상호 참조" in doc
    assert "자르지 않음" in doc or "지금 처리" in doc


# ── 10 · 11. 성적표 ──────────────────────────────────────────────────


def test_z_10_성적표의_표본이_먼저_못박혔다():
    """눈에 띄는 것부터 채우면 점수가 표본을 따라 움직인다."""
    표 = (ROOT / "docs" / "review" / "제안-성적표.md").read_text(encoding="utf-8")
    assert "표본 — 이 넷만 봅니다" in 표
    for 날 in ("2026-03-29", "2026-05-24", "2026-07-05", "2026-08-09"):
        assert 날 in 표
    assert "그 안의 제안을 전부" in 표
    assert "건너뛰지 않습니다" in 표
    # 걸리는 시간을 잰다 — 안 채운 성적표는 없는 것과 같다
    assert "걸린 시간" in 표 and "30분" in 표


def test_z_11_X_이유를_한_단어로_고르게_되어_있다():
    표 = (ROOT / "docs" / "review" / "제안-성적표.md").read_text(encoding="utf-8")
    for 이유 in ("다른업무", "할일아님", "중복", "기타"):
        assert 이유 in 표
    assert "X 이유별" in 표, "세는 자리가 없다"


# ── 12. 10장에 두 줄 ─────────────────────────────────────────────────


def test_z_12_10장에_두_번_이상_당한_것이_적혔다():
    """**횟수가 적혀 있어야 다음 사람이 진지하게 읽는다.**"""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    at = text.index("## 10. 화면 변경을 끝냈다고")
    section = text[at : text.index("## 11.", at)]

    assert "글자를 찾는 시험은 코드와 설명을 못 가립니다" in section
    assert "네 번" in section
    for 이름 in ("code_only", "test_v_09", "_token", "test_y_04"):
        assert 이름 in section, f"{이름} 이 안 적혔다"

    assert "pytest 는 화면을 못 봅니다" in section
    assert "세 번" in section
    assert ".mlist" in section


# ══════════════════════════════════════════════════════════════════════
# 화면 — 제안이 무엇을 하자는 것인지 말한다 (세 번째 리뷰)
# ══════════════════════════════════════════════════════════════════════


# ── 1 ~ 4. 하려는 일이 먼저, 크게 ────────────────────────────────────


def _회의하나(회차와업무):
    """시험용 회의 하나 + 그 업무 id. **`test_` 로 시작하면 안 된다** —
    pytest 가 시험으로 수집해서 반환값을 두고 경고한다."""
    run_id = 회차와업무["run_id"]
    with app_session() as db:
        retreat = db.get(models.Retreat, 회차와업무["retreat_id"])
        m = models.Meeting(retreat_id=retreat.id, title="6월 회의",
                           meeting_date=dt.date(2026, 6, 1),
                           body=회차와업무["title"] + " 일정 논의")
        db.add(m)
        db.commit()
        meeting_id = m.id
    return meeting_id, run_id


def test_w2_01b_화면이_하려는_일을_먼저_크게_그린다():
    """순서가 뒤집혀 있었다 — 하려는 일이 먼저, 근거는 그 아래 작게."""
    js = (ROOT / "app" / "static" / "js" / "meeting.js").read_text(encoding="utf-8")
    # 하려는 일이 먼저 그려진다
    at머리 = js.index("const 머리 =")
    at근거 = js.index("const 근거 =")
    assert at머리 < at근거, "근거를 먼저 만든다"
    assert 'class="mt-do"' in js
    assert "${머리}${근거}" in js or "${머리}${이미}${근거}" in js

    css = (ROOT / "app" / "static" / "css" / "retreat.css").read_text(encoding="utf-8")
    import re as _r

    def decl(sel):
        body = _r.sub(r"/\*.*?\*/", "", css, flags=_r.S)
        at = body.index(sel + "{")
        return body[at + len(sel) + 1 : body.index("}", at)]

    # 크기는 이제 **눈금**에서 끌어온다 — 숫자가 아니라 단으로 견준다.
    # 숫자로 재던 시험은 눈금을 도입하는 순간 못 재게 되는데, 그때
    # "위계가 지켜지는가" 라는 물음 자체는 그대로다
    단 = ["--fz-xs", "--fz-sm", "--fz-md", "--fz-base",
         "--fz-lg", "--fz-xl", "--fz-2xl", "--fz-3xl", "--fz-4xl"]
    번호 = lambda sel: 단.index(
        _r.search(r"font-size:var\((--fz[\w-]*)\)", decl(sel)).group(1))
    assert 번호(".mt-do") > 번호(".mt-sug-why"), "하려는 일이 근거보다 작다"
    # 4-0 — 조용하게. 느낌표도 권유도 없다
    assert "!" not in js[js.index("function 줄("): js.index("function 그린다(")]


def test_w2_03_어느_회의에서_온_것인지가_제안마다_보인다(회차와업무, admin_client):
    meeting_id, run_id = _회의하나(회차와업무)
    data = 제안받기(admin_client, meeting_id)
    assert data["items"], "제안이 없으면 이 시험이 아무것도 안 지킨다"
    for x in data["items"]:
        assert x["action"], "무엇을 하자는 것인지가 없다"
        assert x["from"], "어느 회의에서 온 것인지가 없다"
        assert "2026-06-01" in x["from"]
        if x["kind"] == "discussion":
            # 하려는 일이 **문장**이다 — 업무 이름만 있는 것이 아니다
            assert "논의로 남깁니다" in x["action"]
            assert "「" in x["action"]


def test_w2_04_새_업무_제안도_같은_모양이다(짧은업무, admin_client):
    with app_session() as db:
        retreat = db.get(models.Retreat, 짧은업무)
        m = models.Meeting(retreat_id=retreat.id, title="6월 회의",
                           meeting_date=dt.date(2026, 6, 1),
                           body="- 세미나실 셀프조작 가능여부 확인 필요\n")
        db.add(m)
        db.commit()
        meeting_id = m.id
    data = 제안받기(admin_client, meeting_id)
    새것 = [x for x in data["items"] if x["kind"] == "new"]
    if not 새것:
        pytest.skip("이 회의에서는 새 업무 제안이 안 나온다")
    for x in 새것:
        assert x["action"] and "새 업무로 만듭니다" not in x["action"], \
            "하려는 일에 우리 말머리가 섞였다 — 화면이 라벨로 붙인다"
        assert x["from"]
    js = (ROOT / "app" / "static" / "js" / "meeting.js").read_text(encoding="utf-8")
    assert "새 업무로 만들기" in js, "무엇을 만들자는 것인지 라벨이 없다"


# ── 5 · 6. 누르기 전에 무엇이 적히는지 ───────────────────────────────


def test_w2_05_누르기_전에_남을_문장을_볼_수_있다(회차와업무, admin_client):
    """4-10 이 "무엇을 보고 그렇게 말하는지 함께 보인다" 고 한 자리와 같다."""
    meeting_id, run_id = _회의하나(회차와업무)
    data = 제안받기(admin_client, meeting_id)
    논의 = [x for x in data["items"] if x["kind"] == "discussion"]
    assert 논의
    for x in 논의:
        assert x["preview"], "남을 문장이 없다"
        assert "회의록" in x["preview"] and "에서 옮김" in x["preview"]

    # **미리보기와 실제 저장이 같은 함수를 쓴다** — 두 벌이면 갈린다
    본문 = (ROOT / "app" / "routers" / "meetings.py").read_text(encoding="utf-8")
    assert 본문.count("def discussion_body(") == 1
    assert 본문.count("discussion_body(meeting)") == 2

    js = (ROOT / "app" / "static" / "js" / "meeting.js").read_text(encoding="utf-8")
    assert "남을 내용 보기" in js


def test_w2_05b_보여준_것과_남는_것이_같다(회차와업무, admin_client):
    meeting_id, run_id = _회의하나(회차와업무)
    보여준것 = 제안받기(admin_client, meeting_id)
    미리 = next(x["preview"] for x in 보여준것["items"] if x["kind"] == "discussion")
    admin_client.post(f"/meetings/{meeting_id}/suggestions/apply",
                      json={"run_id": run_id})
    with app_session() as db:
        남은것 = db.scalars(select(models.DiscussionEntry)
                          .where(models.DiscussionEntry.run_id == run_id)).all()
    assert len(남은것) == 1
    assert 남은것[0].body == 미리, "보여준 것과 남는 것이 다르다"


def test_w2_06_이미_있으면_말한다(회차와업무, admin_client):
    """같은 것을 두 번 남기게 두지 않는다 — 두 번 남으면 어느 것이 맞는지
    알 수 없고, 지우는 길은 그 업무의 논의 탭뿐이다."""
    meeting_id, run_id = _회의하나(회차와업무)
    처음 = 제안받기(admin_client, meeting_id)
    assert not any(x["already"] for x in 처음["items"])

    admin_client.post(f"/meetings/{meeting_id}/suggestions/apply",
                      json={"run_id": run_id})
    다음 = 제안받기(admin_client, meeting_id)
    걸린것 = [x for x in 다음["items"] if x["run_id"] == run_id]
    assert 걸린것 and 걸린것[0]["already"], "이미 있는데 말하지 않는다"

    js = (ROOT / "app" / "static" / "js" / "meeting.js").read_text(encoding="utf-8")
    assert "이미 있습니다" in js and "그래도 남기기" in js


# ── 7 ~ 9. 본문에 태그가 안 샌다 ─────────────────────────────────────


def test_w2_07_본문에_태그가_남지_않는다():
    from scripts.import_meetings import mark_highlights

    글 = ('- <span color="red_bg">수련회 간략광고 6/7 </span>\n'
          '<details>\n<summary>접힌 것</summary>\n'
          '\t- <span color="red">오티 - 순서 등 전달</span>\n'
          '</details>\n')
    나온것 = mark_highlights(글)
    for 태그 in ("<span", "</span>", "{color=", "<details", "<summary"):
        assert 태그 not in 나온것, f"{태그} 가 남았다"
    assert "오티 - 순서 등 전달" in 나온것, "내용까지 지웠다"
    assert "접힌 것" in 나온것


def test_w2_08_노란_형광펜이_두_모양_다_바뀐다():
    """노션에 두 가지 모양으로 적혀 있다. 하나만 처리해서 **안내문은
    ⟨형광펜⟩ 을 설명하는데 본문에는 `{color="yellow_bg"}` 가 남았다.**"""
    from scripts.import_meetings import mark_highlights

    assert "⟨형광펜⟩대걸레 문의" in mark_highlights(
        '<span color="yellow_bg">대걸레 문의</span>')
    # 뒤에 붙는 모양
    나온것 = mark_highlights('\t- 만들어보겠다 (박민준) {color="yellow_bg"}')
    assert "⟨형광펜⟩" in 나온것 and "{color=" not in 나온것
    assert "만들어보겠다 (박민준)" in 나온것


def test_w2_09_빨간_형광펜을_따로_적고_이유가_있다():
    """**모르면 합치지 않는다.** 합치면 두 색이 같은 뜻이었다는 주장이 되고,
    그 주장은 아무도 한 적이 없다 (6-9)."""
    from scripts.import_meetings import mark_highlights

    나온것 = mark_highlights('<span color="red_bg">면장갑</span>')
    assert "⟨빨간형광펜⟩면장갑" in 나온것
    assert "⟨형광펜⟩면장갑" not in 나온것, "노란 것과 합쳤다"

    import inspect

    from scripts import import_meetings

    doc = inspect.getdoc(import_meetings.mark_highlights) or ""
    assert "뜻이 같은지 다른지 모른다" in doc
    assert "모르면 합치지 않는다" in doc
    assert "6-9" in doc


# ── 11. 고르는 방식 동결 — **풀었다** ────────────────────────────────
#
# `test_w2_11_고르는_방식은_안_건드렸다` 가 여기 있었다. `suggest.py` 의
# 하한·흔한 낱말·그물 숫자를 **소스 문자열로 붙들어** 아무도 못 건드리게
# 한 시험이다.
#
# **표본을 지키려고 둔 것이고 목적을 다했다.** 성적표를 채우는 동안
# 제안이 움직이면 채운 것이 무엇을 잰 것인지 알 수 없게 되므로 얼려
# 두었는데, 2026-09-03 에 사람이 21개를 다 채웠다(`docs/review/제안-성적표.md`).
# 시험 자신이 적어 둔 해제 조건("지금 성적표를 채우려는 참이다")이
# 끝났으므로 지운다.
#
# **동결 시험을 남겨 두면 안 된다.** 이유가 끝났는데 남아 있으면 다음
# 사람이 고칠 수 없는 이유를 못 찾은 채 시험을 지우게 되고, 그때는
# "왜 얼려 뒀는지" 도 함께 사라진다. 그래서 지운 자리에 이 글을 남긴다.
#
# 다음 판(문장을 읽는 방식)은 **같은 네 회의**로 다시 내서 견준다 —
# 개수가 아니라 회의가 축이다. 2판은 27개라 개수로는 견줄 수 없다.
