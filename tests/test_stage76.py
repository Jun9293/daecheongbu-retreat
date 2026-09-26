"""재정 화면 점검 스크립트 (`docs/checks/fin.js`) — 2026-09-26 · 봐둘것 BJ-i.

예산 · 지출 화면은 **상세 패널이 없어** `drawer.js` 가 못 돕니다(그쪽은 맨 앞에서
`#drawer` 를 찾습니다). 그래서 `phone.js` 처럼 파일을 따로 뒀고, **이 파일이 그
스크립트를 재는 자리**입니다.

**여기서 재는 것은 낱말입니다.** 점검은 브라우저에서만 돌기 때문에, 실제로 심은
고장이 ✗ 로 나오는지는 브라우저에서 돌려 보고 결과를 `docs/review/최근.md` 에
적습니다 — `test_stage19.py` 가 `drawer.js` 에 대해 하는 것과 같은 자리입니다.

**셋을 봅니다** (11-3 의 그 셋) — ① 갈래마다 심을 고장이 있는가 ② 심은 고장이
낼 말을 점검이 실제로 내는가 ③ 그 스크립트가 **값을 안 저장하는가**(점검이
자국을 남기면 안 된다 — 10장).
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIN = ROOT / "docs" / "checks" / "fin.js"
BUDGET_JS = (ROOT / "app" / "static" / "js" / "budget.js").read_text(encoding="utf-8")
EXPEDIT_JS = (ROOT / "app" / "static" / "js" / "expedit.js").read_text(encoding="utf-8")
EXPPOP_JS = (ROOT / "app" / "static" / "js" / "exppop.js").read_text(encoding="utf-8")


def _코드() -> str:
    """주석을 걷어낸 점검 스크립트 — 글자를 찾는 시험의 그 함정 (10장)."""
    글 = FIN.read_text(encoding="utf-8")
    글 = re.sub(r"/\*[\s\S]*?\*/", "", 글)
    return re.sub(r"(?<!:)//[^\n]*", "", 글)


def _고장자리(코드: str) -> str:
    return 코드[코드.index("const 고장들"):코드.index("const 판정리")]


# ── ㄱ. 있는가 ────────────────────────────────────────────────────


def test76_a01_재정_점검_파일이_있고_두_화면을_가른다():
    코드 = _코드()
    assert "budtbl" in 코드 and "exptbl" in 코드, "두 화면 중 하나를 안 본다"
    # 재정 표가 없는 화면에서는 돌지 않고 그렇게 말한다 — 전부 초록이 나오고
    # 아무것도 안 잰 것이 되면 안 된다 (phone.js 가 폭을 전제로 둔 그 까닭)
    assert "치명" in 코드 and "재정 표가 없습니다" in FIN.read_text(encoding="utf-8")


def test76_a02_자가시험이_따로_돈다():
    코드 = _코드()
    assert "window.__자가시험" in 코드, "자가시험을 켜는 자리가 없다"
    # 평소 점검과 갈라야 평소가 안 느려진다
    assert "window.__자가시험 ? 자가시험() : 점검()" in 코드


# ── ㄴ. 셋 중 ① — 갈래마다 심을 고장이 있다 ──────────────────────


def test76_b01_갈래마다_심을_고장이_하나씩_있다():
    """갈래를 세어 두지 않는다 (10장) — **모든 갈래에 심을 것이 있는지**를 본다."""
    자리 = _고장자리(_코드())
    갈래 = re.findall(r"갈래:\s*'([^']+)'", 자리)
    심는다 = re.findall(r"심는다:", 자리)
    나와야 = re.findall(r"나와야:", 자리)
    assert len(갈래) >= 3, f"갈래가 너무 적다 — 무엇을 재고 있나: {갈래}"
    assert len(갈래) == len(심는다) == len(나와야), \
        f"갈래 {len(갈래)} · 심는다 {len(심는다)} · 나와야 {len(나와야)}"
    assert len(set(갈래)) == len(갈래), f"갈래 이름이 겹친다: {갈래}"


def test76_b02_두_화면_갈래가_모두_있다():
    """**한 화면 갈래만 있으면 다른 화면에서는 자가시험이 아무것도 안 심는다.**

    예산에만 심으면 지출에서 돌릴 때 전부 「못 심음」 이 되고, 그러면 그 화면은
    검사가 새는지 한 번도 안 재진다 (11-3 의 「세 화면 · 두 계정」 과 같은 까닭).
    """
    자리 = _고장자리(_코드())
    화면들 = re.findall(r"화면:\s*'([^']+)'", 자리)
    assert "예산" in 화면들 and "지출" in 화면들, f"한쪽 화면 갈래만 있다: {set(화면들)}"


# ── ㄷ. 셋 중 ② — 심은 고장이 낼 말을 점검이 실제로 낸다 ─────────


def test76_c01_나와야_하는_말이_점검에_실제로_있다():
    """그 말을 점검이 안 내면 자가시험은 **영원히 「놓침」** 이라 말한다 —
    심는 쪽이 아니라 재는 쪽이 틀린 것인데 구별이 안 된다."""
    코드 = _코드()
    자리 = _고장자리(코드)
    본체 = 코드[:코드.index("const 고장들")]
    없는것 = [말 for 말 in re.findall(r"나와야:\s*'([^']+)'", 자리) if 말 not in 본체]
    assert 없는것 == [], f"점검이 낼 리 없는 말을 기다린다: {없는것}"


def test76_c02_점검이_실제로_있는_선택자를_누른다():
    """화면이 안 쓰는 이름을 누르면 그 갈래는 늘 건너뜀이다 — 아무것도 안 잰다."""
    코드 = _코드()
    for 이름, 어디 in (("budedit", BUDGET_JS), ("budadd", BUDGET_JS),
                     ("budcancel", BUDGET_JS), ("expedit", EXPEDIT_JS),
                     ("expcancel", EXPEDIT_JS)):
        assert 이름 in 코드, f"점검이 {이름} 을 안 본다"
        assert 이름 in 어디, f"{이름} 이 화면 코드에 없다 — 점검이 없는 것을 누른다"
    for 선택자 in ("longcell", "payer acct", "rcptchip", "rcptadd", "acctcopy"):
        assert 선택자.replace(" ", ".") in 코드 or 선택자 in 코드, f"점검이 {선택자} 를 안 본다"
    # 팝업 부품이 실제로 그 이름을 쓴다
    for 선택자 in ("longcell", "rcptchip", "rcptadd", "acctcopy", "rcptmore", "rcptdel"):
        assert 선택자 in EXPPOP_JS, f"{선택자} 가 팝업 코드에 없다"


# ── ㄹ. 셋 중 ③ — 점검이 자국을 안 남긴다 ────────────────────────


def test76_d01_점검이_저장을_안_누른다():
    """**되돌릴 수 없는 자국을 남기는 누름을 하지 않는다** (10장 · 봐둘것 BI-j).

    저장은 활동 기록에 줄을 남기고 취소는 행을 아래로 내린다 — 점검 한 번이
    그 회차의 기록을 바꾼다. 끝에는 늘 「되돌리기」 로 편집을 끈다.
    """
    코드 = _코드()
    # **읽는 것과 누르는 것을 가른다** — 점검은 「영수증 없는 줄에 번호로 잇기가
    # 없다」 를 재려고 `.rlink` 를 **찾아만** 본다. 이름이 나오는 것을 통째로
    # 막으면 그 막는 쪽 항목을 못 쓴다: 막을 것은 **누름**이다
    누르는것 = [줄.strip() for 줄 in 코드.splitlines() if ".click()" in 줄]
    # **센 것이 0 이면 통과가 아니다** (11-3 의 셋째 축) — 누르는 자리를 한
    # 줄도 못 찾았으면 이 시험은 아무것도 안 보고 초록을 낸다
    assert 누르는것, "누르는 자리를 한 줄도 못 찾았다 — 이 시험이 아무것도 안 본다"
    # `budout`(예산 줄 취소)만 막고 지출 쪽의 같은 단추(`expout`)가 빠져 있었다
    # (2026-09-26 커밋 전 검토 [D]) — 한쪽만 막는 가드는 막는 것이 아니다
    for 금지 in ("budsave", "expsave", "budout", "expout", "rupload", "rlink",
                "rorigsave", "rcptdel", "rcptmore"):
        # 저장하는 이름은 아예 안 부른다 (읽을 일도 없다)
        if 금지 in ("budsave", "expsave", "budout", "expout", "rupload", "rorigsave"):
            assert 금지 not in 코드, f"점검이 {금지} 를 부른다 — 자국이 남는다"
        걸린것 = [표현 for 표현 in 누르는것 if 금지 in 표현]
        assert 걸린것 == [], f"점검이 {금지} 를 누른다 — 자국이 남는다: {걸린것}"
    assert "budcancel" in 코드 and "expcancel" in 코드, "편집을 끄는 자리가 없다"
    # 「막는 쪽」 을 재려면 그 이름을 **찾아는** 봐야 한다 — 그 자리가 실제로 있다
    assert ".rlink" in 코드, "「번호로 잇기가 없다」 를 재는 자리가 없다"


def test76_d02_판마다_자리를_고르고_시작한다():
    """앞 갈래가 편집을 켠 채 끝나면 다음 판이 그 자국 위에서 돈다 —
    **심지 않은 고장이 섞인다**(`phone.js` 가 겪은 그 자리)."""
    코드 = _코드()
    assert "const 판정리" in 코드, "판을 고르는 자리가 없다"
    자가 = 코드[코드.index("const 자가시험"):]
    assert 자가.count("판정리()") >= 3, "자가시험이 판을 안 고르고 심는다"


def test76_d03_안_심었을_때_초록인지도_같은_판에서_본다():
    """늘 빨간 검사는 아무것도 안 재는 검사와 같다 (11-3 의 둘째 축)."""
    assert "안 심으면 초록" in _코드()


def test76_d04_죽은_채로_통과를_안_낸다():
    """한복판에서 죽으면 그때까지 잰 것만 남아 「전부 통과」 로 보인다."""
    코드 = _코드()
    assert "완주" in 코드 and "지킨다" in 코드
    assert "통과: errors.length === 0 && 완주" in 코드


def test76_d05_빨강을_찍는_길과_세는_길이_하나다():
    """둘이면 손으로 맞추게 되고 실제로 어긋난 적이 있다 (`drawer.js` 의 그 자리)."""
    코드 = _코드()
    assert len(re.findall(r"results\.push\(\(ok \?", 코드)) == 1
    assert len(re.findall(r"errors\.push\(", 코드)) == 1
