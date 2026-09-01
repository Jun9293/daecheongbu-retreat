"""세션 서명키 (CLAUDE.md 4-12).

**`test_invite.py::test_06` 이 통과하는데도 실전에서 끊길 수 있었다.**
그 테스트가 보는 것은 "한 프로세스 안에서 두 번 부르면 같은 값" 까지다.
정작 실전에서 문제가 되는 것 — 쓰기가 **조용히 실패해서** 재시작마다 새 키가
만들어지는 경우 — 는 아무 오류도 내지 않으므로 그 테스트를 그대로 통과한다.

여기서는 그 빈 자리를 본다: 저장한 것이 실제로 남았는가, 못 읽으면 멈추는가,
빈 파일을 키로 쓰지는 않는가, 그리고 어디서 왔는지가 기록에 남는가.
임시 폴더만 쓴다.
"""

from __future__ import annotations

import pathlib

import pytest

from app import config


def test_01_파일이_없으면_만들고_다시_켜면_같은_값을_읽는다(tmp_path, monkeypatch):
    """재시작을 흉내 낸다 — 두 번 불러 같은 키가 나와야 로그인이 유지된다."""
    monkeypatch.delenv("DCB_SECRET_KEY", raising=False)
    monkeypatch.setattr(config, "SECRET_KEY_PATH", tmp_path / "secret_key.txt")

    first, source1 = config._secret_key()
    assert (tmp_path / "secret_key.txt").exists()
    assert "새로 만듦" in source1

    second, source2 = config._secret_key()          # 재시작
    assert second == first, "재시작하면 키가 바뀐다 — 전원이 로그아웃된다"
    assert "파일" in source2


def test_02_환경변수가_있으면_그것을_쓴다(tmp_path, monkeypatch):
    monkeypatch.setenv("DCB_SECRET_KEY", "고정된-키")
    monkeypatch.setattr(config, "SECRET_KEY_PATH", tmp_path / "secret_key.txt")

    key, source = config._secret_key()
    assert key == "고정된-키"
    assert "환경변수" in source
    # 환경변수를 쓸 때는 파일을 만들지 않는다
    assert not (tmp_path / "secret_key.txt").exists()


def test_03_빈_파일을_키로_쓰지_않는다(tmp_path, monkeypatch):
    """쓰다 만 파일이 남았을 때 빈 문자열로 서명하면 누구나 위조할 수 있는데
    화면에는 아무 표시도 나지 않는다."""
    monkeypatch.delenv("DCB_SECRET_KEY", raising=False)
    path = tmp_path / "secret_key.txt"
    path.write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(config, "SECRET_KEY_PATH", path)

    assert config._read_key_file(path) is None

    key, source = config._secret_key()
    assert key.strip()
    assert "새로 만듦" in source
    assert path.read_text(encoding="utf-8").strip() == key


def test_04_저장했는데_남지_않으면_멈춘다(tmp_path, monkeypatch):
    """쓰기가 성공한 것처럼 보이고 실제로는 남지 않는 경우가 있다 —
    윈도우 파일 가상화, 매번 지워지는 임시 폴더, 다른 계정으로 도는 서비스.
    **아무 오류도 없이 전원이 로그아웃되는 것이 가장 나쁜 결말이다.**"""
    path = tmp_path / "secret_key.txt"

    def vanishing(self, *args, **kwargs):           # 쓴 척하고 남기지 않는다
        return len(args[0]) if args else 0

    monkeypatch.setattr(pathlib.Path, "write_text", vanishing)

    with pytest.raises(RuntimeError) as caught:
        config._write_key_file(path, "새-키")

    message = str(caught.value)
    assert "다시 읽으니 달라졌습니다" in message
    assert "재시작할 때마다 전원이 로그아웃" in message
    assert "DCB_SECRET_KEY" in message              # 빠져나갈 길을 알려준다


def test_05_읽지_못하면_조용히_새로_만들지_않고_멈춘다(tmp_path, monkeypatch):
    path = tmp_path / "secret_key.txt"
    path.write_text("있는-키", encoding="utf-8")

    def refuse(self, *args, **kwargs):
        raise PermissionError("접근이 거부되었습니다")

    monkeypatch.setattr(pathlib.Path, "read_text", refuse)

    with pytest.raises(RuntimeError) as caught:
        config._read_key_file(path)
    assert "읽지 못했습니다" in str(caught.value)
    assert "로그아웃" in str(caught.value)


# ---------------------------------------------------------------- 지문


def test_06_지문은_키를_드러내지_않고_같은_키면_같다():
    a = config.secret_key_fingerprint("어떤-키")
    b = config.secret_key_fingerprint("어떤-키")
    c = config.secret_key_fingerprint("다른-키")

    assert a == b and a != c
    assert len(a) == 8
    assert "어떤-키" not in a                        # 키 자체는 절대 드러내지 않는다


def test_07_앱이_뜰_때_출처와_지문을_로그에_남긴다():
    """지문이 재시작마다 달라지면 그것이 '로그인이 풀린다' 의 원인이다.
    로그에 없으면 원인을 좁힐 방법이 없다."""
    source = (pathlib.Path(__file__).resolve().parent.parent
              / "app" / "main.py").read_text(encoding="utf-8")

    assert "SECRET_KEY_FINGERPRINT" in source
    assert "SECRET_KEY_SOURCE" in source
    assert "세션 키" in source
    # 키 자체를 남기지 않는다
    assert "SECRET_KEY," not in source.replace("SECRET_KEY_FINGERPRINT,", "")


def test_08_자가진단이_세션_키를_묻는다():
    from scripts import healthcheck

    ok, message = healthcheck.check_secret_key()
    assert isinstance(ok, bool)
    assert "지문" in message or "없습니다" in message

    # 목록에 실제로 들어가 있다
    source = (pathlib.Path(__file__).resolve().parent.parent
              / "scripts" / "healthcheck.py").read_text(encoding="utf-8")
    assert '("세션 키가 고정인가", check_secret_key())' in source
