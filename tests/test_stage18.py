"""기다리지 말고 보고 가기 (+ 못 잡는 모양 세기).

점검이 **세 판 연속 흔들렸고 셋 다 같은 모양**이었다 — 기다리는 시간을
어림으로 박았다. 화면이 아니라 검사가 흔들리면 그 결과로는 아무것도
못 정한다.

**이 파일은 낱말을 잰다.** 점검 스크립트는 브라우저에서만 돌기 때문에,
여기서는 **그것이 어떤 모양으로 적혀 있는지**를 본다 — 실제로 흔들리지
않는지는 두 계정 × 세 화면으로 돌려 봤고 결과는 `docs/review/최근.md` 에
있다.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
점검 = ROOT / "docs" / "checks" / "drawer.js"
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _코드() -> str:
    """주석을 걷어낸 점검 스크립트 — 글자를 찾는 시험의 그 함정 (10장)."""
    글 = 점검.read_text(encoding="utf-8")
    글 = re.sub(r"/\*[\s\S]*?\*/", "", 글)
    return re.sub(r"(?<!:)//[^\n]*", "", 글)


# ════════════════════════════════════════════════════════════════════
# 1. 기다리지 말고 본다
# ════════════════════════════════════════════════════════════════════


def test18_w01_어림으로_기다리는_자리가_손에_꼽힌다():
    """전에는 서른여덟이었다. 남는 것은 **기다릴 상태가 없는 자리**뿐이고
    그 줄에 이유가 적혀 있어야 한다.

    **낱말만 잰다** — 실제로 안 흔들리는지는 두 계정 × 세 화면으로
    돌려 봤다(최근.md).
    """
    남은것 = [줄.strip() for 줄 in _코드().splitlines() if "await sleep(" in 줄]
    # 폴링 간격(25) · check 의 기본 대기 · 일부러 느린 드래그 · 한 틱(0)
    허용 = ("sleep(25)", "sleep(opts.wait || 420)", "sleep(opts.뜸)", "sleep(0)")
    나쁜것 = [줄 for 줄 in 남은것 if not any(x in 줄 for x in 허용)]
    assert 나쁜것 == [], f"어림으로 기다리는 자리가 남았다: {나쁜것}"

    # ③ **이유가 실제로 적혀 있는지도 잰다.** 독스트링이 「그 줄에 이유가
    # 적혀 있어야 한다」 고 약속해 놓고 허용 목록만 보면, 이유 없는 줄이
    # 목록에 들기만 하면 통과한다 (검토가 짚었다)
    원문 = 점검.read_text(encoding="utf-8").splitlines()
    이유없음 = []
    for i, 줄 in enumerate(원문):
        if "await sleep(" not in 줄:
            continue
        # 그 대기를 담고 있는 선언까지 거슬러 올라가, **그 선언에 주석이
        # 붙어 있는지**를 본다. 「앞 N 줄」 로 세면 함수가 한 줄만 길어져도
        # 이유가 사라진 것처럼 빨개진다 — 자리를 세는 것과 같은 실수다
        머리 = next((j for j in range(i, -1, -1)
                    if re.match(r"\s*(const|function)\s", 원문[j])), 0)
        앞 = "\n".join(원문[max(0, 머리 - 6):i + 1])
        if not re.search(r"/\*|^\s*\*|//", 앞, re.M):
            이유없음.append(f"{i + 1}줄: {줄.strip()}")
    assert 이유없음 == [], f"이유가 안 적힌 대기가 있다: {이유없음}"


def test18_w02_상태를_보고_가는_자리가_실제로_있다():
    """③ 검사가 볼 것을 보고 있나 — 「기다림을 없앴다」 고 적어 두고
    아무 데서도 안 보면 그 말이 거짓이다."""
    코드 = _코드()
    assert 코드.count("await 될때까지(") + 코드.count("await 잠깐본다(") >= 10
    assert 코드.count("until:") >= 10


def test18_w03_못_쟀음이_실패와_따로_나온다():
    """검사가 흔들린 것과 화면이 고장 난 것을 가른다. 상한에 걸린 항목이
    ✗ 로 새면 **없는 고장**을 보고하게 된다."""
    코드 = _코드()
    # 상한에 걸리면 못쟀음 에 담는다
    자리 = 코드[코드.index("const 될때까지"):][:700]
    assert "못쟀음.push" in 자리
    # **화면에서도 글자가 다르다** — ✓/✗ 가 아니라 `?` 다
    assert re.search(r"results\.push\(`\?\s*\$\{label\}[^`]*못 쟀음", 코드)
    # 돌려준 값에도 실패와 **따로** 실린다
    assert re.search(r"return \{화면:[^}]*실패: errors[^}]*못쟀음", 코드)
    # 요약 줄도 콘솔 표에 찍히기 전에 붙는다 (안 그러면 콘솔만 보는
    # 사람에게는 못 쟀음이 없는 것과 같다)
    assert 코드.index("못 쟀음 ${못쟀음.length}개") < 코드.index("console.table")


def test18_w04_안_되는_것이_답인_자리는_못_쟀음이_아니다():
    """「닫혀야 하는데 안 닫힌다」 는 화면의 고장이라 ✗ 로 세야 한다 —
    그 자리는 상한까지 보고 그대로 돌려주는 쪽을 쓴다."""
    코드 = _코드()
    자리 = 코드[코드.index("const 잠깐본다"):][:400]
    assert "못쟀음" not in 자리, "안 되는 것이 답인 자리가 못 쟀음으로 샌다"
    assert "return ok" in 자리


def test18_w05_열렸다는_다_그려진_것이다():
    """`openDrawer` 는 `open` 을 먼저 붙이고 **그 다음에** 서버에
    물어본다 — 「open 이 붙었나」 로만 보면 머리와 권한 칩이 아직 옛
    것이라, 관리자로 돌면서 「권한과 어긋남」 이 났다(실제로 그랬다)."""
    코드 = _코드()
    자리 = 코드[코드.index("const 열렸다"):][:300]
    assert "statchip" in 자리 and "불러오는 중" in 자리
    앱 = (ROOT / "app" / "static" / "js" / "drawer.js").read_text(encoding="utf-8")
    at = 앱.index("dw.classList.add('open')")
    assert "await fetch" in 앱[at:at + 500], "앱이 먼저 열고 나중에 불러오는 그 모양이 맞다"


def test18_w06_머리말이_세_판을_말한다():
    """규칙만 적어 두면 다음 사람이 또 시간을 박는다."""
    머리 = 점검.read_text(encoding="utf-8")
    머리 = 머리[: 머리.index("(async () => {")]
    assert "세 판 연속" in 머리
    assert "시간을 줄이거나 타이머를 대체하지 마세요" in 머리
    assert "못 쟀음" in 머리


# ════════════════════════════════════════════════════════════════════
# 2. 죽은 단추를 세지 않는다
# ════════════════════════════════════════════════════════════════════


def test18_d01_죽었는지_보는_곳이_하나다():
    """없는 것 · 안 그려진 것 · 죽어 있는 것 셋을 한 자리에서 본다 —
    자리마다 따로 보면 다음에 죽는 단추가 생길 때 한쪽만 고쳐진다."""
    코드 = _코드()
    assert "const 살아있나 = el =>" in 코드
    자리 = 코드[코드.index("const 살아있나"):][:200]
    assert "shown(el)" in 자리 and "!el.disabled" in 자리
    # 요소를 겨냥한 클릭은 전부 그 문을 지난다
    assert 코드.count("await 누른다(") >= 12


def test18_d02_죽은_요소를_주면_건너뜀으로_센다():
    """막는 쪽. `statchip` 은 고칠 수 없는 계정에서도 지워지지 않고
    `disabled` 로 남아, 눌러도 아무 이벤트가 안 나서 **✓ 가 그냥
    붙고 있었다** (지난 판이 하나 잡았다).

    **낱말만 잰다** — 실제 동작은 두 계정으로 돌려 확인했다. 관리자는
    2·2·4 · 부서 리더는 15·15·16 이 건너뜀으로 잡혔고, 그 수와 어느
    항목이었는지는 `docs/review/최근.md` 3장에 있다."""
    코드 = _코드()
    자리 = 코드[코드.index("const 누른다"):][:400]
    assert "살아있나(el)" in 자리
    assert "건너뜀" in 자리 or "건너뜀" in _코드()[_코드().index("const 누른다"):][:600]


def test18_d03_앱이_죽여_두는_것을_다_안다():
    """이 점검이 도는 세 화면의 코드에서 `disabled` 를 실제로 붙이는
    곳을 **훑어서** 본다. 새로 죽는 단추가 생기면 빨개져 점검의
    `살아있나` 가 그것도 보는지 함께 확인하게 한다.

    **파일 이름을 손으로 적어 두지 않는다** (10장 「자리를 세어 두지
    않습니다」 의 파일판 — 검토가 짚었다). 전에는 여섯을 적어 두고
    `if not p.exists(): continue` 로 넘겼는데, **board.html·
    calendar.html 이 빠져 있었고** 경로가 바뀌면 아무것도 안 보면서
    초록이었다.
    """
    파일들 = []
    for 무늬 in ("app/static/js/drawer.js", "app/static/js/board.js",
                "app/static/js/calendar.js", "app/static/js/tasks.js",
                "app/templates/board.html", "app/templates/calendar.html",
                "app/templates/tasks.html", "app/templates/partials/drawer*.html"):
        파일들 += sorted(ROOT.glob(무늬))
    # ③ **본 것이 0 이면 실패다** — 경로가 바뀌면 조용히 초록이 된다
    assert len(파일들) >= 7, f"훑을 파일을 못 찾았다 — 경로가 바뀌었나: {파일들}"

    자리 = []
    for p in 파일들:
        rel = p.relative_to(ROOT).as_posix()
        for 번호, 줄 in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "disabled" in 줄 and not 줄.strip().startswith(("*", "//", "#", "{#")):
                자리.append(f"{rel}:{번호}")
    # 지금 둘뿐이다 — 권한 칩(statchip)과 Phase 2 의 하단 단추.
    # **바닥도 둔다**: 0 이 되면 훑는 방법이 망가진 것이지 좋아진 것이 아니다
    assert 2 <= len(자리) <= 2, f"죽여 두는 자리가 달라졌다 — 점검도 함께 보라: {자리}"


def test18_d04_상한을_항목마다_늘리는_손잡이가_없다():
    """「못 쟀음」 이 새는 자리가 되지 않게 (검토가 물은 그것).

    항목마다 상한을 줄 수 있으면 느릴 때 그것을 늘려서 넘어가게 되고,
    그러면 이 판이 없애려던 **어림으로 기다리기**가 이름만 바꿔
    돌아온다. `check` 의 상한은 `상한기본` 하나다.
    """
    코드 = _코드()
    assert "const 상한기본 =" in 코드
    자리 = 코드[코드.index("const check = async"):]
    자리 = 자리[:자리.index("const 살아있나")]
    assert "상한기본" in 자리
    옵션 = ("opts." + "상한")            # 10장 — 금지하는 말을 자기가 담지 않는다
    assert 옵션 not in 코드, "항목마다 상한을 주는 길이 다시 생겼다"


def test18_d05_못_쟀어도_주변은_잰다():
    """상한에 걸렸다고 곧바로 빠져나가면, **클릭이 드로어를 닫아 버린
    진짜 회귀가 ✗ 가 아니라 「못 쟀음」 으로** 나온다 — 기다리던 것이
    안 나타난 이유가 바로 그 회귀인데도 (검토가 짚었다).

    그래서 `check` 는 상한에 걸려도 스냅샷을 마저 재고, **주변이
    무너졌으면 ✗** · 멀쩡하면 「못 쟀음」 이다.
    """
    코드 = _코드()
    본체 = 코드[코드.index("const check = async"):]
    본체 = 본체[:본체.index("const 살아있나")]
    # 상한에 걸린 자리에서 곧바로 빠져나가지 않는다
    앞 = 본체[:본체.index("const after = snapshot()")]
    assert "return;" not in 앞, "못 쟀을 때 주변을 안 재고 빠져나간다"
    # 주변이 무너지면 ✗ 이고, 그때는 못쟀음 에 담지 않는다
    assert "적는다" in 코드, "될때까지 가 기록을 미룰 수 있어야 두 번 안 센다"
    assert 본체.index("errors.push") < 본체.index("못쟀음.push"), \
        "✗ 판정이 못 쟀음보다 먼저여야 한다"


# ════════════════════════════════════════════════════════════════════
# 3. 못 잡는 모양 — 넓힐지 숫자로 정한다
# ════════════════════════════════════════════════════════════════════


def test18_c01_자리는_한글_수_뒤에서만_본다():
    """`8자리`·`12자리` 는 자릿수이고 `세 자리` 는 자리 수다.
    숫자 쪽은 재 보니 **전부** 자릿수였고 한글 쪽은 **전부** 진짜였다."""
    cc = _load("check_counts")
    assert cc.센말.search("팀 색이 오는 세 자리")
    for 글 in ("키의 지문 8자리", "md5 앞 12자리", "11자리 숫자일 때만",
               "`/static/js/drawer.<8자리>.js`"):
        assert not cc.센말.search(글), f"자릿수를 자리로 본다: {글}"


def test18_c02_안_넓힌_이유가_숫자로_적혀_있다():
    """「지금 그런 자리는 없다」 로 적지 않는다 — **재서** 적는다.

    **잰 값을 시험에 박지 않는다** (11-3). 그 수는 문서가 말할 값이고
    실제로 이 판 안에서도 움직였다 — 박아 두면 다음 사람이 다시 잴
    때마다 시험이 막는다. 대신 셋을 본다: **수를 적었는가 · 언제 잰
    값인지 · 어떤 그물로 잰 값인지.**

    셋째가 이 판에서 늘었다. 처음에는 수만 적어서 **검토가 그 값을
    재현하지 못했고**, 알고 보니 넘김·날짜 예외를 안 쓴 그물의 값이었다.
    수만 있고 그물이 없으면 다시 잴 수가 없다.
    """
    cc = _load("check_counts")
    머리 = cc.__doc__
    자리 = 머리[머리.index("`벌`·`가지`"):][:900]
    assert re.search(r"\d{4}-\d{2}-\d{2}", 자리), "언제 잰 값인지가 없다"
    # 어떤 그물로 쟀는지 — 이 파일의 그 셋을 그대로 쓴다고 적혀 있어야
    for 이름 in ("볼파일", "글줄", "문단"):
        assert 이름 in 자리, f"어떤 그물로 잰 값인지가 없다: {이름}"
    표 = [줄 for 줄 in 자리.splitlines() if 줄.startswith("|") and "한글 수" in 줄]
    assert 표, "센 값이 표에 없다"
    for 줄 in 표:
        assert re.search(r"\|\s*\*{0,2}\d+\*{0,2}\s*\|", 줄), f"수가 없다: {줄}"
    문서 = (ROOT / "docs" / "봐둘것.md").read_text(encoding="utf-8")
    # **닫힌 항목도 찾는다.** 머리가 `## ~~AG-b · …~~ — 처리함` 으로
    # 바뀌므로 글자로 견주면 **닫는 순간 시험이 빨개진다** — 그건
    # 「숫자가 사라졌다」 가 아니라 「항목이 닫혔다」 인데 구별이 안 된다
    머리 = re.search(r"^#+ .*AG-b.*$", 문서, re.M)
    assert 머리, "AG-b 항목이 없어졌다"
    자리 = 문서[머리.start():][:1600]
    # 여기서도 **잰 값을 박지 않는다** — 표에 수가 있고 언제 잰
    # 값인지가 적혀 있는지만 본다
    assert re.search(r"\d{4}-\d{2}-\d{2}", 자리), "언제 잰 값인지가 없다"
    표 = [줄 for 줄 in 자리.splitlines() if "벌" in 줄 and "|" in 줄]
    assert 표 and re.search(r"\|\s*\d+\s*\|", 표[0]), f"센 값이 표에 없다: {표[:1]}"


def test18_c03_지금_저장소에는_0곳이다():
    """소스를 읽지 않고 **실제로 돌린다.**"""
    r = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"),
                        str(SCRIPTS / "check_counts.py")],
                       cwd=ROOT, capture_output=True)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-1200:]
