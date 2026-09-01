"""같은 이름으로 여러 번 만들어진 계정을 정리한다 (CLAUDE.md 4-12).

    .venv\\Scripts\\python.exe scripts/merge_users.py
    .venv\\Scripts\\python.exe scripts/merge_users.py --keep 20 --apply

**기본은 미리보기다.** `--apply` 없이 돌리면 아무것도 바꾸지 않고 보여만 준다.
계정을 잘못 정리하면 그 사람이 남긴 기록의 주인이 흐려지는데, 그건 화면에
되돌릴 근거가 남지 않는다.

**지우지 않고 비활성화만 한다** (4-12). 지난 회차의 논의와 지출에 그 사람이
작성자로 남아 있어서, 계정을 지우면 그 기록이 "누가 썼는지 모르는 것" 이 된다.
비활성화하면 로그인만 막히고 기록은 그대로 남으며 살아 있던 링크도 함께 취소된다.

**기록을 옮기지 않는다.** 옮기면 "누가 썼는가" 가 사실과 달라진다 —
id=21 이 쓴 논의를 id=20 이 쓴 것으로 만들면, 그건 정리가 아니라 조작이다.
"""

from __future__ import annotations

import sys as _sys

for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select                              # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from app.deps import log_activity                                # noqa: E402
from app import config                                           # noqa: E402
from app.domain import auth as invites                           # noqa: E402
from app.models import (                                         # noqa: E402
    ActivityLog,
    DiscussionEntry,
    ExpenseEntry,
    ProgramItem,
    TaskAttachment,
    TaskRun,
    User,
)

# 그 계정에 달린 기록. **여기 있는 것은 옮기지 않는다** — 몇 건인지 보여주는 것이
# 목적이다. 남길 계정을 고를 때 "어느 쪽에 실제 기록이 있나" 가 근거가 된다.
TRACES = (
    ("논의", DiscussionEntry, "author_id"),
    ("첨부", TaskAttachment, "uploaded_by_id"),
    ("진행 체크", ProgramItem, "done_by_id"),
    ("담당 업무", TaskRun, "assignee_id"),
    ("지출", ExpenseEntry, "payer_id"),
    ("활동 기록", ActivityLog, "actor_id"),
)


def trace_counts(db: Session, user_id: int) -> dict[str, int]:
    out: dict[str, int] = {}
    for label, model, column in TRACES:
        count = db.scalar(
            select(func.count()).select_from(model)
            .where(getattr(model, column) == user_id)
        )
        if count:
            out[label] = count
    return out


def last_seen(db: Session, user_id: int):
    """마지막 활동. 없으면 None — 한 번도 쓴 적 없는 계정을 가려내는 근거다."""
    return db.scalar(
        select(func.max(ActivityLog.created_at)).where(ActivityLog.actor_id == user_id)
    )


def groups(db: Session, *, only_admin: bool = False) -> dict[str, list[User]]:
    """이름이 같은 계정 묶음. 둘 이상인 것만."""
    query = select(User).order_by(User.id)
    if only_admin:
        query = query.where(User.role == "admin")
    by_name: dict[str, list[User]] = {}
    for person in db.scalars(query):
        by_name.setdefault(person.name.strip(), []).append(person)
    return {name: rows for name, rows in by_name.items() if len(rows) > 1}


def survey(db: Session, *, only_admin: bool = False) -> list[dict]:
    rows = []
    for name, people in groups(db, only_admin=only_admin).items():
        rows.append({
            "name": name,
            "people": [
                {
                    "id": p.id,
                    "phone": p.phone_number,
                    "role": p.role,
                    "department_id": p.department_id,
                    "is_active": p.is_active,
                    "created_at": p.created_at,
                    "last_seen": last_seen(db, p.id),
                    "traces": trace_counts(db, p.id),
                }
                for p in people
            ],
        })
    return rows


def merge(db: Session, *, keep_id: int, apply: bool) -> dict:
    """`keep_id` 와 같은 이름인 나머지 계정을 비활성화한다."""
    keeper = db.get(User, keep_id)
    if keeper is None:
        raise SystemExit(f"id={keep_id} 인 계정이 없습니다.")

    others = [
        p for p in db.scalars(
            select(User).where(User.name == keeper.name, User.id != keeper.id)
            .order_by(User.id)
        )
    ]
    targets = [p for p in others if p.is_active]

    if apply and targets:
        for person in targets:
            person.is_active = False
            # 비활성화하면 살아 있던 링크도 함께 죽는다 (4-12)
            invites.revoke_all(db, user=person)
        if not keeper.is_active:
            keeper.is_active = True
        db.commit()
        log_activity(
            db,
            retreat_id=None,
            actor=None,
            action="계정_중복_정리",
            target_type="user",
            target_id=keeper.id,
            summary=(
                f"'{keeper.name}' — id={keeper.id} 만 남기고 "
                f"{', '.join('id=' + str(p.id) for p in targets)} 를 비활성화"
            ),
            before_value={"active": [p.id for p in targets] + [keeper.id]},
            after_value={"kept": keeper.id, "deactivated": [p.id for p in targets]},
        )

    return {"keeper": keeper, "deactivated": targets, "applied": bool(apply and targets)}


def show(rows: list[dict]) -> None:
    if not rows:
        print("  같은 이름으로 여러 개 만들어진 계정이 없습니다.")
        return

    for group in rows:
        print(f"  '{group['name']}' — {len(group['people'])}개")
        for person in group["people"]:
            traces = person["traces"]
            trace_text = (" · ".join(f"{k} {v}" for k, v in traces.items())
                          if traces else "남긴 기록 없음")
            seen = person["last_seen"]
            print(
                f"    id={person['id']:<4} {person['phone']:<14}"
                f" {person['role']:<10}"
                f" 부서={person['department_id'] if person['department_id'] else '없음':<5}"
                f" {'활성' if person['is_active'] else '비활성'}"
            )
            print(
                f"           만든 날 {person['created_at']:%Y-%m-%d %H:%M}"
                f" · 마지막 활동 {seen:%Y-%m-%d %H:%M}" if seen else
                f"           만든 날 {person['created_at']:%Y-%m-%d %H:%M}"
                f" · 마지막 활동 없음"
            )
            print(f"           {trace_text}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="같은 이름으로 여러 번 만들어진 계정을 정리합니다. 기본은 미리보기입니다."
    )
    parser.add_argument("--keep", type=int, help="남길 계정의 id")
    parser.add_argument(
        "--into", type=int,
        help="--keep 과 같은 뜻입니다 (기록을 옮기지는 않습니다)",
    )
    parser.add_argument("--apply", action="store_true", help="실제로 비활성화합니다")
    parser.add_argument(
        "--all-roles", action="store_true",
        help="관리자뿐 아니라 모든 역할에서 같은 이름을 찾습니다",
    )
    args = parser.parse_args()

    from app.db import SessionLocal, init_db

    init_db()
    keep_id = args.keep or args.into

    with SessionLocal() as db:
        rows = survey(db, only_admin=not args.all_roles)
        print("같은 이름으로 여러 개 있는 계정"
              + ("" if args.all_roles else " (관리자)") + "\n")
        show(rows)

        if keep_id is None:
            if rows:
                print("  남길 계정을 정해 다시 부르세요:")
                first = rows[0]["people"][0]["id"]
                print(f"    python scripts/merge_users.py --keep {first} --apply")
                print()
                print("  나머지는 **비활성화만** 합니다 — 지우지 않습니다.")
                print("  그 계정이 남긴 기록은 그대로 두고 작성자도 바꾸지 않습니다.")
            return 0

        result = merge(db, keep_id=keep_id, apply=args.apply)
        keeper, targets = result["keeper"], result["deactivated"]
        print(f"  남길 계정: id={keeper.id} · {keeper.name} · {keeper.phone_number}")
        if not targets:
            print("  비활성화할 것이 없습니다. 이미 정리돼 있습니다.")
            return 0
        for person in targets:
            print(f"  비활성화: id={person.id} · {person.phone_number}")
        print()
        if result["applied"]:
            print("  비활성화했습니다. 기록은 그대로 두었고 초대 링크는 함께 취소했습니다.")
            print("  활동 기록에 남겼습니다.")
            print()
            # **남긴 계정의 링크도 함께 죽었을 수 있다.** 여기서 길을 알려주지
            # 않으면 사람이 계정을 또 만든다 — 중복이 생기는 바로 그 입구다 (4-12)
            print("  남긴 계정으로 다시 들어가려면 링크만 새로 받으세요:")
            print(f"    python scripts/create_admin.py --reissue {keeper.phone_number}")
            print(f"  링크는 {config.BASE_URL} 주소로 나옵니다.")
        else:
            print("  아직 바꾸지 않았습니다 — 실제로 하려면 --apply 를 붙이세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
