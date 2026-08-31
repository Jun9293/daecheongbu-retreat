"""환경설정. 모든 값은 환경변수로 덮어쓸 수 있다."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DCB_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
# 작업 파일(Phase 2) 저장 위치. 영수증과 섞이지 않게 분리한다.
ASSET_DIR = UPLOAD_DIR / "assets"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ASSET_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("DCB_DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")

# 세션 쿠키 서명 키.
#
# **파일로 고정한다.** 매번 새로 만들면 서버를 재시작할 때마다 전원이 로그아웃되고,
# 소스에 박아 두면 저장소를 보는 사람이 세션을 위조할 수 있다.
# 환경변수(DCB_SECRET_KEY)가 있으면 그것을 쓰고, 없으면 데이터 폴더에 만들어 둔다.
def _secret_key() -> str:
    from_env = os.environ.get("DCB_SECRET_KEY")
    if from_env:
        return from_env
    path = DATA_DIR / "secret_key.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    import secrets

    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="utf-8")
    return value


SECRET_KEY = _secret_key()
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

# 웹 푸시 VAPID 연락처 (규격상 mailto: 또는 https: 여야 함)
PUSH_CONTACT = os.environ.get("DCB_PUSH_CONTACT", "mailto:admin@example.com")

# 위험 자동 점검 주기 (초). 0이면 자동 점검을 끈다.
RISK_SCAN_INTERVAL_SECONDS = int(os.environ.get("DCB_RISK_SCAN_INTERVAL", str(60 * 60)))
