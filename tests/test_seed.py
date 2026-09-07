"""데모 데이터 무결성 테스트.

데모 데이터가 "있다고 주장하는 것"은 실제로 있어야 한다.
없는 파일을 가리키는 버전 기록이 남으면 내려받기가 404가 나고,
화면에는 존재하지 않는 파일 크기가 표시된다.
"""

from sqlalchemy import select

from app import models
import seed_data
from tests.conftest import app_session, login_as

# 시드 데이터의 첫 관리자 계정
ADMIN_PHONE = seed_data.USERS[0][1]


def _seed(client):
    """빈 DB(client 픽스처) 위에 데모 데이터를 만든다.

    기본 시드는 실제 이력만 만든다 (계정도 만들지 않는다). 이 파일이 보는 것은
    이전 설계 화면을 눌러보기 위한 demo 데이터라 `demo=True` 로 부른다.
    """
    import seed as seed_module

    seed_module.seed(demo=True)


def test_데모_파일_버전은_실제로_디스크에_존재한다(client):
    _seed(client)

    from app.routers.files import ASSET_DIR

    with app_session() as db:
        versions = list(db.scalars(select(models.FileVersion)))

    assert versions, "데모 파일 버전이 하나도 없습니다."
    missing = [v.stored_name for v in versions if not (ASSET_DIR / v.stored_name).exists()]
    assert missing == [], f"디스크에 없는 데모 파일: {missing}"


def test_데모_파일의_기록된_크기가_실제_크기와_같다(client):
    _seed(client)

    from app.routers.files import ASSET_DIR

    with app_session() as db:
        versions = list(db.scalars(select(models.FileVersion)))

    mismatched = [
        (v.stored_name, v.size_bytes, (ASSET_DIR / v.stored_name).stat().st_size)
        for v in versions
        if (ASSET_DIR / v.stored_name).exists()
        and v.size_bytes != (ASSET_DIR / v.stored_name).stat().st_size
    ]
    assert mismatched == [], f"크기가 실제와 다른 기록: {mismatched}"


def test_데모_파일을_실제로_내려받을_수_있다(client):
    _seed(client)
    login_as(client, ADMIN_PHONE)

    with app_session() as db:
        # 세션 밖에서 lazy load 가 되지 않으므로 필요한 값만 미리 꺼낸다
        targets = [
            (asset.id, asset.title, version.version_no)
            for asset in db.scalars(select(models.FileAsset))
            for version in asset.versions
        ]

    assert targets, "데모 파일이 없습니다."
    for asset_id, title, version_no in targets:
        response = client.get(f"/files/{asset_id}/download/{version_no}")
        assert response.status_code == 200, (
            f"{title} v{version_no} 내려받기 실패 ({response.status_code})"
        )
        assert len(response.content) > 0


def test_데모_파일_버전마다_내용이_다르다(client):
    """v1 과 v2 가 같은 파일을 가리키면 버전 이력이 의미가 없다."""
    _seed(client)
    login_as(client, ADMIN_PHONE)

    with app_session() as db:
        poster = db.scalars(
            select(models.FileAsset).where(models.FileAsset.title == "수련회 포스터")
        ).one()
        version_numbers = sorted(v.version_no for v in poster.versions)

    contents = [
        client.get(f"/files/{poster.id}/download/{no}").content for no in version_numbers
    ]
    assert len(set(contents)) == len(contents), "버전별 파일 내용이 중복됩니다."


def test_데모_파일을_삭제해도_오류가_나지_않는다(client):
    _seed(client)
    login_as(client, ADMIN_PHONE)

    with app_session() as db:
        asset = db.scalars(select(models.FileAsset)).first()
        asset_id = asset.id

    response = client.post(f"/files/{asset_id}/delete", follow_redirects=True)

    assert response.status_code == 200
    with app_session() as db:
        assert db.get(models.FileAsset, asset_id) is None


# ================================================================ 화면 규모


def test_할일_목록이_실제_데이터에서도_가볍게_유지된다(client):
    """선행 작업 선택지를 목록의 매 행마다 그리면 페이지가 수 MB 로 불어난다.

    선택지는 상세 화면에서만 그려야 한다.
    """
    _seed(client)
    login_as(client, ADMIN_PHONE)

    response = client.get("/tasks")

    assert response.status_code == 200
    size = len(response.content)
    assert size < 800_000, f"할 일 목록이 너무 큽니다: {size:,} bytes"
    # 목록에는 선행 작업 체크박스가 없어야 한다
    assert 'name="blocker_ids"' not in response.text


def test_옛_할일_상세_주소는_목록으로_301_이다(client):
    """옛 /tasks/{id} 는 지웠다 (4-14) — 그 id 는 옛 Task 표의 것이라 run 으로
    잇지 못한다. 표와 행은 남는다 (0장 첫 원칙)."""
    _seed(client)
    login_as(client, ADMIN_PHONE)

    with app_session() as db:
        task_id = db.scalars(select(models.Task)).first().id
        before = len(db.scalars(select(models.Task)).all())

    response = client.get(f"/tasks/{task_id}", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "/tasks"
    with app_session() as db:
        assert len(db.scalars(select(models.Task)).all()) == before  # 행은 그대로


def test_모든_주요_화면이_실제_데이터에서_정상_렌더링된다(client):
    _seed(client)
    login_as(client, ADMIN_PHONE)

    # /schedule 은 301 로 /live/staff 에 잇고(14장), /more 는 설정 › 점검이
    # 맡는다 (4-17). TestClient 는 리다이렉트를 따라가므로 /schedule 이 남아
    # 있는 것이 곧 「옛 링크가 살아 있다」 는 검사다.
    paths = [
        "/", "/schedule", "/tasks", "/budget", "/expenses", "/refunds",
        "/settings/retreats", "/notifications", "/reviews", "/files", "/checklists",
        "/meetings", "/settings",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, f"{path} → {response.status_code}"
        assert "Traceback" not in response.text, f"{path} 렌더링 오류"


def test_옛_일정표_주소는_봉사자_시간표로_301_이다(client):
    """옛 /schedule 화면은 지웠다 (14장 「옛 화면 걷어내기」) — 대체 화면은 5-8 봉사자 시간표다.
    표(ScheduleDay·ScheduleItem)와 행은 남는다 (0장 첫 원칙)."""
    _seed(client)
    login_as(client, ADMIN_PHONE)

    response = client.get("/schedule", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/live/staff"

    # 행이 남아 있다 — 화면을 지웠다고 기록을 지우지 않는다
    with app_session() as db:
        assert db.scalars(select(models.ScheduleItem)).first() is not None
