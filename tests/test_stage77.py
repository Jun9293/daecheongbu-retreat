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


# ── ㅂ. 이름·금액 고치기 (2026-09-27 사람이 정함 · 봐둘것 BK-c ㄴ) ──


def test77_f01_취소된_줄도_이름과_금액을_고친다(판):
    """**이름이 잘못 읽혀 취소한 줄을 고쳐 되살리는 것**이 이 자리가 생긴 까닭이다.

    분류(`save_deposit`)는 취소된 줄에서 409 지만, 이것은 「그때 무엇이
    들어왔나」 를 바로잡는 자리라 성격이 다르다.
    """
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid, depositor="가나다", amount=50000).id
        db.commit()
    client.post(f"/income/deposits/{did}/cancel?retreat_id={rid}", data={})
    r = client.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                    data={"depositor": "라마바", "amount": "45000"}, follow_redirects=False)
    assert r.status_code == 303
    with app_session() as db:
        d = db.get(models.IncomeDeposit, did)
        assert (d.depositor, d.amount) == ("라마바", 45000)
        assert d.canceled_at is not None, "고치면서 되살아났다 — 되살리기는 따로다"
    # 분류는 여전히 막힌다
    assert client.post(f"/income/deposits/{did}?retreat_id={rid}",
                       data={"kind": "회비"}).status_code == 409


def test77_f02_고쳐도_같은_캡처는_그대로_건너뛴다(판):
    """**취소의 뜻을 안 바꾼다** (사람이 정함) — 겹침 열쇠는 읽은 때의 값이다."""
    client, rid = 판
    줄들 = [{"이름": "가나다", "금액": 50000, "시각": "09.15 14:22", "잔액": 1_200_000}]
    with app_session() as db:
        넣음, _ = D.담는다(db, retreat_id=rid, 줄들=줄들)
        db.commit()
        assert 넣음 == 1
        did = D.목록(db, retreat_id=rid)[0].id
    client.post(f"/income/deposits/{did}/cancel?retreat_id={rid}", data={})
    client.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                data={"depositor": "라마바", "amount": "99999"})
    with app_session() as db:
        넣음, 건너뜀 = D.담는다(db, retreat_id=rid, 줄들=줄들)
        db.commit()
        assert (넣음, 건너뜀) == (0, 1), "고친 금액이 열쇠를 움직였다"
        assert len(D.목록(db, retreat_id=rid)) == 1


def test77_f03_금액을_줄이면_회비_몫도_따라_줄어든다(판):
    """안 맞추면 되살린 뒤 그 줄에 금액보다 큰 회비가 적혀 있다."""
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid, amount=50000).id
        db.commit()
    client.post(f"/income/deposits/{did}?retreat_id={rid}",
                data={"kind": "회비", "fee_amount": "50000"})
    client.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                data={"depositor": "가나다", "amount": "30000"})
    with app_session() as db:
        d = db.get(models.IncomeDeposit, did)
        assert d.fee_amount == 30000 and D.회비몫(d) == 30000 and D.후원금몫(d) == 0


def test77_f04_고쳐도_추정은_안_풀린다(판):
    """이름을 고친 것이 「회비인지 후원금인지 봤다」 는 뜻은 아니다."""
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid).id
        db.commit()
    client.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                data={"depositor": "라마바", "amount": "50000"})
    with app_session() as db:
        assert D.추정인가(db.get(models.IncomeDeposit, did))


def test77_f05_빈_이름과_0원은_막는다(판):
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid).id
        db.commit()
    for 값 in ({"depositor": "  ", "amount": "50000"},
               {"depositor": "가나다", "amount": "0"},
               {"depositor": "가나다", "amount": "몰라"}):
        assert client.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                           data=값).status_code == 400, 값
    with app_session() as db:
        d = db.get(models.IncomeDeposit, did)
        assert (d.depositor, d.amount) == ("가나다", 50000), "막았는데 값이 들어갔다"


def test77_f08_옛_줄도_고칠_때_열쇠가_언다(판):
    """칸이 붙기 전에 선 줄(`dup_key` 가 빈 줄)도 **고치는 그 순간** 얼린다.

    부팅이 값을 채우는 것이 아니라 사람이 그 줄을 고칠 때 같이 채우는 것이라
    11-2 가 막은 자리가 아니다 (2026-09-27 커밋 전 검토 [E]).
    """
    client, rid = 판
    with app_session() as db:
        d = 입금(db, rid, amount=50000)
        d.dup_key = None          # 칸이 붙기 전에 선 줄
        db.commit()
        did, 옛열쇠 = d.id, D.열쇠of(d)
    client.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                data={"depositor": "라마바", "amount": "77000"})
    with app_session() as db:
        d = db.get(models.IncomeDeposit, did)
        assert d.dup_key == 옛열쇠, "고치는 순간에 안 얼었다"
        assert D.열쇠of(d) == 옛열쇠, "고친 금액을 따라 열쇠가 움직였다"


def test77_f09_열쇠는_칸막이로_갈린다():
    """이어붙이면 자릿수가 옮겨 가며 **다른 줄이 같은 열쇠**가 된다.

    걸렸을 때 화면에는 아무 표시도 안 나고 「겹쳤다」 로 세어진다 — 2026-09-27
    커밋 전 검토가 이 자리를 짚었고(실제로는 칸막이가 있었다) 그 뒤로 여기서 잰다.
    """
    assert D.열쇠("", 10000, 1234567) != D.열쇠("", 100001, 234567)
    assert D.칸막이 in D.열쇠("09.15", 1, 2)


def test77_f10_금액을_올리면_회비는_그대로다(판):
    """회비는 비율이 아니라 액수다 (7-6) — 그래서 분류가 바뀐다. 봐둘것 BK-d."""
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid, amount=50000).id
        db.commit()
    client.post(f"/income/deposits/{did}?retreat_id={rid}",
                data={"kind": "회비", "fee_amount": "50000"})
    client.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                data={"depositor": "가나다", "amount": "80000"})
    with app_session() as db:
        d = db.get(models.IncomeDeposit, did)
        assert D.회비몫(d) == 50000 and D.후원금몫(d) == 30000
        assert D.분류(d) == D.섞임
        assert not D.추정인가(d), "「추정」 은 안 건드린다 — 그래서 확인 필요에도 안 뜬다"


def test77_f06_화면에_이름_금액_칸과_회비_안내가_있다(판):
    """안내 줄은 **산 줄**에만 뜬다 — 취소된 줄에는 분류 폼 자체가 없다."""
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid).id
        db.commit()
    산것 = client.get(f"/income?retreat_id={rid}").text
    assert "비우면 전액 회비, 0 을 적으면 후원금 처리됩니다" in 산것
    client.post(f"/income/deposits/{did}/cancel?retreat_id={rid}", data={})
    취소된것 = client.get(f"/income?retreat_id={rid}").text
    assert 'name="depositor"' in 취소된것 and "이름·금액 저장" in 취소된것,         "취소된 줄에 고치는 칸이 없다"
    assert "분류는 되살린 뒤에" in 취소된것


def test77_f07_열람_전용은_못_고친다(판):
    from fastapi.testclient import TestClient

    from app.main import app

    _, rid = 판
    make_user("가명열람2", "01099997777", role="viewer")
    보는이 = TestClient(app)
    login_as(보는이, "01099997777", name="가명열람2")
    with app_session() as db:
        did = 입금(db, rid).id
        db.commit()
    assert 보는이.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                     data={"depositor": "라마바", "amount": "1"}).status_code == 403


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


# ── ㅅ. 금액을 올릴 때의 안내 (2026-09-27 사람이 정함 · 봐둘것 BK-d ③) ──
#
# **막지 않고 알린다.** 회비는 비율이 아니라 액수라(7-6) 금액을 올려 고치면
# 회비 몫이 그대로 남고 나머지가 후원금이 되는데, 그때 아무 말이 없으면
# **확인한 줄의 분류가 조용히 바뀝니다**(「확인 필요」 칩에도 안 뜹니다).
#
# 막는 코드가 아니라 **말하는 코드**라 시험도 셋이 한 벌이다 —
# ① 말해야 할 때 말하는가 ② **말하면 안 될 때 안 하는가**(내림 · 회비 없음 ·
# 회비와 같은 금액) ③ 말하면서 **저장은 그대로 되는가**.


def _말(r) -> str:
    """flash 한 줄. **쿠키 이름은 앱에서 받는다** (2026-09-27 커밋 전 검토 [G]) —
    글자로 박으면 이름이 바뀔 때 `g01` 만 빨개지고 **「말하면 안 될 때」 쪽
    셋은 빈 글자를 받아 조용히 통과**한다(아무것도 안 보는 검사가 초록을 내는
    그 모양 · 11-3).
    """
    import urllib.parse

    from app.templating import FLASH_COOKIE
    return urllib.parse.unquote(r.cookies.get(FLASH_COOKIE) or "")


def test77_g01_금액을_올리면_한_줄_알리고_저장은_그대로_된다(판):
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid, amount=50000).id
        db.commit()
    client.post(f"/income/deposits/{did}?retreat_id={rid}",
                data={"kind": "회비", "fee_amount": "50000"})
    r = client.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                    data={"depositor": "가나다", "amount": "80000"}, follow_redirects=False)
    assert r.status_code == 303, "알리려고 막았다 — 막지 않기로 정했다"
    말 = _말(r)
    assert "50,000원은 그대로" in 말 and "30,000원이 후원금" in 말, 말
    with app_session() as db:
        d = db.get(models.IncomeDeposit, did)
        assert d.amount == 80000 and D.회비몫(d) == 50000, "알리느라 저장이 안 됐다"


def test77_g02_금액을_내리면_안_알린다(판):
    """내리면 회비를 따라 줄이므로 분류가 안 바뀐다 — 말할 것이 없다."""
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid, amount=50000).id
        db.commit()
    client.post(f"/income/deposits/{did}?retreat_id={rid}",
                data={"kind": "회비", "fee_amount": "50000"})
    r = client.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                    data={"depositor": "가나다", "amount": "30000"}, follow_redirects=False)
    assert "후원금이 됩니다" not in _말(r)


def test77_g03_회비가_없으면_안_알린다(판):
    """원래 전액 후원금이라 올려도 분류가 안 바뀐다."""
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid, amount=50000).id
        db.commit()
    r = client.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                    data={"depositor": "가나다", "amount": "80000"}, follow_redirects=False)
    assert "후원금이 됩니다" not in _말(r)


def test77_g04_바뀐_것이_없으면_아무_말도_안_한다(판):
    """같은 값을 다시 보내면 라우터가 되돌리고 「바뀐 것이 없습니다」 로 끝난다.

    **이 자리는 원래 경계(`금액 <= 회비`)를 재려던 것이었다** — 그런데 그
    경계는 **라우터로는 못 밟습니다**(2026-09-27 커밋 전 검토 [B]):
    `사람이정한다` 가 회비를 금액보다 크게 못 넣고 `고친다` 가 내릴 때 회비를
    깎으므로 늘 `회비 <= 전금액` 이고, 올리는 갈래에서는
    `회비 <= 전금액 < 금액` 이라 그 조건이 참이 될 수 없습니다. 그래서 그
    경계는 **`test77_g05` 가 단위로** 재고, 여기서는 **라우터에서 실제로
    밟히는 것**을 잽니다.

    고치기 전에는 이 시험이 30,000 을 두 번 보내고 있었습니다 — 둘째 요청이
    이 갈래(전==후)로 빠져 **단언이 늘 참**이었습니다. 이름과 주석은 다른
    것을 말하고 있었고, 그것이 10장의 「설명과 코드를 못 가린다」 의 사촌입니다.
    """
    client, rid = 판
    with app_session() as db:
        did = 입금(db, rid, amount=50000).id
        db.commit()
    client.post(f"/income/deposits/{did}?retreat_id={rid}",
                data={"kind": "회비", "fee_amount": "50000"})
    r = client.post(f"/income/deposits/{did}/fix?retreat_id={rid}",
                    data={"depositor": "가나다", "amount": "50000"}, follow_redirects=False)
    말 = _말(r)
    assert "바뀐 것이 없습니다" in 말, 말
    assert "후원금이 됩니다" not in 말
    with app_session() as db:
        assert D.분류(db.get(models.IncomeDeposit, did)) == D.회비


def test77_g05_판정은_domain_한_곳이다(판):
    """문장을 화면이 지으면 두 벌이 된다 — 문이 둘인 것도 여기서 잰다."""
    assert D.올려서_섞이나(전금액=50000, 금액=80000, 회비=50000)
    assert not D.올려서_섞이나(전금액=80000, 금액=50000, 회비=50000), "내림"
    assert not D.올려서_섞이나(전금액=50000, 금액=80000, 회비=None), "회비 없음"
    assert not D.올려서_섞이나(전금액=50000, 금액=80000, 회비=0), "회비 0 은 전액 후원금"
    # **이 줄이 그 경계를 재는 유일한 자리다** — 라우터로는 못 밟는다(`g04` 의 그 까닭)
    assert not D.올려서_섞이나(전금액=30000, 금액=50000, 회비=50000), "여전히 전액 회비"
    import pathlib
    루트 = pathlib.Path(__file__).resolve().parents[1]
    src = (루트 / "app" / "routers" / "income.py").read_text(encoding="utf-8")
    assert "후원금이 됩니다" not in src, "라우터가 같은 문장을 또 짓는다"
