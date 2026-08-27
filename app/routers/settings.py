"""회차 / 부서 / 사용자 관리 (총무팀 전용) + 내 정보."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import DEFAULT_MEAL_SUBSIDY_PER_PERSON
from app.db import get_db
from app.deps import all_retreats, get_current_retreat, log_activity, remember_retreat
from app.domain.auth import normalize_phone
from app.domain.clone import clone_retreat
from app.domain.permissions import ALL_ROLES
from app.models import ActivityLog, Department, ExpenseEntry, Retreat, Task, User
from app.security import get_current_user, require_admin
from app.templating import redirect, render

router = APIRouter()


def _parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    return dt.date.fromisoformat(raw)


@router.get("/settings")
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    retreats = all_retreats(db)
    retreat = get_current_retreat(request, db, user) if retreats else None
    departments = (
        list(
            db.scalars(
                select(Department)
                .where(Department.retreat_id == retreat.id)
                .order_by(Department.sort_order, Department.id)
            )
        )
        if retreat
        else []
    )
    return render(
        request,
        "settings.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": retreats,
            "departments": departments,
            "users": list(db.scalars(select(User).order_by(User.name))),
            "roles": ALL_ROLES,
            "logs": list(
                db.scalars(
                    select(ActivityLog)
                    .where(ActivityLog.retreat_id == (retreat.id if retreat else None))
                    .order_by(ActivityLog.id.desc())
                    .limit(30)
                )
            ),
            "default_cap": DEFAULT_MEAL_SUBSIDY_PER_PERSON,
        },
    )


@router.post("/retreats/create")
def create_retreat(
    name: str = Form(...),
    start_date: str = Form(""),
    end_date: str = Form(""),
    meal_subsidy_per_person: int = Form(DEFAULT_MEAL_SUBSIDY_PER_PERSON),
    clone_from: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if clone_from:
        source = db.get(Retreat, int(clone_from))
        if source is None:
            raise HTTPException(status_code=404, detail="복제할 회차를 찾을 수 없습니다.")
        retreat = clone_retreat(
            db,
            source=source,
            name=name.strip(),
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
        )
        retreat.meal_subsidy_per_person = max(0, meal_subsidy_per_person)
        db.commit()
        summary = f"{retreat.name} ('{source.name}' 복제)"
    else:
        retreat = Retreat(
            name=name.strip(),
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            meal_subsidy_per_person=max(0, meal_subsidy_per_person),
        )
        db.add(retreat)
        db.commit()
        summary = retreat.name

    remember_retreat(db, user, retreat)
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="회차_생성",
        target_type="retreat",
        target_id=retreat.id,
        summary=summary,
    )
    return redirect(f"/settings?retreat_id={retreat.id}", message=f"'{retreat.name}' 회차를 만들었습니다.")


@router.post("/retreats/{retreat_id}/update")
def update_retreat(
    retreat_id: int,
    name: str = Form(...),
    start_date: str = Form(""),
    end_date: str = Form(""),
    meal_subsidy_per_person: int = Form(DEFAULT_MEAL_SUBSIDY_PER_PERSON),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    retreat = db.get(Retreat, retreat_id)
    if retreat is None:
        raise HTTPException(status_code=404, detail="회차를 찾을 수 없습니다.")

    before = {
        "name": retreat.name,
        "meal_subsidy_per_person": retreat.meal_subsidy_per_person,
    }
    retreat.name = name.strip()
    retreat.start_date = _parse_date(start_date)
    retreat.end_date = _parse_date(end_date)
    retreat.meal_subsidy_per_person = max(0, meal_subsidy_per_person)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="회차_수정",
        target_type="retreat",
        target_id=retreat.id,
        summary=retreat.name,
        before_value=before,
        after_value={
            "name": retreat.name,
            "meal_subsidy_per_person": retreat.meal_subsidy_per_person,
        },
    )
    return redirect(
        f"/settings?retreat_id={retreat.id}",
        message="회차 설정을 저장했습니다. (식대 상한은 앞으로 등록되는 지출에 적용됩니다)",
    )


@router.post("/departments/create")
def create_department(
    name: str = Form(...),
    color_tag: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    max_order = (
        db.scalar(
            select(func.max(Department.sort_order)).where(
                Department.retreat_id == retreat.id
            )
        )
        or 0
    )
    dept = Department(
        retreat_id=retreat.id,
        name=name.strip(),
        color_tag=color_tag.strip() or None,
        sort_order=max_order + 1,
    )
    db.add(dept)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="부서_생성",
        target_type="department",
        target_id=dept.id,
        summary=dept.name,
    )
    return redirect(f"/settings?retreat_id={retreat.id}", message="부서를 추가했습니다.")


@router.post("/departments/{department_id}/delete")
def delete_department(
    department_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    dept = db.get(Department, department_id)
    if dept is None or dept.retreat_id != retreat.id:
        raise HTTPException(status_code=404, detail="부서를 찾을 수 없습니다.")

    task_count = db.scalar(
        select(func.count()).select_from(Task).where(Task.department_id == department_id)
    )
    expense_count = db.scalar(
        select(func.count())
        .select_from(ExpenseEntry)
        .where(ExpenseEntry.department_id == department_id)
    )
    name = dept.name
    db.delete(dept)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="부서_삭제",
        target_type="department",
        target_id=department_id,
        summary=f"{name} (연결된 할일 {task_count}건·지출 {expense_count}건은 부서 미지정으로 남습니다)",
    )
    return redirect(f"/settings?retreat_id={retreat.id}", message=f"'{name}' 부서를 삭제했습니다.")


@router.post("/users/create")
def create_user(
    name: str = Form(...),
    phone_number: str = Form(...),
    role: str = Form("member"),
    department_id: str = Form(""),
    bank_account: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    if role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail="알 수 없는 역할입니다.")
    try:
        phone = normalize_phone(phone_number)
    except ValueError as exc:
        return redirect(f"/settings?retreat_id={retreat.id}", message=str(exc))

    if db.scalars(select(User).where(User.phone_number == phone)).first():
        return redirect(
            f"/settings?retreat_id={retreat.id}", message="이미 등록된 전화번호입니다."
        )

    member = User(
        name=name.strip(),
        phone_number=phone,
        role=role,
        department_id=int(department_id) if department_id else None,
        bank_account=bank_account.strip() or None,
    )
    db.add(member)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="사용자_등록",
        target_type="user",
        target_id=member.id,
        summary=f"{member.name} ({role})",
    )
    return redirect(f"/settings?retreat_id={retreat.id}", message=f"{member.name}님을 등록했습니다.")


@router.post("/users/{user_id}/update")
def update_user(
    user_id: int,
    role: str = Form(...),
    department_id: str = Form(""),
    is_active: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    retreat: Retreat = Depends(get_current_retreat),
):
    member = db.get(User, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail="알 수 없는 역할입니다.")

    if member.id == user.id and role != "admin":
        return redirect(
            f"/settings?retreat_id={retreat.id}",
            message="본인의 관리자 권한은 해제할 수 없습니다. 다른 관리자에게 요청해주세요.",
        )

    before = {"role": member.role, "department_id": member.department_id}
    member.role = role
    member.department_id = int(department_id) if department_id else None
    member.is_active = bool(is_active)
    db.commit()
    log_activity(
        db,
        retreat_id=retreat.id,
        actor=user,
        action="사용자_수정",
        target_type="user",
        target_id=member.id,
        summary=member.name,
        before_value=before,
        after_value={"role": member.role, "department_id": member.department_id},
    )
    return redirect(f"/settings?retreat_id={retreat.id}", message="사용자 정보를 수정했습니다.")


@router.post("/me/update")
def update_me(
    name: str = Form(...),
    bank_account: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user.name = name.strip() or user.name
    user.bank_account = bank_account.strip() or None
    db.commit()
    return redirect("/settings", message="내 정보를 저장했습니다.")
