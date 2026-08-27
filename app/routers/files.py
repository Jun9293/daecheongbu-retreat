"""부서별 작업 파일 — 업로드, 버전 이력, 검토 상태."""

from __future__ import annotations

import datetime as dt
import secrets
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import ALLOWED_ASSET_EXTS, MAX_ASSET_BYTES, UPLOAD_DIR
from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.models import (
    FILE_STATUSES,
    Department,
    FileAsset,
    FileVersion,
    Retreat,
    Task,
    User,
)
from app.routers.reviews import create_review_requests
from app.security import assert_can_edit_department, get_current_user, require_editor
from app.templating import redirect, render

router = APIRouter()

ASSET_DIR = UPLOAD_DIR / "assets"
ASSET_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _store_upload(file: UploadFile) -> tuple[str, int]:
    """업로드 파일을 저장하고 (저장파일명, 크기)를 돌려준다."""
    if file is None or not file.filename:
        raise HTTPException(status_code=400, detail="파일을 선택해주세요.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_ASSET_EXTS:
        raise HTTPException(
            status_code=400, detail=f"허용되지 않는 파일 형식입니다: {ext or '(확장자 없음)'}"
        )
    data = file.file.read()
    if len(data) > MAX_ASSET_BYTES:
        limit_mb = MAX_ASSET_BYTES // (1024 * 1024)
        raise HTTPException(status_code=400, detail=f"파일은 {limit_mb}MB 이하만 올릴 수 있습니다.")
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일은 올릴 수 없습니다.")

    stored_name = f"{secrets.token_hex(12)}{ext}"
    (ASSET_DIR / stored_name).write_bytes(data)
    return stored_name, len(data)


def _owned_asset(db: Session, asset_id: int, retreat: Retreat) -> FileAsset:
    asset = db.get(FileAsset, asset_id)
    if asset is None or asset.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return asset


@router.get("/files")
def file_list(
    request: Request,
    department_id: int | None = None,
    status: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    query = select(FileAsset).where(FileAsset.retreat_id == retreat.id)
    if department_id:
        query = query.where(FileAsset.department_id == department_id)
    if status:
        query = query.where(FileAsset.status == status)

    assets = list(db.scalars(query.order_by(FileAsset.updated_at.desc(), FileAsset.id.desc())))

    return render(
        request,
        "files.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "assets": assets,
            "departments": list(
                db.scalars(
                    select(Department)
                    .where(Department.retreat_id == retreat.id)
                    .order_by(Department.sort_order, Department.id)
                )
            ),
            "tasks": list(
                db.scalars(
                    select(Task)
                    .where(Task.retreat_id == retreat.id)
                    .order_by(Task.id.desc())
                )
            ),
            "statuses": FILE_STATUSES,
            "filters": {"department_id": department_id, "status": status},
        },
    )


@router.post("/files/create")
def create_file(
    title: str = Form(...),
    description: str = Form(""),
    department_id: str = Form(""),
    task_id: str = Form(""),
    note: str = Form(""),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    dept_id = int(department_id) if department_id else None
    assert_can_edit_department(user, dept_id)

    stored_name, size = _store_upload(upload)

    asset = FileAsset(
        retreat_id=retreat.id,
        department_id=dept_id,
        task_id=int(task_id) if task_id else None,
        title=title.strip(),
        description=description.strip() or None,
        status="작업중",
        created_by_id=user.id,
    )
    db.add(asset)
    db.flush()

    db.add(
        FileVersion(
            file_asset_id=asset.id,
            version_no=1,
            original_name=upload.filename,
            stored_name=stored_name,
            size_bytes=size,
            note=note.strip() or None,
            uploaded_by_id=user.id,
            uploaded_by_name=user.name,
        )
    )
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="파일_등록",
        target_type="file",
        target_id=asset.id,
        summary=f"{asset.title} (v1)",
    )
    return redirect(f"/files?retreat_id={retreat.id}", message="파일을 등록했습니다.")


@router.post("/files/{asset_id}/versions")
def add_version(
    asset_id: int,
    note: str = Form(""),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    asset = _owned_asset(db, asset_id, retreat)
    assert_can_edit_department(user, asset.department_id)

    stored_name, size = _store_upload(upload)
    next_no = (
        db.scalar(
            select(func.max(FileVersion.version_no)).where(
                FileVersion.file_asset_id == asset.id
            )
        )
        or 0
    ) + 1

    db.add(
        FileVersion(
            file_asset_id=asset.id,
            version_no=next_no,
            original_name=upload.filename,
            stored_name=stored_name,
            size_bytes=size,
            note=note.strip() or None,
            uploaded_by_id=user.id,
            uploaded_by_name=user.name,
        )
    )
    # 새 버전이 올라오면 이전 승인/반려 결과는 무효 — 다시 작업중으로 되돌린다
    if asset.status in ("승인", "반려"):
        asset.status = "작업중"
    asset.updated_at = _now()
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="파일_새버전",
        target_type="file",
        target_id=asset.id,
        summary=f"{asset.title} (v{next_no})",
    )
    return redirect(f"/files?retreat_id={retreat.id}", message=f"v{next_no} 을 올렸습니다.")


@router.post("/files/{asset_id}/status")
def change_status(
    asset_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    asset = _owned_asset(db, asset_id, retreat)
    assert_can_edit_department(user, asset.department_id)
    if status not in FILE_STATUSES:
        raise HTTPException(status_code=400, detail="알 수 없는 상태입니다.")

    before = asset.status
    asset.status = status
    asset.updated_at = _now()
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="파일_상태변경",
        target_type="file",
        target_id=asset.id,
        summary=f"{asset.title}: {before} → {status}",
    )
    return redirect(f"/files?retreat_id={retreat.id}", message="상태를 변경했습니다.")


@router.post("/files/{asset_id}/review-request")
def request_review(
    asset_id: int,
    department_ids: list[int] = Form(default=[]),
    message: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    asset = _owned_asset(db, asset_id, retreat)
    assert_can_edit_department(user, asset.department_id)
    if not department_ids:
        return redirect(
            f"/files?retreat_id={retreat.id}", message="확인을 요청할 부서를 선택해주세요."
        )

    created = create_review_requests(
        db,
        retreat=retreat,
        requester=user,
        department_ids=department_ids,
        message=message,
        file_asset=asset,
    )
    asset.status = "검토요청"
    asset.updated_at = _now()
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="파일_확인요청",
        target_type="file",
        target_id=asset.id,
        summary=f"{asset.title} → {len(created)}개 부서",
    )
    return redirect(
        f"/files?retreat_id={retreat.id}", message=f"{len(created)}개 부서에 확인을 요청했습니다."
    )


@router.get("/files/{asset_id}/download/{version_no}")
def download(
    asset_id: int,
    version_no: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    asset = _owned_asset(db, asset_id, retreat)
    version = db.scalars(
        select(FileVersion).where(
            FileVersion.file_asset_id == asset.id, FileVersion.version_no == version_no
        )
    ).first()
    if version is None:
        raise HTTPException(status_code=404, detail="해당 버전을 찾을 수 없습니다.")

    path = ASSET_DIR / version.stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="파일이 서버에 없습니다.")

    quoted = urllib.parse.quote(version.original_name)
    return FileResponse(
        path,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )


@router.post("/files/{asset_id}/delete")
def delete_file(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
    retreat: Retreat = Depends(get_current_retreat),
):
    asset = _owned_asset(db, asset_id, retreat)
    assert_can_edit_department(user, asset.department_id)

    title = asset.title
    for version in asset.versions:
        stored = ASSET_DIR / version.stored_name
        if stored.exists():
            stored.unlink()
    db.delete(asset)
    db.commit()

    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="파일_삭제",
        target_type="file",
        target_id=asset_id,
        summary=title,
    )
    return redirect(f"/files?retreat_id={retreat.id}", message="파일을 삭제했습니다.")
