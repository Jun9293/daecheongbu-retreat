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

# 겹침 열쇠의 칸막이 (U+001F · 단위 구분자). 사람이 적을 수 있는 글자가 아니라
# 시각·금액·잔액 어디에도 안 들어간다 — `열쇠` 를 보라
칸막이 = ""

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


def 열쇠(시각: str, 금액: int, 잔액: int | None) -> str:
    """겹침을 가르는 열쇠 (시각·금액·잔액) — **한 글자줄**이다.

    유니크 인덱스로 안 두는 것은 **잔액이 비는 줄**이 있어서다 — SQLite 의
    유니크는 NULL 끼리를 다른 값으로 봐서, 잔액 없는 같은 줄이 올릴 때마다
    쌓인다(비품 묶음에서 겪은 그 자리 · 4-18).

    **사이에 `칸막이`(U+001F)를 넣는다** — 그냥 이어붙이면 자릿수가 옮겨 가며
    서로 다른 줄이 같은 열쇠가 된다(금액 10000·잔액 1234567 과 금액 100001·잔액
    234567). 그러면 있는 줄이 안 담기고 「겹쳤다」 로 세어지는데 **화면에는 아무
    표시도 안 난다.** 눈에 안 보이는 글자라 이름을 붙여 둔다 — 2026-09-27 커밋 전
    검토가 이 자리를 「구분자가 없다」 로 읽었다(실제로는 있었다).

    **글자줄인 것은 칸에 얼려 두기 때문이다** — 2026-09-27 에 이름·금액을
    고칠 수 있게 되면서, 고친 금액이 열쇠를 움직이면 **같은 캡처를 다시 올릴
    때 건너뛰지 않게** 된다. 사람이 「취소의 뜻을 안 바꾼다」 로 정했으므로
    열쇠는 **읽은 때의 값**이고 `dup_key` 에 그대로 남는다.
    """
    return 칸막이.join((
        (시각 or "").strip(),
        str(int(금액)),
        "" if 잔액 is None else str(int(잔액)),
    ))


def 열쇠of(d: IncomeDeposit) -> str:
    """그 줄의 열쇠 — **얼려 둔 값이 있으면 그것**이다.

    옛 행(칸이 붙기 전에 선 줄)은 `dup_key` 가 비어 있어 그 자리에서 셈한다.
    그 줄만은 금액을 고치면 열쇠가 따라 움직인다 — 칸이 붙기 전에 선 줄에만
    남는 자국이고, NULL 로 붙이는 대가다(11-2 · 8장의 `scope_key` 와 같은 꼴).
    """
    return d.dup_key or 열쇠(d.deposited_text, d.amount, d.balance)


def 있는열쇠들(db: Session, *, retreat_id: int) -> set[str]:
    줄들 = db.scalars(
        select(IncomeDeposit).where(IncomeDeposit.retreat_id == retreat_id)
    ).all()
    return {열쇠of(d) for d in 줄들}


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
            dup_key=k,
        ))
        넣음 += 1
    return 넣음, 건너뜀


def 고친다(d: IncomeDeposit, *, 이름: str, 금액: int) -> str:
    """캡처가 잘못 읽은 **이름·금액**을 사람이 고친다 (7-6 · 2026-09-27 사람이 정함).

    **겹침 열쇠는 안 움직입니다** — `dup_key` 를 안 건드리므로 같은 캡처를 다시
    올려도 그대로 건너뜁니다. 취소의 뜻(「다시 올려도 안 되살아난다」)을 안
    바꾸면서, 이름이 잘못 읽혀 취소한 줄을 **고쳐서 되살릴 길**을 여는 것이
    이 함수가 있는 까닭입니다.

    **취소된 줄도 고칩니다** — 분류(`사람이정한다`)는 취소된 줄에서 막히지만
    이것은 「그때 무엇이 들어왔나」 를 바로잡는 자리라 성격이 다릅니다.

    **「추정」 은 안 건드립니다** — 이름을 고친 것이 「이 줄이 회비인지 후원금인지
    사람이 봤다」 는 뜻은 아닙니다.

    **돌려주는 것은 화면에 낼 한 줄입니다** — 금액을 올려 분류가 조용히 바뀌는
    자리에만 차 있고 그 밖에는 빈 글자입니다(`올려서_섞이나`).
    """
    이름 = (이름 or "").strip()
    if not 이름:
        raise ValueError("입금자 이름을 적어주세요.")
    if 금액 <= 0:
        raise ValueError("금액은 1원 이상이어야 합니다.")
    # **칸이 붙기 전에 선 줄은 여기서 함께 언다** — 그러지 않으면 그 줄만 고친
    # 금액을 따라 열쇠가 움직인다. 이것은 부팅이 값을 채우는 것이 아니라 **사람이
    # 그 줄을 고칠 때 같이 채우는 것**이라 11-2 가 막은 자리가 아니다
    # (2026-09-27 커밋 전 검토 [E])
    if not d.dup_key:
        d.dup_key = 열쇠(d.deposited_text, d.amount, d.balance)
    옛금액 = d.amount
    d.depositor = 이름[:100]
    d.amount = 금액
    # 금액을 줄이면 회비 몫이 그보다 클 수 있다. `회비몫` 이 화면에서는
    # 잘라 주지만 저장된 값도 맞춰 둔다 — 안 맞추면 되살린 뒤 그 줄을 열었을 때
    # 칸에 금액보다 큰 회비가 적혀 있다
    if d.fee_amount is not None and d.fee_amount > 금액:
        d.fee_amount = 금액
    # **올릴 때는 안 건드리고 대신 말한다** (2026-09-27 사람이 정함 · 봐둘것 BK-d ③) —
    # 회비는 비율이 아니라 액수라(7-6) 「5만원이 회비」 로 확인한 줄의 금액을
    # 8만원으로 바로잡으면 회비는 5만원 그대로이고 나머지가 후원금이 된다.
    # 막지 않는 것은 그 액수를 지키는 것이 맞을 수 있어서이고, 그때 **분류가
    # 조용히 바뀌지 않게** 한 줄을 돌려준다
    return 올려서_섞이나(전금액=옛금액, 금액=금액, 회비=d.fee_amount)


def 올려서_섞이나(*, 전금액: int, 금액: int, 회비: int | None) -> str:
    """금액을 **올려** 고쳐 남는 몫이 후원금이 되는가 — 그러면 그 한 줄이다.

    **막는 말이 아니라 알리는 말이다** (봐둘것 BK-d · 사람이 셋 중 ③ 을 골랐다).
    문이 둘이다 — **올릴 때만**(내리면 회비를 따라 줄이므로 분류가 안 바뀐다)
    그리고 **회비가 붙어 있을 때만**(없으면 원래 전액 후원금이라 말할 것이 없다).

    **「회비가 붙어 있다」 가 곧 「사람이 확인한 줄」 이다** — `fee_amount` 를
    채우는 곳은 `사람이정한다` 하나이고 그것이 `confirmed_at` 을 함께 찍는다.
    BK-d 가 걱정한 것이 「확인한 줄」 인데 그 축을 따로 볼 필요가 없는 까닭이
    이것이다 (2026-09-27 커밋 전 검토) — `confirmed_at` 검사를 또 더하지 않는다.

    **셋째 조건(`금액 <= 회비`)은 규칙이 아니라 직접 부를 때의 방어다** —
    앱에서는 못 밟는다(`사람이정한다` 가 회비를 금액보다 크게 못 넣고 `고친다`
    가 내릴 때 회비를 깎으므로 늘 `회비 <= 전금액` 이고, 올리는 갈래에서는
    `회비 <= 전금액 < 금액` 이다). 그래서 CLAUDE.md 는 문을 **둘**로 적는다.

    **문장이 여기 있는 까닭** — 화면이 저마다 지으면 두 벌이 되고 갈린 쪽을
    아무도 눈치채지 못한다(4-3 이 배지에서 정한 그 자리).
    """
    if 금액 <= 전금액 or not 회비 or 금액 <= 회비:
        return ""
    return (f"회비 {회비:,}원은 그대로라 남는 {금액 - 회비:,}원이 후원금이 됩니다"
            " — 회비 몫을 바꾸려면 그 줄의 분류를 다시 저장해 주세요.")


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
