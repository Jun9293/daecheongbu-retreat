"""백업 — SQLite 파일 · VAPID 키 · 업로드 폴더 (CLAUDE.md 운영).

**파일 복사가 아니라 `VACUUM INTO` 를 쓴다.** 누군가 쓰는 중에 복사하면 반쯤
쓰인 페이지가 섞인 파일이 남는데, 그 파일은 열릴 때까지 멀쩡해 보인다.
`VACUUM INTO` 는 SQLite 가 일관된 스냅샷을 직접 만들어 준다.

VAPID 키도 함께 남긴다. 그 파일이 바뀌면 **기존 구독이 전부 조용히 죽는다** —
아무 오류도 나지 않고 그냥 안 간다 (4-11).

**업로드 폴더도 함께 남긴다.** 첨부파일과 영수증은 DB 밖에 쌓이므로 app.db 만
되돌리면 목록에는 파일이 있는데 열리지 않는다 — 되돌리고 나서야 알게 되는
종류의 실패다. 폴더째 zip 으로 묶어 같은 날짜를 붙인다.

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
import os
import pathlib
import shutil
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR, UPLOAD_DIR                      # noqa: E402

KEEP = 30                      # 이만큼만 남기고 오래된 것부터 지운다

# ── 크기로도 제한한다 ────────────────────────────────────────────────
#
# 첨부 상한이 200MB 가 되면서 개수만으로는 부족해졌다. 큰 것이 몇 개만
# 들어와도 30벌이면 디스크가 금세 찬다. **개수가 30 이하여도 총합이 이보다
# 크면 오래된 것부터 지운다.**
#
# 크기는 **실제로 차지하는 만큼** 센다 — 바뀌지 않은 업로드 zip 은 하드링크로
# 이어 두므로(아래 copy_uploads), 파일 크기를 그냥 더하면 실제보다 몇 배로
# 잡혀 멀쩡한 백업을 지운다.
MAX_TOTAL_BYTES = 10 * 1024 * 1024 * 1024        # 10GB

BACKUP_DIR = DATA_DIR / "backups"
DB_PATH = DATA_DIR / "app.db"
VAPID_PATH = DATA_DIR / "vapid_private.pem"
UPLOADS_PATH = UPLOAD_DIR


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


SIG_PATH_NAME = "uploads-latest.sig"


def uploads_signature(uploads: pathlib.Path) -> str:
    """업로드 폴더의 지금 모습을 한 줄로 요약한다.

    이름·크기·수정시각만 본다. 내용을 다 읽어 해시하면 200MB 짜리가 몇 개만
    있어도 매일 새벽에 그것을 전부 읽게 되는데, 그건 통째로 복사하는 것과
    비용이 다르지 않다.
    """
    import hashlib

    parts = []
    for path in sorted(uploads.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        parts.append(f"{path.relative_to(uploads).as_posix()}|{stat.st_size}|{stat.st_mtime_ns}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def copy_uploads(
    uploads: pathlib.Path, out_dir: pathlib.Path, *, stamp: str
) -> tuple[pathlib.Path | None, bool]:
    """업로드 폴더를 zip 하나로 묶는다. **바뀐 것만 실제로 복사한다.**

    돌려주는 것은 (경로, 새로 묶었는가).

    첨부 상한이 200MB 가 되면서 매일 새벽 통째로 다시 묶는 것이 감당이
    안 됐다. 그런데 올라온 파일은 대개 그대로다 — 첨부는 임의의 이름으로
    저장되므로 덮어쓰이지 않고, 지우는 것만 사람이 한다.

    그래서 **바뀌지 않았으면 다시 묶지 않고 지난 zip 에 하드링크를 건다.**
    되돌리는 절차는 그대로다 — 날짜마다 `uploads-<날짜>.zip` 이 있고
    같은 날짜끼리 셋을 함께 되돌리면 된다. 다만 그 파일이 디스크를 두 번
    차지하지 않을 뿐이다. (하드링크가 안 되는 곳에서는 그냥 복사한다.)

    파일이 하나도 없으면 만들지 않는다 — 빈 zip 이 30개 쌓여 있으면
    "백업에 파일이 있다"와 "파일이 원래 없었다"를 구별할 수 없다.
    """
    if not uploads.exists():
        return None, False
    if not any(path.is_file() for path in uploads.rglob("*")):
        return None, False

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"uploads-{stamp}.zip"
    sig_path = out_dir / SIG_PATH_NAME
    signature = uploads_signature(uploads)

    previous = None
    if sig_path.exists():
        try:
            last_stamp, last_sig = sig_path.read_text(encoding="utf-8").split("\n")[:2]
        except (ValueError, OSError):
            last_stamp = last_sig = ""
        if last_sig == signature:
            candidate = out_dir / f"uploads-{last_stamp}.zip"
            if candidate.exists():
                previous = candidate

    if previous is not None:
        # 같은 초에 두 번 돌면 지난 것과 이번 것의 이름이 같다. 자기 자신에게
        # 링크를 걸 수는 없으므로 그대로 둔다 — DB 스냅샷이 덮어쓰는 것과 같다.
        if previous == target:
            return target, False
        target.unlink(missing_ok=True)
        try:
            os.link(previous, target)
        except OSError:                     # 하드링크가 안 되는 곳이면 그냥 복사
            shutil.copy2(previous, target)
        sig_path.write_text(f"{stamp}\n{signature}", encoding="utf-8")
        return target, False

    made = pathlib.Path(shutil.make_archive(str(out_dir / f"uploads-{stamp}"), "zip",
                                            root_dir=str(uploads)))
    sig_path.write_text(f"{stamp}\n{signature}", encoding="utf-8")
    return made, True


def files_of(out_dir: pathlib.Path, stamp: str) -> tuple[pathlib.Path, ...]:
    """한 회차의 세 파일. 같은 날짜끼리 함께 지우고 함께 되돌린다."""
    return (
        out_dir / f"app-{stamp}.db",
        out_dir / f"vapid-{stamp}.pem",
        out_dir / f"uploads-{stamp}.zip",
    )


def disk_used(paths) -> int:
    """**실제로 차지하는 크기.** 하드링크로 이어진 zip 은 한 번만 센다.

    그냥 더하면 바뀌지 않은 업로드가 30번 세어져, 실제로는 1GB 인데
    30GB 로 잡혀 멀쩡한 백업을 지운다.
    """
    seen, total = set(), 0
    for path in paths:
        if not path.exists():
            continue
        stat = path.stat()
        key = (stat.st_dev, stat.st_ino)
        if stat.st_ino and key in seen:
            continue
        if stat.st_ino:
            seen.add(key)
        total += stat.st_size
    return total


def stamps_in(out_dir: pathlib.Path) -> list[str]:
    """최근 것이 앞."""
    return sorted(
        {path.stem.split("-", 1)[1] for path in out_dir.glob("app-*.db")},
        reverse=True,
    )


def prune(
    out_dir: pathlib.Path, *, keep: int = KEEP, max_total: int = MAX_TOTAL_BYTES
) -> list[pathlib.Path]:
    """오래된 것부터 지운다. DB · 키 · 업로드를 같은 회차로 묶어 함께 지운다.

    **개수와 크기를 함께 본다.** 개수만 보면 200MB 짜리 첨부가 들어온 뒤로
    디스크가 조용히 차고, 크기만 보면 작은 백업이 무한정 쌓인다.
    """
    stamps = stamps_in(out_dir)
    removed: list[pathlib.Path] = []

    def drop(stamp: str) -> None:
        for path in files_of(out_dir, stamp):
            if path.exists():
                path.unlink()
                removed.append(path)

    for stamp in stamps[keep:]:
        drop(stamp)
    kept = stamps[:keep]

    # 남은 것의 총합이 기준을 넘으면 개수가 30 이하여도 오래된 것부터 지운다.
    # **마지막 하나는 남긴다** — 크기 때문에 백업이 하나도 없게 되는 것은
    # 디스크가 차는 것보다 나쁘다.
    while len(kept) > 1 and disk_used(
        path for stamp in kept for path in files_of(out_dir, stamp)
    ) > max_total:
        drop(kept.pop())

    return removed


def run(
    *, db_path: pathlib.Path = DB_PATH, key_path: pathlib.Path = VAPID_PATH,
    uploads: pathlib.Path = UPLOADS_PATH,
    out_dir: pathlib.Path = BACKUP_DIR, keep: int = KEEP,
    max_total: int = MAX_TOTAL_BYTES,
) -> dict:
    if not db_path.exists():
        return {"ok": False, "reason": f"DB 파일이 없습니다: {db_path}"}

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    db_copy = snapshot(db_path, out_dir, stamp=stamp)
    key_copy = copy_vapid(key_path, out_dir, stamp=stamp)
    uploads_copy, uploads_fresh = copy_uploads(uploads, out_dir, stamp=stamp)
    removed = prune(out_dir, keep=keep, max_total=max_total)
    return {
        "ok": True,
        "db": db_copy,
        "vapid": key_copy,
        "uploads": uploads_copy,
        # 바뀐 것이 없어 지난 zip 에 이어 붙였는가
        "uploads_fresh": uploads_fresh,
        "removed": len(removed),
        "kept": len(list(out_dir.glob("app-*.db"))),
        # 이번 회차가 몇 MB 인지 · 전체가 몇 MB 인지
        "size": disk_used(files_of(out_dir, stamp)),
        "total": disk_used(
            path for one in stamps_in(out_dir) for path in files_of(out_dir, one)
        ),
    }


def mb(size: int) -> str:
    return f"{size / (1024 * 1024):,.1f}MB"


if __name__ == "__main__":
    result = run()
    if not result["ok"]:
        print("백업하지 못했습니다 —", result["reason"])
        raise SystemExit(1)
    print(f"백업했습니다: {result['db'].name} ({mb(result['db'].stat().st_size)})")
    if result["vapid"]:
        print(f"  VAPID 키도 함께: {result['vapid'].name}")
    else:
        print("  ! VAPID 키 파일이 없습니다 — 푸시를 아직 쓰지 않았다면 정상입니다.")
    if result["uploads"]:
        note = "새로 묶었습니다" if result["uploads_fresh"] else "바뀐 것이 없어 지난 것에 이어 붙였습니다"
        print(f"  업로드 폴더도 함께: {result['uploads'].name}"
              f" ({mb(result['uploads'].stat().st_size)} · {note})")
    else:
        print("  · 올라온 파일이 아직 없습니다.")
    if result["removed"]:
        print(f"  오래된 백업 {result['removed']}개를 지웠습니다.")
    # 이번 회차가 몇 MB 인지 찍는다 — 안 찍으면 어느 날 갑자기 디스크가 차 있다
    print(f"  이번 백업 {mb(result['size'])} · 전체 {mb(result['total'])}"
          f" (기준 {mb(MAX_TOTAL_BYTES)})")
    print(f"  현재 {result['kept']}개 보관 중 (최대 {KEEP}개)")
