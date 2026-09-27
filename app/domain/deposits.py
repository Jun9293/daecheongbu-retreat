"""회비·후원금 입금 내역 (CLAUDE.md 7-6).

은행 앱의 입금 내역 캡처를 Claude 에게 보여 주고 거래 줄을 뽑아 온다.
**뽑아 온 것은 전부 후원금이고 「추정」 이다** — 이름만으로 회비인지 아닌지
가를 수 없기 때문이다. 총무가 화면에서 회비로 바꾸거나 일부만 나눈다.

**세는 곳은 여기 하나다.** 회비 몫과 후원금 몫을 화면에서 다시 빼면
필터 칩과 합계가 갈린다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import llm
from app.models import IncomeDeposit

# 화면에 쓰는 이름 — 여기 한 곳이다
회비 = "회비"
후원금 = "후원금"
섞임 = "회비+후원금"

SYSTEM = (
    "너는 한국 은행 앱의 입금 내역 캡처를 읽어 거래 줄을 뽑는 도구다. "
    "보이는 것만 적고 짐작해서 채우지 않는다."
)

PROMPT = """이 캡처에 보이는 거래 줄을 JSON 으로만 답해라.

{"줄": [{"이름": "홍길동", "금액": 50000, "시각": "09.15 14:22", "잔액": 1234000}]}

규칙
- **입금(+) 줄만** 담는다. 출금·이체 나감(금액 앞에 `-` 가 붙은 줄)은 **빼라**.
- 금액과 잔액은 쉼표를 뗀 정수로. 잔액이 안 보이면 null.
- 시각은 화면에 적힌 글자 그대로. 없으면 "".
- 이름은 입금자 표기 그대로. 흐려서 못 읽겠으면 그 줄을 빼라.
- 한 줄도 못 읽으면 {"줄": []} 로 답해라. **지어내지 마라.**
- JSON 말고 아무것도 쓰지 마라."""


def 회비몫(d: IncomeDeposit) -> int:
    return max(0, min(d.amount, d.fee_amount or 0))


def 후원금몫(d: IncomeDeposit) -> int:
    """**빼서 센다** — 두 칸으로 두면 합이 금액과 어긋나는 줄이 생긴다."""
    return max(0, d.amount - 회비몫(d))


def 분류(d: IncomeDeposit) -> str:
    if 회비몫(d) and 후원금몫(d):
        return 섞임
    return 회비 if 회비몫(d) else 후원금


def 추정인가(d: IncomeDeposit) -> bool:
    """사람이 그 줄을 보고 저장하기 전까지는 추정이다."""
    return d.confirmed_at is None


def 열쇠(시각: str, 금액: int, 잔액: int | None) -> tuple[str, int, int | None]:
    """겹침을 가르는 열쇠 (시각·금액·잔액).

    유니크 인덱스로 안 두는 것은 **잔액이 비는 줄**이 있어서다 — SQLite 의
    유니크는 NULL 끼리를 다른 값으로 봐서, 잔액 없는 같은 줄이 올릴 때마다
    쌓인다(비품 묶음에서 겪은 그 자리 · 4-18).
    """
    return ((시각 or "").strip(), int(금액), None if 잔액 is None else int(잔액))


def 있는열쇠들(db: Session, *, retreat_id: int) -> set[tuple[str, int, int | None]]:
    줄들 = db.scalars(
        select(IncomeDeposit).where(IncomeDeposit.retreat_id == retreat_id)
    ).all()
    return {열쇠(d.deposited_text, d.amount, d.balance) for d in 줄들}


def 목록(db: Session, *, retreat_id: int) -> list[IncomeDeposit]:
    return list(
        db.scalars(
            select(IncomeDeposit)
            .where(IncomeDeposit.retreat_id == retreat_id)
            .order_by(IncomeDeposit.id)
        ).all()
    )


def 걸러낸다(줄들: list[IncomeDeposit], 필터: str) -> list[IncomeDeposit]:
    """필터 칩 — 조건은 여기 하나다 (4-15 가 홈과 지출에서 정한 그 규칙)."""
    산것 = [d for d in 줄들 if d.canceled_at is None]
    if 필터 == "fee":
        return [d for d in 산것 if 회비몫(d)]
    if 필터 == "donation":
        return [d for d in 산것 if 후원금몫(d)]
    if 필터 == "check":
        return [d for d in 산것 if 추정인가(d)]
    return 줄들


def 합(줄들: list[IncomeDeposit]) -> dict:
    산것 = [d for d in 줄들 if d.canceled_at is None]
    return {
        "건수": len(산것),
        "금액": sum(d.amount for d in 산것),
        "회비": sum(회비몫(d) for d in 산것),
        "후원금": sum(후원금몫(d) for d in 산것),
        "확인필요": sum(1 for d in 산것 if 추정인가(d)),
    }


class 못읽음(RuntimeError):
    """대답은 왔는데 우리가 못 읽었다 — 키가 없는 것과 **다른 사정**이다."""


def 줄로바꾼다(raw: dict) -> list[dict]:
    """모델의 답에서 쓸 줄만 고른다. **출금과 꼴이 틀린 줄은 뺀다.**"""
    담긴 = raw.get("줄")
    if not isinstance(담긴, list):
        raise 못읽음("JSON 에 「줄」 목록이 없습니다")
    고른 = []
    for 하나 in 담긴:
        if not isinstance(하나, dict):
            continue
        이름 = str(하나.get("이름") or "").strip()
        try:
            금액 = int(하나.get("금액"))
        except (TypeError, ValueError):
            continue
        잔액 = 하나.get("잔액")
        try:
            잔액 = None if 잔액 is None else int(잔액)
        except (TypeError, ValueError):
            잔액 = None
        # 출금 줄은 안 담는다 — 0 원도 담을 것이 없다
        if not 이름 or 금액 <= 0:
            continue
        고른.append({"이름": 이름[:100], "금액": 금액,
                     "시각": str(하나.get("시각") or "").strip()[:50], "잔액": 잔액})
    return 고른


def 읽는다(data: bytes, media_type: str, *, 부르기=None):
    """캡처 한 장을 읽어 (줄들, 대답) 을 돌려준다.

    키가 없으면 `llm.LlmUnavailable` 이 그대로 올라간다 — 화면이 `상태().말`
    을 그대로 보인다. 대답은 왔는데 JSON 이 아니면 `못읽음` 이다. **둘을
    한 말로 뭉치지 않는다**: 할 일이 다르다(키를 넣는 것과 다시 찍는 것).
    """
    부르기 = 부르기 or llm.ask
    대답 = 부르기(SYSTEM, PROMPT, images=[(media_type, data)])
    raw = llm.json_만(대답.text)
    if not raw:
        raise 못읽음("답이 JSON 이 아닙니다")
    return 줄로바꾼다(raw), 대답


def 담는다(db: Session, *, retreat_id: int, 줄들: list[dict]) -> tuple[int, int]:
    """읽은 줄을 넣는다 → (넣은 수, 겹쳐서 건너뛴 수).

    같은 캡처를 두 번 올려도 안 쌓인다. commit 은 **부르는 쪽이** 한다.
    """
    있는 = 있는열쇠들(db, retreat_id=retreat_id)
    넣음 = 건너뜀 = 0
    for 하나 in 줄들:
        k = 열쇠(하나["시각"], 하나["금액"], 하나["잔액"])
        if k in 있는:
            건너뜀 += 1
            continue
        있는.add(k)
        db.add(IncomeDeposit(
            retreat_id=retreat_id,
            depositor=하나["이름"],
            amount=하나["금액"],
            deposited_text=하나["시각"],
            balance=하나["잔액"],
        ))
        넣음 += 1
    return 넣음, 건너뜀


def 사람이정한다(d: IncomeDeposit, *, 회비금액: int | None) -> None:
    """사람이 그 줄을 보고 저장한다 — **추정이 풀린다.**

    회비 금액은 0 부터 그 줄의 금액까지다. 비우면 전부 후원금이다.
    """
    if 회비금액 is None:
        d.fee_amount = None
    else:
        if 회비금액 < 0 or 회비금액 > d.amount:
            raise ValueError(f"회비 금액은 0 부터 {d.amount:,}원 사이여야 합니다.")
        d.fee_amount = 회비금액
    d.confirmed_at = dt.datetime.now()
