# -*- coding: utf-8 -*-
"""옛 작업 파일(/files · FileAsset)을 업무 첨부(4-9)로 옮긴다 — 일회성.

.venv\\Scripts\\python.exe scripts/migrate_files.py            (미리보기)
.venv\\Scripts\\python.exe scripts/migrate_files.py --실행     (실제로 옮김)

- 업무에 연결된 파일은 그 업무의 run 으로, 미연결 큐시트는
  「프로그램별 큐시트 제작」 run 으로 간다. **그 업무가 그 회차에 없으면
  멈추고 보고한다 — 만들지 않는다.**
- 파일 이름은 원래 이름 그대로(끝에 v1·v2 가 이미 붙어 있다), 디스크에는
  임의 이름으로 복사한다 (4-9). **원본 FileAsset 행과 디스크 파일은 지우지
  않는다** (0장).
- 승인 상태는 첨부에 자리가 없으므로 ActivityLog 에
  「작업 파일에서 옮김 — 당시 상태: ○○」 로 남긴다.
- 큐시트에 걸린 확인 요청(ReviewRequest)은 run_id 를 그 업무로 채운다 —
  file_asset_id 는 그대로 둔다.
- 두 번 돌리면 두 번 옮기지 않는다 — 이미 옮긴 흔적(ActivityLog
  `작업파일_이관`)이 있으면 멈춘다.
"""

from __future__ import annotations

import secrets
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.config import ASSET_DIR, ATTACHMENT_DIR  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import (  # noqa: E402
    ActivityLog,
    FileAsset,
    ReviewRequest,
    Task,
    TaskAttachment,
    TaskRun,
)

CUE_TASK_TITLE = "프로그램별 큐시트 제작"


def run_for_asset(db, asset: FileAsset) -> TaskRun | None:
    """이 파일이 갈 업무(run). 연결된 옛 Task 는 제목으로 같은 회차의 run 을
    찾는다 — 옛 id 는 run 을 잇지 못한다 (4-14 와 같은 사정)."""
    wanted = None
    if asset.task_id:
        task = db.get(Task, asset.task_id)
        wanted = task.title if task else None
    elif "큐시트" in (asset.title or ""):
        wanted = CUE_TASK_TITLE
    if not wanted:
        return None
    runs = [
        r
        for r in db.scalars(select(TaskRun).where(TaskRun.retreat_id == asset.retreat_id))
        if r.library.title == wanted
    ]
    return runs[0] if len(runs) == 1 else None


def main() -> int:
    do = "--실행" in sys.argv
    init_db()
    with SessionLocal() as db:
        already = db.scalars(
            select(ActivityLog).where(ActivityLog.action == "작업파일_이관")
        ).first()
        if already is not None:
            print("이미 옮긴 흔적(ActivityLog 작업파일_이관)이 있습니다 — 멈춥니다.")
            print("두 번 옮기면 같은 파일이 첨부에 두 벌 생깁니다.")
            return 1

        assets = list(db.scalars(select(FileAsset).order_by(FileAsset.id)))
        if not assets:
            print("옮길 작업 파일이 없습니다.")
            return 0

        plan = []
        for asset in assets:
            run = run_for_asset(db, asset)
            if run is None:
                print(f"!! 「{asset.title}」 이(가) 갈 업무를 찾지 못했습니다 — 멈춥니다.")
                print("   업무를 만들어 옮기지 않습니다 — 사람이 자리를 정해 주세요.")
                return 1
            plan.append((asset, run))

        for asset, run in plan:
            print(f"「{asset.title}」 (상태: {asset.status}) → "
                  f"[{run.run_no}] {run.library.title} (run {run.id})")
            for v in sorted(asset.versions, key=lambda v: v.version_no):
                src = ASSET_DIR / v.stored_name
                ok = "" if src.exists() else "  !! 디스크에 파일이 없습니다"
                print(f"   v{v.version_no} · {v.original_name} · {v.size_bytes}B{ok}")
                if not src.exists():
                    print("   멈춥니다 — 목록에는 있는데 열리지 않는 첨부를 만들지 않습니다.")
                    return 1
            reviews = db.scalars(
                select(ReviewRequest).where(ReviewRequest.file_asset_id == asset.id)
            ).all()
            for review in reviews:
                print(f"   확인 요청 {review.id} ({review.status}) → run_id={run.id} 로 채움")

        if not do:
            print("\n미리보기입니다 — 실제로 옮기려면 --실행 을 붙이세요.")
            return 0

        for asset, run in plan:
            for v in sorted(asset.versions, key=lambda v: v.version_no):
                src = ASSET_DIR / v.stored_name
                stored = f"{secrets.token_hex(16)}{Path(v.original_name).suffix.lower()}"
                shutil.copy2(src, ATTACHMENT_DIR / stored)   # 원본은 그대로 둔다
                db.add(
                    TaskAttachment(
                        run_id=run.id,
                        original_name=v.original_name,
                        stored_name=stored,
                        size_bytes=v.size_bytes or src.stat().st_size,
                        uploaded_by_id=v.uploaded_by_id or asset.created_by_id,
                        uploaded_by_name=v.uploaded_by_name,
                        uploaded_at=v.uploaded_at,
                    )
                )
            for review in db.scalars(
                select(ReviewRequest).where(ReviewRequest.file_asset_id == asset.id)
            ):
                review.run_id = run.id
            db.add(
                ActivityLog(
                    retreat_id=asset.retreat_id,
                    actor_type="system",
                    actor_name="scripts/migrate_files.py",
                    action="작업파일_이관",
                    target_type="task_run",
                    target_id=run.id,
                    summary=f"작업 파일에서 옮김 — 당시 상태: {asset.status} "
                            f"(「{asset.title}」 버전 {len(asset.versions)}건)",
                )
            )
        db.commit()
        print("\n옮겼습니다. 원본 행·파일은 그대로 남아 있습니다.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
