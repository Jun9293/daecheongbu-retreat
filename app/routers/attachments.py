"""업무 첨부파일 (CLAUDE.md 4-9).

**회차별이다.** TaskRun 에 붙으므로 새 회차를 열 때 업무는 따라와도 파일은
따라오지 않는다. 논의 내역과 같은 취급이고, 업무 규칙(라이브러리)과 다르다.

권한은 **그 업무를 고칠 수 있는 사람과 같다.** 부서는 `key` 로 비교한다
(CLAUDE.md 2장) — `Department.id` 로 비교하면 새 회차가 열리는 순간 모든 부서
리더가 자기 부서 업무에도 파일을 못 올린다. 보는 것은 회차를 볼 수 있는
누구나 된다 — 논의 내역과 같은 범위다.
"""

from __future__ import annotations

import datetime as dt
import secrets
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import ALLOWED_ATTACHMENT_EXTS, ATTACHMENT_DIR, MAX_ATTACHMENT_BYTES
from app.db import get_db
from app.deps import get_current_retreat, log_activity
from app.domain import permissions as perm
from app.domain.departments import department_key_of
from app.models import Retreat, TaskAttachment, TaskRun, User
from app.security import get_current_user

router = APIRouter()


def _now() -> dt.datetime:
    """**벽시계 시각으로 남긴다.** 화면에 "2026-09-01 에 올림" 으로 보이는 값이라
    UTC 로 남기면 자정부터 아침 9시 사이에 올린 파일이 하루 전으로 보인다 —
    한국에서만 쓰는 시스템이고, 사람이 보는 것은 방금 그 시각이다.
    수련회 진행 화면(`routers/live.py`)의 체크 시각과 같은 기준이다."""
    return dt.datetime.now()


def _load_run(db: Session, retreat: Retreat, run_id: int) -> TaskRun:
    run = db.get(TaskRun, run_id)
    if run is None or run.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다.")
    return run


def _can_edit(db: Session, user: User, run: TaskRun) -> bool:
    return perm.can_edit_department_by_key(
        role=user.role,
        user_department_key=department_key_of(db, user),
        target_department_key=run.department.key if run.department else None,
    )


def _require_edit(db: Session, user: User, run: TaskRun) -> None:
    if not _can_edit(db, user, run):
        raise HTTPException(status_code=403, detail="내 부서의 업무에만 파일을 올릴 수 있습니다.")


def _human(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}MB"
    if size >= 1024:
        return f"{size / 1024:.0f}KB"
    return f"{size}B"


def view(attachment: TaskAttachment, *, can_edit: bool) -> dict:
    return {
        "id": attachment.id,
        "name": attachment.original_name,
        "ext": attachment.ext,
        "size": attachment.size_bytes,
        "size_label": _human(attachment.size_bytes),
        "by": attachment.uploaded_by_name or "",
        "at": attachment.uploaded_at.strftime("%Y-%m-%d"),
        "url": f"/board/task/{attachment.run_id}/files/{attachment.id}/download",
        "can_edit": can_edit,
    }


def serialize(db: Session, user: User, run: TaskRun) -> list[dict]:
    """상세 패널이 한 번에 받아 가도록 board.py 에서도 쓴다."""
    can_edit = _can_edit(db, user, run)
    return [view(a, can_edit=can_edit) for a in run.attachments]


def limits() -> dict:
    """왜 거절당했는지 말할 수 있으려면 화면도 상한을 알아야 한다."""
    return {
        "max_bytes": MAX_ATTACHMENT_BYTES,
        "max_label": _human(MAX_ATTACHMENT_BYTES),
        "exts": sorted(ALLOWED_ATTACHMENT_EXTS),
    }


@router.get("/board/task/{run_id}/files")
def list_files(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    run = _load_run(db, retreat, run_id)
    return {"files": serialize(db, user, run), "limits": limits(), "can_edit": _can_edit(db, user, run)}


@router.post("/board/task/{run_id}/files")
async def upload(
    run_id: int,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    run = _load_run(db, retreat, run_id)
    _require_edit(db, user, run)

    if not upload or not upload.filename:
        raise HTTPException(status_code=400, detail="파일을 고르지 않았습니다.")

    # 이름은 표시용으로만 쓴다. 경로 조각이 들어와도 마지막 조각만 남긴다.
    original = Path(upload.filename.replace("\\", "/")).name.strip() or "이름없는파일"
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_ATTACHMENT_EXTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{ext or '확장자 없는 파일'} 은(는) 올릴 수 없습니다. "
                f"올릴 수 있는 형식: {', '.join(sorted(ALLOWED_ATTACHMENT_EXTS))}"
            ),
        )

    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일은 올릴 수 없습니다.")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"파일이 {_human(len(data))} 라 너무 큽니다. "
                f"{_human(MAX_ATTACHMENT_BYTES)} 까지 올릴 수 있습니다."
            ),
        )

    # 올린 이름을 그대로 디스크에 쓰지 않는다 — 경로 조작·중복·한글 인코딩
    stored = f"{secrets.token_hex(16)}{ext}"
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    (ATTACHMENT_DIR / stored).write_bytes(data)

    attachment = TaskAttachment(
        run_id=run.id,
        original_name=original[:300],
        stored_name=stored,
        size_bytes=len(data),
        uploaded_by_id=user.id,
        uploaded_by_name=user.name,
        uploaded_at=_now(),
    )
    db.add(attachment)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="첨부",
        target_type="task_run",
        target_id=run.id,
        after_value={"file": original},
    )
    db.refresh(run)
    return {"files": serialize(db, user, run)}


class RenameIn(BaseModel):
    name: str


@router.post("/board/task/{run_id}/files/{attachment_id}/rename")
def rename(
    run_id: int,
    attachment_id: int,
    payload: RenameIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    run = _load_run(db, retreat, run_id)
    _require_edit(db, user, run)
    attachment = db.get(TaskAttachment, attachment_id)
    if attachment is None or attachment.run_id != run.id:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    # 이름만 바꾼다. 디스크의 파일은 그대로다 — 이름은 표시용일 뿐이다.
    name = Path(payload.name.replace("\\", "/")).name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름을 비울 수 없습니다.")
    # 확장자를 지워 버리면 무슨 파일인지 알 수 없게 되므로 원래 것을 붙여 준다
    if not Path(name).suffix and attachment.ext:
        name = f"{name}.{attachment.ext}"
    attachment.original_name = name[:300]
    db.commit()
    db.refresh(run)
    return {"files": serialize(db, user, run)}


@router.post("/board/task/{run_id}/files/{attachment_id}/delete")
def delete(
    run_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    run = _load_run(db, retreat, run_id)
    _require_edit(db, user, run)
    attachment = db.get(TaskAttachment, attachment_id)
    if attachment is None or attachment.run_id != run.id:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    path = ATTACHMENT_DIR / attachment.stored_name
    name = attachment.original_name
    db.delete(attachment)
    db.commit()
    if path.exists():
        path.unlink()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="첨부 삭제",
        target_type="task_run",
        target_id=run.id,
        before_value={"file": name},
    )
    db.refresh(run)
    return {"files": serialize(db, user, run)}


@router.get("/board/task/{run_id}/files/{attachment_id}/download")
def download(
    run_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    run = _load_run(db, retreat, run_id)
    attachment = db.get(TaskAttachment, attachment_id)
    if attachment is None or attachment.run_id != run.id:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    path = ATTACHMENT_DIR / attachment.stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="파일이 서버에 없습니다.")
    quoted = urllib.parse.quote(attachment.original_name)
    return FileResponse(
        path,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
