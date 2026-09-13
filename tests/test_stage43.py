"""빈 백업을 정리 대상에서 뺀다 — 2026-09-13 (봐둘것 AZ-a).

시험이 운영 DB 를 비운 날 새벽 3시 백업이 빈 DB 를 떴다. 개수(30)로 지우면
빈 판이 하루 한 칸씩 성한 판을 밀어낸다. `scripts/backup.py` 가 뜰 때 행 수를
옆 파일에 남기고, **의심스러운 판은 세지도 지우지도 않는지** 잰다.

**수를 박지 않는다** — 기준은 `backup.SUSPECT_RATIO` 에서 끌어오고, 판의 행 수는
만들 때 정한 값을 그 자리에서 센다. 백업은 `tmp_path` 에 만든다 — 운영 백업
폴더에 대고 재지 않는다.
"""

from __future__ import annotations

import json
import sqlite3

from scripts import backup


def _판(out, stamp, *, 회차, 행):
    """앱과 같은 꼴(`retreats` 표가 있는) 백업 하나."""
    out.mkdir(parents=True, exist_ok=True)
    이음 = sqlite3.connect(out / f"app-{stamp}.db")
    이음.execute("CREATE TABLE retreats (id INTEGER PRIMARY KEY)")
    이음.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY)")
    이음.executemany("INSERT INTO retreats DEFAULT VALUES", [()] * 회차)
    이음.executemany("INSERT INTO notes DEFAULT VALUES", [()] * 행)
    이음.commit()
    이음.close()
    (out / f"vapid-{stamp}.pem").write_text("키", encoding="utf-8")


def _남은(out):
    return set(backup.stamps_in(out))


def test43_a01_빈_판은_남고_성한_판이_밀려나지_않는다(tmp_path):
    """성한 판 넷(오래됨) 뒤에 빈 판이 여럿 쌓여도, keep 칸은 성한 판이 채운다."""
    out = tmp_path / "backups"
    성한 = [f"20260901-00000{i}" for i in range(4)]
    빈 = [f"20260913-00000{i}" for i in range(3)]
    for s in 성한:
        _판(out, s, 회차=2, 행=200)
    for s in 빈:
        _판(out, s, 회차=0, 행=0)

    지운 = backup.prune(out, keep=3)

    assert _남은(out) >= set(빈), "빈 판을 지웠다 — 지울지는 사람이 정한다"
    assert _남은(out) >= set(성한[-3:]), "성한 판이 빈 판에 밀려났다"
    assert 성한[0] not in _남은(out), "keep 을 넘는 성한 판은 여전히 지워야 한다"
    assert all("20260913" not in p.name for p in 지운)


def test43_a02_규칙이_없으면_이_판에서_성한_판을_잃는다(tmp_path, monkeypatch):
    """a01 의 판이 **실제로 무는지** — 의심을 끄면 성한 판이 지워져야 한다(③).
    끄고도 성한 판이 남으면 a01 은 아무것도 안 잰다."""
    out = tmp_path / "backups"
    성한 = [f"20260901-00000{i}" for i in range(4)]
    for s in 성한:
        _판(out, s, 회차=2, 행=200)
    for i in range(3):
        _판(out, f"20260913-00000{i}", 회차=0, 행=0)

    monkeypatch.setattr(backup, "suspects", lambda *_: set())
    backup.prune(out, keep=3)
    assert not (set(성한) <= _남은(out)), "의심을 꺼도 성한 판이 다 남는다 — 판이 안 문다"


def test43_a03_행이_터무니없이_적으면_회차가_있어도_의심이다(tmp_path):
    out = tmp_path / "backups"
    큰 = 1000
    _판(out, "20260901-000000", 회차=2, 행=큰)
    적은 = int(큰 * backup.SUSPECT_RATIO) - 10          # 기준 바로 아래
    _판(out, "20260902-000000", 회차=1, 행=적은)
    assert backup.suspects(out, backup.stamps_in(out)) == {"20260902-000000"}


def test43_a03b_회차가_0_이면_행이_많아도_의심이다(tmp_path):
    """상대 기준과 **따로** 무는지 — 회차 표만 비고 다른 표가 그대로인 판.
    b02 의 빈 판은 두 기준에 함께 걸려서, 회차 기준을 걷어도 초록이었다
    (고장을 심어 보고 알았다)."""
    out = tmp_path / "backups"
    _판(out, "20260901-000000", 회차=2, 행=200)
    _판(out, "20260902-000000", 회차=0, 행=200)
    assert backup.suspects(out, backup.stamps_in(out)) == {"20260902-000000"}


def test43_a04_절반으로_줄어든_판은_성한_판이다(tmp_path):
    """2026-09-10 에 계정 정리로 행이 실제로 절반 가까이 줄었다 — 그 판을 의심하면
    정당한 정리 뒤의 판이 영영 안 지워지고, 사람이 빈 판 경고를 믿지 않게 된다."""
    out = tmp_path / "backups"
    _판(out, "20260909-000000", 회차=2, 행=3000)
    _판(out, "20260910-000000", 회차=2, 행=1500)
    assert backup.suspects(out, backup.stamps_in(out)) == set()


def test43_b01_뜰_때_행_수를_옆_파일에_남긴다(tmp_path):
    """백업 파일을 안 열고도 성한지 안다 — 옆 파일의 수가 실제와 같은가."""
    db = tmp_path / "app.db"
    이음 = sqlite3.connect(db)
    이음.execute("CREATE TABLE retreats (id INTEGER PRIMARY KEY)")
    이음.executemany("INSERT INTO retreats DEFAULT VALUES", [()] * 3)
    이음.commit()
    이음.close()

    결과 = backup.run(db_path=db, key_path=tmp_path / "없음.pem",
                     uploads=tmp_path / "없음", out_dir=tmp_path / "backups")
    stamp = 결과["db"].stem.split("-", 1)[1]
    옆 = json.loads(backup.rows_path(tmp_path / "backups", stamp).read_text(encoding="utf-8"))
    assert 옆 == backup.count_rows(결과["db"])
    assert 옆["tables"]["retreats"] == 3 and 결과["rows"] == 옆["total"]
    assert 결과["suspect"] is False


def test43_b02_빈_운영을_뜨면_그렇다고_말한다(tmp_path):
    db = tmp_path / "app.db"
    이음 = sqlite3.connect(db)
    이음.execute("CREATE TABLE retreats (id INTEGER PRIMARY KEY)")
    이음.commit()
    이음.close()
    out = tmp_path / "backups"
    _판(out, "20260901-000000", 회차=2, 행=100)

    결과 = backup.run(db_path=db, key_path=tmp_path / "없음.pem",
                     uploads=tmp_path / "없음", out_dir=out)
    assert 결과["suspect"] is True
    assert "정리 대상에서 뺐습니다" in open(backup.__file__, encoding="utf-8").read()


def test43_b03_옆_파일은_그_판과_함께_지운다(tmp_path):
    """옆 파일만 남으면 없는 판의 수가 성한 것처럼 읽힌다."""
    out = tmp_path / "backups"
    for i in range(3):
        _판(out, f"20260901-00000{i}", 회차=2, 행=100)
    for s in backup.stamps_in(out):
        backup.rows_of(out, s)                     # 이 규칙 전의 판 — 한 번 세어 남긴다
    backup.prune(out, keep=1)
    assert sorted(p.name for p in out.glob("*.rows.json")) == ["app-20260901-000002.rows.json"]


def test43_c01_되돌리는_안내가_행_수를_먼저_보라고_한다():
    """이름이 가장 최근인 것이 성한 것이 아니다 — 백업 폴더를 여는 사람이 그 자리에서
    읽는 안내(`읽어보기.txt`)의 「되돌릴 때」 에 적힌다."""
    되돌릴때 = backup.README_TEXT.split("■ 되돌릴 때", 1)[1]
    assert "rows.json" in 되돌릴때 and "가장 최근" in 되돌릴때
