# -*- coding: utf-8 -*-
"""문을 여는 세 갈래 (4-12). 서버 컴퓨터에서 돌립니다.

## 왜 있나

**화면으로 돌아올 길이 없는 사람이 생깁니다.** 비밀번호를 만드는 자리
(설정 › 사용자)는 **이미 관리자여야** 들어갑니다. 그래서 첫 관리자가
아직 없거나 마지막 관리자가 비밀번호를 잊으면 아무도 아무것도 못 합니다 —
그 자리를 이 스크립트가 맡습니다.

`scripts/관리자링크.py` 와 `scripts/create_admin.py` 가 하던 일입니다.
둘 다 초대 링크를 발급하던 것이라 링크를 걷으면서 함께 지웠고, 여기
갈래 ① 과 ② 가 그 자리를 대신합니다.

## 화면에만 찍는다

목록도 비밀번호도 **터미널에만** 나갑니다. 파일에 쓰지 않습니다 —
원문을 저장하지 않는 것이 이 구조의 전제입니다. 발급했다는 **사실만**
활동 기록에 남기고 **값은 남기지 않습니다.**

## 쓰는 법

    .venv\\Scripts\\python.exe scripts/계정문열기.py
    .venv\\Scripts\\python.exe scripts/계정문열기.py --첫관리자 "이름" 아이디
    .venv\\Scripts\\python.exe scripts/계정문열기.py --재설정 3
    .venv\\Scripts\\python.exe scripts/계정문열기.py --재설정 3 --아이디 아이디
    .venv\\Scripts\\python.exe scripts/계정문열기.py --링크끊기

넷째 줄은 **아이디가 아직 없는 관리자**에게 아이디를 붙이면서 비밀번호를
만듭니다 — 비밀번호만 있고 아이디가 없으면 못 들어옵니다.

**연락처는 여기서 받지 않습니다.** 명령줄에 적으면 그 번호가 PowerShell
기록에 남습니다. 연락처는 들어간 뒤 설정 › 사용자에서 넣습니다 — 로그인에
쓰는 값이 아니라 연락처일 뿐이기 때문입니다.
"""

from __future__ import annotations

import sys as _sys

# 윈도우 기본 콘솔(cp949)에서 한글·기호가 깨지지 않게 한다 — 안내를 못 찍고
# 죽으면 막힌 사람이 무엇을 할지 모른다
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
from app.domain import auth as 옛링크                             # noqa: E402
from app.domain import login as 로그인                            # noqa: E402
from app.domain import permissions as perm                       # noqa: E402
from app.models import User                                      # noqa: E402


def 문상태(person: User) -> str:
    """그 계정이 지금 들어올 수 있는가. **화면의 그 넷과 같은 말**로 적는다."""
    if not person.login_id:
        return "아이디 없음"
    if not person.password_hash:
        return "비밀번호 없음"
    if 로그인.잠겼나(person):
        return "잠김"
    return "첫 비밀번호" if person.must_change_password else "쓰는 중"


def 보인다(raw: str, person: User) -> None:
    """**이 창에만 보인다.** 파일에 쓰지 않는다."""
    print()
    print(f"{person.name} 님의 비밀번호입니다. 이 창에만 보입니다.")
    print()
    print(f"  아이디   {person.login_id}")
    print(f"  비밀번호 {raw}")
    print()
    print("본인에게 전해주세요. 처음 들어오면 비밀번호를 바꾸는 화면이 먼저 뜹니다.")
    print("**이전 비밀번호는 이제 쓸 수 없습니다.**")
    print(f"(로그인 주소: {config.BASE_URL}/login)")


def 목록(db: Session) -> int:
    """관리자만 표로. **이름은 화면에만 나갑니다.**"""
    people = list(db.scalars(
        select(User).where(User.role == perm.ADMIN).order_by(User.id)))
    if not people:
        print("관리자(admin) 계정이 하나도 없습니다.")
        print("  첫 한 사람은 이렇게 만듭니다:")
        print('    python scripts/계정문열기.py --첫관리자 "이름" 아이디')
        return 1

    print(f"관리자 계정 {len(people)}개")
    print()
    머리 = ("id", "이름", "아이디", "상태")
    print(f"  {머리[0]:>3}  {머리[1]:<12} {머리[2]:<16} {머리[3]:<12} 계정")
    for p in people:
        print(f"  {p.id:>3}  {p.name:<12} {p.login_id or '-':<16}"
              f" {문상태(p):<12} {'활성' if p.is_active else '비활성'}")
    print()
    print("  비밀번호를 다시 만들 사람의 id 를 이렇게 줍니다:")
    print("    python scripts/계정문열기.py --재설정 <id>")
    return 0


def 첫관리자(db: Session, name: str, login_id: str) -> int:
    """갈래 ① — **이미 있으면 안 만들고 말한다.**

    관리자가 하나라도 있으면 이 길은 필요 없습니다. 그때 또 만들면 관리자
    계정이 불어나는데, 그것이 초대 링크 시절에 넷이 됐던 그 입구입니다 —
    같은 사람에게 알림이 그 수만큼 가고 담당자 목록에 같은 이름이 여러 번
    뜹니다(4-12). 비밀번호만 필요하면 갈래 ② 입니다.
    """
    있는사람 = perm.admins(db, active_only=False)
    if 있는사람:
        print(f"이미 관리자 계정이 {len(있는사람)}개 있습니다 — 만들지 않았습니다.")
        print("  비밀번호만 다시 만들려면 id 를 골라 이렇게 부르세요:")
        print("    python scripts/계정문열기.py --재설정 <id>")
        print()
        목록(db)
        # **거절은 1 로 끝낸다.** 이 파일의 다른 거절이 전부 1 이라,
        # 여기만 0 이면 부르는 쪽이 「만들었다」 와 구별할 수 없다 —
        # 실제로 그 어긋남 때문에 시험이 늘 참인 단언으로 적혔다(검토)
        return 1

    login_id = 로그인.아이디다듬기(login_id)
    if not login_id:
        print("아이디를 함께 주세요 — 이름의 로마자를 씁니다.")
        return 1
    # **규칙은 화면과 같은 것 하나다** — 여기만 지나가게 두면 규칙 밖
    # 아이디가 들어가고, 그 계정은 설정 › 사용자에서 저장이 안 된다(검토)
    if 로그인.아이디가이상한가(login_id):
        print(로그인.아이디안내)
        return 1
    if 로그인.아이디로찾기(db, login_id) is not None:
        print("그 아이디를 이미 쓰는 계정이 있습니다.")
        return 1

    person = User(name=name.strip(), role=perm.ADMIN, login_id=login_id)
    db.add(person)
    db.flush()
    raw = 로그인.첫비밀번호()
    로그인.비밀번호를정한다(db, person, raw, 첫판=True)
    # **누가 눌렀는지는 비운다** — 서버 앞에 앉은 사람이 누구인지 알 수 없다.
    # 받는 사람을 행위자로 적으면 「그 사람이 스스로 만들었다」 는 거짓이 남는다
    log_activity(db, retreat_id=None, actor=None, action="계정_생성",
                 target_type="user", target_id=person.id,
                 summary=f"{person.name} (첫 관리자 · 서버에서 만듦)")
    db.commit()
    보인다(raw, person)
    print("연락처와 부서는 들어간 뒤 설정 › 사용자에서 넣어주세요.")
    return 0


def 아이디를준다(db: Session, person: User, login_id: str) -> int:
    """`--재설정 <id> --아이디 <아이디>` — 아이디가 없는 관리자에게 붙인다."""
    login_id = 로그인.아이디다듬기(login_id)
    if 로그인.아이디가이상한가(login_id):
        print(로그인.아이디안내)
        return 1
    있는사람 = 로그인.아이디로찾기(db, login_id)
    if 있는사람 is not None and 있는사람.id != person.id:
        print(f"그 아이디는 이미 {있는사람.name} 님이 쓰고 있습니다 — 바꾸지 않았습니다.")
        return 1
    person.login_id = login_id
    db.commit()
    print(f"{person.name} 님의 아이디를 정했습니다.")
    return 0


def 재설정(db: Session, user_id: int) -> int:
    """갈래 ② — 있는 사람의 비밀번호를 다시 만든다.

    **관리자가 아니면 거절합니다.** 이 스크립트는 「관리자가 다시 들어갈 길」
    하나만 엽니다 — 아무 계정의 비밀번호나 만드는 자리가 되면, 서버 컴퓨터를
    잠깐 쓰는 사람이 아무나로 들어갈 수 있게 됩니다. 다른 사람의 비밀번호는
    화면(설정 › 사용자)에서 만듭니다.
    """
    person = db.get(User, user_id)
    if person is None:
        print(f"id {user_id} 인 계정이 없습니다. 인자 없이 불러 목록을 보세요.")
        return 1
    if person.role != perm.ADMIN:
        print(f"id {user_id} 는 관리자(admin)가 아닙니다 — 만들지 않았습니다.")
        print("  이 스크립트는 관리자가 다시 들어갈 길만 엽니다.")
        print("  다른 계정의 비밀번호는 들어간 뒤 설정 › 사용자에서 만드세요.")
        return 1
    if not person.is_active:
        print(f"id {user_id} 는 비활성 계정입니다 — 만들지 않았습니다.")
        print("  되살리는 것은 설정 › 사용자에서 합니다 (4-12).")
        return 1
    if not person.login_id:
        print(f"id {user_id} 는 아이디가 없습니다 — 비밀번호만 있어도 못 들어옵니다.")
        print("  아이디를 함께 주세요:")
        print(f"    python scripts/계정문열기.py --재설정 {user_id} --아이디 <아이디>")
        return 1

    raw = 로그인.첫비밀번호()
    로그인.비밀번호를정한다(db, person, raw, 첫판=True)
    log_activity(db, retreat_id=None, actor=None, action="첫_비밀번호_발급",
                 target_type="user", target_id=person.id,
                 summary=f"{person.name} 님의 비밀번호를 서버에서 다시 만들었습니다 (관리자 복구).")
    db.commit()
    보인다(raw, person)
    return 0


def 링크끊기(db: Session) -> int:
    """갈래 ③ — 살아 있는 옛 초대 링크를 전부 끊는다. **먼저 센다.**

    로그인이 아이디·비밀번호로 바뀐 뒤에도 `invite_tokens` 에 아직 안 쓴
    링크가 남아 있습니다. 지금은 `/invite/<토큰>` 이 토큰을 보지 않고
    로그인 화면으로 보내므로 그것으로 들어올 수는 없지만, **표에 「살아
    있음」 으로 남아 있으면 다음 사람이 그 문이 열려 있는 줄로 읽습니다.**
    행은 지우지 않고 `revoked_at` 만 찍습니다 (0장).
    """
    tokens = 옛링크.살아있는것들(db)
    if not tokens:
        print("살아 있는 초대 링크가 없습니다 — 끊을 것이 없습니다.")
        return 0
    print(f"살아 있는 초대 링크 {len(tokens)}개를 끊습니다.")
    끊은수 = 옛링크.전부끊는다(db)
    log_activity(db, retreat_id=None, actor=None, action="초대_링크_취소",
                 target_type="user", target_id=None,
                 summary=f"남아 있던 초대 링크 {끊은수}개를 끊었습니다 (로그인 판).")
    db.commit()
    print(f"{끊은수}개를 끊었습니다. 행은 지우지 않았습니다 — 누가 언제 들어왔는지가 거기 있습니다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="문을 여는 세 갈래 — 첫 관리자 · 비밀번호 다시 만들기 · 옛 링크 끊기.",
        epilog="인자 없이 부르면 관리자 목록을 찍습니다.",
    )
    ap.add_argument("--첫관리자", nargs=2, metavar=("이름", "아이디"),
                    help="관리자가 하나도 없을 때만 만듭니다")
    ap.add_argument("--재설정", type=int, metavar="id",
                    help="그 관리자의 비밀번호를 다시 만듭니다")
    ap.add_argument("--아이디", default="", metavar="아이디",
                    help="--재설정 과 함께: 아이디가 없는 관리자에게 붙입니다")
    ap.add_argument("--링크끊기", action="store_true",
                    help="살아 있는 옛 초대 링크를 전부 끊습니다 (먼저 셉니다)")
    args = ap.parse_args()

    고른것 = [bool(args.첫관리자), args.재설정 is not None, args.링크끊기]
    if sum(고른것) > 1:
        print("갈래는 한 번에 하나만 고르세요.")
        return 1

    # **`init_db()` 를 부르지 않는다.** 이 스크립트가 도는 때는 DB 가 이미
    # 있는 때뿐이고, 그 함수는 앱이 뜰 때 도는 한 번짜리 전환들을 함께
    # 부른다 — 비밀번호 하나 만들자고 그것들을 다시 밟을 이유가 없다.
    with SessionLocal() as db:
        try:
            if args.첫관리자:
                return 첫관리자(db, *args.첫관리자)
            if args.링크끊기:
                return 링크끊기(db)
            if args.재설정 is not None:
                if args.아이디:
                    person = db.get(User, args.재설정)
                    if person is None:
                        print(f"id {args.재설정} 인 계정이 없습니다.")
                        return 1
                    코드 = 아이디를준다(db, person, args.아이디)
                    if 코드:
                        return 코드
                return 재설정(db, args.재설정)
            return 목록(db)
        except OperationalError as exc:
            # **두 가지를 갈라 말한다.** 둘을 한 말로 묶으면 틀린 진단이
            # 나가고, 그때 그 사람은 정확히 「화면으로 돌아올 길이 없는」
            # 상태다 — 이 스크립트가 있는 이유가 그것이다(머리말).
            말 = str(exc)
            if "no such column" in 말 or "no such table: users" in 말 and "login" in 말:
                print("계정 표에 아이디·비밀번호 칸이 아직 없습니다.")
                print("  앱을 한 번 띄우면 부팅이 그 칸을 붙입니다 (4-12).")
                print("  작업 스케줄러의 앱을 켜거나 서버를 한 번 재시작한 뒤 다시 부르세요.")
                return 1
            # **데이터 폴더를 잘못 짚으면 sqlite 가 빈 파일을 만든다** — 그러면
            # 첫 조회에서 트레이스백으로 죽는다
            print("데이터베이스를 열었는데 표가 없습니다 — 빈 파일을 만든 것 같습니다.")
            print(f"  지금 보고 있는 곳: {config.DATABASE_URL}")
            print("  DCB_DATA_DIR 이 운영 데이터 폴더를 가리키는지 보고,")
            print("  앱이 한 번이라도 뜬 적 있는 폴더인지 확인하세요.")
            return 1


if __name__ == "__main__":
    sys.exit(main())
