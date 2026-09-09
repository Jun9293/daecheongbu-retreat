# -*- coding: utf-8 -*-
"""관리자가 다시 들어갈 링크를 뽑는다 (4-12).

## 왜 있나

**세션을 잃은 관리자는 화면으로 돌아올 길이 없습니다.** 로그인 화면은
「초대 링크로 들어옵니다」 를 알려 줄 뿐이고, 링크를 발급하는 자리
(`/admin/users`)는 **이미 관리자여야** 들어갑니다. 그래서 마지막 관리자가
기기를 잃으면 아무도 아무것도 못 합니다 — 서버 컴퓨터에서 도는 이
스크립트가 그 자리입니다.

`create_admin.py --reissue` 도 같은 일을 하지만 **연락처를 알아야**
합니다. 링크를 잃은 사람이 자기 계정의 연락처 표기를 기억 못 하면 그
길도 막힙니다. 그래서 여기서는 **먼저 관리자 목록을 보여주고 id 로**
고릅니다.

## 링크를 만드는 코드를 새로 쓰지 않는다

발급도 주소 만들기도 `app/domain/auth.py` 의 `issue` · `invite_url`
하나를 그대로 부릅니다 (4-12 「만드는 것은 화면이든 스크립트든
domain/auth.issue 하나」). 두 곳에서 만들면 한쪽만 고쳐집니다.

## 화면에만 찍는다

목록도 링크도 **터미널에만** 나갑니다. 파일에 쓰지 않습니다 — 토큰
원문을 저장하지 않는 것이 이 구조의 전제입니다(4-12). 발급했다는
**사실만** 활동 기록에 남기고 **값은 남기지 않습니다.**

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/관리자링크.py            # 관리자 목록
    .venv\\Scripts\\python.exe scripts/관리자링크.py 3          # 그 id 의 링크
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글·기호가 깨지지 않게 한다 — 안내를
# 못 찍고 죽으면 막힌 사람이 무엇을 할지 모른다 (create_admin.py 와 같다)
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
from sqlalchemy.exc import OperationalError                       # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from app import config                                           # noqa: E402
from app.db import SessionLocal                                   # noqa: E402
from app.deps import log_activity                                # noqa: E402
from app.domain import auth as invites                           # noqa: E402
from app.domain import permissions as perm                       # noqa: E402
from app.models import InviteToken, User                         # noqa: E402


def 마지막입장(db: Session, user: User) -> str:
    """**「마지막 로그인」 을 저장하는 칸이 없습니다.**

    세션이 90일이라(4-12) 화면을 언제 마지막으로 열었는지는 아무 데도
    안 남습니다. 여기서 낼 수 있는 가장 가까운 사실은 **링크를 마지막으로
    쓴 때**(`invite_tokens.used_at`)입니다. 그 이름으로 찍습니다 —
    없는 값을 「마지막 로그인」 이라고 부르면 그 뒤로 아무도 안 의심합니다.
    """
    쓴때 = db.scalars(
        select(InviteToken.used_at)
        .where(InviteToken.user_id == user.id, InviteToken.used_at.is_not(None))
        .order_by(InviteToken.used_at.desc())
    ).first()
    return 쓴때.strftime("%Y-%m-%d") if 쓴때 else "-"


def 목록(db: Session) -> int:
    """관리자만 표로. **이름은 화면에만 나갑니다.**"""
    people = list(db.scalars(
        select(User).where(User.role == perm.ADMIN).order_by(User.id)))
    if not people:
        print("관리자(admin) 계정이 하나도 없습니다.")
        print("  처음 한 사람은 이렇게 만듭니다:")
        print('    python scripts/create_admin.py "이름" <연락처>')
        return 1

    print(f"관리자 계정 {len(people)}개")
    print()
    print(f"  {'id':>3}  {'이름':<12} {'역할':<10} {'마지막 로그인(링크 쓴 때)':<22} 상태")
    for p in people:
        상태 = "활성" if p.is_active else "비활성"
        print(f"  {p.id:>3}  {p.name:<12} {p.role:<10} {마지막입장(db, p):<22} {상태}")
    print()
    print("  링크가 필요한 사람의 id 를 뒤에 붙여 다시 부르세요:")
    print("    python scripts/관리자링크.py <id>")
    return 0


def 링크(db: Session, user_id: int) -> int:
    person = db.get(User, user_id)
    if person is None:
        print(f"id {user_id} 인 계정이 없습니다. 인자 없이 불러 목록을 보세요.")
        return 1
    # **관리자가 아니면 거절합니다.** 이 스크립트는 「관리자가 다시 들어갈
    # 길」 하나만 엽니다 — 아무 계정의 링크나 뽑는 자리가 되면, 서버
    # 컴퓨터를 잠깐 쓰는 사람이 아무나로 로그인할 수 있게 됩니다.
    # 다른 사람의 링크는 화면(`/admin/users`)에서 발급합니다 (4-12).
    if person.role != perm.ADMIN:
        print(f"id {user_id} 는 관리자(admin)가 아닙니다 — 발급하지 않았습니다.")
        print("  이 스크립트는 관리자가 다시 들어갈 길만 엽니다.")
        print("  다른 계정의 링크는 로그인한 뒤 설정 › 사용자에서 발급하세요.")
        return 1
    if not person.is_active:
        print(f"id {user_id} 는 비활성 계정입니다 — 발급하지 않았습니다.")
        print("  되살리는 것은 설정 › 사용자에서 합니다 (4-12).")
        return 1

    raw = invites.issue(db, user=person)
    # **발급했다는 사실만 남깁니다.** 값(토큰·주소)은 남기지 않습니다 —
    # 활동 기록은 화면에서 누구나 읽는 자리다.
    # **누가 눌렀는지는 비웁니다**(`actor=None`) — 서버 앞에 앉은 사람이
    # 누구인지 이 스크립트는 알 수 없습니다. 받는 사람을 행위자로 적으면
    # 「그 사람이 스스로 발급했다」 는 거짓이 기록에 남습니다.
    log_activity(
        db,
        retreat_id=None,
        actor=None,
        action="초대_링크_발급",
        target_type="user",
        target_id=person.id,
        summary=f"{person.name} 님의 링크를 서버에서 발급했습니다 (관리자 복구).",
    )
    db.commit()

    print()
    print(f"{person.name} 님의 로그인 링크입니다. 이 창에만 보입니다.")
    print()
    print(f"  {invites.invite_url(raw)}")
    print()
    print(f"유효기간 {invites.INVITE_TTL_DAYS}일 · 한 번 쓰면 만료됩니다.")
    print("**이전에 발급한 링크는 이제 쓸 수 없습니다.**")
    if config.BASE_URL:
        print(f"(주소는 DCB_BASE_URL 로 받았습니다: {config.BASE_URL})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="관리자가 다시 들어갈 링크를 뽑습니다 (서버 컴퓨터에서).",
        epilog="예:  관리자링크.py        (목록)   /   관리자링크.py 3   (그 id 의 링크)",
    )
    ap.add_argument("id", nargs="?", type=int, help="링크를 받을 관리자 계정 id")
    args = ap.parse_args()

    # **`init_db()` 를 부르지 않습니다.** 이 스크립트가 도는 때는 DB 가
    # 이미 있는 때뿐이고(관리자가 세션을 잃은 상황), 그 함수는 앱이 뜰 때
    # 도는 한 번짜리 전환들을 함께 부릅니다 — 링크 하나 뽑자고 그것들을
    # 다시 밟을 이유가 없습니다.
    with SessionLocal() as db:
        try:
            return 목록(db) if args.id is None else 링크(db, args.id)
        except OperationalError:
            # **데이터 폴더를 잘못 짚으면 sqlite 가 빈 파일을 만듭니다** —
            # 그러면 첫 조회에서 트레이스백으로 죽습니다. 이 파일 머리에
            # 「안내를 못 찍고 죽으면 막힌 사람이 무엇을 할지 모른다」 고
            # 적어 두었으므로 이 갈래만 사람 말로 받습니다.
            print("데이터베이스를 열었는데 표가 없습니다 — 빈 파일을 만든 것 같습니다.")
            print(f"  지금 보고 있는 곳: {config.DATABASE_URL}")
            print("  DCB_DATA_DIR 이 운영 데이터 폴더를 가리키는지 보고,")
            print("  앱이 한 번이라도 뜬 적 있는 폴더인지 확인하세요.")
            return 1


if __name__ == "__main__":
    sys.exit(main())
