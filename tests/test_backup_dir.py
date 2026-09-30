"""백업 자리 — `DCB_BACKUP_DIR` 을 읽는 곳은 `app.paths.백업자리` 하나다 (2026-09-30).

전에는 설정 › 점검(백업 마지막 시각)과 자가진단(백업 용량)이 `data/backups` 를 박아 두고
읽어서, 위치를 옮기면 두 화면이 옛 자리를 봤다. 여기서 재는 것:
- 다른 자리를 주면 점검 화면과 자가진단이 **그 자리**를 본다
- 값이 없으면 기본값(`<데이터>/backups`)을 본다
- 빈칸뿐 · 상대 경로 · 끝의 `/` · 폴더 없음 · 읽기 권한 없음 — 폴더를 **만들지 않고** 까닭을 낸다
"""

from __future__ import annotations

import os
import pathlib
import sqlite3

import pytest

from app import paths


def _판(자리: pathlib.Path, 때: str) -> pathlib.Path:
    자리.mkdir(parents=True, exist_ok=True)
    p = 자리 / f"app-{때}.db"
    sqlite3.connect(p).close()
    return p


# ── 읽는 곳 하나 ────────────────────────────────────────────────────────

def test_bd01_값이_없거나_빈칸이면_기본값(monkeypatch):
    monkeypatch.delenv("DCB_BACKUP_DIR", raising=False)
    assert paths.백업자리() == (paths.DATA_DIR / "backups", None)
    monkeypatch.setenv("DCB_BACKUP_DIR", "   ")
    assert paths.백업자리() == (paths.DATA_DIR / "backups", None)


def test_bd02_상대_경로는_쓰지_않고_기본값으로도_물러서지_않는다(monkeypatch):
    monkeypatch.setenv("DCB_BACKUP_DIR", "rel/backups")
    자리, 문제 = paths.백업자리()
    assert 자리 is None and "절대 경로" in 문제


def test_bd03_끝의_슬래시와_겹친_슬래시를_정리한다(monkeypatch, tmp_path):
    monkeypatch.setenv("DCB_BACKUP_DIR", str(tmp_path) + "//bk///")
    assert paths.백업자리() == (tmp_path / "bk", None)


def test_bd04_폴더_없음_폴더_아님_권한_없음을_가리고_만들지_않는다(tmp_path):
    없음 = tmp_path / "없음"
    assert "없습니다" in paths.백업자리_문제(없음)
    assert not 없음.exists(), "읽기만 해야 한다 — 폴더를 만들었다"

    파일 = tmp_path / "파일"
    파일.write_text("x")
    assert "폴더가 아닙니다" in paths.백업자리_문제(파일)

    잠김 = tmp_path / "잠김"
    잠김.mkdir()
    잠김.chmod(0)
    try:
        if os.geteuid() == 0:
            pytest.skip("root 는 권한을 무시한다")
        assert "읽을 수 없습니다" in paths.백업자리_문제(잠김)
    finally:
        잠김.chmod(0o755)

    assert paths.백업자리_문제(tmp_path) is None


def test_bd05_셈하는_곳은_하나다():
    """`DCB_BACKUP_DIR` 을 환경에서 읽는 파이썬 코드가 `app/paths.py` 밖에 없다."""
    root = pathlib.Path(__file__).resolve().parent.parent
    밖 = []
    for p in list((root / "app").rglob("*.py")) + list((root / "scripts").glob("*.py")):
        글 = p.read_text(encoding="utf-8")
        if 'environ.get("DCB_BACKUP_DIR"' in 글 or "environ['DCB_BACKUP_DIR'" in 글 or 'getenv("DCB_BACKUP_DIR"' in 글:
            밖.append(p.relative_to(root).as_posix())
    assert 밖 == ["app/paths.py"], 밖


# ── 점검 화면 ────────────────────────────────────────────────────────────

def test_bd06_점검_화면은_DCB_BACKUP_DIR_의_판을_본다(admin_client, monkeypatch, tmp_path):
    다른곳 = tmp_path / "다른곳"
    판 = _판(다른곳, "20260930-030000")
    os.utime(판, (1790000000, 1790000000))       # 2026-09-21 근처 — 기본 자리에는 없는 값
    monkeypatch.setenv("DCB_BACKUP_DIR", str(다른곳) + "/")
    본문 = admin_client.get("/settings/checkup").text
    import datetime as dt
    기대 = dt.datetime.fromtimestamp(1790000000).strftime("%Y.%m.%d %H:%M")
    assert 기대 in 본문


def test_bd07_점검_화면은_값이_없으면_기본_자리를_본다(admin_client, monkeypatch, tmp_path):
    monkeypatch.delenv("DCB_BACKUP_DIR", raising=False)
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    판 = _판(tmp_path / "backups", "20260930-030000")
    os.utime(판, (1780000000, 1780000000))
    import datetime as dt
    기대 = dt.datetime.fromtimestamp(1780000000).strftime("%Y.%m.%d %H:%M")
    assert 기대 in admin_client.get("/settings/checkup").text


def test_bd08_점검_화면은_못_읽으면_까닭을_내고_폴더를_안_만든다(admin_client, monkeypatch, tmp_path, caplog):
    없음 = tmp_path / "없음"
    monkeypatch.setenv("DCB_BACKUP_DIR", str(없음))
    with caplog.at_level("WARNING"):
        본문 = admin_client.get("/settings/checkup").text
    assert "백업 폴더가 없습니다" in 본문
    assert not 없음.exists()
    assert sum("백업 마지막 시각" in r.getMessage() for r in caplog.records) == 1

    monkeypatch.setenv("DCB_BACKUP_DIR", "rel/x")
    assert "절대 경로" in admin_client.get("/settings/checkup").text


# ── 자가진단 ────────────────────────────────────────────────────────────

def test_bd09_자가진단은_DCB_BACKUP_DIR_의_용량을_잰다(monkeypatch, tmp_path):
    from scripts import healthcheck

    다른곳 = tmp_path / "다른곳"
    다른곳.mkdir()
    (다른곳 / "app-x.db").write_bytes(b"0" * (3 * 1024 * 1024))
    monkeypatch.setenv("DCB_BACKUP_DIR", str(다른곳))
    ok, message = healthcheck.check_disk()
    assert "백업 3MB" in message, message


def test_bd10_자가진단은_값이_없으면_기본_자리를_잰다(monkeypatch, tmp_path):
    from scripts import healthcheck

    monkeypatch.delenv("DCB_BACKUP_DIR", raising=False)
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "app-x.db").write_bytes(b"0" * (5 * 1024 * 1024))
    ok, message = healthcheck.check_disk()
    assert "백업 5MB" in message, message


def test_bd11_자가진단은_못_읽으면_한_줄_붙이고_디스크_판정은_한다(monkeypatch, tmp_path):
    from scripts import healthcheck

    없음 = tmp_path / "없음"
    monkeypatch.setenv("DCB_BACKUP_DIR", str(없음))
    ok, message = healthcheck.check_disk()
    assert "남은 공간" in message and "백업 못 잼" in message and "없습니다" in message
    assert not 없음.exists()
