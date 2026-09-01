"""수련회 진행 (CLAUDE.md 5장) — 일자·상태·지연 계산.

이 화면은 지금까지 만든 것들과 성격이 다릅니다. 준비 보드는 몇 달에 걸쳐
천천히 보는 것이지만, 여기는 **현장에서 휴대폰으로 급히 보는 것**입니다.

**시각에 의존하는 판정은 전부 `now` 를 받습니다.** 기본값을 쓰지 않고 인자로
넘기는 이유는 두 가지입니다 — 테스트가 실행 시각에 따라 갈리면 안 되고,
한 화면을 그리는 동안 여러 계산이 서로 다른 '지금'을 보면 안 됩니다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    PROGRAM_PARTS,
    PROGRAM_PHASES,
    TEAM_WORDS,
    Program,
    ProgramItem,
    Retreat,
)

# 부서 키 → 파트 (5-3). 총무팀 파트는 총무팀 안의 나눔이라 부서와 1:1 이 아니다 —
# 맞는 것만 이어 준다. 없으면 '전체' 로 두고 사용자가 직접 고른다.
DEPARTMENT_PART = {
    "hebron": "헤브론",
    "koram": "코람데오",
    "jaejeong": "재정",
}

ALL_PARTS = "전체"

# 범위 칩 (5-2). 파트 칩과 **함께** 걸린다 — 파트는 '무슨 일인가',
# 범위는 '팀이 움직이는가 내가 하는가' 라 서로 다른 축이다.
ALL_SCOPES = "전체"
TEAM_ONLY = "team"
PERSON_ONLY = "person"

# 봉사팀 파트는 팀이 움직이는 자리다 — 가져올 때의 추측에 쓴다.
TEAM_PARTS = frozenset({"헤브론", "코람데오"})


def guess_scope(part: str | None, assignee: str | None) -> str:
    """scope 가 적혀 있지 않을 때의 추측 (5-2).

    **추측이지 규칙이 아닙니다.** 컬럼으로 따로 두는 이유가 여기 있습니다 —
    총무팀 항목에도 "강당 의자 세팅_전체" 처럼 팀 단위가 섞이고, 봉사팀도
    개인에게 붙는 일이 생깁니다. 그래서 넣은 뒤 화면에서 고칠 수 있습니다.

    기준: 파트가 봉사팀이면 팀. 담당이 비었거나 묶음 이름이면 팀. 나머지는 개인.
    """
    if (part or "").strip() in TEAM_PARTS:
        return "team"
    who = (assignee or "").strip()
    if not who:
        return "team"
    return "team" if who in TEAM_WORDS else "person"


# ── 일자 ─────────────────────────────────────────────────────────────
#
# 날짜를 저장하지 않고 회차의 개회일에서 계산한다. 라이브러리가 절대 날짜를
# 갖지 않는 것과 같은 이유다 — 개회일이 바뀌면 프로그램표도 따라 움직여야 한다.
#
#   선발대 = 개회일 하루 전
#   N일차  = 개회일부터 폐회 전날까지
#   폐회   = 폐회일


def day_dates(retreat: Retreat) -> dict[str, dt.date]:
    """일자 이름 → 날짜. 개회일이 없으면 빈 값을 돌려준다."""
    start, end = retreat.start_date, retreat.end_date
    if start is None:
        return {}
    end = end or start
    if end < start:
        end = start
    out = {"선발대": start - dt.timedelta(days=1)}
    span = (end - start).days
    for offset in range(span):
        out[f"{offset + 1}일차"] = start + dt.timedelta(days=offset)
    out["폐회"] = end
    return out


def day_names(retreat: Retreat, programs: list[Program] | None = None) -> list[str]:
    """화면에 그릴 일자 순서.

    회차에서 계산한 목록이 기본이되, 그 목록에 없는 이름으로 프로그램이 들어와
    있으면 **버리지 않고 뒤에 붙입니다** — 회차 기간이 줄어들었을 때 그 날의
    프로그램이 조용히 사라지면 아무도 알아차리지 못합니다.
    """
    names = list(day_dates(retreat))
    for program in programs or []:
        if program.day not in names:
            names.append(program.day)
    return names


def label_of(name: str, date: dt.date | None) -> str:
    """'8/22(토)' — 일자 탭의 윗줄."""
    if date is None:
        return name
    weekday = "월화수목금토일"[date.weekday()]
    return f"{date.month}/{date.day}({weekday})"


# ── 상태 ─────────────────────────────────────────────────────────────


def _minutes(hhmm: str | None) -> int:
    """'15:20' → 920. 못 읽으면 하루 끝으로 본다(아직 시작 안 한 것으로)."""
    try:
        hour, _, minute = (hhmm or "").partition(":")
        return int(hour) * 60 + int(minute)
    except ValueError:
        return 24 * 60


def program_state(
    program: Program,
    following: Program | None,
    *,
    day_date: dt.date | None,
    now: dt.datetime,
) -> str:
    """'done' | 'live' | 'todo'.

    **저장된 값이 아니라 시각에서 계산합니다.** 4-10 에서 기한 초과를 날짜로
    계산하기로 한 것과 같은 이유입니다 — 아무도 누르지 않아도 시스템이
    알아차려야 합니다. 현장에서는 상태를 눌러 줄 사람이 특히 없습니다.
    """
    if day_date is None:
        return "todo"
    today = now.date()
    if day_date < today:
        return "done"
    if day_date > today:
        return "todo"
    minute_now = now.hour * 60 + now.minute
    if following is not None and _minutes(following.start_time) <= minute_now:
        return "done"
    if _minutes(program.start_time) <= minute_now:
        return "live"
    return "todo"


def has_started(state: str) -> bool:
    """시작했는가 — 진행 중이거나 이미 지났으면 시작한 것이다."""
    return state in ("live", "done")


def late_items(program: Program, state: str) -> list[ProgramItem]:
    """`지연` 이 붙을 준비(전) 항목.

    5-2: "프로그램이 이미 시작됐는데 준비 항목이 안 끝났으면 지연 배지가 붙습니다."
    **진행 중일 때만이 아니라 이미 지나간 것도 봅니다** — 지나갔는데 준비가
    안 끝난 것은 더 나쁜 상태지 덜 나쁜 상태가 아닙니다.
    """
    if not has_started(state):
        return []
    return [i for i in program.items if i.phase == "pre" and not i.done]


def leftover_post(program: Program, state: str) -> list[ProgramItem]:
    """끝났는데 남아 있는 정리(후) 항목.

    5-2 가 "정리 항목이 특히 중요하다 — 다음 프로그램 준비와 겹치면 누락된다"고
    적은 자리입니다. **다음 프로그램으로 넘어가면 앞 프로그램의 정리 항목은
    화면에서 사라지는데, 그것이 정확히 누락이 생기는 지점입니다.** 그래서
    왼쪽 목록에서도 보이게 합니다.
    """
    if state != "done":
        return []
    return [i for i in program.items if i.phase == "post" and not i.done]


def counts(program: Program) -> tuple[int, int]:
    """(완료, 전체)."""
    items = program.items
    return sum(1 for i in items if i.done), len(items)


def day_progress(programs: list[Program]) -> tuple[int, int]:
    """그 날 전체의 (완료, 전체). 진행률은 실제 체크 수에서 계산한다."""
    done = total = 0
    for program in programs:
        c, t = counts(program)
        done += c
        total += t
    return done, total


def carried_only(retreat: Retreat, programs: list[Program], *, now: dt.datetime) -> bool:
    """프로그램표만 옮겨 왔고 체크는 하나도 없는 **종료된** 회차인가.

    지난 회차에 프로그램표만 있고 체크가 하나도 없으면 화면이 "아무것도 안 했다"로
    읽힙니다. 실제로는 다 했는데 **그때 이 시스템이 없었을 뿐**입니다.
    없는 기록을 지어내지도 않고(6-9), 안 한 것처럼 보이게 두지도 않습니다 —
    진행률 대신 그 사정을 한 줄로 적습니다.

    판단 근거는 **종료된 회차 + 체크 0건** 뿐입니다. 회차에 표시를 따로 달지
    않습니다 — 표시를 달면 누군가 그것을 켜고 꺼야 하고, 안 켜면 또 조용히 틀립니다.

    체크는 **회차 전체**로 셉니다. 그 날만 보면 진행 중인 회차에서 아직 아무도
    누르지 않은 날이 같은 문구를 달게 됩니다.
    """
    if not programs:
        return False
    closing = retreat.end_date or retreat.start_date
    ended = bool(getattr(retreat, "is_archived", False)) or bool(
        closing and closing < now.date()
    )
    if not ended:
        return False
    return not any(item.done for program in programs for item in program.items)


def parts_in(programs: list[Program]) -> list[str]:
    """그 날 실제로 쓰인 파트만. 정해진 순서를 지키고 모르는 값은 뒤에 붙인다."""
    used = {i.part_key for p in programs for i in p.items if i.part_key}
    ordered = [k for k in PROGRAM_PARTS if k in used]
    ordered += sorted(used - set(PROGRAM_PARTS))
    return ordered


def scopes_in(programs: list[Program]) -> list[str]:
    """그 날 실제로 쓰인 범위만. 한쪽만 있으면 칩을 낼 이유가 없다."""
    used = {i.scope_key for p in programs for i in p.items}
    return [k for k in ("team", "person") if k in used]


def default_part(department_key: str | None, available: list[str]) -> str:
    """내 부서와 맞는 파트를 기본으로 잡는다. 없으면 전체."""
    part = DEPARTMENT_PART.get(department_key or "")
    return part if part and part in available else ALL_PARTS


# ── 화면에 넘길 묶음 ──────────────────────────────────────────────────


def load_programs(db: Session, retreat: Retreat) -> list[Program]:
    return list(
        db.scalars(
            select(Program)
            .where(Program.retreat_id == retreat.id)
            .order_by(Program.start_time, Program.sort_order, Program.id)
        )
    )


def build(
    db: Session,
    retreat: Retreat,
    *,
    now: dt.datetime,
    day: str | None = None,
    department_key: str | None = None,
) -> dict:
    """진행 화면 한 판.

    `now` 를 반드시 받습니다 — 한 판을 그리는 동안 모든 계산이 같은 '지금'을
    봐야 합니다. 중간에 자정을 넘기면 일자 탭과 NOW 선이 어긋납니다.
    """
    programs = load_programs(db, retreat)
    dates = day_dates(retreat)
    names = day_names(retreat, programs)
    by_day: dict[str, list[Program]] = {name: [] for name in names}
    for program in programs:
        by_day.setdefault(program.day, []).append(program)

    today = now.date()
    # 오늘이 회차 기간 안이면 그 날, 아니면 첫 날 (5 — 화면이 죽지 않아야 한다)
    today_name = next((n for n in names if dates.get(n) == today), None)
    if day not in by_day:
        day = today_name or (names[0] if names else None)

    rows = by_day.get(day, []) if day else []
    day_date = dates.get(day) if day else None
    # 종료된 회차 + 체크 0건 (5-6). 아래 판정들이 이 값을 본다.
    carried = carried_only(retreat, programs, now=now)

    programs_view = []
    live_index = None
    for index, program in enumerate(rows):
        following = rows[index + 1] if index + 1 < len(rows) else None
        state = program_state(program, following, day_date=day_date, now=now)
        done, total = counts(program)
        # 시스템 밖에서 진행한 회차에는 `지연` 도 `정리 N건 남음` 도 붙이지 않는다.
        # 둘 다 "안 끝났다"는 말인데, 그 회차는 안 끝난 게 아니라 **누른 적이 없는**
        # 것이다. 위에 그 사정을 적어 놓고 아래를 빨갛게 덮으면 한 화면이 서로를
        # 부정한다 — 4-10 에서 완료와 연쇄 경고를 함께 내지 않기로 한 것과 같다.
        late = [] if carried else late_items(program, state)
        leftover = [] if carried else leftover_post(program, state)
        if state == "live" and live_index is None:
            live_index = index
        programs_view.append(
            {
                "id": program.id,
                "start_time": program.start_time,
                "name": program.name,
                "host": program.host,
                "place": program.place,
                "note": program.note,
                "end_time": program.end_time,
                # 이 셋이 봉사자 시간표에서 어느 칸에 어떻게 서는지를 정한다 (5-8)
                "audience": program.audience_key,
                "track": program.track_key,
                "parallel": program.is_parallel,
                "state": state,
                "done": done,
                "total": total,
                "late": len(late),
                "leftover_post": len(leftover),
                "items": [item_view(i) for i in program.items],
            }
        )

    # 열면 진행 중인 프로그램이 자동 선택된다 (5-1).
    # 진행 중인 것이 없으면(기간 밖이거나 사이 시간) 첫 프로그램.
    selected = live_index if live_index is not None else (0 if programs_view else None)

    done_count, total_count = day_progress(rows)
    available = parts_in(rows)
    return {
        "days": [
            {
                "name": name,
                "label": label_of(name, dates.get(name)),
                "date": dates[name].isoformat() if name in dates else None,
                "count": len(by_day.get(name, [])),
                "is_today": dates.get(name) == today,
            }
            for name in names
        ],
        "day": day,
        "day_date": day_date.isoformat() if day_date else None,
        "is_today": day_date == today,
        "now": now.strftime("%H:%M"),
        "programs": programs_view,
        "selected": selected,
        "progress": {
            "done": done_count,
            "total": total_count,
            "percent": round(done_count / total_count * 100) if total_count else 0,
        },
        "carried_only": carried,
        "parts": available,
        "default_part": default_part(department_key, available),
        "scopes": scopes_in(rows),
    }


def item_view(item: ProgramItem) -> dict:
    return {
        "id": item.id,
        "phase": item.phase,
        # ALTER 로 붙은 컬럼이라 기존 행은 NULL 이다 — 읽는 자리는 늘 scope_key
        "scope": item.scope_key,
        "part": item.part_key,
        "assignee": item.assignee_name or "",
        "text": item.text,
        "done": item.done,
        "done_at": item.done_at.strftime("%H:%M") if item.done_at else None,
        "done_by": item.done_by.name if item.done_by else None,
    }


# ── 지난 회차에서 복사해 오기 (5-5) ──────────────────────────────────


def copy_programs(db: Session, *, source: Retreat, target: Retreat) -> int:
    """지난 회차의 프로그램표를 통째로 가져온다.

    **체크 상태는 가져오지 않습니다** — 지난 회차의 사실이지 이번 회차의 것이
    아닙니다. 논의 내역이 접힌 채로 따라오고 진행 상태는 전부 대기로 돌아가는
    것(6-10)과 같은 원칙입니다.

    날짜는 저장하지 않으므로 옮길 것이 없습니다 — `day` 이름만 따라가고
    실제 날짜는 새 회차의 개회일에서 다시 계산됩니다.
    """
    existing = load_programs(db, target)
    for program in existing:
        db.delete(program)
    db.flush()

    copied = 0
    for program in load_programs(db, source):
        fresh = Program(
            retreat_id=target.id,
            day=program.day,
            start_time=program.start_time,
            name=program.name,
            host=program.host,
            place=program.place,
            note=program.note,
            # **셋을 빠뜨리면 안 된다.** 이것들이 봉사자 시간표에서 어느 칸에
            # 어떻게 서는지를 정한다(5-8). 안 옮기면 복사해 온 회차의 표가
            # 통째로 틀리는데, 값이 기본값으로 채워져 **아무 오류도 나지 않는다.**
            audience=program.audience_key,
            track=program.track_key,
            parallel=program.is_parallel,
            end_time=program.end_time,
            sort_order=program.sort_order,
        )
        db.add(fresh)
        db.flush()
        for item in program.items:
            db.add(
                ProgramItem(
                    program_id=fresh.id,
                    phase=item.phase,
                    part_key=item.part_key,
                    assignee_name=item.assignee_name,
                    text=item.text,
                    sort_order=item.sort_order,
                    # done_at · done_by_id 는 옮기지 않는다
                )
            )
        copied += 1
    db.flush()
    return copied


def valid_phase(phase: str) -> bool:
    return phase in PROGRAM_PHASES
