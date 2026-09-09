"""도막 2 — 계정 정리 · 링크 정의 하나로.

**되돌릴 수 없는 일에는 시험이 셋 다 있어야 한다** (11-3) — ① 안 지워야
할 때 안 지우는가 ② 지워야 할 때 지우는가 ③ 검사가 볼 것을 실제로 보고
있는가(센 것이 0이면 실패다).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import re

import pytest
from sqlalchemy import func, select, text

from app import models
from app.domain import auth as invites
from tests.conftest import app_session, make_user

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _스크립트(이름: str):
    spec = importlib.util.spec_from_file_location(이름, ROOT / f"scripts/{이름}.py")
    모듈 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(모듈)
    return 모듈


def _users(db) -> int:
    return db.execute(select(func.count()).select_from(models.User)).scalar_one()


# ════════════════════════════════════════════════════════════════════
# 1. 계정정리.py
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def 여럿(admin_client):
    """남길 관리자 + 지워질 계정 셋, 그리고 그들을 가리키는 행."""
    with app_session() as db:
        admin = db.scalars(select(models.User).where(models.User.role == "admin")).first()
        남길 = admin.id
    리더 = make_user("지워질 리더", "01077770001", "dept_lead")
    부서원 = make_user("지워질 부서원", "01077770002", "member")
    비활성 = make_user("지워질 비활성", "01077770003", "viewer")
    with app_session() as db:
        # 지워질 사람을 가리키는 행 — CASCADE 하나, SET NULL 하나, FK 없는 것 하나
        db.add(models.Notification(user_id=리더, kind="시스템", title="t", body="b",
                                   dedupe_key="시험-리더"))
        db.add(models.ActivityLog(actor_type="user", actor_id=부서원, actor_name="지워질 부서원",
                                  action="시험", target_type="x", target_id=1))
        db.add(models.ActivityLog(actor_type="user", actor_id=남길, actor_name="남길 사람",
                                  action="시험", target_type="x", target_id=1))
        # 남길 계정의 살아 있는 링크와 지워질 계정의 링크
        invites.issue(db, user=db.get(models.User, 남길))
        invites.issue(db, user=db.get(models.User, 리더))
        db.get(models.User, 비활성).is_active = False
        db.commit()
    return {"남길": 남길, "리더": 리더, "부서원": 부서원, "비활성": 비활성}


def test24_a01_실행_없이는_아무것도_안_지운다(여럿, monkeypatch):
    """**기본이 미리보기다.** 인자를 줘도 `--실행` 이 없으면 표만 보이고 멈춘다."""
    모듈 = _스크립트("계정정리")
    with app_session() as db:
        전 = _users(db)
        assert 전 >= 4, "③ 지울 것이 실제로 있어야 이 시험이 뜻이 있다"
        assert 모듈.정리(db, 여럿["남길"], 실행=False) == 0
        assert _users(db) == 전, "미리보기가 지웠다"


def test24_a02_관리자가_아니거나_비활성이면_거절한다(여럿):
    """남길 계정이 관리자·활성이 아니면 지운 뒤 아무도 설정 화면에 못 들어간다."""
    모듈 = _스크립트("계정정리")
    with app_session() as db:
        전 = _users(db)
        assert 모듈.정리(db, 여럿["리더"], 실행=True) == 1, "관리자가 아닌데 받았다"
        assert 모듈.정리(db, 여럿["비활성"], 실행=True) == 1, "비활성인데 받았다"
        assert 모듈.정리(db, 999_999, 실행=True) == 1
        assert _users(db) == 전, "거절해 놓고 지웠다"


def test24_a03_실행하면_하나만_남고_참조가_정리된다(여럿, tmp_path, monkeypatch):
    """② 지워야 할 때 지우는가 — 그리고 **무엇이 어떻게 되는지**까지.

    CASCADE 는 함께 사라지고, SET NULL 은 남되 이름을 잃고, FK 없는
    `activity_logs.actor_id` 는 스크립트가 직접 비우되 `actor_name` 은 남는다.
    남길 계정의 살아 있는 링크는 그대로다."""
    모듈 = _스크립트("계정정리")
    # 사본은 시험 폴더에 뜬다 — 운영 백업 폴더를 건드리지 않는다.
    # 시험 DB 는 test.db 라 이름이 다르므로 app.db 로 한 벌 놓아 준다
    import shutil
    from app.db import engine
    monkeypatch.setattr(모듈.config, "DATA_DIR", tmp_path)
    shutil.copy(engine.url.database, tmp_path / "app.db")
    # 스크립트는 「세션이 여는 파일 = 사본을 뜰 파일」 을 확인한다 — 시험
    # DB 는 test.db 라 그 이름을 맞춰 준다 (지우는 것은 여전히 시험 DB 다)
    monkeypatch.setattr(모듈.config, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")

    with app_session() as db:
        남길 = 여럿["남길"]
        assert db.execute(text("pragma foreign_keys")).scalar_one() == 1, "③ FK 가 켜져 있어야 CASCADE 가 돈다"
        전_알림 = db.execute(select(func.count()).select_from(models.Notification)
                          .where(models.Notification.user_id == 여럿["리더"])).scalar_one()
        assert 전_알림 == 1, "③ 지워질 사람을 가리키는 알림이 실제로 있어야 한다"

        assert 모듈.정리(db, 남길, 실행=True) == 0

        assert _users(db) == 1
        assert db.get(models.User, 남길) is not None
        # CASCADE — 함께 사라짐
        assert db.execute(select(func.count()).select_from(models.Notification)
                          .where(models.Notification.user_id == 여럿["리더"])).scalar_one() == 0
        assert db.execute(select(func.count()).select_from(models.InviteToken)
                          .where(models.InviteToken.user_id == 여럿["리더"])).scalar_one() == 0
        # 남길 계정의 살아 있는 링크는 남는다
        assert invites.live_token(db, user=db.get(models.User, 남길)) is not None
        # FK 없는 칸 — 비워지되 이름은 남는다
        고아 = db.execute(text(
            "select count(*) from activity_logs where actor_id is not null "
            "and actor_id not in (select id from users)")).scalar_one()
        assert 고아 == 0, "가리킬 곳 없는 actor_id 가 남았다"
        남은이름 = db.execute(text(
            "select actor_name from activity_logs where action='시험' and actor_id is null")).scalars().all()
        assert "지워질 부서원" in 남은이름, "actor_name 까지 지웠다"
        # 남길 사람의 기록은 actor_id 도 그대로
        assert db.execute(text(
            "select count(*) from activity_logs where action='시험' and actor_id = :id"),
            {"id": 남길}).scalar_one() == 1
        # 활동 기록 한 줄 — 수만, 이름 없음
        줄 = db.scalars(select(models.ActivityLog)
                        .where(models.ActivityLog.action == "계정_삭제")).all()
        assert len(줄) == 1 and 줄[0].actor_id is None
        assert "지워질" not in (줄[0].summary or "")
    # 사본이 먼저 떠졌다
    assert list(tmp_path.glob("backups/app-*.db")), "지우기 전 사본이 없다"


def test24_a05_여는_파일과_뜨는_파일이_다르면_지우지_않는다(여럿, monkeypatch, tmp_path):
    """DCB_DATABASE_URL 로 둘이 갈리면 「다른 파일의 사본」 을 뜨고도
    「떴습니다」 가 찍힌다 — 그 갈래를 막는다."""
    모듈 = _스크립트("계정정리")
    monkeypatch.setattr(모듈.config, "DATA_DIR", tmp_path)          # 사본은 tmp/app.db
    # DATABASE_URL 은 시험 DB(test.db) 그대로 → 둘이 다르다
    with app_session() as db:
        전 = _users(db)
        with pytest.raises(RuntimeError):
            모듈.정리(db, 여럿["남길"], 실행=True)
        db.rollback()
    with app_session() as db:
        assert _users(db) == 전
    assert not list(tmp_path.glob("backups/*")), "다른 파일의 사본을 떴다"


def test24_a04_사본이_안_떠지면_지우지_않는다(여럿, monkeypatch, tmp_path):
    모듈 = _스크립트("계정정리")

    def 실패(*a, **k):
        raise OSError("디스크가 찼다고 치자")

    monkeypatch.setattr(모듈.backup, "snapshot", 실패)
    monkeypatch.setattr(모듈.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(모듈.config, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    with app_session() as db:
        전 = _users(db)
        with pytest.raises(OSError):
            모듈.정리(db, 여럿["남길"], 실행=True)
        db.rollback()
    with app_session() as db:
        assert _users(db) == 전, "사본 없이 지웠다"


# ════════════════════════════════════════════════════════════════════
# 3. 링크 정의 하나로
# ════════════════════════════════════════════════════════════════════


def _토큰(db, uid, **덮어쓸):
    t = models.InviteToken(user_id=uid, token_hash=f"h-{uid}-{len(덮어쓸)}",
                           expires_at=models._now() + dt.timedelta(days=7))
    for k, v in 덮어쓸.items():
        setattr(t, k, v)
    db.add(t)
    return t


def test24_b01_취소됐거나_만료된_링크만_가진_사람은_안_받은_사람이다(admin_client):
    """설정 › 사용자의 「링크 안 받은 사람」 이 `problem_with` 를 따른다.

    ① 취소·만료만 가진 사람은 세어지고 ② 살아 있는 링크를 가진 사람은
    안 세어지고 ③ 그 두 사람이 실제로 표에 있다."""
    취소만 = make_user("취소만 가진 사람", "01077770011", "member")
    만료만 = make_user("만료만 가진 사람", "01077770012", "member")
    산것 = make_user("살아 있는 링크", "01077770013", "member")
    with app_session() as db:
        지금 = models._now()
        _토큰(db, 취소만, revoked_at=지금)
        _토큰(db, 만료만, expires_at=지금 - dt.timedelta(days=1))
        _토큰(db, 산것)
        db.commit()
        # 같은 것을 함수로도 확인 — 화면이 이것을 부른다
        assert invites.live_token(db, user=db.get(models.User, 취소만)) is None
        assert invites.live_token(db, user=db.get(models.User, 만료만)) is None
        assert invites.live_token(db, user=db.get(models.User, 산것)) is not None

    page = admin_client.get("/admin/users").text
    import re
    m = re.search(r"링크 안 받은 사람 (\d+)명", page)
    assert m, "③ 화면에 그 수가 없다"
    안받음 = int(m.group(1))
    # 관리자 자신은 이미 들어왔고, 새로 만든 셋 중 둘이 「안 받은 사람」 이다
    with app_session() as db:
        기대 = sum(
            1 for p in db.scalars(select(models.User)) if p.is_active
            and invites.live_token(db, user=p) is None and not invites.entered_ever(db, user=p))
    assert 안받음 == 기대
    assert 기대 >= 2, "③ 취소·만료 두 사람이 실제로 세어져야 한다"


# 토큰의 세 칸을 **조건으로** 쓰는 모양들. 값을 찍기만 하는 것
# (`token.expires_at.date()`)은 판정이 아니다.
토큰판정 = re.compile(
    r"(used_at|revoked_at|expires_at)\s*(is_\(|is_not\(|==|!=|<=?|>=?|\.is_|\bis\s+(not\s+)?None)"
    r"|(if|elif|while|and|or|not)\s+(not\s+)?[\w.]*\.(used_at|revoked_at|expires_at)\s*[:)]"
    r"|bool\([\w.]*\.(used_at|revoked_at|expires_at)\)"
)


def _토큰판정줄(파일들):
    걸린것 = []
    for p in 파일들:
        for i, 줄 in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if 토큰판정.search(줄):
                걸린것.append(f"{p.relative_to(ROOT).as_posix()}:{i}")
    return 걸린것


def _판정볼파일():
    return [p for p in sorted((ROOT / "app").rglob("*.py")) + sorted((ROOT / "scripts").glob("*.py"))
            + sorted((ROOT / "app/templates").rglob("*.html"))
            if p.name not in ("auth.py", "models.py")]


def test24_b02_토큰_상태를_스스로_판정하는_코드가_없다():
    """**「살아 있다」 는 `problem_with` 하나다.** 다른 자리가 `used_at` ·
    `revoked_at` · `expires_at` 을 보고 스스로 가르면 뜻이 갈린다.

    auth.py 밖에서 그 세 칸을 **조건으로** 쓰는 줄이 0 이어야 한다.
    템플릿도 본다."""
    assert _토큰판정줄(_판정볼파일()) == []


def test24_b02b_판정을_심으면_잡힌다():
    """③ 검사가 볼 것을 실제로 보고 있는가 — 흔한 파이썬 판정 모양을
    하나씩 심어 전부 걸리는지 잰다. 검토자가 처음 정규식을 돌려 보니
    `is not None` · 참거짓 · `not` 이 다 새어 나갔다."""
    temp = ROOT / "app" / "__stage24_fake_tmp.py"
    모양들 = [
        "if token.revoked_at is not None:",
        "if token.used_at is None:",
        "if token.used_at:",
        "if not t.revoked_at:",
        "ok = bool(t.used_at)",
        "InviteToken.used_at.is_not(None)",
        "if token.expires_at < _now():",
        "alive = tok.revoked_at is None and tok.used_at is None",
    ]
    try:
        for 줄 in 모양들:
            temp.write_text(줄 + "\n", encoding="utf-8")
            assert _토큰판정줄([temp]) == ["app/__stage24_fake_tmp.py:1"], f"못 잡음: {줄}"
        # 값만 찍는 것은 안 잡혀야 한다 — 잡으면 admin_users 의 날짜 표시가 빨개진다
        temp.write_text("x = token.expires_at.date().isoformat()\n", encoding="utf-8")
        assert _토큰판정줄([temp]) == []
    finally:
        temp.unlink()


def test24_b03_revoke_all_도_같은_정의를_쓴다(admin_client):
    """발급할 때 앞의 링크를 취소하는 자리가 「살아 있다」 를 따로 정하고
    있었다 — 기한을 안 봤다. 이제 `problem_with` 가 None 인 것만 취소한다."""
    사람 = make_user("재발급 받는 사람", "01077770021", "member")
    with app_session() as db:
        u = db.get(models.User, 사람)
        지금 = models._now()
        만료 = _토큰(db, 사람, expires_at=지금 - dt.timedelta(days=1))
        산것 = _토큰(db, 사람)
        db.commit()
        수 = invites.revoke_all(db, user=u)
        assert 수 == 1, "살아 있는 것 하나만 취소해야 한다"
        db.refresh(만료); db.refresh(산것)
        assert 산것.revoked_at is not None
        assert 만료.revoked_at is None, "이미 죽은 것을 또 취소했다 — 정의가 둘이다"
