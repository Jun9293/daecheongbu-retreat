"""담당자 표기 통일 (CLAUDE.md 5-3). 수용 기준 1~11.

`ProgramItem.assignee_name` 은 계정과 잇지 않은 이름 문자열이라(5장) 표기가
갈린다 — `민준` 과 `민준M` 이 같은 사람인데 둘 다 쓰인다.

**3번이 가장 중요하다.** `하람`·`나윤`·`온` 처럼 M 없이만 쓰는 사람에게 M 을
붙이면 사람 이름이 틀어진다. 짝이 있는 것만 맞춘다.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from scripts import import_programs, normalize_names
from tests.conftest import app_session, login_as

OPEN = dt.date(2026, 8, 21)
CLOSE = dt.date(2026, 8, 23)


@pytest.fixture
def data(client):
    """회차 둘. 앞의 것에만 갈린 표기를 넣는다 (8번 — 다른 회차는 안 건드린다)."""
    with app_session() as db:
        main = models.Retreat(
            name="2026 여름수련회 Belong", start_date=OPEN, end_date=CLOSE)
        other = models.Retreat(
            name="2027 겨울수련회",
            start_date=dt.date(2027, 1, 15), end_date=dt.date(2027, 1, 17))
        db.add_all([main, other])
        db.flush()

        def program(retreat, day, time, name, rows):
            p = models.Program(
                retreat_id=retreat.id, day=day, start_time=time, name=name,
                host="총무팀", sort_order=0)
            db.add(p)
            db.flush()
            for order, (part, who, text) in enumerate(rows):
                db.add(models.ProgramItem(
                    program_id=p.id, phase="pre", part_key=part,
                    assignee_name=who, text=text, sort_order=order, scope="person"))
            return p

        program(main, "1일차", "14:00", "Belong FM", [
            ("행정", "민준", "롤링배너 교체"),               # 짝 있음 → 바뀐다
            ("행정", "민준M", "카드키 배부 확인"),            # 이미 M
            ("행정", "하람", "선발대 인원 확인"),             # 짝 없음 → 그대로
            ("비품", "나윤", "물 세팅"),                     # 짝 없음 → 그대로
            ("비품", "온", "인원계수"),                      # 짝 없음 → 그대로
        ])
        program(main, "2일차", "11:30", "점심식사", [
            ("교역자", "하윤·예솔·소율", "외부강사 식사"),     # 여럿 — 둘이 바뀐다
            ("교역자", "하윤M", "강사 안내"),
            ("교역자", "예솔M", "차량 안내"),
            ("현장관리", "서윤·나윤", "다과 세팅"),            # 여럿 — 둘 다 짝 없음
            ("비품", "수영,미르/도현", "짐 정리"),             # 다른 구분자
            ("비품", "도현M", "침례짐"),
            ("행정", "전체", "의자 정렬"),                    # 묶음 이름
            ("행정", "담당M", "안내 방송"),                   # 사람 이름이 아닌 M
        ])
        # 다른 회차 — 같은 갈림이 있어도 --retreat 로 준 것만 바꾼다
        program(other, "1일차", "09:00", "겨울 집회", [
            ("행정", "민준", "겨울 롤링배너"),
            ("행정", "민준M", "겨울 카드키"),
        ])
        db.commit()
        return {"main_id": main.id, "other_id": other.id}


def names_of(db, retreat_id):
    programs = db.scalars(
        select(models.Program).where(models.Program.retreat_id == retreat_id))
    return sorted(i.assignee_name for p in programs for i in p.items)


def preview(db, name="2026 여름수련회 Belong"):
    return normalize_names.run(db, retreat_name=name)


# ---------------------------------------------------------------- 1. 미리보기


def test_01_apply_없이_돌리면_아무것도_바뀌지_않고_목록만_나온다(data):
    """이름을 잘못 바꾸면 누가 무엇을 맡았는지가 틀어진다. 기본은 미리보기다."""
    with app_session() as db:
        before = names_of(db, data["main_id"])
        result = preview(db)

    assert result["applied"] is False
    assert len(result["changes"]) == 3          # 항목 3개가 바뀔 예정
    # 하윤·예솔·소율 한 칸에서 둘이 함께 바뀌므로 이름 단위로는 4번이다
    assert result["mapping"] == {
        "하윤": "하윤M", "예솔": "예솔M", "도현": "도현M", "민준": "민준M"}

    with app_session() as db:
        assert names_of(db, data["main_id"]) == before
        assert db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "담당자_표기_통일")).all() == []


# ---------------------------------------------------------------- 2. 통일


def test_02_M_쪽으로_통일된다(data):
    with app_session() as db:
        result = normalize_names.run(
            db, retreat_name="2026 여름수련회 Belong", apply=True)
    assert result["applied"] is True

    with app_session() as db:
        names = names_of(db, data["main_id"])
    # 홑이름이 M 으로
    assert "민준M" in names and "민준" not in names
    # 여럿 든 칸 안에서도
    assert "하윤M·예솔M·소율" in names
    assert "수영,미르/도현M" in names


# ---------------------------------------------------------------- 3. 짝 없는 이름


def test_03_M_짝이_없는_이름은_그대로_남는다(data):
    """**없는 짝에 M 을 붙이면 사람 이름이 틀어진다.**"""
    with app_session() as db:
        normalize_names.run(db, retreat_name="2026 여름수련회 Belong", apply=True)

    with app_session() as db:
        names = names_of(db, data["main_id"])

    for kept in ("하람", "나윤", "온", "서윤·나윤", "전체", "담당M"):
        assert kept in names, f"{kept} 이(가) 바뀌었다"
    for never in ("하람M", "나윤M", "온M", "전체M", "소율M", "서윤M"):
        assert not any(never in n for n in names), f"{never} 이(가) 생겼다"


def test_03b_짝_찾기가_M_있는_것만_고른다(data):
    with app_session() as db:
        mapping = preview(db)["mapping"]

    assert set(mapping) == {"하윤", "예솔", "도현", "민준"}
    for absent in ("하람", "나윤", "온", "서윤", "소율", "미르", "수영", "전체"):
        assert absent not in mapping


# ---------------------------------------------------------------- 4. 여럿 든 칸


def test_04_여럿이_든_칸에서도_각_이름이_따로_바뀐다(data):
    """통째로 비교하면 `서윤·나윤` 안의 이름은 못 고친다."""
    with app_session() as db:
        result = preview(db)
        changed = {c["before"]: c["after"] for c in result["changes"]}

    # 한 칸에서 둘이 함께 바뀐다
    assert changed["하윤·예솔·소율"] == "하윤M·예솔M·소율"
    # 셋 중 하나만
    assert changed["수영,미르/도현"] == "수영,미르/도현M"
    # 아무도 안 바뀌는 칸은 목록에 없다
    assert "서윤·나윤" not in changed


def test_04b_구분자로_쪼갠_뒤_다시_합친다():
    mapping = {"민준": "민준M", "하윤": "하윤M"}
    assert normalize_names.rewrite("민준", mapping) == "민준M"
    assert normalize_names.rewrite("민준·하람", mapping) == "민준M·하람"
    assert normalize_names.rewrite("하람·민준", mapping) == "하람·민준M"
    assert normalize_names.rewrite("하윤·민준", mapping) == "하윤M·민준M"
    # 바꿀 것이 없으면 None — 아무 관계 없는 줄을 건드리지 않는다
    assert normalize_names.rewrite("하람·나윤", mapping) is None
    assert normalize_names.rewrite("", mapping) is None


# ---------------------------------------------------------------- 5. 구분자


def test_05_구분자가_원래_쓰던_것으로_유지된다(data):
    with app_session() as db:
        changed = {c["before"]: c["after"] for c in preview(db)["changes"]}

    assert changed["수영,미르/도현"] == "수영,미르/도현M"      # 쉼표와 빗금 그대로
    assert changed["하윤·예솔·소율"] == "하윤M·예솔M·소율"     # 가운뎃점 그대로

    mapping = {"민준": "민준M"}
    assert normalize_names.rewrite("하람,민준", mapping) == "하람,민준M"
    assert normalize_names.rewrite("하람/민준", mapping) == "하람/민준M"
    # 앞뒤 공백은 정리하되 구분자는 그대로
    assert normalize_names.rewrite("하람 · 민준", mapping) == "하람·민준M"


# ---------------------------------------------------------------- 6. 자료에서


def test_06_짝을_코드에_박지_않고_회차_자료에서_찾는다(data):
    """다음 회차에 다른 이름이 갈려도 같은 스크립트가 잡아야 한다."""
    import inspect

    source = inspect.getsource(normalize_names)
    for hardcoded in ("민준", "하윤", "예솔", "도현"):
        assert f'"{hardcoded}"' not in source, f"{hardcoded} 이 코드에 박혀 있다"

    # 새로 갈린 이름을 넣으면 그것도 잡는다
    with app_session() as db:
        program = db.scalars(select(models.Program).where(
            models.Program.retreat_id == data["main_id"])).first()
        db.add_all([
            models.ProgramItem(program_id=program.id, phase="pre", part_key="행정",
                               assignee_name="건우", text="새 이름", sort_order=90),
            models.ProgramItem(program_id=program.id, phase="pre", part_key="행정",
                               assignee_name="건우M", text="새 이름 M", sort_order=91),
        ])
        db.commit()

    with app_session() as db:
        assert preview(db)["mapping"]["건우"] == "건우M"


# ---------------------------------------------------------------- 7. 없는 회차


def test_07_없는_회차_이름을_주면_있는_회차를_보여주고_멈춘다(data):
    with app_session() as db:
        with pytest.raises(import_programs.ImportError_) as caught:
            normalize_names.run(db, retreat_name="2026 여름수련회")

    message = str(caught.value)
    assert "회차가 없습니다" in message
    assert "2026 여름수련회 Belong" in message      # 있는 회차를 알려준다

    with app_session() as db:
        assert "민준" in names_of(db, data["main_id"])   # 아무것도 안 바뀌었다


def test_07b_회차_찾기를_두_벌_만들지_않았다():
    import inspect

    source = inspect.getsource(normalize_names)
    assert "from scripts.import_programs import" in source
    assert "find_retreat" in source
    assert "def find_retreat" not in source, "같은 것을 두 벌 만들었다"


# ---------------------------------------------------------------- 8. 다른 회차


def test_08_다른_회차의_항목은_바뀌지_않는다(data):
    with app_session() as db:
        normalize_names.run(db, retreat_name="2026 여름수련회 Belong", apply=True)

    with app_session() as db:
        winter = names_of(db, data["other_id"])
    assert "민준" in winter, "다른 회차가 바뀌었다"
    assert winter.count("민준M") == 1          # 원래 있던 하나뿐


# ---------------------------------------------------------------- 9. 안 건드리는 것


def test_09_TaskRun_assignee_id_와_done_by_id_는_바뀌지_않는다(admin_client, data):
    """assignee_id 는 계정이지 이름이 아니고, done_by_id 는 누가 눌렀는지의 기록이다."""
    with app_session() as db:
        person = models.User(name="민준", phone_number="01099998888", role="member")
        db.add(person)
        db.flush()
        lib = models.TaskLibrary(
            title="포스터 제작", kind="main", default_department_key="sketch",
            related_department_keys=[], related_library_ids=[],
            date_anchor="week", default_d_week=13, default_offset_days=0,
            default_span_days=6)
        db.add(lib)
        db.flush()
        run_row = models.TaskRun(
            library_id=lib.id, retreat_id=data["main_id"], included=True,
            d_week=13, start_date=OPEN, end_date=OPEN, status="대기",
            assignee_id=person.id)
        db.add(run_row)
        # 체크한 사람도 남겨 둔다.
        # 겨울 회차에도 같은 이름이 있으므로 이 회차 것으로 좁힌다
        item = db.scalars(
            select(models.ProgramItem)
            .join(models.Program)
            .where(models.Program.retreat_id == data["main_id"],
                   models.ProgramItem.assignee_name == "민준")).one()
        item.done_at = dt.datetime(2026, 8, 21, 14, 0)
        item.done_by_id = person.id
        db.commit()
        run_id, person_id, item_id = run_row.id, person.id, item.id

    with app_session() as db:
        normalize_names.run(db, retreat_name="2026 여름수련회 Belong", apply=True)

    with app_session() as db:
        assert db.get(models.TaskRun, run_id).assignee_id == person_id
        saved = db.get(models.ProgramItem, item_id)
        assert saved.done_by_id == person_id
        assert saved.done_at is not None
        assert saved.assignee_name == "민준M"      # 이름만 바뀐다
        # 사람 계정의 이름도 그대로다
        assert db.get(models.User, person_id).name == "민준"


# ---------------------------------------------------------------- 10. 활동 기록


def test_10_apply_하면_log_activity_에_남는다(data):
    with app_session() as db:
        normalize_names.run(db, retreat_name="2026 여름수련회 Belong", apply=True)

    with app_session() as db:
        logs = list(db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "담당자_표기_통일")))
    assert len(logs) == 1
    log = logs[0]
    assert log.retreat_id == data["main_id"]
    assert log.target_type == "retreat"
    assert "3건" in log.summary                  # 바뀐 **항목** 수
    assert "민준→민준M" in log.summary            # 무엇을 바꿨는지
    assert "도현→도현M" in log.summary
    assert sorted(log.after_value["names"]) == ["도현M", "민준M", "예솔M", "하윤M"]


# ---------------------------------------------------------------- 11. 두 번


def test_11_두_번_돌려도_두_번째는_바꿀_것이_없다(data):
    with app_session() as db:
        first = normalize_names.run(
            db, retreat_name="2026 여름수련회 Belong", apply=True)
    assert len(first["changes"]) == 3

    with app_session() as db:
        second = normalize_names.run(
            db, retreat_name="2026 여름수련회 Belong", apply=True)

    assert second["changes"] == []
    assert second["applied"] is False
    # 짝은 그대로 보이지만(둘 다 쓰인 적이 있다는 뜻은 아니고 이제 M 만 남았다)
    # 바꿀 것이 없으니 활동 기록도 더 늘지 않는다
    with app_session() as db:
        logs = list(db.scalars(select(models.ActivityLog).where(
            models.ActivityLog.action == "담당자_표기_통일")))
    assert len(logs) == 1


def test_11b_다_맞춰지면_짝_자체가_사라진다(data):
    with app_session() as db:
        normalize_names.run(db, retreat_name="2026 여름수련회 Belong", apply=True)
    with app_session() as db:
        result = preview(db)
    # X 가 하나도 남지 않았으므로 짝이 아니다
    assert result["mapping"] == {}
    assert result["changes"] == []
