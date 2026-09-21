"""톤 판 — 색온도 · 고정폭 · 팀색 tint · 모서리 (CLAUDE.md 4-0 · 4-13).

2026-09-21 에 사람이 정한 것 셋을 잰다.

1. **숫자를 줄 세우려고 고정폭 글꼴을 쓰지 않는다.** `--mono` 는 사라졌고
   그 자리는 `font-variant-numeric:tabular-nums` 다. 글자를 하나씩 읽는
   자리(서명키 칸 · 회의록의 파일 이름)만 `--code` 로 남는다.
2. **무채색을 차가운 쪽으로 옮긴다.** 4-0 의 원칙(순검정 안 씀 · 헤어라인 ·
   뜻 있는 색 셋)은 그대로고 「따뜻한 무채색」 → 「차가운 무채색」 이다.
3. **팀색이 면에도 온다 — 아주 옅게.** 바 · 점 · 부서 머리 줄 · 부서 칩.

**세는 것이 0 이면 실패다** (11-3) — 아무것도 안 보는 검사가 초록을 내는 것이
이 저장소가 여러 번 겪은 사고다. 그래서 「찾은 자리가 몇인가」 를 함께 잰다.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS_PATH = ROOT / "app" / "static" / "css" / "retreat.css"
CSS = CSS_PATH.read_text(encoding="utf-8")


def 미디어를_걷는다(글: str) -> str:
    """`@media {...}` 를 통째로 뺀 것 — **넓은 화면에서 서는 규칙만** 남는다.

    같은 셀렉터가 좁은 화면 규칙에도 있어서, 이름으로만 훑으면 넓은 화면의
    선을 지워도 그쪽이 대신 걸려 초록이 된다.
    """
    남은 = []
    i = 0
    while i < len(글):
        자리 = 글.find("@media", i)
        if 자리 < 0:
            남은.append(글[i:])
            break
        남은.append(글[i:자리])
        여는괄호 = 글.find("{", 자리)
        if 여는괄호 < 0:
            break
        깊이, j = 0, 여는괄호
        while j < len(글):
            if 글[j] == "{":
                깊이 += 1
            elif 글[j] == "}":
                깊이 -= 1
                if 깊이 == 0:
                    break
            j += 1
        i = j + 1
    return "".join(남은)


def 민낯(글: str) -> str:
    """주석을 걷어낸 것. **찾는 말이 설명글에 있으면 시험이 거짓말을 한다** (10장)."""
    return re.sub(r"/\*.*?\*/", "", 글, flags=re.S)


def 색들(글: str) -> list[str]:
    return [h.upper() for h in re.findall(r"#[0-9a-fA-F]{6}\b", 민낯(글))]


def 따뜻한가(h: str) -> bool:
    """R > B 면 따뜻하다. 무채색의 색온도를 재는 가장 단순한 잣대다."""
    return int(h[1:3], 16) > int(h[5:7], 16)


# ── 1. 고정폭 글꼴 ───────────────────────────────────────────────────


def test63_a01_mono_토큰이_없다():
    """`--mono` 를 참조하는 곳이 0 이어야 한다 (지시문 2c)."""
    본문 = 민낯(CSS)
    assert "--mono" not in 본문, "숫자를 줄 세우는 고정폭 토큰이 남아 있다"


def test63_a02_숫자는_tabular_nums_로_줄_선다():
    """고정폭을 걷은 자리가 **그냥 사라지면** 예산표의 자릿수가 어긋난다."""
    본문 = 민낯(CSS)
    쓴곳 = re.findall(r"font-variant-numeric:\s*tabular-nums", 본문)
    assert len(쓴곳) >= 60, f"tabular-nums 가 {len(쓴곳)} 자리뿐이다 — 걷어내기만 한 것이다"
    assert ".mono{font-variant-numeric:tabular-nums}" in 본문.replace(" ", ""), \
        "템플릿·JS 가 쓰는 .mono 가 숫자를 안 줄 세운다"


def test63_a03_글자를_읽는_자리만_고정폭이다():
    """**숫자 정렬과 다른 이유다** — 서명키 · 파일 이름은 한 글자씩 읽는다.

    자리를 세어 두지 않고 **이름으로** 적는다 (10장) — 늘어나면 여기에 이유와
    함께 더한다.
    """
    본문 = 민낯(CSS)
    assert "--code:ui-monospace" in 본문.replace(" ", ""), "글자를 읽는 자리의 토큰이 없다"
    쓴곳 = re.findall(r"([^{}\n]+)\{[^{}]*var\(--code\)", 본문)
    자리 = {" ".join(s.split()) for s in 쓴곳}
    허락 = {
        ".mt-from-note code": "회의록이 가리키는 파일 이름 — 글자를 하나씩 읽는다",
        ".keybox input": "서명키 칸 — 한 글자만 틀려도 못 쓴다",
    }
    샌것 = {s for s in 자리 if not any(s.endswith(k) for k in 허락)}
    assert not 샌것, f"글자를 읽는 자리가 아닌데 고정폭이다: {샌것}"
    assert 자리, "--code 를 쓰는 곳이 하나도 없다 — 토큰만 남았다"


# ── 2. 색온도 ────────────────────────────────────────────────────────


def test63_b01_무채색이_차갑다():
    """잉크 · 면 · 선이 **R > B 가 아니다.** 4-0 의 「차가운 무채색」."""
    뿌리 = re.search(r":root\{(.*?)\n\}", 민낯(CSS), re.S)
    assert 뿌리, ":root 를 못 찾았다"
    안 = 뿌리.group(1)
    for 이름 in ("--ink", "--ink-2", "--ink-3", "--side"):
        m = re.search(rf"{re.escape(이름)}:\s*(#[0-9A-Fa-f]{{6}})", 안)
        assert m, f"{이름} 이 없다"
        h = m.group(1).upper()
        assert not 따뜻한가(h), f"{이름}({h}) 이 아직 따뜻하다 — R > B"


def test63_b02_선도_차갑다():
    안 = 민낯(CSS)
    for 이름 in ("--rule", "--rule-2"):
        m = re.search(rf"{re.escape(이름)}:\s*rgba\((\d+),(\d+),(\d+)", 안)
        assert m, f"{이름} 이 rgba 가 아니다"
        r, _g, b = (int(x) for x in m.groups())
        assert r < b, f"{이름} 이 아직 따뜻하다 — R {r} ≥ B {b}"


def test63_b03_무채색에_따뜻한_것이_없다():
    """**뜻 있는 색(앰버 · 붉은색)은 따뜻해야 한다 — 그것이 뜻이다.**

    그래서 비율로 재면 안 된다. 처음에 그렇게 썼다가 21/38 이 나왔는데 그중
    열여덟이 상태 배지 · 경고 띠의 앰버 · 붉은색이었다 — 고쳐야 할 것과 그대로
    둘 것이 한 수에 섞였다. **채도가 아주 낮은 색만** 골라 거기에 따뜻한 것이
    없는지 본다. 화면 전체를 덮는 것은 그쪽이고, 4-0 이 옮긴 것도 그쪽이다.

    그리고 **색온도가 새어 들어온 입구는 하드코딩**이었다 — 옛 `--ink-3` 값이
    두 자리에 글자로 박혀 있어서 토큰만 고쳤을 때 그대로 따뜻하게 남았다.
    그래서 잣대를 「비율」 이 아니라 **「무채색이 `:root` 밖에 박혀 있지 않은가」**
    로 둔다. 뜻 있는 색은 이 잣대에 안 걸린다 — 채도가 높다.
    """
    본문 = 민낯(CSS)
    뿌리 = re.search(r":root\{.*?\n\}", 본문, re.S)
    assert 뿌리, ":root 를 못 찾았다"
    밖 = 본문[:뿌리.start()] + 본문[뿌리.end():]

    def 채도(h: str) -> int:
        v = [int(h[i:i + 2], 16) for i in (1, 3, 5)]
        return max(v) - min(v)

    # **`%23` 도 `#` 이다** — data-URI 안의 SVG 가 그 꼴로 색을 쓴다. `#` 만
    # 보던 시절에는 사이드바 캐럿의 옛 흐림값이 이 검사를 통째로 지나갔다
    전부 = sorted({("#" + m).upper()
                  for m in re.findall(r"(?:#|%23)([0-9a-fA-F]{6})\b", 밖)})
    assert len(전부) >= 5, f":root 밖에서 색을 {len(전부)}개만 읽었다 — 세는 자리가 틀렸다"
    # **잴 것이 없으면 통과가 아니다** (11-3) — 앞서는 채도 낮은 색이 둘뿐이라
    # 무엇을 박아도 초록이 나올 수 있었다
    # **흰색과 거의 흰색은 빼고 센다** — 그것들은 무엇을 박아도 통과하므로
    # 세어 봐야 「잴 것이 있다」 를 못 지킨다 (커밋 전 검토 [R7])
    판정할것 = [h for h in 전부 if 채도(h) <= 12
              and min(int(h[i:i + 2], 16) for i in (1, 3, 5)) < 235]
    assert len(판정할것) >= 1, "채도가 낮고 흰색이 아닌 색을 하나도 못 읽었다 — 잴 것이 없다"
    샌것 = [h for h in 판정할것 if 따뜻한가(h)]
    assert not 샌것, f"무채색이 :root 밖에 박혀 있다 — 토큰을 고쳐도 안 따라온다: {샌것}"


def test63_b04_대비는_그대로_지킨다():
    """9장 — 혼자 뜻을 지는 글자는 4.5:1 이상, `--ink-3` 은 그 아래에 남는다."""
    def 광도(h: str) -> float:
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def 대비(a: str, b: str) -> float:
        l1, l2 = sorted((광도(a), 광도(b)), reverse=True)
        return (l1 + 0.05) / (l2 + 0.05)

    안 = 민낯(CSS)
    값 = {이름: re.search(rf"{re.escape(이름)}:\s*(#[0-9A-Fa-f]{{6}})", 안).group(1)
         for 이름 in ("--ink", "--ink-2", "--ink-3", "--side")}
    assert 대비(값["--ink"], "#FFFFFF") >= 10
    assert 대비(값["--ink-2"], "#FFFFFF") >= 4.5
    assert 대비(값["--ink-2"], 값["--side"]) >= 4.5, "보조 글자가 면 위에서 기준을 못 넘는다"
    흐림 = 대비(값["--ink-3"], "#FFFFFF")
    assert 3.5 <= 흐림 < 4.5, f"흐림이 {흐림:.2f}:1 — 보조와 구별이 안 되거나 너무 옅다"


def test63_b05_본문은_흰_종이이고_구역은_선으로_나뉜다():
    """**본문 바탕을 흰색으로** (4-0 · 2026-09-21 에 사람이 정함).

    전에는 본문이 회색이고 그 위에 흰 면을 얹었다. 형제 저장소를 화면으로 열어 보니
    본문이 순백이고 구역을 **선으로만** 나눴고, 회색 위의 흰 카드는 카드마다
    테두리를 한 겹 더 요구해 화면을 칸으로 잘게 썰었다.

    그 회색 토큰은 **지웠다** — 본문에서 걷고 나니 부르는 자리가 없었다.
    사이드바·헤더의 면은 처음부터 `--side` 다.
    """
    본문 = 민낯(CSS)
    m = re.search(r"\.setting\{background:var\((--[\w-]+)\)", 본문)
    assert m, ".setting 의 바탕을 못 읽었다"
    assert m.group(1) == "--paper", f"본문 바탕이 {m.group(1)} 이다 — 흰 종이가 아니다"
    # **죽은 토큰을 남기지 않는다** — 부르는 자리가 없는 이름은 그것을 설명한
    # 글이 낡게 만든다(커밋 전 검토). 본문에서 걷은 그 회색 면이 그랬다
    # **이름 하나가 아니라 `:root` 가 정한 것을 전부** 본다 — 「--bg 가 남았나」 로
    # 적어 두면 메시지는 일반 규칙처럼 읽히는데 재는 것은 한 이름뿐이고, 실제로
    # `--paper-2` 가 그 틈으로 살아 있었다(다시 보기가 짚었다).
    뿌리 = re.search(r":root\{(.*?)\n\}", 본문, re.S)
    assert 뿌리, ":root 를 못 찾았다"
    # 부르는 자리는 CSS 만이 아니다 — 보드의 격자 폭은 파이썬이 인라인으로 적는다
    부르는데 = 본문 + ROOT.joinpath("app/domain/board.py").read_text(encoding="utf-8")
    죽은토큰 = [이름 for 이름 in re.findall(r"(--[\w-]+)\s*:", 뿌리.group(1))
              if f"var({이름})" not in 부르는데 and f"var({이름}," not in 부르는데]
    assert not 죽은토큰, f"부르는 자리가 없는 토큰이 남아 있다: {죽은토큰}"

    # 구역을 담던 상자들이 **네 면 테두리를 안 두르고**, 그러고도 **저마다
    # 선을 남긴다.** 합쳐서 세면 한 자리가 둘을 내는 바람에 다른 자리의 선을
    # 전부 지워도 통과한다(커밋 전 검토가 재어 짚었다) — **자리마다 잰다.**
    넓은화면 = 미디어를_걷는다(본문)
    for 이름 in ("fld", "kpi", "lcard", "ncard", "tblwrap"):
        m = re.search(rf"(?<![\w.-])\.{이름}\{{([^}}]*)\}}", 본문)
        assert m, f".{이름} 규칙을 못 찾았다"
        assert not re.search(r"(?<!-)border:\s*1px", m.group(1)), \
            f".{이름} 이 아직 네 면 테두리를 두른다 — 구역은 선으로만 나눈다"
        # **좁은 화면 규칙을 빼고 센다.** 같은 이름이 `@media` 안에도 있어서,
        # 넓은 화면의 선을 지워도 그쪽이 대신 걸려 초록이 됐다 — `.kpi+.kpi` 가
        # 실제로 그랬다(다시 보기가 고장을 심어 짚었다).
        선 = re.findall(
            rf"(?<![\w.-])\.{이름}(?![\w-])[^{{]*\{{[^}}]*border-(?:top|bottom|left):\s*1(?:\.5)?px",
            넓은화면)
        assert 선, f".{이름} 이 넓은 화면에서 구역을 가르는 선을 하나도 안 남겼다"
    # 구역 머리는 굵은 선으로 「여기부터 한 덩이」 를 말한다
    assert re.search(r"\.fld h3\{[^}]*border-bottom:\s*1\.5px", 본문), \
        "구역 머리 아래 굵은 선이 없다"


# ── 3. 팀색이 면에도 온다 ────────────────────────────────────────────


def test63_c01_바와_점이_팀색으로_채워진다():
    from app.domain import board

    for 상태, 비율 in (("대기", board.TINT_TODO), ("진행중", board.TINT_WIP)):
        bg, border = board.bar_style(상태, "#B44B42", kind="main", ghost=False)
        assert bg == board.tint("#B44B42", 비율), f"{상태} 바탕이 팀색에서 안 나온다"
        assert bg.startswith("rgb("), f"{상태} 바탕이 색이 아니다: {bg}"
        assert border == "#B44B42"
    # 아주 옅어야 한다 — 선택 테두리와 지연 배지를 묻지 않는다
    assert 0 < board.TINT_TODO < board.TINT_WIP <= 0.2


def test63_c02_못_읽는_팀색은_보드를_안_죽인다():
    from app.domain import board

    for 나쁜색 in ("", None, "빨강", "#12345"):
        bg, _ = board.bar_style("대기", 나쁜색, kind="main", ghost=False)
        assert bg.startswith("rgb("), f"{나쁜색!r} 에서 바탕이 깨졌다: {bg}"


def test63_c03_완료와_고스트는_팀색을_안_쓴다():
    """**완료를 눈에 띄게 하지 않는다** (4-3) — 시선은 미완료로 가야 한다."""
    from app.domain import board

    assert board.bar_style("완료", "#B44B42", kind="main", ghost=False) == board.BAR_DONE
    assert board.bar_style("대기", "#B44B42", kind="main", ghost=True)[0] == "none"


def test63_c04_부서_머리_줄과_칩이_팀색으로_채워진다():
    본문 = 민낯(CSS)
    assert "--team" in 본문, "보드 부서 머리 줄이 팀색을 안 받는다"
    # **`var()` 가 겹쳐 있다** — 물러설 값도 토큰이라 `[^)]*` 로는 못 읽는다
    섞은곳 = re.findall(r"color-mix\(in srgb,\s*var\((--team|--c)[^%]*?(\d+)%", 본문)
    assert len(섞은곳) >= 3, f"면을 팀색으로 섞는 자리가 {len(섞은곳)} 뿐이다"
    for _이름, 퍼센트 in 섞은곳:
        assert int(퍼센트) <= 14, f"팀색이 {퍼센트}% 로 너무 진하다 — 배지가 묻힌다"
    # **모르는 브라우저가 맨 바탕이 되지 않게** 앞줄이 있어야 한다 (color-mix 폴백)
    board_html = (ROOT / "app" / "templates" / "board.html").read_text(encoding="utf-8")
    assert "--team:{{ dept.color }}" in board_html


def test63_c06_팀색이_실제로_보인다():
    """**상한만 지키면 사람이 고쳐 달라고 한 그 상태로 조용히 돌아간다.**

    커밋 전 검토가 [R4] 로 짚었다 — `TINT_TODO` 를 0.001 로 낮춰도 그때까지의
    시험 넷이 전부 초록이었다. 사람이 규칙을 뒤집은 까닭이 「색이 아홉 가지나
    있는데 화면이 통째로 회색으로 읽혔다」 이므로, 상한을 값으로 지킨 것처럼
    **하한도 값으로** 지킨다.
    """
    from app.domain import board

    바탕 = [int(x) for x in re.findall(r"\d+", board.tint("못읽는색", board.TINT_WIP))]
    깔린것 = {}
    for 색 in ("#2F4858", "#B44B42", "#4A8A5C", "#7A5BA6"):
        rgb = [int(x) for x in re.findall(r"\d+", board.tint(색, board.TINT_WIP))]
        깔린것[색] = tuple(rgb)
        assert max(abs(a - b) for a, b in zip(rgb, 바탕)) >= 6, \
            f"{색} 을 깐 면이 종이색과 거의 같다 — 팀색이 사실상 사라졌다"
    # **서로 다른 부서가 서로 다른 면을 낸다** — 한 색으로 뭉뚱그리지 않는다
    assert len(set(깔린것.values())) == len(깔린것), "부서마다 면이 안 갈린다"


def test63_c05_가장_진한_tint_위에서도_보조_글자가_읽힌다():
    """**상한이 왜 그 값인지를 시험이 말한다.** 커밋 전 검토가 재어 짚었다 —
    가장 어두운 부서색을 15% 로 깔면 `--ink-2` 가 4.5:1 아래로 떨어진다.
    그래서 상한이 14% 이고, 그 경계를 글로 적는 대신 여기서 잰다 (9장).
    """
    from app.domain import board

    def 광도(h: str) -> float:
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def 대비(a: str, b: str) -> float:
        l1, l2 = sorted((광도(a), 광도(b)), reverse=True)
        return (l1 + 0.05) / (l2 + 0.05)

    안 = 민낯(CSS)
    잉크 = re.search(r"--ink:\s*(#[0-9A-Fa-f]{6})", 안).group(1)
    보조 = re.search(r"--ink-2:\s*(#[0-9A-Fa-f]{6})", 안).group(1)
    # **CSS 가 실제로 섞는 토큰에서 읽는다** — 다른 이름에서 읽으면 둘이 같은
    # 값일 때만 우연히 맞고, 한쪽을 고치면 조용히 옛 면을 잰다(커밋 전 검토)
    면 = re.search(r"--side:\s*(#[0-9A-Fa-f]{6})", 안).group(1)
    머리들 = {int(p) for p in
            re.findall(r"color-mix\(in srgb,\s*var\(--team[^%]*?(\d+)%", 안)}
    assert 머리들, "부서 머리 줄의 tint 비율을 CSS 에서 못 읽었다"
    머리비율 = max(머리들)
    칩들 = {int(p) for p in
           re.findall(r"color-mix\(in srgb,\s*var\(--c[^%]*?(\d+)%", 안)}
    assert 칩들, "부서 칩의 tint 비율을 CSS 에서 못 읽었다"
    칩비율 = max(칩들)
    # **섞는 바탕도 CSS 에서 읽는다** — 비율만 읽고 바탕을 박아 두면 CSS 쪽
    # 색을 바꿨을 때 조용히 옛 바탕을 잰다(다시 보기가 짚었다)
    칩바탕 = re.search(
        r"color-mix\(in srgb,\s*var\(--c[^%]*?\d+%,\s*(#[0-9A-Fa-f]{6})", 안).group(1)
    # 2장의 부서 아홉 색. **부서 색은 설정에서 사람이 넣는 값이라 더 어두운
    # 색은 이 시험 밖이다** — 14% 는 「지금 아홉 색에서」 안전한 값이다
    # (커밋 전 검토 [R5] 가 검정·파랑으로 재어 4.5 아래가 나오는 것을 보였다).
    # 다행히 tint 면 위에 보조색이 얹히는 자리는 아래 「머리 줄」 뿐이다
    부서색 = ["#2F4858", "#77848F", "#3B6EA5", "#B95A83", "#4A8A5C",
             "#B44B42", "#8A6A4F", "#7A5BA6", "#A98A1E"]

    def 깔면(색: str, 비율: float, 바탕: str) -> str:
        """`color-mix(in srgb, 색 N%, 바탕)` 과 같은 셈 — 화면이 하는 그것이다."""
        c = [int(색[i:i + 2], 16) for i in (1, 3, 5)]
        p = [int(바탕[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02X%02X%02X" % tuple(round(a * 비율 + b * (1 - 비율)) for a, b in zip(c, p))

    for 색 in 부서색:
        rgb = [int(x) for x in re.findall(r"\d+", board.tint(색, board.TINT_WIP))]
        바 = "#%02X%02X%02X" % tuple(rgb)
        assert 대비(잉크, 바) >= 7, f"{색} 바 위에서 본문이 {대비(잉크, 바):.2f}:1"
        assert 대비(보조, 바) >= 4.5, \
            f"{색} 바 위에서 보조 글자가 {대비(보조, 바):.2f}:1 — 9장의 4.5 아래다"
        # **부서 머리 줄은 면이 다르다**(사이드바 면 위) — 거기 얹히는 개수와
        # 캐럿이 9장의 3.5:1 아래로 내려갔던 자리다 (커밋 전 검토 [R3]).
        # **비율을 여기 박지 않고 CSS 에서 읽는다** — 박으면 CSS 를 올려도
        # 이 시험이 옛 값을 재서 조용히 지나간다(고장을 심어 확인)
        머리 = 깔면(색, 머리비율 / 100, 면)
        assert 대비(보조, 머리) >= 4.5, \
            f"{색} 머리 줄에서 보조 글자가 {대비(보조, 머리):.2f}:1"
        # **부서 칩은 흰 종이 위다** — 본문 바탕이 흰색이 되면서 칩이 섞는 바탕과
        # 실제 바탕이 같아졌다 (4-0 · 2026-09-21). 글자는 `--ink` 다
        칩 = 깔면(색, 칩비율 / 100, 칩바탕)
        assert 대비(잉크, 칩) >= 7, f"{색} 칩에서 본문이 {대비(잉크, 칩):.2f}:1"


# ── 4. 모서리 ────────────────────────────────────────────────────────


def test63_d01_모서리가_둘로_모였다():
    """18가지가 흩어져 한 화면에 6px 카드와 10px 카드가 함께 떴다 (4-0)."""
    본문 = 민낯(CSS)
    값 = [v.strip() for v in re.findall(r"border-radius:([^;}]*)", 본문)]
    assert 값, "border-radius 를 하나도 못 읽었다"
    # **한 값짜리만 보면 「6px 6px 0 0」 이 그대로 지나간다** — 모서리별 꼴도
    # 조각으로 갈라 본다 (커밋 전 검토가 짚은 자리)
    낱값 = {조각 for v in 값 for 조각 in v.split() if re.fullmatch(r"\d+px", 조각)}
    assert 낱값 <= {"999px"}, f"눈금 밖의 모서리가 남아 있다: {sorted(낱값)}"
    assert "--r:4px" in 본문.replace(" ", "") and "--r-lg:8px" in 본문.replace(" ", "")


def test63_d02_원과_알약은_눈금이_아니다():
    """50% 와 999px 은 크기가 아니라 **모양**이라 그대로 둔다."""
    본문 = 민낯(CSS)
    assert "border-radius:50%" in 본문.replace(" ", "")
    assert "border-radius:999px" in 본문.replace(" ", "")


# ── 5. 글자 크기 분포 ────────────────────────────────────────────────


def test63_e01_작은_글자에_몰려_있지_않다():
    """고치기 전에는 `--fz` 눈금을 쓴 선언 411 중 295(72%)가 12~14px 이었다.

    **크기를 세는 것이 아니라 단을 센다** — `--fz` 가 올라가면 같은 단이
    더 커지므로, 12~14px 에 해당하던 세 단(xs · sm · md)의 **비중**을 잰다.
    """
    본문 = 민낯(CSS)
    m = re.search(r"--fz:\s*(\d+)px", 본문)
    assert m and int(m.group(1)) >= 16, "기준 크기가 안 올라갔다"
    쓴것 = re.findall(r"font-size:\s*var\((--fz[\w-]*)\)", 본문)
    assert len(쓴것) >= 300, f"{len(쓴것)} 자리만 읽었다 — 세는 자리가 틀렸다"
    작은단 = [x for x in 쓴것 if x in ("--fz-xs", "--fz-sm")]
    # xs 13 · sm 14 만 14px 이하다 — md 는 15px 로 올라갔다
    assert len(작은단) / len(쓴것) < 0.45, \
        f"14px 이하가 아직 {len(작은단)}/{len(쓴것)} 이다"
