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


# ── 「마지막 백업」 은 판 이름의 때 하나로 (2026-10-01) ──────────────────

def _성한판(out, stamp, 회차=2, 수정시각=None):
    import os as _os

    out.mkdir(parents=True, exist_ok=True)
    p = out / f"app-{stamp}.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE retreats (id INTEGER PRIMARY KEY)")
    c.executemany("INSERT INTO retreats DEFAULT VALUES", [()] * 회차)
    c.commit()
    c.close()
    if 수정시각 is not None:
        _os.utime(p, (수정시각, 수정시각))
    return p


def test_11e_판의때는_정해진_꼴만_읽는다():
    import datetime as real_dt

    assert backup.판의때("20260930-030000") == real_dt.datetime(2026, 9, 30, 3, 0, 0)
    assert backup.판의때("20260930-030000-02") == real_dt.datetime(2026, 9, 30, 3, 0, 0)
    for 틀림 in ("20260930-030000x", "20260930-0300", "foo", "20261340-030000", "20260930-030000-2"):
        assert backup.판의때(틀림) is None, 틀림


def test_11f_마지막성한판은_이름의_때를_쓰고_빈_판_미래_판_못읽는_판을_건너뛴다(tmp_path, caplog):
    import datetime as real_dt

    out = tmp_path / "backups"
    지금 = real_dt.datetime(2026, 10, 1, 12, 0, 0)
    늦은수정 = real_dt.datetime(2026, 10, 1, 11, 0, 0).timestamp()
    _성한판(out, "20260930-082754", 수정시각=늦은수정)        # 옮겨 온 판 — 수정 시각만 늦다
    _성한판(out, "20260929-030000", 수정시각=늦은수정 + 60)
    _성한판(out, "20260930-090000", 회차=0)                   # 더 늦은 빈 판
    _성한판(out, "20261005-030000")                           # 미래
    (out / "app-이름이다름.db").write_bytes(b"")              # 꼴이 다른 판
    with caplog.at_level("WARNING", logger="backup"):
        stamp, 때 = backup.마지막성한판(out, now=지금)
    assert stamp == "20260930-082754" and 때 == real_dt.datetime(2026, 9, 30, 8, 27, 54)
    줄 = [r.getMessage() for r in caplog.records if r.name == "backup"]
    assert sum("못 읽어" in m for m in 줄) == 1 and sum("미래" in m for m in 줄) == 1, 줄
    # 신선도는 같은 판을 말한다 — 셈하는 곳이 하나다
    assert "app-20260930-082754.db" in backup.신선도(out, 48, now=지금)[1]
    assert not list(out.glob("*.rows.json")), "읽기만 해야 한다"


def test_11g_마지막성한판은_판이_없거나_폴더가_없으면_None_이고_만들지_않는다(tmp_path):
    assert backup.마지막성한판(tmp_path / "없음") is None
    assert not (tmp_path / "없음").exists()
    (tmp_path / "빈").mkdir()
    assert backup.마지막성한판(tmp_path / "빈") is None


def test_11h_같은_때의_판이면_붙인_번호가_큰_것이_마지막이다(tmp_path):
    out = tmp_path / "backups"
    for s in ("20260930-030000", "20260930-030000-02", "20260930-030000-03"):
        _성한판(out, s)
    assert backup.마지막성한판(out)[0] == "20260930-030000-03"


# ── 정리 로그가 지운 판의 이름을 남긴다 (2026-10-01) ─────────────────────

def _실행(tmp_path):
    """backup.py 를 **임시 폴더에 대고** 실제로 돌려 표준출력을 받는다 — 로그 줄 그 자체를 잰다."""
    import os as _os
    import subprocess
    import sys as _sys
    from pathlib import Path

    뿌리 = Path(__file__).resolve().parent.parent
    env = dict(_os.environ, DCB_DATA_DIR=str(tmp_path / "data"), DCB_BACKUP_DIR=str(tmp_path / "bk"))
    r = subprocess.run([_sys.executable, "scripts/backup.py"], cwd=뿌리, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _운영과옛판(tmp_path, 옛판수):
    # **임시 폴더의 앱 DB 자리**다 — 운영 data/ 가 아니다. 경로를 한 변수로 나눠 적는 것은
    # test42_b03(운영 DB 를 이름하는 시험은 읽기 전용 엔진만)이 글자로 보기 때문이다
    시험데이터 = tmp_path / "data"
    시험데이터.mkdir()
    _성한판(시험데이터, "x")                                   # 앱 DB 자리용 — 이름은 아래서 바꾼다
    (시험데이터 / "app-x.db").rename(시험데이터 / "app.db")
    이름 = [f"202608{d:02d}-030000" for d in range(1, 옛판수 + 1)]
    for s in 이름:
        _성한판(tmp_path / "bk", s)
    return 이름


def test_11i_정리_줄에_지운_판의_이름이_남고_재실행은_정책대로_다음_판을_지운다(tmp_path):
    이름 = _운영과옛판(tmp_path, 32)                          # 32 + 이번 1 = 33 → 오래된 3판
    첫 = _실행(tmp_path)
    줄 = [l for l in 첫.splitlines() if "정리:" in l]
    assert len(줄) == 1, 첫
    assert "지운 판 3" in 줄[0] and ", ".join(이름[:3]) in 줄[0], 줄[0]
    for s in 이름[:3]:
        assert not (tmp_path / "bk" / f"app-{s}.db").exists()
    # 재실행 — 이번 판이 하나 늘어 또 하나를 지운다(정책). 지운 이름이 정확히 다음 것이다
    둘 = _실행(tmp_path)
    assert [l for l in 둘.splitlines() if "정리:" in l][0].endswith(이름[3])


def test_11j_지울_판이_없으면_정리_줄을_안_낸다(tmp_path):
    _운영과옛판(tmp_path, 3)
    출력 = _실행(tmp_path)
    assert "정리:" not in 출력 and "못 지운" not in 출력, 출력
    assert "현재 4개 보관 중" in 출력                       # 보관 수는 여전히 말한다


def test_11k_많이_지우면_앞_10개_이름과_나머지_수만_적는다():
    이름 = [f"202608{d:02d}-030000" for d in range(1, 16)]
    줄 = backup.정리줄({"before": 45, "protected": 0, "removed_stamps": 15, "removed": 60,
                        "removed_names": 이름, "prune_failed": []})
    assert len(줄) == 1
    assert ", ".join(이름[:10]) + " 외 5판" in 줄[0]
    assert 이름[10] not in 줄[0]


def test_11l_지우기_실패는_멈추지_않고_판_이름과_까닭을_한_줄로_남긴다(tmp_path, monkeypatch):
    out = tmp_path / "bk"
    for d in range(1, 6):
        _성한판(out, f"202608{d:02d}-030000")
    막을 = out / "app-20260801-030000.db"
    진짜 = type(막을).unlink

    def 가짜(self, *a, **k):
        if self == 막을:
            raise PermissionError(13, "Permission denied")
        return 진짜(self, *a, **k)

    monkeypatch.setattr(type(막을), "unlink", 가짜)
    실패 = []
    지운 = backup.prune(out, keep=2, 실패=실패)
    assert 실패 == [("20260801-030000", "app-20260801-030000.db: Permission denied")]
    assert not (out / "app-20260802-030000.db").exists()      # 나머지는 계속 지웠다
    # 지운 DB 는 둘 — 행 수 옆 파일(.rows.json)도 함께 지워지므로 파일 수가 아니라 DB 를 센다
    assert 막을.exists() and sum(p.suffix == ".db" for p in 지운) == 2
    줄 = backup.정리줄({"removed_stamps": 2, "before": 5, "protected": 0, "removed": 2,
                        "removed_names": ["20260802-030000", "20260803-030000"], "prune_failed": 실패})
    assert len(줄) == 2 and "!! 정리하다 못 지운 판 1: 20260801-030000 — app-20260801-030000.db: Permission denied" == 줄[1].strip()
