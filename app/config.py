"""환경설정. 모든 값은 환경변수로 덮어쓸 수 있다."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DCB_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("DCB_DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")

# 세션 쿠키 서명 키. 운영 배포 시 반드시 환경변수로 지정할 것.
SECRET_KEY = os.environ.get("DCB_SECRET_KEY", "dev-only-insecure-secret-change-me")
SESSION_COOKIE = "dcb_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30일

# SMS 발송 방식: "console"(개발용, 서버 로그에 코드 출력) | "solapi" | "aligo" 등
SMS_PROVIDER = os.environ.get("DCB_SMS_PROVIDER", "console")
# 개발 모드에서는 인증코드를 화면에 직접 노출해 로그인 테스트를 가능하게 한다.
DEV_MODE = os.environ.get("DCB_DEV_MODE", "1") == "1"

AUTH_CODE_TTL_SECONDS = 180
AUTH_CODE_MAX_ATTEMPTS = 5

# 식대 1인당 지원 상한 기본값 (회차별로 재설정 가능 — 하드코딩 금지 원칙)
DEFAULT_MEAL_SUBSIDY_PER_PERSON = 8_000

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_UPLOAD_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".heic"}
