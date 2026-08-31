"""백업 — SQLite 파일과 VAPID 키 (CLAUDE.md 운영).

**파일 복사가 아니라 `VACUUM INTO` 를 쓴다.** 누군가 쓰는 중에 복사하면 반쯤
쓰인 페이지가 섞인 파일이 남는데, 그 파일은 열릴 때까지 멀쩡해 보인다.
`VACUUM INTO` 는 SQLite 가 일관된 스냅샷을 직접 만들어 준다.

VAPID 키도 함께 남긴다. 그 파일이 바뀌면 **기존 구독이 전부 조용히 죽는다** —
아무 오류도 나지 않고 그냥 안 간다 (4-11).

    .venv\\Scripts\\python.exe scripts/backup.py
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글·기호가 깨지지 않게 한다.
# 여기서 터지면 "무엇이 문제인지 말해주는 스크립트" 가 자기 때문에 죽는다.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import datetime as dt
import pathlib
import shutil
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR                                  # noqa: E402

KEEP = 30                      # 이만큼만 남기고 오래된 것부터 지운다
BACKUP_DIR = DATA_DIR / "backups"
DB_PATH = DATA_DIR / "app.db"
VAPID_PATH = DATA_DIR / "vapid_private.pem"


def snapshot(
    db_path: pathlib.Path, out_dir: pathlib.Path, *, stamp: str | None = None
) -> pathlib.Path:
    """VACUUM INTO 로 일관된 사본을 만든다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"app-{stamp}.db"
    if target.exists():
        target.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        # 경로에 따옴표가 들어가도 깨지지 않게 파라미터로 넘긴다
        conn.execute("VACUUM INTO ?", (str(target),))
    finally:
        conn.close()
    return target


def copy_vapid(key_path: pathlib.Path, out_dir: pathlib.Path, *, stamp: str) -> pathlib.Path | None:
    if not key_path.exists():
        return None
    target = out_dir / f"vapid-{stamp}.pem"
    shutil.copy2(key_path, target)
    return target


def prune(out_dir: pathlib.Path, *, keep: int = KEEP) -> list[pathlib.Path]:
    """오래된 것부터 지운다. DB 와 키를 같은 회차로 묶어 함께 지운다."""
    stamps = sorted(
        {path.stem.split("-", 1)[1] for path in out_dir.glob("app-*.db")},
        reverse=True,
    )
    removed: list[pathlib.Path] = []
    for stamp in stamps[keep:]:
        for path in (out_dir / f"app-{stamp}.db", out_dir / f"vapid-{stamp}.pem"):
            if path.exists():
                path.unlink()
                removed.append(path)
    return removed


def run(
    *, db_path: pathlib.Path = DB_PATH, key_path: pathlib.Path = VAPID_PATH,
    out_dir: pathlib.Path = BACKUP_DIR, keep: int = KEEP,
) -> dict:
    if not db_path.exists():
        return {"ok": False, "reason": f"DB 파일이 없습니다: {db_path}"}

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    db_copy = snapshot(db_path, out_dir, stamp=stamp)
    key_copy = copy_vapid(key_path, out_dir, stamp=stamp)
    removed = prune(out_dir, keep=keep)
    return {
        "ok": True,
        "db": db_copy,
        "vapid": key_copy,
        "removed": len(removed),
        "kept": len(list(out_dir.glob("app-*.db"))),
    }


if __name__ == "__main__":
    result = run()
    if not result["ok"]:
        print("백업하지 못했습니다 —", result["reason"])
        raise SystemExit(1)
    size = result["db"].stat().st_size / 1024
    print(f"백업했습니다: {result['db'].name} ({size:,.0f} KB)")
    if result["vapid"]:
        print(f"  VAPID 키도 함께: {result['vapid'].name}")
    else:
        print("  ! VAPID 키 파일이 없습니다 — 푸시를 아직 쓰지 않았다면 정상입니다.")
    if result["removed"]:
        print(f"  오래된 백업 {result['removed']}개를 지웠습니다.")
    print(f"  현재 {result['kept']}개 보관 중 (최대 {KEEP}개)")
