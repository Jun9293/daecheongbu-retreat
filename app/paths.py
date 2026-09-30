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


def 백업자리() -> tuple[Path | None, str | None]:
    """백업 위치 — **`DCB_BACKUP_DIR` 을 읽는 곳은 여기 하나다** (2026-09-30).

    `scripts/backup.py`(뜨는 쪽) · 설정 › 점검(마지막 시각) · 자가진단(용량) · 맥의 셸
    (`backup.py --자리` 로 물어본다)이 전부 이것을 부른다. 전에는 점검과 자가진단이
    `data/backups` 를 박아 두고 읽어서, 위치를 옮기면 두 화면이 옛 자리를 봤다.

    돌려주는 것은 (자리, 문제). **문제가 있으면 자리는 None** — 기본값으로 물러서면
    틀린 값을 준 사람이 모르는 채 다른 자리를 보게 된다.
    - 비었거나 빈칸뿐 → 기본 `<데이터>/backups`
    - 상대 경로 → 쓰지 않는다(어디를 기준으로 할지 부르는 자리마다 달라진다)
    - 끝의 `/` · 겹친 `/` → 정리한다
    **읽기만 한다** — 폴더가 있는지는 안 본다(그것은 `백업자리_문제`).
    """
    값 = os.environ.get("DCB_BACKUP_DIR", "").strip()
    if not 값:
        return DATA_DIR / "backups", None
    if not os.path.isabs(값):
        return None, "DCB_BACKUP_DIR 이 절대 경로가 아니라 쓰지 않습니다"
    return Path(os.path.normpath(값)), None


def 백업자리_문제(자리: Path) -> str | None:
    """그 자리를 **읽을 수 있나** — 없으면 None, 있으면 까닭 한 줄. 폴더를 만들지 않는다."""
    try:
        if not 자리.exists():
            return f"백업 폴더가 없습니다: {자리}"
        if not 자리.is_dir():
            return f"백업 자리가 폴더가 아닙니다: {자리}"
        if not os.access(자리, os.R_OK | os.X_OK):
            return f"백업 폴더를 읽을 수 없습니다(권한): {자리}"
        next(자리.iterdir(), None)
    except OSError as exc:
        return f"백업 폴더를 읽지 못했습니다: {자리} — {exc.strerror or exc}"
    return None
