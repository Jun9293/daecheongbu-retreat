"""Claude API 로 나가는 **유일한 문** (회의록 5단계).

회의록 제안이 낱말 겹침에서 문장 읽기로 넘어가면서 생겼다. 부르는 곳이
둘이 되면 키를 읽는 방법·모델 이름·요금 계산이 갈리고, **갈린 쪽을 아무도
눈치채지 못한다** — 이 프로젝트가 여섯 번 고쳐 온 그 모양이다.

## 키는 저장소 밖에 둔다

공개 저장소다 (11-2). 키가 한 번 올라가면 지우고 커밋해도 **히스토리에
남는다.** 그래서 두 곳에서만 읽는다.

    1) 환경변수  DCB_ANTHROPIC_KEY
    2) 파일       data/anthropic_key.txt      ← `.gitignore` 에 걸려 있다

**키가 없어도 앱은 뜬다.** VAPID 키가 없을 때 푸시만 꺼진 채로 뜨는 것과
같은 규칙이다 (4-11) — 키 하나가 없다고 서버가 죽으면 안 된다. 대신
`상태()` 가 "왜 안 되는지" 를 한국어로 돌려주고, 화면이 그것을 그대로
사람에게 보여준다. **조용히 안 되는 것이 가장 나쁘다.**

## 요금은 여기 한 곳에서 센다

회의 하나에 얼마가 드는지 사람이 알아야 한다 — 회의록을 저장할 때마다
자동으로 부르기 때문이다 (5단계). 토큰 수와 단가를 곱하는 곳이 흩어지면
화면에 뜨는 값과 실제가 갈린다.

**단가는 바뀐다.** 그래서 숫자를 코드에 박되 **한 곳에** 두고, 환경변수로
덮을 수 있게 한다. 바뀐 것을 모르고 쓰면 "회의당 30원" 이 몇 배가 돼도
화면은 30원이라고 말한다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from app import config

# ── 키 ───────────────────────────────────────────────────────────────
KEY_ENV = "DCB_ANTHROPIC_KEY"
KEY_PATH: Path = config.DATA_DIR / "anthropic_key.txt"

# ── 모델과 요금 ──────────────────────────────────────────────────────
#
# **Sonnet 을 기본으로 둔다.** 회의록을 저장할 때마다 자동으로 부르고
# (5단계) 회차마다 50건쯤 되므로, 값이 성능만큼 중요하다. 이번에 넘어야 할
# 벽은 "낱말은 겹쳤는데 그 얘기를 한 적이 없다" 를 알아보는 것이고
# (제안-성적표), 그건 Sonnet 이 한다.
#
# 더 어려운 것을 시키고 싶으면 `DCB_LLM_MODEL` 로 바꾼다. 요금도 함께
# 바꿔야 한다 — 안 바꾸면 화면의 값만 틀린다.
MODEL = os.environ.get("DCB_LLM_MODEL", "claude-sonnet-5")
API_URL = os.environ.get("DCB_ANTHROPIC_URL", "https://api.anthropic.com/v1/messages")
API_VERSION = "2023-06-01"

# 100만 토큰당 달러. **요금표는 바뀐다** — 바뀌면 여기와 문서를 함께 고친다.
PRICE_IN = float(os.environ.get("DCB_LLM_PRICE_IN", "3.0"))
PRICE_OUT = float(os.environ.get("DCB_LLM_PRICE_OUT", "15.0"))
# 화면에 원으로 보여주기 위한 환율. 정확할 필요는 없고 자릿수만 맞으면 된다.
USD_KRW = float(os.environ.get("DCB_USD_KRW", "1400"))

TIMEOUT = float(os.environ.get("DCB_LLM_TIMEOUT", "120"))


class LlmUnavailable(RuntimeError):
    """키가 없거나 부를 수 없다. **화면이 이 말을 그대로 보여준다.**"""


@dataclass
class 키상태:
    ok: bool
    출처: str          # '환경변수' | '파일' | '없음'
    말: str            # 사람이 읽는 한 줄


def read_key() -> str | None:
    """키. 환경변수가 먼저고 없으면 파일.

    **빈 파일을 키로 쓰지 않는다.** 쓰다 만 파일이 남았을 때 빈 문자열로
    부르면 401 이 나는데, 화면에는 "분석에 실패했습니다" 만 뜨고 왜인지는
    안 나온다 (`secret_key.txt` 에서 같은 것을 겪었다 — config).
    """
    v = (os.environ.get(KEY_ENV) or "").strip()
    if v:
        return v
    if KEY_PATH.exists():
        try:
            v = KEY_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return v or None
    return None


def 상태() -> 키상태:
    """지금 부를 수 있는가. **화면이 이것을 그대로 말한다.**"""
    if (os.environ.get(KEY_ENV) or "").strip():
        return 키상태(True, "환경변수", f"{KEY_ENV} 로 연결돼 있습니다.")
    if read_key():
        return 키상태(True, "파일", f"{KEY_PATH.name} 로 연결돼 있습니다.")
    return 키상태(
        False, "없음",
        # **화면이 "낱말로 골랐다" 는 말을 이미 한다.** 여기서 또 하면 같은
        # 말이 두 번 뜬다 — 왜 그렇게 됐는지와 어떻게 고치는지만 적는다
        "아직 연결되지 않았습니다 —"
        " 넣는 방법은 docs/배포-안내.md 14장에 있습니다.",
    )


# ── 부르기 ───────────────────────────────────────────────────────────
@dataclass
class 대답:
    text: str
    in_tokens: int
    out_tokens: int
    model: str

    @property
    def 달러(self) -> float:
        return (self.in_tokens * PRICE_IN + self.out_tokens * PRICE_OUT) / 1_000_000

    @property
    def 원(self) -> float:
        return self.달러 * USD_KRW


def ask(system: str, user: str, *, max_tokens: int = 4000,
        model: str | None = None) -> 대답:
    """한 번 부른다. **키가 없으면 부르지 않고 왜인지 말한다.**"""
    key = read_key()
    if not key:
        raise LlmUnavailable(상태().말)
    body = {
        "model": model or MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    try:
        r = httpx.post(
            API_URL,
            headers={
                "x-api-key": key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            json=body,
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:                               # noqa: BLE001
        raise LlmUnavailable(f"부르지 못했습니다 — {exc.__class__.__name__}") from None
    if r.status_code != 200:
        # **본문을 그대로 붙이지 않는다.** 오류 본문에 키가 되비쳐 오는 일이
        # 있고, 이 말은 화면에 뜬다. 상태 코드와 종류까지만 옮긴다.
        종류 = ""
        try:
            종류 = (r.json().get("error") or {}).get("type") or ""
        except Exception:                                        # noqa: BLE001
            pass
        raise LlmUnavailable(f"응답이 {r.status_code} 입니다"
                             + (f" ({종류})" if 종류 else ""))
    data = r.json()
    조각 = [c.get("text", "") for c in data.get("content", []) if c.get("type") == "text"]
    사용 = data.get("usage") or {}
    return 대답(
        text="".join(조각),
        in_tokens=int(사용.get("input_tokens") or 0),
        out_tokens=int(사용.get("output_tokens") or 0),
        model=data.get("model") or (model or MODEL),
    )


def json_만(text: str) -> dict:
    """대답에서 JSON 만 꺼낸다.

    **앞뒤에 말이 붙어 와도 죽지 않는다.** `json.loads` 가 바로 안 되면
    첫 `{` 부터 마지막 `}` 까지를 다시 시도한다. 그래도 안 되면 빈 것을
    돌려준다 — 여기서 예외를 던지면 화면이 통째로 빈다 (4-10 조건 8).
    """
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    try:
        return json.loads(text)
    except Exception:                                            # noqa: BLE001
        pass
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        try:
            return json.loads(text[i:j + 1])
        except Exception:                                        # noqa: BLE001
            pass
    return {}
