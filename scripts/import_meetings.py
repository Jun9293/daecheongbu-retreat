"""노션 회의록 옮기기 (CLAUDE.md 회의록 1단계).

앞으로 회의록은 이 프로그램에 적고 노션에는 더 쓰지 않는다. 그래서 이 옮기기는
**일회성 이사**다 — 화면을 만들 일이 아니라 스크립트다.

    .venv\\Scripts\\python.exe scripts/import_meetings.py data/notion-meetings ^
        --retreat "2026 여름수련회 Belong"
    .venv\\Scripts\\python.exe scripts/import_meetings.py data/notion-meetings ^
        --retreat "..." --until 2026-06-30 --apply

`import_programs.py`(5-5) 와 **같은 규칙**을 따른다.

- `--apply` 없이 돌리면 **보여만 준다.** 기본이 미리보기다
- 이상한 것이 있으면 **어느 페이지의 어느 대목인지 말하고 멈춘다**
- **이미 있으면 그냥 덮지 않는다.** 몇 건이 지워질지 먼저 말하고
  `--replace` 를 줬을 때만 지운다

## 시뮬레이션 (3단계)

`--until 2026-06-30` 을 주면 **그 날짜까지의 회의만** 넣는다. 다음 실제 회의는
한참 뒤라, 26년 여름수련회의 실제 회의록을 시간순으로 하나씩 넣으면서 그때
무엇을 제안하는지 보는 것이 이 옵션의 목적이다.

**날짜 없는 덩어리는 `--until` 에 걸리지 않는다.** 언제 적은 것인지 모르므로
"6월까지" 에 든다고도 안 든다고도 할 수 없다 — 시뮬레이션에서는 빼고,
`--include-undated` 를 줬을 때만 넣는다. 모르는 것을 아는 척하지 않는다.

## 되돌리기

옮기기 한 번에 `--batch` 이름이 붙고 `Meeting.import_batch` 에 남는다.
`--undo <이름>` 으로 그 묶음만 골라 낸다 — 26년은 **끝난 실제 회차**라
개발 중 넣은 것이 6-2 자동 분류의 입력값이 되면 안 된다.
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글이 깨지지 않게 한다.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                    # noqa: E402

from app.db import SessionLocal, init_db                         # noqa: E402
from app.domain.meeting_import import cut, 회의                   # noqa: E402
from app.models import ActivityLog, Meeting, Retreat             # noqa: E402


class 멈춤(Exception):
    """무엇이 잘못됐는지 한국어로 말하고 멈추기 위한 것."""


def read_pages(folder: pathlib.Path) -> list[tuple[str, str]]:
    if not folder.is_dir():
        raise 멈춤(f"폴더가 없습니다: {folder}")
    pages = sorted(folder.glob("*.md"))
    if not pages:
        raise 멈춤(f"{folder} 에 .md 파일이 없습니다.")
    return [(p.stem, p.read_text(encoding="utf-8")) for p in pages]


def collect(folder: pathlib.Path) -> tuple[list[회의], list[tuple[str, object]]]:
    """모든 페이지를 잘라 시간순으로 모은다."""
    모두: list[회의] = []
    안본것: list[tuple[str, object]] = []
    for name, text in read_pages(folder):
        회의들, 걸린 = cut(text, source=name)
        모두.extend(회의들)
        안본것 += [(name, g) for g in 걸린]
    # 날짜 있는 것이 먼저, 그 안에서 시간순. 날짜 없는 것은 뒤로.
    모두.sort(key=lambda m: (m.date is None, m.date or dt.date.max, m.source))
    return 모두, 안본것


def 표시(m: 회의) -> str:
    return f"{m.date.isoformat() if m.date else '(날짜 없음)':>12}  {m.source} · {m.heading}"


def mark_highlights(body: str) -> str:
    """형광펜 자리에 `⟨미완료?⟩` 를 붙인다.

    **물음표가 붙어 있는 것이 중요하다.** 형광펜의 뜻은 노션에 적혀 있지 않고
    쓰인 모양에서 읽은 **추측**이다 (`meeting_import` 의 머리말).
    """
    import re

    return re.sub(
        r'<span color="yellow_bg">(.*?)</span>',
        lambda mm: f"⟨미완료?⟩{mm.group(1).strip()}",
        body,
        flags=re.S,
    )


def preview(회의들: list[회의], 안본것: dict[str, list[str]], *,
            until: dt.date | None, include_undated: bool) -> None:
    print("=" * 74)
    print("미리보기입니다. **아무것도 넣지 않았습니다.**  넣으려면 --apply")
    print("=" * 74)

    쪽별: dict[str, list[회의]] = {}
    for m in 회의들:
        쪽별.setdefault(m.source, []).append(m)
    print("\n[페이지별]")
    for name, items in 쪽별.items():
        날 = sum(1 for x in items if x.date)
        print(f"  {name:22s} 회의 {len(items):2d}건  (날짜 {날} · 날짜 없음 {len(items) - 날})")
    print(f"  {'합계':22s} 회의 {len(회의들)}건")

    고른것 = pick(회의들, until=until, include_undated=include_undated)
    if until:
        print(f"\n[--until {until}] 넣을 것 {len(고른것)}건 / 전체 {len(회의들)}건")
        if not include_undated:
            뺀것 = sum(1 for m in 회의들 if m.date is None)
            if 뺀것:
                print(f"  · 날짜 없는 덩어리 {뺀것}건은 뺐습니다 — 언제 적은 것인지"
                      " 모르므로 '어느 날짜까지' 에 들어가는지 말할 수 없습니다.")
                print("    넣으려면 --include-undated")

    print("\n[넣을 회의]")
    for m in 고른것:
        print("  " + 표시(m))

    빈자리 = [m for m in 고른것 if getattr(m, "empty_slot", False)]
    if 빈자리:
        print(f"\n[템플릿의 빈 칸 {len(빈자리)}건]  `26.00.00` — 회의가 아닙니다.")
        print("  날짜 없는 덩어리와 다릅니다(그쪽은 진짜 내용이 들어 있습니다).")
        for m in 빈자리:
            print(f"    {표시(m)}")

    형광 = [m for m in 고른것 if m.highlights]
    if 형광:
        import re as _re
        전부 = [h for m in 형광 for h in m.highlights]
        씨 = lambda t: _re.sub(r"[\s·,.()\-~]", "", t)
        셈: dict[str, int] = {}
        for h in 전부:
            셈[씨(h)] = 셈.get(씨(h), 0) + 1
        반복 = {k: v for k, v in 셈.items() if v >= 2}
        print(f"\n[형광펜 {len(전부)}곳 · 서로 다른 문장 {len(셈)}개"
              f" · 두 번 이상 나온 것 {len(반복)}개]")
        print("  **뜻은 추측이고 근거가 약합니다.** 노션에 규칙이 적혀 있지 않고,")
        print("  '안 끝나서 넘어온 것' 이라는 읽기는 두 번 나온 것들에 기대고 있습니다.")
        print(f"  나머지 {len(셈) - len(반복)}개는 한 번씩만 나옵니다 —"
              " 그냥 눈에 띄게 칠한 것일 수도 있습니다.")
        print("  본문에 ⟨미완료?⟩ 로 붙습니다. **물음표를 뗄지는 사람이 정합니다.**")
        for k, v in sorted(반복.items(), key=lambda x: -x[1]):
            원문 = next(h for h in 전부 if 씨(h) == k)
            print(f"    {v}번  {원문[:56]}")

    확실 = [m for m in 고른것 if m.people_sure]
    볼만 = [m for m in 고른것 if m.people_maybe]
    if 확실 or 볼만:
        print("\n" + "!" * 74)
        print("[사람 평가로 읽히는 대목]  **자동으로 빼지 않았습니다. 사람이 정합니다.**")
        print("  CLAUDE.md 9장 — 사람에 대한 평가는 이 시스템에 넣지 않습니다.")
        print("  0장의 '지식은 사람이 아니라 기록에 남긴다' 는 **업무 지식**을 말한")
        print("  것이지 사람 품평이 아닙니다. 기계는 둘을 가릴 수 없습니다 —")
        print("  `재정에 익숙` 은 평가이고 `재정 담당 …` 은 업무입니다.")
        print("!" * 74)
        if 확실:
            print(f"  ▸ 거의 확실 (MBTI) — {sum(len(m.people_sure) for m in 확실)}줄")
            for m in 확실:
                print(f"    {표시(m)}")
                for line in m.people_sure[:10]:
                    print(f"        · {line[:70]}")
        if 볼만:
            print(f"  ▸ 볼 만함 (잘함·못함 류) —"
                  f" {sum(len(m.people_maybe) for m in 볼만)}줄."
                  " **업무 메모도 걸립니다**(`사용못함` 등)")
            for m in 볼만:
                print(f"    {표시(m)}")
                for line in m.people_maybe[:10]:
                    print(f"        · {line[:70]}")
        print("  → 넣지 않으려면 그 회의를 --skip 으로 빼세요"
              " (예: --skip 04-총무팀:26.06.21)")

    if 안본것:
        묶음: dict[str, list] = {}
        for name, g in 안본것:
            묶음.setdefault(g.kind, []).append((name, g))
        말 = {
            "안본제목": "[회의로 보지 않은 빨간 줄]  버린 것이 아니라 아래 회의의 내용으로 들어갑니다",
            "날짜같은줄": "[본문 안에 날짜처럼 보이는 줄]  **자르지 않았습니다. 말만 합니다** —"
                       " 색이 다르거나 자릿수가 달라 제목으로 못 알아본 것일 수 있습니다",
            "머리말": "[첫 회의 앞의 글]  회의로 넣지 않았습니다. 필요하면 손으로 옮기세요",
        }
        for kind in ("날짜같은줄", "안본제목", "머리말"):
            것들 = 묶음.get(kind)
            if not 것들:
                continue
            print(f"\n{말[kind]}")
            for name, g in 것들:
                붙 = f"   → 「{g.붙은곳}」 에 붙음" if g.붙은곳 else ""
                print(f"  {name} · {g.text[:56]}{붙}")

    print("\n[옮기지 않는 것]")
    print("  · 첨부 파일 — 있었다는 사실만 남깁니다 (본체는 안 옮깁니다)")
    print("  · 이미지 — 노션의 서명된 주소는 만료됩니다")
    print("  · 다른 노션 페이지로의 mention — 링크가 이 시스템 밖을 가리킵니다")


def pick(회의들: list[회의], *, until: dt.date | None,
         include_undated: bool, skip: set[str] | None = None) -> list[회의]:
    """넣을 것만 고른다. **미리보기와 실제가 같은 함수를 쓴다** —
    두 벌이 되면 보여준 것과 넣는 것이 갈리고, 갈린 쪽을 아무도 눈치채지 못한다."""
    skip = skip or set()
    고른것 = []
    for m in 회의들:
        if f"{m.source}:{m.heading.split()[0]}" in skip or m.heading in skip:
            continue
        if m.date is None:
            if until and not include_undated:
                continue
        elif until and m.date > until:
            continue
        고른것.append(m)
    return 고른것


def apply(회의들: list[회의], *, retreat: Retreat, batch: str, replace: bool) -> int:
    with SessionLocal() as db:
        있던것 = list(db.scalars(
            select(Meeting).where(Meeting.retreat_id == retreat.id,
                                  Meeting.origin == "노션")))
        if 있던것 and not replace:
            raise 멈춤(
                f"이 회차에 이미 옮겨 온 회의록이 {len(있던것)}건 있습니다.\n"
                "        덮어쓰려면 --replace 를 붙여주세요. 그러면 위의 것이 전부 지워집니다.\n"
                "        묶음 하나만 골라 내려면 --undo <묶음이름> 을 쓰세요.")
        if 있던것 and replace:
            for m in 있던것:
                db.delete(m)
            db.flush()

        for m in 회의들:
            db.add(Meeting(
                retreat_id=retreat.id,
                title=m.heading,
                meeting_date=m.date,
                attendee_names=[],
                body=mark_highlights(m.body),
                origin="노션",
                source_ref=m.source,
                import_batch=batch,
            ))
        db.add(ActivityLog(
            retreat_id=retreat.id, actor_type="user", action="회의록_옮기기",
            target_type="meeting", target_id=None,
            summary=f"노션에서 {len(회의들)}건 (묶음 {batch})",
        ))
        db.commit()
    return len(회의들)


def undo(batch: str, *, retreat: Retreat) -> int:
    with SessionLocal() as db:
        해당 = list(db.scalars(
            select(Meeting).where(Meeting.retreat_id == retreat.id,
                                  Meeting.import_batch == batch)))
        if not 해당:
            raise 멈춤(f"'{batch}' 묶음으로 넣은 회의록이 없습니다.")
        for m in 해당:
            db.delete(m)
        db.add(ActivityLog(
            retreat_id=retreat.id, actor_type="user", action="회의록_옮기기_되돌림",
            target_type="meeting", target_id=None,
            summary=f"묶음 {batch} {len(해당)}건 지움",
        ))
        db.commit()
    return len(해당)


def find_retreat(name: str) -> Retreat:
    """**이름으로 정확히 찾는다.** 비슷한 이름을 골라 넣지 않는다 (5-5)."""
    with SessionLocal() as db:
        r = db.scalars(select(Retreat).where(Retreat.name == name)).first()
        if r:
            db.expunge(r)
            return r
        전부 = [x.name for x in db.scalars(select(Retreat))]
    raise 멈춤("그런 이름의 회차가 없습니다: " + name + "\n        있는 회차 — "
               + (", ".join(전부) if 전부 else "(없음)"))


def main() -> int:
    ap = argparse.ArgumentParser(description="노션 회의록 옮기기")
    ap.add_argument("folder", nargs="?", default="data/notion-meetings",
                    help="노션에서 받아 온 .md 들이 있는 폴더")
    ap.add_argument("--retreat", required=True, help="넣을 회차의 이름 (정확히)")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 넣는다. 없으면 보여만 준다")
    ap.add_argument("--replace", action="store_true",
                    help="이미 옮겨 온 것이 있으면 지우고 다시 넣는다")
    ap.add_argument("--until", help="이 날짜까지의 회의만 (YYYY-MM-DD). 시뮬레이션용")
    ap.add_argument("--include-undated", action="store_true",
                    help="--until 과 함께 쓸 때 날짜 없는 덩어리도 넣는다")
    ap.add_argument("--skip", action="append", default=[],
                    help="넣지 않을 회의 (예: 04-총무팀:26.06.21). 여러 번 쓸 수 있다")
    ap.add_argument("--batch", help="옮기기 묶음 이름. 안 주면 오늘 날짜와 시각")
    ap.add_argument("--undo", help="그 묶음으로 넣은 것을 지운다")
    args = ap.parse_args()

    init_db()
    try:
        retreat = find_retreat(args.retreat)
        if args.undo:
            n = undo(args.undo, retreat=retreat)
            print(f"'{args.undo}' 묶음 {n}건을 지웠습니다.")
            return 0

        until = dt.date.fromisoformat(args.until) if args.until else None
        회의들, 안본것 = collect(pathlib.Path(args.folder))
        if not args.apply:
            preview(회의들, 안본것, until=until,
                    include_undated=args.include_undated)
            return 0

        고른것 = pick(회의들, until=until, include_undated=args.include_undated,
                     skip=set(args.skip))
        batch = args.batch or dt.datetime.now().strftime("%Y%m%d-%H%M")
        n = apply(고른것, retreat=retreat, batch=batch, replace=args.replace)
        print(f"{n}건을 넣었습니다. 묶음 이름 '{batch}'")
        print(f"되돌리려면 —  --retreat \"{args.retreat}\" --undo {batch}")
        return 0
    except 멈춤 as e:
        print("멈췄습니다 —", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
