"""프로그램표 가져오기 (CLAUDE.md 5장).

구글시트의 일자별 시트를 옮긴 JSON 을 `Program` · `ProgramItem` 으로 넣는다.

    .venv\\Scripts\\python.exe scripts/import_programs.py data/2026여름_프로그램표.json ^
        --retreat "2026 여름수련회"

**이 파일은 무엇을 했는지의 기록이 아니라 무엇을 하기로 했는지의 표다.**
그래서 `done_at` · `done_by_id` 를 넣지 않는다 — 지어낸 체크는 "누가 놓쳐도
시스템이 대신 알아차리는가" 라는 판단 기준(0장)을 정면으로 무너뜨린다.
체크가 하나도 없는 지난 회차를 화면이 어떻게 다루는지는 5-6 에 있다.

**두 번 돌려도 그냥 덮어쓰지 않는다.** 몇 건이 지워질지 먼저 말하고 `--replace`
를 줬을 때만 지운다 — 실수로 한 번 더 돌려서 날아가면 되돌릴 방법이 없다.
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글·기호가 깨지지 않게 한다.
# 여기서 터지면 "무엇이 문제인지 말해주는 스크립트" 가 자기 때문에 죽는다.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from app.domain.live import guess_scope                          # noqa: E402
from app.models import (                                         # noqa: E402
    PROGRAM_AUDIENCES,
    PROGRAM_PARTS,
    PROGRAM_PHASES,
    PROGRAM_SCOPES,
    PROGRAM_TRACKS,
    Program,
    ProgramItem,
    Retreat,
)

# 일자 이름 — 선발대 · N일차 · 폐회. 회차가 길면 3일차·4일차도 나오므로
# 목록으로 못박지 않고 모양으로 본다. 대신 오타는 여기서 걸린다.
DAY_SHAPE = re.compile(r"^(선발대|폐회|\d+일차)$")
TIME_SHAPE = re.compile(r"^(\d{1,2}):(\d{2})$")


class ImportError_(Exception):
    """무엇이 잘못됐는지 한국어로 말하고 멈추기 위한 것."""


def line_of(raw: str, needle: str) -> int | None:
    """그 문장이 파일 몇 번째 줄에 있는지. 못 찾으면 None.

    JSON 은 줄 단위가 아니라서 파서가 줄 번호를 주지 않는다. 사람이 파일을
    열어 고쳐야 하므로 '어디쯤인지'를 손으로 찾아 준다.
    """
    if not needle:
        return None
    at = raw.find(json.dumps(needle, ensure_ascii=False)[1:-1])
    if at < 0:
        return None
    return raw.count("\n", 0, at) + 1


def parse(path: pathlib.Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImportError_(f"JSON 을 읽지 못했습니다 — {exc}") from None
    if not isinstance(data.get("days"), dict):
        raise ImportError_("파일에 days 가 없습니다. { \"days\": { \"선발대\": [...] } } 모양이어야 합니다.")
    return data, raw


def check(data: dict, raw: str) -> list[dict]:
    """넣기 전에 전부 훑는다. **하나라도 이상하면 아무것도 넣지 않는다** —
    절반만 들어간 프로그램표는 비어 있는 것보다 나쁘다."""
    rows: list[dict] = []
    for day, programs in data["days"].items():
        if not DAY_SHAPE.match(str(day)):
            raise ImportError_(
                f"모르는 일자입니다: '{day}'\n"
                f"        선발대 · 1일차 · 2일차 … · 폐회 중 하나여야 합니다."
            )
        if not isinstance(programs, list):
            raise ImportError_(f"'{day}' 의 프로그램 목록이 배열이 아닙니다.")

        for index, program in enumerate(programs, 1):
            name = str(program.get("name") or "").strip()
            where = f"{day} {index}번째 프로그램"
            if not name:
                raise ImportError_(f"{where} 에 이름이 없습니다.")
            where = f"{day} {index}번째 '{name}'"

            time = TIME_SHAPE.match(str(program.get("start_time") or "").strip())
            if not time:
                line = line_of(raw, name)
                raise ImportError_(
                    f"{where} 의 시각을 읽지 못했습니다: "
                    f"'{program.get('start_time')}'\n"
                    f"        09:30 처럼 적어주세요."
                    + (f" ({line}번째 줄 근처)" if line else "")
                )
            hour, minute = int(time.group(1)), int(time.group(2))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ImportError_(f"{where} 의 시각이 범위를 벗어났습니다: {program['start_time']}")

            items = []
            for order, item in enumerate(program.get("items") or [], 1):
                text = str(item.get("text") or "").strip()
                spot = f"{where} → {order}번째 항목"
                if not text:
                    raise ImportError_(f"{spot} 에 내용이 없습니다.")

                part = str(item.get("part") or "").strip()
                if part not in PROGRAM_PARTS:
                    line = line_of(raw, text)
                    raise ImportError_(
                        f"모르는 파트입니다: '{part}'\n"
                        f"        {spot}"
                        + (f" ({line}번째 줄)" if line else "")
                        + f"\n        \"{text}\"\n"
                        f"        쓸 수 있는 파트: {' · '.join(PROGRAM_PARTS)}"
                    )

                phase = str(item.get("phase") or "").strip()
                if phase not in PROGRAM_PHASES:
                    line = line_of(raw, text)
                    raise ImportError_(
                        f"모르는 구간입니다: '{phase}'\n"
                        f"        {spot}"
                        + (f" ({line}번째 줄)" if line else "")
                        + "\n        pre(준비) · mid(진행) · post(정리) 중 하나여야 합니다."
                    )

                who = item.get("assignee")

                # 범위 (5-2). **없으면 person 으로 몰지 않고 계산한다** —
                # scope 가 없던 시절의 파일도 그대로 들어가야 하는데, 전부
                # 개인으로 몰리면 봉사자 열이 통째로 개인 일이 된다.
                raw_scope = item.get("scope")
                inferred = raw_scope is None or str(raw_scope).strip() == ""
                if inferred:
                    scope = guess_scope(part, who)
                else:
                    scope = str(raw_scope).strip()
                    if scope not in PROGRAM_SCOPES:
                        line = line_of(raw, text)
                        raise ImportError_(
                            f"모르는 범위입니다: '{scope}'\n"
                            f"        {spot}"
                            + (f" ({line}번째 줄)" if line else "")
                            + f'\n        "{text}"\n'
                            f"        team(팀 단위) · person(개인 단위) 중 하나여야 합니다."
                        )

                items.append({
                    "phase": phase,
                    "part_key": part,
                    "assignee_name": (str(who).strip() or None) if who else None,
                    "text": text,
                    "sort_order": order - 1,
                    "scope": scope,
                    # 파일에 적혀 있던 것인지 우리가 추측한 것인지 — 세어서 알려준다
                    "_inferred": inferred,
                })

            # ── 봉사자 시간표가 쓰는 것들 (5-8) ──
            # 없으면 기본값. 이상한 값이면 어느 줄인지 말하고 멈춘다.
            def pick(key: str, allowed: tuple[str, ...], fallback: str) -> str:
                raw_value = program.get(key)
                if raw_value is None or str(raw_value).strip() == "":
                    return fallback
                value = str(raw_value).strip()
                if value not in allowed:
                    line = line_of(raw, name)
                    raise ImportError_(
                        f"모르는 {key} 입니다: '{value}'\n"
                        f"        {where}"
                        + (f" ({line}번째 줄 근처)" if line else "")
                        + f"\n        {' · '.join(allowed)} 중 하나여야 합니다."
                    )
                return value

            audience = pick("audience", PROGRAM_AUDIENCES, "all")
            track = pick("track", PROGRAM_TRACKS, "main")

            raw_parallel = program.get("parallel")
            if raw_parallel is None or str(raw_parallel).strip() == "":
                parallel = False
            elif isinstance(raw_parallel, bool):
                parallel = raw_parallel
            else:
                text_value = str(raw_parallel).strip().lower()
                if text_value in ("true", "1", "yes"):
                    parallel = True
                elif text_value in ("false", "0", "no"):
                    parallel = False
                else:
                    line = line_of(raw, name)
                    raise ImportError_(
                        f"모르는 parallel 입니다: '{raw_parallel}'\n"
                        f"        {where}"
                        + (f" ({line}번째 줄 근처)" if line else "")
                        + "\n        true · false 중 하나여야 합니다."
                    )

            raw_end = program.get("end_time")
            end_time = None
            if raw_end is not None and str(raw_end).strip():
                end = TIME_SHAPE.match(str(raw_end).strip())
                if not end or not (0 <= int(end.group(1)) <= 23
                                   and 0 <= int(end.group(2)) <= 59):
                    line = line_of(raw, name)
                    raise ImportError_(
                        f"{where} 의 끝 시각을 읽지 못했습니다: '{raw_end}'\n"
                        f"        09:30 처럼 적어주세요."
                        + (f" ({line}번째 줄 근처)" if line else "")
                    )
                end_time = f"{int(end.group(1)):02d}:{int(end.group(2)):02d}"

            rows.append({
                "day": str(day),
                "start_time": f"{hour:02d}:{minute:02d}",
                "end_time": end_time,
                "audience": audience,
                "track": track,
                "parallel": parallel,
                "name": name,
                "host": (str(program.get("host")).strip() or None) if program.get("host") else None,
                "place": (str(program.get("place")).strip() or None) if program.get("place") else None,
                "note": (str(program.get("note")).strip() or None) if program.get("note") else None,
                "items": items,
            })
    return rows


def find_retreat(db: Session, name: str) -> Retreat:
    """이름으로 찾는다. **비슷한 이름을 골라 넣지 않는다** —
    엉뚱한 회차에 61개를 넣고 나면 어느 것이 원래 것인지 알 수 없다."""
    found = list(db.scalars(select(Retreat).where(Retreat.name == name)))
    if len(found) == 1:
        return found[0]
    have = [r.name for r in db.scalars(select(Retreat).order_by(Retreat.id))]
    if not found:
        raise ImportError_(
            f"'{name}' 이라는 회차가 없습니다.\n"
            f"        있는 회차: {' / '.join(have) if have else '(없음)'}\n"
            f"        --retreat 에 정확한 이름을 적어주세요."
        )
    raise ImportError_(f"'{name}' 이라는 회차가 {len(found)}개입니다. 먼저 정리해주세요.")


def run(
    db: Session, *, path: pathlib.Path, retreat_name: str, replace: bool = False
) -> dict:
    data, raw = parse(path)
    rows = check(data, raw)
    retreat = find_retreat(db, retreat_name)

    existing = list(
        db.scalars(select(Program).where(Program.retreat_id == retreat.id))
    )
    if existing and not replace:
        items = sum(len(p.items) for p in existing)
        checked = sum(1 for p in existing for i in p.items if i.done_at)
        raise ImportError_(
            f"'{retreat.name}' 에 이미 프로그램 {len(existing)}개 · 항목 {items}건이 있습니다"
            + (f" (그중 {checked}건은 체크된 것입니다)" if checked else "")
            + ".\n"
            "        덮어쓰려면 --replace 를 붙여주세요. 그러면 위의 것이 전부 지워집니다."
        )

    removed = len(existing)
    for program in existing:
        db.delete(program)
    db.flush()

    for order, row in enumerate(rows):
        program = Program(
            retreat_id=retreat.id,
            day=row["day"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            audience=row["audience"],
            track=row["track"],
            parallel=row["parallel"],
            name=row["name"],
            host=row["host"],
            place=row["place"],
            note=row["note"],
            sort_order=order,
        )
        db.add(program)
        db.flush()
        for item in row["items"]:
            # done_at · done_by_id 를 넣지 않는다 — 이 파일은 계획이지 기록이 아니다.
            # _inferred 는 세어서 알려주기 위한 것이라 컬럼이 아니다.
            fields = {k: v for k, v in item.items() if not k.startswith("_")}
            db.add(ProgramItem(program_id=program.id, **fields))
    db.commit()

    by_day: dict[str, dict[str, int]] = {}
    parts: dict[str, int] = {}
    people: dict[str, int] = {}
    scopes: dict[str, int] = {"team": 0, "person": 0}
    guessed = 0
    for row in rows:
        slot = by_day.setdefault(
            row["day"], {"programs": 0, "items": 0, "team": 0, "person": 0})
        slot["programs"] += 1
        slot["items"] += len(row["items"])
        for item in row["items"]:
            parts[item["part_key"]] = parts.get(item["part_key"], 0) + 1
            slot[item["scope"]] += 1
            scopes[item["scope"]] += 1
            if item["assignee_name"]:
                people[item["assignee_name"]] = people.get(item["assignee_name"], 0) + 1
    guessed = sum(1 for r in rows for i in r["items"] if i["_inferred"])

    return {
        "retreat": retreat.name,
        "programs": len(rows),
        "items": sum(len(r["items"]) for r in rows),
        "removed": removed,
        "by_day": by_day,
        "parts": parts,
        "scopes": scopes,
        "guessed_scopes": guessed,
        "people": people,
        "similar": similar_names(people),
    }


def similar_names(people: dict[str, int]) -> list[tuple[str, str]]:
    """비슷한 이름 짝. 담당자는 계정과 잇지 않으므로 오타가 그대로 남는다 —
    사람이 눈으로 확인할 수 있게 짚어 준다. 고치지는 않는다."""
    split = re.compile(r"[·,/]")
    counts: dict[str, int] = {}
    for name, n in people.items():
        for one in split.split(name):
            one = one.strip()
            if one:
                counts[one] = counts.get(one, 0) + n

    pairs: list[tuple[str, str]] = []
    for name in sorted(counts):
        # 'M' 이 붙은 것과 안 붙은 것 (민준 / 민준M)
        if not name.endswith("M") and name + "M" in counts:
            pairs.append((f"{name} ({counts[name]}건)", f"{name}M ({counts[name + 'M']}건)"))
        # 공백만 다른 것
        squished = name.replace(" ", "")
        for other in counts:
            if other != name and other.replace(" ", "") == squished and name < other:
                pairs.append((f"{name} ({counts[name]}건)", f"{other} ({counts[other]}건)"))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="구글시트에서 옮긴 프로그램표 JSON 을 회차에 넣습니다."
    )
    parser.add_argument("path", help="JSON 파일 경로")
    parser.add_argument("--retreat", required=True, help="넣을 회차의 이름 (정확히)")
    parser.add_argument(
        "--replace", action="store_true",
        help="이미 있는 프로그램표를 지우고 넣습니다 (되돌릴 수 없습니다)",
    )
    args = parser.parse_args()

    path = pathlib.Path(args.path)
    if not path.exists():
        print(f"파일이 없습니다: {path}")
        return 1

    from app.db import SessionLocal, init_db

    init_db()
    with SessionLocal() as db:
        try:
            result = run(db, path=path, retreat_name=args.retreat, replace=args.replace)
        except ImportError_ as exc:
            print("넣지 못했습니다 —", exc)
            return 1

    print(f"'{result['retreat']}' 에 넣었습니다.")
    if result["removed"]:
        print(f"  (있던 프로그램 {result['removed']}개를 지우고 새로 넣었습니다)")
    print(f"  프로그램 {result['programs']}개 · 항목 {result['items']}건\n")

    print("  일자별")
    for day, slot in result["by_day"].items():
        print(f"    {day}: 프로그램 {slot['programs']}개 · 항목 {slot['items']}건"
              f" (팀 {slot['team']} · 개인 {slot['person']})")

    print("\n  범위별 항목")
    print(f"    팀 단위 {result['scopes']['team']}건 · 개인 단위 {result['scopes']['person']}건")
    if result["guessed_scopes"]:
        print(f"    (그중 {result['guessed_scopes']}건은 파일에 범위가 없어 담당·파트로 추측했습니다.")
        print("     추측이지 규칙이 아니므로 화면에서 고칠 수 있습니다)")

    print("\n  파트별 항목")
    for part in PROGRAM_PARTS:
        if part in result["parts"]:
            print(f"    {part}: {result['parts'][part]}건")

    print(f"\n  담당자로 적힌 이름 {len(result['people'])}가지")
    for name in sorted(result["people"]):
        print(f"    {name} ({result['people'][name]}건)")

    if result["similar"]:
        print("\n  ! 비슷한 이름이 함께 있습니다 — 같은 사람인지 확인해주세요.")
        print("    (담당자는 계정과 잇지 않으므로 적은 그대로 남습니다)")
        for left, right in result["similar"]:
            print(f"    {left}  vs  {right}")

    print("\n  체크 상태는 넣지 않았습니다 — 이 파일은 무엇을 하기로 했는지의 표입니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
