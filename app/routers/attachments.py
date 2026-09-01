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

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import (
    ALLOWED_ATTACHMENT_EXTS,
    ATTACHMENT_DIR,
    DISK_FREE_FLOOR_BYTES,
    MAX_ATTACHMENT_BYTES,
)
from app.db import get_db
from app.deps import get_current_retreat, log_activity
from app.domain import permissions as perm
from app.domain.departments import department_key_of
from app.models import Retreat, TaskAttachment, TaskRun, User
from app.security import get_current_user

router = APIRouter()


# 한 번에 읽는 조각. 너무 작으면 200MB 에 조각이 수만 개가 되고,
# 너무 크면 메모리가 그만큼 튄다.
CHUNK_BYTES = 1024 * 1024
# 받는 동안 디스크를 다시 보는 간격
DISK_RECHECK_BYTES = 32 * 1024 * 1024


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


# ── 디스크가 조용히 차지 않게 한다 ───────────────────────────────
#
# 상한을 200MB 로 올린 순간 이것이 현실이 된다. 지금까지는 찰 때까지 받다가
# **어느 날 아무 설명 없이** 실패했다. 받아 놓고 나중에 깨지는 것보다
# 이유를 말하고 거절하는 편이 낫다.


def disk_free(path: Path | None = None) -> int:
    """업로드 폴더가 있는 디스크의 남은 공간(바이트)."""
    import shutil as _shutil

    target = path or ATTACHMENT_DIR
    target.mkdir(parents=True, exist_ok=True)
    return _shutil.disk_usage(target).free


def _require_disk(incoming: int) -> None:
    """받고 나서도 최소한의 여유가 남는지 본다.

    **여유를 왜 못 받는지 말한다.** "실패했습니다" 만으로는 파일이 큰 건지
    서버가 이상한 건지 알 수 없어서 사람이 같은 파일을 몇 번씩 다시 올린다.
    """
    free = disk_free()
    if free - incoming >= DISK_FREE_FLOOR_BYTES:
        return
    raise HTTPException(
        status_code=507,
        detail=(
            f"서버 디스크가 부족해 받을 수 없습니다 — 남은 공간 {_human(free)}, "
            f"이 파일 {_human(incoming)}. "
            f"최소 {_human(DISK_FREE_FLOOR_BYTES)} 는 남겨 두어야 합니다. "
            "총무팀에 알려 주세요."
        ),
    )


def view(attachment: TaskAttachment, *, can_edit: bool) -> dict:
    """목록의 한 줄. **파일과 링크가 같은 모양으로 나간다.**

    화면이 둘을 갈라 놓지 않고 한 목록에 섞어 그리므로(4-9), 구조도 갈라
    두지 않는다. 다른 것은 `is_link` 와 그때만 채워지는 `domain` 뿐이다.
    """
    link = attachment.is_link
    return {
        "id": attachment.id,
        "name": attachment.original_name,
        "ext": attachment.ext,
        "size": attachment.size_bytes,
        # 링크는 용량을 차지하지 않는다. 크기 자리에 도메인을 낸다 —
        # 어디로 가는 링크인지가 보여야 누를지 말지 판단이 된다
        "size_label": attachment.domain if link else _human(attachment.size_bytes),
        "is_link": link,
        "domain": attachment.domain,
        "by": attachment.uploaded_by_name or "",
        "at": attachment.uploaded_at.strftime("%Y-%m-%d"),
        "url": attachment.url if link
        else f"/board/task/{attachment.run_id}/files/{attachment.id}/download",
        "can_edit": can_edit,
    }


def serialize(db: Session, user: User, run: TaskRun) -> list[dict]:
    """상세 패널이 한 번에 받아 가도록 board.py 에서도 쓴다.

    **파일·링크 구분 없이 올린 순서로, 최근이 위다** (4-9). 종류로 묶으면
    같은 업무의 자료가 두 덩어리로 갈려 "저건 어디 있더라" 를 두 번 찾는다.
    """
    can_edit = _can_edit(db, user, run)
    rows = sorted(run.attachments, key=lambda a: (a.uploaded_at, a.id), reverse=True)
    return [view(a, can_edit=can_edit) for a in rows]


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
    request: Request,
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

    # ── 조각을 받아 바로 디스크에 쓴다 ────────────────────────────────
    #
    # 200MB 를 통째로 메모리에 올리지 않는다. 그리고 **중간에 끊기면 반쯤
    # 올라간 것을 남기지 않는다** — 사람이 취소를 누르면 브라우저가 연결을
    # 끊는데, 그때 남은 조각이 디스크에 쌓이면 아무도 그것을 지우지 않는다.
    #
    # 올린 이름을 그대로 디스크에 쓰지 않는다 — 경로 조작·중복·한글 인코딩
    stored = f"{secrets.token_hex(16)}{ext}"
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    path = ATTACHMENT_DIR / stored

    # 받기 전에 한 번 물어본다. 여기서 걸러 내면 200MB 를 다 받고 나서
    # 거절하는 일이 없다. Content-Length 를 못 믿으므로 받는 동안 또 본다.
    declared = int(request.headers.get("content-length") or 0)
    if declared:
        _require_disk(min(declared, MAX_ATTACHMENT_BYTES))

    size = 0
    try:
        with path.open("wb") as out:
            while chunk := await upload.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_ATTACHMENT_BYTES:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"파일이 너무 큽니다. "
                            f"{_human(MAX_ATTACHMENT_BYTES)} 까지 올릴 수 있습니다."
                        ),
                    )
                # 받는 동안에도 여유를 본다. 미리 본 값은 짐작일 뿐이고,
                # 같은 시각에 다른 사람이 올리고 있을 수도 있다.
                if size % DISK_RECHECK_BYTES < CHUNK_BYTES:
                    _require_disk(0)
                out.write(chunk)
        if not size:
            raise HTTPException(status_code=400, detail="빈 파일은 올릴 수 없습니다.")
    except BaseException:
        # 취소·끊김·거절 — 어느 쪽이든 반쯤 쓰인 파일을 남기지 않는다.
        # ClientDisconnect 는 HTTPException 이 아니므로 BaseException 으로 받는다.
        path.unlink(missing_ok=True)
        raise

    attachment = TaskAttachment(
        run_id=run.id,
        original_name=original[:300],
        stored_name=stored,
        size_bytes=size,
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


class LinkIn(BaseModel):
    url: str
    name: str


NOT_A_URL = "주소가 아닙니다. https:// 로 시작하는 주소를 넣어주세요."
NEEDS_NAME = (
    "무엇인지 적어주세요. 이 목록만 보고도 알 수 있게 적어야 합니다 — "
    "주소만 있으면 나중에 아무도 열지 않습니다."
)


@router.post("/board/task/{run_id}/links")
def add_link(
    run_id: int,
    payload: LinkIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """링크를 붙인다 (CLAUDE.md 4-9).

    **파일과 같은 목록에 들어간다.** 담당자에게는 둘 다 그냥 자료이고,
    나누면 "저건 어디 있더라" 를 두 번 찾게 된다. 다만 링크는 우리 서버에
    없어서 지워지거나 권한이 막히면 안 열리는데 우리가 어쩔 수 없으므로,
    그 차이는 화면에서 점선으로 보인다.

    권한·회차 규칙은 파일과 같다. 용량은 차지하지 않으므로 상한과
    디스크 검사는 지나가지 않는다.
    """
    run = _load_run(db, retreat, run_id)
    _require_edit(db, user, run)

    raw = (payload.url or "").strip()
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail=NOT_A_URL)

    # **설명을 비워 둘 수 없다.** `drive.google.com/drive/folders/1aB3xY...`
    # 만 보고 아는 사람은 없다 — 그런 링크는 목록에 남아도 아무도 안 연다.
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail=NEEDS_NAME)

    attachment = TaskAttachment(
        run_id=run.id,
        original_name=name[:300],
        stored_name="",              # 디스크에 아무것도 없다
        size_bytes=0,
        url=raw[:2000],
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
        action="링크 첨부",
        target_type="task_run",
        target_id=run.id,
        after_value={"link": raw, "name": name},
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

    if attachment.is_link:
        # 링크에서 이름은 **설명**이다. 파일 이름 규칙(경로 자르기·확장자
        # 붙이기)을 그대로 적용하면 `교개협 폴더` 가 이상하게 바뀐다.
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail=NEEDS_NAME)
    else:
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

    # 링크에는 지울 파일이 없다. stored_name 이 비었으므로 그냥 이으면
    # 업로드 폴더 자체를 가리키게 된다 — 그 상태로 unlink 하면 터진다.
    path = (ATTACHMENT_DIR / attachment.stored_name) if attachment.stored_name else None
    name = attachment.original_name
    was_link = attachment.is_link
    db.delete(attachment)
    db.commit()
    if path is not None and path.is_file():
        path.unlink()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="링크 삭제" if was_link else "첨부 삭제",
        target_type="task_run",
        target_id=run.id,
        before_value={"link" if was_link else "file": name},
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
    if attachment.is_link:
        # 링크는 화면이 직접 연다. 여기로 오면 무언가 잘못된 것이므로
        # 파일이 있는 척하지 않는다.
        raise HTTPException(status_code=404, detail="이것은 링크입니다 — 내려받을 파일이 없습니다.")
    path = ATTACHMENT_DIR / attachment.stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="파일이 서버에 없습니다.")
    quoted = urllib.parse.quote(attachment.original_name)
    return FileResponse(
        path,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
