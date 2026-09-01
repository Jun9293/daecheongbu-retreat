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


# ════════════════════════════════════════════════════════════════════
#  작업 C — 큰 파일과 링크 첨부 (수용기준 14~27)
# ════════════════════════════════════════════════════════════════════


# ── 14. 상한 ──────────────────────────────────────────────────────────


def test_c14_상한이_200MB_이고_넘으면_이유가_나온다(admin_client, task_data):
    """**숫자에 근거가 있다.** 실제로 올린 가장 큰 것이 164MB 였다."""
    from app import config

    assert config.MAX_ATTACHMENT_BYTES == 200 * 1024 * 1024

    # 화면도 상한을 안다 — 왜 거절당했는지 말할 수 있으려면 필요하다
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    detail = admin_client.get(f"/board/task/{run_id}").json()
    limits = detail["attachment_limits"]
    assert limits["max_bytes"] == config.MAX_ATTACHMENT_BYTES
    assert "200" in limits["max_label"]

    # 164MB 짜리가 들어가는지 — 예전 상한(25MB)이었으면 여기서 막혔다
    assert 164 * 1024 * 1024 < config.MAX_ATTACHMENT_BYTES

    # 넘으면 이유를 말한다
    too_big = b"x" * (config.MAX_ATTACHMENT_BYTES + 1)
    res = upload(admin_client, run_id, "너무큰것.zip", body=too_big)
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "큽니다" in detail and "200" in detail


def test_c14b_실제로_올리는_형식이_전부_열려_있다():
    """이미지 원본 · PDF · PPT — 실제로 오간 것들이다."""
    from app import config

    for ext in (".jpg", ".png", ".tif", ".heic", ".cr2", ".pdf", ".pptx",
                ".psd", ".ai", ".zip", ".mp4", ".mov"):
        assert ext in config.ALLOWED_ATTACHMENT_EXTS, f"{ext} 가 막혀 있다"


# ── 18. 디스크 여유가 없으면 거절한다 ─────────────────────────────────


def test_c18_디스크_여유가_없으면_이유를_말하고_거절한다(
    admin_client, task_data, monkeypatch
):
    """**받아 놓고 나중에 깨지는 것보다 낫다.**

    지금까지는 찰 때까지 받다가 어느 날 아무 설명 없이 실패했다.
    """
    from app import config
    from app.routers import attachments

    # 여유를 흉내 낸다 — 거절선보다 조금 위. 이 파일을 받으면 아래로 내려간다
    monkeypatch.setattr(
        attachments, "disk_free",
        lambda path=None: config.DISK_FREE_FLOOR_BYTES + 1000)

    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    res = upload(admin_client, run_id, "시안.pdf", body=b"x" * 5000)
    assert res.status_code == 507
    detail = res.json()["detail"]
    assert "디스크" in detail and "부족" in detail
    # 얼마가 남았고 이 파일이 얼마인지 함께 말한다 — 그래야 무엇을 할지 안다
    assert "남은 공간" in detail

    # 파일이 남지 않았다
    assert admin_client.get(f"/board/task/{run_id}").json()["attachments"] == []


def test_c18b_여유가_있으면_그대로_올라간다(admin_client, task_data, monkeypatch):
    from app.routers import attachments

    monkeypatch.setattr(attachments, "disk_free", lambda path=None: 500 * 1024 ** 3)
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    assert upload(admin_client, run_id, "시안.pdf", body=b"x" * 5000).status_code == 200


# ── 20. 반쯤 올라간 것을 남기지 않는다 ────────────────────────────────


def test_c20_거절당한_파일은_서버에_남지_않는다(admin_client, task_data):
    """취소·끊김·거절 — 어느 쪽이든 조각을 남기지 않는다.

    취소는 브라우저가 연결을 끊는 것이라 시험에서 그대로 흉내 내기 어렵다.
    같은 자리(스트리밍 도중의 중단)를 지나는 **상한 초과**로 확인한다 —
    조각을 지우는 코드는 하나뿐이라 여기가 곧 거기다.
    """
    from app import config

    before = set(ATTACHMENT_DIR.glob("*"))
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    res = upload(admin_client, run_id, "큰것.zip",
                 body=b"x" * (config.MAX_ATTACHMENT_BYTES + 1))
    assert res.status_code == 400
    assert set(ATTACHMENT_DIR.glob("*")) == before, "반쯤 쓰인 파일이 남았다"


def test_c20b_빈_파일도_조각을_남기지_않는다(admin_client, task_data):
    before = set(ATTACHMENT_DIR.glob("*"))
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    res = upload(admin_client, run_id, "빈것.pdf", body=b"")
    assert res.status_code == 400
    assert set(ATTACHMENT_DIR.glob("*")) == before


# ── 19. 올리는 중 표시 ────────────────────────────────────────────────


def test_c19_올리는_중_진행률과_취소가_목록_맨_위에_있다(admin_client, task_data):
    """164MB 를 올리면 몇 분이 걸린다. 아무 반응이 없으면 창을 닫는다."""
    page = admin_client.get("/board").text
    # 진행 칸이 목록보다 위에 있다
    assert page.index('id="dupnow"') < page.index('id="dfiles"'), "진행 칸이 목록 아래에 있다"

    js = admin_client.get("/static/js/drawer.js").text
    assert "XMLHttpRequest" in js, "fetch 는 올리는 진행률을 주지 않는다"
    assert "xhr.upload.onprogress" in js
    assert "dupcancel" in js and "abort()" in js
    assert "남음" in js, "남은 시간을 말하지 않는다"
    assert "창을 닫지 마세요" in js


# ── 21~26. 링크 첨부 ──────────────────────────────────────────────────


def add_link(client, run_id, url, name):
    return client.post(f"/board/task/{run_id}/links", json={"url": url, "name": name})


def test_c21_링크가_파일과_한_목록에_섞인다(admin_client, task_data):
    """나누면 저건 어디 있더라 를 두 번 찾게 된다."""
    run_id = task_data["runs"]["포스터 제작"]["run_id"]

    upload(admin_client, run_id, "시안.pdf")
    res = add_link(admin_client, run_id, "https://youtube.com/watch?v=abc",
                   "8/21 집회 영상 원본")
    assert res.status_code == 200

    files = admin_client.get(f"/board/task/{run_id}").json()["attachments"]
    assert len(files) == 2
    # **올린 순서로, 최근이 위** — 종류로 묶지 않는다
    assert files[0]["name"] == "8/21 집회 영상 원본"
    assert files[0]["is_link"] is True
    assert files[1]["name"] == "시안.pdf"
    assert files[1]["is_link"] is False


def test_c22_링크가_점선과_화살표로_구분된다(admin_client, task_data):
    """같아 보이면 안 된다 — 링크는 우리 서버에 없어서 지워지거나 권한이
    막히면 안 열리는데, 그건 우리가 어쩔 수 없다."""
    js = admin_client.get("/static/js/drawer.js").text
    assert "fitem link" in js or "' link'" in js
    assert "↗" in js

    css = admin_client.get("/static/css/retreat.css").text
    assert ".fitem.link .ext" in css
    assert "border-style:dashed" in css


def test_c23_둘째_줄에_도메인이_나온다(admin_client, task_data):
    """youtube.com 인지 drive.google.com 인지가 보이면 누를지 말지
    판단이 된다. **전체 주소는 넣지 않는다** — 잘려서 아무 소용이 없다."""
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    long_url = "https://drive.google.com/drive/folders/1aB3xY7ZzQq" + "0" * 60
    add_link(admin_client, run_id, long_url, "교개협 제출용 폴더")

    row = admin_client.get(f"/board/task/{run_id}").json()["attachments"][0]
    assert row["domain"] == "drive.google.com"
    assert row["size_label"] == "drive.google.com", "크기 자리에 도메인이 오지 않았다"
    assert long_url not in row["size_label"]

    # www. 는 떼고 보여준다
    add_link(admin_client, run_id, "https://www.youtube.com/watch?v=x", "영상")
    top = admin_client.get(f"/board/task/{run_id}").json()["attachments"][0]
    assert top["domain"] == "youtube.com"


def test_c24_주소가_아니면_이유와_함께_거절한다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]

    for bad in ("교개협 폴더", "drive.google.com/x", "ftp://x.example.com/a",
                "javascript:alert(1)", ""):
        res = add_link(admin_client, run_id, bad, "설명")
        assert res.status_code == 400, f"{bad!r} 가 통과했다"
        assert "https://" in res.json()["detail"]

    assert admin_client.get(f"/board/task/{run_id}").json()["attachments"] == []
    # http 도 된다 — 사내망 주소가 그렇다
    assert add_link(admin_client, run_id, "http://a.example.com/x", "설명").status_code == 200


def test_c25_설명을_비우면_붙지_않는다(admin_client, task_data):
    """drive.google.com/drive/folders/1aB3xY... 만 보고 아는 사람은 없다."""
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    for blank in ("", "   "):
        res = add_link(admin_client, run_id, "https://drive.google.com/x", blank)
        assert res.status_code == 400
        assert "적어주세요" in res.json()["detail"]
    assert admin_client.get(f"/board/task/{run_id}").json()["attachments"] == []


def test_c26_링크도_회차별이고_누가_언제_넣었는지_남는다(
    admin_client, lead_client, task_data
):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    add_link(admin_client, run_id, "https://youtube.com/x", "영상")

    row = admin_client.get(f"/board/task/{run_id}").json()["attachments"][0]
    assert row["by"], "누가 넣었는지 남지 않았다"
    assert row["at"], "언제 넣었는지 남지 않았다"

    # 회차에 붙는다 (TaskRun) — 파일과 같다
    with app_session() as db:
        link = db.scalars(
            select(models.TaskAttachment).where(models.TaskAttachment.url.is_not(None))
        ).first()
        assert link.run_id == run_id
        assert link.size_bytes == 0, "링크는 용량을 차지하지 않는다"
        assert link.stored_name == "", "링크에는 디스크의 파일이 없다"

    # 붙이는 권한도 파일과 같다 — 총무M 업무에는 스케치 리더가 손댈 수 없다
    other = task_data["runs"]["차량 신청"]["run_id"]
    assert add_link(lead_client, other, "https://a.example.com/x", "설명").status_code == 403


def test_c26b_링크를_지우면_업로드_폴더를_건드리지_않는다(admin_client, task_data):
    """stored_name 이 비어 있어 그냥 이으면 **업로드 폴더 자체**를 가리킨다."""
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    add_link(admin_client, run_id, "https://youtube.com/x", "영상")
    row = admin_client.get(f"/board/task/{run_id}").json()["attachments"][0]

    res = admin_client.post(f"/board/task/{run_id}/files/{row['id']}/delete")
    assert res.status_code == 200
    assert res.json()["files"] == []
    assert ATTACHMENT_DIR.exists(), "업로드 폴더가 통째로 지워졌다"


def test_c26c_링크의_이름은_설명이라_확장자를_붙이지_않는다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    add_link(admin_client, run_id, "https://youtube.com/x", "영상")
    row = admin_client.get(f"/board/task/{run_id}").json()["attachments"][0]

    res = admin_client.post(f"/board/task/{run_id}/files/{row['id']}/rename",
                            json={"name": "8/21 집회 영상"})
    assert res.status_code == 200
    # 파일 이름 규칙(경로 자르기)을 적용하면 "21 집회 영상" 이 된다
    assert res.json()["files"][0]["name"] == "8/21 집회 영상"


def test_c26d_링크는_내려받기가_아니라_원래_주소로_간다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    url = "https://drive.google.com/drive/folders/abc"
    add_link(admin_client, run_id, url, "폴더")
    row = admin_client.get(f"/board/task/{run_id}").json()["attachments"][0]
    assert row["url"] == url, "링크가 내려받기 주소를 가리킨다"

    res = admin_client.get(f"/board/task/{run_id}/files/{row['id']}/download")
    assert res.status_code == 404
    assert "링크" in res.json()["detail"]


# ── 27. 탭 다섯이 넘치지 않는다 ───────────────────────────────────────


def test_c27_탭_이름을_줄여_첨부파일이_잘리지_않는다(admin_client, task_data):
    """드로어 폭(440px)에서 다섯이 넘쳤다. **첨부파일이 맨 끝이라
    잘리면 안 되므로** 줄일 곳은 가운데다."""
    import re

    page = admin_client.get("/board").text
    names = dict(re.findall(r'<button data-p="(\w+)"[^>]*>([^<]*)', page))
    assert names["log"].strip() == "논의", "논의 내역이 줄지 않았다"
    assert names["rel"].strip() == "연결", "연결된 업무가 줄지 않았다"
    assert names["files"].strip() == "첨부파일", "첨부파일 이름은 그대로여야 한다"

    # 맨 끝인지도 함께 본다 — 줄이다가 순서가 바뀌면 안 된다
    order = [page.index(f'data-p="{p}"') for p in ("rules", "log", "cal", "rel", "files")]
    assert order == sorted(order)

    # 글자 수 합이 줄었는지 (드로어 폭에 들어가는가의 대용)
    total = sum(len(names[p].strip()) for p in ("rules", "log", "cal", "rel", "files"))
    assert total <= 16, f"탭 이름이 아직 길다 ({total}자)"


# ── 15~16. 백업이 감당한다 ────────────────────────────────────────────


def test_c15_바뀐_것만_복사한다(tmp_path):
    """200MB 짜리가 몇 개만 쌓여도 매일 새벽 그만큼을 복사한다.

    올라온 파일은 대개 그대로다 — 첨부는 임의의 이름으로 저장되므로
    덮어쓰이지 않고, 지우는 것만 사람이 한다.

    **날짜를 직접 주고 부른다.** run() 은 지금 시각으로 이름을 짓는데,
    시험에서 두 번 부르면 같은 초에 들어가 같은 이름이 된다 — 그러면
    "다시 묶었는가" 를 이름으로 구별할 수 없다.
    """
    import zipfile

    from scripts import backup

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "big.bin").write_bytes(b"x" * 200_000)
    out = tmp_path / "backups"

    first, fresh1 = backup.copy_uploads(uploads, out, stamp="20260101-000001")
    assert fresh1 is True, "첫 번은 새로 묶어야 한다"

    # 바뀐 것이 없으면 다시 묶지 않는다
    second, fresh2 = backup.copy_uploads(uploads, out, stamp="20260101-000002")
    assert fresh2 is False, "안 바뀌었는데 또 묶었다"
    assert second.exists(), "그래도 그 날짜의 zip 은 있어야 한다"
    assert second.name != first.name

    # 되돌리는 절차가 그대로다 — 같은 날짜의 zip 을 풀면 같은 내용이 나온다
    with zipfile.ZipFile(second) as z:
        assert z.read("big.bin") == b"x" * 200_000

    # **실제로 차지하는 크기는 한 벌뿐이다** (하드링크가 되는 곳에서).
    # 그냥 더하면 바뀌지 않은 업로드가 30번 세어져 멀쩡한 백업을 지운다.
    assert backup.disk_used([first, second]) == first.stat().st_size

    # 파일이 바뀌면 다시 묶는다
    (uploads / "new.bin").write_bytes(b"y" * 100)
    third, fresh3 = backup.copy_uploads(uploads, out, stamp="20260101-000003")
    assert fresh3 is True, "바뀌었는데 다시 묶지 않았다"
    with zipfile.ZipFile(third) as z:
        assert set(z.namelist()) == {"big.bin", "new.bin"}


def test_c15b_같은_초에_두_번_돌아도_깨지지_않는다(tmp_path):
    """작업 스케줄러가 겹쳐 부르는 일이 있다. 자기 자신에게 링크를 걸 수는 없다."""
    from scripts import backup

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "a.txt").write_text("가", encoding="utf-8")
    out = tmp_path / "backups"

    backup.copy_uploads(uploads, out, stamp="20260101-000001")
    again, fresh = backup.copy_uploads(uploads, out, stamp="20260101-000001")
    assert again.exists() and fresh is False


def test_c15c_run_도_같은_길로_묶는다(tmp_path):
    """실제로 부르는 것은 run() 이다 — 그 길도 지나가 본다."""
    import sqlite3

    from scripts import backup

    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "a.txt").write_text("가", encoding="utf-8")

    result = backup.run(db_path=db_path, key_path=tmp_path / "x.pem",
                        uploads=uploads, out_dir=tmp_path / "backups")
    assert result["ok"] and result["uploads"] is not None
    assert result["uploads_fresh"] is True


def test_c16_총합이_기준을_넘으면_오래된_것부터_지운다(tmp_path):
    """개수만 보면 200MB 짜리가 들어온 뒤로 디스크가 조용히 찬다."""
    import sqlite3

    from scripts import backup

    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()
    out = tmp_path / "backups"
    out.mkdir()

    # 개수는 30 이하지만 총합이 크다
    for i in range(10):
        stamp = f"20260101-{i:06d}"
        (out / f"app-{stamp}.db").write_bytes(b"x" * 100_000)

    backup.run(db_path=db_path, key_path=tmp_path / "x.pem",
               uploads=tmp_path / "없음", out_dir=out,
               keep=30, max_total=300_000)

    left = sorted(backup.stamps_in(out))
    assert len(left) < 11, "크기 기준이 걸리지 않았다"
    assert backup.disk_used(
        path for s in left for path in backup.files_of(out, s)) <= 300_000
    # 오래된 것부터 지웠다 — 방금 만든 것은 남아 있다
    assert left[-1] > "20260101-000009"


def test_c16b_크기_때문에_백업이_하나도_없게_되지는_않는다(tmp_path):
    """디스크가 차는 것보다 백업이 없는 것이 나쁘다."""
    import sqlite3

    from scripts import backup

    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (a TEXT)")
    conn.commit()
    conn.close()
    out = tmp_path / "backups"

    result = backup.run(db_path=db_path, key_path=tmp_path / "x.pem",
                        uploads=tmp_path / "없음", out_dir=out,
                        keep=30, max_total=1)
    assert result["ok"]
    assert len(backup.stamps_in(out)) == 1, "마지막 하나까지 지웠다"


def test_c16c_백업_크기를_찍는다(tmp_path):
    """안 찍으면 어느 날 갑자기 디스크가 차 있다."""
    import sqlite3

    from scripts import backup

    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()
    result = backup.run(db_path=db_path, key_path=tmp_path / "x.pem",
                        uploads=tmp_path / "없음", out_dir=tmp_path / "backups")
    assert result["size"] > 0
    assert result["total"] >= result["size"]
    assert "이번 백업" in open("scripts/backup.py", encoding="utf-8").read()


# ── 17. 자가진단이 디스크 여유를 본다 ─────────────────────────────────


def test_c17_자가진단이_디스크_여유를_보여준다(monkeypatch, tmp_path):
    """여유를 흉내 내서 시험한다 — 진짜 디스크를 채울 수는 없다."""
    import collections
    import shutil

    from scripts import healthcheck

    Usage = collections.namedtuple("Usage", "total used free")

    def fake(free_gb):
        return lambda path: Usage(2000 * 1024 ** 3, 0, int(free_gb * 1024 ** 3))

    # 넉넉하면 [정상]
    monkeypatch.setattr(shutil, "disk_usage", fake(500))
    ok, message = healthcheck.check_disk()
    assert ok is True
    assert "남은 공간" in message and "올라온 파일" in message

    # 경고선 아래면 [문제] — 거절이 시작되기 전에 알아야 한다
    monkeypatch.setattr(shutil, "disk_usage", fake(3))
    ok, message = healthcheck.check_disk()
    assert ok is False
    assert "막힙니다" in message

    # 거절선 아래면 지금 막힌다고 말한다
    monkeypatch.setattr(shutil, "disk_usage", fake(1))
    ok, message = healthcheck.check_disk()
    assert ok is False
    assert "거절됩니다" in message


def test_c17b_자가진단_목록에_들어가_있다():
    source = open("scripts/healthcheck.py", encoding="utf-8").read()
    assert '("디스크 여유", check_disk())' in source


# ════════════════════════════════════════════════════════════════════
#  리뷰에서 나온 것 — 수용기준 8~11 · 13
# ════════════════════════════════════════════════════════════════════

import pathlib as _pathlib

DRAWER_JS = (_pathlib.Path(__file__).resolve().parent.parent
             / "app" / "static" / "js" / "drawer.js")


# ── 8 · 9. 보내기 전에 크기를 본다 ────────────────────────────────────


def test_r08_상한을_넘으면_보내기_전에_거절한다(admin_client, task_data):
    """**서버까지 갔다 오면 이유가 도착하지 못한다.**

    서버는 본문을 읽는 도중에 400 으로 답하는데, 클라이언트가 아직 보내는
    중이면 XHR 이 `onerror` 로 떨어져서 "파일이 너무 큽니다" 가 화면에 닿지
    않는다 — 사람은 몇 분을 기다린 끝에 "연결이 끊겼습니다" 만 본다.
    """
    js = DRAWER_JS.read_text(encoding="utf-8")
    assert "function preflight(" in js
    body = js[js.index("function preflight("):]
    body = body[: body.index("\n}")]
    assert "file.size > limits.max_bytes" in body
    assert "too-big" in body

    # 보내기 전에 부른다 — putFile 보다 앞이어야 뜻이 있다
    send = js[js.index("async function sendFiles("):]
    send = send[: send.index("\n}")]
    assert send.index("preflight(file)") < send.index("putFile(cur, file)")

    # 화면이 상한을 알고 있다 (그래야 보내기 전에 볼 수 있다)
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    limits = admin_client.get(f"/board/task/{run_id}").json()["attachment_limits"]
    assert limits["max_bytes"] > 0 and limits["max_label"]


def test_r09_터널_한계를_넘으면_경고하되_막지_않는다(admin_client, task_data):
    """집 안 회선에서는 올라간다 — 서버가 있는 곳에서 올리면 되는 것을
    못 하게 만들면 안 된다. **막는 선이 아니라 알려 주는 선**이다."""
    from app import config

    assert config.TUNNEL_MAX_BYTES == 95 * 1024 * 1024
    assert config.TUNNEL_MAX_BYTES < config.MAX_ATTACHMENT_BYTES, (
        "경고선이 상한보다 크면 경고가 뜰 일이 없다")

    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    limits = admin_client.get(f"/board/task/{run_id}").json()["attachment_limits"]
    assert limits["tunnel_max_bytes"] == config.TUNNEL_MAX_BYTES
    assert limits["tunnel_max_label"]

    js = DRAWER_JS.read_text(encoding="utf-8")
    body = js[js.index("function preflight("):]
    body = body[: body.index("\n}")]
    assert "tunnel_max_bytes" in body
    # 경고이지 거절이 아니다 — preflight 는 'tunnel' 을 돌려주고 sendFiles 가 묻는다
    send = js[js.index("async function sendFiles("):]
    send = send[: send.index("\n\n")]
    assert "confirm(" in send, "묻지 않고 막고 있다"
    assert "그래도 올려 보시겠습니까" in send


def test_r09b_안내_문구가_상한과_같은_숫자를_말한다(admin_client, task_data):
    """글에 숫자를 박아 두면 상한을 바꿨을 때 화면이 조용히 거짓말을 한다."""
    page = admin_client.get("/board").text
    assert 'id="dfilenote"' in page, "문구를 고쳐 쓸 자리가 없다"

    js = DRAWER_JS.read_text(encoding="utf-8")
    assert "limits.tunnel_max_label" in js
    # 숫자를 코드에 박아 두지 않았는지
    assert "95MB" not in js and "100MB" not in js


# ── 10 · 11. 첨부 삭제 ────────────────────────────────────────────────


def test_r10_파일을_못_지워도_기록이_남고_500_이_나지_않는다(
    admin_client, task_data, monkeypatch
):
    """윈도우에서는 누가 내려받는 중이면 파일이 잠긴다. 지우기를 먼저 하면
    그때 DB 행은 이미 사라졌는데 500 이 나가고 활동 기록도 안 남는다 —
    **무엇이 없어졌는지 아무도 모른다.**"""
    from app.routers import attachments

    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    upload(admin_client, run_id, "잠긴시안.pdf")
    row = admin_client.get(f"/board/task/{run_id}").json()["attachments"][0]

    # 파일이 잠긴 상황을 흉내 낸다
    real = _pathlib.Path.unlink

    def locked(self, *args, **kw):
        if self.suffix == ".pdf":
            raise PermissionError(32, "다른 프로세스가 사용 중")
        return real(self, *args, **kw)

    monkeypatch.setattr(_pathlib.Path, "unlink", locked)

    res = admin_client.post(f"/board/task/{run_id}/files/{row['id']}/delete")
    assert res.status_code == 200, "파일을 못 지웠다고 500 이 났다"
    assert res.json()["files"] == [], "목록에서는 사라져야 한다"

    # 활동 기록이 남았는가 — 무엇이 없어졌는지 알 수 있어야 한다
    with app_session() as db:
        logs = list(db.scalars(
            select(models.ActivityLog).where(models.ActivityLog.action == "첨부 삭제")))
        assert logs, "활동 기록이 남지 않았다"


def test_r11_못_지운_파일이_로그에_남는다(admin_client, task_data, monkeypatch, caplog):
    """조용히 삼키지 않는다. 디스크에 남은 것은 나중에 누군가 치워야 한다."""
    import logging

    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    upload(admin_client, run_id, "잠긴시안2.pdf")
    row = admin_client.get(f"/board/task/{run_id}").json()["attachments"][0]

    real = _pathlib.Path.unlink

    def locked(self, *args, **kw):
        if self.suffix == ".pdf":
            raise PermissionError(32, "다른 프로세스가 사용 중")
        return real(self, *args, **kw)

    monkeypatch.setattr(_pathlib.Path, "unlink", locked)

    with caplog.at_level(logging.WARNING, logger="app.routers.attachments"):
        admin_client.post(f"/board/task/{run_id}/files/{row['id']}/delete")

    said = [r.getMessage() for r in caplog.records]
    assert any("지우지 못했습니다" in one for one in said), \
        f"못 지운 것이 로그에 없다: {said}"
    # **무엇을** 못 지웠는지가 있어야 나중에 누가 치울 수 있다
    assert any("잠긴시안2.pdf" in one for one in said), \
        f"무엇을 못 지웠는지가 로그에 없다: {said}"


def test_r10b_기록이_지우기보다_먼저다():
    """순서가 이 시험의 전부다 — 지우기가 앞서면 실패했을 때 기록이 안 남는다."""
    source = open("app/routers/attachments.py", encoding="utf-8").read()
    body = source[source.index('@router.post("/board/task/{run_id}/files/{attachment_id}/delete")'):]
    body = body[: body.index("@router.get")]
    assert body.index("log_activity(") < body.index("path.unlink()"), \
        "파일 지우기가 활동 기록보다 앞에 있다"


# ── 13. 확장자 ────────────────────────────────────────────────────────


def test_r13_확장자_없는_이름으로_바꿔도_점이_두_개가_되지_않는다(
    admin_client, task_data
):
    """`ext` 는 점을 품지 않으므로(models 의 rpartition) `보고서..pdf` 는
    원래 나지 않았다. 그래도 붙이는 쪽에서 막아 둔다 — 그쪽이 바뀌면 난다."""
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    upload(admin_client, run_id, "시안.pdf")
    row = admin_client.get(f"/board/task/{run_id}").json()["attachments"][0]

    res = admin_client.post(f"/board/task/{run_id}/files/{row['id']}/rename",
                            json={"name": "보고서"})
    assert res.status_code == 200
    assert res.json()["files"][0]["name"] == "보고서.pdf"
    assert ".." not in res.json()["files"][0]["name"]


def test_r13b_끝에_점을_찍으면_확장자가_사라지던_것을_막는다(
    admin_client, task_data
):
    """**이건 진짜로 있던 문제다.** `Path("보고서.").suffix` 는 빈 문자열이
    아니라 `"."` 이라, "확장자가 있다" 로 읽혀 되붙이기를 건너뛰었다 —
    `시안.pdf` 를 `보고서.` 로 바꾸면 확장자가 조용히 사라졌다."""
    from pathlib import Path as _P

    assert _P("보고서.").suffix == ".", "전제가 바뀌었다 — 이 시험을 다시 보라"

    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    upload(admin_client, run_id, "시안.pdf")
    row = admin_client.get(f"/board/task/{run_id}").json()["attachments"][0]

    res = admin_client.post(f"/board/task/{run_id}/files/{row['id']}/rename",
                            json={"name": "보고서."})
    assert res.status_code == 200
    saved = res.json()["files"][0]["name"]
    assert saved == "보고서.pdf", f"확장자가 사라졌다: {saved!r}"


def test_r13c_점만_적으면_거절한다(admin_client, task_data):
    run_id = task_data["runs"]["포스터 제작"]["run_id"]
    upload(admin_client, run_id, "시안.pdf")
    row = admin_client.get(f"/board/task/{run_id}").json()["attachments"][0]

    res = admin_client.post(f"/board/task/{run_id}/files/{row['id']}/rename",
                            json={"name": "  ..  "})
    assert res.status_code == 400


# ── 6(d). 디스크 다시 보기를 조각 크기에 기대지 않는다 ────────────────


def test_r6d_디스크_다시_보기를_나머지_연산으로_세지_않는다():
    """`size % 간격 < 조각크기` 는 조각이 딱 1MB 로 올 때만 맞는다.
    조각 크기는 클라이언트와 서버 사정에 따라 달라진다."""
    source = open("app/routers/attachments.py", encoding="utf-8").read()
    assert "size % DISK_RECHECK_BYTES" not in source
    assert "next_check" in source
    assert "if size >= next_check:" in source
