"""계정 관리 (CLAUDE.md 4-12).

총무팀이 사람을 등록하고 초대 링크를 발급하는 자리. 지금까지는 seed 로만
계정을 만들 수 있었는데, 그러면 매 회차 담당자가 바뀔 때마다 코드를 고쳐야 한다.

**화면에는 삭제가 없다.** 지난 회차의 논의와 지출에 그 사람이 작성자로 남아
있으므로, 지우면 기록이 "누가 썼는지 모르는 것" 이 된다. 비활성화만 둔다.
(사람이 id 를 골라 지우는 한 갈래는 `scripts/계정정리.py` — 0장의 예외.)

**한 사람에 부서를 여럿 붙이고 각각 리더/팀원을 고른다** (도막 4). 전체 역할
(`users.role`)은 총무팀·일반·열람 전용 셋이고, 부서 역할은 소속 줄에서
파생한다 — 소속을 읽고 쓰는 것은 `domain/permissions` 하나다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import all_retreats, log_activity, resolve_retreat
from app.domain import auth as invites
from app.domain import permissions as perm
from app.domain.departments import DEPARTMENT_NAMES
from app.domain.permissions import ALL_ROLES, DEPT_ROLE_LABELS, ROLE_LABELS
from app.models import NO_PHONE, User
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


class 배정불가(Exception):
    """이번 회차에 없는 부서에 붙이려 했다 — 부르는 쪽이 사람 말로 되돌린다."""

    def __init__(self, name: str, *, no_retreat: bool):
        super().__init__(name)
        self.name, self.no_retreat = name, no_retreat


async def _wanted_departments(request: Request, choices: list[dict], *, has_retreat: bool
                              ) -> tuple[dict[str, str], set[str]]:
    """폼의 `dept_<키>` 칸들 → ({키: 부서 역할}, 뗄 지난 부서 키들). 빈 값은 「소속 아님」.

    선택지에 없는 키는 **조용히 버리지 않고 거절한다** — 이번 회차에 없는
    부서에 붙이면 그 사람은 아무 업무도 못 고치는데 아무도 모른다.
    `drop_<키>` 는 지난 회차 소속을 **골라서** 떼는 칸이다 — 폼에 없는 소속은
    저장해도 안 지워지므로(배포 5) 떼는 길이 따로 있어야 한다.
    """
    form = await request.form()
    allowed = {c["key"] for c in choices}
    wanted: dict[str, str] = {}
    drop: set[str] = set()
    for field, value in form.multi_items():
        if field.startswith("drop_"):
            drop.add(field[len("drop_"):])
            continue
        if not field.startswith("dept_"):
            continue
        key = field[len("dept_"):]
        value = (value or "").strip()
        if key not in allowed:
            if not value:
                continue          # 비운 채 되돌아온 옛 칸 — 붙이려는 것이 아니다
            raise 배정불가(DEPARTMENT_NAMES.get(key, key), no_retreat=not has_retreat)
        if not value:
            continue
        if value not in perm.DEPT_ROLES:
            raise HTTPException(status_code=400, detail="알 수 없는 부서 역할입니다.")
        wanted[key] = value
    return wanted, drop


def _배정불가_안내(e: 배정불가) -> str:
    if e.no_retreat:
        return f"아직 회차가 없어 '{e.name}' 을(를) 배정할 수 없습니다. 회차를 먼저 만들어주세요."
    return f"이번 회차에 없는 부서라 배정할 수 없습니다: {e.name}. 설정 › 부서에서 먼저 확인해주세요."


def _rows_for(db: Session, retreat, live_keys: set[str]) -> list[dict]:
    rows = []
    for person in db.scalars(select(User).order_by(User.is_active.desc(), User.name)):
        token = invites.live_token(db, user=person)
        # 이번 회차에 있는 부서 → 폼의 선택 값 · 없는 부서 → 표시만 (건드리지 않는다).
        # 소속 줄은 permissions 가 읽어 준다 — 여기서 표를 직접 안 본다
        current = {k: r for k, r in perm.roles_by_key(person).items() if k in live_keys}
        stale = [
            {"key": key, "name": name, "role_label": role_label}
            for key, name, role_label in perm.membership_names(person, dept_names=DEPARTMENT_NAMES)
            if key not in live_keys
        ]
        rows.append(
            {
                "id": person.id,
                "name": person.name,
                "phone": person.phone_number,
                # 비활성 계정은 번호를 놓았다. 빈 칸으로 두면 누구였는지 알 수
                # 없으므로 원래 번호를 흐리게 보여준다 (4-12)
                "retired_phone": person.retired_phone,
                "role": person.role,
                "role_label": ROLE_LABELS.get(person.role, person.role),
                "current": current,          # {키: lead|member}
                "stale": stale,              # 지난 회차 소속 — **건드리지 않는다**
                "departments_text": perm.describe(person, dept_names=DEPARTMENT_NAMES),
                "is_active": person.is_active,
                "invite_live": token is not None,
                "invite_expires": token.expires_at.date().isoformat() if token else None,
                # 링크 상태는 **셋이다** (4-12). 「보냈는가」 와 「들어왔는가」 를
                # 한 값에 담으면, 아직 못 들어온 사람과 이미 쓰고 링크가 만료된
                # 사람이 같은 칸에 들어가 **누구에게 보내야 하는지**가 안 보인다.
                "invite_state": (
                    "들어옴" if invites.entered_ever(db, user=person)
                    else ("보냈음" if token is not None else "안 보냄")
                ),
            }
        )
    return rows


@router.get("/admin/users")
def users_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    retreat = resolve_retreat(db, user, None)
    choices = _department_choices(db, retreat)
    live_keys = {c["key"] for c in choices}
    rows = _rows_for(db, retreat, live_keys)

    # **누가 남았는지 위에서 한 번에 보인다** (4-12). 열아홉 명에게 차례로
    # 보내는 일이라, 목록을 훑어 세는 것은 사람이 할 일이 아니다.
    # 비활성 계정은 세지 않는다 — 링크를 보낼 사람이 아니다.
    보낼사람 = [r for r in rows if r["is_active"] and r["invite_state"] == "안 보냄"]
    기다리는사람 = [r for r in rows if r["is_active"] and r["invite_state"] == "보냈음"]

    return render(
        request,
        "admin_users.html",
        {
            "user": user,
            "retreat": retreat,
            "retreats": all_retreats(db),
            "rows": rows,
            "yet_count": len(보낼사람),
            "sent_count": len(기다리는사람),
            "in_count": sum(
                1 for r in rows if r["is_active"] and r["invite_state"] == "들어옴"
            ),
            "departments": choices,
            "dept_roles": [{"value": r, "label": DEPT_ROLE_LABELS[r]} for r in perm.DEPT_ROLES],
            "roles": [{"value": r, "label": ROLE_LABELS.get(r, r)} for r in ALL_ROLES],
            "active_tab": "settings",
            "page_subtitle": "계정 관리",
            # 원문은 URL 을 타지 않는다. 한 번만 꺼내지는 자리에서 가져온다.
            # **완성된 주소로 넘긴다.** 앱은 127.0.0.1 에만 열려 있어서
            # request.base_url 은 바깥 주소가 아니다 — 그걸 복사해 보내면
            # 받는 사람 브라우저에서 열리지 않는다 (11-2)
            # 원문과 이름은 **한 키에 묶여** 나온다 — 이름을 따로(u=) 실으면
            # 주소를 손봤을 때 「B 님의 링크」 아래 A 의 링크가 뜰 자리가 생긴다
            "issued_url": (
                invites.invite_url(taken[0])
                if (taken := invites.take(request.query_params.get("k"))) else None
            ),
            "issued_for": (taken[1] or None) if taken else None,
            "no_departments": not choices,
        },
    )


@router.post("/admin/users/new")
async def create_user(
    request: Request,
    name: str = Form(...),
    phone_number: str = Form(...),
    role: str = Form(perm.GENERAL),
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

    retreat = resolve_retreat(db, user, None)
    choices = _department_choices(db, retreat)
    try:
        wanted, _ = await _wanted_departments(request, choices, has_retreat=retreat is not None)
    except 배정불가 as e:
        return redirect("/admin/users", message=_배정불가_안내(e))

    person = User(name=name, phone_number=phone, role=role)
    db.add(person)
    db.flush()
    perm.set_memberships(db, person, wanted, among=list(retreat.departments) if retreat else [])
    db.commit()
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="계정_생성",
        target_type="user",
        target_id=person.id,
        summary=f"{name} ({ROLE_LABELS.get(role, role)}"
                + (f" · {perm.describe(person, dept_names=DEPARTMENT_NAMES)}" if wanted else "") + ")",
    )
    raw = invites.issue(db, user=person, actor=user)
    # 원문 대신 **한 번 쓰면 사라지는 키**만 싣는다 — 주소창·방문 기록·접속 로그
    # 어디에도 링크가 남지 않게 하기 위해서다. 이름도 같은 키에 묶여 간다.
    return redirect(f"/admin/users?k={invites.stash(raw, person.name)}")


def _clean_phone(raw: str) -> str:
    """`010-1234-5678` 로 넣어도 숫자만 남긴다."""
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def _phone_taken_by(db: Session, phone: str, *, exclude_id: int) -> User | None:
    """그 번호를 **쥐고 있는** 다른 계정.

    비활성 계정은 비활성화할 때 번호를 놓으므로(4-12) 여기 걸리지 않는다.
    로그인은 초대 링크로 하지 번호로 하지 않으니 비활성 계정에게 번호는
    필요 없고, 붙들고 있으면 남긴 계정에 그 번호를 넣을 수 없어 정리가 끝나지 않는다.
    """
    if not phone:
        return None
    return db.scalars(
        select(User).where(
            User.phone_number == phone,
            User.id != exclude_id,
            User.is_active,
        )
    ).first()


@router.post("/admin/users/{user_id}/update")
async def update_user(
    request: Request,
    user_id: int,
    role: str = Form(...),
    # **없는 것과 비운 것은 다르다.** 폼은 늘 보내지만, 부서·권한만 바꾸려고
    # 부르는 쪽이 있으면 그때 연락처가 지워지면 안 된다.
    # 안 보냈으면(None) 그대로 두고, 보냈는데 비었으면 거절한다.
    phone_number: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    if role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail="알 수 없는 권한입니다.")

    # ── 연락처 (4-12) ────────────────────────────────────────
    # 연락처는 계정을 구분하는 열쇠라, 겹치면 **조용히 엉뚱한 계정에 링크가 간다.**
    # 그래서 고칠 수는 있되 겹치는 것은 막고 누구 것인지 말한다.
    if phone_number is not None and not person.is_active:
        # 되살리고 나서 고친다 — 비활성 계정은 번호를 쥐고 있지 않다
        return redirect(
            "/admin/users",
            message=f"{person.name} 님은 비활성 계정이라 연락처를 고칠 수 없습니다. "
                    "먼저 다시 활성화해주세요.",
        )

    phone = person.phone_number if phone_number is None else _clean_phone(phone_number)
    if not phone:
        return redirect(
            "/admin/users",
            message=f"{person.name} 님의 연락처를 비울 수 없습니다. "
                    "연락처가 없으면 나중에 그 계정을 찾을 길이 없습니다.",
        )
    if phone != person.phone_number:
        owner = _phone_taken_by(db, phone, exclude_id=person.id)
        if owner is not None:
            return redirect(
                "/admin/users",
                message=(
                    f"이 번호는 이미 {owner.name} 님이 쓰고 있습니다"
                    + ("" if owner.is_active else " (비활성 계정)")
                    + f". {person.name} 님의 연락처를 바꾸지 않았습니다."
                ),
            )

    retreat = resolve_retreat(db, user, None)
    choices = _department_choices(db, retreat)
    try:
        wanted, drop = await _wanted_departments(request, choices, has_retreat=retreat is not None)
    except 배정불가 as e:
        return redirect("/admin/users", message=_배정불가_안내(e))

    before = {"role": person.role, "departments": perm.describe(person)}
    # **바뀐 것만 적는다.** 안 바뀐 연락처가 기록에 남으면 나중에 "이때 번호를
    # 건드렸나" 를 다시 따져야 한다.
    phone_changed = phone != person.phone_number
    if phone_changed:
        before["phone"] = person.phone_number
        person.phone_number = phone

    person.role = role
    # **이번 회차의 부서만 맞춘다** — 지난 회차 소속은 건드리지 않는다.
    # 권한만 고치려고 저장했을 때 지난 회차 소속이 조용히 지워지면 안 된다.
    붙임, 뗌 = perm.set_memberships(
        db, person, wanted, among=list(retreat.departments) if retreat else [])
    if drop:
        뗌 = 뗌 + perm.unassign_keys(db, person, drop)
    db.commit()
    after = {"role": role, "departments": perm.describe(person)}
    if phone_changed:
        after["phone"] = phone

    # 연락처를 바꿔도 **살아 있는 초대 링크를 죽이지 않는다** —
    # 링크는 계정(user_id)에 붙지 번호에 붙지 않는다.

    changes = [f"{before['role']} → {role}"] if before["role"] != role else []
    if phone_changed:
        changes.append(f"{before['phone']} → {phone}")
    if 붙임:
        changes.append("소속 +" + ", ".join(붙임))
    if 뗌:
        changes.append("소속 -" + ", ".join(뗌))
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="계정_변경",
        target_type="user",
        target_id=person.id,
        summary=f"{person.name}: " + (" · ".join(changes) if changes else "바뀐 것 없음"),
        before_value=before,
        after_value=after,
    )
    return redirect("/admin/users", message=f"{person.name} 님의 설정을 바꿨습니다.")


@router.post("/admin/users/{user_id}/invite")
def issue_invite(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """새 링크를 발급한다. 남아 있던 링크는 함께 취소된다.

    만드는 것은 화면이든 스크립트(create_admin.py)든 **invites.issue 하나**다 —
    두 길로 만들면 하나만 고쳐진다. 화면의 JS 가 부르면(inline=1) JSON 으로
    그 자리에 돌려주고, JS 가 없으면 리다이렉트로 맨 위 배너에 띄운다 —
    원문과 이름은 stash 한 키에 묶여 배너로 간다 — 어긋날 자리가 없다.
    **링크는 계정에 붙는다 — 소속과 무관하다** (4-12).
    """
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
    if request.query_params.get("inline"):
        token = invites.live_token(db, user=person)
        return JSONResponse(
            {
                "url": invites.invite_url(raw),
                "name": person.name,
                "expires": token.expires_at.date().isoformat() if token else None,
            },
            # 링크 원문이 담긴 응답이다 — 어디에도 저장될 이유가 없다
            headers={"Cache-Control": "no-store"},
        )
    return redirect(f"/admin/users?k={invites.stash(raw, person.name)}")


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
    """비활성화·복구. **화면에는 삭제가 없다** — 지난 회차 기록의 작성자가 사라지면 안 된다."""
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    if person.id == user.id:
        return redirect("/admin/users", message="자기 계정은 비활성화할 수 없습니다.")

    person.is_active = active == "on"

    # ── 번호를 놓고 되받는다 (4-12) ─────────────────────────────────
    # 비활성 계정은 로그인을 못 하므로 번호를 붙들 이유가 없다. 붙들고 있으면
    # 중복을 정리한 뒤 남긴 계정에 실제 번호를 넣을 수 없다.
    note = ""
    if not person.is_active:
        invites.revoke_all(db, user=person)
        if person.phone_number:
            person.retired_phone = person.phone_number
            person.phone_number = NO_PHONE
            note = f" · 연락처 {person.retired_phone} 반납"
    else:
        wanted = person.retired_phone
        if wanted and not person.phone_number:
            owner = _phone_taken_by(db, wanted, exclude_id=person.id)
            if owner is None:
                person.phone_number = wanted
                person.retired_phone = None
                note = f" · 연락처 {wanted} 되돌림"
            else:
                # **조용히 돌아오지 않게 한다** — 왜 빈 채로 남았는지 말해준다
                note = f" · 연락처 {wanted} 되돌리지 못함({owner.name} 사용 중)"

    db.commit()
    log_activity(
        db,
        retreat_id=None,
        actor=user,
        action="계정_활성_변경",
        target_type="user",
        target_id=person.id,
        summary=f"{person.name}: {'활성' if person.is_active else '비활성'}{note}",
    )

    message = f"{person.name} 님을 {'다시 활성화' if person.is_active else '비활성화'}했습니다."
    if "되돌리지 못함" in note:
        owner_name = note.split("(")[-1].rstrip(") 사용 중")
        message += (
            f" 원래 번호 {person.retired_phone} 은(는) 지금 {owner_name} 님이"
            " 쓰고 있어 되돌리지 못했습니다."
        )
    elif "반납" in note:
        message += f" 연락처 {person.retired_phone} 은(는) 반납했습니다 — 다른 계정이 쓸 수 있습니다."
    return redirect("/admin/users", message=message)
