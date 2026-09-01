"""업무 첨부파일 (CLAUDE.md 4-9). 수용 기준 8~14.

**임시 폴더에만 쓴다.** conftest 가 `DCB_DATA_DIR` 을 임시 경로로 잡아 두었으므로
`app.config.ATTACHMENT_DIR` 도 그 아래에 있다 — 운영 데이터 폴더를 건드리지 않는다.
네트워크에도 의존하지 않는다.
"""

from __future__ import annotations

import datetime as dt
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.config import ALLOWED_ATTACHMENT_EXTS, ATTACHMENT_DIR, MAX_ATTACHMENT_BYTES
from tests.conftest import app_session, login_as

OPEN = dt.date(2026, 8, 21)


@pytest.fixture
def task_data(admin_client):
    """부서 2개 · 업무 2건. 스케치 리더 계정을 함께 만든다.

    권한을 부서 **키**로 보는지 확인해야 하므로 부서에 key 를 반드시 넣는다.
    """
    with app_session() as db:
        retreat = models.Retreat(
            name="2026 여름수련회 Belong", start_date=OPEN, end_date=dt.date(2026, 8, 23)
        )
        db.add(retreat)
        db.flush()

        depts = {}
        for order, (key, name, color) in enumerate(
            [("chongmuM", "1 총무M", "#2F4858"), ("sketch", "4 스케치", "#B95A83")]
        ):
            dept = models.Department(
                retreat_id=retreat.id, key=key, name=name, color_tag=color, sort_order=order
            )
            db.add(dept)
            db.flush()
            depts[key] = dept

        runs = {}
        for key, title, d_week in [("sketch", "포스터 제작", 13), ("chongmuM", "차량 신청", 2)]:
            lib = models.TaskLibrary(
                title=title,
                kind="main",
                default_department_key=key,
                related_department_keys=[],
                related_library_ids=[],
                date_anchor="week",
                default_d_week=d_week,
                default_offset_days=0,
                default_span_days=6,
            )
            db.add(lib)
            db.flush()
            run = models.TaskRun(
                library_id=lib.id,
                retreat_id=retreat.id,
                included=True,
                department_id=depts[key].id,
                d_week=d_week,
                start_date=dt.date(2026, 5, 24),
                end_date=dt.date(2026, 5, 31),
                status="대기",
            )
            db.add(run)
            db.flush()
            runs[title] = {"run_id": run.id, "library_id": lib.id}

        db.add(
            models.User(
                name="스케치 리더",
                phone_number="01055556666",
                role="dept_lead",
                department_id=depts["sketch"].id,
            )
        )
        db.commit()
        return {"retreat_id": retreat.id, "runs": runs}


@pytest.fixture
def lead_client(task_data):
    """스케치 부서 리더. 자기 부서(포스터 제작)만 고칠 수 있다."""
    from app.main import app

    client = TestClient(app)
    login_as(client, "01055556666")
    return client


def upload(client, run_id, name, body=b"hello", **kw):
    return client.post(
        f"/board/task/{run_id}/files",
        files={"upload": (name, io.BytesIO(body), kw.get("mime", "application/octet-stream"))},
    )


# ---------------------------------------------------------------- 8. 탭


def test_08_첨부파일_탭이_맨_끝에_있고_개수가_표시된다(admin_client, task_data):
    """탭은 업무 규칙 · 논의 내역 · 달력 · 연결된 업무 · 첨부파일 순이다."""
    page = admin_client.get("/board").text

    order = [page.index(f'data-p="{p}"') for p in ("rules", "log", "cal", "rel", "files")]
    assert order == sorted(order), "첨부파일이 탭 맨 끝이 아니다"
    assert 'id="fileN"' in page, "개수를 표시할 자리가 없다"

    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    detail = admin_client.get(f"/board/task/{run_id}").json()
    assert detail["attachments"] == []

    upload(admin_client, run_id, "시안.pdf")
    detail = admin_client.get(f"/board/task/{run_id}").json()
    assert len(detail["attachments"]) == 1


# ------------------------------------------------- 9. 올리기 · 내려받기 · 삭제


def test_09_파일을_올리면_목록에_뜨고_내려받기와_삭제가_된다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]

    response = upload(admin_client, run_id, "포스터_시안.pdf", b"PDF-CONTENT")
    assert response.status_code == 200, response.text
    files = response.json()["files"]
    assert len(files) == 1
    entry = files[0]
    assert entry["name"] == "포스터_시안.pdf"
    assert entry["ext"] == "pdf"
    assert entry["size"] == len(b"PDF-CONTENT")
    assert entry["by"] == "총무 김간사"
    # 벽시계 기준이다 — UTC 로 남기면 자정~아침 9시에 올린 파일이 하루 전으로 보인다
    assert entry["at"] == dt.datetime.now().date().isoformat()

    got = admin_client.get(entry["url"])
    assert got.status_code == 200
    assert got.content == b"PDF-CONTENT"
    # 한글 파일 이름이 깨지지 않게 UTF-8 로 실어 보낸다
    assert "filename*=UTF-8''" in got.headers["content-disposition"]

    gone = admin_client.post(f"/board/task/{run_id}/files/{entry['id']}/delete")
    assert gone.status_code == 200
    assert gone.json()["files"] == []
    assert admin_client.get(entry["url"]).status_code == 404


def test_09b_이름을_바꿔도_디스크의_파일은_그대로다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    entry = upload(admin_client, run_id, "임시.pdf", b"X").json()["files"][0]

    renamed = admin_client.post(
        f"/board/task/{run_id}/files/{entry['id']}/rename", json={"name": "포스터 시안 최종"}
    )
    assert renamed.status_code == 200
    # 확장자를 지워도 무엇인지 알 수 있게 원래 것을 붙여 준다
    assert renamed.json()["files"][0]["name"] == "포스터 시안 최종.pdf"
    assert admin_client.get(entry["url"]).content == b"X"


def test_09c_파일_이름을_그대로_디스크에_쓰지_않는다(admin_client, task_data):
    """경로 조작·중복·한글 인코딩이 한꺼번에 사라진다."""
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    upload(admin_client, run_id, "../../탈출_시도.pdf", b"X")

    with app_session() as db:
        stored = db.scalars(select(models.TaskAttachment)).all()
    assert len(stored) == 1
    saved = stored[0]
    # 올린 이름은 마지막 조각만 남기고, 실제 파일은 임의의 이름으로 저장한다
    assert saved.original_name == "탈출_시도.pdf"
    assert ".." not in saved.stored_name and "/" not in saved.stored_name
    assert saved.stored_name != saved.original_name
    assert (ATTACHMENT_DIR / saved.stored_name).exists()


def test_09d_같은_이름을_두_번_올려도_서로_덮어쓰지_않는다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    upload(admin_client, run_id, "시안.pdf", "첫번째".encode())
    files = upload(admin_client, run_id, "시안.pdf", "두번째".encode()).json()["files"]

    assert len(files) == 2
    bodies = {admin_client.get(f["url"]).content for f in files}
    assert bodies == {"첫번째".encode(), "두번째".encode()}


# ---------------------------------------------------------------- 10. 하단 버튼


def test_10_하단에_파일_첨부_버튼이_없다(admin_client, task_data):
    """탭 안에 올리는 자리가 생겼으므로 같은 기능이 두 군데 있으면 안 된다 (4-9)."""
    page = admin_client.get("/board").text
    # 사이드바에도 </aside> 가 있으므로 마지막 것(= 상세 패널의 끝)까지 자른다
    foot = page[page.index('class="dfoot"') : page.rindex("</aside>")]

    assert "파일 첨부" not in foot
    assert "하위 업무 추가" in foot          # 나머지 버튼은 그대로다
    # 올리는 자리는 첨부파일 탭 안에 있다
    assert 'id="ddrop"' in page


# ---------------------------------------------------------------- 11. 회차별


def test_11_새_회차를_열면_업무는_따라오고_첨부는_따라오지_않는다(admin_client, task_data):
    """첨부는 TaskRun 에 붙는다 — 논의 내역과 같은 취급이고 업무 규칙과 다르다."""
    from app.domain import library as lib_domain

    old_run = task_data["runs"]["포스터 제작"]["run_id"]
    library_id = task_data["runs"]["포스터 제작"]["library_id"]
    upload(admin_client, old_run, "이번회차_시안.pdf", b"OLD")

    with app_session() as db:
        new_retreat = lib_domain.create_retreat(
            db,
            name="2027 겨울수련회",
            open_date=dt.date(2027, 1, 15),
            close_date=dt.date(2027, 1, 17),
            meal_subsidy=8_000,
            department_keys=["chongmuM", "sketch"],
            selected_library_ids={library_id},
        )
        new_run = db.scalars(
            select(models.TaskRun).where(
                models.TaskRun.retreat_id == new_retreat.id,
                models.TaskRun.library_id == library_id,
            )
        ).one()
        # 업무는 따라왔다
        assert new_run.library.title == "포스터 제작"
        # 파일은 따라오지 않았다
        assert new_run.attachments == []
        # 지난 회차의 파일은 그대로 남아 있다
        assert len(db.get(models.TaskRun, old_run).attachments) == 1


def test_11b_업무를_지우면_첨부_행도_함께_사라진다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    upload(admin_client, run_id, "시안.pdf", b"X")

    with app_session() as db:
        db.delete(db.get(models.TaskRun, run_id))
        db.commit()
        assert db.scalars(select(models.TaskAttachment)).all() == []


# ---------------------------------------------------------------- 12. 권한


def test_12_남의_부서_업무에_파일을_올리면_403(lead_client, task_data):
    """부서는 key 로 비교한다 (CLAUDE.md 2장)."""
    mine = task_data["runs"]["포스터 제작"]["run_id"]      # 스케치
    other = task_data["runs"]["차량 신청"]["run_id"]        # 총무M

    assert upload(lead_client, mine, "내부서.pdf").status_code == 200

    refused = upload(lead_client, other, "남의부서.pdf")
    assert refused.status_code == 403
    assert "내 부서" in refused.json()["detail"]


def test_12b_남의_부서_파일은_지우거나_이름을_바꿀_수도_없다(admin_client, lead_client, task_data):
    other = task_data["runs"]["차량 신청"]["run_id"]
    entry = upload(admin_client, other, "총무M_자료.pdf", b"X").json()["files"][0]

    assert lead_client.post(f"/board/task/{other}/files/{entry['id']}/delete").status_code == 403
    assert lead_client.post(
        f"/board/task/{other}/files/{entry['id']}/rename", json={"name": "바꾸기"}
    ).status_code == 403
    # 보는 것은 된다 — 논의 내역과 같은 범위다
    assert lead_client.get(entry["url"]).status_code == 200
    assert lead_client.get(f"/board/task/{other}/files").json()["can_edit"] is False


def test_12c_부서_행이_회차마다_새로_생겨도_키로_알아본다(lead_client, task_data):
    """`Department.id` 로 비교하면 새 회차가 열리는 순간 조용히 막힌다."""
    with app_session() as db:
        # 다음 회차의 스케치 부서 — 같은 key, 다른 id
        later = models.Retreat(
            name="2027 겨울수련회",
            start_date=dt.date(2027, 1, 15),
            end_date=dt.date(2027, 1, 17),
        )
        db.add(later)
        db.flush()
        dept = models.Department(
            retreat_id=later.id, key="sketch", name="4 스케치", color_tag="#B95A83", sort_order=0
        )
        db.add(dept)
        db.flush()
        lib = models.TaskLibrary(
            title="포스터 제작(다음 회차)",
            kind="main",
            default_department_key="sketch",
            related_department_keys=[],
            related_library_ids=[],
            date_anchor="week",
            default_d_week=13,
            default_offset_days=0,
            default_span_days=6,
        )
        db.add(lib)
        db.flush()
        run = models.TaskRun(
            library_id=lib.id,
            retreat_id=later.id,
            included=True,
            department_id=dept.id,
            d_week=13,
            start_date=dt.date(2026, 10, 18),
            end_date=dt.date(2026, 10, 25),
            status="대기",
        )
        db.add(run)
        db.commit()
        run_id, retreat_id = run.id, later.id

    ok = lead_client.post(
        f"/board/task/{run_id}/files?retreat_id={retreat_id}",
        files={"upload": ("다음회차.pdf", io.BytesIO(b"X"), "application/pdf")},
    )
    assert ok.status_code == 200, ok.text


# ---------------------------------------------------------------- 13. 상한


def test_13_용량을_넘으면_이유와_함께_거부한다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]

    too_big = upload(admin_client, run_id, "큰파일.pdf", b"x" * (MAX_ATTACHMENT_BYTES + 1))

    assert too_big.status_code == 400
    detail = too_big.json()["detail"]
    assert "너무 큽니다" in detail
    assert "MB" in detail                      # 상한이 얼마인지 함께 말한다
    assert admin_client.get(f"/board/task/{run_id}/files").json()["files"] == []


def test_13b_허용하지_않는_확장자는_이유와_함께_거부한다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]

    refused = upload(admin_client, run_id, "설치파일.exe", b"MZ")

    assert refused.status_code == 400
    detail = refused.json()["detail"]
    assert ".exe" in detail
    assert "올릴 수 있는 형식" in detail
    assert ".exe" not in ALLOWED_ATTACHMENT_EXTS


def test_13c_확장자가_없거나_빈_파일도_사유를_말한다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]

    assert "확장자 없는 파일" in upload(admin_client, run_id, "이름만", b"X").json()["detail"]
    assert "빈 파일" in upload(admin_client, run_id, "빈것.pdf", b"").json()["detail"]


def test_13d_화면도_상한을_알아야_이유를_말할_수_있다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]

    limits = admin_client.get(f"/board/task/{run_id}/files").json()["limits"]

    assert limits["max_bytes"] == MAX_ATTACHMENT_BYTES
    assert limits["max_label"].endswith("MB")
    assert ".pdf" in limits["exts"]


# ---------------------------------------------------------------- 14. 백업


def test_14_backup_이_업로드_폴더도_함께_남긴다(tmp_path):
    """파일은 DB 밖에 쌓인다. app.db 만 되돌리면 목록에 있는 파일이 열리지 않는다."""
    import sqlite3
    import zipfile

    from scripts import backup

    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE note (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    uploads = tmp_path / "uploads"
    (uploads / "attachments").mkdir(parents=True)
    (uploads / "attachments" / "abc123.pdf").write_bytes(b"PDF")

    result = backup.run(
        db_path=db_path,
        key_path=tmp_path / "없는키.pem",
        uploads=uploads,
        out_dir=tmp_path / "backups",
    )

    assert result["ok"] is True
    assert result["uploads"] is not None and result["uploads"].exists()
    with zipfile.ZipFile(result["uploads"]) as zf:
        assert "attachments/abc123.pdf" in zf.namelist()
        assert zf.read("attachments/abc123.pdf") == b"PDF"


def test_14b_올라온_파일이_없으면_빈_zip_을_만들지_않는다(tmp_path):
    """빈 zip 이 30개 쌓이면 '백업에 파일이 있다'와 '원래 없었다'를 구별할 수 없다."""
    import sqlite3

    from scripts import backup

    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()
    uploads = tmp_path / "uploads"
    uploads.mkdir()

    result = backup.run(
        db_path=db_path, key_path=tmp_path / "x.pem", uploads=uploads,
        out_dir=tmp_path / "backups",
    )
    assert result["uploads"] is None


def test_14c_오래된_업로드_묶음도_DB_와_같은_회차로_지운다(tmp_path):
    import sqlite3

    from scripts import backup

    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()
    uploads = tmp_path / "uploads"
    (uploads).mkdir()
    (uploads / "a.txt").write_text("가", encoding="utf-8")
    out = tmp_path / "backups"
    out.mkdir()
    for i in range(35):
        stamp = f"20260101-{i:06d}"
        (out / f"app-{stamp}.db").write_text("옛것", encoding="utf-8")
        (out / f"uploads-{stamp}.zip").write_text("옛파일", encoding="utf-8")

    backup.run(db_path=db_path, key_path=tmp_path / "x.pem", uploads=uploads,
               out_dir=out, keep=30)

    assert not (out / "uploads-20260101-000000.zip").exists()
    assert (out / "uploads-20260101-000006.zip").exists()
