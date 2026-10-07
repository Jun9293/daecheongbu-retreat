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
import logging
import os
import re
import pathlib
import shutil
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# **app.config 가 아니라 app.paths 에서 받는다** — config 는 읽히는 순간 폴더를 만들고 서명키를
# 쓴다. 앱 밖 자리(--살핀다)가 data/ 가 빈 날 불려도 흔적을 남기지 않게(2026-09-13 사람이 정함).
from app.paths import DATA_DIR, UPLOAD_DIR, 백업자리              # noqa: E402

_log = logging.getLogger("backup")

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

# ── 빈 백업을 정리 대상에서 뺀다 (2026-09-13 · 봐둘것 AZ-a) ────────────
#
# 시험이 운영 DB 를 비운 날 새벽 3시에 이 스크립트가 **빈 DB 를 떴다.** 이름만
# 보면 그것이 가장 최근 판이고, 개수(30)로 지우면 빈 판이 하루 한 칸씩 성한 판을
# 밀어낸다 — 시간이 더 지났으면 성한 판이 다 밀려나고 빈 판만 남는다.
#
# 그래서 뜰 때 **표마다 행 수를 옆 파일(`app-<때>.rows.json`)에 남긴다** — 백업을
# 안 열고도 성한지 안다. 그리고 **의심스러운 판은 성한 판의 칸(KEEP)에 안 센다** —
# 따로 `SUSPECT_KEEP` 까지 남기고, 크기가 넘치면 성한 판보다 먼저 지운다(아래).
# 증거로 남길 판은 `지키는판` 에 까닭과 함께 적는다.
#
# **의심의 기준에 「몇 행 미만」 을 박지 않는다.** 행 수는 회차가 쌓이면 자라서
# 오늘 맞는 숫자가 내년에는 성한 판을 빈 판으로 부른다. 대신 둘을 본다.
#   ① 회차 표(`retreats`)가 있는데 0 행 — 이 앱의 운영 DB 는 회차 없이는 뜻이
#      없다(구조의 신호). 표가 아예 없는 판은 이 앱의 DB 가 아니라 이 기준을 안 건다
#   ② 행 합이 **가운데 판(중앙값)의 `SUSPECT_RATIO` 미만** — 상대 기준.
#      가장 큰 판과 견주지 않는 까닭은 `suspects` 에 있다(한 판이 튀면 전부 의심이 된다).
#      「반으로 줄었다」 로 잡지 않는 까닭: 2026-09-10 에 계정 정리로 행이 실제로
#      절반 가까이 줄었다(3091 → 1604). 그 판은 성한 판이다.
# 행 수를 못 읽는 판(SQLite 가 아닌 파일)은 **의심에 안 넣는다** — 그 판으로는
# 되돌릴 수도 없어서 지워도 잃는 것이 없고, 넣으면 영영 안 지워지고 쌓인다.
SUSPECT_RATIO = 0.10

# ── 의심 판에도 상한을 둔다 (2026-09-13 · 사람이 정함) ─────────────────
#
# 의심 판은 성한 판의 칸(KEEP)을 안 차지하지만, 그대로 두면 **운영이 빈 채로
# 오래 가는 날 하루 하나씩 한없이 쌓인다.** 그래서 의심 판은 따로 이만큼만 남기고
# 넘는 것은 오래된 것부터 지운다. 크기가 넘칠 때도 **의심 판을 성한 판보다 먼저**
# 지운다 — 빈 판으로는 되돌릴 수 없으므로 잃는 것이 가장 적은 쪽부터다.
#
# **7 인 까닭** — 빈 판이 뜨면 그날 아침 앱의 알림에 선다(`알린다`). 한 주 동안
# 아무도 그 알림을 안 봤다면 의심 판을 더 쌓아 둔다고 달라질 것이 없다. 증거로
# 볼 것은 **처음 빈 날의 판**이고 그 판은 아래의 `지키는판` 이 따로 붙든다.
# 성한 판 30(KEEP)과 겹치지 않는 별도 칸이라, 의심 판이 몇이든 성한 판은 30 이
# 그대로 남는다.
SUSPECT_KEEP = 7

# **어떤 경우에도 안 지우는 판** — 날짜와 까닭을 함께 적는다. 개수·크기·의심 상한
# 어느 것도 이 판을 안 세고 안 지운다. 앱 알림도 안 세운다: 사람이 이미 알고
# 남기기로 정한 판이라 「지울지 정하세요」 가 매번 설 까닭이 없다.
# **문서가 되돌리는 자리로 가리키는 사본은 여기 반드시 넣는다** — 규칙과 까닭은 CLAUDE.md 11-2 백업 절
# (여기 다시 적지 않는다). 짝이 맞는지는 tests/test_stage52.py 가 본다.
지키는판 = {
    "20260913-030001": "2026-09-13 시험이 운영 DB 를 비운 채 돈 새벽 백업 — 사고의 증거"
                       "라 지우지 않기로 사람이 정했다(봐둘것 AZ-a)",
    "20260912-151859": "2026-09-13 사고 직전의 성한 판 — 사고 증거로 030001(빈 백업)과 짝을 이룬다."
                       " 2026-09-15 사람이 지키기로 정했다(봐둘것 AZ-a)",
    "20260915-002352": "2026-09-15 재정 시트를 운영에 들이기 직전 사본(scripts/재정들여오기.py) — 문서가 되돌리는"
                       " 자리로 가리키는 판이라 개수·크기 정리에서 빼 지우지 않는다(CLAUDE.md 7-1 · 7-5)",
    "20260915-144929": "2026-09-15 못 이은 지출 30 건을 결산 식으로 채우기 직전 사본(scripts/재정짝잇기.py) — 덮인 옛"
                       " 시트 글자를 활동 기록에 안 남기기로 해 문서가 되돌리는 자리로 가리킨다(CLAUDE.md 7-5 · 봐둘것 BB-h)",
    "20260916-151047": "2026-09-16 노션 업무 233 을 회차 1 에 들이기 직전 사본(scripts/노션업무들이기.py) — 그 판이"
                       " 업무 102 를 미실행으로 내렸고, 되돌리는 자리를 문서가 이 이름으로 가리킨다(CLAUDE.md 13장 · 봐둘것 BC-c)",
    "20260917-152010": "2026-09-17 테스트 시드 업무(라이브러리 13 · run 26)를 지우기 직전 사본(scripts/테스트시드삭제.py) —"
                       " 0장 둘째 예외로 행을 지웠고 되돌리는 자리를 문서가 이 이름으로 가리킨다(CLAUDE.md 0장 · 봐둘것 BD-b)",
    "20260918-003508": "2026-09-18 노션 업무 100 에 상위를 채우기 직전 사본(scripts/업무계층채우기.py) — 되돌리는"
                       " 자리를 문서가 이 이름으로 가리킨다(CLAUDE.md 14장 · 봐둘것 BF-a)",
}

# **위치는 바꿀 수 있다** (2026-09-30 · 맥 이전 3단계) — `DCB_BACKUP_DIR` 을 읽는 곳은
# `app.paths.백업자리` 하나다(점검 화면 · 자가진단 · 맥의 셸도 그것을 부른다). 비면 전과 같은
# `data/backups`. 그 위치가 붙어 있는지·쓸 수 있는지는 **부르는 쪽이 먼저 본다**
# (scripts/mac/백업.sh) — 여기서 폴더를 만들면 빠진 드라이브 자리에 내장 디스크 폴더가
# 생겨 조용히 거기 쌓인다. 값이 틀렸으면(`자리문제`) 아래 main 이 78 로 멈춘다 — 기본값으로
# 물러서 다른 자리에 뜨지 않는다. 모듈을 읽는 자리를 죽이지 않으려고 이름은 기본값을 든다.
_자리, 자리문제 = 백업자리()
BACKUP_DIR = _자리 or (DATA_DIR / "backups")
DB_PATH = DATA_DIR / "app.db"
VAPID_PATH = DATA_DIR / "vapid_private.pem"
UPLOADS_PATH = UPLOAD_DIR


def 안겹치는때(out_dir: pathlib.Path, stamp: str) -> str:
    """이 이름의 판이 이미 있으면 `-02` · `-03` … 을 붙인다 — **절대 덮지 않는다** (2026-09-30).

    판 이름이 초 단위라 같은 초에 두 번 돌면 뒤엣것이 앞엣것을 같은 이름으로 덮었다.
    같은 순간의 사본이라 대개 같은 내용이지만, 그 사이에 DB 가 바뀌었으면 **앞 판을
    말없이 잃는다** — 재현했다(맥 이전 3단계 마무리). 붙인 이름도 `stamps_in` 이
    그대로 읽고, 문자열로 늘어놓으면 붙인 쪽이 뒤(더 최근)로 선다.
    """
    후보, n = stamp, 1
    while any(p.exists() for p in files_of(out_dir, 후보)):
        n += 1
        후보 = f"{stamp}-{n:02d}"   # 두 자리 — `-10` 이 `-2` 앞에 서지 않게
    return 후보


def snapshot(
    db_path: pathlib.Path, out_dir: pathlib.Path, *, stamp: str | None = None
) -> pathlib.Path:
    """VACUUM INTO 로 일관된 사본을 만든다. **있는 판을 덮지 않는다** — 이름이 겹치면 붙인다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = 안겹치는때(out_dir, stamp or dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    target = out_dir / f"app-{stamp}.db"

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


README_NAME = "읽어보기.txt"

# 백업 폴더를 여는 사람은 대개 **밖으로 복사하려고** 연다. 그 자리에서 읽지
# 않으면 폴더째 복사해 버리는데, 업로드 zip 이 하드링크로 이어져 있어서
# USB·클라우드에서는 전부 실체로 펼쳐진다 (11-2). 안내가 저장소 문서에만
# 있으면 그때 아무도 안 본다. 그래서 폴더 안에 둔다.
README_TEXT = """이 폴더에 대해 — 읽고 복사하세요

■ 폴더째 통째로 복사하지 마세요

  uploads-날짜.zip 은 내용이 안 바뀌면 다시 묶지 않고, 지난 것과
  **한 파일을 같이 가리키게** 해 둡니다(하드링크).
  그래서 이 컴퓨터에서는 30벌이 있어도 몇 벌 크기밖에 안 씁니다.

  그런데 USB(exFAT) · 구글 드라이브 · 원드라이브는 그 이어짐을 모릅니다.
  복사하는 순간 전부 진짜 파일로 펼쳐집니다 —
  업로드가 1GB 면 30벌이 30GB 가 됩니다.

■ 최근 몇 벌만 복사하세요 (파워셸에 그대로 붙여넣기)

  $원본 = "{here}"
  $받을곳 = "D:\\대청부백업"          # USB 나 클라우드 폴더로 바꾸세요
  New-Item -ItemType Directory -Force $받을곳 | Out-Null
  Get-ChildItem $원본 -Filter "app-*.db" |
    Sort-Object Name -Descending |
    Where-Object {{
      $행수 = Join-Path $원본 ($_.BaseName + ".rows.json")
      -not (Test-Path $행수) -or ((Get-Content $행수 -Raw -Encoding UTF8 | ConvertFrom-Json).tables.retreats -ne 0)
    }} |
    Select-Object -First 3 | ForEach-Object {{
      $날짜 = $_.BaseName -replace '^app-',''
      Get-ChildItem $원본 -Filter "*-$날짜.*" | Copy-Item -Destination $받을곳 -Force
    }}

  이렇게 나오면 성공 — 받을곳에 app-…db · uploads-…zip · vapid-…pem 과
  행 수 파일(app-…rows.json)이 날짜별로 들어 있습니다.
  회차가 0 인 판(빈 판)은 건너뜁니다 — 이름순으로만 고르면 빈 판부터 복사합니다.

■ 옛 zip 을 열어서 고쳐 저장하지 마세요

  같은 파일을 가리키던 **다른 날짜의 zip 도 함께 바뀝니다.**
  안을 들여다보는 것은 괜찮습니다. 고쳐 저장하는 것만 하지 마세요.

■ 되돌릴 때

  **먼저 그 날짜의 app-날짜.rows.json 을 메모장으로 여세요.** 표마다 행 수가
  적혀 있습니다. 이름이 가장 최근인 것이 성한 것이 아닙니다 — 운영 DB 가 빈
  채로 새벽 백업이 돌면 가장 최근 판이 빈 판입니다(2026-09-13 에 실제로 그랬습니다).
  "retreats" 가 0 이거나 total 이 다른 날보다 터무니없이 적으면 그 판을 쓰지 마세요.

  서버를 끄고, **같은 날짜끼리 셋을 함께** 되돌립니다.
    app-날짜.db      →  data\\app.db
    uploads-날짜.zip  →  풀어서 data\\uploads\\
    vapid-날짜.pem    →  data\\vapid_private.pem
  날짜를 섞으면 DB 의 목록과 실제 파일이 어긋나고,
  VAPID 를 빼먹으면 알림 구독이 살아나지 않습니다.

(이 파일은 backup.py 가 돌 때마다 다시 씁니다. 고쳐도 되돌아갑니다.)
"""


def write_readme(out_dir: pathlib.Path) -> pathlib.Path:
    """폴더를 여는 사람이 그 자리에서 읽도록 안내를 남긴다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / README_NAME
    target.write_text(README_TEXT.format(here=out_dir), encoding="utf-8")
    return target


def files_of(out_dir: pathlib.Path, stamp: str) -> tuple[pathlib.Path, ...]:
    """한 회차의 파일. 같은 날짜끼리 함께 지우고 함께 되돌린다."""
    return (
        out_dir / f"app-{stamp}.db",
        out_dir / f"vapid-{stamp}.pem",
        out_dir / f"uploads-{stamp}.zip",
        rows_path(out_dir, stamp),
    )


def rows_path(out_dir: pathlib.Path, stamp: str) -> pathlib.Path:
    return out_dir / f"app-{stamp}.rows.json"


def count_rows(db_file: pathlib.Path) -> dict:
    """표마다 행 수 — **읽기 전용으로** 연다(백업을 세다 고치면 안 된다)."""
    conn = sqlite3.connect(f"{db_file.resolve().as_uri()}?mode=ro", uri=True)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        tables = {n: conn.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0] for n in sorted(names)}
    finally:
        conn.close()
    return {"total": sum(tables.values()), "tables": tables}


def write_rows(out_dir: pathlib.Path, stamp: str) -> dict:
    import json

    rows = count_rows(out_dir / f"app-{stamp}.db")
    rows_path(out_dir, stamp).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows


def rows_of(out_dir: pathlib.Path, stamp: str, *, 기록: bool = True) -> dict | None:
    """옆 파일에서 읽는다. 없거나 · 모양이 틀렸거나 · 판보다 옛것이면 다시 세어 남긴다.
    못 읽으면 None.

    **옆 파일을 그냥 믿지 않는다** — 사람이 메모장으로 여는 파일이라 고쳐질 수 있고,
    판(`app-<때>.db`)을 다른 사본으로 바꿔 넣으면 옛 수가 남는다. 모양이 틀리면
    `prune` 이 죽고, 새벽 작업의 실패는 아무에게도 안 닿는다(봐둘것 AZ-c).
    """
    import json

    db_file = out_dir / f"app-{stamp}.db"
    side = rows_path(out_dir, stamp)
    try:
        rows = json.loads(side.read_text(encoding="utf-8"))
        if (isinstance(rows, dict) and isinstance(rows.get("total"), int)
                and isinstance(rows.get("tables"), dict)
                and side.stat().st_mtime >= db_file.stat().st_mtime):
            return rows
    except (OSError, ValueError):
        pass
    try:
        # 기록=False 면 세기만 하고 옆 파일을 안 쓴다 — 앱 밖에서 **읽기만** 하는 자리(`살핀다`)
        return write_rows(out_dir, stamp) if 기록 else count_rows(db_file)
    except (sqlite3.Error, OSError):
        return None


def suspects(out_dir: pathlib.Path, stamps: list[str], *, 기록: bool = True) -> set[str]:
    """비었거나 터무니없이 적은 판 — 기준은 `SUSPECT_RATIO` 위의 글.

    **견주는 것은 가장 큰 판이 아니라 가운데 판(중앙값)이다.** 가장 큰 판을 쓰면
    한 판이 튀는 순간(시험 자료를 크게 넣었다 뺀 날) 그 뒤의 판이 전부 의심이 되고,
    의심 판은 개수·크기에 안 세므로 **아무것도 안 지워진 채 쌓인다** — 커밋 전
    검토가 50,001행 한 판 뒤 2,002행 40판으로 재어 짚었다. 중앙값은 한 판에 안 흔들린다.
    빈 판이 절반을 넘게 쌓이면 중앙값이 내려가 ②가 약해지지만, 그때는 ①이 잡는다.
    """
    import statistics

    rows = {s: rows_of(out_dir, s, 기록=기록) for s in stamps}
    totals = [r["total"] for r in rows.values() if r]
    middle = statistics.median(totals) if totals else 0
    out = set()
    for s, r in rows.items():
        if r is None:
            continue            # 못 읽는 판은 되돌릴 수도 없다 — 지워도 잃는 것이 없다
        tables = r["tables"]
        if ("retreats" in tables and tables["retreats"] == 0) or r["total"] < middle * SUSPECT_RATIO:
            out.add(s)
    return out


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
    out_dir: pathlib.Path, *, keep: int = KEEP, max_total: int = MAX_TOTAL_BYTES,
    실패: list[tuple[str, str]] | None = None,
) -> list[pathlib.Path]:
    """오래된 것부터 지운다. DB · 키 · 업로드를 같은 회차로 묶어 함께 지운다.

    **개수와 크기를 함께 본다.** 개수만 보면 200MB 짜리 첨부가 들어온 뒤로
    디스크가 조용히 차고, 크기만 보면 작은 백업이 무한정 쌓인다.

    **의심스러운 판(`suspects`)은 성한 판의 칸에 안 센다** — 빈 판이 칸을 차지해
    성한 판을 밀어내지 않게. 의심 판은 따로 `SUSPECT_KEEP` 까지만 남기고, 크기가
    넘칠 때는 **의심 판부터** 지운다. `지키는판` 은 어느 셈에도 안 든다.
    """
    전부 = [s for s in stamps_in(out_dir) if s not in 지키는판]
    빼둘 = suspects(out_dir, 전부)             # 한 번만 센다 — 줄마다 부르면 판 수의 제곱
    stamps = [s for s in 전부 if s not in 빼둘]
    의심 = [s for s in 전부 if s in 빼둘]       # 최근 것이 앞
    removed: list[pathlib.Path] = []

    def drop(stamp: str) -> None:
        # **하나가 안 지워져도 멈추지 않는다** (2026-10-01) — 전에는 예외가 그대로 올라가
        # 판은 떴는데 정리·알림·안내 파일이 통째로 건너뛰어졌다. 못 지운 것은 (판, 까닭)으로
        # `실패` 에 모아 부르는 쪽이 한 줄로 남긴다. 이미 없는 파일은 실패가 아니다
        for path in files_of(out_dir, stamp):
            try:
                if path.exists():
                    path.unlink()
                    removed.append(path)
            except FileNotFoundError:
                continue
            except OSError as exc:
                if 실패 is not None:
                    실패.append((stamp, f"{path.name}: {exc.strerror or exc}"))

    for stamp in 의심[SUSPECT_KEEP:]:
        drop(stamp)
    의심 = 의심[:SUSPECT_KEEP]
    for stamp in stamps[keep:]:
        drop(stamp)
    kept = stamps[:keep]

    # 남은 것의 총합이 기준을 넘으면 개수가 30 이하여도 오래된 것부터 지운다.
    # **의심 판을 먼저** 지운다. **성한 판의 마지막 하나는 남긴다** — 크기 때문에
    # 백업이 하나도 없게 되는 것은 디스크가 차는 것보다 나쁘다.
    def 합() -> int:
        return disk_used(path for stamp in kept + 의심 for path in files_of(out_dir, stamp))

    while 합() > max_total and (의심 or len(kept) > 1):
        drop(의심.pop() if 의심 else kept.pop())

    return removed


BACKUP_NOTICE_KIND = "백업"


def 의심말들(out_dir: pathlib.Path, *, 기록: bool = True) -> list[tuple[str, str, str]]:
    """**빈 판 경고의 판정과 말이 서는 곳은 여기 하나다** — (판의 때, 제목, 본문).

    앱 안(`알린다` → 알림 화면)과 앱 밖(`살핀다` → 되살아나나.ps1)이 **같은 이것을** 부른다.
    두 곳이 저마다 판정하거나 글을 적으면 한쪽만 고쳐져 두 자리가 다른 말을 한다.
    **DB 를 안 연다** — 백업 폴더만 읽는다. 그래서 운영 DB 가 비어도 말한다.
    `지키는판` 은 안 낸다.
    """
    나온것 = []
    전부 = stamps_in(out_dir)
    for stamp in sorted(s for s in suspects(out_dir, 전부, 기록=기록) if s not in 지키는판):
        r = rows_of(out_dir, stamp, 기록=기록) or {"total": "?", "tables": {}}
        나온것.append((
            stamp,
            f"새벽 백업이 비어 있습니다 — app-{stamp}.db",
            (f"회차 {r['tables'].get('retreats', '?')} · 행 {r['total']}. "
             "먼저 운영 DB 가 비지 않았는지 보세요 — 홈에 회차와 업무가 보이면 "
             "성한 것입니다. 비었으면 이 판이 아니라 그 앞 날짜의 성한 판으로 "
             "되돌립니다(배포-안내 「되돌리려면」). 이 판은 성한 판의 칸에 안 "
             "세고, 지울지는 사람이 정합니다."),
        ))
    return 나온것


def 살핀다(out_dir: pathlib.Path = BACKUP_DIR) -> list[str]:
    """**앱 밖 알림 자리** — DB 를 안 열고 백업 폴더만 읽어, 의심 판이 있으면 그 말을 줄로
    돌려준다. 없으면 빈 목록. `scripts/되살아나나.ps1` 이 부른다.

    앱 안 알림은 **DB 가 성할 때만** 선다 — 계정까지 빈 사고에서는 알릴 사람이 DB 에
    없다(봐둘것 AZ-c). 이 자리는 DB 와 무관해서 그때도 말한다. **읽기만 한다** — 옆 파일을
    안 쓴다(운영 자료는 읽기만).
    """
    if not out_dir.exists():
        return []
    return [f"!! {제목}\n     {본문}" for _, 제목, 본문 in 의심말들(out_dir, 기록=False)]


판이름꼴 = re.compile(r"(\d{8}-\d{6})(?:-\d{2,})?")
미래허용 = dt.timedelta(minutes=5)         # 시계가 조금 어긋난 것은 미래로 안 본다


def 판의때(stamp: str) -> dt.datetime | None:
    """판 이름의 때 — `YYYYmmdd-HHMMSS` 에 붙인 `-02` 까지만 받는다. 꼴이 다르면 None.

    **파일 수정 시각을 쓰지 않는다** — 판을 옮기거나 복사하면 수정 시각이 그날로 바뀐다
    (윈도우에서 옮겨 온 판이 실제로 그랬다 · 맥 이전 자잘한 정리 3). 이름은 뜬 때다.
    """
    맞음 = 판이름꼴.fullmatch(stamp)
    if not 맞음:
        return None
    try:
        return dt.datetime.strptime(맞음.group(1), "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def 마지막성한판(out_dir: pathlib.Path, *, now: dt.datetime | None = None) -> tuple[str, dt.datetime] | None:
    """**마지막 성한 판**과 그 때 — 「마지막 백업」 을 셈하는 곳은 여기 하나다 (2026-10-01).

    설정 › 점검(마지막 시각)과 `신선도`(백업점검)가 같이 부른다. 전에는 점검 화면만 파일
    수정 시각을 써서, 옮겨 온 판에서 두 자리가 다른 시각을 말했다. **읽기만 한다** — 폴더를
    만들지 않고 옆 파일도 안 쓴다(`기록=False`). 판이 없으면 None.

    건너뛰는 것 — 빈 판(`suspects` · 그 판으로는 되돌릴 수 없다), 이름에서 때를 못 읽는 판,
    지금보다 미래인 판(시계가 틀렸던 판이 「늘 싱싱함」 을 만들지 않게). 앞의 하나는 빈 판
    알림이 따로 말하고, 뒤의 둘은 **종류마다 로그 한 줄**로 남긴다.
    """
    now = now or dt.datetime.now()
    if not out_dir.is_dir():
        return None
    전부 = stamps_in(out_dir)
    빼둘 = suspects(out_dir, 전부, 기록=False)
    못읽음, 미래, 성한 = [], [], []
    for s in 전부:
        때 = 판의때(s)
        if 때 is None:                   # 이름부터 본다 — 행 수를 못 세는 판은 빈 판으로도 걸린다
            못읽음.append(s)
        elif s in 빼둘:
            continue
        elif 때 > now + 미래허용:
            미래.append(s)
        else:
            성한.append((때, s))
    if 못읽음:
        _log.warning("백업 판 이름에서 때를 못 읽어 건너뜀 %d개: %s", len(못읽음), ", ".join(못읽음[:3]))
    if 미래:
        _log.warning("백업 판의 때가 지금보다 미래라 건너뜀 %d개: %s", len(미래), ", ".join(미래[:3]))
    if not 성한:
        return None
    때, stamp = max(성한)
    return stamp, 때


def 신선도(out_dir: pathlib.Path, 시간: float, *, now: dt.datetime | None = None) -> tuple[bool, str]:
    """**마지막 성한 판**이 `시간` 보다 오래됐는가 — (싱싱한가, 한 줄 말). **읽기만 한다.**

    성한 판은 `suspects` 에 안 걸린 판이다(빈 판으로는 되돌릴 수 없으니 「백업이 있다」
    에 안 센다). 옆 파일도 안 쓴다(`기록=False`). 맥의 점검(`scripts/mac/백업점검.sh`)이
    부른다 — 새벽 3시가 기계가 꺼져 있어 건너뛰어졌는지, 위치가 빠져 며칠째 안 떴는지를
    **백업 자신이 아니라 바깥에서** 본다(백업이 안 돌면 백업은 아무 말도 못 한다).
    """
    now = now or dt.datetime.now()
    if not out_dir.is_dir():
        return False, f"백업 폴더가 없습니다: {out_dir}"
    마지막 = 마지막성한판(out_dir, now=now)          # 「마지막 백업」 은 여기 하나에서
    if 마지막 is None:
        return False, f"성한 판이 하나도 없습니다 (판 {len(stamps_in(out_dir))}개)"
    stamp, 때 = 마지막
    나이 = (now - 때).total_seconds() / 3600
    if 나이 > 시간:
        return False, f"마지막 성한 판이 {나이:.1f}시간 전입니다 (기준 {시간:g}시간) — app-{stamp}.db"
    return True, f"마지막 성한 판 {나이:.1f}시간 전 (기준 {시간:g}시간) — app-{stamp}.db"


def 알린다(db_path: pathlib.Path, out_dir: pathlib.Path) -> tuple[int, str | None]:
    """의심 판마다 **총무팀 전원의 앱 알림**에 한 번 세운다 — (새로 세운 수, 못 세운 까닭).

    새벽 작업의 출력은 작업 스케줄러가 남기지 않아 아무에게도 안 닿았다(봐둘것 AZ-c).
    그래서 사람이 평소에 지나는 자리 — 사이드바 배지와 알림 화면 — 에 세운다.
    **새 자리를 만들지 않고** `app.notifications.notify` 를 그대로 부른다.

    - **같은 판으로 두 번 안 선다** — `dedupe_key` 가 판의 때라 사람마다 한 번이다.
      매일 새벽 같은 줄이 쌓이면 아무도 안 읽는다
    - **의심 판이 없으면 아무 말도 안 한다** — 「이상 없음」 이 쌓이면 진짜 경고가 묻힌다
    - `지키는판` 은 안 세운다 — 사람이 이미 알고 남기기로 정한 판이다
    - **못 세우면 까닭을 돌려준다** — 조용히 삼키면 경고가 안 선 것과 구별이 안 된다
    """
    말들 = 의심말들(out_dir)
    if not 말들:
        return 0, None
    try:
        from sqlalchemy import create_engine, inspect
        from sqlalchemy.orm import Session

        from app import notifications as notify_service
        from app.domain import permissions as perm

        engine = create_engine(f"sqlite:///{db_path}")
        try:
            if not {"notifications", "users"} <= set(inspect(engine).get_table_names()):
                return 0, "이 DB 에 알림 표가 없습니다"
            새로 = 0
            with Session(engine, expire_on_commit=False) as db:
                총무 = perm.admins(db)
                if not 총무:
                    return 0, "알릴 총무팀 계정이 없습니다"
                for stamp, 제목, 본문 in 말들:
                    새로 += len(notify_service.notify(
                        db, users=총무, retreat_id=None, kind=BACKUP_NOTICE_KIND,
                        title=제목, body=본문,
                        link="/settings/checkup",
                        dedupe_key=f"backup-suspect:{stamp}",
                        # **웹 푸시로 안 보낸다** (2026-09-13 에 사람이 정함) — 새벽 3시에
                        # 자는 사람 휴대폰이 울린다. 백업이 이상한 것은 그 순간 뛰어갈 일이
                        # 아니라 아침에 보면 되는 일이고, 급한 알림과 섞이면 둘 다 안 읽힌다
                        push=False,
                    ))
            return 새로, None
        finally:
            engine.dispose()
    except Exception as e:  # 알림이 백업을 막으면 안 된다 — 까닭은 돌려준다
        return 0, f"{type(e).__name__}: {e}"


def run(
    *, db_path: pathlib.Path = DB_PATH, key_path: pathlib.Path = VAPID_PATH,
    uploads: pathlib.Path = UPLOADS_PATH,
    out_dir: pathlib.Path = BACKUP_DIR, keep: int = KEEP,
    max_total: int = MAX_TOTAL_BYTES,
) -> dict:
    if not db_path.exists():
        return {"ok": False, "reason": f"DB 파일이 없습니다: {db_path}"}

    stamp = 안겹치는때(out_dir, dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    db_copy = snapshot(db_path, out_dir, stamp=stamp)
    # **행 수를 못 세도 백업은 이어 간다** — 여기서 멈추면 VAPID·업로드가 안 남는다
    try:
        rows = write_rows(out_dir, stamp)
    except (sqlite3.Error, OSError):
        rows = None
    suspect = stamp in suspects(out_dir, stamps_in(out_dir))
    key_copy = copy_vapid(key_path, out_dir, stamp=stamp)
    uploads_copy, uploads_fresh = copy_uploads(uploads, out_dir, stamp=stamp)
    # **지우기 전에 센다** — 무엇이 몇 판 있었고 몇 판이 지워졌는지가 로그에 남아야
    # 「어제까지 있던 판이 왜 없나」 를 되짚을 수 있다(2026-09-30)
    전판 = stamps_in(out_dir)
    지킬판 = sum(1 for s in 전판 if s in 지키는판)
    못지움: list[tuple[str, str]] = []
    removed = prune(out_dir, keep=keep, max_total=max_total, 실패=못지움)
    # 지운 판의 **이름**도 남긴다(2026-10-01) — 수만 남으면 어떤 판이 사라졌는지 되짚을 수 없다
    지운이름 = sorted(set(전판) - set(stamps_in(out_dir)))
    지운판 = len(지운이름)
    알림수, 알림못함 = 알린다(db_path, out_dir)
    write_readme(out_dir)
    return {
        "ok": True,
        "db": db_copy,
        "rows": rows["total"] if rows else None,
        # 비었거나 터무니없이 적어 정리에서 뺀 판인가 (SUSPECT_RATIO)
        "suspect": suspect,
        # 의심 판을 앱 알림에 새로 세운 수 · 못 세웠으면 그 까닭
        "notified": 알림수,
        "notify_error": 알림못함,
        "vapid": key_copy,
        "uploads": uploads_copy,
        # 바뀐 것이 없어 지난 zip 에 이어 붙였는가
        "uploads_fresh": uploads_fresh,
        "removed": len(removed),
        # 지우기 전 판 수 · 그중 지킬 판 · 지운 판 수 (파일 수가 아니라 날짜 묶음 수)
        "before": len(전판),
        "protected": 지킬판,
        "removed_stamps": 지운판,
        "removed_names": 지운이름,
        # 못 지운 것 — (판, 까닭). 백업 자체는 성공이라 멈추지 않고 한 줄로 알린다
        "prune_failed": 못지움,
        "kept": len(list(out_dir.glob("app-*.db"))),
        # 이번 회차가 몇 MB 인지 · 전체가 몇 MB 인지
        "size": disk_used(files_of(out_dir, stamp)),
        "total": disk_used(
            path for one in stamps_in(out_dir) for path in files_of(out_dir, one)
        ),
    }


정리줄_최대이름 = 10       # 한 줄에 이름을 이만큼까지 — 넘으면 「외 N판」


def _이름들(이름: list[str]) -> str:
    앞 = ", ".join(이름[:정리줄_최대이름])
    return 앞 + (f" 외 {len(이름) - 정리줄_최대이름}판" if len(이름) > 정리줄_최대이름 else "")


def 정리줄(result: dict) -> list[str]:
    """정리 로그 — **지운 판이 없으면 아무 줄도 안 낸다** (2026-10-01).

    지웠으면 지우기 전 수 · 지킨 판 수 · 지운 판 수 · 파일 수와 **지운 판의 이름**(앞 10개와
    나머지 수)을 한 줄에. 못 지운 것이 있으면 그 판의 이름과 까닭을 한 줄 더.
    매일 「지운 것 없음」 이 쌓이면 진짜 줄이 묻혀서 없을 때는 침묵한다.
    """
    줄 = []
    if result.get("removed_stamps"):
        줄.append(f"  정리: 지우기 전 {result['before']}판 (지킬 판 {result['protected']})"
                 f" → 지운 판 {result['removed_stamps']} (파일 {result['removed']}개): "
                 + _이름들(result.get("removed_names", [])))
    실패 = result.get("prune_failed") or []
    if 실패:
        판들 = sorted({s for s, _ in 실패})
        까닭 = 실패[0][1] + (f" 외 {len(실패) - 1}건" if len(실패) > 1 else "")
        줄.append(f"  !! 정리하다 못 지운 판 {len(판들)}: {_이름들(판들)} — {까닭}")
    return 줄


def mb(size: int) -> str:
    return f"{size / (1024 * 1024):,.1f}MB"


if __name__ == "__main__":
    if 자리문제:
        print(자리문제)
        raise SystemExit(78)
    if sys.argv[1:] == ["--자리"]:
        # 셸이 위치를 따로 셈하지 않게 여기서 물어본다(맥의 백업.sh · 백업점검.sh)
        print(BACKUP_DIR)
        raise SystemExit(0)
    if sys.argv[1:2] == ["--신선도"]:
        # 앱 밖 · 읽기만 — 0 싱싱함 · 1 오래됨(또는 판 없음). 부르는 쪽이 한 줄로 남긴다
        try:
            기준 = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
        except ValueError:
            print("--신선도 뒤에는 시간(숫자)을 줍니다")
            raise SystemExit(78)
        괜찮나, 말 = 신선도(BACKUP_DIR, 기준)
        print(말)
        raise SystemExit(0 if 괜찮나 else 1)
    if sys.argv[1:] == ["--살핀다"]:
        # 앱 밖 자리 — DB 를 안 열고 백업 폴더만 읽는다(되살아나나.ps1 이 부른다)
        줄들 = 살핀다()
        print("\n".join(줄들) if 줄들 else "  빈 판 없음")
        raise SystemExit(0)
    result = run()
    if not result["ok"]:
        print("백업하지 못했습니다 —", result["reason"])
        raise SystemExit(1)
    print(f"백업했습니다: {result['db'].name} ({mb(result['db'].stat().st_size)} · "
          + (f"행 {result['rows']:,})" if result["rows"] is not None else "행 수를 못 셌습니다)"))
    if result["notify_error"]:
        print(f"  !! 빈 판 경고를 앱 알림에 못 세웠습니다 — {result['notify_error']}")
    elif result["notified"]:
        print(f"  빈 판 경고를 앱 알림에 세웠습니다 ({result['notified']}건)")
    if result["suspect"]:
        print("  !! 이 백업은 비었거나 터무니없이 적습니다 — 정리 대상에서 뺐습니다."
              " 운영 DB 가 비지 않았는지 보세요 (봐둘것 AZ-a)")
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
    # 지운 판이 있을 때만 이름과 함께 · 못 지운 것은 이름과 까닭 (정리줄)
    for 줄 in 정리줄(result):
        print(줄)
    # 이번 회차가 몇 MB 인지 찍는다 — 안 찍으면 어느 날 갑자기 디스크가 차 있다
    print(f"  이번 백업 {mb(result['size'])} · 전체 {mb(result['total'])}"
          f" (기준 {mb(MAX_TOTAL_BYTES)})")
    # 지키는 판을 갈라 적는다 — 한 수로 적으면 한도(KEEP)를 넘은 것처럼 읽힌다. 「그 밖」 에는
    # 의심 판도 들 수 있어 「성한 판 N」 이라고 단정하지 않는다
    print(f"  보관 중 {result['kept']}개 (지키는 판 {result['protected']}"
          f" + 그 밖 {result['kept'] - result['protected']} · 성한 판은 최대 {KEEP}개)")
