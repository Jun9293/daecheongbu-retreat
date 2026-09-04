# -*- coding: utf-8 -*-
"""표본 네 회의를 **다시 내서** 채점표를 만든다 (회의록 7단계).

낱말 겹침의 성적은 사람이 이미 채웠다 — 21개 중 14개
(`docs/review/제안-성적표.md`). 문장으로 읽는 판이 나아졌는지 말하려면
**같은 네 회의**로 다시 내서 견줘야 한다. 다른 회의로 채우면 두 숫자가
무엇을 견준 것인지 알 수 없어진다.

    .venv\\Scripts\\python.exe scripts/suggest_sample.py ^
        --retreat "2026 여름수련회 Belong"

**채점은 사람이 한다.** 이 스크립트는 낸 것과 근거를 표로 적어 둘 뿐이다.

## 운영 DB 를 건드리지 않는다

읽기만 한다 — 제안을 저장하지도, 회의록을 고치지도 않는다. 그래도 다른
DB 로 돌리고 싶으면 `DCB_DATABASE_URL` 을 주면 된다.

## 비율로 견준다

제안 수가 달라진다. 낱말 겹침은 21개를 냈는데 문장으로 읽으면 더 낼 수도
덜 낼 수도 있다. 그래서 **맞은 개수가 아니라 비율**로 견주고,
**"마땅히 나왔어야 하는데 안 나온 것"** 칸을 함께 둔다 — 그 칸이 없으면
**적게 내는 쪽으로 점수를 올릴 수 있다.**
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                   # noqa: E402

from app.db import SessionLocal, init_db                        # noqa: E402
from app.domain import llm as llm_mod                           # noqa: E402
from app.domain import suggest as S                             # noqa: E402
from app.models import Meeting, Retreat                         # noqa: E402

# **표본을 바꾸지 않는다.** 바꾸면 지난 판과 견줄 수 없다 (성적표의 '표본').
표본 = ["26.03.29 (1차)", "26.05.24", "26.07.05", "26.08.09"]

_리뷰 = pathlib.Path(__file__).resolve().parent.parent / "docs" / "review"
나갈곳 = _리뷰 / "제안-2판.md"
낱말나갈곳 = _리뷰 / "제안-1판.md"

# **1판의 성적은 고정된 사실이다** — 2026-09-03 에 사람이 채점했다
# (`docs/review/제안-성적표.md`). 다시 계산하지 않는다.
일판 = {"논의": (8, 13), "새 업무": (6, 8)}
일판합계 = (14, 21)


def 회차찾기(db, 이름: str) -> Retreat:
    """**이름으로 정확히 찾는다.** 비슷한 것을 골라 쓰지 않는다 —
    엉뚱한 회차로 표본을 내면 채점이 통째로 무의미하다 (5-5 와 같은 규칙)."""
    r = db.scalars(select(Retreat).where(Retreat.name == 이름)).first()
    if r is None:
        있는것 = [x.name for x in db.scalars(select(Retreat).order_by(Retreat.id))]
        print(f"'{이름}' 회차가 없습니다. 있는 회차:")
        for n in 있는것:
            print("  -", n)
        raise SystemExit(1)
    return r


def 한줄(x) -> str:
    if x.kind == "decision":
        return (f"| 결정사항 | {x.text} | `{(x.quote or '').strip()}` | | |")
    if x.kind == "discussion":
        return (f"| 논의 | 「{x.run_title}」 (run {x.run_id}) | {x.why} | | |")
    if x.kind == "new":
        곁 = " · ".join(filter(None, [
            f"상위: {x.parent_title}" if x.parent_title else "",
            x.department or ""]))
        return (f"| 새 업무 | {x.title or x.text}{(' — ' + 곁) if 곁 else ''}"
                f" | {x.why} | | |")
    return f"| {x.kind} | {x.text} | {x.why} | | |"


def 센다(제안들) -> int:
    """**'더있음' 은 제안이 아니다.**

    "이름이 겹치는 업무가 7건 더 있습니다" 는 안내 줄이다. 이것까지 세면
    낸 개수가 부풀어, 성적표와 견주는 검사가 **틀린 채로 통과한다** —
    실제로 20개인데 21개로 세어 그냥 지나갔다.
    """
    return sum(1 for x in 제안들 if x.kind != "더있음")


def 제안줄인가(줄: str) -> bool:
    칸 = 줄.split("|")
    return len(칸) == 7 and 칸[1].strip() in ("결정사항", "논의", "새 업무")


def 표요약(글: str) -> tuple[int, int]:
    """이미 있는 파일이 무엇을 담고 있나 — 무엇을 덮게 되는지 먼저 말한다."""
    줄들 = 글.splitlines()
    return (sum(1 for x in 줄들 if x.startswith("## 26.")),
            sum(1 for x in 줄들 if 제안줄인가(x)))


def 채운곳(글: str) -> list[str]:
    """**사람이 채운 자리.** 하나라도 있으면 `--replace` 로도 덮지 않는다.

    27개를 채우는 데 사람이 눈으로 회의록을 다시 읽는다. 그것이 한 번의
    실행으로 사라지면 되돌릴 방법이 없다 — 판정은 DB 에도 없고 이 파일이
    유일한 자리다.
    """
    X이유칸 = ("`다른업무`", "`할일아님`", "`중복`", "`기타`")
    찾음: list[str] = []
    for i, 줄 in enumerate(글.splitlines(), 1):
        칸 = 줄.split("|")
        if 제안줄인가(줄):
            if 칸[4].strip():
                찾음.append(f"{i}줄 · 판정 '{칸[4].strip()}'")
            elif 칸[5].strip():
                찾음.append(f"{i}줄 · X 이유 '{칸[5].strip()}'")
        elif "안 나온 것이 있나요?" in 줄 and 줄.split("→")[-1].strip():
            찾음.append(f"{i}줄 · 놓친 것 '{줄.split('→')[-1].strip()}'")
        # **칸 수를 세어 표를 가른다.** 마크다운 한 줄은 양 끝에도 칸이
        # 생기므로 `| a | b |` 는 4개, `| a | b | c |` 는 5개다. 처음에
        # 3열 표를 4로 세어 「놓친 것」 이 채워진 것을 놓쳤다
        elif len(칸) == 5 and 칸[1].strip().startswith("26."):
            if 칸[2].strip() or 칸[3].strip():
                찾음.append(f"{i}줄 · 놓친 것 표 ({칸[1].strip()})")
        elif len(칸) == 4 and 칸[1].strip() in X이유칸 and 칸[2].strip():
            찾음.append(f"{i}줄 · X 이유 표 ({칸[1].strip()})")
    return 찾음


def 막는다(out: pathlib.Path, replace: bool) -> None:
    """**이미 있는 것을 조용히 덮지 않는다** — `import_programs.py` 와 같은
    규칙이다 (5-5). 없는 규칙을 만드는 것이 아니라 여기만 안 걸려 있었다.

    키 검사보다 **먼저** 부른다. 못 쓸 것을 알면서 돈을 들여 부를 이유가 없다.
    """
    if not out.exists():
        return
    글 = out.read_text(encoding="utf-8")
    채운 = 채운곳(글)
    if 채운:
        print()
        print(f"{out} 에 **사람이 채운 것이 있습니다 - {len(채운)}곳.**")
        for 자리 in 채운[:8]:
            print("   ", 자리)
        if len(채운) > 8:
            print(f"    … 외 {len(채운) - 8}곳")
        print("`--replace` 로도 덮지 않습니다. `--out` 으로 다른 파일에 내보내세요.")
        print("아무것도 쓰지 않았습니다.")
        raise SystemExit(4)
    if not replace:
        회의, 제안 = 표요약(글)
        print()
        print(f"{out} 이(가) 이미 있습니다 - 회의 {회의}건 · 제안 {제안}개를 덮게 됩니다.")
        print("덮으려면 `--replace` 를 주세요. 아무것도 쓰지 않았습니다.")
        raise SystemExit(5)


def 다채운뒤(묶음) -> list[str]:
    """**종류별로 견준다.** 2판에 `결정사항` 이 새로 생겨서 합계끼리 견주면
    같은 것을 센 수가 아니다 — 그리고 결정사항은 회의록 줄을 그대로 인용하는
    것이라 잘 맞을 수밖에 없어서, 섞으면 비율을 끌어올린다.
    """
    셈: dict[str, int] = {}
    for _, r in 묶음:
        for x in r.제안들:
            이름 = {"decision": "결정사항", "discussion": "논의",
                   "new": "새 업무"}.get(x.kind, x.kind)
            셈[이름] = 셈.get(이름, 0) + 1
    합 = sum(셈.values())

    def 칸(이름: str) -> str:
        맞, 전 = 일판.get(이름, (0, 0))
        # **반올림이다.** 8/13 = 61.5 를 버리면 61 이 되는데 문서는 62 다
        왼 = f"{맞}/{전} ({round(맞 * 100 / 전)}%)" if 전 else "(1판에 없던 종류)"
        return f"| {이름} | {왼} | / {셈.get(이름, 0)} |"

    맞, 전 = 일판합계
    return [
        "## 다 채운 뒤",
        "",
        "**종류별로 견줍니다.** 2판에 `결정사항` 이 새로 생겨서 합계끼리 견주면",
        f"같은 것을 센 수가 아닙니다 — {합} 과 {전} 은 종류 구성이 다릅니다.",
        "그리고 **결정사항은 회의록의 그 줄을 그대로 인용하는 것이라 잘 맞을 수밖에",
        f'없습니다.** 합계에 섞으면 그 {셈.get("결정사항", 0)}개가 비율을 끌어올려 "좋아졌다" 가 나옵니다.',
        "",
        "| 종류 | 1판 (낱말) | 2판 (문장) |",
        "|---|---|---|",
        칸("논의"),
        칸("새 업무"),
        칸("결정사항"),
        f"| 합계 | {맞}/{전} ({round(맞 * 100 / 전)}%) | / {합} |",
        "",
        "| 회의 | 놓친 것이 있나 | 무엇을 놓쳤나 |",
        "|---|---|---|",
    ] + [f"| {m.title.split(' (')[0]} | | |" for m, _ in 묶음] + [
        "",
        "**X 이유별로도 셉니다** (성적표의 「X 이유를 셀 자리」 에 옮겨 적습니다).",
        "",
        "| 이유 | 2판 |",
        "|---|---|",
        "| `다른업무` | |",
        "| `할일아님` | |",
        "| `중복` | |",
        "| `기타` | |",
        "",
        "**1판의 `03.29 #1` 도 여기서 정합니다.** 1판 성적표가 그것을 「같은 모양」",
        "넷에 넣지 않고 이름만 적어 두었습니다 — 사람이 그렇게 분류한 것이",
        "아니어서입니다 (6-9). 지금 넷 중 하나로 정해 주세요.",
        "→ `다른업무` / `할일아님` / `중복` / `기타` 중: ______",
        "",
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description="표본 네 회의를 다시 내서 채점표를 만든다")
    ap.add_argument("--retreat", required=True)
    ap.add_argument("--낱말", action="store_true",
                    help="문장을 읽지 않고 낱말 겹침으로만 낸다 (1판 목록 · Claude 를 부르지 않는다)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--replace", action="store_true",
                    help="이미 있는 파일을 덮는다. 사람이 채운 것이 있으면 이것으로도 안 덮는다")
    args = ap.parse_args()

    낱말판 = getattr(args, "낱말")
    out = pathlib.Path(args.out) if args.out else (낱말나갈곳 if 낱말판 else 나갈곳)

    # **덮어쓰기 검사가 먼저다.** 키 검사·API 호출보다 앞에 둔다 — 못 쓸 것을
    # 알면서 돈을 들여 부를 이유가 없다
    막는다(out, args.replace)

    상태 = llm_mod.상태()
    if not 낱말판 and not 상태.ok:
        # **낱말로 물러선 것을 2판이라고 적지 않는다.** 그러면 견주는 두 숫자가
        # 같은 방식의 것이 되어 아무것도 재지 못한다
        print("Claude 키가 없습니다 -", 상태.말)
        print("docs/배포-안내.md 14장 을 보고 키를 넣은 뒤 다시 돌려 주세요.")
        raise SystemExit(2)

    init_db()
    db = SessionLocal()
    try:
        retreat = 회차찾기(db, args.retreat)
        묶음 = []
        총원 = 0.0
        for 제목 in 표본:
            m = db.scalars(
                select(Meeting).where(Meeting.retreat_id == retreat.id,
                                      Meeting.title == 제목)).first()
            if m is None:
                print(f"  ! 회의록 없음: {제목}")
                continue
            print(f"  … {제목}", flush=True)
            if 낱말판:
                # **낱말 겹침은 결정적이고 Claude 를 부르지 않는다.** 보드와
                # 회의록이 그대로면 같은 것이 나온다 — 그래서 1판이 무엇을
                # 냈는지 지금 다시 적을 수 있다
                r = S.결과(제안들=S.낱말제안(db, retreat=retreat, meeting=m,
                                        as_of=m.meeting_date),
                          방식="낱말", 말="낱말 겹침으로 골랐습니다")
            else:
                r = S.suggest_full(db, retreat=retreat, meeting=m,
                                   as_of=m.meeting_date)
            총원 += r.원
            묶음.append((m, r))
            if 낱말판:
                print(f"     {센다(r.제안들)}개", flush=True)
            else:
                print(f"     {len(r.제안들)}개 · {r.부른횟수}번 · "
                      f"in {r.입력토큰:,} out {r.출력토큰:,} (생각 {r.생각토큰:,}) · "
                      f"{r.원:,.0f}원" + ("  [못 읽음]" if r.실패 else ""), flush=True)

        총개수 = sum(센다(r.제안들) for _, r in 묶음)
        if 낱말판 and 총개수 != 일판합계[1]:
            # **대조의 전제가 무너진다.** 성적표의 21개와 다르면 그 사이
            # 보드나 회의록이 바뀐 것이고, "1판이 맞힌 것을 2판이 놓쳤나" 를
            # 셀 수 없게 된다
            print()
            print(f"낸 것이 {총개수}개입니다 - 성적표의 {일판합계[1]}개와 다릅니다.")
            print("그 사이 보드나 회의록이 바뀐 것이고, 대조의 전제가 무너집니다.")
            print("아무것도 쓰지 않았습니다.")
            raise SystemExit(6)

        물러선것 = [] if 낱말판 else [m.title for m, r in 묶음 if r.방식 != "문장"]
        if 물러선것:
            # **키만 보는 것으로는 부족했다.** 네트워크가 끊겼을 때 낱말
            # 결과가 그대로 2판으로 적혔다 — 그러면 견주는 두 숫자가 같은
            # 방식의 것이 되어 아무것도 재지 못한다
            print("\n문장으로 못 읽은 회의가 있습니다:", ", ".join(물러선것))
            for m, r in 묶음:
                if r.방식 != "문장":
                    print(f"   {m.title}: {r.말}")
            print("아무것도 쓰지 않았습니다. 고친 뒤 다시 돌려 주세요.")
            raise SystemExit(3)

        만든때 = f"{dt.datetime.now():%Y-%m-%d %H:%M}"
        if 낱말판:
            줄 = [
                "# 제안 1판 — 낱말 겹침으로 낸 것 (무엇을 냈는지의 기록)",
                "",
                f"만든 때: {만든때} (KST) · 회차: {retreat.name} · "
                "방식: 낱말 겹침 (Claude 를 부르지 않습니다)",
                "",
                "> **이 목록은 다시 낸 것입니다.** 2026-09-03 에 사람이 채점한 "
                "그 목록과 **같은지 확인되지 않았습니다** — 보드나 회의록이 "
                "그 사이 바뀌었으면 다를 수 있습니다.",
                "",
                "**판정 칸은 비워 둡니다.** 1판 채점은 `제안-성적표.md` 에 이미 "
                "있고, 여기 다시 적으면 같은 사실이 두 곳이 됩니다. 이 문서는 "
                "**무엇을 냈는지**만 남깁니다 — 1판이 맞힌 8개가 무엇이었는지 "
                "어디에도 없어서, 2판이 그것을 놓쳤는지 대조할 수 없었기 "
                "때문입니다.",
                "",
                "---",
                "",
            ]
        else:
            줄 = [
                "# 제안 2판 — 문장으로 읽은 것 (채점 전)",
                "",
                f"만든 때: {만든때} (KST) · "
                f"회차: {retreat.name} · 모델: {llm_mod.MODEL}",
                "",
                "**채점은 사람이 합니다.** 아래 표의 `판정` 과 `X 이유` 칸을 채우세요.",
                "판정은 `O`(맞다) · `X`(엉뚱하다) · `?`(반반) 입니다.",
                "",
                "> **1판(낱말 겹침)은 21개 중 14개(67%)였습니다** "
                "(`제안-성적표.md`). **종류별로 견줍니다** — 아래 「다 채운 뒤」 를 보세요.",
                "",
                f"이 표를 만드는 데 든 값: **약 {총원:,.0f}원** "
                f"(회의 {len(묶음)}건, 평균 {총원 / max(1, len(묶음)):,.0f}원)",
                "",
                "---",
                "",
            ]
        for m, r in 묶음:
            줄 += [
                f"## {m.title} ({m.meeting_date})",
                "",
                (f"- 낸 것 **{센다(r.제안들)}개** · 방식: 낱말 겹침"
                 if 낱말판 else
                 f"- 보낸 업무 목록: **{r.글자수:,}자** · 부른 횟수 {r.부른횟수}"
                 f" · 토큰 **{r.입력토큰:,} / {r.출력토큰:,}**"
                 f"(그중 생각 {r.생각토큰:,}) · 이 회의 값 **{r.원:,.0f}원**"),
            ]
            if not 낱말판:
                줄.append(f"- {r.말}")
            if r.사람평가:
                줄.append(f"- **사람 평가로 보이는 대목 {len(r.사람평가)}줄** — "
                          "제안에는 담기지 않았습니다 (9장)")
            if r.걸러낸것:
                줄.append("- 걸러낸 것: " + " · ".join(dict.fromkeys(r.걸러낸것)))
            줄 += [
                "",
                "| 종류 | 무엇을 하자는 것 | 근거 / 인용 | 판정 | X 이유 |",
                "|---|---|---|---|---|",
            ]
            if not r.제안들:
                줄.append("| — | (낸 것이 없습니다) | | | |")
            else:
                줄 += [한줄(x) for x in r.제안들]
            줄 += [
                "",
                "**마땅히 나왔어야 하는데 안 나온 것이 있나요?**  O / X  → ",
                "",
                "> 이 칸이 없으면 **적게 내는 쪽으로 점수를 올릴 수 있습니다.**",
                "",
                "---",
                "",
            ]
        if not 낱말판:
            줄 += 다채운뒤(묶음) + [
                "**근거도 함께 보세요.** 맞혔는데 근거가 낱말 하나면 나아진 것이",
                "아닙니다 (6-3). 2판의 근거는 문장이어야 합니다.",
                "",
            ]
        out.write_text("\n".join(줄) + "\n", encoding="utf-8")
        print()
        print(f"적었습니다: {out}  ({총개수}개)")
        if not 낱말판:
            print(f"모두 {총원:,.0f}원 들었습니다.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
