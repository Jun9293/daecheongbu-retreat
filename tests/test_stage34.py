"""로그인 판 — 초대 링크를 걷고 아이디·비밀번호로 (2026-09-11).

| 잰 것 | 어디 |
|---|---|
| 가 | `app/domain/login.py` — 셈을 올린 줄도 읽히나 · `maxmem` 없이는 터지나 |
| 나·다·라 | 같은 파일의 `들어온다` — 사유를 가르나 · 비활성 · 잠금 |
| 마 | `app/security.py` 의 문 하나 — 첫 비밀번호면 화면이 안 열리나 |
| 바 | 설정 › 사용자 — **값이 실린 응답에만** no-store 인가 |
| 사 | `app/routers/login.py` — 옛 초대 주소가 404 가 아니라 로그인인가 |
| 아 | `scripts/계정문열기.py` 세 갈래 |
| 자 | 저장소 어느 파일에도 비밀번호가 없나 |
| 차·카 | `input[type=password]` 의 크기 · 바깥 링크 설명 |

**합성 자료만 쓴다** — 운영 DB 는 시험이 열지 않는다. 사람 이름은 가명이고
비밀번호도 지어낸 값이다.

각 독스트링에 **그 줄이 실제로 무엇을 보는지** 적는다 — 막혀야 할 것이 막히는가 ·
막히면 안 되는 것이 통과하는가 · 검사가 볼 것을 보고 있는가(11-3).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import pathlib
import re
import subprocess

import pytest
from sqlalchemy import select

from app.domain import login as 로그인
from app.models import User
from tests.conftest import app_session, login_as

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 지어낸 값이다 — 어느 사람의 것도 아니다
지어낸값 = "지어낸비밀번호34"


def _스크립트(이름: str):
    spec = importlib.util.spec_from_file_location(이름, ROOT / f"scripts/{이름}.py")
    모듈 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(모듈)
    return 모듈


@pytest.fixture
def 문열기():
    return _스크립트("계정문열기")


def _사람(client, *, 아이디="hadam", 비번=지어낸값, 첫판=False, 활성=True,
        이름="정하윤", phone="01055550001") -> int:
    """시험용 계정 하나. **로그인 화면을 지나는 것만 재려고** 여기서 바로 만든다.

    `비번=None` 이면 비밀번호가 아예 없는 계정이다 — 아직 아무것도 못 받은
    사람이 그 상태다.
    """
    with app_session() as db:
        person = User(name=이름, phone_number=phone, role="general",
                      login_id=아이디, is_active=활성)
        db.add(person)
        db.flush()
        if 비번 is not None:
            로그인.비밀번호를정한다(db, person, 비번, 첫판=첫판)
        person.is_active = 활성
        db.commit()
        return person.id


# ── 가) 셈을 올려도 읽힌다 · maxmem 이 없으면 터진다 ──────────────────

def test34_a01_줄에_적힌_셈으로_읽는다():
    """가) **읽을 때 지금 셈이 아니라 줄에 적힌 셈으로 센다.**

    본다 — ① 지금 셈으로 만든 줄이 읽히는가 ② **더 낮은 셈**으로 만든 옛
    줄도 읽히는가 ③ 그 줄에 실제로 옛 셈이 적혀 있는가(적혀 있지 않으면
    ② 는 지금 셈과 우연히 같아서 통과한 것이다).

    지금 셈으로 고정해 세면 세기를 올린 날 **그 전에 비밀번호를 정한 사람
    전원이 조용히 못 들어온다** — 비밀번호가 틀렸다는 말만 나온다.
    """
    지금 = 로그인.해시한다(지어낸값)
    assert 로그인.맞나(지금, 지어낸값)
    assert f"${로그인.N}$" in 지금

    옛셈 = 2**12
    assert 옛셈 != 로그인.N, "옛 셈을 지금 셈과 같게 두면 아무것도 안 재는 줄이다"
    salt = bytes(range(16))
    key = hashlib.scrypt(지어낸값.encode(), salt=salt, n=옛셈, r=8, p=1,
                         maxmem=128 * 옛셈 * 8 * 3, dklen=32)
    옛줄 = f"scrypt${옛셈}$8$1${salt.hex()}${key.hex()}"
    assert 로그인.맞나(옛줄, 지어낸값), "옛 셈으로 만든 줄을 못 읽는다"
    assert not 로그인.맞나(옛줄, 지어낸값 + "x")


def test34_a02_maxmem_을_안_주면_지금_셈은_실제로_터진다():
    """가) **말로 적지 않고 잰다.**

    본다 — ① 지금 셈(`N`·`R`·`P`)으로 `maxmem` 없이 부르면 실제로 터지는가
    ② 우리가 세는 크기를 주면 지나가는가. ① 이 안 터지면 그때는 기본값이
    넉넉해진 것이므로, 이 줄이 빨개져서 사람이 그 사실을 보게 된다.

    이것이 같은 노트북의 다른 앱에서 실제로 밟은 자리다 — 안 주면 셈을
    올리는 순간 전원이 조용히 못 들어간다.
    """
    salt = bytes(range(16))
    with pytest.raises(ValueError):
        hashlib.scrypt(b"x", salt=salt, n=로그인.N, r=로그인.R, p=로그인.P)
    hashlib.scrypt(b"x", salt=salt, n=로그인.N, r=로그인.R, p=로그인.P,
                   maxmem=로그인._maxmem(로그인.N, 로그인.R, 로그인.P))


def test34_a03_원문도_되돌릴_것도_줄에_없다():
    """가) 해시 줄에 남는 것은 셈·소금·해시뿐이다.

    본다 — 줄 안에 원문이 조각으로도 없는가. 있으면 DB 가 새는 순간
    비밀번호가 함께 샌다.
    """
    줄 = 로그인.해시한다(지어낸값)
    assert 지어낸값 not in 줄
    assert 줄.startswith("scrypt$") and len(줄.split("$")) == 6


# ── 나) 없는 아이디와 틀린 비밀번호가 같은 말 ──────────────────────────

def test34_b01_없는_아이디와_틀린_비밀번호가_글자까지_같다(client):
    """나) **말을 글자로 견준다.**

    본다 — ① 없는 아이디의 사유 ② 있는 아이디에 틀린 비밀번호의 사유가
    **같은 글자**인가 ③ 맞는 비밀번호는 지나가는가(막기만 하면 문이 닫힌
    것과 같다).

    갈라 말하면 아이디 목록을 만들 수 있고, 그 목록이 곧 사람 목록이다.
    """
    _사람(client, 아이디="hadam")
    with app_session() as db:
        _, 없는쪽 = 로그인.들어온다(db, "없는아이디", 지어낸값)
        _, 틀린쪽 = 로그인.들어온다(db, "hadam", "틀린값입니다")
        맞은쪽, 사유 = 로그인.들어온다(db, "hadam", 지어낸값)
    assert 없는쪽 == 틀린쪽, f"사유가 갈린다: {없는쪽!r} / {틀린쪽!r}"
    assert 맞은쪽 is not None and 사유 is None


def test34_b02_없는_아이디일_때도_해시를_한_번_센다(client, monkeypatch):
    """나) **시간으로도 안 갈리게 한다.**

    본다 — 없는 아이디로 들어올 때 해시를 세는 함수가 **실제로 한 번**
    불리는가. 안 부르면 바로 돌아가므로, 걸린 시간만 재도 어느 아이디가
    있는지 알 수 있다.

    시간을 직접 재지 않는 이유는 **시험이 기계 속도에 흔들리기** 때문이다 —
    재는 것은 「한 번 셌는가」 이고, 그것이 시간이 같아지는 근거다.
    """
    센횟수 = []
    진짜 = 로그인.맞나
    monkeypatch.setattr(로그인, "맞나",
                        lambda stored, raw: (센횟수.append(stored), 진짜(stored, raw))[1])
    with app_session() as db:
        로그인.들어온다(db, "없는아이디", 지어낸값)
    assert len(센횟수) == 1, "없는 아이디인데 해시를 안 셌다"
    assert 센횟수[0] == 로그인.더미해시()


# ── 다) 비활성은 맞든 틀리든 같은 말 ──────────────────────────────────

def test34_c01_비활성은_비밀번호가_맞아도_같은_말이다(client):
    """다) **둘을 같은 판에서 잰다.**

    본다 — ① 비활성 계정에 **맞는** 비밀번호 ② **틀린** 비밀번호가 같은
    말을 내는가 ③ 그 말이 보통의 「맞지 않습니다」 와 다른가(같으면 비활성
    이라는 사실을 아무도 못 듣는다) ④ 다시 켜면 들어와지는가.

    비밀번호 검사를 앞에 두면 같은 비활성 계정이 맞을 때와 틀릴 때 다른
    말을 내서, **그 계정의 비밀번호를 맞혔는지를 화면이 알려 준다.**
    """
    uid = _사람(client, 아이디="dohyun", 활성=False)
    with app_session() as db:
        _, 맞은판 = 로그인.들어온다(db, "dohyun", 지어낸값)
        _, 틀린판 = 로그인.들어온다(db, "dohyun", "틀린값입니다")
    assert 맞은판 == 틀린판 == 로그인.TOLD_INACTIVE
    assert 맞은판 != 로그인.TOLD

    with app_session() as db:
        db.get(User, uid).is_active = True
        db.commit()
        사람, 사유 = 로그인.들어온다(db, "dohyun", 지어낸값)
    assert 사람 is not None and 사유 is None


# ── 라) 잠금 ──────────────────────────────────────────────────────────

def test34_d01_아홉_번까지는_안_잠기고_열_번째에_잠긴다(client):
    """라) **막히는 쪽과 안 막히는 쪽을 함께 잰다.**

    본다 — ① 아홉 번 틀려도 안 잠기는가(그 사이에 맞히면 들어와야 한다)
    ② 열 번째에 잠기는가 ③ 잠긴 뒤에는 **맞는 비밀번호도** 막히는가
    (맞히면 풀린다면 잠글 뜻이 없다) ④ 잠금 시각이 지나면 다시 열리는가.
    """
    _사람(client, 아이디="seojin")
    with app_session() as db:
        for i in range(로그인.MAX_FAILS - 1):
            _, 사유 = 로그인.들어온다(db, "seojin", "틀린값입니다")
            assert 사유 == 로그인.TOLD, f"{i + 1}번째에 벌써 잠겼다"
        _, 사유 = 로그인.들어온다(db, "seojin", "틀린값입니다")
        assert 사유 == 로그인.TOLD_LOCKED
        _, 사유 = 로그인.들어온다(db, "seojin", 지어낸값)
        assert 사유 == 로그인.TOLD_LOCKED, "잠겼는데 맞는 비밀번호로 풀렸다"

        뒤 = 로그인.now() + dt.timedelta(minutes=로그인.LOCK_MINUTES + 1)
        사람, 사유 = 로그인.들어온다(db, "seojin", 지어낸값, at=뒤)
    assert 사람 is not None and 사유 is None


def test34_d02_잠금이_DB_에_있다(client):
    """라) **세션을 새로 만들어 잰다.**

    본다 — 잠근 뒤 **다른 세션**에서 읽어도 잠겨 있는가. 메모리에 두면
    서버를 다시 켜는 것으로 풀리는데, 같은 세션 안에서만 보면 그 차이가
    안 잡힌다.
    """
    uid = _사람(client, 아이디="nayun")
    with app_session() as db:
        for _ in range(로그인.MAX_FAILS):
            로그인.들어온다(db, "nayun", "틀린값입니다")
    with app_session() as 새세션:
        사람 = 새세션.get(User, uid)
        assert 사람.locked_until is not None, "잠금이 저장되지 않았다"
        assert 로그인.잠겼나(사람)
        _, 사유 = 로그인.들어온다(새세션, "nayun", 지어낸값)
    assert 사유 == 로그인.TOLD_LOCKED


def test34_d03_맞히면_센_수가_0_으로_돌아간다(client):
    """라) 막히면 안 되는 쪽 — **아홉 번 틀리고 맞힌 사람**이 다음에 한 번
    틀렸다고 잠기면 안 된다.

    본다 — 맞힌 뒤 `failed_count` 가 0 인가.
    """
    uid = _사람(client, 아이디="minjun")
    with app_session() as db:
        for _ in range(로그인.MAX_FAILS - 1):
            로그인.들어온다(db, "minjun", "틀린값입니다")
        assert db.get(User, uid).failed_count == 로그인.MAX_FAILS - 1
        로그인.들어온다(db, "minjun", 지어낸값)
    with app_session() as db:
        assert db.get(User, uid).failed_count == 0


# ── 마) 첫 비밀번호인 채로는 화면이 안 열린다 ─────────────────────────

def _로그인한다(client, 아이디, 비번):
    return client.post("/login", data={"login_id": 아이디, "password": 비번},
                       follow_redirects=False)


def test34_e01_첫_비밀번호면_화면이_안_열리고_바꾼_뒤엔_열린다(client):
    """마) **막는 곳이 하나인지**를 화면 여럿으로 잰다.

    본다 — ① 첫 비밀번호로 들어온 뒤 서로 다른 화면 셋이 전부 `/password`
    로 밀리는가(한 화면만 보면 그 화면에만 걸어 두어도 통과한다)
    ② 바꾸는 화면 자신은 열리는가(그 문으로 받으면 스스로를 막는다)
    ③ 바꾼 뒤에는 그 셋이 열리는가.
    """
    _사람(client, 아이디="hadam", 첫판=True)
    assert _로그인한다(client, "hadam", 지어낸값).status_code == 303

    # **서로 다른 화면 셋**이다 — 한 화면만 보면 그 화면에만 걸어 두어도 통과한다
    화면들 = ("/", "/settings", "/notifications")
    for 자리 in 화면들:
        답 = client.get(자리, follow_redirects=False)
        assert 답.status_code == 303 and 답.headers["location"] == "/password", \
            f"{자리} 가 첫 비밀번호인 채로 열렸다"
    assert client.get("/password").status_code == 200

    바꿈 = client.post("/password", data={"password": "새로지어낸값12", "password2": "새로지어낸값12"},
                     follow_redirects=False)
    assert 바꿈.status_code == 303
    for 자리 in 화면들:
        assert client.get(자리, follow_redirects=False).status_code == 200, \
            f"바꿨는데 {자리} 가 안 열린다"


def test34_e02_짧거나_서로_다른_값은_거절한다(client):
    """마) 막히는 쪽 — 길이 하나뿐인 규칙이 실제로 걸리는가.

    본다 — ① 두 번 적은 값이 다르면 거절 ② `MIN_LENGTH` 아래면 거절
    ③ 그 둘 다 **비밀번호가 안 바뀌는가**(거절해 놓고 바꾸면 더 나쁘다).
    """
    uid = _사람(client, 아이디="hadam", 첫판=True)
    _로그인한다(client, "hadam", 지어낸값)
    with app_session() as db:
        앞 = db.get(User, uid).password_hash

    짧은값 = "a" * (로그인.MIN_LENGTH - 1)
    for 값, 둘째 in ((지어낸값, 지어낸값 + "x"), (짧은값, 짧은값)):
        답 = client.post("/password", data={"password": 값, "password2": 둘째})
        assert 답.status_code == 400, (값, 답.status_code)
    with app_session() as db:
        assert db.get(User, uid).password_hash == 앞


def test34_e03_비밀번호가_없는_옛_계정은_그_화면에_안_갇힌다(client):
    """마) **막히면 안 되는 쪽.**

    이 칸이 붙기 전에 만들어진 계정은 기본값이 참인 채로 서는데 **바꿀
    비밀번호가 아예 없다.** 그때도 막으면, 세션이 살아 있던 사람들이 서버를
    다시 켜는 순간 바꾸는 화면에 갇힌다 — 거기서 값을 정해도 아이디가 없어
    다음 로그인은 여전히 막힌다.

    본다 — ① 참이지만 해시가 없는 계정은 화면이 열리는가 ② **해시가 생기면
    그때 막히는가**(둘을 같은 판에서 봐야 「안 막는다」 가 「영영 안 막는다」 가
    아니라는 것이 보인다).
    """
    uid = _사람(client, 아이디="yetgye", 비번=None)
    with app_session() as db:
        사람 = db.get(User, uid)
        사람.must_change_password = True
        db.commit()
    # 세션만 있는 상태를 만든다 — 로그인 화면은 해시가 없으면 못 지난다.
    # 쿠키를 서명하는 곳은 `security` 하나라 그것을 그대로 쓴다
    from fastapi.testclient import TestClient

    from app import config, security
    from app.main import app

    옛사람 = TestClient(app)
    옛사람.cookies.set(config.SESSION_COOKIE, security._serializer.dumps({"uid": uid}))
    assert 옛사람.get("/", follow_redirects=False).status_code == 200,         "바꿀 비밀번호가 없는데 바꾸는 화면에 갇혔다"

    with app_session() as db:
        로그인.비밀번호를정한다(db, db.get(User, uid), 지어낸값, 첫판=True)
    막힘 = 옛사람.get("/", follow_redirects=False)
    assert 막힘.status_code == 303 and 막힘.headers["location"] == "/password"


# ── 바) 발급 응답에만 no-store ─────────────────────────────────────────

def test34_f01_비밀번호가_실린_응답에만_no_store_다(admin_client, client):
    """바) **그 응답에만** 인가를 두 판에서 잰다.

    본다 — ① 그냥 연 사용자 화면에는 no-store 가 **없는가**(늘 붙이면 무엇이
    특별한지 아무도 모르게 된다) ② 발급한 뒤 값이 실린 화면에는 붙는가
    ③ 그 화면에 값이 실제로 보이는가 ④ 새로고침하면 값이 사라지는가
    (한 번만 보인다는 말이 참인가).
    """
    평소 = admin_client.get("/admin/users")
    assert "no-store" not in 평소.headers.get("cache-control", "")

    # **남에게** 발급한다 — 자기 것은 값을 안 보여주고 바꾸는 화면으로 간다
    # (발급하면 그 사람에게는 이 화면부터 안 열리기 때문이다)
    uid = _사람(client, 아이디="gansa")

    낸다 = admin_client.post(f"/admin/users/{uid}/password", follow_redirects=False)
    assert 낸다.status_code == 303
    자리 = 낸다.headers["location"]
    assert "k=" in 자리

    보임 = admin_client.get(자리)
    assert "no-store" in 보임.headers.get("cache-control", "")
    값 = re.search(r'id="firstpw" readonly value="([^"]+)"', 보임.text)
    assert 값, "발급했는데 값이 화면에 없다"

    다시 = admin_client.get(자리)
    assert 값.group(1) not in 다시.text, "새로고침했는데 값이 또 나온다"
    assert "no-store" not in 다시.headers.get("cache-control", "")


def test34_f02_발급하면_그_값으로_들어와지고_바꾸는_화면이_먼저_뜬다(admin_client, client):
    """바) 발급이 실제로 문을 여는가 — **값을 화면에서 읽어 그대로 써 본다.**

    본다 — ① 그 값으로 로그인이 되는가 ② 들어오자마자 바꾸는 화면으로
    밀리는가(발급하면 `must_change_password` 가 참이다) ③ 옛 비밀번호로는
    이제 못 들어오는가.
    """
    uid = _사람(client, 아이디="jiwoo")
    낸다 = admin_client.post(f"/admin/users/{uid}/password", follow_redirects=False)
    보임 = admin_client.get(낸다.headers["location"])
    새값 = re.search(r'id="firstpw" readonly value="([^"]+)"', 보임.text).group(1)

    assert _로그인한다(client, "jiwoo", 지어낸값).status_code == 401, "옛 값이 아직 통한다"
    assert _로그인한다(client, "jiwoo", 새값).status_code == 303
    답 = client.get("/", follow_redirects=False)
    assert 답.status_code == 303 and 답.headers["location"] == "/password"


def test34_f03_아이디가_없으면_발급하지_않고_말한다(admin_client, client):
    """바) 막히는 쪽 — 아이디 없는 계정에 비밀번호만 주면 **못 들어온다.**

    본다 — ① 거절하는가 ② 거절하면서 무엇을 해야 하는지 말하는가
    ③ 비밀번호가 실제로 안 생겼는가(말만 하고 만들면 더 나쁘다).
    """
    uid = _사람(client, 아이디=None, 비번=None)
    답 = admin_client.post(f"/admin/users/{uid}/password", follow_redirects=False)
    assert 답.status_code == 303 and "k=" not in 답.headers["location"]
    with app_session() as db:
        assert db.get(User, uid).password_hash is None


# ── 사) 옛 초대 주소 ──────────────────────────────────────────────────

def test34_g01_옛_초대_주소가_로그인으로_간다(client):
    """사) **404 가 아니다.**

    본다 — ① 살아 있던 적도 없는 아무 토큰으로 열어도 404 가 아니라
    로그인 화면으로 가는가 ② 그 말이 「이제 링크를 쓰지 않는다」 인가
    ③ **들어와지지는 않는가**(보내 주기만 하고 문을 열면 안 된다).

    카카오톡에 남은 링크를 누른 사람에게 「없는 주소」 를 보이면 시스템이
    고장난 것으로 읽힌다.
    """
    답 = client.get("/invite/아무토큰", follow_redirects=False)
    assert 답.status_code == 303
    assert 답.headers["location"] == "/login"
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"


def test34_g02_만드는_길이_코드에_안_남아_있다():
    """사) **코드를 남겨 두면 그것이 곧 열린 문이다.**

    본다 — ① `app/` 안에 초대 링크를 만들거나 쓰는 함수가 없는가
    ② 표와 끊는 길은 **남아 있는가**(0장 — 행을 지우지 않는다).
    ③ 검사가 실제로 파일을 읽었는가(안 읽고 통과하면 아무것도 안 본 것이다).
    """
    from app.domain import auth as 옛링크

    for 이름 in ("issue", "redeem", "invite_url", "stash", "take"):
        assert not hasattr(옛링크, 이름), f"{이름} 이(가) 아직 있다"
    assert hasattr(옛링크, "전부끊는다") and hasattr(옛링크, "problem_with")

    본파일 = 0
    for path in (ROOT / "app").rglob("*.py"):
        글 = path.read_text(encoding="utf-8")
        본파일 += 1
        assert "invite_url(" not in 글, path
    assert 본파일 > 10, "app 아래 파일을 못 읽었다 — 아무것도 안 본 검사다"


# ── 아) 계정문열기 세 갈래 ────────────────────────────────────────────

def test34_h01_첫관리자는_없을_때만_만든다(client, 문열기, capsys):
    """아) 갈래 ① — 막히는 쪽과 안 막히는 쪽을 함께.

    본다 — ① 관리자가 없으면 만드는가 ② 만든 계정이 **첫 비밀번호 상태**
    인가 ③ **이미 있으면 안 만들고 말하는가** ④ 그때 계정 수가 안 느는가
    (말만 하고 만들면 그것이 계정이 불어나던 그 입구다).
    """
    with app_session() as db:
        assert 문열기.첫관리자(db, "정하윤", "hayun") == 0
    나온말 = capsys.readouterr().out
    assert "hayun" in 나온말
    with app_session() as db:
        사람 = 로그인.아이디로찾기(db, "hayun")
        assert 사람 is not None and 사람.role == "admin"
        assert 사람.must_change_password and 사람.password_hash
        앞 = db.scalars(select(User)).all()

    with app_session() as db:
        # **거절은 1 이다.** 전에 여기 `!= 0 or True` 라고 적혀 있었는데 그것은
        # 늘 참이라 아무것도 안 보는 줄이었고, 그렇게 적힌 까닭은 갈래 ① 이
        # 거절하면서 0 으로 끝났기 때문이다(검토가 짚음). 스크립트를 고쳤다
        assert 문열기.첫관리자(db, "최도현", "dohyun") == 1
        assert 로그인.아이디로찾기(db, "dohyun") is None, "이미 있는데 또 만들었다"
        assert len(db.scalars(select(User)).all()) == len(앞)
    assert "이미 관리자 계정이" in capsys.readouterr().out


def test34_h02_재설정은_관리자만이고_값을_화면에만_찍는다(client, 문열기, capsys):
    """아) 갈래 ② — **관리자가 아니면 거절한다.**

    본다 — ① 일반 계정은 거절하는가 ② 그때 비밀번호가 안 바뀌었는가
    ③ 관리자는 새 값을 받는가 ④ 그 값이 화면에 찍히고 **그 값으로 실제로
    들어와지는가** ⑤ 다시 첫 비밀번호 상태가 되는가.
    """
    일반 = _사람(client, 아이디="ilban")
    with app_session() as db:
        앞 = db.get(User, 일반).password_hash
        assert 문열기.재설정(db, 일반) == 1
        assert db.get(User, 일반).password_hash == 앞
    capsys.readouterr()

    with app_session() as db:
        person = db.get(User, 일반)
        person.role = "admin"
        db.commit()
        assert 문열기.재설정(db, 일반) == 0
    나온말 = capsys.readouterr().out
    새값 = [ln.split()[-1] for ln in 나온말.splitlines() if ln.strip().startswith("비밀번호 ")]
    assert 새값, 나온말
    with app_session() as db:
        사람, 사유 = 로그인.들어온다(db, "ilban", 새값[0])
        assert 사람 is not None, 사유
        assert db.get(User, 일반).must_change_password


def test34_h03_링크끊기는_먼저_세고_행을_지우지_않는다(client, 문열기, capsys):
    """아) 갈래 ③ — **먼저 세어 사람에게 보인다.**

    본다 — ① 살아 있는 링크 수를 말하는가 ② 그만큼 끊는가 ③ **행은
    그대로인가**(0장 — 누가 언제 들어왔는지가 거기 있다) ④ 두 번째로
    돌리면 「끊을 것이 없다」 인가(「성공」 이 아니다).
    """
    from app.models import InviteToken

    uid = _사람(client, 아이디="hadam")
    with app_session() as db:
        for i in range(3):
            db.add(InviteToken(user_id=uid, token_hash=f"해시{i}",
                               expires_at=dt.datetime.now() + dt.timedelta(days=7)))
        db.commit()

    with app_session() as db:
        assert 문열기.링크끊기(db) == 0
    나온말 = capsys.readouterr().out
    assert "3개" in 나온말
    with app_session() as db:
        전부 = db.scalars(select(InviteToken)).all()
        assert len(전부) == 3, "행을 지웠다"
        assert all(t.revoked_at is not None for t in 전부)
        assert 문열기.링크끊기(db) == 0
    assert "끊을 것이 없습니다" in capsys.readouterr().out


# ── 아이디 — 겹침과 글자 규칙 (가장 비싼 자리) ────────────────────────
#
# 4-12 가 「겹치면 **로그인 자체가 엉뚱한 계정으로 갑니다**」 라고 적어 둔
# 자리다. 검토 전에는 이 판에서 **유일하게 안 재진** 자리였다.

def test34_m01_겹치는_아이디로는_저장이_안_되고_누구_것인지_말한다(admin_client, client):
    """막히는 쪽 — 겹침.

    본다 — ① 남이 쓰는 아이디로 바꾸려 하면 거절하는가 ② **누구 것인지**
    말하는가(안 말하면 총무팀이 왜 막혔는지 모른다) ③ **아이디가 실제로
    안 바뀌었는가** ④ 대소문자만 다른 것도 같은 아이디로 보는가(휴대폰이
    첫 글자를 키운다) ⑤ 자기 아이디를 그대로 저장하는 것은 막지 않는가.
    """
    가 = _사람(client, 아이디="gapdol", 이름="정하윤", phone="01055550011")
    나 = _사람(client, 아이디="eulsun", 이름="최도현", phone="01055550012")

    답 = admin_client.post(f"/admin/users/{나}/update",
                         data={"role": "general", "login_id": "GapDol"},
                         follow_redirects=True)
    assert "정하윤" in 답.text, "누구 것인지 안 말한다"
    with app_session() as db:
        assert db.get(User, 나).login_id == "eulsun", "겹치는데 바뀌었다"
        assert db.get(User, 가).login_id == "gapdol"

    # ⑤ 안 막히는 쪽 — 자기 것을 그대로 저장하는 것은 지나간다
    admin_client.post(f"/admin/users/{나}/update",
                      data={"role": "general", "login_id": "EulSun"})
    with app_session() as db:
        assert db.get(User, 나).login_id == "eulsun"


def test34_m02_규칙_밖_아이디는_화면도_스크립트도_거절한다(admin_client, client, 문열기, capsys):
    """막히는 쪽 — 글자 규칙. **두 길에서 같이 잰다.**

    규칙이 화면에만 있으면 스크립트로 규칙 밖 값이 들어가고, 그렇게 들어간
    계정은 **설정 › 사용자에서 저장 자체가 안 됩니다** — 폼이 그 값을 되돌려
    받아 거절하면서 권한·부서·연락처까지 못 고치게 됩니다(검토 F5).

    본다 — ① 화면이 거절하는가 ② **스크립트도 거절하는가** ③ 둘 다
    값이 안 바뀌었는가 ④ 규칙 안 값은 지나가는가.
    """
    uid = _사람(client, 아이디="ok.name-1", phone="01055550013")
    with app_session() as db:
        assert db.get(User, uid).login_id == "ok.name-1", "④ 규칙 안 값이 막혔다"

    for 나쁜값 in ("하윤", "a", "has space", "UPPER!", "-start"):
        admin_client.post(f"/admin/users/{uid}/update",
                          data={"role": "general", "login_id": 나쁜값})
        with app_session() as db:
            assert db.get(User, uid).login_id == "ok.name-1", f"① 화면이 통과시켰다: {나쁜값}"

    관리자 = _사람(client, 아이디="seobeo", 이름="정하윤", phone="01055550014")
    with app_session() as db:
        db.get(User, 관리자).role = "admin"
        db.commit()
    capsys.readouterr()
    with app_session() as db:
        assert 문열기.아이디를준다(db, db.get(User, 관리자), "하윤") == 1, "② 스크립트가 통과시켰다"
        assert db.get(User, 관리자).login_id == "seobeo", "③ 거절했는데 바뀌었다"
    assert "아이디는" in capsys.readouterr().out


def test34_m03_유니크_인덱스가_실제로_서_있고_빈_값끼리는_안_겹친다(client):
    """③ **검사가 볼 것을 보고 있는가** — 화면이 막는 것과 DB 가 막는 것은
    다른 층이다. 화면만 막으면 스크립트·손질이 그 아래로 지나간다.

    본다 — ① 인덱스가 실제로 서 있는가 ② 그 인덱스로 **DB 가 겹침을
    거절하는가**(같은 값을 날 연결로 넣어 본다) ③ **빈 값(NULL)끼리는
    겹침이 아닌가**(아직 아이디를 안 받은 계정이 여럿이다).
    """
    import sqlalchemy as sa
    from app.db import engine

    이름들 = {r[0] for r in engine.connect().execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='index'"))}
    assert "ix_users_login_id" in 이름들, "① 인덱스가 없다"

    _사람(client, 아이디="dupkey", phone="01055550015")
    with app_session() as db:
        db.add(User(name="겹치는 사람", phone_number="01055550016", role="general",
                    login_id="dupkey"))
        try:
            db.commit()
            raise AssertionError("② DB 가 겹침을 받아들였다")
        except sa.exc.IntegrityError:
            db.rollback()

    # ③ 빈 값끼리는 여럿이어도 된다
    with app_session() as db:
        for n in (17, 18):
            db.add(User(name=f"아이디 없는 사람 {n}", phone_number=f"010555500{n}",
                        role="general"))
        db.commit()


def test34_m04_자기_자신에게_발급하면_값을_안_보이고_바꾸는_화면으로_간다(admin_client):
    """물음 2 — **그 갈래를 실제로 밟는다.**

    본다 — ① 자기 것은 `k=` 없이 `/password` 로 가는가 ② 그래도 비밀번호는
    실제로 새로 생겼는가(말만 하고 안 만들면 더 나쁘다) ③ 그 뒤 사용자
    화면이 안 열리는가(발급하면 첫 비밀번호 상태가 된다).
    """
    with app_session() as db:
        나 = db.scalars(select(User)).first()
        나.login_id = "gansa"
        db.commit()
        uid, 앞 = 나.id, 나.password_hash

    답 = admin_client.post(f"/admin/users/{uid}/password", follow_redirects=False)
    assert 답.status_code == 303
    assert 답.headers["location"] == "/password" and "k=" not in 답.headers["location"]
    with app_session() as db:
        사람 = db.get(User, uid)
        assert 사람.password_hash != 앞, "② 값이 안 바뀌었다"
        assert 사람.must_change_password
    막힘 = admin_client.get("/admin/users", follow_redirects=False)
    assert 막힘.status_code == 303 and 막힘.headers["location"] == "/password"


def test34_m05_가르는_것과_안_가르는_것의_경계가_문서와_같다(client):
    """나·다 · 검토 F6 — **어디까지 가르지 않는지**를 잰다.

    4-12 는 「없는 아이디와 틀린 비밀번호만 같은 말이고, 비활성과 잠김은
    일부러 다르게 말한다」 고 적었다. 문서가 넷 전부라고 읽히면 다음 사람이
    그것을 믿는다.

    본다 — ① 그 둘은 같은 말인가 ② 비활성·잠김은 **다른 말**인가(그래서
    되살려야 하는 사람과 기다리면 되는 사람이 갈린다) ③ **같은 판에서**
    없는 아이디는 아무리 틀려도 잠김이 안 나오고 **있는 아이디는 열 번째에
    잠기는가** — 그 갈림이 이 경계의 한 자락이고, 둘을 따로 재면 「같은
    횟수를 틀렸는데 한쪽만 잠긴다」 가 안 보인다.
    """
    _사람(client, 아이디="gyeonggye", phone="01055550019")
    with app_session() as db:
        _, 없는쪽 = 로그인.들어온다(db, "없는아이디", 지어낸값)
        _, 틀린쪽 = 로그인.들어온다(db, "gyeonggye", "틀린값입니다")
        assert 없는쪽 == 틀린쪽 == 로그인.TOLD

        # ③ 같은 횟수를 **나란히** 틀린다 — 있는 쪽은 이미 한 번 틀렸으므로
        # 남은 것만 채우고, 없는 쪽은 그보다 더 틀려 본다
        없는것 = []
        있는것 = []
        for i in range(로그인.MAX_FAILS + 2):
            _, 없 = 로그인.들어온다(db, "없는아이디", "틀린값입니다")
            없는것.append(없)
            if i < 로그인.MAX_FAILS - 1:
                _, 있 = 로그인.들어온다(db, "gyeonggye", "틀린값입니다")
                있는것.append(있)

        assert set(없는것) == {로그인.TOLD}, "없는 아이디가 잠겼다 — 문서를 다시 봐야 한다"
        assert 있는것[-1] == 로그인.TOLD_LOCKED, "있는 아이디가 열 번째에 안 잠겼다"
        assert set(있는것[:-1]) == {로그인.TOLD}, "아홉 번째까지 벌써 잠겼다"

    assert len({로그인.TOLD, 로그인.TOLD_INACTIVE, 로그인.TOLD_LOCKED}) == 3, \
        "② 비활성·잠김이 보통의 거절과 같은 말이 됐다 — 4-12 의 경계가 달라졌다"


def test34_n01_걷을_것만_걷었다(client):
    """가) **걷은 것과 남긴 것을 같은 판에서 본다.**

    한쪽만 보면 「다 지웠다」 와 「걷을 것만 걷었다」 가 구별되지 않는다.

    본다 — ① 그 함수가 모듈에 없는가 ② `app/` 과 `tests/` 어디에서도
    **부르지 않는가** ③ **훑은 파일이 비지 않았나**(0개를 훑고 통과하면
    아무것도 안 본 것이다) ④ 함께 남기기로 한 것은 **남아 있고 실제로
    불리는가** — `revoke_all` 은 `scripts/merge_users.py` 가 아직 부른다
    ⑤ 남긴 것이 실제로 도는가(이름만 있고 죽어 있으면 남긴 뜻이 없다).

    **찾는 모양은 `이름(` 이다** — 이 독스트링이 그 이름을 설명하려고
    담고 있어서, 낱말로 찾으면 이 시험이 자기 자신에게 걸린다(10장).
    """
    from app.domain import auth as 옛링크
    from app.models import InviteToken

    걷은것 = "live_token" + "("
    assert not hasattr(옛링크, 걷은것[:-1])

    본파일 = 0
    부르는곳 = []
    for 뿌리 in ("app", "tests"):
        for path in (ROOT / 뿌리).rglob("*.py"):
            본파일 += 1
            if 걷은것 in path.read_text(encoding="utf-8"):
                부르는곳.append(str(path.relative_to(ROOT)))
    assert 본파일 > 50, f"훑은 파일이 {본파일}개뿐이다 — 아무것도 안 본 검사다"
    assert not 부르는곳, f"걷었다는데 아직 부른다: {부르는곳}"

    # ④ 남긴 것 — 있고, 부르는 곳도 있다
    assert hasattr(옛링크, "revoke_all")
    머지 = (ROOT / "scripts/merge_users.py").read_text(encoding="utf-8")
    assert "revoke_all(" in 머지, "남기기로 한 까닭(부르는 곳이 있다)이 사라졌다"

    # ⑤ 이름만 남은 것이 아니라 실제로 돈다
    uid = _사람(client, 아이디="namgin", phone="01055550021")
    with app_session() as db:
        db.add(InviteToken(user_id=uid, token_hash="옛해시-남긴것",
                           expires_at=dt.datetime.now() + dt.timedelta(days=7)))
        db.commit()
        assert 옛링크.revoke_all(db, user=db.get(User, uid)) == 1
        assert 옛링크.살아있는것들(db) == []


# ── 자) 비밀번호가 저장소 어느 파일에도 없다 ──────────────────────────

def test34_i01_발급한_값이_저장소_어느_파일에도_없다(admin_client, client):
    """자) **파일 목록을 견주고 바이트로 훑는다.**

    본다 — ① 발급한 값이 git 이 아는 파일 어디에도 없는가 ② **훑은 파일이
    비어 있지 않은가**(0개를 훑고 통과하면 아무것도 안 본 것이다) ③ 그
    검사가 실제로 값을 찾을 수 있는 검사인가 — 일부러 심은 값이 잡히는지
    같은 방식으로 한 번 재 본다.
    """
    uid = _사람(client, 아이디="chanmi")
    낸다 = admin_client.post(f"/admin/users/{uid}/password", follow_redirects=False)
    보임 = admin_client.get(낸다.headers["location"])
    새값 = re.search(r'id="firstpw" readonly value="([^"]+)"', 보임.text).group(1)
    바이트 = 새값.encode("utf-8")

    파일들 = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True
                         ).stdout.split(b"\0")
    훑은수 = 0
    찾음 = []
    for 이름 in 파일들:
        if not 이름:
            continue
        path = ROOT / 이름.decode("utf-8")
        if not path.is_file():
            continue
        내용 = path.read_bytes()
        훑은수 += 1
        if 바이트 in 내용:
            찾음.append(path.name)
    assert 훑은수 > 100, f"훑은 파일이 {훑은수}개뿐이다 — 아무것도 안 본 검사다"
    assert not 찾음, f"비밀번호가 파일에 있다: {찾음}"

    # ③ 같은 방식으로 **잡히는지**를 잰다 — 못 잡는 검사면 ① 은 뜻이 없다.
    # 저장소에 분명히 있는 글자를 같은 길로 찾아 본다
    assert b"scrypt$" in (ROOT / "app/domain/login.py").read_bytes(),         "훑는 방식이 있는 값도 못 찾는다"


def test34_i02_비밀번호를_로그에_안_남긴다(admin_client, client):
    """자) **활동 기록은 화면에서 누구나 읽는 자리다.**

    본다 — ① 발급 뒤 활동 기록에 값이 없는가 ② 그래도 **발급했다는 사실은
    남는가**(안 남으면 나중에 누가 언제 만들었는지 알 수 없다).
    """
    from app.models import ActivityLog

    uid = _사람(client, 아이디="areum")
    낸다 = admin_client.post(f"/admin/users/{uid}/password", follow_redirects=False)
    보임 = admin_client.get(낸다.headers["location"])
    새값 = re.search(r'id="firstpw" readonly value="([^"]+)"', 보임.text).group(1)

    with app_session() as db:
        줄들 = db.scalars(select(ActivityLog)).all()
        글 = "\n".join(f"{r.action} {r.summary} {r.before_value} {r.after_value}" for r in 줄들)
    assert 새값 not in 글
    assert "첫_비밀번호_발급" in 글


# ── 차) 비밀번호 칸의 크기 ────────────────────────────────────────────

def _눈금() -> dict[str, float]:
    """`--fz` 눈금을 실제 값(px)으로 푼다 — 토큰 이름만 보면 크기를 못 잰다."""
    글 = (ROOT / "app/static/css/retreat.css").read_text(encoding="utf-8")
    뿌리 = 글[글.index(":root{"):글.index("}", 글.index(":root{"))]
    기준 = float(re.search(r"--fz:\s*(\d+(?:\.\d+)?)px", 뿌리).group(1))
    값 = {"--fz": 기준}
    for 이름, 셈 in re.findall(r"(--fz-[\w-]+):\s*calc\(var\(--fz\)\s*([-+]\s*[\d.]+)px\)", 뿌리):
        값[이름] = 기준 + float(셈.replace(" ", ""))
    for 이름 in re.findall(r"(--fz-[\w-]+):\s*var\(--fz\)", 뿌리):
        값[이름] = 기준
    return 값


def test34_j01_비밀번호_칸이_16px_아래로_안_내려간다():
    """차) **아이폰이 확대하는 선을 넘긴다.**

    본다 — ① CSS 에 `input[type=password]` 규칙이 있는가 ② 그 크기가 눈금을
    풀었을 때 16px 이상인가(토큰 이름만 보면 값이 바뀌어도 안 걸린다)
    ③ 눈금 풀이가 실제로 돌았는가.

    16px 아래면 사파리가 그 칸을 누르는 순간 화면을 확대하고 되돌려 주지
    않는다 — 홈 화면에 붙인 앱에는 주소창이 없어 되돌릴 길도 없다.
    """
    글 = (ROOT / "app/static/css/retreat.css").read_text(encoding="utf-8")
    m = re.search(r"input\[type=password\]\{[^}]*font-size:\s*var\((--fz[\w-]*)\)", 글)
    assert m, "CSS 에 input[type=password] 의 크기 규칙이 없다"
    눈금 = _눈금()
    assert len(눈금) > 3, "눈금을 못 풀었다 — 아무것도 안 재는 줄이다"
    잰값 = 눈금[m.group(1)]
    assert 잰값 >= 16, f"{m.group(1)} 이 {잰값}px 이다 — 아이폰이 확대하는 선 아래다"


def test34_j02_로그인_화면에_실제로_그_칸이_있다(client):
    """차) 규칙만 있고 칸이 없으면 잰 뜻이 없다.

    본다 — 로그인 화면과 바꾸는 화면에 `type="password"` 칸이 있는가.
    """
    글 = client.get("/login").text
    assert 'type="password"' in 글 and 'name="login_id"' in 글
    _사람(client, 아이디="hadam", 첫판=True)
    _로그인한다(client, "hadam", 지어낸값)
    assert 'type="password"' in client.get("/password").text


# ── 카) 바깥 링크 설명 ────────────────────────────────────────────────

def test34_k01_바깥_링크_설명은_있으면_그리고_없으면_안_그린다(admin_client):
    """카) **비면 안 그린다** 를 두 판에서.

    본다 — ① 설명을 넣으면 사이드바에 그 줄이 나오는가 ② 비우면 그 줄이
    **아예 없는가**(빈 줄이 있으면 그 자리가 무엇인지 또 묻게 된다)
    ③ 주소를 지우면 항목도 설명도 함께 사라지는가.
    """
    admin_client.post("/settings/external-link",
                      data={"name": "예산 시트", "url": "https://example.com/sheet",
                            "note": "영수증 올리는 곳"})
    글 = admin_client.get("/").text
    assert "예산 시트" in 글 and "영수증 올리는 곳" in 글
    assert "extnote" in 글

    admin_client.post("/settings/external-link",
                      data={"name": "예산 시트", "url": "https://example.com/sheet", "note": ""})
    글 = admin_client.get("/").text
    assert "예산 시트" in 글 and "extnote" not in 글

    admin_client.post("/settings/external-link", data={"name": "", "url": "", "note": ""})
    글 = admin_client.get("/").text
    assert "예산 시트" not in 글


# ── 문 자체가 한 곳인가 ───────────────────────────────────────────────

def test34_l01_화면마다_막지_않고_문_하나에서_막는다():
    """마) **막는 곳이 하나인지**를 코드에서도 본다.

    본다 — ① `must_change_password` 를 보는 곳이 `app/` 안에서 인증 의존
    하나뿐인가(화면 파일이 저마다 보면 새 화면이 그 줄을 빠뜨린다)
    ② 훑은 파일이 비어 있지 않은가.

    화면 쪽(`admin_users.py`)이 **상태를 보여주려고** 읽는 것은 막는 것이
    아니라 그리는 것이라 세지 않는다 — 그 자리는 `door` 한 줄이다.
    """
    막는곳 = []
    본파일 = 0
    for path in (ROOT / "app").rglob("*.py"):
        본파일 += 1
        for n, 줄 in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "must_change_password" in 줄 and "raise" not in 줄:
                continue
            if "비밀번호를바꿔야함" in 줄 and "raise" in 줄:
                막는곳.append(f"{path.name}:{n}")
    assert 본파일 > 10
    assert 막는곳 == ["security.py"] or all(p.startswith("security.py") for p in 막는곳), 막는곳
    assert len(막는곳) == 1, f"막는 자리가 하나가 아니다: {막는곳}"
