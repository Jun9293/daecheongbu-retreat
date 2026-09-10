"""비품 (4-18) — 품목은 라이브러리(EquipmentItem), 수량·체크·위치는 회차별(EquipmentRun).

고칠 수 있는지는 `permissions.can_edit_department_key(user, item.team_key)` **하나**다 —
id 비교를 새로 심지 않는다(2장). 못 고치는 사람에게는 단추가 아예 안 나온다
(상태 칸에서 정한 그 자리 — 4-14). 지우는 길은 없다 — 「이번 회차 불필요」 는
`included` 를 끄는 것이고 행은 그 묶음 끝에 흐리게 남는다(0장).

라이브러리에는 있는데 이번 회차에 EquipmentRun 이 없는 품목을 담는 길은 아직
없다 — 회차가 하나뿐이라 그 화면이 한 번도 안 뜬다 (봐둘것 AO-b).
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity
from app.domain import permissions as perm
from app.models import Department, EquipmentItem, EquipmentRun, Retreat, User
from app.security import get_current_user
from app.templating import redirect, render

router = APIRouter(prefix="/equipment")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _run(db: Session, run_id: int, retreat: Retreat) -> EquipmentRun:
    run = db.get(EquipmentRun, run_id)
    if run is None or run.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="비품을 찾을 수 없습니다.")
    return run


def _gate(user: User, run: EquipmentRun) -> None:
    """부서는 키로 — 화면의 단추와 같은 판정이라 화면만 감춘 것이 아니다."""
    if not perm.can_edit_department_key(user, run.item.team_key):
        raise HTTPException(status_code=403, detail="내 부서의 비품만 고칠 수 있습니다.")


def groups_of(db: Session, retreat: Retreat) -> list[dict]:
    """묶음(팀 · group_name)별로 — 쓰는 것이 먼저, 「이번 회차 불필요」 는 묶음 끝에."""
    rows = db.execute(
        select(EquipmentRun, EquipmentItem)
        .join(EquipmentItem, EquipmentItem.id == EquipmentRun.item_id)
        .where(EquipmentRun.retreat_id == retreat.id)
        .order_by(EquipmentItem.team_key, EquipmentItem.group_name,
                  EquipmentRun.included.desc(), EquipmentRun.sort_order, EquipmentRun.id)
    ).all()
    depts = {d.key: d for d in db.scalars(
        select(Department).where(Department.retreat_id == retreat.id)) if d.key}
    groups: dict[tuple[str, str], dict] = {}
    for run, item in rows:
        key = (item.team_key, item.group_name)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"team_key": item.team_key, "dept": depts.get(item.team_key),
                               "name": item.group_name or "묶음 없음", "rows": [],
                               "checked": 0, "total": 0}
        g["rows"].append((run, item))
        if run.included:
            g["total"] += 1
            g["checked"] += 1 if run.checked else 0
    # 부서 순서(sort_order)로 — 키의 알파벳순이면 「부서 미지정」 이 맨 앞에 선다
    return sorted(groups.values(),
                  key=lambda g: (g["dept"].sort_order if g["dept"] else 999, g["team_key"], g["name"]))


@router.get("")
def equipment_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    return render(request, "equipment.html", {
        "user": user, "retreat": retreat, "retreats": all_retreats(db),
        "groups": groups_of(db, retreat),
        "active_tab": "equipment", "page_subtitle": "비품",
    })


@router.post("/{run_id}/toggle")
def toggle(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    run = _run(db, run_id, retreat)
    _gate(user, run)
    run.checked = not run.checked
    run.checked_by_id = user.id if run.checked else None
    run.checked_by_name = user.name if run.checked else None
    run.checked_at = _now() if run.checked else None
    db.commit()
    return redirect(f"/equipment?retreat_id={retreat.id}")


@router.post("/{run_id}/include")
def include(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    """「이번 회차 불필요」 ↔ 되살리기 — 행은 남는다 (0장)."""
    run = _run(db, run_id, retreat)
    _gate(user, run)
    run.included = not run.included
    db.commit()
    log_activity(db, retreat_id=retreat.id, actor=user,
                 action="비품_포함" if run.included else "비품_불필요",
                 target_type="equipment_run", target_id=run.id, summary=run.item.name)
    return redirect(f"/equipment?retreat_id={retreat.id}",
                    message="이번 회차에 다시 넣었습니다." if run.included else "이번 회차 불필요로 표시했습니다.")


@router.post("/{run_id}/edit")
def edit(
    run_id: int,
    quantity: str = Form(""),
    location: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    retreat: Retreat = Depends(get_current_retreat),
):
    run = _run(db, run_id, retreat)
    _gate(user, run)
    run.quantity = quantity.strip() or None
    run.location = location.strip() or None
    db.commit()
    return redirect(f"/equipment?retreat_id={retreat.id}")
