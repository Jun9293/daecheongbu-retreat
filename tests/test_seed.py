"""데모 데이터 무결성 테스트.

데모 데이터가 "있다고 주장하는 것"은 실제로 있어야 한다.
없는 파일을 가리키는 버전 기록이 남으면 내려받기가 404가 나고,
화면에는 존재하지 않는 파일 크기가 표시된다.
"""

from sqlalchemy import select

from app import models
from tests.conftest import app_session, login_as


def _seed(client):
    """빈 DB(client 픽스처) 위에 데모 데이터를 만든다."""
    import seed as seed_module

    seed_module.seed()


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
    login_as(client, "01011112222")

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
    login_as(client, "01011112222")

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
    login_as(client, "01011112222")

    with app_session() as db:
        asset = db.scalars(select(models.FileAsset)).first()
        asset_id = asset.id

    response = client.post(f"/files/{asset_id}/delete", follow_redirects=True)

    assert response.status_code == 200
    with app_session() as db:
        assert db.get(models.FileAsset, asset_id) is None
