"""환경설정. 모든 값은 환경변수로 덮어쓸 수 있다."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DCB_DATA_DIR", BASE_DIR / "data"))

# ── 올라온 파일은 전부 이 아래에 있다 ───────────────────────────────
#
# 경로를 한 군데로 모으는 이유는 백업 때문이다. 파일은 DB 밖에 쌓이므로
# app.db 만 남기면 첨부가 통째로 빠지는데, **그 실패가 조용하다** —
# 되돌리고 나서야 목록에 있는 파일이 열리지 않는 것으로 알게 된다.
# scripts/backup.py 는 UPLOAD_DIR 하나만 보면 되도록 여기서 정한다.
UPLOAD_DIR = DATA_DIR / "uploads"
# 작업 파일(Phase 2) 저장 위치. 영수증과 섞이지 않게 분리한다.
ASSET_DIR = UPLOAD_DIR / "assets"
# 업무 상세 패널의 첨부파일 (CLAUDE.md 4-9). 회차별이라 TaskRun 에 붙는다.
ATTACHMENT_DIR = UPLOAD_DIR / "attachments"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ASSET_DIR.mkdir(parents=True, exist_ok=True)
ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("DCB_DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")

# 세션 쿠키 서명 키.
#
# **파일로 고정한다.** 매번 새로 만들면 서버를 재시작할 때마다 전원이 로그아웃되고,
# 소스에 박아 두면 저장소를 보는 사람이 세션을 위조할 수 있다.
# 환경변수(DCB_SECRET_KEY)가 있으면 그것을 쓰고, 없으면 데이터 폴더에 만들어 둔다.
#
# **어디서 왔는지를 반드시 남긴다.** 이 값이 조용히 바뀌면 증상은 "재시작할 때마다
# 로그인이 풀린다" 인데, 어디에도 아무 말이 없어 원인을 좁힐 수가 없다.
# 그래서 출처(SECRET_KEY_SOURCE)와 지문(SECRET_KEY_FINGERPRINT)을 함께 두고
# 앱이 뜰 때 로그에 적는다 — 지문이 재시작마다 달라지면 그게 답이다.
# **키 자체는 절대 로그에 남기지 않는다.** 로그가 새면 세션을 위조할 수 있다.
SECRET_KEY_PATH = DATA_DIR / "secret_key.txt"


def _read_key_file(path: Path) -> str | None:
    """파일에 쓸 만한 키가 있으면 그것. 없거나 비었으면 None.

    **빈 파일을 키로 쓰지 않는다.** 쓰다 만 파일이 남았을 때 빈 문자열로 서명하면
    누구나 세션을 위조할 수 있는데 화면에는 아무 표시도 나지 않는다.
    """
    if not path.exists():
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:                                       # noqa: BLE001
        raise RuntimeError(
            f"세션 키 파일을 읽지 못했습니다: {path}\n"
            f"  {exc}\n"
            "  이 파일을 읽지 못하면 재시작할 때마다 전원이 로그아웃됩니다.\n"
            "  파일 권한을 확인하거나, DCB_SECRET_KEY 환경변수로 직접 주세요."
        ) from None
    return value or None


def _write_key_file(path: Path, value: str) -> None:
    """새 키를 파일에 남긴다. **남았는지 읽어서 확인한다.**

    쓰기가 성공한 것처럼 보이고 실제로는 남지 않는 경우가 있다 —
    윈도우의 UAC 파일 가상화, 매번 지워지는 임시 폴더, 다른 계정으로 도는 서비스.
    그러면 재시작마다 새 키가 만들어지고 **아무 오류도 나지 않은 채** 전원이
    로그아웃된다. 되짚을 근거가 없는 실패라 여기서 미리 막는다.
    """
    try:
        path.write_text(value, encoding="utf-8")
    except OSError as exc:                                       # noqa: BLE001
        raise RuntimeError(
            f"세션 키 파일을 만들지 못했습니다: {path}\n"
            f"  {exc}\n"
            "  이 파일이 남지 않으면 재시작할 때마다 전원이 로그아웃됩니다.\n"
            "  폴더에 쓸 수 있는지 확인하거나, DCB_SECRET_KEY 환경변수로 직접 주세요."
        ) from None

    if _read_key_file(path) != value:
        raise RuntimeError(
            f"세션 키를 저장했는데 다시 읽으니 달라졌습니다: {path}\n"
            "  쓰기가 실제로는 다른 곳으로 갔을 수 있습니다"
            " (윈도우 파일 가상화 · 임시 폴더 · 다른 계정으로 도는 서비스).\n"
            "  이대로 두면 재시작할 때마다 전원이 로그아웃됩니다.\n"
            "  DCB_SECRET_KEY 환경변수로 직접 주면 확실합니다."
        )


def _secret_key() -> tuple[str, str]:
    """(키, 출처). 출처는 사람이 읽는 말이다."""
    from_env = os.environ.get("DCB_SECRET_KEY")
    if from_env:
        return from_env, "환경변수 DCB_SECRET_KEY"

    existing = _read_key_file(SECRET_KEY_PATH)
    if existing:
        return existing, f"파일 {SECRET_KEY_PATH}"

    import secrets

    value = secrets.token_urlsafe(48)
    _write_key_file(SECRET_KEY_PATH, value)
    return value, f"새로 만듦 → {SECRET_KEY_PATH}"


SECRET_KEY, SECRET_KEY_SOURCE = _secret_key()


def secret_key_fingerprint(key: str | None = None) -> str:
    """키의 지문 8자리. **키 자체는 절대 드러내지 않는다.**

    재시작 전후로 이 값이 같으면 세션은 유지된다. 다르면 그것이 로그아웃의 원인이다.
    """
    import hashlib

    return hashlib.sha256((key or SECRET_KEY).encode("utf-8")).hexdigest()[:8]


SECRET_KEY_FINGERPRINT = secret_key_fingerprint()

SESSION_COOKIE = "dcb_session"
# 초대 링크를 한 번 열면 그 기기에서 계속 로그인된 상태로 둔다 (CLAUDE.md 4-12).
SESSION_MAX_AGE = 60 * 60 * 24 * 90  # 90일


# 식대 1인당 지원 상한 기본값 (회차별로 재설정 가능 — 하드코딩 금지 원칙)
DEFAULT_MEAL_SUBSIDY_PER_PERSON = 8_000

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_UPLOAD_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".heic"}

# ------------------------------------------------------------------ Phase 2

# 작업 파일은 영수증보다 크다 (포스터 원본, 영상 등)
MAX_ASSET_BYTES = int(os.environ.get("DCB_MAX_ASSET_MB", "50")) * 1024 * 1024
ALLOWED_ASSET_EXTS = ALLOWED_UPLOAD_EXTS | {
    ".psd", ".ai", ".zip", ".pptx", ".ppt", ".xlsx", ".xls", ".docx", ".doc",
    ".hwp", ".hwpx", ".mp4", ".mov", ".mp3", ".wav", ".txt", ".csv", ".svg",
}

# ── 업무 첨부파일 (CLAUDE.md 4-9) ────────────────────────────────────
#
# 상한을 정해 두는 이유는 거절할 때 **이유를 말할 수 있게** 하기 위해서다.
# 상한이 없으면 디스크가 찰 때까지 받다가 어느 날 아무 설명 없이 실패한다.
#
# **200MB 인 이유는 실제로 그만한 것을 올리기 때문이다.** 25MB 로 두었더니
# 이미지 원본·PPT·PDF 가 막혔고, 가장 큰 것이 164MB 였다. 상한은 짐작이
# 아니라 실제로 오간 것에서 나와야 한다.
#
# **숫자만 올리면 안 된다.** 큰 파일은 세 곳에 같이 닿는다 —
#   · 백업 (scripts/backup.py) — 매일 새벽 통째로 복사하면 디스크가 금세 찬다
#   · 디스크 여유 (scripts/healthcheck.py) — 조용히 차다가 어느 날 실패한다
#   · 올리는 동안의 화면 — 몇 분이 걸리므로 아무 반응이 없으면 창을 닫는다
MAX_ATTACHMENT_BYTES = int(os.environ.get("DCB_MAX_ATTACHMENT_MB", "200")) * 1024 * 1024
ALLOWED_ATTACHMENT_EXTS = {
    # 이미지 — 원본을 그대로 올리는 일이 많아 RAW 와 TIFF 까지 받는다
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".svg",
    ".tif", ".tiff", ".bmp", ".cr2", ".nef", ".arw", ".dng",
    # 문서
    ".pdf", ".txt", ".csv", ".md",
    ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # 디자인 · 묶음
    ".psd", ".ai", ".eps", ".indd", ".zip", ".7z", ".rar",
    # 소리 · 영상 (영상은 링크로 붙이는 편이 낫지만, 짧은 것은 올라온다)
    ".mp3", ".m4a", ".wav", ".flac", ".aac",
    ".mp4", ".mov", ".webm", ".mkv", ".avi",
}

# ── 디스크 여유 ──────────────────────────────────────────────────────
#
# 상한을 200MB 로 올린 순간 "디스크가 언제 차는가" 가 현실이 된다.
# 지금까지는 찰 때까지 받다가 **아무 설명 없이** 실패하는 구조였다.
#
#   · 올릴 때 — 받고 나서도 이만큼은 남아야 한다. 안 되면 이유를 말하고 거절한다.
#     받아 놓고 나중에 깨지는 것보다 낫다
#   · 자가진단 — 이보다 적으면 [문제] 로 낸다. 거절이 시작되기 **전에** 알아야 한다
#
# 거절선보다 경고선을 넉넉히 두는 이유는, 경고를 보고 치울 시간이 있어야
# 하기 때문이다. 둘이 같으면 "경고"가 곧 "이미 막힘"이다.
DISK_FREE_FLOOR_BYTES = int(os.environ.get("DCB_DISK_FLOOR_MB", "2048")) * 1024 * 1024
DISK_FREE_WARN_BYTES = int(os.environ.get("DCB_DISK_WARN_MB", "5120")) * 1024 * 1024

# 웹 푸시 VAPID 연락처 (규격상 mailto: 또는 https: 여야 함)
PUSH_CONTACT = os.environ.get("DCB_PUSH_CONTACT", "mailto:admin@example.com")

# 위험 자동 점검 주기 (초). 0이면 자동 점검을 끈다.
RISK_SCAN_INTERVAL_SECONDS = int(os.environ.get("DCB_RISK_SCAN_INTERVAL", str(60 * 60)))

# ── 바깥에서 보이는 주소 ──────────────────────────────────────────────
#
# **초대 링크는 완성된 채로 나가야 합니다.** 전에는 주소 앞부분을 자리표시자로
# 찍어 두고 사람이 매번 손으로 갈아 끼웠는데, 그러다 토큰까지
# 건드려 링크가 깨졌습니다 — 하루에 대여섯 번씩 그랬습니다.
# 자리표시자를 남기지 않습니다. 붙여넣으면 바로 열려야 합니다.
#
# 앱은 `127.0.0.1:8000` 에만 열려 있고 바깥은 Cloudflare Tunnel 로 들어오므로
# (11-2), 서버가 자기 주소로 아는 값(`request.base_url`)은 `127.0.0.1` 입니다.
# 그래서 **바깥 주소는 여기서 따로 정합니다.**
BASE_URL = os.environ.get("DCB_BASE_URL", "https://retreat.recba12.com").rstrip("/")
