"""계정 관리 (CLAUDE.md 4-12).

총무팀이 사람을 등록하고 초대 링크를 발급하는 자리. 지금까지는 seed 로만
계정을 만들 수 있었는데, 그러면 매 회차 담당자가 바뀔 때마다 코드를 고쳐야 한다.

**삭제는 두지 않는다.** 지난 회차의 논의와 지출에 그 사람이 작성자로 남아
있으므로, 지우면 기록이 "누가 썼는지 모르는 것" 이 된다. 비활성화만 둔다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, log_activity, resolve_retreat
from app.domain import auth as invites
from app.domain.departments import DEPARTMENT_NAMES, department_key_of
from app.domain.permissions import ALL_ROLES, ROLE_LABELS
from app.models import Department, User
from app.security import require_admin
from app.templating import redirect, render

router = APIRouter()


def _department_choices(db: Session, retreat) -> list[dict]:
    """부서는 **키로** 고른다.

    Department 행은 회차마다 새로 만들어지므로 id 로 붙이면 새 회차에서 무너진다
    (CLAUDE.md 2장). 화면에서도 키를 값으로 쓴다.

    **현재 회차에 있는 부서만 낸다.** 모든 회차를 훑으면 해체된 부서(2장의
    '봉사팀 공통' 처럼)가 목록에 남는다. 행이 존재하니 저장은 되는데, 이번
    회차에 없는 부서라 그 사람은 아무 업무도 고치지 못한다 — 조용히 미지정으로
    떨어지는 것과 결과가 같고 검사도 통과한다.
    """
    if retreat is None:
        return []
    return [
        {"key": dept.key, "name": dept.name or DEPARTMENT_NAMES.get(dept.key, dept.key)}
        for dept in sorted(retreat.departments, key=lambda d: d.sort_order)
        if dept.key
    ]


def _department_row(db: Session, retreat, key: str | None) -> Department | None:
    """현재 회차에서 그 키의 Department 행."""
    if not key or retreat is None:
        return None
    return next((d for d in retreat.departments if d.key == key), None)


def _resolve_department(
    db: Session, retreat, key: str, *, keep_for: User | None = None
) -> tuple[Department | None, str | None]:
    """(부서 행, 사유). 없는 키는 **조용히 None 으로 떨어뜨리지 않는다.**

    `keep_for` 는 지금 그 사람이 붙어 있는 부서다. 값이 그대로면 **바꾸는 것이
    아니라 유지하는 것**이므로 통과시킨다 — 권한만 고치려고 저장했을 때 지난
    회차 소속이 조용히 지워지면 안 되기 때문이다. 새로 배정하는 것만 막는다.
    """
    if not key:
        return None, None
    if keep_for is not None and key == department_key_of(db, keep_for):
        return keep_for.department, None          # 그대로 둔다
    dept = _department_row(db, retreat, key)
    if dept is None:
        name = DEPARTMENT_NAMES.get(key, key)
        if retreat is None:
            return None, (
                f"아직 회차가 없어 '{name}' 을(를) 배정할 수 없습니다. "
                "회차를 먼저 만들어주세요."
            )
        return None, (
            f"'{name}' 은(는) 이번 회차({retreat.name})에 없는 부서라 배정할 수 없습니다. "
            "회차에 그 부서를 넣은 뒤에 다시 지정해주세요."
        )
    return dept, None


@router.get("/admin/users")
def users_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    retreat = resolve_retreat(db, user, None)
    choices = _department_choices(db, retreat)
    live_keys = {c["key"] for c in choices}

    rows = []
    for person in db.scalars(select(User).order_by(User.is_active.desc(), User.name)):
        token = invites.live_token(db, user=person)
        key = department_key_of(db, person)
        rows.append(
            {
                "id": person.id,
                "name": person.name,
                "phone": person.phone_number,
                "role": person.role,
                "role_label": ROLE_LABELS.get(person.role, person.role),
                "department_key": key,
                # 지난 회차 부서에 붙어 있는 계정은 **건드리지 않는다.**
                # 조용히 바꾸거나 지우지 않고, 그렇다는 것만 보여준다.
                "department_stale": bool(key) and key not in live_keys,
                "department_name": DEPARTMENT_NAMES.get(key, key) if key else None,
                "is_active": person.is_active,
                "invite_live": token is not None,
                "invite_expires": token.expires_at.date().isoformat() if token else None,
            }
        )

    return render(
        request,
        "admin_users.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "rows": rows,
            "departments": choices,
            "roles": [{"value": r, "label": ROLE_LABELS.get(r, r)} for r in ALL_ROLES],
            "active_tab": None,
            "page_subtitle": "계정 관리",
            # 원문은 URL 을 타지 않는다. 한 번만 꺼내지는 자리에서 가져온다.
            "issued": invites.take(request.query_params.get("k")),
            "no_departments": not choices,
        },
    )


@router.post("/admin/users/new")
def create_user(
    name: str = Form(...),
    phone_number: str = Form(...),
    role: str = Form("member"),
    department_key: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    name = name.strip()
    phone = "".join(ch for ch in phone_number if ch.isdigit())
    if not name:
        return redirect("/admin/users", message="이름을 입력해주세요.")
    if not phone:
        return redirect("/admin/users", message="연락처를 입력해주세요.")
    if role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail="알 수 없는 권한입니다.")
    if db.scalars(select(User).where(User.phone_number == phone)).first():
        return redirect("/admin/users", message="이미 등록된 연락처입니다.")

    dept, problem = _resolve_department(db, resolve_retreat(db, user, None), department_key)
    if problem:
        return redirect("/admin/users", message=problem)

    person = User(
        name=name,
        phone_number=phone,
        role=role,
        department_id=dept.id if dept else None,
    )
    db.add(person)
    db.commit()
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="계정_생성",
        target_type="user",
        target_id=person.id,
        summary=f"{name} ({ROLE_LABELS.get(role, role)})",
    )
    raw = invites.issue(db, user=person, actor=user)
    # 원문 대신 **한 번 쓰면 사라지는 키**만 싣는다 — 주소창·방문 기록·접속 로그
    # 어디에도 링크가 남지 않게 하기 위해서다.
    return redirect(f"/admin/users?k={invites.stash(raw)}")


@router.post("/admin/users/{user_id}/update")
def update_user(
    user_id: int,
    role: str = Form(...),
    department_key: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    if role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail="알 수 없는 권한입니다.")

    dept, problem = _resolve_department(
        db, resolve_retreat(db, user, None), department_key, keep_for=person
    )
    if problem:
        return redirect("/admin/users", message=problem)

    before = {"role": person.role, "department_key": department_key_of(db, person)}
    person.role = role
    person.department_id = dept.id if dept else None
    db.commit()
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="계정_변경",
        target_type="user",
        target_id=person.id,
        summary=f"{person.name}: {before['role']} → {role}",
        before_value=before,
        after_value={"role": role, "department_key": department_key or None},
    )
    return redirect("/admin/users", message=f"{person.name} 님의 설정을 바꿨습니다.")


@router.post("/admin/users/{user_id}/invite")
def issue_invite(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """새 링크를 발급한다. 남아 있던 링크는 함께 취소된다."""
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    raw = invites.issue(db, user=person, actor=user)
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="초대_링크_발급",
        target_type="user",
        target_id=person.id,
        summary=f"{person.name} 님의 초대 링크를 발급했습니다.",
    )
    return redirect(f"/admin/users?k={invites.stash(raw)}")


@router.post("/admin/users/{user_id}/revoke")
def revoke_invite(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    count = invites.revoke_all(db, user=person)
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="초대_링크_취소",
        target_type="user",
        target_id=person.id,
        summary=f"{person.name} 님의 링크 {count}건을 취소했습니다.",
    )
    return redirect("/admin/users", message=f"{person.name} 님의 링크를 취소했습니다.")


@router.post("/admin/users/{user_id}/active")
def set_active(
    user_id: int,
    active: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """비활성화·복구. **삭제는 없다** — 지난 회차 기록의 작성자가 사라지면 안 된다."""
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    if person.id == user.id:
        return redirect("/admin/users", message="자기 계정은 비활성화할 수 없습니다.")

    person.is_active = active == "on"
    if not person.is_active:
        invites.revoke_all(db, user=person)
    db.commit()
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="계정_활성_변경",
        target_type="user",
        target_id=person.id,
        summary=f"{person.name}: {'활성' if person.is_active else '비활성'}",
    )
    return redirect(
        "/admin/users",
        message=f"{person.name} 님을 {'다시 활성화' if person.is_active else '비활성화'}했습니다.",
    )
