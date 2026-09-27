"""5단계 — 수입 화면과 입금 캡처 (CLAUDE.md 7-6 · 2026-09-27).

- `llm.ask` 에 그림을 실을 수 있다. **글만 보낼 때의 모양은 안 바뀐다**
  (회의록 쪽 호출이 그대로 돌아야 한다)
- **실제 API 를 부르지 않는다.** `httpx.post` 를 가짜로 바꿔 나가는 몸통과
  들어오는 대답만 잰다 — 시험이 진짜 요금을 쓰면 안 되고, 대답이 매번 달라
  무엇을 지키는지 알 수 없게 된다 (`test_suggest_llm.py` 가 둔 그 규칙)
- 캡처 → 읽기 → 담기 → **겹침 건너뛰기** → 줄 편집 → 필터
- 막는 쪽: 키가 없을 때 · JSON 이 깨졌을 때 · 같은 캡처를 두 번 올렸을 때

**시험 자료에 실명이 없다** (11-2). 수는 박지 않는다 (11-3).
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from sqlalchemy import select

from app import models
from app.domain import deposits as D
from app.domain import llm as llm_mod
from tests.conftest import app_session, login_as, make_user

TODAY = dt.date.today()
그림 = b"\x89PNG\r\n\x1a\n" + "가짜그림".encode()


class 가짜대답:
    """`llm.대답` 중 우리가 쓰는 자리만 흉내 낸다."""

    def __init__(self, text: str, 원: float = 30.0):
        self.text = text
        self.원 = 원
        self.model = "가짜모델"


def 부르기를(text: str, 기록=None):
    def call(system, user, **kw):
        if 기록 is not None:
            기록.append({"system": system, "user": user, "kw": kw})
        return 가짜대답(text)

    return call


줄셋 = json.dumps({"줄": [
    {"이름": "가나다", "금액": 50000, "시각": "09.15 14:22", "잔액": 1_200_000},
    {"이름": "라마바", "금액": 30000, "시각": "09.15 15:01", "잔액": 1_230_000},
    {"이름": "사아자", "금액": -9000, "시각": "09.15 16:00", "잔액": 1_221_000},
]}, ensure_ascii=False)


@pytest.fixture
def 판(admin_client):
    with app_session() as db:
        r = models.Retreat(name="수입 회차", meal_subsidy_per_person=8000,
                           start_date=TODAY + dt.timedelta(days=30),
                           end_date=TODAY + dt.timedelta(days=32))
        db.add(r)
        db.flush()
        db.add(models.Department(retreat_id=r.id, key="chongmuM", name="1 총무M", sort_order=0))
        db.commit()
        rid = r.id
    return admin_client, rid


def 입금(db, rid, **kw):
    값 = {"depositor": "가나다", "amount": 50000, "deposited_text": "09.15 14:22",
          "balance": 1_200_000}
    값.update(kw)
    d = models.IncomeDeposit(retreat_id=rid, **값)
    db.add(d)
    db.flush()
    return d


# ── ㄱ. llm.ask 에 그림 싣기 ──────────────────────────────────────


class 가짜응답:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _가짜post(monkeypatch, 담을곳, *, payload=None):
    payload = payload or {"content": [{"type": "text", "text": "{}"}],
                          "usage": {"input_tokens": 10, "output_tokens": 5},
                          "model": "가짜모델", "stop_reason": "end_turn"}

    def post(url, **kw):
        담을곳.append(kw)
        return 가짜응답(payload)

    monkeypatch.setattr(llm_mod.httpx, "post", post)
    monkeypatch.setattr(llm_mod, "read_key", lambda: "sk-가짜")


def test77_a01_그림을_실으면_블록_목록으로_나간다(monkeypatch):
    보낸것 = []
    _가짜post(monkeypatch, 보낸것)
    llm_mod.ask("시스템", "이 캡처를 읽어라", images=[("image/png", 그림)])
    content = 보낸것[0]["json"]["messages"][0]["content"]
    assert isinstance(content, list) and len(content) == 2
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    # 그림이 앞, 지시가 뒤 — 지시를 보고 그림을 읽는다
    assert content[1] == {"type": "text", "text": "이 캡처를 읽어라"}


def test77_a02_그림이_없으면_옛_모양_그대로다(monkeypatch):
    """회의록 쪽 호출이 그대로 돌아야 한다 — 같은 일을 하는 두 모양을 안 만든다."""
    보낸것 = []
    _가짜post(monkeypatch, 보낸것)
    llm_mod.ask("시스템", "회의록입니다")
    assert 보낸것[0]["json"]["messages"][0]["content"] == "회의록입니다"


def test77_a03_모르는_그림_종류는_보내기_전에_막는다(monkeypatch):
    보낸것 = []
    _가짜post(monkeypatch, 보낸것)
    with pytest.raises(llm_mod.LlmUnavailable) as e:
        llm_mod.ask("시스템", "읽어라", images=[("image/tiff", 그림)])
    assert "image/tiff" in str(e.value)
    assert not 보낸것, "거절할 것을 실어 보냈다 — 400 만 돌아와 까닭이 화면에 안 남는다"


def test77_a04_그림을_실어도_대답을_그대로_읽는다(monkeypatch):
    보낸것 = []
    _가짜post(monkeypatch, 보낸것, payload={
        "content": [{"type": "text", "text": 줄셋}],
        "usage": {"input_tokens": 1200, "output_tokens": 300},
        "model": "가짜모델", "stop_reason": "end_turn"})
    대답 = llm_mod.ask("시스템", "읽어라", images=[("image/jpeg", 그림)])
    assert 대답.in_tokens == 1200 and 대답.out_tokens == 300
    assert 대답.원 > 0, "요금을 못 셌다 — 화면과 로그에 남길 값이다"


# ── ㄴ. 캡처를 읽어 담는다 ────────────────────────────────────────


def test77_b01_출금_줄은_안_담는다():
    줄들, _ = D.읽는다(그림, "image/png", 부르기=부르기를(줄셋))
    assert [하나["이름"] for 하나 in 줄들] == ["가나다", "라마바"]
    assert all(하나["금액"] > 0 for 하나 in 줄들)


def test77_b02_그림을_그대로_실어_보낸다():
    기록 = []
    D.읽는다(그림, "image/png", 부르기=부르기를(줄셋, 기록))
    assert 기록[0]["kw"]["images"] == [("image/png", 그림)]


def test77_b03_담으면_전부_후원금이고_추정이다(판):
    _, rid = 판
    줄들, _ = D.읽는다(그림, "image/png", 부르기=부르기를(줄셋))
    with app_session() as db:
        넣음, 건너뜀 = D.담는다(db, retreat_id=rid, 줄들=줄들)
        db.commit()
        assert (넣음, 건너뜀) == (2, 0)
        담긴 = D.목록(db, retreat_id=rid)
        assert all(D.분류(d) == D.후원금 for d in 담긴)
        assert all(D.추정인가(d) for d in 담긴)
        assert [d.deposited_text for d in 담긴] == ["09.15 14:22", "09.15 15:01"]


def test77_b04_같은_캡처를_두_번_올려도_안_쌓인다(판):
    _, rid = 판
    줄들, _ = D.읽는다(그림, "image/png", 부르기=부르기를(줄셋))
    with app_session() as db:
        D.담는다(db, retreat_id=rid, 줄들=줄들)
        db.commit()
        넣음, 건너뜀 = D.담는다(db, retreat_id=rid, 줄들=줄들)
        db.commit()
        assert (넣음, 건너뜀) == (0, 2)
        assert len(D.목록(db, retreat_id=rid)) == 2


def test77_b05_잔액이_비어도_겹침으로_잡는다(판):
    """SQLite 유니크로 뒀으면 NULL 끼리가 달라 쌓였을 자리다 (4-18 의 그 자리)."""
    _, rid = 판
    줄들 = [{"이름": "가나다", "금액": 50000, "시각": "09.15 14:22", "잔액": None}]
    with app_session() as db:
        D.담는다(db, retreat_id=rid, 줄들=줄들)
        db.commit()
        넣음, 건너뜀 = D.담는다(db, retreat_id=rid, 줄들=줄들)
        db.commit()
        assert (넣음, 건너뜀) == (0, 1)


def test77_b06_다른_회차의_같은_줄은_겹침이_아니다(판):
    _, rid = 판
    with app_session() as db:
        다른 = models.Retreat(name="다른 회차", start_date=TODAY, end_date=TODAY)
        db.add(다른)
        db.flush()
        줄들 = [{"이름": "가나다", "금액": 50000, "시각": "09.15 14:22", "잔액": 1}]
        D.담는다(db, retreat_id=rid, 줄들=줄들)
        넣음, _ = D.담는다(db, retreat_id=다른.id, 줄들=줄들)
        db.commit()
        assert 넣음 == 1


# ── ㄷ. 못 읽었을 때 ──────────────────────────────────────────────


def test77_c01_JSON_이_아니면_못읽음이다():
    with pytest.raises(D.못읽음):
        D.읽는다(그림, "image/png", 부르기=부르기를("미안, 못 읽겠어요"))


def test77_c02_한_줄도_못_읽으면_빈_목록이고_못읽음이_아니다():
    """모델이 「없다」 고 한 것과 우리가 못 읽은 것은 **다른 사정**이다 (4-10 조건 4)."""
    줄들, _ = D.읽는다(그림, "image/png", 부르기=부르기를('{"줄": []}'))
    assert 줄들 == []


def test77_c03_일부만_읽혀도_읽은_만큼_담는다(판):
    """꼴이 틀린 줄이 섞여도 나머지를 버리지 않는다."""
    _, rid = 판
    섞인 = json.dumps({"줄": [
        {"이름": "가나다", "금액": 50000, "시각": "09.15", "잔액": 1},
        {"이름": "", "금액": 10000, "시각": "09.15", "잔액": 2},
        {"이름": "라마바", "금액": "몰라", "시각": "09.15", "잔액": 3},
    ]}, ensure_ascii=False)
    줄들, _ = D.읽는다(그림, "image/png", 부르기=부르기를(섞인))
    assert len(줄들) == 1


def test77_c04_키가_없으면_그_말이_그대로_올라온다(monkeypatch, 판):
    client, rid = 판
    monkeypatch.setattr(llm_mod, "read_key", lambda: None)
    r = client.post(f"/income/deposits/capture?retreat_id={rid}",
                    files={"capture": ("cap.png", 그림, "image/png")},
                    data={"filter": ""})
    assert r.status_code == 503
    말 = r.json()["detail"]
    assert "캡처를 읽지 못했습니다" in 말
    # **접두사만 보면 「그대로 표시」 가 안 재진다** (커밋 전 검토 [O]) —
    # 화면이 보이는 것은 `상태().말` 이고 그 말이 실려야 사람이 무엇을 할지 안다
    assert llm_mod.상태().말 in 말, "키가 없는 까닭이 안 실렸다"


def test77_c05_JSON_이_깨지면_다시_찍으라고_말한다(monkeypatch, 판):
    client, rid = 판
    monkeypatch.setattr(D, "읽는다", lambda *a, **k: (_ for _ in ()).throw(D.못읽음("x")))
    r = client.post(f"/income/deposits/capture?retreat_id={rid}",
                    files={"capture": ("cap.png", 그림, "image/png")},
                    data={"filter": ""})
    assert r.status_code == 502
    assert "다시 찍어" in r.json()["detail"]


def test77_c06_그림이_아니면_보내기_전에_막는다(판):
    client, rid = 판
    r = client.post(f"/income/deposits/capture?retreat_id={rid}",
                    files={"capture": ("cap.pdf", b"%PDF", "application/pdf")},
                    data={"filter": ""})
    assert r.status_code == 400 and "PNG" in r.json()["detail"]


# ── ㄹ. 화면 — 올리고 · 고치고 · 거른다 ──────────────────────────


def test77_d01_캡처를_올리면_읽은_수와_겹친_수를_말한다(monkeypatch, 판):
    client, rid = 판
    monkeypatch.setattr(D, "읽는다",
                        lambda *a, **k: (D.줄로바꾼다(json.loads(줄셋)), 가짜대답(줄셋)))
    for 차례 in (1, 2):
        r = client.post(f"/income/deposits/capture?retreat_id={rid}",
                        files={"capture": ("cap.png", 그림, "image/png")},
                        data={"filter": ""}, follow_redirects=False)
        assert r.status_code == 303
        말 = r.cookies.get("dcb_flash") or ""
        import urllib.parse
        말 = urllib.parse.unquote(말)
        assert "입금 2건 읽음" in 말
        if 차례 == 2:
            assert "겹친 입금 2건 건너뜀" in 말
    with app_session() as db:
        assert len(D.목록(db, retreat_id=rid)) == 2


def test77_d02_줄을_회비로_바꾸면_추정이_풀린다(판):
    client, rid = 판
    with app_session() as db:
        d = 입금(db, rid)
        db.commit()
        did = d.id
    r = client.post(f"/income/deposits/{did}?retreat_id={rid}",
                    data={"kind": "회비", "fee_amount": "20000"}, follow_redirects=False)
    assert r.status_code == 303
    with app_session() as db:
        d = db.get(models.IncomeDeposit, did)
        assert D.회비몫(d) == 20000 and D.후원금몫(d) == 30000
        assert D.분류(d) == D.섞임
        assert not D.추정인가(d)


def test77_d03_금액을_비우면_전액_회비다(판):
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid).id
        db.commit()
    client.post(f"/income/deposits/{did}?retreat_id={rid}", data={"kind": "회비", "fee_amount": ""})
    with app_session() as db:
        d = db.get(models.IncomeDeposit, did)
        assert D.분류(d) == D.회비 and D.후원금몫(d) == 0


def test77_d04_후원금으로_두고_저장해도_추정이_풀린다(판):
    """보고서 「후원금이 맞다」 고 정한 줄을 영영 추정으로 두지 않는다."""
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid).id
        db.commit()
    client.post(f"/income/deposits/{did}?retreat_id={rid}", data={"kind": "후원금"})
    with app_session() as db:
        d = db.get(models.IncomeDeposit, did)
        assert D.분류(d) == D.후원금 and not D.추정인가(d)


def test77_d05_금액_밖의_회비는_막는다(판):
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid, amount=50000).id
        db.commit()
    r = client.post(f"/income/deposits/{did}?retreat_id={rid}",
                    data={"kind": "회비", "fee_amount": "50001"})
    assert r.status_code == 400
    # **아래쪽도 잰다** — 화면은 `min="0"` 이 먼저 막지만 서버가 마지막이다
    # (2026-09-27 둘째 검토 [F2] — 위쪽만 재고 「0~금액 밖」 이라고 적고 있었다)
    r2 = client.post(f"/income/deposits/{did}?retreat_id={rid}",
                     data={"kind": "회비", "fee_amount": "-1"})
    assert r2.status_code == 400
    with app_session() as db:
        assert D.추정인가(db.get(models.IncomeDeposit, did)), "막았는데 값이 들어갔다"


def test77_d06_필터가_걸린다(판):
    _, rid = 판
    with app_session() as db:
        전액회비 = 입금(db, rid, depositor="회비사람", deposited_text="a")
        D.사람이정한다(전액회비, 회비금액=전액회비.amount)
        반반 = 입금(db, rid, depositor="반반사람", deposited_text="b")
        D.사람이정한다(반반, 회비금액=10000)
        그대로 = 입금(db, rid, depositor="추정사람", deposited_text="c")
        db.commit()
        줄들 = D.목록(db, retreat_id=rid)
        이름 = lambda 값: sorted(d.depositor for d in D.걸러낸다(줄들, 값))  # noqa: E731
        assert 이름("fee") == ["반반사람", "회비사람"]
        assert 이름("donation") == ["반반사람", "추정사람"]
        assert 이름("check") == ["추정사람"]
        assert len(D.걸러낸다(줄들, "")) == 3
        assert 그대로.id


def test77_d07_취소한_줄은_합과_필터에서_빠지고_행은_남는다(판):
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid).id
        db.commit()
    client.post(f"/income/deposits/{did}/cancel?retreat_id={rid}", data={})
    with app_session() as db:
        줄들 = D.목록(db, retreat_id=rid)
        assert len(줄들) == 1, "지우지 않는다 (0장)"
        assert D.합(줄들)["건수"] == 0
        assert D.걸러낸다(줄들, "check") == []
    # 취소된 줄은 못 고친다 (7-3 의 그 규칙)
    r = client.post(f"/income/deposits/{did}?retreat_id={rid}", data={"kind": "회비"})
    assert r.status_code == 409


def test77_d08_화면이_뜨고_필터_칩과_올리는_자리가_있다(판):
    client, rid = 판
    with app_session() as db:
        입금(db, rid)
        db.commit()
    html = client.get(f"/income?retreat_id={rid}").text
    assert "입금 내역 캡처 올리기" in html
    assert 'id="incchips"' in html and "확인 필요" in html
    assert "추정" in html
    # 사이드바에 예산과 지출 사이
    assert html.index('href="/budget"') < html.index('href="/income"') < html.index('href="/expenses"')
    # **사람이 정한 여섯 칸이 표 머리에 다 있다** (2026-09-27 둘째 검토 [D2]) —
    # 대조 표가 이 시험을 가리키는데 「추정」 하나만 겹치고 있었다
    머리 = html[html.index('id="deptbl"'):html.index("</thead>", html.index('id="deptbl"'))]
    for 칸 in ("입금자", "금액", "입금 시각", "분류", "회비", "후원금", "잔액"):
        assert f">{칸}</th>" in 머리, f"표 머리에 「{칸}」 칸이 없다"


def test77_d09_수입_항목은_7가지_종류로_고른다(판):
    from app.domain.budget import 수입종류
    client, rid = 판
    html = client.get(f"/income?retreat_id={rid}").text
    assert len(수입종류) == 7
    for 종류 in 수입종류:
        assert f"<option>{종류}</option>" in html or f">{종류}</option>" in html


def test77_d10_예산_화면에는_수입_표가_없고_길만_남는다(판):
    client, rid = 판
    html = client.get(f"/budget?retreat_id={rid}").text
    assert 'href="/income' in html, "옮긴 자리를 안 가리키면 사람이 못 찾는다"
    assert "수입 추가" not in html, "쓰는 길이 두 곳이 됐다"


def test77_d11_열람_전용은_올리지도_고치지도_못한다(판):
    """**셋을 다 잰다** — 보는 것은 되고 올리는 것도 고치는 것도 막힌다.

    「고치는 것」 만 재고 이름에 「올리지도」 를 적어 두면 그 라우트는 한 번도
    안 재집니다(2026-09-27 커밋 전 검토 [H]). 그리고 **303 을 통과로 받지
    않습니다** — `require_admin` 은 403 하나를 내므로, 303 을 허용하면 성공
    리다이렉트가 그대로 지나가 이 단언이 아무것도 안 가릅니다.
    """
    _, rid = 판
    from fastapi.testclient import TestClient

    from app.main import app

    make_user("가명열람", "01099998888", role="viewer")
    보는이 = TestClient(app)
    login_as(보는이, "01099998888", name="가명열람")
    with app_session() as db:
        did = 입금(db, rid).id
        db.commit()
    assert 보는이.get(f"/income?retreat_id={rid}").status_code == 200
    assert 보는이.post(f"/income/deposits/{did}?retreat_id={rid}",
                     data={"kind": "회비"}).status_code == 403
    올림 = 보는이.post(f"/income/deposits/capture?retreat_id={rid}",
                     files={"capture": ("cap.png", 그림, "image/png")}, data={"filter": ""})
    assert 올림.status_code == 403, "열람 전용이 캡처를 올렸다"
    assert 보는이.post(f"/income/deposits/{did}/cancel?retreat_id={rid}",
                     data={}).status_code == 403
    with app_session() as db:
        d = db.get(models.IncomeDeposit, did)
        assert D.추정인가(d) and d.canceled_at is None, "열람 전용이 고쳤다"


# ── ㅁ. 막는 쪽 — 보내기 전에 ────────────────────────────────────


def test77_e01_빈_파일은_보내기_전에_막는다(판):
    """모르는 종류를 막는 것과 같은 자리다 — 보내 봐야 값만 나간다."""
    client, rid = 판
    r = client.post(f"/income/deposits/capture?retreat_id={rid}",
                    files={"capture": ("cap.png", b"", "image/png")}, data={"filter": ""})
    assert r.status_code == 400 and "빈 파일" in r.json()["detail"]


def test77_e02_5MB_를_넘으면_보내기_전에_막고_얼마인지_말한다(판, monkeypatch):
    """Anthropic 이 그림 한 장을 5MB 까지 받는다 — 넘으면 거절당하므로 우리 말로 막는다.

    **부르지 않는 것까지 잰다** — 막는다고 적어 두고 실어 보내면 값이 나간다.
    """
    from app.routers import income as R

    client, rid = 판
    불렀나 = []
    monkeypatch.setattr(D, "읽는다", lambda *a, **k: 불렀나.append(1))
    r = client.post(f"/income/deposits/capture?retreat_id={rid}",
                    files={"capture": ("cap.png", b"x" * (R.MAX_CAPTURE_BYTES + 1), "image/png")},
                    data={"filter": ""})
    assert r.status_code == 400
    assert "5MB" in r.json()["detail"] and "MB)" in r.json()["detail"], "얼마였는지 안 말한다"
    assert not 불렀나, "막을 것을 실어 보냈다"


def test77_e03_상한_안쪽은_지나간다(판, monkeypatch):
    """막히면 안 되는 것이 통과하는가 (11-3 의 그 둘째 축)."""
    from app.routers import income as R

    client, rid = 판
    monkeypatch.setattr(D, "읽는다", lambda *a, **k: ([], 가짜대답("{}")))
    r = client.post(f"/income/deposits/capture?retreat_id={rid}",
                    files={"capture": ("cap.png", b"x" * (R.MAX_CAPTURE_BYTES - 1), "image/png")},
                    data={"filter": ""}, follow_redirects=False)
    assert r.status_code == 303, "상한 안쪽인데 막혔다"


def test77_d12_활동_기록에_남는다(판):
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid).id
        db.commit()
    client.post(f"/income/deposits/{did}?retreat_id={rid}",
                data={"kind": "회비", "fee_amount": "10000"})
    with app_session() as db:
        남은 = db.scalars(select(models.ActivityLog)
                        .where(models.ActivityLog.action == "입금_분류")).all()
        assert 남은 and 남은[-1].target_id == did
