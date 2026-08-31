"""실제 2026 여름수련회 Belong 데이터를 DB에 넣는 스크립트.

    .venv\\Scripts\\python.exe seed.py            # 데이터 생성
    .venv\\Scripts\\python.exe seed.py --reset    # 전부 지우고 다시 생성

원본은 seed_data.py 를 보세요 (구글시트 일정표 + 노션 업무 DB).
"""

from __future__ import annotations

import datetime as dt
import struct
import sys
import zlib

from sqlalchemy import select

import seed_data as D
import seed_library
import seed_library_data as L
from app.config import ASSET_DIR, DATA_DIR, DATABASE_URL
from app.db import Base, SessionLocal, engine, init_db
from app.domain.meal import calculate_meal_settlement
from app.models import (
    BudgetCategory,
    Checklist,
    ChecklistItem,
    Department,
    ExpenseEntry,
    FileAsset,
    FileVersion,
    Meeting,
    MeetingItem,
    Retreat,
    ReviewRequest,
    ScheduleDay,
    ScheduleItem,
    Task,
    User,
)


LEGACY_DEPARTMENTS = {
    "총무M": "chongmuM",
    "행정": "chongmu",
    "현장관리": "chongmu",
    "비품": "chongmu",
    "음식": "chongmu",
    "교역자": "chongmu",
    "봉사팀공통": "chongmu",
    "재정": "jaejeong",
    "선교사회": "seongyo",
    "스케치": "sketch",
    "헤브론": "hebron",
    "코람데오": "koram",
    "개기자": "gaegija",
    "새친구팀": "saechingu",
}


# ---------------------------------------------------------------- 데모 파일 생성


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def make_demo_png(path, *, width=480, height=640, top_rgb, bottom_rgb) -> int:
    """세로 그라데이션 PNG. 외부 라이브러리 없이 표준 라이브러리로 만든다."""
    rows = bytearray()
    for y in range(height):
        ratio = y / max(1, height - 1)
        pixel = bytes(
            int(top_rgb[i] + (bottom_rgb[i] - top_rgb[i]) * ratio) for i in range(3)
        )
        rows.append(0)
        rows.extend(pixel * width)

    data = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)
    return len(data)


def make_demo_xlsx(path, *, title: str, header: list, rows: list) -> int:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(header)
    for row in rows:
        ws.append(list(row))
    for column, width in zip("ABCDE", (12, 28, 14, 30, 14)):
        ws.column_dimensions[column].width = width
    wb.save(path)
    return path.stat().st_size


# ---------------------------------------------------------------- 시드


def seed(demo: bool = False) -> None:
    """기본값은 **실제 이력만** — 회차·부서·업무 라이브러리·지난 회차 실행 기록.

    계정은 만들지 않는다. 자리표시자 전화번호로 계정을 심어 두면 배포한 뒤에도
    그대로 남아, 아무도 안 쓰는 계정이 담당자 후보 목록에 섞인다.
    실제 계정은 총무팀이 `/admin/users` 에서 만들고 초대 링크를 보낸다 (4-12).

    `demo=True` 는 이전 설계 화면(할 일·회의록·지출·파일)을 눌러보기 위한 것이다.
    그 화면들이 작성자·담당자를 요구하므로 자리표시자 계정이 함께 만들어진다.
    """
    init_db()

    with SessionLocal() as db:
        if db.scalars(select(Retreat)).first():
            print("이미 데이터가 있습니다. 다시 만들려면 --reset 옵션을 쓰세요.")
            return

        retreat = Retreat(
            name=D.RETREAT_NAME,
            start_date=D.RETREAT_START,
            end_date=D.RETREAT_END,
            meal_subsidy_per_person=D.MEAL_SUBSIDY,
        )
        db.add(retreat)
        db.flush()

        # 부서 — CLAUDE.md 2장의 9개. 봉사팀 공통은 해체됐다.
        by_key: dict[str, Department] = {}
        for order, (key, name, color) in enumerate(L.DEPARTMENTS):
            dept = Department(
                retreat_id=retreat.id, key=key, name=name, color_tag=color, sort_order=order
            )
            db.add(dept)
            db.flush()
            by_key[key] = dept

        # 기존 시트/노션의 팀 이름 → 새 부서.
        # 행정·현장관리·비품·음식·교역자는 부서가 아니라 총무팀 안의 '파트'다.
        depts: dict[str, Department] = {
            legacy: by_key[key] for legacy, key in LEGACY_DEPARTMENTS.items()
        }

        if not demo:
            # 실제 이력만 — 준비 단계 보드와 세팅 마법사가 쓰는 것이 전부 여기 있다.
            seed_library.seed_all(db, retreat)
            db.commit()
            print(f"'{D.RETREAT_NAME}' 을(를) 만들었습니다. (실제 이력만)")
            print(f"  부서 {len(L.DEPARTMENTS)}개 · 업무 라이브러리 "
                  f"{len(L.LIBRARY) + len(L.LIBRARY_ONLY)}건 (실행 이력 1회차)")
            print("  계정은 만들지 않았습니다 — 첫 관리자는 아래로 만드세요:")
            print("    .venv\\Scripts\\python.exe scripts/create_admin.py \"이름\" 01012345678")
            return

        # 사용자 (demo 전용 — 자리표시자 번호다)
        users: dict[str, User] = {}
        for name, phone, role, dept_name in D.USERS:
            user = User(
                name=name,
                phone_number=phone,
                role=role,
                department_id=depts[dept_name].id if dept_name else None,
                bank_account=None,
            )
            db.add(user)
            db.flush()
            users[name] = user

        # 예산 항목
        cats: dict[tuple[str, str], BudgetCategory] = {}
        for order, (l1, l2, l3, amount) in enumerate(D.BUDGET_CATEGORIES):
            cat = BudgetCategory(
                retreat_id=retreat.id,
                level1=l1,
                level2=l2,
                level3=l3,
                planned_amount=amount,
                sort_order=order,
            )
            db.add(cat)
            db.flush()
            cats[(l1, l2)] = cat

        # 봉사자 일차별 시간표
        for order, day_data in enumerate(D.SCHEDULE_DAYS):
            day = ScheduleDay(
                retreat_id=retreat.id,
                label=day_data["label"],
                date=day_data["date"],
                sort_order=order,
            )
            db.add(day)
            db.flush()
            for start, end, title, place, dept_name in day_data["items"]:
                db.add(
                    ScheduleItem(
                        schedule_day_id=day.id,
                        title=title,
                        start_time=start,
                        end_time=end,
                        location=place,
                        department_id=depts[dept_name].id if dept_name else None,
                    )
                )

        # 할 일
        tasks: dict[str, Task] = {}
        for title, dept_name, date_str, status, stage in D.TASKS:
            assignee_name = D.DEPT_ASSIGNEE.get(dept_name)
            task = Task(
                retreat_id=retreat.id,
                title=title,
                description=f"[{stage}] 노션 · 전체팀 Main업무",
                department_id=depts[dept_name].id,
                assignee_id=users[assignee_name].id if assignee_name else None,
                due_date=dt.date.fromisoformat(date_str),
                status=status,
                blocked_by_task_ids=[],
                related_department_ids=[],
            )
            db.add(task)
            db.flush()
            tasks[title] = task

        # 선후행 의존성
        for follower_title, blocker_title in D.TASK_DEPENDENCIES:
            follower = tasks.get(follower_title)
            blocker = tasks.get(blocker_title)
            if follower is not None and blocker is not None:
                follower.blocked_by_task_ids = sorted(
                    set((follower.blocked_by_task_ids or []) + [blocker.id])
                )

        # 체크리스트
        for order, (name, dept_name, items) in enumerate(D.CHECKLISTS):
            checklist = Checklist(
                retreat_id=retreat.id,
                name=name,
                department_id=depts[dept_name].id,
                sort_order=order,
            )
            db.add(checklist)
            db.flush()
            for item_order, (label, quantity, checked) in enumerate(items):
                leader = users.get(D.DEPT_ASSIGNEE.get(dept_name, ""))
                db.add(
                    ChecklistItem(
                        checklist_id=checklist.id,
                        label=label,
                        quantity=quantity,
                        checked=checked,
                        checked_by_id=leader.id if (checked and leader) else None,
                        checked_by_name=leader.name if (checked and leader) else None,
                        checked_at=dt.datetime.now() if checked else None,
                        sort_order=item_order,
                    )
                )

        # 회의록
        for meeting_data in D.MEETINGS:
            meeting = Meeting(
                retreat_id=retreat.id,
                title=meeting_data["title"],
                meeting_date=meeting_data["date"],
                attendee_names=meeting_data["attendees"],
                body=meeting_data["body"],
                created_by_id=users["박민준"].id,
            )
            db.add(meeting)
            db.flush()
            for order, (kind, content, dept_name, who, due) in enumerate(
                meeting_data["items"]
            ):
                item = MeetingItem(
                    meeting_id=meeting.id,
                    kind=kind,
                    content=content,
                    department_id=depts[dept_name].id if dept_name else None,
                    assignee_id=users[who].id if who else None,
                    due_date=due,
                    sort_order=order,
                )
                # 이미 할 일로 등록된 액션아이템은 연결해 둔다
                if kind == "액션아이템" and content in tasks:
                    item.converted_task_id = tasks[content].id
                db.add(item)

        # 지출 — 식대
        receipt_no = 0
        meal_cat = cats[("그 외", "수련회 준비지원")]
        for dept_name, payer, account, amount, head, label, date in D.MEAL_EXPENSES:
            receipt_no += 1
            settlement = calculate_meal_settlement(
                amount=amount, headcount=head, per_person_cap=retreat.meal_subsidy_per_person
            )
            db.add(
                ExpenseEntry(
                    retreat_id=retreat.id,
                    budget_category_id=meal_cat.id,
                    level1=meal_cat.level1,
                    level2=meal_cat.level2,
                    level3a=meal_cat.level3,
                    level3b=label,
                    receipt_number=receipt_no,
                    expense_date=date,
                    amount=amount,
                    department_id=depts[dept_name].id,
                    payer_name=payer,
                    payer_account=account,
                    paid=False,
                    is_meal_expense=True,
                    meal_headcount=head,
                    meal_attendee_names=[],
                    subsidy_amount=settlement.subsidy_amount,
                    personal_burden_amount=settlement.personal_burden_amount,
                )
            )

        # 지출 — 일반
        for l1, l2, amount, payer, note, date, paid in D.GENERAL_EXPENSES:
            receipt_no += 1
            cat = cats[(l1, l2)]
            db.add(
                ExpenseEntry(
                    retreat_id=retreat.id,
                    budget_category_id=cat.id,
                    level1=cat.level1,
                    level2=cat.level2,
                    level3a=cat.level3,
                    receipt_number=receipt_no,
                    expense_date=date,
                    amount=amount,
                    payer_name=payer,
                    note=note,
                    paid=paid,
                    paid_date=date + dt.timedelta(days=2) if paid else None,
                    subsidy_amount=amount,
                )
            )

        # 작업 파일 (실제로 열리는 파일을 만들어 둔다)
        poster = FileAsset(
            retreat_id=retreat.id,
            department_id=depts["스케치"].id,
            task_id=tasks.get("포스터 확정").id if "포스터 확정" in tasks else None,
            title="수련회 포스터",
            description="A2 인쇄용 최종 시안",
            status="승인",
            created_by_id=users["박민준"].id,
        )
        db.add(poster)
        db.flush()
        for version_no, (name, note, days_ago, top, bottom) in enumerate(
            [
                ("poster_v1.png", "1차 시안 — 색감 확인 부탁", 78, (67, 56, 202), (14, 116, 144)),
                ("poster_v2.png", "2차 — 문구 수정 반영, 최종 확정", 71, (109, 40, 217), (219, 39, 119)),
            ],
            start=1,
        ):
            stored = f"demo-poster-v{version_no}.png"
            size = make_demo_png(ASSET_DIR / stored, top_rgb=top, bottom_rgb=bottom)
            db.add(
                FileVersion(
                    file_asset_id=poster.id,
                    version_no=version_no,
                    original_name=name,
                    stored_name=stored,
                    size_bytes=size,
                    note=note,
                    uploaded_by_id=users["박민준"].id,
                    uploaded_by_name="박민준",
                    uploaded_at=dt.datetime.now() - dt.timedelta(days=days_ago),
                )
            )

        cue = FileAsset(
            retreat_id=retreat.id,
            department_id=depts["헤브론"].id,
            title="1일차 집회 큐시트",
            description="집회1 (오세영 목사) 진행 큐시트",
            status="검토요청",
            created_by_id=users["박민준"].id,
        )
        db.add(cue)
        db.flush()
        cue_stored = "demo-cue-v1.xlsx"
        cue_size = make_demo_xlsx(
            ASSET_DIR / cue_stored,
            title="1일차 집회",
            header=["시간", "순서", "담당", "비고"],
            rows=[
                ("18:50", "송출 스탠바이", "헤브론", "18:00 리허설 시작"),
                ("19:00", "오프닝 찬양", "코람데오", "인이어 체크 완료"),
                ("19:20", "광고 및 공지", "총무팀", "롤링배너 교체"),
                ("19:30", "설교 — 오세영 목사", "선교사회", "무선마이크 2번"),
                ("20:30", "결단 찬양", "코람데오", "조명 어둡게"),
                ("21:00", "기도회1 안내", "최도현M", "새친구 힐링 30 안내"),
            ],
        )
        db.add(
            FileVersion(
                file_asset_id=cue.id,
                version_no=1,
                original_name="cue_sheet_v1.xlsx",
                stored_name=cue_stored,
                size_bytes=cue_size,
                note="초안",
                uploaded_by_id=users["박민준"].id,
                uploaded_by_name="박민준",
                uploaded_at=dt.datetime.now() - dt.timedelta(days=12),
            )
        )

        # 확인 요청 — 헤브론 큐시트를 코람데오에 확인 요청 (대기 중)
        db.add(
            ReviewRequest(
                retreat_id=retreat.id,
                file_asset_id=cue.id,
                department_id=depts["코람데오"].id,
                requester_id=users["박민준"].id,
                requester_name="박민준",
                message="집회1 찬양 순서와 시간 확인 부탁드립니다",
            )
        )

        db.commit()

        # 업무 라이브러리 + 지난 회차 실행 이력 (준비 단계 보드 · 세팅 마법사)
        seed_library.seed_all(db, retreat, demo=True)

    print(f"'{D.RETREAT_NAME}' 데이터를 만들었습니다.")
    print(f"  부서 {len(L.DEPARTMENTS)}개 · 사용자 {len(D.USERS) + len(seed_library.EXTRA_USERS)}명")
    print(f"  업무 라이브러리 {len(L.LIBRARY) + len(L.LIBRARY_ONLY)}건 (실행 이력 1회차)")
    print(f"  일정 {len(D.SCHEDULE_DAYS)}일차 / 총 {sum(len(d['items']) for d in D.SCHEDULE_DAYS)}건")
    print(f"  할 일 {len(D.TASKS)}건 · 체크리스트 {len(D.CHECKLISTS)}개 · 회의록 {len(D.MEETINGS)}건")
    print(f"  지출 {len(D.MEAL_EXPENSES) + len(D.GENERAL_EXPENSES)}건")
    print("\n※ demo 계정입니다. 전화번호는 자리표시자이고 로그인은 초대 링크로 합니다.")
    print("   초대 링크는 /admin/users 에서 발급합니다.")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        # 서버가 켜진 채로는 drop_all 이 파일을 완전히 비우지 못한다.
        # SQLite 는 파일째 지우는 것이 확실하다.
        engine.dispose()
        removed = False
        if DATABASE_URL.startswith("sqlite:///"):
            for path in (DATA_DIR / "app.db", DATA_DIR / "app.db-journal",
                         DATA_DIR / "app.db-wal", DATA_DIR / "app.db-shm"):
                if path.exists():
                    try:
                        path.unlink()
                        removed = True
                    except PermissionError:
                        print(f"  ! {path.name} 를 지울 수 없습니다 — 실행 중인 서버를 먼저 닫아주세요.")
                        raise SystemExit(1)
        if not removed:
            Base.metadata.drop_all(engine)
        for leftover in ASSET_DIR.glob("demo-*"):
            leftover.unlink()
        print("기존 데이터를 삭제했습니다.")
    seed(demo="--demo" in sys.argv)
