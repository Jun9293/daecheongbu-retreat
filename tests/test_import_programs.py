"""프로그램표 가져오기 (CLAUDE.md 5-5 · 5-6). 수용 기준 1~6.

**실제 JSON 파일이 아니라 작은 임시 파일로 시험합니다.** 진짜 파일에 기대면
그 파일이 바뀔 때마다 테스트가 흔들리고, 무엇을 지키려던 것인지 잊힙니다.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from sqlalchemy import select

from app import models
from app.domain import live as live_domain
from scripts import import_programs
from tests.conftest import app_session

OPEN = dt.date(2026, 8, 21)
CLOSE = dt.date(2026, 8, 23)


def write(tmp_path, days, name="파일.json"):
    path = tmp_path / name
    path.write_text(
        json.dumps({"retreat": "아무개", "source": "시트", "days": days},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return path


def item(text, *, phase="pre", part="행정", who="하람"):
    return {"phase": phase, "part": part, "assignee": who, "text": text}


def program(time, name, items, **kw):
    return {"start_time": time, "name": name, "host": kw.get("host"),
            "place": kw.get("place"), "note": kw.get("note"), "items": items}


SAMPLE = {
    "선발대": [
        program("09:30", "본당집합", [item("총무팀 들어오는 시간 확인")], host="총무팀"),
        program("10:00", "짐정리", [
            item("비품리스트 확인", part="비품", who="전체"),
            item("박스 번호 작성", phase="mid", part="비품", who="전체"),
        ], place="본당"),
    ],
    "1일차": [
        program("08:00", "아침식사", [item("식수계수", part="음식", who="준서")]),
    ],
    "2일차": [
        program("10:00", "GBS", [
            item("나눔지 배부"),
            item("인원계수", phase="mid", part="비품", who="온"),
            item("나눔지 회수", phase="post", part="비품", who="서윤"),
        ], host="하윤M"),
    ],
    "폐회": [
        program("11:00", "파송예배", [item("영수증 취합", phase="post", part="재정", who="준서")]),
    ],
}


@pytest.fixture
def retreat(client):
    """회차 하나. `client` 로 DB 를 비우고 시작한다."""
    with app_session() as db:
        made = models.Retreat(
            name="2026 여름수련회", start_date=OPEN, end_date=CLOSE)
        db.add(made)
        db.commit()
        return made.id


def load(db, retreat_id):
    return live_domain.load_programs(db, db.get(models.Retreat, retreat_id))


# ---------------------------------------------------------------- 1. 넣기


def test_01_프로그램과_항목이_회차에_들어간다(tmp_path, retreat):
    path = write(tmp_path, SAMPLE)

    with app_session() as db:
        result = import_programs.run(db, path=path, retreat_name="2026 여름수련회")

    assert result["programs"] == 5
    assert result["items"] == 8
    assert result["removed"] == 0

    with app_session() as db:
        programs = load(db, retreat)
        assert len(programs) == 5
        assert sum(len(p.items) for p in programs) == 8
        # 파일 순서대로 sort_order 가 붙는다
        assert [p.sort_order for p in sorted(programs, key=lambda x: x.id)] == [0, 1, 2, 3, 4]
        # 프로그램의 속성이 그대로 들어간다
        first = next(p for p in programs if p.name == "본당집합")
        assert (first.day, first.start_time, first.host) == ("선발대", "09:30", "총무팀")
        assert first.place is None and first.note is None
        # 항목의 순서도 파일 순서다
        gbs = next(p for p in programs if p.name == "GBS")
        assert [i.phase for i in gbs.items] == ["pre", "mid", "post"]
        assert [i.sort_order for i in gbs.items] == [0, 1, 2]
        assert gbs.items[1].part_key == "비품"
        assert gbs.items[1].assignee_name == "온"


def test_01b_일자별_파트별_담당자를_세어_돌려준다(tmp_path, retreat):
    with app_session() as db:
        result = import_programs.run(
            db, path=write(tmp_path, SAMPLE), retreat_name="2026 여름수련회")

    # 범위(5-2)가 생기면서 팀·개인 건수가 함께 온다
    assert result["by_day"] == {
        "선발대": {"programs": 2, "items": 3, "team": 2, "person": 1},
        "1일차": {"programs": 1, "items": 1, "team": 0, "person": 1},
        "2일차": {"programs": 1, "items": 3, "team": 0, "person": 3},
        "폐회": {"programs": 1, "items": 1, "team": 0, "person": 1},
    }
    assert result["parts"] == {"행정": 2, "비품": 4, "음식": 1, "재정": 1}
    assert result["people"]["전체"] == 2


def test_01c_비슷한_이름을_짚어_준다(tmp_path, retreat):
    """담당자는 계정과 잇지 않으므로 오타가 그대로 남는다. 고치지는 않는다."""
    days = {"1일차": [program("09:00", "예배", [
        item("A", who="민준"), item("B", who="민준M"),
        item("C", who="서윤"), item("D", who="서윤·나윤"),
    ])]}
    with app_session() as db:
        result = import_programs.run(
            db, path=write(tmp_path, days), retreat_name="2026 여름수련회")

    pairs = " / ".join(f"{a} vs {b}" for a, b in result["similar"])
    assert "민준" in pairs and "민준M" in pairs
    # 여러 명을 한 칸에 적은 것(서윤·나윤)은 짝으로 치지 않는다
    assert "서윤 vs 서윤·나윤" not in pairs
    # 이름은 적힌 그대로 저장된다
    with app_session() as db:
        names = {i.assignee_name for p in load(db, retreat) for i in p.items}
    assert names == {"민준", "민준M", "서윤", "서윤·나윤"}


# ---------------------------------------------------------------- 2. 일자·날짜


def test_02_일자_4개가_잡히고_날짜가_계산된다(tmp_path, retreat):
    with app_session() as db:
        import_programs.run(db, path=write(tmp_path, SAMPLE), retreat_name="2026 여름수련회")

    with app_session() as db:
        made = db.get(models.Retreat, retreat)
        programs = load(db, retreat)
        assert {p.day for p in programs} == {"선발대", "1일차", "2일차", "폐회"}

        # 날짜는 저장하지 않고 개회일에서 계산한다 (5-1)
        dates = live_domain.day_dates(made)
        assert dates["선발대"] == dt.date(2026, 8, 20)
        assert dates["1일차"] == dt.date(2026, 8, 21)
        assert dates["2일차"] == dt.date(2026, 8, 22)
        assert dates["폐회"] == dt.date(2026, 8, 23)

        view = live_domain.build(db, made, now=dt.datetime(2026, 8, 22, 9, 0))
        assert [d["name"] for d in view["days"]] == ["선발대", "1일차", "2일차", "폐회"]
        assert [d["label"] for d in view["days"]] == [
            "8/20(목)", "8/21(금)", "8/22(토)", "8/23(일)"]


def test_02b_모르는_일자는_멈춘다(tmp_path, retreat):
    days = {"둘째날": [program("09:00", "예배", [item("A")])]}
    with app_session() as db:
        with pytest.raises(import_programs.ImportError_) as caught:
            import_programs.run(db, path=write(tmp_path, days), retreat_name="2026 여름수련회")
    assert "둘째날" in str(caught.value)
    assert "선발대" in str(caught.value)


# ---------------------------------------------------------------- 3. 덮어쓰기


def test_03_두_번_돌려도_replace_없이는_덮어쓰지_않는다(tmp_path, retreat):
    """실수로 한 번 더 돌려서 날아가면 되돌릴 방법이 없다."""
    path = write(tmp_path, SAMPLE)
    with app_session() as db:
        import_programs.run(db, path=path, retreat_name="2026 여름수련회")

    with app_session() as db:
        with pytest.raises(import_programs.ImportError_) as caught:
            import_programs.run(db, path=path, retreat_name="2026 여름수련회")

    message = str(caught.value)
    assert "이미 프로그램 5개 · 항목 8건이 있습니다" in message
    assert "--replace" in message

    # 막혔으니 그대로 남아 있다
    with app_session() as db:
        assert len(load(db, retreat)) == 5

    # --replace 를 주면 지우고 다시 넣는다
    with app_session() as db:
        again = import_programs.run(
            db, path=path, retreat_name="2026 여름수련회", replace=True)
    assert again["removed"] == 5
    with app_session() as db:
        assert len(load(db, retreat)) == 5


def test_03b_체크된_것이_있으면_몇_건인지_함께_말한다(tmp_path, retreat):
    path = write(tmp_path, SAMPLE)
    with app_session() as db:
        import_programs.run(db, path=path, retreat_name="2026 여름수련회")
    with app_session() as db:
        first = db.scalars(select(models.ProgramItem)).first()
        first.done_at = dt.datetime(2026, 8, 22, 10, 0)
        db.commit()

    with app_session() as db:
        with pytest.raises(import_programs.ImportError_) as caught:
            import_programs.run(db, path=path, retreat_name="2026 여름수련회")
    assert "1건은 체크된 것입니다" in str(caught.value)


def test_03c_없는_회차면_이유를_말하고_멈춘다(tmp_path, retreat):
    """비슷한 이름을 골라 넣지 않는다 — 엉뚱한 회차에 넣고 나면 알 수 없다."""
    with app_session() as db:
        with pytest.raises(import_programs.ImportError_) as caught:
            import_programs.run(
                db, path=write(tmp_path, SAMPLE), retreat_name="2026 여름 수련회")
    message = str(caught.value)
    assert "'2026 여름 수련회' 이라는 회차가 없습니다" in message
    assert "2026 여름수련회" in message          # 있는 회차를 알려준다

    with app_session() as db:
        assert load(db, retreat) == []            # 아무것도 넣지 않았다


# ---------------------------------------------------------------- 4. 모르는 파트


def test_04_모르는_파트가_있으면_멈추고_어느_줄인지_말한다(tmp_path, retreat):
    days = {
        "1일차": [
            program("09:00", "예배", [item("정상 항목")]),
            program("10:00", "식사", [item("이상한 항목", part="홍보팀")]),
        ]
    }
    path = write(tmp_path, days)
    with app_session() as db:
        with pytest.raises(import_programs.ImportError_) as caught:
            import_programs.run(db, path=path, retreat_name="2026 여름수련회")

    message = str(caught.value)
    assert "모르는 파트입니다: '홍보팀'" in message
    assert "1일차 2번째 '식사' → 1번째 항목" in message
    assert "이상한 항목" in message
    assert "번째 줄" in message                   # 파일에서 찾을 수 있게
    assert "행정" in message                       # 쓸 수 있는 파트를 알려준다

    # **하나라도 이상하면 아무것도 넣지 않는다** — 절반만 들어간 표가 더 나쁘다
    with app_session() as db:
        assert load(db, retreat) == []


def test_04b_모르는_구간과_이상한_시각도_멈춘다(tmp_path, retreat):
    with app_session() as db:
        with pytest.raises(import_programs.ImportError_) as caught:
            import_programs.run(db, path=write(
                tmp_path, {"1일차": [program("09:00", "예배", [item("A", phase="during")])]},
                name="a.json"), retreat_name="2026 여름수련회")
        assert "모르는 구간입니다: 'during'" in str(caught.value)

        with pytest.raises(import_programs.ImportError_) as caught:
            import_programs.run(db, path=write(
                tmp_path, {"1일차": [program("아침", "예배", [item("A")])]},
                name="b.json"), retreat_name="2026 여름수련회")
        assert "09:30 처럼" in str(caught.value)

    with app_session() as db:
        assert load(db, retreat) == []


def test_04c_줄_번호는_찾을_수_있을_때만_붙인다():
    raw = '{\n "days": {\n  "1일차": [\n   {"text": "찾을 문장"}\n  ]\n }\n}'
    assert import_programs.line_of(raw, "찾을 문장") == 4
    assert import_programs.line_of(raw, "없는 문장") is None


# ══════════════════════════════════════════════════════════════════════
# 범위 — 팀 단위 / 개인 단위 (5-2). 수용 기준 3·4·5
# ══════════════════════════════════════════════════════════════════════


def test_s03_scope_가_적힌_파일은_적힌_대로_들어간다(tmp_path, retreat):
    days = {"1일차": [program("18:00", "저녁집회", [
        {"phase": "pre", "part": "헤브론", "assignee": "헤브론",
         "text": "코람데오 리허설 시작", "scope": "team"},
        {"phase": "pre", "part": "현장관리", "assignee": "전체",
         "text": "강당 의자 세팅", "scope": "team"},
        {"phase": "pre", "part": "현장관리", "assignee": "나윤",
         "text": "진행자 물 세팅", "scope": "person"},
        {"phase": "mid", "part": "비품", "assignee": "온",
         "text": "인원계수", "scope": "person"},
    ])]}
    with app_session() as db:
        result = import_programs.run(
            db, path=write(tmp_path, days), retreat_name="2026 여름수련회")

    assert result["scopes"] == {"team": 2, "person": 2}
    assert result["guessed_scopes"] == 0          # 전부 파일에 적혀 있었다
    assert result["by_day"]["1일차"] == {
        "programs": 1, "items": 4, "team": 2, "person": 2}

    with app_session() as db:
        items = {i.text: i.scope for p in load(db, retreat) for i in p.items}
    assert items["코람데오 리허설 시작"] == "team"
    assert items["진행자 물 세팅"] == "person"


def test_s04_scope_가_없는_옛_파일은_기준대로_계산되고_전부_person_이_되지_않는다(tmp_path, retreat):
    """scope 가 없던 시절의 파일도 그대로 들어가야 하는데, 전부 개인으로
    몰리면 봉사자 열이 통째로 개인 일이 된다."""
    days = {"1일차": [program("18:00", "저녁집회", [
        item("코람데오 리허설 시작", part="코람데오", who="코람데오"),   # 봉사팀 파트 → 팀
        item("강당 의자 세팅", part="현장관리", who="전체"),            # 묶음 이름 → 팀
        item("비품 정리", part="비품", who=None),                      # 담당 없음 → 팀
        item("진행자 물 세팅", part="현장관리", who="나윤"),            # 개인 이름 → 개인
        item("인원계수", part="비품", who="온"),                        # 개인 이름 → 개인
    ])]}
    # 파일에 scope 키가 아예 없다
    raw = json.loads(write(tmp_path, days).read_text(encoding="utf-8"))
    assert all("scope" not in i
               for p in raw["days"]["1일차"] for i in p["items"])

    with app_session() as db:
        result = import_programs.run(
            db, path=write(tmp_path, days), retreat_name="2026 여름수련회")

    assert result["scopes"] == {"team": 3, "person": 2}
    assert result["scopes"]["team"] > 0, "전부 개인으로 몰렸다"
    assert result["guessed_scopes"] == 5          # 다섯 건 다 추측한 것이다

    with app_session() as db:
        items = {i.text: i.scope for p in load(db, retreat) for i in p.items}
    assert items["코람데오 리허설 시작"] == "team"
    assert items["비품 정리"] == "team"
    assert items["인원계수"] == "person"


def test_s05_team_person_이_아닌_값은_멈추고_어느_줄인지_말한다(tmp_path, retreat):
    days = {"1일차": [
        program("09:00", "예배", [item("정상 항목")]),
        program("18:00", "저녁집회", [
            {"phase": "pre", "part": "현장관리", "assignee": "나윤",
             "text": "이상한 범위 항목", "scope": "그룹"},
        ]),
    ]}
    with app_session() as db:
        with pytest.raises(import_programs.ImportError_) as caught:
            import_programs.run(
                db, path=write(tmp_path, days), retreat_name="2026 여름수련회")

    message = str(caught.value)
    assert "모르는 범위입니다: '그룹'" in message
    assert "1일차 2번째 '저녁집회' → 1번째 항목" in message
    assert "이상한 범위 항목" in message
    assert "번째 줄" in message
    assert "team(팀 단위)" in message and "person(개인 단위)" in message

    # 하나라도 이상하면 아무것도 넣지 않는다
    with app_session() as db:
        assert load(db, retreat) == []


def test_s05b_빈_문자열은_거부가_아니라_추측이다(tmp_path, retreat):
    """적지 않은 것과 잘못 적은 것은 다르다."""
    days = {"1일차": [program("09:00", "예배", [
        {"phase": "pre", "part": "헤브론", "assignee": "건우",
         "text": "음향 확인", "scope": ""},
    ])]}
    with app_session() as db:
        result = import_programs.run(
            db, path=write(tmp_path, days), retreat_name="2026 여름수련회")
    assert result["scopes"]["team"] == 1
    assert result["guessed_scopes"] == 1


def test_s05c_추측한_건수를_따로_알려준다(tmp_path, retreat):
    """추측이지 규칙이 아니므로 몇 건을 추측했는지 사람이 알아야 한다."""
    days = {"1일차": [program("09:00", "예배", [
        {"phase": "pre", "part": "행정", "assignee": "하람",
         "text": "적혀 있는 것", "scope": "person"},
        item("추측한 것", part="행정", who="다은"),
    ])]}
    with app_session() as db:
        result = import_programs.run(
            db, path=write(tmp_path, days), retreat_name="2026 여름수련회")
    assert result["scopes"] == {"team": 0, "person": 2}
    assert result["guessed_scopes"] == 1          # 둘 중 하나만 추측


def test_s05d_넣은_뒤에_내부용_표시가_남지_않는다(tmp_path, retreat):
    """_inferred 는 세어서 알려주기 위한 것이라 컬럼이 아니다."""
    with app_session() as db:
        import_programs.run(db, path=write(tmp_path, SAMPLE), retreat_name="2026 여름수련회")
    with app_session() as db:
        items = [i for p in load(db, retreat) for i in p.items]
    assert items and all(not hasattr(i, "_inferred") for i in items)
    assert all(i.scope in ("team", "person") for i in items)


# ---------------------------------------------------------------- 5. 체크 없음


def test_05_체크_상태가_하나도_들어가지_않는다(tmp_path, retreat):
    """이 파일은 무엇을 했는지의 기록이 아니라 무엇을 하기로 했는지의 표다."""
    # 파일에 done 이 적혀 있어도 무시한다
    days = json.loads(json.dumps(SAMPLE, ensure_ascii=False))
    days["1일차"][0]["items"][0]["done"] = True
    days["1일차"][0]["items"][0]["done_at"] = "2026-08-21T08:30:00"

    with app_session() as db:
        import_programs.run(db, path=write(tmp_path, days), retreat_name="2026 여름수련회")

    with app_session() as db:
        items = [i for p in load(db, retreat) for i in p.items]
        assert len(items) == 8
        assert all(i.done_at is None for i in items)
        assert all(i.done_by_id is None for i in items)
        assert not any(i.done for i in items)


# ---------------------------------------------------------------- 6. 안내 문구


def test_06_종료된_회차_더하기_체크_0건이면_진행률_대신_안내가_나온다(tmp_path, retreat):
    """지난 회차에 프로그램표만 있으면 화면이 '아무것도 안 했다'로 읽힌다.
    실제로는 다 했는데 그때 이 시스템이 없었을 뿐이다."""
    with app_session() as db:
        import_programs.run(db, path=write(tmp_path, SAMPLE), retreat_name="2026 여름수련회")

    after = dt.datetime(2026, 9, 10, 14, 0)       # 회차가 끝난 뒤
    during = dt.datetime(2026, 8, 22, 14, 0)      # 회차 도중

    with app_session() as db:
        made = db.get(models.Retreat, retreat)
        assert live_domain.build(db, made, now=after)["carried_only"] is True
        # 아직 안 끝난 회차에는 붙지 않는다 — 그냥 아직 안 누른 것이다
        assert live_domain.build(db, made, now=during)["carried_only"] is False


def test_06b_체크가_하나라도_있으면_안내_대신_진행률이_나온다(tmp_path, retreat):
    with app_session() as db:
        import_programs.run(db, path=write(tmp_path, SAMPLE), retreat_name="2026 여름수련회")
    with app_session() as db:
        first = db.scalars(select(models.ProgramItem)).first()
        first.done_at = dt.datetime(2026, 8, 21, 9, 0)
        db.commit()

    after = dt.datetime(2026, 9, 10, 14, 0)
    with app_session() as db:
        made = db.get(models.Retreat, retreat)
        view = live_domain.build(db, made, now=after)
        assert view["carried_only"] is False
        # 체크는 회차 전체로 센다 — 그 날에 없어도 다른 날에 있으면 진행률이다
        assert view["day"] == "선발대"


def test_06c_프로그램이_없으면_안내도_없다(retreat):
    after = dt.datetime(2026, 9, 10, 14, 0)
    with app_session() as db:
        made = db.get(models.Retreat, retreat)
        assert live_domain.build(db, made, now=after)["carried_only"] is False


def test_06d_보관된_회차도_종료로_본다(tmp_path, retreat):
    with app_session() as db:
        import_programs.run(db, path=write(tmp_path, SAMPLE), retreat_name="2026 여름수련회")
    with app_session() as db:
        made = db.get(models.Retreat, retreat)
        made.is_archived = True
        db.commit()

    during = dt.datetime(2026, 8, 22, 14, 0)      # 아직 기간 안이지만 보관됨
    with app_session() as db:
        made = db.get(models.Retreat, retreat)
        assert live_domain.build(db, made, now=during)["carried_only"] is True


def test_06f_시스템_밖에서_진행한_회차에는_지연도_남은_정리도_붙지_않는다(tmp_path, retreat):
    """`지연` 과 `정리 N건 남음` 은 둘 다 "안 끝났다"는 말인데, 그 회차는 안 끝난 게
    아니라 **누른 적이 없는** 것이다. 위에 사정을 적어 놓고 아래를 빨갛게 덮으면
    한 화면이 서로를 부정한다 (4-10 에서 완료와 연쇄 경고를 함께 내지 않는 것과 같다)."""
    with app_session() as db:
        import_programs.run(db, path=write(tmp_path, SAMPLE), retreat_name="2026 여름수련회")

    after = dt.datetime(2026, 9, 10, 14, 0)
    with app_session() as db:
        made = db.get(models.Retreat, retreat)
        view = live_domain.build(db, made, now=after, day="2일차")
        assert view["carried_only"] is True
        assert all(p["late"] == 0 for p in view["programs"])
        assert all(p["leftover_post"] == 0 for p in view["programs"])

        # 판정 자체는 그대로다 — 가리는 것은 배지뿐이다
        assert all(p["state"] == "done" for p in view["programs"])

    # 체크가 하나라도 생기면 보통대로 돌아온다
    with app_session() as db:
        first = db.scalars(select(models.ProgramItem)).first()
        first.done_at = dt.datetime(2026, 8, 20, 9, 0)
        db.commit()
    with app_session() as db:
        made = db.get(models.Retreat, retreat)
        view = live_domain.build(db, made, now=after, day="2일차")
        assert view["carried_only"] is False
        assert any(p["late"] for p in view["programs"])


def test_06g_진행_중인_회차에서는_지연이_그대로_붙는다(tmp_path, retreat):
    """5-6 이 5-2 를 덮어쓰지 않게 한다 — 가리는 것은 끝난 회차뿐이다."""
    with app_session() as db:
        import_programs.run(db, path=write(tmp_path, SAMPLE), retreat_name="2026 여름수련회")

    during = dt.datetime(2026, 8, 22, 14, 0)      # 2일차 오후 — GBS(10:00) 는 진행 중
    with app_session() as db:
        made = db.get(models.Retreat, retreat)
        view = live_domain.build(db, made, now=during, day="2일차")
        assert view["carried_only"] is False
        gbs = next(p for p in view["programs"] if p["name"] == "GBS")
        assert gbs["state"] == "live"
        assert gbs["late"] == 1                    # 시작했는데 준비 1건이 안 끝났다

        # 선발대는 이미 지난 날이라 남은 정리가 잡힌다
        past = live_domain.build(db, made, now=during, day="선발대")
        assert any(p["leftover_post"] for p in past["programs"]) or all(
            not [i for i in p["items"] if i["phase"] == "post"] for p in past["programs"])


def test_06h_화면_쪽도_같은_회차에서는_배지를_그리지_않는다():
    js = open("app/static/js/live.js", encoding="utf-8").read()
    # 항목 배지 · 왼쪽 목록 · 상세 위쪽 안내 셋 다 같은 값을 본다
    assert "!LIVE.carried_only && phase === 'pre'" in js
    assert "LIVE.carried_only || !started" in js
    assert "p.leftover_post && !LIVE.carried_only" in js


def test_06e_화면이_0퍼센트_막대_대신_문구를_그린다():
    html = open("app/templates/live.html", encoding="utf-8").read()
    assert "live.carried_only" in html
    assert "시스템 밖에서 진행했습니다" in html
    # 안내가 뜨는 쪽에는 막대가 없다
    carried = html[html.index("live.carried_only"):html.index("{% else %}")]
    assert "class=\"bar\"" not in carried
    assert "progress.percent" not in carried
