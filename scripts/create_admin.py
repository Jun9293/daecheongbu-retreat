"""첫 관리자 계정을 만들고 초대 링크를 한 번 출력한다.

계정 관리 화면(/admin/users)에 들어가려면 이미 관리자여야 하므로, 맨 처음
한 사람만 여기서 만든다. 그 뒤로는 전부 화면에서 한다.

    .venv\\Scripts\\python.exe scripts/create_admin.py "박민준" 01012345678
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

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                    # noqa: E402

from app.db import SessionLocal, init_db                         # noqa: E402
from app.domain import auth as invites                           # noqa: E402
from app.models import User                                      # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print('쓰는 법:  python scripts/create_admin.py "이름" 01012345678')
        return 1

    name = sys.argv[1].strip()
    phone = "".join(ch for ch in sys.argv[2] if ch.isdigit())
    if not name or not phone:
        print("이름과 연락처를 모두 넣어주세요.")
        return 1

    init_db()
    with SessionLocal() as db:
        person = db.scalars(select(User).where(User.phone_number == phone)).first()
        if person is None:
            person = User(name=name, phone_number=phone, role="admin")
            db.add(person)
            db.commit()
            print(f"'{name}' 관리자 계정을 만들었습니다.")
        else:
            person.role = "admin"
            person.is_active = True
            db.commit()
            print(f"'{person.name}' 을(를) 관리자로 바꿨습니다.")

        raw = invites.issue(db, user=person)

    print()
    print("아래 주소를 브라우저에서 여시면 로그인됩니다.")
    print("이 링크는 지금 한 번만 보입니다 — 원문을 저장하지 않기 때문입니다.")
    print(f"  https://<내-주소>/invite/{raw}")
    print()
    print(f"유효기간 {invites.INVITE_TTL_DAYS}일 · 한 번 쓰면 만료됩니다.")
    print("다시 필요하면 이 명령을 한 번 더 실행하면 새 링크가 나옵니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
