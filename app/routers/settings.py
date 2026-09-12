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
from app.domain import login as 로그인
from app.domain import permissions as perm
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
from app.domain.departments import departments_of

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
    """내 정보 탭 — 이름 · 연락처 · 부서 · **비밀번호** · 푸시 구독 · 로그아웃."""
    return render(
        request,
        "settings.html",
        {**_base_ctx(request, db, user), "push_public_key": push_key(),
         "external": external_link(db),
         # **비밀번호가 있을 때만 그 자리를 그린다** (4-17). 없는 사람에게는
         # 바꿀 것이 없고, 그 사람이 할 일은 총무팀에서 첫 비밀번호를 받는
         # 것이다 — 안 되는 자리를 보여 주면 거기서 시간을 쓴다
         "can_change_password": bool(user.password_hash),
         "min_length": 로그인.MIN_LENGTH},
    )


@router.post("/settings/password")
def change_my_password(
    request: Request,
    password: str = Form(""),
    password2: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """설정 › 내 정보에서 본인이 바꾼다 (4-17 · 2026-09-11 에 사람이 정함).

    **지금 비밀번호는 묻지 않습니다.** 그렇게 정한 대가와 남는 것은
    `docs/봐둘것.md` AS-a 에 적혀 있습니다.

    **판정은 `domain/login.바꿔도되나` 하나**이고 첫 비밀번호를 바꾸는
    화면과 같은 것을 부릅니다 — 두 벌이면 한쪽에서만 통과하는 값이
    생기고 갈린 쪽을 아무도 눈치채지 못합니다.

    **비밀번호가 없는 계정은 여기로 못 들어옵니다** — 화면에 자리가 안
    보이는 것과 같은 판정을 서버도 다시 봅니다(화면만 감춘 것이 아닙니다).
    """
    if not user.password_hash:
        return redirect(
            "/settings",
            message="아직 비밀번호가 없습니다 — 총무팀에서 첫 비밀번호를 받으세요.",
        )
    탈 = 로그인.바꿔도되나(password, password2)
    if 탈:
        return redirect("/settings", message=탈)

    # 첫판이 아니므로 `must_change_password` 가 거짓으로 내려간다
    로그인.비밀번호를정한다(db, user, password)
    # **바꿨다는 사실만** 남긴다. 값은 남기지 않는다
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action=로그인.바꾼_행위,
        target_type="user",
        target_id=user.id,
        summary=로그인.바꾼_말(user),
    )
    return redirect("/settings", message="비밀번호를 바꿨습니다.")


def _expense_stats(db: Session, retreat_id: int) -> tuple[int, int]:
    """회차 상세·목록의 「지출 완료 N건 · X원」 — 취소된 행은 넣지 않는다 (7-4).

    summary 는 원천에서 빼는데 이 둘만 품으면 같은 화면의 두 숫자가 갈린다 —
    「지출 완료」 라는 이름이라 취소 행을 세면 말 그대로 틀린다.
    """
    live = (ExpenseEntry.retreat_id == retreat_id, ExpenseEntry.canceled_at.is_(None))
    count = db.scalar(
        select(func.count()).select_from(ExpenseEntry).where(*live)
    ) or 0
    total = db.scalar(
        select(func.coalesce(func.sum(ExpenseEntry.amount), 0)).where(*live)
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
            # 두 부서 사람은 두 번 세어진다 — 「부서 인원 합 > 계정 수」 가 맞다 (도막 4)
            "member_count": len(users_in_department(db, d.key)) if d.key else 0,
        }
        for d in departments_of(db, target.id)
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
            # 이 줄이 없어서 화면이 「부서가 없습니다」 라고 말했다 (2026-09-11).
            # 만든 값을 안 넘기면 Jinja 가 조용히 빈 것으로 그린다
            "dept_rows": dept_rows,
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
    departments = departments_of(db, retreat.id if retreat else None)
    return render(request, "settings_departments.html", {**ctx, "departments": departments})


@router.get("/settings/checkup")
def settings_checkup(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    ctx = _base_ctx(request, db, user)
    retreat = ctx["retreat"]

    admins = perm.admins(db)
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


@router.get("/retreats/{retreat_id}/reschedule-preview")
def reschedule_preview(
    retreat_id: int,
    open_date: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """개회일을 그날로 바꾸면 무엇이 달라지는지 — **저장하기 전에** (6-4).

    **세는 것은 `library.reschedule_preview` 하나**이고 실제로 옮기는
    `reschedule` 이 같은 `_plan` 을 쓴다. 두 곳에서 따로 세면 보여준 수와
    실제가 갈리고, 갈린 쪽을 아무도 눈치채지 못한다.
    """
    from app.domain.library import reschedule_preview as 센다

    retreat = db.get(Retreat, retreat_id)
    if retreat is None:
        raise HTTPException(status_code=404, detail="회차를 찾을 수 없습니다.")
    새개회 = _parse_date(open_date)
    if 새개회 is None:
        raise HTTPException(status_code=400, detail="개회일이 없습니다.")
    if 새개회 == retreat.start_date:
        return {"changed": False}
    return {"changed": True, **센다(db, retreat, 새개회)}


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
    from app.domain.departments import next_team_key

    # 키는 여기서도 발급한다 — 키 없는 부서는 소속·알림이 전부 비껴간다 (2장)
    dept = Department(
        retreat_id=retreat.id,
        key=next_team_key(db),
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
# ── 바깥 링크 (도막 4 · 3장) ─────────────────────────────────────
# 바깥 서비스의 관리자 화면처럼 **저장소 어디에도 적으면 안 되는 주소**는
# DB 에만 둔다. 값이 있으면 사이드바에 그 이름의 항목이 생겨 새 창으로 열린다.
EXTERNAL_LINK_NAME = "external_link_name"
EXTERNAL_LINK_URL = "external_link_url"
EXTERNAL_LINK_NOTE = "external_link_note"


def external_link(db: Session) -> dict | None:
    """(이름, 주소, 설명) — **이름과 주소가 있을 때만.** 설명은 있으면 붙는다.

    이름만 보고 「저게 뭐였더라」 를 묻게 되는 자리라 한 줄을 달 수 있게
    했다(첨부의 링크에 설명을 비워 둘 수 없게 한 것과 같은 자리 — 4-9).
    다만 **여기서는 비워도 된다**: 사이드바 항목은 하나뿐이고 이름이 이미
    보이므로, 강제하면 값을 넣으려고 아무 말이나 적게 된다.
    **비면 안 그린다** — 빈 줄이 있으면 그 자리가 무엇인지 또 묻게 된다.
    """
    from app.models import SiteSetting

    name = db.get(SiteSetting, EXTERNAL_LINK_NAME)
    url = db.get(SiteSetting, EXTERNAL_LINK_URL)
    if name is None or url is None or not (name.value and url.value):
        return None
    note = db.get(SiteSetting, EXTERNAL_LINK_NOTE)
    return {"name": name.value, "url": url.value,
            "note": (note.value or "") if note is not None else ""}


@router.post("/settings/external-link")
def set_external_link(
    name: str = Form(""),
    url: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """총무팀만 고친다. **이름이나 주소 한쪽만 비어도** 사이드바 항목이
    사라진다 — 위의 `external_link()` 가 둘 다 있을 때만 내주기 때문이다.
    화면 안내도 같은 말이다(`settings.html` 의 `.hint.lone` 줄).
    """
    from app.models import SiteSetting

    name, url, note = name.strip(), url.strip(), note.strip()
    if url and not url.startswith(("http://", "https://")):
        return redirect("/settings", message="주소는 http:// 또는 https:// 로 시작해야 합니다.")
    # 주소를 지우면 설명도 함께 지운다 — 가리킬 곳이 없는 설명만 남으면
    # 다음에 링크를 넣는 사람이 남의 설명을 물려받는다
    if not url:
        note = ""
    for key, value in ((EXTERNAL_LINK_NAME, name), (EXTERNAL_LINK_URL, url),
                       (EXTERNAL_LINK_NOTE, note)):
        row = db.get(SiteSetting, key)
        if row is None:
            row = SiteSetting(key=key)
            db.add(row)
        row.value = value or None
    db.commit()
    # 주소는 활동 기록에도 남기지 않는다 — 화면에서 누구나 읽는 자리다
    log_activity(db, retreat_id=None, actor=user, action="바깥_링크_변경",
                 target_type="setting", target_id=None,
                 summary=f"바깥 링크: {name or '(없음)'}")
    return redirect("/settings", message="바깥 링크를 저장했습니다." if url else "바깥 링크를 지웠습니다.")


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
