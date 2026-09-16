"""노션 업무를 그대로 들인다 (2026-09-16 · `scripts/노션업무들이기.py`).

값은 전부 지어낸 것이다 — 실제 노션 줄(data/노션업무전체.real.tsv)은 열지 않는다.
**고장을 심어 잰다** — 다른 회차를 지키는 줄, 관계를 양쪽에 펴는 줄, 다시 세기가
실제로 빨개지는지를 각각 깨뜨려 본다.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import re
import sys

import pytest
from sqlalchemy import select

from app import db as app_db
from app import models

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _들이기():
    이름 = "노션업무들이기_시험"
    spec = importlib.util.spec_from_file_location(이름, ROOT / "scripts" / "노션업무들이기.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[이름] = mod
    spec.loader.exec_module(mod)
    return mod


줄들 = [
    # id, 제목, 업무속성, 담당팀, 관련 팀, 시작, 마감, 관련업무, 설명
    ("n1", "포스터 제작", "Main", "4 스케치", '["4 스케치","1 총무M"]', "2026-06-01", "", '["n2"]', ""),
    ("n2", "포스터 확정", "Sub", "4 스케치", "", "2026-06-08", "2026-06-10", "", "쓰는 법을 여기 적는다"),
    ("n3", "중간점검", "Sch", "2 봉사팀 공통", '["교개협"]', "2026-07-05", "", '["n9","n1"]', ""),
    ("n4", "구분이 없는 줄", "", "7 재정", "", "", "", "", ""),
    ("(D-3주차)", "(D-3주차)", "", "0", "", "2026-08-02", "", "", ""),
]


def _파일(tmp_path, 값=줄들) -> pathlib.Path:
    p = tmp_path / "노션업무전체.real.tsv"
    p.write_text("\n".join("\t".join(r) for r in 값) + "\n", encoding="utf-8")
    return p


def _회차(db, 이름="2026 여름수련회 Belong", 개회=dt.date(2026, 8, 21)):
    r = models.Retreat(name=이름, start_date=개회, end_date=개회 + dt.timedelta(days=2))
    db.add(r)
    db.flush()
    for 키, 나 in (("sketch", "4 스케치"), ("jaejeong", "7 재정"), ("chongmu", "1 총무팀")):
        db.add(models.Department(retreat_id=r.id, key=키, name=나))
    db.flush()
    return r


def _옛run(db, retreat, 제목="옛 업무", included=True):
    lib = models.TaskLibrary(title=제목, kind="main")
    db.add(lib)
    db.flush()
    run = models.TaskRun(library_id=lib.id, retreat_id=retreat.id, included=included, run_no=1)
    db.add(run)
    db.commit()          # **commit 까지 한다** — 되돌림을 재는 시험이 rollback 으로 심어 둔 것까지 날린다
    return lib, run


def _run수(db, retreat) -> int:
    """세션이 든 객체가 아니라 DB 를 센다 — 지운 행은 commit 전까지 세션에 남는다."""
    from sqlalchemy import func
    return db.scalar(select(func.count(models.TaskRun.id)).where(models.TaskRun.retreat_id == retreat.id))


# ── 칸 ────────────────────────────────────────────────────────────────

def test57_a01_라이브러리_칸은_NULL_로_붙고_부팅은_값을_안_채운다():
    붙는 = [(t, c, d) for t, c, d in app_db._ADDED_COLUMNS if (t, c) == ("task_library", "notion_page_id")]
    assert len(붙는) == 1
    assert "NOT NULL" not in 붙는[0][2] and "DEFAULT" not in 붙는[0][2]
    본것 = [p for p in (ROOT / "app").rglob("*.py") if p.name not in ("models.py", "db.py")]
    assert len(본것) > 10, "app/ 에서 훑은 파일이 없다 — 아무것도 안 보는 검사다"
    assert [p.name for p in 본것 if "notion_page_id" in p.read_text(encoding="utf-8")] == []
    db글 = (ROOT / "app" / "db.py").read_text(encoding="utf-8")
    assert len(re.findall(r'"task_library", "notion_page_id"', db글)) == 1
    assert models.TaskLibrary.__table__.c.notion_page_id.nullable


# ── 읽기 ──────────────────────────────────────────────────────────────

def test57_b01_표지를_빼고_읽고_읽은_수_셋을_돌려준다(tmp_path):
    m = _들이기()
    읽은것, 수 = m.읽는다(_파일(tmp_path))
    assert [r["id"] for r in 읽은것] == ["n1", "n2", "n3", "n4"], "D-주차 표지가 섞였다"
    assert 읽은것[1]["설명"] == "쓰는 법을 여기 적는다"
    # **셋을 다 돌려준다** — 마지막 수 하나만으로는 옮겨 적다 빠진 줄을 못 본다
    assert 수 == {"읽은 줄": 5, "D-주차 표지": 1, "남은 줄": 4}
    assert 읽은것[0]["줄번호"] == 1


def test57_b02_id_가_겹치거나_비면_멈춘다(tmp_path):
    m = _들이기()
    with pytest.raises(m.멈춤, match="같은 노션 id"):
        m.읽는다(_파일(tmp_path, 줄들 + [줄들[0]]))
    with pytest.raises(m.멈춤, match="id 나 제목"):
        m.읽는다(_파일(tmp_path, [("", "제목만 있는 줄", "Main", "", "", "", "", "", "")]))
    with pytest.raises(m.멈춤, match="파일이 없습니다"):
        m.읽는다(tmp_path / "없는파일.tsv")


def test57_b03_줄이_이상하면_줄_번호를_말하고_멈춘다(tmp_path):
    """값을 못 찍는 파일이라 줄 번호가 사람의 유일한 손잡이다(4-18)."""
    m = _들이기()
    한칸더 = [줄들[0], 줄들[1] + ("남는 칸",)]
    with pytest.raises(m.멈춤, match="2번째 줄의 칸이 10개"):
        m.읽는다(_파일(tmp_path, 한칸더))
    나쁜날짜 = [줄들[0], ("n8", "날짜가 이상한 줄", "Main", "", "", "2026-13-99", "", "", "")]
    with pytest.raises(m.멈춤, match="2번째 줄의 날짜 꼴"):
        m.읽는다(_파일(tmp_path, 나쁜날짜))
    거꾸로 = [("n8", "거꾸로", "Main", "", "", "2026-06-10", "2026-06-01", "", "")]
    with pytest.raises(m.멈춤, match="1번째 줄의 마감이 시작보다"):
        m.읽는다(_파일(tmp_path, 거꾸로))
    마감만 = [("n8", "마감만", "Main", "", "", "", "2026-06-01", "", "")]
    with pytest.raises(m.멈춤, match="시작 없이 마감만"):
        m.읽는다(_파일(tmp_path, 마감만))
    # 막히면 안 되는 쪽 — 뒤의 빈 칸을 안 쓴 줄은 그대로 지나간다
    짧은줄 = [("n8", "칸이 모자란 줄", "Main", "1 총무팀")]
    남은, 수 = m.읽는다(_파일(tmp_path, 짧은줄))
    assert 수["남은 줄"] == 1 and 남은[0]["설명"] == ""


# ── 계획 ──────────────────────────────────────────────────────────────

def test57_c01_구분_담당_관련팀을_옮기고_못_옮긴_것을_센다(db, tmp_path):
    m = _들이기()
    r = _회차(db)
    판 = m.고른다(db, r, m.읽는다(_파일(tmp_path))[0])
    세울 = {x["노션id"]: x for x in 판.세울}
    assert [세울[k]["구분"] for k in ("n1", "n2", "n3", "n4")] == ["main", "sub", "schedule", "main"]
    assert 세울["n1"]["부서키"] == "sketch" and 세울["n1"]["부서id"] is not None
    # 「2 봉사팀 공통」 은 앱에 부서가 없다 — 비우고 센다(2장)
    assert 세울["n3"]["부서키"] is None
    assert 판.수["담당을 못 옮긴 줄"] == 1
    assert 판.수["구분 없어 기본으로 둘 줄"] == 1
    # 「교개협」 도 앱 부서가 아니다
    assert 세울["n3"]["관련팀"] == [] and 판.수["관련팀을 일부 버린 줄"] == 1
    assert 세울["n1"]["관련팀"] == ["sketch", "chongmuM"]
    assert 세울["n2"]["규칙"] == "쓰는 법을 여기 적는다" and 판.수["업무 규칙이 붙는 줄"] == 1
    assert 판.수["날짜가 없는 줄"] == 1


def test57_c02_관계는_양쪽에_펴고_표_밖은_못_옮긴_것으로_센다(db, tmp_path):
    m = _들이기()
    r = _회차(db)
    판 = m.고른다(db, r, m.읽는다(_파일(tmp_path))[0])
    # n1→n2 한쪽만 적혀 있어도 n2 쪽에도 선다. n3→n1 도 마찬가지
    assert 판.관계 == {"n1": ["n2", "n3"], "n2": ["n1"], "n3": ["n1"]}
    assert 판.수["노션이 적은 관련업무 칸의 항목"] == 3
    assert 판.수["옮길 수 있는 관련업무 항목"] == 2
    assert 판.수["자기·표지·이 표 밖을 가리켜 못 옮기는 항목"] == 1, "없는 id(n9)를 못 셌다"


def test57_c03_날짜는_상대_자리로_바뀐다(db, tmp_path):
    from app.domain import dweek
    m = _들이기()
    r = _회차(db)
    판 = m.고른다(db, r, m.읽는다(_파일(tmp_path))[0])
    세울 = {x["노션id"]: x for x in 판.세울}
    자리 = 세울["n2"]["자리"]
    돌아온 = dweek.resolve_dates(r.start_date, anchor=자리["date_anchor"], d_week=자리["default_d_week"],
                               offset_days=자리["default_offset_days"], span_days=자리["default_span_days"])
    assert 돌아온 == (dt.date(2026, 6, 8), dt.date(2026, 6, 10)), "상대 자리로 갔다 오면 날짜가 달라진다"
    assert 세울["n4"]["시작"] is None, "날짜가 없는 줄에 없던 날짜가 생겼다"


def test57_c04_모르는_갈래는_멈춘다(db, tmp_path):
    m = _들이기()
    r = _회차(db)
    노션 = m.읽는다(_파일(tmp_path))[0]
    with pytest.raises(m.멈춤, match="지움방식"):
        m.고른다(db, r, 노션, 지움방식="지움")
    with pytest.raises(m.멈춤, match="구분없음"):
        m.고른다(db, r, 노션, 구분없음="Main")
    r.start_date = None
    with pytest.raises(m.멈춤, match="개회일"):
        m.고른다(db, r, 노션)


# ── 넣기 ──────────────────────────────────────────────────────────────

def test57_d01_뺌은_run_을_안_지우고_included_만_끈다(db, tmp_path):
    m = _들이기()
    r = _회차(db)
    _, 옛 = _옛run(db, r)
    db.add(models.TaskAttachment(run_id=옛.id, original_name="시안.pdf", stored_name="x", size_bytes=1))
    db.flush()
    판 = m.고른다(db, r, m.읽는다(_파일(tmp_path))[0], 지움방식="뺌")
    m.넣는다(db, r, 판)
    남은 = db.scalars(select(models.TaskRun).where(models.TaskRun.retreat_id == r.id)).all()
    assert len(남은) == 1 + 4
    assert db.get(models.TaskRun, 옛.id) is not None and db.get(models.TaskRun, 옛.id).included is False
    assert db.scalar(select(models.TaskAttachment.id)) is not None, "첨부가 사라졌다"
    새것 = [t for t in 남은 if t.id != 옛.id]
    # **번호가 겹치면 안 된다**(4-14) — 옛 run 이 1 을 쥔 채 남으므로 새것은 2 부터 잇는다
    assert sorted(t.run_no for t in 새것) == [2, 3, 4, 5]
    assert len({t.run_no for t in 남은}) == len(남은), "회차 안에서 run_no 가 겹친다"
    assert all(t.status == "대기" for t in 새것)


def test57_d01b_삭제면_번호가_1_부터고_잃을_것을_미리_센다(db, tmp_path):
    m = _들이기()
    r = _회차(db)
    _, 옛 = _옛run(db, r)
    db.add(models.TaskAttachment(run_id=옛.id, original_name="시안.pdf", stored_name="x", size_bytes=1))
    db.commit()
    # 0장 — 「어느 표에 몇 행이 걸리는지를 먼저 세어 사람에게 보이고」
    판 = m.고른다(db, r, m.읽는다(_파일(tmp_path))[0], 지움방식="삭제")
    걸림 = {k: v for k, v in 판.수.items() if k.startswith("삭제면 걸림")}
    # **스키마와 견준다** — 손으로 적은 표끼리 견주면 그 표가 틀려도 초록이다(두 번째 검토 [A])
    from app.models import Base, TaskRun as _TR
    스키마 = {(표.name, fk.parent.name, (fk.ondelete or "NO ACTION").upper())
            for 표 in Base.metadata.sorted_tables for fk in 표.foreign_keys
            if fk.column is _TR.__table__.c.id}
    assert 스키마, "task_runs 를 가리키는 FK 를 하나도 안 찾았다 — 아무것도 안 보는 검사다"
    assert {(t, c, o) for _, t, c, o in m.걸리는곳()} == 스키마, "걸리는 곳이 스키마와 다르다"
    assert 걸림["삭제면 걸림 · 첨부(CASCADE)"] == 1
    assert 걸림["삭제면 걸림 · 확인 요청(NO ACTION)"] == 0
    # 4-14 — 「삭제」 라도 1부터 주지 않는다(1..102 가 살아 있는 다른 업무를 가리키게 된다)
    assert 판.번호시작 == 2
    m.넣는다(db, r, 판)
    assert sorted(t.run_no for t in db.scalars(
        select(models.TaskRun).where(models.TaskRun.retreat_id == r.id))) == [2, 3, 4, 5]


def test57_d01d_SET_NULL_은_삭제를_안_막는다(db, tmp_path):
    """CASCADE · SET NULL · NO ACTION 은 뜻이 다르다 — 막는 것은 마지막 둘뿐이다(0장 · 두 번째 검토 [A])."""
    m = _들이기()
    assert dict((표, 걸림) for _, 표, _, 걸림 in m.걸리는곳())["meeting_items"] == "SET NULL"
    r = _회차(db)
    _, 옛 = _옛run(db, r)
    회의 = models.Meeting(title="회의", origin="사람")
    db.add(회의)
    db.flush()
    db.add(models.MeetingItem(meeting_id=회의.id, kind="할일", content="한 줄", converted_run_id=옛.id))
    db.commit()
    판 = m.고른다(db, r, m.읽는다(_파일(tmp_path))[0], 지움방식="삭제")
    assert 판.수["삭제면 걸림 · 회의 항목이 가리킴(SET NULL)"] == 1
    m.넣는다(db, r, 판)                       # **막히면 안 된다** — 가리킴만 잃는다
    assert _run수(db, r) == 4


def test57_d01c_NO_ACTION_이_걸려_있으면_삭제는_사람_말로_멈춘다(db, tmp_path):
    """안 막으면 flush 에서 원시 트레이스백이 난다 — 사람이 보는 것은 그것뿐이다."""
    m = _들이기()
    r = _회차(db)
    _, 옛 = _옛run(db, r)
    부서 = db.scalar(select(models.Department).where(models.Department.retreat_id == r.id))
    db.add(models.ReviewRequest(run_id=옛.id, retreat_id=r.id, department_id=부서.id, status="대기"))
    db.commit()
    판 = m.고른다(db, r, m.읽는다(_파일(tmp_path))[0], 지움방식="삭제")
    assert 판.수["삭제면 걸림 · 확인 요청(NO ACTION)"] == 1
    with pytest.raises(m.멈춤, match="FK 가 막는"):
        m.넣는다(db, r, 판)
    db.rollback()
    # 막히면 안 되는 쪽 — 걸린 것이 없으면 그대로 지난다
    db.delete(db.scalar(select(models.ReviewRequest)))
    db.commit()
    판2 = m.고른다(db, r, m.읽는다(_파일(tmp_path))[0], 지움방식="삭제")
    m.넣는다(db, r, 판2)
    assert _run수(db, r) == 4


def test57_d05_같은_페이지_id_가_이미_있으면_두_번_안_들인다(db, tmp_path):
    m = _들이기()
    r = _회차(db)
    판 = m.고른다(db, r, m.읽는다(_파일(tmp_path))[0])
    m.넣는다(db, r, 판)
    db.commit()
    with pytest.raises(m.멈춤, match="이미 들여온"):
        m.고른다(db, r, m.읽는다(_파일(tmp_path))[0])


def test57_d02_삭제는_run_행을_지운다(db, tmp_path):
    m = _들이기()
    r = _회차(db)
    lib, 옛 = _옛run(db, r)
    판 = m.고른다(db, r, m.읽는다(_파일(tmp_path))[0], 지움방식="삭제")
    m.넣는다(db, r, 판)
    # **id 로 견주지 않는다** — 표가 비면 SQLite 가 rowid 를 다시 1부터 준다(새 run 이 옛 id 를 받는다)
    남은 = db.scalars(select(models.TaskRun).where(models.TaskRun.retreat_id == r.id)).all()
    assert len(남은) == 4
    assert lib.id not in {t.library_id for t in 남은}, "삭제인데 옛 run 이 남았다"
    assert db.get(models.TaskLibrary, lib.id) is not None, "라이브러리까지 지웠다"


def test57_d03_관련업무가_양쪽_라이브러리에_실제로_적힌다(db, tmp_path):
    m = _들이기()
    r = _회차(db)
    판 = m.고른다(db, r, m.읽는다(_파일(tmp_path))[0])
    m.넣는다(db, r, 판)
    쪽 = {l.notion_page_id: l for l in db.scalars(select(models.TaskLibrary))
         if l.notion_page_id}
    assert set(쪽) == {"n1", "n2", "n3", "n4"}
    assert sorted(쪽["n1"].related_library_ids) == sorted([쪽["n2"].id, 쪽["n3"].id])
    assert 쪽["n2"].related_library_ids == [쪽["n1"].id], "한쪽만 적힌 노션 관계가 양쪽에 안 섰다"
    assert 쪽["n4"].related_library_ids == []
    assert 쪽["n2"].rules == "쓰는 법을 여기 적는다"


def test57_d04_다른_회차는_안_건드린다(db, tmp_path):
    m = _들이기()
    r1, r2 = _회차(db), _회차(db, "2027 여름수련회", dt.date(2027, 8, 20))
    공용 = models.TaskLibrary(title="두 회차가 같이 쓰는 업무", kind="main")
    db.add(공용)
    db.flush()
    for 회차 in (r1, r2):
        db.add(models.TaskRun(library_id=공용.id, retreat_id=회차.id, run_no=1))
    db.commit()
    for 방식 in ("뺌", "삭제"):
        판 = m.고른다(db, r1, m.읽는다(_파일(tmp_path))[0], 지움방식=방식)
        assert 판.수["그 라이브러리를 함께 쓰는 다른 회차의 run"] == 1
        m.넣는다(db, r1, 판)
        남 = db.scalars(select(models.TaskRun).where(models.TaskRun.retreat_id == r2.id)).all()
        assert len(남) == 1 and 남[0].included is True, f"{방식} 이 다른 회차의 run 을 건드렸다"
        assert db.get(models.TaskLibrary, 공용.id) is not None, f"{방식} 이 공용 라이브러리를 지웠다"
        db.rollback()            # 심은 것은 commit 돼 있으므로 이 판에서 넣은 것만 물러난다
        assert _run수(db, r1) == 1


# ── 돌리기 ────────────────────────────────────────────────────────────

def test57_e01_미리보기는_아무것도_안_바꾼다(db, tmp_path, capsys):
    m = _들이기()
    r = _회차(db)
    _옛run(db, r)
    전 = m.센다(db, r)
    m.돌린다(db, r.id, 실행=False, 파일=_파일(tmp_path), 사본=False)
    assert m.센다(db, r) == 전
    찍힌 = capsys.readouterr().out
    assert "노션 줄(표지 뺌): 4" in 찍힌 and "바꾸지 않았습니다" in 찍힌
    # **화면에 나오는지까지 본다** — 사람이 노션과 대조하는 것은 이 셋이다(두 번째 검토 [H])
    assert "읽은 줄: 5" in 찍힌 and "D-주차 표지: 1" in 찍힌 and "남은 줄: 4" in 찍힌
    assert "포스터" not in 찍힌, "미리보기에 값이 찍혔다"


def test57_e01b_삭제가_막힐_것이면_미리보기가_미리_말한다(db, tmp_path, capsys):
    """11-2 의 순서(미리보기 → 실행)는 미리보기가 실행 결과를 미리 말한다는 전제 위에 있다."""
    m = _들이기()
    r = _회차(db)
    _, 옛 = _옛run(db, r)
    부서 = db.scalar(select(models.Department).where(models.Department.retreat_id == r.id))
    db.add(models.ReviewRequest(run_id=옛.id, retreat_id=r.id, department_id=부서.id, status="대기"))
    db.commit()
    m.돌린다(db, r.id, 실행=False, 파일=_파일(tmp_path), 사본=False, 지움방식="삭제")
    assert "이대로 --실행 하면" in capsys.readouterr().out
    # 막히면 안 되는 쪽 — 「뺌」 은 그 줄을 안 낸다
    m.돌린다(db, r.id, 실행=False, 파일=_파일(tmp_path), 사본=False, 지움방식="뺌")
    assert "이대로 --실행 하면" not in capsys.readouterr().out


def test57_e02_실행은_다시_세어_맞을_때만_넣는다(db, tmp_path, capsys):
    m = _들이기()
    r = _회차(db)
    _옛run(db, r)
    m.돌린다(db, r.id, 실행=True, 파일=_파일(tmp_path), 사본=False)
    수 = m.센다(db, r)
    assert 수["run"] == 5 and 수["산 run"] == 4
    assert 수["산 run · main"] == 2 and 수["산 run · sub"] == 1 and 수["산 run · schedule"] == 1
    assert "포스터" not in capsys.readouterr().out


def test57_e03_다시_세기에_고장을_심으면_되돌린다(db, tmp_path, monkeypatch):
    m = _들이기()
    r = _회차(db)
    _옛run(db, r)
    전 = m.센다(db, r)
    진짜 = m.센다
    monkeypatch.setattr(m, "센다", lambda db_, rt: dict(진짜(db_, rt), **{"run": 999}))
    with pytest.raises(m.멈춤, match="run 수가 계획과"):
        m.돌린다(db, r.id, 실행=True, 파일=_파일(tmp_path), 사본=False)
    monkeypatch.undo()
    assert m.센다(db, r) == 전, "되돌리지 않았다"


@pytest.mark.parametrize("깨는칸, 말", [("라이브러리", "라이브러리 수가 계획과"),
                                     ("다른 회차 run", "다른 회차의 run 이 바뀌었습니다")])
def test57_e04_나머지_가드_둘도_실제로_되돌린다(db, tmp_path, monkeypatch, 깨는칸, 말):
    """**가드마다 밟아 본다** — 다른 회차를 지키는 줄이 바로 이 가드다(11-3)."""
    m = _들이기()
    r = _회차(db)
    _옛run(db, r)
    전 = m.센다(db, r)
    진짜 = m.센다
    처음 = {"쨌": True}

    def 두번째부터깬다(db_, rt):
        답 = 진짜(db_, rt)
        if 처음["쨌"]:                       # 넣기 전에 센 것은 그대로 둔다 — 깨는 것은 다시 센 쪽이다
            처음["쨌"] = False
            return 답
        return dict(답, **{깨는칸: 답[깨는칸] + 1})

    monkeypatch.setattr(m, "센다", 두번째부터깬다)
    with pytest.raises(m.멈춤, match=말):
        m.돌린다(db, r.id, 실행=True, 파일=_파일(tmp_path), 사본=False)
    monkeypatch.undo()
    assert m.센다(db, r) == 전, "되돌리지 않았다"
