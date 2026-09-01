"""수련회 진행 화면 (CLAUDE.md 5장).

**체크는 로그인한 사람 누구나 합니다.** 현장에서는 옆 사람 것도 대신 눌러야
하고, 손이 비는 사람이 누르는 것이 맞습니다. 누가 눌렀는지는 `done_by_id` 로
남기므로 나중에 확인할 수 있습니다.

**프로그램과 항목을 만들고 고치는 것은 총무팀만** 합니다 — 그건 현장에서
급히 하는 일이 아니라 미리 짜 두는 일입니다.
"""

from __future__ import annotations

import datetime as dt
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.domain import live as live_domain
from app.domain import staff_sheet as sheet_domain
from app.domain import permissions as perm
from app.domain.departments import department_key_of
from app.models import (
    AUDIENCE_HINTS,
    AUDIENCE_LABELS,
    PARALLEL_HINT,
    PROGRAM_AUDIENCES,
    PROGRAM_DAYS,
    PROGRAM_PARTS,
    PROGRAM_SCOPES,
    PROGRAM_TRACKS,
    TEAM_WORDS,
    TRACK_HINTS,
    TRACK_LABELS,
    Program,
    ProgramItem,
    Retreat,
    User,
)
from app.security import get_current_user
from app.templating import redirect, render

router = APIRouter()


def _now() -> dt.datetime:
    return dt.datetime.now()


def _require_admin(user: User) -> None:
    if not perm.can_manage_retreat(user.role):
        raise HTTPException(status_code=403, detail="총무팀만 프로그램표를 고칠 수 있습니다.")


def _owned_program(db: Session, retreat: Retreat, program_id: int) -> Program:
    program = db.get(Program, program_id)
    if program is None or program.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="프로그램을 찾을 수 없습니다.")
    return program


def _owned_item(db: Session, retreat: Retreat, item_id: int) -> ProgramItem:
    item = db.get(ProgramItem, item_id)
    if item is None or item.program.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    return item


@router.get("/live")
def live_page(
    request: Request,
    day: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    my_key = department_key_of(db, user)
    # 헤브론·코람데오 소속이면 봉사팀 보기가 기본으로 열린다 (5-8).
    # 총무팀은 이 화면이 기본이고 위의 탭으로 건너간다.
    is_team = live_domain.DEPARTMENT_PART.get(my_key or "") in live_domain.TEAM_PARTS
    if is_team and request.query_params.get("stay") is None:
        return redirect("/live/staff")

    view = live_domain.build(
        db,
        retreat,
        now=_now(),
        day=day,
        department_key=my_key,
    )
    return render(
        request,
        "live.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "live": view,
            "can_manage": perm.can_manage_retreat(user.role),
            # 복사해 올 수 있는 지난 회차 — 프로그램표가 실제로 있는 것만
            "sources": _copy_sources(db, retreat),
            "day_names": PROGRAM_DAYS,
            "part_names": PROGRAM_PARTS,
            # 프로그램을 만들 때 고르는 셋 (5-1). **뜻을 함께 넘긴다** —
            # `staff` 를 보고 무엇인지 아는 사람은 이걸 만든 사람뿐이다
            "audiences": [
                {"value": v, "label": AUDIENCE_LABELS[v], "hint": AUDIENCE_HINTS[v]}
                for v in PROGRAM_AUDIENCES
            ],
            "tracks": [
                {"value": v, "label": TRACK_LABELS[v], "hint": TRACK_HINTS[v]}
                for v in PROGRAM_TRACKS
            ],
            "parallel_hint": PARALLEL_HINT,
            # 새 항목의 범위를 추측하는 데 쓴다. 추측이지 규칙이 아니라
            # 사용자가 바꿀 수 있다 (5-2)
            "team_parts": sorted(live_domain.TEAM_PARTS),
            "team_words": sorted(TEAM_WORDS),
            # 헤브론·코람데오 소속이면 봉사팀 보기가 기본이다 (5-8)
            "staff_default": live_domain.DEPARTMENT_PART.get(
                department_key_of(db, user) or ""
            ) in live_domain.TEAM_PARTS,
            "active_tab": "live",
            "page_subtitle": "수련회 진행",
        },
    )


# ── 봉사팀 보기 (5-8) ────────────────────────────────────────────────
#
# **로그인한 사람 누구나 본다** — 봉사팀도 총무팀도. 봉사팀이 직접 받아 갈 수
# 있어야 총무팀을 거치지 않는다.


@router.get("/live/staff")
def staff_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    return render(
        request,
        "staff_sheet.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            # 화면과 파일이 **같은 함수에서 나온 같은 구조**를 쓴다 (5-8)
            "sheet": sheet_domain.build(db, retreat),
            "active_tab": "live",
            "page_subtitle": "봉사팀 보기",
        },
    )


@router.get("/live/staff.xlsx")
def staff_download(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """엑셀로 내려받기. **로그인한 사람 누구나.**"""
    from fastapi.responses import Response

    from app.domain import staff_xlsx

    sheet = sheet_domain.build(db, retreat)
    try:
        blob = staff_xlsx.write(sheet)
    except staff_xlsx.SheetBroken as exc:
        # 손상된 파일을 내주지 않는다
        raise HTTPException(status_code=500, detail=str(exc)) from None

    name = urllib.parse.quote(f"{retreat.name}_봉사자시간표.xlsx")
    return Response(
        blob,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"},
    )


def _copy_sources(db: Session, retreat: Retreat) -> list[dict]:
    """프로그램표를 가진 다른 회차. 비어 있는 회차를 고르게 두면 헛수고가 된다."""
    rows = []
    for other in all_retreats(db):
        if other.id == retreat.id:
            continue
        count = db.scalar(
            select(Program.id).where(Program.retreat_id == other.id).limit(1)
        )
        if count:
            total = len(live_domain.load_programs(db, other))
            rows.append({"id": other.id, "name": other.name, "count": total})
    return rows


@router.get("/live/data")
def live_data(
    day: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """화면이 다시 그릴 때 쓰는 것. 판정은 서버에서만 한다."""
    return live_domain.build(
        db, retreat, now=_now(), day=day,
        department_key=department_key_of(db, user),
    )


# ── 체크 ─────────────────────────────────────────────────────────────


class CheckIn(BaseModel):
    done: bool


@router.post("/live/item/{item_id}/check")
def check_item(
    item_id: int,
    payload: CheckIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """체크는 로그인한 사람 누구나. 현장에서 옆 사람 것도 대신 눌러야 한다."""
    item = _owned_item(db, retreat, item_id)
    if payload.done:
        # 이미 눌려 있으면 시각을 덮어쓰지 않는다 — 처음 누른 때가 사실이다
        if item.done_at is None:
            item.done_at = _now()
            item.done_by_id = user.id
    else:
        item.done_at = None
        item.done_by_id = None
    db.commit()
    db.refresh(item)
    program = item.program
    done, total = live_domain.counts(program)
    return {
        "item": live_domain.item_view(item),
        "program": {"id": program.id, "done": done, "total": total},
    }


# ── 프로그램표 짜기 (총무팀) ──────────────────────────────────────────


class ProgramIn(BaseModel):
    day: str
    start_time: str
    name: str
    host: str | None = None
    place: str | None = None
    note: str | None = None
    end_time: str | None = None
    # 셋이 봉사자 시간표에서 이 프로그램이 어느 칸에 어떻게 서는지를 정합니다
    # (5-8). **기본은 가장 흔한 경우** — 참가자와 함께하는 정규일정입니다.
    audience: str = "all"
    track: str = "main"
    parallel: bool = False


def _check_choice(value: str, allowed: tuple[str, ...], label: str) -> str:
    """정해진 값 중 하나인가. **모르는 값을 조용히 기본값으로 바꾸지 않습니다** —
    그러면 화면에서 고른 것과 저장된 것이 달라지는데 아무 표시도 나지 않습니다."""
    if value not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"{label} 값이 올바르지 않습니다: {value}",
        )
    return value


def _check_time(value: str) -> str:
    raw = (value or "").strip()
    try:
        hour, _, minute = raw.partition(":")
        if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="시각은 09:30 처럼 적어주세요.") from None
    return f"{int(hour):02d}:{int(minute):02d}"


@router.post("/live/program")
def create_program(
    payload: ProgramIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    _require_admin(user)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="프로그램 이름을 적어주세요.")
    program = Program(
        retreat_id=retreat.id,
        day=payload.day.strip(),
        start_time=_check_time(payload.start_time),
        name=payload.name.strip(),
        host=(payload.host or "").strip() or None,
        place=(payload.place or "").strip() or None,
        note=(payload.note or "").strip() or None,
        end_time=_check_time(payload.end_time) if payload.end_time else None,
        audience=_check_choice(payload.audience, PROGRAM_AUDIENCES, "참가"),
        track=_check_choice(payload.track, PROGRAM_TRACKS, "구분"),
        parallel=bool(payload.parallel),
        sort_order=len(live_domain.load_programs(db, retreat)),
    )
    db.add(program)
    db.commit()
    log_activity(
        db, retreat_id=retreat.id, actor=user, action="프로그램 추가",
        target_type="program", target_id=program.id,
        after_value={"day": program.day, "name": program.name},
    )
    return {"id": program.id}


@router.post("/live/program/{program_id}")
def update_program(
    program_id: int,
    payload: ProgramIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    _require_admin(user)
    program = _owned_program(db, retreat, program_id)
    program.day = payload.day.strip()
    program.start_time = _check_time(payload.start_time)
    program.name = payload.name.strip() or program.name
    program.host = (payload.host or "").strip() or None
    program.place = (payload.place or "").strip() or None
    program.note = (payload.note or "").strip() or None
    program.end_time = (
        _check_time(payload.end_time) if payload.end_time else None
    )
    program.audience = _check_choice(payload.audience, PROGRAM_AUDIENCES, "참가")
    program.track = _check_choice(payload.track, PROGRAM_TRACKS, "구분")
    program.parallel = bool(payload.parallel)
    db.commit()
    log_activity(
        db, retreat_id=retreat.id, actor=user, action="프로그램 수정",
        target_type="program", target_id=program.id,
        after_value={"day": program.day, "name": program.name,
                     "audience": program.audience_key,
                     "track": program.track_key,
                     "parallel": program.is_parallel},
    )
    return {"id": program.id}


@router.post("/live/program/{program_id}/delete")
def delete_program(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    _require_admin(user)
    program = _owned_program(db, retreat, program_id)
    name = program.name
    db.delete(program)
    db.commit()
    log_activity(
        db, retreat_id=retreat.id, actor=user, action="프로그램 삭제",
        target_type="program", target_id=program_id, before_value={"name": name},
    )
    return {"ok": True}


class ItemIn(BaseModel):
    phase: str
    part_key: str
    assignee_name: str | None = None
    text: str
    # 팀이 통째로 움직이는가, 개인에게 붙는가 (5-2).
    # 비워 두면 파트·담당으로 추측한다 — 추측이지 규칙이 아니다.
    scope: str | None = None


@router.post("/live/program/{program_id}/item")
def create_item(
    program_id: int,
    payload: ItemIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    _require_admin(user)
    program = _owned_program(db, retreat, program_id)
    if not live_domain.valid_phase(payload.phase):
        raise HTTPException(status_code=400, detail="구간은 준비·진행·정리 중 하나입니다.")
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="할 일을 적어주세요.")
    part_key = (payload.part_key or "").strip() or "행정"
    assignee = (payload.assignee_name or "").strip() or None
    scope = (payload.scope or "").strip()
    if not scope:
        scope = live_domain.guess_scope(part_key, assignee)
    if scope not in PROGRAM_SCOPES:
        raise HTTPException(
            status_code=400,
            detail="범위는 team(팀 단위) · person(개인 단위) 중 하나입니다.",
        )
    item = ProgramItem(
        program_id=program.id,
        phase=payload.phase,
        part_key=part_key,
        assignee_name=assignee,
        text=payload.text.strip(),
        sort_order=len(program.items),
        scope=scope,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"item": live_domain.item_view(item)}


class ScopeIn(BaseModel):
    scope: str


@router.post("/live/item/{item_id}/scope")
def set_scope(
    item_id: int,
    payload: ScopeIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """범위를 바꾼다. 넣을 때의 추측이 틀렸을 수 있어서 있는 길이다 (5-2)."""
    _require_admin(user)
    item = _owned_item(db, retreat, item_id)
    scope = (payload.scope or "").strip()
    if scope not in PROGRAM_SCOPES:
        raise HTTPException(
            status_code=400,
            detail="범위는 team(팀 단위) · person(개인 단위) 중 하나입니다.",
        )
    item.scope = scope
    db.commit()
    db.refresh(item)
    return {"item": live_domain.item_view(item)}


@router.post("/live/item/{item_id}/delete")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    _require_admin(user)
    item = _owned_item(db, retreat, item_id)
    db.delete(item)
    db.commit()
    return {"ok": True}


# ── 지난 회차에서 복사해 오기 (5-5) ──────────────────────────────────


class CopyIn(BaseModel):
    source_retreat_id: int


@router.post("/live/copy")
def copy_from(
    payload: CopyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """프로그램표는 매 회차 새로 만듭니다. 손으로 하나씩 넣게 두면 아무도 안 씁니다."""
    _require_admin(user)
    source = db.get(Retreat, payload.source_retreat_id)
    if source is None or source.id == retreat.id:
        raise HTTPException(status_code=400, detail="가져올 회차를 고르세요.")
    copied = live_domain.copy_programs(db, source=source, target=retreat)
    if not copied:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"{source.name} 에는 프로그램표가 없습니다.")
    db.commit()
    log_activity(
        db, retreat_id=retreat.id, actor=user, action="프로그램표 복사",
        target_type="retreat", target_id=retreat.id,
        after_value={"from": source.name, "programs": copied},
    )
    return {"copied": copied}
