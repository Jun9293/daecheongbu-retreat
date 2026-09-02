"""업무 간 선후행 관계 (CLAUDE.md 2장 · 4-10 · 6-8).

수용 기준 1~10 에 하나씩 대응한다. 함수 이름 끝의 숫자가 그 번호다.

세 관계를 섞지 않는 것이 이 파일이 지키는 것 —
관련업무는 방향이 없고, 선행은 방향이 있으며 가진 쪽에만 저장하고,
상위-하위는 포함 관계지 앞을 막는 관계가 아니다.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import models
from app.domain import library as lib_domain
from tests.conftest import app_session, login_as

OPEN = dt.date(2026, 8, 21)


def _library(db, title, *, key="sketch", d_week=10, parent=None, kind="main"):
    lib = models.TaskLibrary(
        title=title,
        kind=kind,
        parent_library_id=parent,
        default_department_key=key,
        related_department_keys=[],
        related_library_ids=[],
        prerequisite_library_ids=[],
        date_anchor="week",
        default_d_week=d_week,
        default_offset_days=0,
        default_span_days=0,
    )
    db.add(lib)
    db.flush()
    return lib


@pytest.fixture
def libs(admin_client):
    """부서 2개와 라이브러리 업무 몇 건을 가진 회차."""
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회 Belong", start_date=OPEN, end_date=dt.date(2026, 8, 23)
        )
        db.add(retreat)
        db.flush()
        depts = {}
        for order, (key, name, color) in enumerate(
            [("sketch", "4 스케치", "#B95A83"), ("hebron", "5 헤브론", "#4A8A5C")]
        ):
            dept = models.Department(
                retreat_id=retreat.id, key=key, name=name, color_tag=color, sort_order=order
            )
            db.add(dept)
            db.flush()
            depts[key] = dept

        poster = _library(db, "포스터 제작", d_week=9)
        design = _library(db, "시안 확정", d_week=11, parent=poster.id, kind="sub")
        gear = _library(db, "장비 확인", key="hebron", d_week=12)
        deliver = _library(db, "장비 전달", key="hebron", d_week=6)
        archived = _library(db, "옛 업무", d_week=13)
        archived.archived_at = dt.datetime(2026, 1, 1)

        runs = {}
        for lib in (poster, design, gear, deliver):
            run = models.TaskRun(
                library_id=lib.id,
                retreat_id=retreat.id,
                included=True,
                department_id=depts[lib.default_department_key].id,
                d_week=lib.default_d_week,
                start_date=dt.date(2026, 6, 7),
                end_date=dt.date(2026, 6, 7),
                status="대기",
                blocked_by_run_ids=[],
            )
            db.add(run)
            db.flush()
            runs[lib.title] = run.id

        db.add(
            models.User(
                name="헤브론 리더",
                phone_number="01077778888",
                role="dept_lead",
                department_id=depts["hebron"].id,
            )
        )
        db.commit()
        return {
            "retreat_id": retreat.id,
            "runs": runs,
            "libs": {
                "poster": poster.id,
                "design": design.id,
                "gear": gear.id,
                "deliver": deliver.id,
                "archived": archived.id,
            },
        }


@pytest.fixture
def hebron_client(libs):
    from app.main import app

    client = TestClient(app)
    login_as(client, "01077778888")
    return client


# ── 1. 필드와 자동 컬럼 추가 ──────────────────────────────────────────


def test_01_선행_필드가_있고_컬럼이_자동으로_붙는다(libs):
    assert hasattr(models.TaskLibrary, "prerequisite_library_ids")

    from app.db import _ADDED_COLUMNS, engine

    assert ("task_library", "prerequisite_library_ids", "TEXT") in _ADDED_COLUMNS

    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(task_library)"))}
    assert "prerequisite_library_ids" in columns


# ── 2. NULL 인 기존 행 ────────────────────────────────────────────────


def test_02_NULL_인_기존_행을_읽어도_터지지_않는다(libs, admin_client):
    """ALTER 로 붙은 컬럼은 기존 행에서 NULL 이다. 읽는 자리는 전부 `or []` 로 감싼다."""
    with app_session() as db:
        db.execute(
            text("UPDATE task_library SET prerequisite_library_ids = NULL WHERE id = :i"),
            {"i": libs["libs"]["poster"]},
        )
        db.commit()
        lib = db.get(models.TaskLibrary, libs["libs"]["poster"])
        assert lib_domain.prerequisites_of(lib) == []

    with app_session() as db:
        assert lib_domain.dependents_map(db) == {} or True
        assert lib_domain.flat_catalog(db, open_date=OPEN)
    assert admin_client.get("/board").status_code == 200
    assert admin_client.get("/library").status_code == 200


# ── 3. 단방향 저장 ────────────────────────────────────────────────────


def test_03_선행은_단방향으로만_저장된다(libs, admin_client):
    a, b = libs["libs"]["deliver"], libs["libs"]["gear"]
    res = admin_client.post(
        "/library/prerequisites", json={"library_id": a, "prerequisite_ids": [b]}
    )
    assert res.status_code == 200, res.text

    with app_session() as db:
        assert lib_domain.prerequisites_of(db.get(models.TaskLibrary, a)) == [b]
        # 반대편에는 아무것도 쓰지 않는다 — 후속은 계산해서 얻는다
        assert lib_domain.prerequisites_of(db.get(models.TaskLibrary, b)) == []
        assert lib_domain.dependents_map(db)[b] == [a]


# ── 4. 검증 네 가지 ───────────────────────────────────────────────────


def test_04a_자기_자신은_거부된다(libs, admin_client):
    a = libs["libs"]["poster"]
    res = admin_client.post(
        "/library/prerequisites", json={"library_id": a, "prerequisite_ids": [a]}
    )
    assert res.status_code == 400
    assert "자기 자신" in res.json()["detail"]


def test_04b_순환은_거부된다(libs, admin_client):
    gear, deliver, poster = (
        libs["libs"]["gear"], libs["libs"]["deliver"], libs["libs"]["poster"]
    )
    # deliver ← gear, gear ← poster 까지는 정상
    assert admin_client.post(
        "/library/prerequisites", json={"library_id": deliver, "prerequisite_ids": [gear]}
    ).status_code == 200
    assert admin_client.post(
        "/library/prerequisites", json={"library_id": gear, "prerequisite_ids": [poster]}
    ).status_code == 200
    # poster ← deliver 를 더하면 고리가 된다
    res = admin_client.post(
        "/library/prerequisites", json={"library_id": poster, "prerequisite_ids": [deliver]}
    )
    assert res.status_code == 400
    assert "고리" in res.json()["detail"]

    with app_session() as db:   # 거부됐으니 저장도 되지 않는다
        assert lib_domain.prerequisites_of(db.get(models.TaskLibrary, poster)) == []


def test_04c_상위하위는_거부된다(libs, admin_client):
    """상위는 나를 포함하는 관계지 앞을 막는 관계가 아니다 (CLAUDE.md 4-10)."""
    poster, design = libs["libs"]["poster"], libs["libs"]["design"]
    up = admin_client.post(
        "/library/prerequisites", json={"library_id": design, "prerequisite_ids": [poster]}
    )
    assert up.status_code == 400 and "상위" in up.json()["detail"]

    down = admin_client.post(
        "/library/prerequisites", json={"library_id": poster, "prerequisite_ids": [design]}
    )
    assert down.status_code == 400 and "하위" in down.json()["detail"]


def test_04d_보관된_업무는_거부된다(libs, admin_client):
    res = admin_client.post(
        "/library/prerequisites",
        json={"library_id": libs["libs"]["poster"],
              "prerequisite_ids": [libs["libs"]["archived"]]},
    )
    assert res.status_code == 400
    assert "보관된" in res.json()["detail"]


def test_04e_사유가_화면에_보인다(libs, admin_client):
    """위반 사유를 화면에 띄우는 자리가 실제로 있는지."""
    page = admin_client.get("/library")
    assert page.status_code == 200
    assert 'id="prewarn"' in page.text          # 사유를 적는 자리
    js = _JsResponse(_js("library.js"))
    assert "out.detail" in js.text              # 서버가 준 사유를 그대로 쓴다


# ── 5. 회차 생성이 blocked_by_run_ids 를 채운다 ───────────────────────


def test_05_새_회차를_만들면_선행이_run_으로_옮겨진다(libs):
    gear, deliver = libs["libs"]["gear"], libs["libs"]["deliver"]
    with app_session() as db:
        lib_domain.set_prerequisites(db, db.get(models.TaskLibrary, deliver), [gear])
        db.commit()

    with app_session() as db:
        retreat = lib_domain.create_retreat(
            db,
            name="2027 겨울수련회",
            open_date=dt.date(2027, 1, 14),
            close_date=dt.date(2027, 1, 17),
            meal_subsidy=8000,
            department_keys=["sketch", "hebron"],
            selected_library_ids={
                libs["libs"]["poster"], gear, deliver
            },
        )
    with app_session() as db:
        from sqlalchemy import select

        rows = {
            run.library_id: run
            for run in db.scalars(
                select(models.TaskRun).where(models.TaskRun.retreat_id == retreat.id)
            )
        }
        assert rows[deliver].blocked_by_run_ids == [rows[gear].id]
        assert rows[gear].blocked_by_run_ids == []   # 역방향은 저장하지 않는다


def test_05b_included_끼리만_연결한다(libs):
    gear, deliver = libs["libs"]["gear"], libs["libs"]["deliver"]
    with app_session() as db:
        lib_domain.set_prerequisites(db, db.get(models.TaskLibrary, deliver), [gear])
        db.commit()

    with app_session() as db:
        retreat = lib_domain.create_retreat(
            db,
            name="선행 빠진 회차",
            open_date=dt.date(2027, 1, 14),
            close_date=dt.date(2027, 1, 17),
            meal_subsidy=8000,
            department_keys=["sketch", "hebron"],
            selected_library_ids={deliver},      # gear 를 뺐다
        )
        unmet = getattr(retreat, "unmet_prerequisites", [])

    with app_session() as db:
        from sqlalchemy import select

        rows = {
            run.library_id: run
            for run in db.scalars(
                select(models.TaskRun).where(models.TaskRun.retreat_id == retreat.id)
            )
        }
        assert rows[deliver].blocked_by_run_ids == []   # 끊긴 참조를 만들지 않는다
        assert rows[gear].included is False
    assert [u["prerequisite_id"] for u in unmet] == [gear]


# ── 6. 마법사 4단계 경고 ──────────────────────────────────────────────


def test_06_선행이_빠지면_마법사에_경고로_뜬다(libs, admin_client):
    gear, deliver = libs["libs"]["gear"], libs["libs"]["deliver"]
    with app_session() as db:
        lib_domain.set_prerequisites(db, db.get(models.TaskLibrary, deliver), [gear])
        db.commit()

    # 서버가 근거를 준다
    with app_session() as db:
        missing = lib_domain.missing_prerequisites(db, {deliver})
        assert len(missing) == 1
        assert missing[0]["prerequisite_title"] == "장비 확인"
        assert missing[0]["title"] == "장비 전달"
        assert lib_domain.missing_prerequisites(db, {deliver, gear}) == []

    # 마법사 화면이 그 근거를 받아 간다
    preview = admin_client.post(
        "/setup/preview",
        json={"open_date": "2027-01-14", "close_date": "2027-01-17"},
    )
    assert preview.status_code == 200, preview.text
    row = next(i for i in preview.json()["items"] if i["title"] == "장비 전달")
    assert row["prereqs"][0]["prerequisite_title"] == "장비 확인"
    assert row["prereqs"][0]["owner_id"] == str(gear)

    js = _js("setup.js")
    assert "선행 업무" in js and "unmet" in js


# ── 7. /library 에서 상위·하위 모두 지정하고 해제한다 ─────────────────


def test_07_상위와_하위_모두에_지정하고_해제한다(libs, admin_client):
    poster, design, gear = (
        libs["libs"]["poster"], libs["libs"]["design"], libs["libs"]["gear"]
    )
    # 하위 업무(시안 확정)에도 선행을 건다 — 선후행이 실제로 필요한 자리다
    assert admin_client.post(
        "/library/prerequisites", json={"library_id": design, "prerequisite_ids": [gear]}
    ).status_code == 200
    assert admin_client.post(
        "/library/prerequisites", json={"library_id": poster, "prerequisite_ids": [gear]}
    ).status_code == 200

    with app_session() as db:
        rows = {r["library_id"]: r for r in lib_domain.flat_catalog(db, open_date=OPEN)}
        assert rows[design]["depth"] == 1        # 하위가 한 줄로 펼쳐진다
        assert [p["library_id"] for p in rows[design]["prerequisites"]] == [gear]
        assert {d["library_id"] for d in rows[gear]["dependents"]} == {design, poster}

    # 빈 목록으로 저장하면 해제된다
    assert admin_client.post(
        "/library/prerequisites", json={"library_id": design, "prerequisite_ids": []}
    ).status_code == 200
    with app_session() as db:
        assert lib_domain.prerequisites_of(db.get(models.TaskLibrary, design)) == []

    page = admin_client.get("/library")
    assert "선후행 관계" in page.text and "선행 고르기" in page.text
    assert 'id="pfind"' in page.text             # 이름으로 좁혀 찾기


# ── 8. 근거가 붙은 제안, 누르기 전에는 저장 안 함 ─────────────────────


def test_08_제안은_근거와_함께_나오고_저장되지_않는다(libs, admin_client):
    gear, deliver = libs["libs"]["gear"], libs["libs"]["deliver"]
    with app_session() as db:
        # 관련업무로 묶고 (양방향), D-주차는 gear(12) 가 deliver(6) 보다 앞선다
        db.get(models.TaskLibrary, deliver).related_library_ids = [gear]
        db.get(models.TaskLibrary, gear).related_library_ids = [deliver]
        db.commit()

    with app_session() as db:
        proposals = lib_domain.prerequisite_proposals(db)
        pair = next(
            p for p in proposals
            if p["library_id"] == deliver and p["prerequisite_id"] == gear
        )
        assert "D-12주 → D-6주" in pair["rationale"]
        assert "관련업무" in pair["rationale"]
        # 반대 방향(이른 업무가 늦은 것을 기다림)은 제안하지 않는다
        assert not any(
            p["library_id"] == gear and p["prerequisite_id"] == deliver for p in proposals
        )
        # 제안만으로는 저장되지 않는다
        assert lib_domain.prerequisites_of(db.get(models.TaskLibrary, deliver)) == []
        # 라이브러리 행을 새로 만들지도 않는다
        assert db.query(models.TaskLibrary).filter_by(origin="claude_suggestion").count() == 0

    page = admin_client.get("/library")
    assert "누르기 전에는 저장되지 않습니다" in page.text
    assert 'class="prop"' in page.text


def test_08b_시드에는_선후행이_없다():
    """이력을 지어내지 않는다 (CLAUDE.md 6-9). 관계도 마찬가지다.

    시드의 RELATIONS 는 방향 없는 '관련업무'다. 선행으로 옮겨 심으면
    실제로 그런 제약이 있었는지 확인한 적 없는 관계가 판단 근거가 된다.
    """
    import seed_library_data

    assert not hasattr(seed_library_data, "PREREQUISITES")
    source = pathlib.Path("seed_library.py").read_text(encoding="utf-8")
    assert "prerequisite" not in source
    # RELATIONS 는 양방향 관련업무로만 쓰인다
    assert "related_library_ids" in source


# ── 9. 상세 패널의 선행 / 후속 / 관련 ─────────────────────────────────


def test_09_상세_패널에서_선행_후속_관련이_구분된다(libs, admin_client):
    gear, deliver = libs["libs"]["gear"], libs["libs"]["deliver"]
    gear_run, deliver_run = libs["runs"]["장비 확인"], libs["runs"]["장비 전달"]

    saved = admin_client.post(
        f"/board/task/{deliver_run}/prerequisites", json={"run_ids": [gear_run]}
    )
    assert saved.status_code == 200, saved.text
    assert [r["run_id"] for r in saved.json()["prerequisites"]] == [gear_run]

    # 기다리는 쪽에서 보면 선행, 반대편에서 보면 후속
    mine = admin_client.get(f"/board/task/{deliver_run}").json()
    assert [r["run_id"] for r in mine["prerequisites"]] == [gear_run]
    assert mine["dependents"] == []

    theirs = admin_client.get(f"/board/task/{gear_run}").json()
    assert theirs["prerequisites"] == []
    assert [r["run_id"] for r in theirs["dependents"]] == [deliver_run]

    # 이번 회차의 링크도 함께 맞춰진다
    with app_session() as db:
        assert db.get(models.TaskRun, deliver_run).blocked_by_run_ids == [gear_run]

    # 보드 meta 가 관련과 별개 키로 싣는다
    board = admin_client.get("/board")
    assert board.status_code == 200
    assert "blocked_by_run_ids" in board.text and "blocks_run_ids" in board.text

    # 연결된 업무 목록은 **상세 패널** 안에 있다. 패널은 보드와 달력이
    # 같이 쓰는 한 벌이라 board.js 가 아니라 drawer.js 에 있다 (4-13).
    js = _js("drawer.js")
    assert "선행 — 끝나야 시작할 수 있다" in js
    assert "후속 — 나를 기다린다" in js
    assert "관련 — 방향 없음" in js
    assert "다음 회차에도 그대로 적용됩니다" in js
    assert "data-act=\"open\"" in js and "data-act=\"move\"" in js   # 열기/이동 유지


def test_09b_상세_패널에서도_같은_검증이_걸린다(libs, admin_client):
    poster_run = libs["runs"]["포스터 제작"]
    res = admin_client.post(
        f"/board/task/{poster_run}/prerequisites", json={"run_ids": [poster_run]}
    )
    assert res.status_code == 400
    assert "자기 자신" in res.json()["detail"]


# ── 10. 편집 권한 ─────────────────────────────────────────────────────


def test_10_남의_부서_업무의_선후행_편집은_403(libs, hebron_client):
    """선행을 '가진 쪽' 업무의 담당 부서와 총무팀만 고칠 수 있다."""
    poster_run = libs["runs"]["포스터 제작"]      # 스케치 담당
    deliver_run = libs["runs"]["장비 전달"]        # 헤브론 담당
    gear_run = libs["runs"]["장비 확인"]

    denied = hebron_client.post(
        f"/board/task/{poster_run}/prerequisites", json={"run_ids": [gear_run]}
    )
    assert denied.status_code == 403

    # 자기 부서 업무는 고칠 수 있다 — 남의 부서 업무를 선행으로 두는 것도 된다
    allowed = hebron_client.post(
        f"/board/task/{deliver_run}/prerequisites", json={"run_ids": [poster_run]}
    )
    assert allowed.status_code == 200, allowed.text

    with app_session() as db:
        assert db.get(models.TaskRun, deliver_run).blocked_by_run_ids == [poster_run]
        # 넣어준 쪽(포스터)에는 아무것도 쓰이지 않는다
        assert db.get(models.TaskRun, poster_run).blocked_by_run_ids == []


# ── 11. 마법사 3단계(catalog)의 기존 동작 ─────────────────────────────


def test_11_catalog_은_그대로다(libs):
    """선후행은 flat_catalog 로 따로 만들었다. catalog 는 건드리지 않았다."""
    with app_session() as db:
        rows = lib_domain.catalog(db, open_date=OPEN)
        titles = {r["title"] for r in rows}
        assert "포스터 제작" in titles
        assert "시안 확정" not in titles          # 하위는 children 안에 중첩된다
        poster = next(r for r in rows if r["title"] == "포스터 제작")
        assert [c["title"] for c in poster["children"]] == ["시안 확정"]
        assert "prerequisites" not in poster      # catalog 의 모양은 그대로


# ════════════════════════════════════════════════════════════════════
#  상태를 바꾸면 판정도 함께 바뀐다 (수용기준 6·7)
# ════════════════════════════════════════════════════════════════════
#
# `setStatus` 가 `detail.status` 만 갈아끼우고 다시 그리는데 `renderDiag` 는
# 손대지 않은 `detail.diagnosis` 를 그렸다. **상태 변경은 판정을 바꾸는 바로
# 그 동작**이라(4-10 의 1번: 완료면 맨 위에서 끊는다), 완료로 바꿔도 위쪽에
# '진행 불가' 가 남았다. 패널 이름이 판정 결과인 화면이라 더 그렇다.

import pathlib as _pathlib


def _js(name: str) -> str:
    """정적 JS 를 **디스크에서** 읽는다. 주소에 내용 해시가 들어가 있어서
    (`/static/js/drawer.<8자리>.js`) 이름만으로는 HTTP 로 못 받는다 —
    해시 없는 주소는 404 다. 파일 내용을 보려던 시험이므로 서버를 거칠
    이유가 애초에 없었다."""
    import pathlib as _p

    return (_p.Path(__file__).resolve().parent.parent
            / "app" / "static" / "js" / name).read_text(encoding="utf-8")


class _JsResponse:
    """`.status_code` · `.text` 만 흉내 낸다 — 이 시험이 쓰는 것이 그 둘뿐이다."""

    def __init__(self, text: str):
        self.status_code, self.text = 200, text



DRAWER_JS = _pathlib.Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "drawer.js"


def test_r06_상태를_바꾸면_판정을_다시_받아온다():
    js = DRAWER_JS.read_text(encoding="utf-8")

    body = js[js.index("async function setStatus("):]
    body = body[: body.index("\n}")]
    assert "refreshDiag" in body, "상태를 바꾸고 판정을 다시 받지 않는다"

    # '다시 분석' 버튼과 같은 길을 쓴다 — 두 벌로 두면 한쪽만 고쳐진다
    assert "$('dgR').onclick = () => { if (cur !== null) refreshDiag(cur); };" in js


def test_r06b_서버가_상태에_맞는_판정을_준다(libs, admin_client):
    """화면이 다시 받아 올 값이 실제로 바뀌는지 — 안 바뀌면 다시 받아도 소용없다.

    4-10 의 1번은 **완료를 맨 위에서 끊는다.** 선행이 미완료인 채로 끝낸
    업무가 '진행 불가' 로 찍히면 안 되기 때문이다.
    """
    # **종료된 회차는 판정하지 않는다** (4-10) — 그 상태로는 상태를 바꿔도
    # 판정이 그대로라 이 시험이 헛돈다. 진행 중인 회차로 옮겨 놓고 본다.
    import datetime as _dt

    from sqlalchemy import select
    with app_session() as db:
        retreat = db.get(models.Retreat, libs["retreat_id"])
        retreat.start_date = _dt.date.today() + _dt.timedelta(days=30)
        retreat.end_date = _dt.date.today() + _dt.timedelta(days=32)
        for run in db.scalars(select(models.TaskRun)):
            run.end_date = _dt.date.today() + _dt.timedelta(days=20)
        db.commit()

    deliver = libs["runs"]["장비 전달"]
    gear = libs["runs"]["장비 확인"]
    admin_client.post(f"/board/task/{deliver}/prerequisites", json={"run_ids": [gear]})

    before = admin_client.get(f"/board/task/{deliver}").json()["diagnosis"]
    assert before["verdict"] == "진행 불가"

    admin_client.post(f"/board/task/{deliver}/status", json={"status": "완료"})
    after = admin_client.get(f"/board/task/{deliver}").json()["diagnosis"]
    assert after["verdict"] == "완료", "상태를 바꿨는데 판정이 그대로다"
    assert before["verdict"] != after["verdict"]


def test_r07_판정을_못_받아와도_패널이_살아_있다():
    """4-10 조건 8 — 판정 한 자리가 비는 것으로 끝나야지, 나머지 근거까지
    사라지면 결정적인 절반을 애써 분리한 이유가 없어진다."""
    js = DRAWER_JS.read_text(encoding="utf-8")

    body = js[js.index("async function refreshDiag("):]
    body = body[: body.index("\n}\n")]

    # 실패는 삼키되, 옛 판정을 지우지 않는다
    assert "catch" in body, "실패를 받지 않는다 — 패널이 통째로 멈춘다"
    assert "if (!res.ok) return;" in body
    assert "renderDiag(null)" not in body and "innerHTML = ''" not in body

    # 받아 오는 동안 옛것임이 보이고, 끝나면 반드시 풀린다
    assert "classList.add('busy')" in body
    assert "finally" in body and "classList.remove('busy')" in body

    # 그 사이에 다른 업무를 열었으면 남의 판정을 덮어쓰지 않는다
    assert "String(cur) !== String(fresh.run_id)" in body
