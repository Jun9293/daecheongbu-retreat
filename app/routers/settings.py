"""설정 — 탭 여섯 (CLAUDE.md 4-17).

내 정보 · 회차 관리는 누구나, 부서 · 사용자 · 업무 라이브러리 · 점검은
총무팀(admin)만. 사용자는 `/admin/users`, 라이브러리는 `/settings/library`
(routers/library.py)가 그대로 맡고 여기서는 탭으로만 잇는다 —
**화면만 옮기고 엔드포인트는 그대로다.**
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import DEFAULT_MEAL_SUBSIDY_PER_PERSON
from app.db import get_db
from app.push import application_server_key as push_key
from app.deps import all_retreats, get_current_retreat, log_activity, remember_retreat
from app.domain import board as board_domain
from app.domain import dweek
from app.domain.budget import build_budget_summary
from app.domain.clone import clone_retreat
from app.domain.period import is_over
from app.models import (
    ActivityLog,
    BudgetCategory,
    Department,
    ExpenseEntry,
    Program,
    ProgramItem,
    Retreat,
    Task,
    TaskRun,
    User,
)
from app.security import get_current_user, require_admin
from app.templating import redirect, render

router = APIRouter()


def _parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    return dt.date.fromisoformat(raw)


def _base_ctx(request: Request, db: Session, user: User) -> dict:
    retreats = all_retreats(db)
    retreat = get_current_retreat(request, db, user) if retreats else None
    return {
        "user": user,
        "retreat": retreat,
        "retreats": retreats,
        "active_tab": "settings",
        "page_subtitle": "설정",
    }


@router.get("/settings")
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """내 정보 탭 — 이름 · 연락처 · 부서 · 이 기기의 푸시 구독 · 로그아웃."""
    return render(
        request,
        "settings.html",
        {**_base_ctx(request, db, user), "push_public_key": push_key()},
    )


def _expense_stats(db: Session, retreat_id: int) -> tuple[int, int]:
    count = db.scalar(
        select(func.count()).select_from(ExpenseEntry).where(ExpenseEntry.retreat_id == retreat_id)
    ) or 0
    total = db.scalar(
        select(func.coalesce(func.sum(ExpenseEntry.amount), 0)).where(
            ExpenseEntry.retreat_id == retreat_id
        )
    ) or 0
    return int(count), int(total)


@router.get("/settings/retreats")
def settings_retreats(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """회차 관리 탭 — 보는 것은 누구나, 만들고 고치는 것은 총무팀만 (4-17)."""
    ctx = _base_ctx(request, db, user)
    today = dt.date.today()
    rows = []
    for r in ctx["retreats"]:
        run_count = db.scalar(
            select(func.count())
            .select_from(TaskRun)
            .where(TaskRun.retreat_id == r.id, TaskRun.included.is_(True))
        ) or 0
        expense_count, expense_sum = _expense_stats(db, r.id)
        rows.append(
            {
                "retreat": r,
                "run_count": int(run_count),
                "expense_count": expense_count,
                "expense_sum": expense_sum,
                "over": is_over(r, today),
            }
        )
    return render(request, "settings_retreats.html", {**ctx, "retreat_rows": rows})


@router.get("/settings/retreats/{retreat_id}")
def settings_retreat_detail(
    retreat_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = db.get(Retreat, retreat_id)
    if target is None:
        raise HTTPException(status_code=404, detail="회차를 찾을 수 없습니다.")

    today = dt.date.today()
    runs = list(
        db.scalars(
            select(TaskRun).where(TaskRun.retreat_id == target.id, TaskRun.included.is_(True))
        )
    )
    run_done = sum(1 for r in runs if r.status == "완료")
    # 지연은 저장된 status 가 아니라 날짜에서 계산한다 (4-10 · overdue_of)
    run_overdue = sum(1 for r in runs if board_domain.overdue_of(r, today))

    # 남은 지출은 summary 의 것을 그대로 쓴다 (4-17) — 여기서 다시 세지 않는다
    budget = build_budget_summary(db, retreat=target)
    expense_count, expense_sum = _expense_stats(db, target.id)

    program_count = db.scalar(
        select(func.count()).select_from(Program).where(Program.retreat_id == target.id)
    ) or 0
    program_item_count = db.scalar(
        select(func.count())
        .select_from(ProgramItem)
        .join(Program, ProgramItem.program_id == Program.id)
        .where(Program.retreat_id == target.id)
    ) or 0

    # 소속 인원도 **키로** 센다 (2장) — 행(id)으로 세면 다른 회차에 붙은
    # 계정이 빠져 새 회차의 부서가 전부 0명으로 보인다
    from app.domain.departments import users_in_department

    dept_rows = [
        {
            "name": d.name,
            "color": d.color,
            "member_count": (
                len(users_in_department(db, d.key)) if d.key
                else db.scalar(
                    select(func.count()).select_from(User).where(User.department_id == d.id)
                ) or 0
            ),
        }
        for d in db.scalars(
            select(Department)
            .where(Department.retreat_id == target.id)
            .order_by(Department.sort_order, Department.id)
        )
    ]

    return render(
        request,
        "settings_retreat_detail.html",
        {
            **_base_ctx(request, db, user),
            "target": target,
            "over": is_over(target, today),
            "d1_sunday": dweek.anchor_sunday(target.start_date) if target.start_date else None,
            "run_count": len(runs),
            "run_done": run_done,
            "run_overdue": run_overdue,
            "budget": budget,
            "unspent_count": budget.unspent_count,
            "unspent_planned": budget.unspent_planned,
            "expense_count": expense_count,
            "expense_sum": expense_sum,
            "program_count": int(program_count),
            "program_item_count": int(program_item_count),
        },
    )


@router.get("/settings/departments")
def settings_departments(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    ctx = _base_ctx(request, db, user)
    retreat = ctx["retreat"]
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
    return render(request, "settings_departments.html", {**ctx, "departments": departments})


@router.get("/settings/checkup")
def settings_checkup(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    ctx = _base_ctx(request, db, user)
    retreat = ctx["retreat"]

    admins = list(db.scalars(select(User).where(User.role == "admin", User.is_active.is_(True))))
    names = [a.name for a in admins]
    dup_admin_names = sorted({n for n in names if names.count(n) > 1})

    # 백업 마지막 시각 — data/backups 의 가장 최근 파일. 벽시계로 적는다 (5-8)
    last_backup = None
    try:
        from app.config import BASE_DIR

        backups = sorted((BASE_DIR / "data" / "backups").glob("app-*.db"))
        if backups:
            stamp = dt.datetime.fromtimestamp(backups[-1].stat().st_mtime)
            last_backup = stamp.strftime("%Y.%m.%d %H:%M")
    except OSError:
        pass

    return render(
        request,
        "settings_checkup.html",
        {
            **ctx,
            "vapid_ready": bool(push_key()),
            "admin_count": len(admins),
            "dup_admin_names": dup_admin_names,
            "last_backup": last_backup,
            "logs": list(
                db.scalars(
                    select(ActivityLog)
                    .where(ActivityLog.retreat_id == (retreat.id if retreat else None))
                    .order_by(ActivityLog.id.desc())
                    .limit(30)
                )
            ),
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
    return redirect("/settings/retreats", message=f"'{retreat.name}' 회차를 만들었습니다.")


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
    old_open = retreat.start_date
    retreat.name = name.strip()
    retreat.start_date = _parse_date(start_date)
    retreat.end_date = _parse_date(end_date)
    retreat.meal_subsidy_per_person = max(0, meal_subsidy_per_person)
    db.commit()

    # 개회일이 바뀌면 준비 업무 날짜가 D-주차를 유지한 채 함께 이동한다
    moved = 0
    if retreat.start_date != old_open:
        from app.domain.library import reschedule

        moved = reschedule(db, retreat)
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
        f"/settings/retreats/{retreat.id}",
        message=(
            f"회차 설정을 저장했습니다. 개회일이 바뀌어 준비 업무 {moved}건의 날짜를 옮겼습니다."
            if moved
            else "회차 설정을 저장했습니다. (식대 상한은 앞으로 등록되는 지출에 적용됩니다)"
        ),
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
    return redirect("/settings/departments", message="부서를 추가했습니다.")


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
    return redirect("/settings/departments", message=f"'{name}' 부서를 삭제했습니다.")


# 구설계 사용자 POST(/users/create · /users/{id}/update)는 지웠다 (14장) —
# 화면이 없어진 엔드포인트다. 사용자 관리는 /admin/users (4-12) 하나다.
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
