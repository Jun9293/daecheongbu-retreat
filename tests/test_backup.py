"""백업 (CLAUDE.md 운영). 수용 기준 11, 12.

임시 DB 로 시험한다. 실제 데이터 폴더를 건드리지 않는다.
"""

from __future__ import annotations

import sqlite3

import pytest

from scripts import backup


@pytest.fixture
def sample(tmp_path):
    """작은 SQLite 파일과 VAPID 키 하나."""
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE note (id INTEGER PRIMARY KEY, body TEXT)")
    conn.executemany("INSERT INTO note (body) VALUES (?)", [("가",), ("나",)])
    conn.commit()
    conn.close()

    key_path = tmp_path / "vapid_private.pem"
    key_path.write_text("-----BEGIN PRIVATE KEY-----\n가짜\n", encoding="utf-8")
    return {"db": db_path, "key": key_path, "out": tmp_path / "backups"}


def test_11_VACUUM_INTO_로_복사하고_VAPID_키도_남긴다(sample):
    result = backup.run(
        db_path=sample["db"], key_path=sample["key"], out_dir=sample["out"]
    )
    assert result["ok"] is True

    copied = result["db"]
    assert copied.exists() and copied.parent == sample["out"]
    assert copied.name.startswith("app-") and copied.suffix == ".db"

    # 복사본이 실제로 열리고 내용이 같다 (반쯤 쓰인 파일이면 여기서 깨진다)
    conn = sqlite3.connect(copied)
    rows = [r[0] for r in conn.execute("SELECT body FROM note ORDER BY id")]
    conn.close()
    assert rows == ["가", "나"]

    assert result["vapid"] is not None
    assert result["vapid"].exists()
    assert "가짜" in result["vapid"].read_text(encoding="utf-8")


def test_11b_파일_복사가_아니라_VACUUM_INTO_다():
    """쓰는 중에 복사하면 깨진 파일이 남는다. 그 파일은 열릴 때까지 멀쩡해 보인다."""
    import inspect

    source = inspect.getsource(backup.snapshot)
    assert "VACUUM INTO" in source
    assert "shutil.copy" not in source


def test_11c_VAPID_키가_없어도_DB_는_백업된다(sample):
    sample["key"].unlink()
    result = backup.run(
        db_path=sample["db"], key_path=sample["key"], out_dir=sample["out"]
    )
    assert result["ok"] is True
    assert result["db"].exists()
    assert result["vapid"] is None


def test_11d_DB_가_없으면_사유를_말한다(tmp_path):
    result = backup.run(
        db_path=tmp_path / "없는파일.db", key_path=tmp_path / "x.pem",
        out_dir=tmp_path / "backups",
    )
    assert result["ok"] is False
    assert "DB 파일이 없습니다" in result["reason"]


def test_12_30개를_넘으면_오래된_것부터_지운다(sample):
    out = sample["out"]
    out.mkdir(parents=True, exist_ok=True)
    # 오래된 것 35개를 만들어 둔다 (DB 와 키를 짝지어서)
    for i in range(35):
        stamp = f"20260101-{i:06d}"
        (out / f"app-{stamp}.db").write_text("옛것", encoding="utf-8")
        (out / f"vapid-{stamp}.pem").write_text("옛키", encoding="utf-8")

    result = backup.run(
        db_path=sample["db"], key_path=sample["key"], out_dir=out, keep=30
    )
    assert result["ok"] is True

    remaining = sorted(p.name for p in out.glob("app-*.db"))
    assert len(remaining) == 30
    assert result["db"].exists()                       # 방금 만든 것은 남는다
    # 옛것 35개 + 방금 1개 = 36개 중 오래된 6개가 지워진다
    assert "app-20260101-000000.db" not in remaining
    assert "app-20260101-000005.db" not in remaining      # 여섯 번째까지 지워진다
    assert "app-20260101-000006.db" in remaining
    # 짝지은 키도 함께 지워졌다
    assert not (out / "vapid-20260101-000000.pem").exists()
    assert (out / "vapid-20260101-000006.pem").exists()


def test_12b_기본_보관_개수는_30이다():
    assert backup.KEEP == 30


def test_11c_같은_초에_두_번_돌아도_앞_판을_덮지_않는다(sample, tmp_path, monkeypatch):
    """판 이름이 초 단위라 같은 초에 두 번 돌면 뒤엣것이 앞 판을 덮었다 (2026-09-30 재현).
    그 사이에 DB 가 바뀌면 앞 판을 말없이 잃는다. **이름을 붙여 둘 다 남겨야 한다.**"""
    import datetime as real_dt

    class 고정(real_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 30, 3, 0, 0)

    monkeypatch.setattr(backup.dt, "datetime", 고정)
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "a.txt").write_text("첨부", encoding="utf-8")
    인자 = dict(db_path=sample["db"], key_path=sample["key"], uploads=uploads, out_dir=sample["out"])

    첫 = backup.run(**인자)
    conn = sqlite3.connect(sample["db"])
    conn.execute("INSERT INTO note (body) VALUES ('다')")
    conn.commit()
    conn.close()
    둘 = backup.run(**인자)
    셋 = backup.run(**인자)

    assert [첫["db"].name, 둘["db"].name, 셋["db"].name] == [
        "app-20260930-030000.db", "app-20260930-030000-02.db", "app-20260930-030000-03.db"]
    # 앞 판은 그대로다 — 덮였으면 3 행이다
    n = sqlite3.connect(f"file:{첫['db']}?mode=ro", uri=True).execute("SELECT count(*) FROM note").fetchone()[0]
    assert n == 2
    # 날짜 묶음마다 제 짝이 있다(업로드 zip 은 이름이 달라 이어 붙는다)
    for r in (첫, 둘, 셋):
        stamp = r["db"].stem.split("-", 1)[1]
        assert r["vapid"].name == f"vapid-{stamp}.pem" and r["uploads"].name == f"uploads-{stamp}.zip"
    # 붙인 쪽이 더 최근으로 선다
    assert backup.stamps_in(sample["out"])[:3] == ["20260930-030000-03", "20260930-030000-02", "20260930-030000"]
    # 다른 스크립트가 부르는 snapshot 도 덮지 않는다
    사본 = backup.snapshot(sample["db"], sample["out"], stamp="20260930-030000")
    assert 사본.name == "app-20260930-030000-04.db"


def test_11d_신선도는_마지막_성한_판의_나이를_보고_읽기만_한다(tmp_path):
    """빈 판은 「백업이 있다」 에 안 센다 — 그 판으로는 되돌릴 수 없다. 옆 파일도 안 쓴다."""
    import datetime as real_dt

    out = tmp_path / "backups"
    out.mkdir()
    지금 = real_dt.datetime(2026, 9, 30, 12, 0, 0)

    def 판(시간전, 회차):
        p = out / f"app-{(지금 - real_dt.timedelta(hours=시간전)):%Y%m%d-%H%M%S}.db"
        c = sqlite3.connect(p)
        c.execute("CREATE TABLE retreats (id INTEGER PRIMARY KEY)")
        c.executemany("INSERT INTO retreats DEFAULT VALUES", [()] * 회차)
        c.commit()
        c.close()

    assert backup.신선도(tmp_path / "없음", 30, now=지금)[0] is False
    assert backup.신선도(out, 30, now=지금)[0] is False          # 판이 없다
    판(40, 2)
    판(40.5, 2)
    판(5, 0)                                                   # 가장 최근은 빈 판
    괜찮나, 말 = backup.신선도(out, 30, now=지금)
    assert 괜찮나 is False and "40.0시간" in 말
    assert backup.신선도(out, 48, now=지금)[0] is True
    assert not list(out.glob("*.rows.json")), "읽기만 해야 한다"
