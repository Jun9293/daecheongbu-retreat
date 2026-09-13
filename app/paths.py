"""데이터 경로만 — **폴더를 만들지 않고 파일을 쓰지 않는다.**

`app.config` 는 읽히는 순간 데이터 폴더를 만들고 서명키가 없으면 새로 쓴다. 앱이 뜨는
자리에는 그것이 맞지만, **읽기만 하는 자리**(`scripts/backup.py --살핀다`)가 그것을
부르면 `data/` 가 통째로 빈 사고 직후에 흔적을 남긴다 — 무엇이 원래 있던 것인지
흐려진다(2026-09-13 에 사람이 정함). 그래서 경로를 셈하는 곳을 여기로 떼고
`app.config` 도 이것을 받아 쓴다 — 경로를 두 곳에서 셈하면 갈린다.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DCB_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
