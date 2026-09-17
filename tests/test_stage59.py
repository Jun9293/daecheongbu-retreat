"""테스트 시드 삭제 (2026-09-17 · 0장 예외 · `scripts/테스트시드삭제.py`) 와 seed.py 의 운영 경로 막기.

값은 전부 지어낸 것이다 — 운영 DB 는 열지 않는다. id 를 일부러 정해 넣어 스크립트의 `대상` 꼴을 흉내 낸다.
**고장을 심어 잰다** — 다시 세기 · 직전 재확인 · 시드 흔적 검사가 실제로 멈추는지 각각 깨뜨려 본다.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import re
import sys

import pytest
from sqlalchemy import func, select

from app import models

ROOT = pathlib.Path(__file__).resolve().parent.parent
시드때 = dt.datetime(2026, 8, 29, 14, 0, 37)


def _삭제():
    이름 = "테스트시드삭제_시험"
    spec = importlib.util.spec_from_file_location(이름, ROOT / "scripts" / "테스트시드삭제.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[이름] = mod
    spec.loader.exec_module(mod)
    return mod


def _lib(db, id_, *, parent=None, related=(), prereq=(), notion=None, origin="history", when=시드때, kind="main"):
    lib = models.TaskLibrary(id=id_, title=f"지어낸 업무 {id_}", kind=kind, parent_library_id=parent,
                             related_library_ids=list(related), prerequisite_library_ids=list(prereq),
                             notion_page_id=notion, origin=origin, created_at=when)
    db.add(lib)
    return lib


def _자리(db):
    """회차 둘 · 대상 여섯(501~506) · 남길 것 셋(노션 · 마법사 · 보통 시드)."""
    r1 = models.Retreat(name="지난 회차", start_date=dt.date(2026, 8, 21), end_date=dt.date(2026, 8, 23))
    r2 = models.Retreat(name="다음 회차", start_date=dt.date(2027, 8, 20), end_date=dt.date(2027, 8, 22))
    db.add_all([r1, r2])
    db.flush()
    _lib(db, 501)                               # 걸린 것 없음 → 지운다
    _lib(db, 502, parent=501, kind="sub")       # 대상의 하위 · 대상 → 지운다
    _lib(db, 503)                               # 논의가 걸림 → 뺀다
    _lib(db, 504)                               # 남는 라이브러리(601)의 상위 → 뺀다
    _lib(db, 505)                               # 뺀 503 이 관련업무로 가리킴 → 뺀다(되풀이)
    _lib(db, 506)                               # 남는 run 이 선행으로 가리킴 → 뺀다
    db.get(models.TaskLibrary, 503).related_library_ids = [505]
    _lib(db, 601, parent=504, kind="sub")       # 보통 시드(대상 아님)
    _lib(db, 602, notion="n" * 32, when=dt.datetime(2026, 9, 16))
    _lib(db, 603, origin="claude_suggestion", when=dt.datetime(2026, 8, 30))
    db.flush()
    runs = {}
    no = 1
    for lib in (501, 502, 503, 504, 505, 506, 601, 602, 603):
        for r in (r1, r2):
            if lib == 602 and r is r2 or lib == 603 and r is r1:
                continue
            run = models.TaskRun(library_id=lib, retreat_id=r.id, included=(r is r2), run_no=no)
            no += 1
            db.add(run)
            db.flush()
            runs[(lib, r.id)] = run
    runs[(601, r2.id)].blocked_by_run_ids = [runs[(506, r2.id)].id]
    entry = models.DiscussionEntry(_legacy_run_id=runs[(503, r1.id)].id, body="지어낸 논의")
    db.add(entry)
    db.commit()
    return r1, r2, runs


대상 = (501, 502, 503, 504, 505, 506)


def _수(db, 표):
    return db.scalar(select(func.count()).select_from(표))


def test59_a01_걸린_것이_있으면_빼고_되풀이한다(db):
    m = _삭제()
    _자리(db)
    판 = m.고른다(db, 대상)
    assert 판.지울lib == [501, 502]
    assert set(판.뺀것) == {503, 504, 505, 506}
    assert 판.뺀것[503] == ["논의"]
    assert 판.뺀것[504] == ["남는 라이브러리의 상위"]
    assert 판.뺀것[505] == ["남는 라이브러리의 관련업무"], "뺀 것이 가리키는 대상을 되풀이로 못 뺐다"
    assert 판.뺀것[506] == ["남는 run 의 선행 링크"]
    assert len(판.run들) == 4                          # 두 회차 × 둘
    # 막히면 안 되는 쪽 — 대상끼리의 상위(502 → 501)는 걸림이 아니다
    assert 501 not in 판.뺀것


def test59_a02_미리보기는_아무것도_안_바꾸고_목록만_저장소_밖에_쓴다(db, tmp_path, capsys):
    m = _삭제()
    _자리(db)
    전 = (_수(db, models.TaskLibrary), _수(db, models.TaskRun))
    목록 = tmp_path / "테스트시드삭제.real.md"
    m.돌린다(db, 실행=False, 목록=목록, 대상ids=대상)
    assert (_수(db, models.TaskLibrary), _수(db, models.TaskRun)) == 전
    출력 = capsys.readouterr().out
    assert "지울 것: 라이브러리 2 · run 4" in 출력
    assert "지어낸 업무" not in 출력, "출력에 제목이 샜다 — id 와 수만 찍는다"
    assert "지어낸 업무 501" in 목록.read_text(encoding="utf-8")


def test59_a03_실행하면_정확히_그만큼_지우고_나머지는_그대로다(db, tmp_path):
    m = _삭제()
    r1, r2, runs = _자리(db)
    남길run = sorted(r.id for (lib, _), r in runs.items() if lib not in (501, 502))
    m.돌린다(db, 실행=True, 기대=[501, 502], 사본=False, 목록=tmp_path / "x.real.md", 대상ids=대상)
    db.expire_all()
    assert _수(db, models.TaskLibrary) == 9 - 2
    assert sorted(db.scalars(select(models.TaskRun.id))) == 남길run
    assert db.get(models.TaskLibrary, 602) and db.get(models.TaskLibrary, 603)      # 노션 · 마법사
    assert db.get(models.TaskLibrary, 601).parent_library_id == 504
    기록 = db.scalars(select(models.ActivityLog).where(models.ActivityLog.action == "테스트시드_삭제")).all()
    assert len(기록) == 1 and 기록[0].actor_type == "system"
    assert 기록[0].after_value["라이브러리"] == [501, 502]
    # 두 번째는 할 것이 없다
    판 = m.돌린다(db, 실행=True, 기대=[501, 502], 사본=False, 목록=tmp_path / "x.real.md", 대상ids=대상)
    assert 판.지울lib == [] and 판.없는것 == [501, 502]


def test59_a04_시드_흔적과_안_맞으면_아무것도_안_한다(db, tmp_path):
    m = _삭제()
    _자리(db)
    for 대상하나 in (602, 603):             # 노션 줄 · 마법사 제안을 대상으로 잘못 적은 경우
        with pytest.raises(m.멈춤, match="시드였다는 흔적"):
            m.돌린다(db, 실행=True, 기대=[501, 502], 사본=False, 목록=tmp_path / "x.real.md", 대상ids=대상 + (대상하나,))
    늦게 = _lib(db, 507, when=dt.datetime(2026, 8, 29, 14, 0, 38))     # 그 초를 벗어난 줄
    db.commit()
    with pytest.raises(m.멈춤, match="시드였다는 흔적"):
        m.고른다(db, (507,))
    assert _수(db, models.TaskLibrary) == 10 and 늦게.id == 507


def test59_a05_지운_뒤_다시_센_수가_다르면_되돌린다(db, tmp_path, monkeypatch):
    """고장을 심는다 — 지우는 김에 노션 줄까지 지우면 다시 세기가 잡아야 한다."""
    m = _삭제()
    _자리(db)
    진짜 = m.지운다

    def 더지운다(db_, 판):
        진짜(db_, 판)
        db_.execute(m.text("delete from task_runs where library_id = 602"))
        db_.execute(m.text("delete from task_library where id = 602"))

    monkeypatch.setattr(m, "지운다", 더지운다)
    with pytest.raises(m.멈춤, match="되돌렸습니다"):
        m.돌린다(db, 실행=True, 기대=[501, 502], 사본=False, 목록=tmp_path / "x.real.md", 대상ids=대상)
    db.expire_all()
    assert _수(db, models.TaskLibrary) == 9 and db.get(models.TaskLibrary, 501)


def test59_a06_지우기_직전에_다시_센_목록이_다르면_멈춘다(db, tmp_path, monkeypatch):
    m = _삭제()
    _자리(db)
    진짜 = m.고른다
    불린 = []

    def 두번째는_다르다(db_, ids):
        판 = 진짜(db_, ids)
        불린.append(1)
        if len(불린) == 2:
            판.지울lib = 판.지울lib[:1]
        return 판

    monkeypatch.setattr(m, "고른다", 두번째는_다르다)
    with pytest.raises(m.멈춤, match="미리보기와 다릅니다"):
        m.돌린다(db, 실행=True, 기대=[501, 502], 사본=False, 목록=tmp_path / "x.real.md", 대상ids=대상)
    db.expire_all()
    assert _수(db, models.TaskLibrary) == 9


def test59_a07_사본은_지울_것이_있을_때만_지우기_전에_뜬다(db, tmp_path, monkeypatch):
    m = _삭제()
    _자리(db)
    순서 = []
    monkeypatch.setattr(m, "사본을_뜬다", lambda: 순서.append("사본"))
    진짜 = m.지운다
    monkeypatch.setattr(m, "지운다", lambda d, p: (순서.append("지움"), 진짜(d, p)))
    m.돌린다(db, 실행=True, 기대=[501, 502], 목록=tmp_path / "x.real.md", 대상ids=대상)
    assert 순서 == ["사본", "지움"]
    순서.clear()
    m.돌린다(db, 실행=True, 기대=[501, 502], 목록=tmp_path / "x.real.md", 대상ids=대상)
    assert 순서 == [], "지울 것이 없는데 사본을 떴다"


def test59_a08_빈_목록은_아무_줄도_안_가리킨다(db):
    m = _삭제()
    _자리(db)
    assert m._in([]) == "-1"
    수 = m.센다(db, [], [])
    assert 수["남길 라이브러리 지문"][0] == 9, "빈 목록이 `not in (NULL)` 이 되어 남길 줄을 0 으로 셌다"
    assert 수["대상 라이브러리 남음"] == 0


def test59_a10_사람이_본_목록과_다르거나_없으면_안_지운다(db, tmp_path):
    m = _삭제()
    _자리(db)
    with pytest.raises(m.멈춤, match="--기대"):
        m.돌린다(db, 실행=True, 사본=False, 목록=tmp_path / "x.real.md", 대상ids=대상)
    # 그사이 걸림이 풀려 승인 안 된 줄이 끼는 경우 — 503 의 논의와 관련업무를 걷는다
    db.execute(m.text("delete from discussion_entries"))
    db.execute(m.text("update task_library set related_library_ids = '[]' where id = 503"))
    db.commit()
    with pytest.raises(m.멈춤, match="사람이 본 미리보기와 다릅니다"):
        m.돌린다(db, 실행=True, 기대=[501, 502], 사본=False, 목록=tmp_path / "x.real.md", 대상ids=대상)
    assert _수(db, models.TaskLibrary) == 9


def test59_a11_라이브러리_기록과_규칙과_run_활동_기록도_걸림이다(db):
    """글자 값으로 견주는 줄은 틀려도 0 이 나온다 — 심어서 잰다(11-3)."""
    m = _삭제()
    r1, r2, runs = _자리(db)
    db.add(models.ActivityLog(action="제목_변경", target_type="task_library", target_id=501))
    db.add(models.ActivityLog(action="업무_날짜_변경", target_type="task_run", target_id=runs[(502, r1.id)].id))
    db.commit()
    판 = m.고른다(db, 대상)
    assert 판.뺀것[501] == ["라이브러리 활동 기록"]
    assert 판.뺀것[502] == ["활동 기록"]
    db.execute(m.text("delete from activity_logs"))
    db.get(models.TaskLibrary, 501).rules = "이렇게 한다"
    db.commit()
    판 = m.고른다(db, 대상)
    assert 판.뺀것[501] == ["업무 규칙"]
    assert 502 in 판.지울lib, "대상끼리의 상위는 걸림이 아니다"


def test59_a09_스크립트에는_id_만_있고_제목이_없다():
    m = _삭제()
    assert set(m.확정) <= set(m.대상) and set(m.출처불명) <= set(m.대상)
    import seed_library_data as L
    글 = (ROOT / "scripts" / "테스트시드삭제.py").read_text(encoding="utf-8")
    제목들 = [t for t, *_ in L.LIBRARY]
    assert len(제목들) > 50, "견줄 제목이 없다 — 아무것도 안 보는 검사다"
    assert [t for t in 제목들 if t in 글] == []


# ── seed.py 의 운영 경로 막기 ──────────────────────────────────────────

def test59_b01_운영_폴더를_가리키면_참이다(tmp_path):
    import seed
    운영 = ROOT / "data"
    assert seed.운영경로인가(운영, f"sqlite:///{tmp_path / 'app.db'}")
    assert seed.운영경로인가(tmp_path, f"sqlite:///{운영 / 'app.db'}"), "DB 주소만 운영이면 놓친다"
    # 막히면 안 되는 쪽 — 개발 폴더
    assert not seed.운영경로인가(tmp_path, f"sqlite:///{tmp_path / 'app.db'}")


def test59_b02_시험_환경은_운영이_아니고_막는_자리는_지우기_전이다():
    import seed
    assert not seed.운영경로인가(), "시험이 운영 폴더를 가리킨다"
    # 파이썬 주석만 걷는다 — 막는 줄이 주석 안에만 있으면 잡혀야 한다
    본문 = "\n".join(re.sub(r"#.*$", "", 줄) for 줄 in (ROOT / "seed.py").read_text(encoding="utf-8").splitlines())
    main = 본문[본문.index('if __name__ == "__main__":'):]
    assert main.index("_운영이면_멈춘다()") < main.index("--reset"), "파일을 지운 뒤에 막는다"
    함수 = 본문[본문.index("def seed("):]
    assert 함수.index("_운영이면_멈춘다()") < 함수.index("init_db()")


def test59_b03_막는_함수가_운영이면_끝낸다(monkeypatch, capsys):
    import seed
    monkeypatch.setattr(seed, "운영경로인가", lambda *a, **k: True)
    with pytest.raises(SystemExit) as e:
        seed._운영이면_멈춘다()
    assert e.value.code == 1 and "아무것도 안 했습니다" in capsys.readouterr().out
    monkeypatch.setattr(seed, "운영경로인가", lambda *a, **k: False)
    seed._운영이면_멈춘다()


def test59_c01_목업_예시_규칙과_0장_예외가_기준_문서에_있다():
    글 = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    영 = 글[글.index("## 0. 목적과 판단 기준"):글.index("## 1. 확정된 결정사항")]
    assert "scripts/테스트시드삭제.py" in 영 and "d18a0c1" in 영
    육구 = 글[글.index("### 6-9. 첫 세팅"):글.index("### 6-10.")]
    assert re.search(r"목업.*시드", 육구)


def test59_c02_시드에_목업_예시_목록이_없고_시드_업무는_모두_실행_기록이_된다(db):
    """6-9 — 목업 예시를 시드에 안 넣는다. 걷은 목록이 되살아나면 빨개진다."""
    import seed_library
    import seed_library_data as L
    assert not hasattr(L, "LIBRARY_ONLY")
    본문 = (ROOT / "seed_library.py").read_text(encoding="utf-8")
    assert "LIBRARY_ONLY" not in 본문
    r = models.Retreat(name="시드 회차", start_date=dt.date(2026, 8, 21), end_date=dt.date(2026, 8, 23))
    db.add(r)
    db.flush()
    for i, (key, name, color) in enumerate(L.DEPARTMENTS):
        db.add(models.Department(retreat_id=r.id, key=key, name=name, color_tag=color, sort_order=i))
    db.flush()
    seed_library.seed_all(db, r)
    assert _수(db, models.TaskLibrary) == len(L.LIBRARY) > 50
    뺀 = db.scalar(select(func.count()).select_from(models.TaskRun).where(models.TaskRun.included.is_(False)))
    assert 뺀 == 0, "시드가 「그 회차 미실행」 줄을 다시 세운다"
