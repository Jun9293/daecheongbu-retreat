# -*- coding: utf-8 -*-
"""표본 네 회의를 **다시 내서** 채점표를 만든다 (회의록 7단계).

낱말 겹침의 성적은 사람이 이미 채웠다 — 20개 중 14개
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

제안 수가 달라진다. 낱말 겹침은 20개를 냈는데 문장으로 읽으면 더 낼 수도
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

나갈곳 = pathlib.Path(__file__).resolve().parent.parent / "docs" / "review" / "제안-2판.md"


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


def main() -> None:
    ap = argparse.ArgumentParser(description="표본 네 회의를 다시 내서 채점표를 만든다")
    ap.add_argument("--retreat", required=True)
    ap.add_argument("--out", default=str(나갈곳))
    args = ap.parse_args()

    상태 = llm_mod.상태()
    if not 상태.ok:
        # **낱말로 물러선 것을 2판이라고 적지 않는다.** 그러면 견주는 두 숫자가
        # 같은 방식의 것이 되어 아무것도 재지 못한다
        print("Claude 키가 없습니다 —", 상태.말)
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
            r = S.suggest_full(db, retreat=retreat, meeting=m, as_of=m.meeting_date)
            총원 += r.원
            묶음.append((m, r))
            print(f"     {len(r.제안들)}개 · {r.부른횟수}번 · "
                  f"in {r.입력토큰:,} out {r.출력토큰:,} (생각 {r.생각토큰:,}) · "
                  f"{r.원:,.0f}원" + ("  [못 읽음]" if r.실패 else ""), flush=True)

        물러선것 = [m.title for m, r in 묶음 if r.방식 != "문장"]
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

        줄 = [
            "# 제안 2판 — 문장으로 읽은 것 (채점 전)",
            "",
            f"만든 때: {dt.datetime.now():%Y-%m-%d %H:%M} (KST) · "
            f"회차: {retreat.name} · 모델: {llm_mod.MODEL}",
            "",
            "**채점은 사람이 합니다.** 아래 표의 `판정` 과 `X 이유` 칸을 채우세요.",
            "판정은 `O`(맞다) · `X`(엉뚱하다) · `?`(반반) 입니다.",
            "",
            "> **1판(낱말 겹침)은 20개 중 14개(70%)였습니다** "
            "(`제안-성적표.md`). 제안 수가 달라지므로 **비율로 견줍니다.**",
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
                f"- 보낸 업무 목록: **{r.글자수:,}자** · 부른 횟수 {r.부른횟수}"
                f" · 토큰 **{r.입력토큰:,} / {r.출력토큰:,}**"
                f"(그중 생각 {r.생각토큰:,}) · 이 회의 값 **{r.원:,.0f}원**",
                f"- {r.말}",
            ]
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
        줄 += [
            "## 다 채운 뒤",
            "",
            "| | 1판 (낱말) | 2판 (문장) |",
            "|---|---|---|",
            "| 낸 것 | 20 | |",
            "| 맞은 것 | 14 | |",
            "| 비율 | 70% | |",
            "| 놓친 회의 | (안 셌음) | |",
            "",
            "**근거도 함께 보세요.** 맞혔는데 근거가 낱말 하나면 나아진 것이",
            "아닙니다 (6-3). 2판의 근거는 문장이어야 합니다.",
            "",
        ]
        pathlib.Path(args.out).write_text("\n".join(줄) + "\n", encoding="utf-8")
        print(f"\n적었습니다: {args.out}")
        print(f"모두 {총원:,.0f}원 들었습니다.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
