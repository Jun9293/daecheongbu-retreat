"""멈출 때 범위를 좁힌다 · 빈 판 경고가 화면에 선다 · 의심 판 상한 — 2026-09-13.

**실제로 프로세스를 만들어 잰다.** 이 저장소 밖(`tmp_path`)과 안(저장소 뿌리)에
같은 무늬를 단 잠자는 파이썬을 하나씩 띄우고, 고르는 도구가 안의 것만 고르는지
본다. 띄운 둘은 **띄운 PID 로만** 치운다 — 이 시험이 기계의 다른 프로세스를
건드리면 그것이 곧 고치려는 고장이다.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import uuid

import psutil
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import 내프로세스  # noqa: E402


def _잠든다(폴더, 무늬):
    return subprocess.Popen(
        [sys.executable, "-c", f"import time; time.sleep(120)  # {무늬}"],
        cwd=폴더,
    )


def _나무(proc):
    """띄운 PID 와 그 자손 — 윈도우의 `.venv` python 은 런처라 같은 명령줄의
    자식을 하나 더 띄운다(재 보고 알았다)."""
    try:
        p = psutil.Process(proc.pid)
        return {p.pid} | {c.pid for c in p.children(recursive=True)}
    except psutil.NoSuchProcess:
        return set()


def _치운다(*procs):
    for proc in procs:
        for pid in _나무(proc):
            try:
                psutil.Process(pid).kill()
            except psutil.NoSuchProcess:
                pass
        proc.wait(timeout=10)


def _기다린다(무늬, 수):
    """띄운 프로세스가 목록에 올라올 때까지."""
    import time

    끝 = time.time() + 10
    while time.time() < 끝:
        if len(내프로세스.훑는다(무늬)) >= 수:
            return
        time.sleep(0.1)


def test44_a01_저장소_밖은_안_고르고_안은_고른다(tmp_path):
    무늬 = f"dcb-marker-{uuid.uuid4().hex}"
    밖 = _잠든다(tmp_path, 무늬)
    안 = _잠든다(ROOT, 무늬)
    try:
        _기다린다(무늬, 4)
        안나무, 밖나무 = _나무(안), _나무(밖)
        # ③ 무늬만으로는 둘 다 걸린다 — 가르는 것이 실제로 일을 하는지
        assert 안나무 | 밖나무 <= {줄["pid"] for 줄 in 내프로세스.훑는다(무늬)}
        내것, 남의것 = 내프로세스.고른다(무늬)
        assert {줄["pid"] for 줄 in 내것} == 안나무
        assert 밖나무 <= {줄["pid"] for 줄 in 남의것}
    finally:
        _치운다(밖, 안)


def test44_a02_멈추면_안의_것만_멈추고_밖은_산다(tmp_path):
    무늬 = f"dcb-marker-{uuid.uuid4().hex}"
    밖 = _잠든다(tmp_path, 무늬)
    안 = _잠든다(ROOT, 무늬)
    try:
        _기다린다(무늬, 4)
        안나무, 밖나무 = _나무(안), _나무(밖)
        내것, _ = 내프로세스.고른다(무늬)
        assert set(내프로세스.멈춘다(내것)) == 안나무
        안.wait(timeout=10)
        assert not any(psutil.pid_exists(pid) for pid in 안나무), "안의 것이 안 멈췄다"
        assert 밖.poll() is None and all(psutil.pid_exists(pid) for pid in 밖나무), "밖의 것까지 멈췄다"
    finally:
        _치운다(밖, 안)


def test44_a03_빈_무늬는_거절한다():
    with pytest.raises(ValueError):
        내프로세스.훑는다("  ")


def test44_a04_작업_폴더를_못_읽으면_내_것이_아니다():
    assert 내프로세스._안인가(None, ROOT) is False
    assert 내프로세스._안인가(str(ROOT / "tests"), ROOT) is True
    assert 내프로세스._안인가(str(ROOT.parent), ROOT) is False


# ── 의심 판 상한 · 증거 판 · 앱 알림 ──────────────────────────────────────

import datetime as dt  # noqa: E402
import sqlite3  # noqa: E402

from scripts import backup  # noqa: E402
from tests.conftest import app_session  # noqa: E402


def _판(out, stamp, *, 회차, 행):
    out.mkdir(parents=True, exist_ok=True)
    이음 = sqlite3.connect(out / f"app-{stamp}.db")
    이음.execute("CREATE TABLE retreats (id INTEGER PRIMARY KEY)")
    이음.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY)")
    이음.executemany("INSERT INTO retreats DEFAULT VALUES", [()] * 회차)
    이음.executemany("INSERT INTO notes DEFAULT VALUES", [()] * 행)
    이음.commit()
    이음.close()


def _때(i):
    return f"20260801-{i:06d}"


def test44_b01_의심_판이_상한을_넘으면_의심_판부터_지우고_성한_판은_남는다(tmp_path):
    """수를 박지 않는다 — 상한은 `SUSPECT_KEEP`, 성한 칸은 `KEEP` 에서 끌어온다."""
    out = tmp_path / "backups"
    성한수 = 3
    성한 = [_때(i) for i in range(성한수)]
    의심 = [_때(100 + i) for i in range(backup.SUSPECT_KEEP + 3)]      # 상한보다 셋 많다
    for s in 성한:
        _판(out, s, 회차=2, 행=200)
    for s in 의심:
        _판(out, s, 회차=0, 행=0)

    backup.prune(out, keep=backup.KEEP)
    남은 = set(backup.stamps_in(out))
    assert set(성한) <= 남은, "성한 판이 지워졌다"
    assert set(의심[-backup.SUSPECT_KEEP:]) <= 남은, "최근 의심 판이 지워졌다"
    assert not set(의심[:3]) & 남은, "상한을 넘는 오래된 의심 판이 안 지워졌다"


def test44_b02_상한을_안_넘으면_아무것도_안_지운다(tmp_path):
    out = tmp_path / "backups"
    for i in range(3):
        _판(out, _때(i), 회차=2, 행=200)
    for i in range(backup.SUSPECT_KEEP):
        _판(out, _때(100 + i), 회차=0, 행=0)
    전 = set(backup.stamps_in(out))
    assert backup.prune(out, keep=backup.KEEP) == []
    assert set(backup.stamps_in(out)) == 전


def test44_b03_크기가_넘치면_의심_판을_성한_판보다_먼저_지운다(tmp_path):
    out = tmp_path / "backups"
    성한 = [_때(i) for i in range(2)]
    의심 = [_때(100 + i) for i in range(2)]
    for s in 성한:
        _판(out, s, 회차=2, 행=200)
    for s in 의심:
        _판(out, s, 회차=0, 행=0)
    한판 = (out / f"app-{성한[0]}.db").stat().st_size
    # 판 넷 중 하나를 빼면 들어가는 크기 — 무엇을 먼저 지우는지만 본다
    backup.prune(out, keep=backup.KEEP, max_total=한판 * 3 + 한판 // 2)
    남은 = set(backup.stamps_in(out))
    assert set(성한) <= 남은, "의심 판이 남았는데 성한 판을 지웠다"
    assert len(set(의심) & 남은) == 1


def test44_b04_증거_판은_상한에도_크기에도_안_지워진다(tmp_path):
    out = tmp_path / "backups"
    증거 = next(iter(backup.지키는판))
    _판(out, 증거, 회차=0, 행=0)
    for i in range(2):
        _판(out, _때(i), 회차=2, 행=200)
    for i in range(backup.SUSPECT_KEEP + 5):
        _판(out, _때(100 + i), 회차=0, 행=0)
    backup.prune(out, keep=1, max_total=1)
    assert 증거 in backup.stamps_in(out), "사고의 증거 판을 지웠다"
    # ③ 그 판이 실제로 의심 판으로 잡히는 모양이었는지 — 안 잡혔다면 이 시험은 아무것도 안 본다
    assert 증거 in backup.suspects(out, [증거, _때(0), _때(1)])


def _운영DB():
    from app.db import engine

    return pathlib.Path(engine.url.database)


def _회차를_연다():
    from app import models

    with app_session() as db:
        db.add(models.Retreat(name="알림 회차", start_date=dt.date(2026, 8, 20),
                              end_date=dt.date(2026, 8, 22)))
        db.commit()


def test44_c01_의심_판이_있으면_알림_화면에_그_말이_선다(admin_client, tmp_path):
    _회차를_연다()
    out = tmp_path / "backups"
    for i in range(3):
        _판(out, _때(i), 회차=2, 행=200)
    _판(out, _때(9), 회차=0, 행=0)

    수, 까닭 = backup.알린다(_운영DB(), out)
    assert 까닭 is None and 수 == 1, 까닭
    글 = admin_client.get("/notifications").text
    assert f"새벽 백업이 비어 있습니다 — app-{_때(9)}.db" in 글
    assert "그 앞 날짜의 성한 판으로" in 글, "무엇을 하라는지가 화면에 없다"


def test44_c02_같은_판으로_두_번_안_선다(admin_client, tmp_path):
    from sqlalchemy import func, select

    from app.models import Notification

    _회차를_연다()
    out = tmp_path / "backups"
    for i in range(3):
        _판(out, _때(i), 회차=2, 행=200)
    _판(out, _때(9), 회차=0, 행=0)
    assert backup.알린다(_운영DB(), out)[0] == 1
    assert backup.알린다(_운영DB(), out)[0] == 0
    with app_session() as db:
        assert db.scalar(select(func.count()).select_from(Notification)
                         .where(Notification.kind == backup.BACKUP_NOTICE_KIND)) == 1
    assert admin_client.get("/notifications").text.count(f"app-{_때(9)}.db") == 1


def test44_c03_의심_판이_없으면_아무_말도_안_한다(admin_client, tmp_path):
    _회차를_연다()
    out = tmp_path / "backups"
    for i in range(3):
        _판(out, _때(i), 회차=2, 행=200)
    assert backup.알린다(_운영DB(), out) == (0, None)
    assert "새벽 백업이 비어 있습니다" not in admin_client.get("/notifications").text


def test44_c04_증거_판으로는_알림을_안_세운다(admin_client, tmp_path):
    _회차를_연다()
    out = tmp_path / "backups"
    for i in range(3):
        _판(out, _때(i), 회차=2, 행=200)
    증거 = next(iter(backup.지키는판))
    _판(out, 증거, 회차=0, 행=0)
    assert 증거 in backup.suspects(out, backup.stamps_in(out))
    assert backup.알린다(_운영DB(), out) == (0, None)
    assert "새벽 백업이 비어 있습니다" not in admin_client.get("/notifications").text


def test44_c05_알림_표가_없으면_까닭을_돌려준다(tmp_path):
    out = tmp_path / "backups"
    for i in range(3):
        _판(out, _때(i), 회차=2, 행=200)
    _판(out, _때(9), 회차=0, 행=0)
    빈DB = tmp_path / "app.db"
    sqlite3.connect(빈DB).close()
    수, 까닭 = backup.알린다(빈DB, out)
    assert 수 == 0 and 까닭, "못 세웠는데 까닭이 없다 — 조용히 삼켰다"


# ── 추적 전 새 파일도 글 검사가 본다 (앞 판의 「7/7」 이 틀렸던 자리) ─────────


@pytest.mark.parametrize("검사", ["check_stale", "check_counts"])
def test44_d01_추적_전_새_파일도_볼파일에_든다(검사):
    """얼린 판을 `git add` 하기 전에 돌려도 그 판이 검사 안에 든다.
    저장소 안에 추적 안 된 글 파일을 잠깐 만들어 재고 곧바로 지운다."""
    import importlib

    모듈 = importlib.import_module(f"scripts.{검사}")
    새것 = ROOT / "docs" / "review" / f"zz-추적전-{uuid.uuid4().hex}.md"
    새것.write_text("추적 전 새 파일\n", encoding="utf-8")
    try:
        assert 새것.resolve() in {p.resolve() for p in 모듈.볼파일()}, "추적 전 새 파일을 안 본다"
    finally:
        새것.unlink()


def test44_d02_gitignore_된_것은_여전히_안_본다():
    """넓히다가 gitignore 된 운영 자료까지 보면 안 된다. `data/` 안에도 추적하는
    가명 파일이 있어 폴더로 가르지 않고 **gitignore 판정 그대로** 견준다."""
    from scripts import check_stale

    이름들 = [p.relative_to(ROOT).as_posix() for p in check_stale.볼파일()]
    assert 이름들, "하나도 못 봤다 — 이 시험이 아무것도 안 본다"
    r = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"], cwd=ROOT,
                       input="\n".join(이름들), capture_output=True, text=True, encoding="utf-8")
    assert r.stdout.strip() == "", f"gitignore 된 것을 본다: {r.stdout[:200]}"
