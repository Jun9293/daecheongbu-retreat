"""첫 관리자 계정을 만들고 초대 링크를 한 번 출력한다.

계정 관리 화면(/admin/users)에 들어가려면 이미 관리자여야 하므로, 맨 처음
한 사람만 여기서 만든다. 그 뒤로는 전부 화면에서 한다.

    .venv\\Scripts\\python.exe scripts/create_admin.py "이름" 01012341234
    .venv\\Scripts\\python.exe scripts/create_admin.py --reissue 01012341234

**링크가 필요할 뿐인데 계정을 만들게 하지 않는다.** 이것이 관리자 계정이
넷으로 불어난 뿌리다 — 초대 링크는 한 번 쓰면 만료되므로(4-12) 재발급이 자주
필요한데, 링크만 다시 받는 길이 눈에 띄지 않으면 사람은 계정을 다시 만든다.
그리고 중복 계정은 **알림을 여러 번 보낸다** — 조용한 문제가 아니다.

그래서 셋을 지킨다.
  · 같은 연락처가 이미 있으면 **새로 만들지 않고** 링크만 다시 발급한다
  · 같은 이름의 관리자가 있으면 **멈추고 보여준다** (동명이인은 --force)
  · 링크만 필요하면 --reissue
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
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from app import config                                           # noqa: E402
from app.db import SessionLocal, init_db                         # noqa: E402
from app.domain import auth as invites                           # noqa: E402
from app.models import User                                      # noqa: E402

# 환경변수를 안 준 상태인지 알아보려고 둔다 — 안내 문구가 달라진다
DEFAULT_BASE_URL = "https://retreat.recba12.com"


def digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def same_name_admins(db: Session, name: str) -> list[User]:
    """같은 이름의 살아 있는 관리자들."""
    return list(
        db.scalars(
            select(User)
            .where(User.name == name, User.role == "admin", User.is_active)
            .order_by(User.id)
        )
    )


def describe(person: User) -> str:
    return (
        f"id={person.id} · {person.name} · {person.phone_number}"
        f" · {person.role}{'' if person.is_active else ' (비활성)'}"
    )


def show_link(raw: str) -> None:
    print()
    print("아래 주소를 그대로 복사해서 카카오톡으로 보내시면 됩니다.")
    print("이 링크는 지금 한 번만 보입니다 — 원문을 저장하지 않기 때문입니다.")
    # **완성된 주소를 찍는다.** 자리표시자를 남기면 사람이 앞부분을 손으로
    # 갈아 끼우다 토큰까지 건드려 링크가 깨진다 (4-12)
    print(f"  {invites.invite_url(raw)}")
    print()
    if config.BASE_URL != DEFAULT_BASE_URL:
        print(f"(주소는 DCB_BASE_URL 로 받았습니다: {config.BASE_URL})")
    else:
        print(f"(주소가 다르면 DCB_BASE_URL 로 알려주세요. 지금은 {config.BASE_URL})")
    print(f"유효기간 {invites.INVITE_TTL_DAYS}일 · 한 번 쓰면 만료됩니다.")
    print("**링크를 잃어버렸으면 계정을 다시 만들지 마세요.** 아래로 링크만 다시 받습니다:")
    print("  python scripts/create_admin.py --reissue <연락처>")


def reissue(db: Session, phone: str) -> int:
    person = db.scalars(select(User).where(User.phone_number == phone)).first()
    if person is None:
        have = list(db.scalars(select(User).where(User.role == "admin").order_by(User.id)))
        print(f"'{phone}' 연락처의 계정이 없습니다.")
        if have:
            print("  있는 관리자 계정:")
            for one in have:
                print(f"    {describe(one)}")
        print("  연락처를 확인하거나, 계정을 새로 만들려면 이름과 함께 부르세요:")
        print('    python scripts/create_admin.py "이름" <연락처>')
        return 1

    if not person.is_active:
        person.is_active = True
        db.commit()
        print(f"'{person.name}' 계정이 비활성이라 다시 켰습니다.")
    raw = invites.issue(db, user=person)
    print(f"'{person.name}' ({person.phone_number}) 의 링크를 다시 발급했습니다.")
    print("  계정을 새로 만들지 않았습니다. 남아 있던 옛 링크는 함께 취소됐습니다.")
    show_link(raw)
    return 0


def create(db: Session, name: str, phone: str, force: bool) -> int:
    # 1) 같은 연락처가 이미 있으면 — 새로 만들지 않는다
    existing = db.scalars(select(User).where(User.phone_number == phone)).first()
    if existing is not None:
        changed = []
        if existing.role != "admin":
            existing.role = "admin"
            changed.append("관리자로 바꿨습니다")
        if not existing.is_active:
            existing.is_active = True
            changed.append("다시 켰습니다")
        if changed:
            db.commit()
        print(f"이미 있는 계정입니다 — 새 링크를 발급했습니다.")
        print(f"  {describe(existing)}")
        if changed:
            print("  " + " · ".join(changed))
        show_link(invites.issue(db, user=existing))
        return 0

    # 2) 연락처는 다른데 같은 이름의 관리자가 있으면 — 멈추고 보여준다
    twins = same_name_admins(db, name)
    if twins and not force:
        print(f"'{name}' 이라는 관리자가 이미 있습니다. 만들지 않았습니다.")
        for one in twins:
            print(f"  {describe(one)}")
        print()
        print("  · 그 사람의 링크가 필요한 것이라면 (계정을 만들지 마세요):")
        print(f"      python scripts/create_admin.py --reissue {twins[0].phone_number}")
        print("  · 정말 다른 사람(동명이인)이라면:")
        print(f'      python scripts/create_admin.py "{name}" {phone} --force')
        return 1

    person = User(name=name, phone_number=phone, role="admin")
    db.add(person)
    db.commit()
    if twins:
        print(f"'{name}' 관리자 계정을 하나 더 만들었습니다 (--force).")
        print(f"  같은 이름이 이제 {len(twins) + 1}개입니다 — 알림이 그만큼 갑니다.")
        print("  헷갈리면 scripts/merge_users.py 로 정리하세요.")
    else:
        print(f"'{name}' 관리자 계정을 만들었습니다.")
    show_link(invites.issue(db, user=person))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="첫 관리자 계정을 만들거나, 링크만 다시 발급합니다.",
        epilog='예:  create_admin.py "홍길동" 01012341234   /   '
               "create_admin.py --reissue 01012341234",
    )
    parser.add_argument("name", nargs="?", help="이름")
    parser.add_argument("phone", nargs="?", help="연락처")
    parser.add_argument(
        "--reissue", metavar="연락처",
        help="계정을 만들지 않고 그 연락처의 초대 링크만 다시 발급합니다",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="같은 이름의 관리자가 있어도 새로 만듭니다 (동명이인일 때만)",
    )
    args = parser.parse_args()

    init_db()

    if args.reissue:
        phone = digits(args.reissue)
        if not phone:
            print("연락처를 숫자로 넣어주세요.")
            return 1
        with SessionLocal() as db:
            return reissue(db, phone)

    if not args.name or not args.phone:
        print('쓰는 법:  python scripts/create_admin.py "이름" <연락처>')
        print("          python scripts/create_admin.py --reissue <연락처>")
        print()
        print("  링크를 잃어버렸을 뿐이라면 --reissue 를 쓰세요.")
        print("  계정을 다시 만들면 같은 사람이 둘이 되고 알림도 두 번 갑니다.")
        return 1

    name = args.name.strip()
    phone = digits(args.phone)
    if not name or not phone:
        print("이름과 연락처를 모두 넣어주세요.")
        return 1

    with SessionLocal() as db:
        return create(db, name, phone, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
