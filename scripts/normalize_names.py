"""담당자 표기 통일 — `민준` / `민준M` 처럼 갈린 이름을 M 쪽으로 맞춘다 (CLAUDE.md 5-3).

    .venv\\Scripts\\python.exe scripts/normalize_names.py --retreat "2026 여름수련회 Belong"
    .venv\\Scripts\\python.exe scripts/normalize_names.py --retreat "..." --apply

**왜 스크립트인가** — `ProgramItem.assignee_name` 은 계정과 잇지 않은 이름
문자열이다(5장). 현장에 계정 없는 사람이 섞이기 때문에 그렇게 두었고, 그 대가로
오타와 표기 흔들림이 그대로 남는다. 화면에서 하나씩 고치면 180건 중 어느 것을
고쳤는지 알 수 없고 다음 회차에 또 생긴다. **무엇을 어떻게 바꿨는지 남는 방식으로 한다.**

**`--apply` 없이 돌리면 보여만 준다.** 기본이 미리보기다 — 이름을 잘못 바꾸면
누가 무엇을 맡았는지가 틀어지는데, 그건 되돌릴 근거가 화면에 남지 않는다.

**짝을 코드에 박지 않는다.** 회차 자료에서 `X` 와 `XM` 이 둘 다 쓰인 것만 찾아
`X` 를 `XM` 으로 바꾼다. 다음 회차에 다른 이름이 갈려도 같은 스크립트가 잡고,
`하람`·`나윤`·`온` 처럼 M 없이만 쓰는 사람에게는 손대지 않는다 —
**없는 짝에 M 을 붙이면 사람 이름이 틀어진다.**
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글·기호가 깨지지 않게 한다.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from app.deps import log_activity                                # noqa: E402
# 회차를 이름으로 찾는 것은 이미 있다 — 같은 것을 두 벌 만들지 않는다.
# 비슷한 이름을 골라 넣지 않고 있는 회차를 보여주고 멈추는 규칙도 함께 따라온다.
from scripts.import_programs import ImportError_, find_retreat   # noqa: E402

from app.models import Program, ProgramItem, Retreat             # noqa: E402

# 한 칸에 여럿이 들어 있다: `서윤·나윤`, `온·시우·다은`.
# **쪼개서 각 이름을 따로 보고 다시 합친다** — 통째로 비교하면 그 안의 이름은 못 고친다.
# 구분자를 잡아 두는 이유는 원래 쓰던 것을 그대로 돌려놓기 위해서다.
SPLIT = re.compile(r"([·,/])")


def split_names(value: str) -> list[str]:
    """구분자를 사이에 낀 채로 쪼갠다. 홀수 자리가 이름, 짝수 자리가 구분자."""
    return SPLIT.split(value or "")


def pairs_in(items: list[ProgramItem]) -> dict[str, str]:
    """이 회차에서 `X` 와 `XM` 이 둘 다 쓰인 것만 찾아 {X: XM} 으로.

    **회차 자료에서 찾는다.** 목록을 코드에 박으면 다음 회차에 다른 이름이
    갈렸을 때 이 스크립트가 아무것도 못 한다.
    """
    seen: set[str] = set()
    for item in items:
        for token in split_names(item.assignee_name or ""):
            name = token.strip()
            if name and name not in "·,/":
                seen.add(name)
    # XM 이 있는 X 만. 없으면 건드리지 않는다.
    return {n: n + "M" for n in sorted(seen) if not n.endswith("M") and n + "M" in seen}


def rewrite(value: str, mapping: dict[str, str]) -> str | None:
    """바뀔 값. 바꿀 것이 없으면 None.

    앞뒤 공백은 정리하되 **구분자는 원래 쓰던 것을 그대로 둔다.**
    바뀌는 항목에서만 공백을 정리한다 — 아무 관계 없는 줄까지 건드리면
    "무엇을 바꿨는가" 가 흐려진다.
    """
    if not value:
        return None
    parts = split_names(value)
    changed = False
    out = []
    for index, token in enumerate(parts):
        if index % 2:                       # 구분자 — 그대로
            out.append(token)
            continue
        name = token.strip()
        if name in mapping:
            out.append(mapping[name])
            changed = True
        else:
            out.append(name)
    return "".join(out) if changed else None


def collect(db: Session, retreat: Retreat) -> tuple[dict[str, str], list[dict]]:
    """(짝, 바뀔 항목들). 이 회차의 ProgramItem 만 본다 (4단계)."""
    programs = list(
        db.scalars(
            select(Program)
            .where(Program.retreat_id == retreat.id)
            .order_by(Program.start_time, Program.sort_order, Program.id)
        )
    )
    items = [i for p in programs for i in p.items]
    mapping = pairs_in(items)

    changes = []
    for program in programs:
        for item in program.items:
            fresh = rewrite(item.assignee_name or "", mapping)
            if fresh is None or fresh == item.assignee_name:
                continue
            changes.append({
                "item": item,
                "id": item.id,
                "before": item.assignee_name,
                "after": fresh,
                "day": program.day,
                "start_time": program.start_time,
                "program": program.name,
                "part": item.part_key,
                "text": item.text,
            })
    return mapping, changes


def run(db: Session, *, retreat_name: str, apply: bool = False) -> dict:
    retreat = find_retreat(db, retreat_name)
    mapping, changes = collect(db, retreat)

    if apply and changes:
        for row in changes:
            row["item"].assignee_name = row["after"]
        db.commit()
        summary = " · ".join(
            f"{a}→{b} {sum(1 for c in changes if _touches(c, a))}건"
            for a, b in sorted(mapping.items())
            if any(_touches(c, a) for c in changes)
        )
        log_activity(
            db,
            retreat_id=retreat.id,
            actor=None,
            action="담당자_표기_통일",
            target_type="retreat",
            target_id=retreat.id,
            summary=f"{len(changes)}건 — {summary}",
            before_value={"names": sorted(mapping)},
            after_value={"names": sorted(mapping.values()), "items": len(changes)},
        )

    return {
        "retreat": retreat.name,
        "mapping": mapping,
        "changes": changes,
        "applied": bool(apply and changes),
    }


def _touches(change: dict, name: str) -> bool:
    """그 항목이 이름 `name` 때문에 바뀌었는가."""
    before = {t.strip() for t in split_names(change["before"] or "")}
    after = {t.strip() for t in split_names(change["after"] or "")}
    return name in before and name not in after


def show(result: dict, *, apply: bool) -> None:
    changes = result["changes"]
    mapping = result["mapping"]

    print(f"'{result['retreat']}' 담당자 표기\n")
    if not mapping:
        print("  갈린 표기가 없습니다. (X 와 XM 이 둘 다 쓰인 이름이 없습니다)")
        return

    print(f"  찾은 짝 {len(mapping)}개 — " + " · ".join(f"{a}→{b}" for a, b in mapping.items()))
    if not changes:
        print("\n  바꿀 것이 없습니다. 이미 맞춰져 있습니다.")
        return

    print()
    for name, target in mapping.items():
        rows = [c for c in changes if _touches(c, name)]
        if not rows:
            continue
        print(f"  {name} → {target}   ({len(rows)}건)")
        for row in rows:
            head = f"{row['day']} {row['start_time']} {row['program']}"
            print(f"    · {head:<28} [{row['part']}] {row['text'][:46]}")
            if row["before"] != name:          # 여럿이 든 칸은 통째로 보여준다
                print(f"      {row['before']}  →  {row['after']}")
        print()

    print(f"  합계 {len(changes)}건")
    if apply:
        print("  바꿨습니다. 활동 기록에 남겼습니다.")
    else:
        print("  아직 바꾸지 않았습니다 — 실제로 바꾸려면 --apply 를 붙이세요.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="담당자 표기를 M 쪽으로 통일합니다. 기본은 미리보기입니다."
    )
    parser.add_argument("--retreat", required=True, help="회차 이름 (정확히)")
    parser.add_argument(
        "--apply", action="store_true",
        help="실제로 바꿉니다 (없으면 보여주기만 합니다)",
    )
    args = parser.parse_args()

    from app.db import SessionLocal, init_db

    init_db()
    with SessionLocal() as db:
        try:
            result = run(db, retreat_name=args.retreat, apply=args.apply)
        except ImportError_ as exc:
            print("하지 못했습니다 —", exc)
            return 1
        show(result, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
