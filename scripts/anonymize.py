"""저장소에 들어가는 실명·연락처를 가명으로 바꾼다.

**왜 두는가** — 이 저장소를 언젠가 공개할 수 있게 열어 두기 위해서다.
봉사자와 교역자의 실명은 본인 동의 없이 공개될 성질이 아니고, 커밋 기록에
한 번 들어가면 나중에 지우려면 기록을 통째로 다시 써야 한다.

**무엇을 지키는가**

- **글자 수와 `M` 접미사를 그대로 둔다.** 화면 폭·정렬이 그대로 시험되고,
  `이름` / `이름M` 처럼 짝으로 갈린 표기를 맞추는 `normalize_names.py` 의
  시험도 그대로 성립한다 (5-3)
- **사람 이름이 아닌 것은 건드리지 않는다** — `총무M`(부서), `담당M`(역할),
  `전체`·`봉사자`·`총무팀`·`헤브론`·`코람데오`, 파트 이름(`행정`·`재정` 등)
- **한 글자 이름도 한 글자로 바꾼다.** 두 글자로 바꾸면 그 이름이 든 칸의
  줄바꿈이 달라진다

**어떻게 안전하게 바꾸는가** — 짧은 이름을 그냥 바꾸면 그 글자가 든 낱말까지
망가진다. 실제로 두 글자 이름 하나를 문자열로 바꿨더니 그 글자가 든 낱말이 함께 깨졌다.
그래서 **앞뒤가 한글·영문·숫자가 아닐 때만** 바꾼다. 바꾼 뒤에는 테스트
전체를 돌려 확인한다.

**대응표(`MAP_PATH`)는 저장소에 올리지 않는다.** 실명과 가명을
나란히 적어 둔 것만으로 원래 이름이 드러나기 때문이다.

    .venv\\Scripts\\python.exe scripts/anonymize.py          # 무엇이 바뀔지만 보여준다
    .venv\\Scripts\\python.exe scripts/anonymize.py --apply
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 표는 `data/` 에 두고 gitignore 한다 — 실데이터를 저장소 밖에 두는 것과 같다.
MAP_PATH = ROOT / "data" / "anonymize-map.json"


def load_map() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(이름 쌍, 번호 쌍). **긴 이름부터** 돌려준다 —
    성을 붙인 표기를 이름만 적은 표기보다 먼저 만나야 함께 바뀐다."""
    if not MAP_PATH.exists():
        raise SystemExit(
            f"대응표가 없습니다: {MAP_PATH}\n"
            "  이 파일은 실명이 들어 있어 저장소에 올리지 않습니다.\n"
            "  아래 모양으로 만들어 주세요:\n"
            '    {"names": [["실명", "가명"], ...],\n'
            '     "phones": [["01000000000", "01011112222"]]}'
        )
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    names: list[tuple[str, str]] = []
    임자: dict[str, str] = {}          # 표기 -> 가명
    for 줄 in data.get("names", []):
        # **한 줄 = 한 사람.** 새 모양은 표기를 여럿 둔다 —
        #   {"가명": "가명이름", "표기": ["성이 붙은 표기", "이름만 적은 표기"]}
        # 성이 붙은 표기를 같은 사람 아래 둘 수 있고, 한 사람이
        # 두 줄이 되지 않는다. **옛 모양 `[실명, 가명]` 도 그대로
        # 읽는다** — 표기가 하나뿐인 사람은 옮길 이유가 없다.
        if isinstance(줄, dict):
            가명 = 줄["가명"]
            표기들 = 줄["표기"]
        else:
            표기들, 가명 = [줄[0]], 줄[1]
        for 표기 in 표기들:
            # **표기마다 가명을 따로 둘 수 있다** — `["홍◯◯", "남◯◯"]`.
            # 성이 붙은 표기는 세 글자이므로 세 글자 가명이어야
            # 한다 (11-2 의 "글자 수를 지킨다"). 그렇다고 사람을
            # 두 줄로 나누면 한 줄 = 한 사람이 깨진다.
            if isinstance(표기, (list, tuple)):
                표기, 이표기의가명 = 표기[0], 표기[1]
            else:
                이표기의가명 = 가명
            # **한 표기가 두 사람에게 있으면 거절한다.** 그냥 두면
            # 뒤엣것이 이기면서 **두 사람이 조용히 한 사람이 되고** 
            # 아무 오류도 나지 않는다. 2026-09-04 에 이름 하나가
            # 성이 다른 **두 사람**을 가리키고 있었다.
            if 표기 in 임자 and 임자[표기] != 이표기의가명:
                raise SystemExit(
                    f"대응표에서 한 표기가 두 사람에게 있습니다: "
                    f"{표기[0]}◯… → {임자[표기]} / {이표기의가명}. "
                    "한 줄 = 한 사람입니다. 표기를 한쪽으로 모으거나 "
                    "성을 붙여 갈라 주세요.")
            임자[표기] = 이표기의가명
            names.append((표기, 이표기의가명))
    # **긴 표기부터 바꾼다.** 이름만 적은 표기를 먼저 바꾸면 성이 붙은
    # 표기가 `성 + 가명` 이 되어 **두 사람이 다시 섞인다.**
    names.sort(key=lambda pair: -len(pair[0]))
    return names, [(a, b) for a, b in data.get("phones", [])]


# ── 물어보는 창구 ────────────────────────────────────────────────
#
# **부르는 쪽이 대응표의 구조를 몰라야 한다.** 원본 모양(dict 인지
# 두 칸짜리 목록인지)을 그대로 돌려주면, 구조가 바뀔 때 부르는 쪽이
# 깨진다 — 2026-09-04 에 한 줄에 표기를 여럿 두는 모양으로 바꾸자
# `test_x_21` 이 `p[0]` 에서 깨졌다. 그래서 **물음 단위로만** 낸다.


def 표기들() -> list[str]:
    """찾아야 할 표기 전부 (이름 + 번호). **긴 것부터.**"""
    names, phones = load_map()
    return [a for a, _ in names] + [a for a, _ in phones]


def 가명(표기: str) -> str | None:
    """그 표기가 무엇으로 바뀌는가. 모르는 표기면 None."""
    names, phones = load_map()
    return dict(names + phones).get(표기)


def 가명수() -> int:
    """**서로 다른 가명의 수.** 사람 수가 아니다 —
    한 사람이 표기마다 다른 가명을 가질 수 있다
    (`["홍◯◯", "남◯◯"]` 처럼 성이 붙은 표기는 세 글자 가명).

    전에는 이 함수가 **「사람 수」** 를 센다고 적혀 있었는데, 표기마다
    가명을 두게 되면서 그 이름이 **거짓이 됐다.** 세는 것이
    바뀌었으면 이름도 바뀌어야 한다.
    """
    names, _ = load_map()
    return len({b for _, b in names})


def 표기수() -> int:
    """이름 표기 수."""
    names, _ = load_map()
    return len(names)


def 표기여럿인줄이있나() -> bool:
    """**새 모양(한 줄에 표기 여럿)이 읽히는가.**

    수를 견주지 않는다 — `표기수() > 가명수()` 는 *표기 둘이 가명
    하나를 나눠 쓰는* 줄에서만 참이라, 표기마다 가명을 둔 줄로
    옮기면 **구조는 멀쩡한데 거짓이 된다.** 모양을 직접 본다.
    """
    # **읽는 곳은 하나다.** 전에는 여기서 직접 파싱했는데, 파일 안이라
    # "읽는 곳은 하나" 는 지켜졌지만 **구조를 아는 곳이 둘**이 됐다.
    # 대응표가 없을 때의 안내도 `load_map()` 것만 나와야 한다.
    names, _ = load_map()
    임자: dict[str, int] = {}
    for _표기, 가명 in names:
        임자[가명] = 임자.get(가명, 0) + 1
    # 한 가명을 표기 둘이 나눠 쓰거나, 성이 붙은 표기가 따로 가명을
    # 가진 줄이 있으면 새 모양이 읽힌 것이다
    return any(n > 1 for n in 임자.values()) or _성붙은표기가있나(names)


def _성붙은표기가있나(names) -> bool:
    """세 글자 표기가 두 글자 표기를 뒤에 품고 있으면 성이 붙은 것."""
    짧은것 = {t for t, _ in names if len(t) == 2}
    return any(len(t) == 3 and t[1:] in 짧은것 for t, _ in names)


# 사람 이름처럼 생겼지만 아닌 것. 절대 바꾸지 않는다.
# **KEEP 은 「절대 바꾸지 않는다」 라서 잘못 들어간 것이 가장 조용하다.**
# 실명이 하나 섞이면 영영 익명화되지 않고 `check_names` 도 안 본다.
# 그래서 **무엇인지 한 줄씩** 적는다 — 다음에 훑을 때 사람이 갈라 본다.
# `tests/test_anonymize_map.py` 가 대응표와 겹치면 빨개진다.
#
# **여기 넣을 것은 「부서·파트·팀 이름」 뿐이다.** 역할·호칭처럼
# 그냥 사람 이름이 아닌 말은 `check_names.py` 의 `_이름아님` 이다 —
# 결과가 다르다: 여기 넣으면 **익명화에서도 영영 제외**되고, 저기는
# 그 검사에서만 안 본다. **어디에 적는가의 정본은 `_이름아님` 옆에
# 있다** (check_names.py).
KEEP = {
    # 부서 (2장의 부서표)
    "총무팀", "헤브론", "코람데오", "새친구팀", "선교사회", "스케치", "개기자",
    "재정",
    # 총무팀 파트 (5-3)
    "행정", "비품", "음식", "교역자", "현장관리",
    # 사람 묶음을 가리키는 말 (부서표 밖)
    "봉사자", "봉사팀",
    # 사람이 아니라 묶음을 가리키는 말
    "전체", "총무M", "담당M",
    # 성가대 한 팀의 이름 (사용자 확인). **2장 부서표에는 없다** —
    # 아홉 부서와 다른 갈래라 그렇다
    "셀라",
}

# 문서의 산문에는 **입력할 수 없는 모양**으로 둔다 — 예시 번호를 그대로
# 입력해 계정이 하나 더 생긴 적이 있다 (4-12).
DOC_PHONE = "010-XXXX-XXXX"

# **글자에 붙어 있으면 이름이 아니다.** 앞뒤가 한글·영문·숫자면 건너뛴다 —
# 그래야 `진행`·`필요한`·`중요한` 을 망가뜨리지 않으면서, 줄 처음과 끝에
# 선 이름도 잡는다. 구분자 목록을 적는 방식은 줄 끝을 놓쳤다.
WORDISH = r"[가-힣A-Za-z0-9]"


def targets() -> list[pathlib.Path]:
    # `-c core.quotepath=false` 가 없으면 한글 파일명이 `\354\227...` 로 나온다
    out = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    ).stdout.split("\n")
    skip = (".png", ".svg", ".ico", ".woff", ".woff2", ".xlsx", ".db")
    return [
        ROOT / name for name in out
        if name and not name.endswith(skip)
        and not name.endswith("scripts/anonymize.py")
    ]


def swap(text: str, *, doc: bool = False, names=None, phones=None) -> tuple[str, int]:
    """바꾼 글과 바꾼 횟수. **기록을 다시 쓸 때도 이 함수를 쓴다** —
    두 벌로 만들면 작업 트리와 기록이 다르게 바뀐다."""
    if names is None or phones is None:
        names, phones = load_map()
    changed = 0

    for real, fake in phones:
        replacement = DOC_PHONE if doc else fake
        if real in text:
            changed += text.count(real)
            text = text.replace(real, replacement)

    for real, fake in names:
        # `M` 접미사는 이름의 일부로 함께 넘어간다 (이름M → 가명M)
        #
        # **`M` 이 붙었으면 뒤가 한글이어도 바꾼다** — `◯◯M으로`,
        # `◯◯M이` 처럼 조사가 붙는다. 2026-09-04 에 이 틈으로
        # 이름 하나가 공개 커밋에 남았다.
        #
        # **이건 느슨하게 하는 것이 아니라 좁게 더하는 것이다.**
        # `필요한`·`진행`·`중요한` 은 `M` 이 없으므로 영향이 0이고,
        # 앞의 lookbehind 는 그대로라 낱말 안에 든 것은 여전히
        # 안 바뀐다. 늘어난 자리는 "이름 + M + 한글" 하나뿐이고,
        # 그건 5-3 이 정한 담당자 표기다.
        pattern = re.compile(
            f"(?<!{WORDISH})({re.escape(real)})"
            f"(?:(M)|()(?!{WORDISH}))")

        def hit(m: re.Match) -> str:
            nonlocal changed
            if m.group(0) in KEEP:
                return m.group(0)
            changed += 1
            return fake + (m.group(2) or "")

        # 앞뒤로 겹치는 자리가 있어 두 번 훑는다
        for _ in range(2):
            text = pattern.sub(hit, text)
    return text, changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 고친다")
    args = ap.parse_args()

    names, phones = load_map()
    total, touched = 0, []
    for path in targets():
        try:
            before = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        # 문서(.md)는 산문이라 번호를 입력 불가능한 모양으로 둔다
        after, n = swap(before, doc=path.suffix == ".md",
                        names=names, phones=phones)
        if n and after != before:
            total += n
            touched.append((path.relative_to(ROOT).as_posix(), n))
            if args.apply:
                path.write_text(after, encoding="utf-8")

    for name, n in sorted(touched, key=lambda x: -x[1]):
        print(f"{n:5d}  {name}")
    print()
    print(f"{len(touched)}개 파일 · {total}곳")
    if not args.apply:
        print("아직 바꾸지 않았습니다 — 실제로 하려면 --apply 를 붙이세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
