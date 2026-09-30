"""옮기는 자료가 같은지 두 기계에서 같은 방식으로 잰다 — **읽기만 한다** (docs/맥-이전.md 8장).

윈도우와 맥에서 각각 돌려 **출력 두 개를 나란히 놓고** 견준다. 출력은 늘 같은 차례라
그대로 견줄 수 있다. DB 는 읽기 전용으로 열고(`backup.count_rows`), 기본으로는 아무 파일도
쓰지 않는다 — `--저장` 일 때만 아래의 그 한 자리에 쓴다.

    .venv\\Scripts\\python.exe scripts\\옮김확인.py
    .venv/bin/python scripts/옮김확인.py
    .venv/bin/python scripts/옮김확인.py <데이터 폴더>
    .venv/bin/python scripts/옮김확인.py --저장 윈도우

**출력은 채팅·보고에 붙이지 않는다** — 지문이 들어 있다(값은 아니지만 옮길 이유가 없다).
그래서 첫 줄이 늘 그 경고이고, **기본은 화면에만** 낸다. 견주려고 파일로 남길 때는
`--저장 <이름>` 으로 **`data/옮김확인/<이름>.txt` 에만** 쓴다 — 그 폴더는 `.gitignore` 에
있다. 다른 자리로는 쓰지 않는다(리다이렉트로 아무 데나 남기면 그 자리가 새는 곳이 된다).

재는 것 — 옮길 묶음(`app.db` · `uploads/` · `vapid_private.pem` · `secret_key.txt` ·
`anthropic_key.txt`)의 파일 수 · 바이트 · 짧은 지문(sha256 앞 12자), DB 의 무결성
검사와 표마다 행 수. **비밀 파일은 내용을 안 찍는다** — 크기와 지문만(지문으로는 값을
되살릴 수 없다). 백업 폴더와 `*.real.*` 같은 작업 자료는 옮길 묶음이 아니라 안 센다.
"""

from __future__ import annotations

import hashlib
import pathlib
import sqlite3
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from app.paths import DATA_DIR    # noqa: E402  — 폴더를 만들지 않는 쪽
import backup                     # noqa: E402  — 행 수는 백업과 같은 함수로 센다

낱파일 = ("app.db", "vapid_private.pem", "secret_key.txt", "anthropic_key.txt")


def 지문(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for 조각 in iter(lambda: f.read(1 << 20), b""):
            h.update(조각)
    return h.hexdigest()[:12]


def 잰다(data: pathlib.Path) -> list[str]:
    줄 = [f"데이터 폴더: {data.name}/"]
    수 = 크기 = 0
    for 이름 in 낱파일:
        p = data / 이름
        if p.is_file():
            n = p.stat().st_size
            수 += 1
            크기 += n
            줄.append(f"  {이름:<20} {n:>12,} 바이트  지문 {지문(p)}")
        else:
            줄.append(f"  {이름:<20} 없음")
    up = data / "uploads"
    파일들 = sorted(x for x in up.rglob("*") if x.is_file()) if up.is_dir() else []
    묶음 = hashlib.sha256()
    up크기 = 0
    for x in 파일들:
        n = x.stat().st_size
        up크기 += n
        묶음.update(f"{x.relative_to(up).as_posix()}|{n}|{지문(x)}\n".encode())
    줄.append(f"  {'uploads/':<20} 파일 {len(파일들)}개 · {up크기:,} 바이트  지문 {묶음.hexdigest()[:12]}")
    수 += len(파일들)
    크기 += up크기
    줄.append(f"옮길 묶음: 파일 {수}개 · {크기:,} 바이트")

    db = data / "app.db"
    if db.is_file():
        conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
        try:
            검사 = conn.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            conn.close()
        행 = backup.count_rows(db)
        줄.append(f"DB 무결성: {검사} · 표 {len(행['tables'])}개 · 행 합 {행['total']:,}")
        for 표, n in 행["tables"].items():
            줄.append(f"  {표:<32} {n:>8,}")
    return 줄


경고 = "!! 이 출력은 채팅·보고에 붙이지 말 것 — 지문이 들어 있습니다 (두 기계의 출력끼리만 견줍니다)"
저장폴더이름 = "옮김확인"          # data/ 아래 — .gitignore 의 data/옮김확인/ 와 같은 이름


def 저장할곳(data: pathlib.Path, 이름: str) -> pathlib.Path:
    """**이름만 받는다** — 경로를 받으면 아무 데나 쓸 수 있게 된다."""
    if not 이름 or any(c in 이름 for c in "/\\:") or 이름.startswith("."):
        raise SystemExit(f"--저장 에는 경로가 아니라 이름만 줍니다(예: 윈도우 · 맥): {이름!r}")
    return data / 저장폴더이름 / f"{이름}.txt"


if __name__ == "__main__":
    남은것 = sys.argv[1:]
    저장이름 = None
    if "--저장" in 남은것:
        i = 남은것.index("--저장")
        if i + 1 >= len(남은것):
            raise SystemExit("--저장 뒤에 이름을 줍니다(예: --저장 윈도우)")
        저장이름 = 남은것[i + 1]
        del 남은것[i:i + 2]
    대상 = pathlib.Path(남은것[0]) if 남은것 else DATA_DIR
    if not 대상.is_dir():
        print(f"데이터 폴더가 없습니다: {대상}")
        raise SystemExit(1)
    글 = "\n".join([경고] + 잰다(대상))
    if 저장이름 is None:
        print(글)
    else:
        곳 = 저장할곳(대상, 저장이름)
        곳.parent.mkdir(exist_ok=True)
        곳.write_text(글 + "\n", encoding="utf-8")
        # 저장할 때는 화면에 내용을 안 낸다 — 경고와 자리만
        print(경고)
        print(f"저장했습니다: {곳.parent.name}/{곳.name} (저장소에 안 올라갑니다)")
