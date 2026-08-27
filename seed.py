"""데모 데이터 생성 스크립트.

    .venv\\Scripts\\python.exe seed.py                 # 데모 데이터 추가
    .venv\\Scripts\\python.exe seed.py --reset         # DB 초기화 후 다시 생성

실제 운영 시작 전에 화면을 눌러보기 위한 용도입니다.
전화번호는 실제로 SMS가 가지 않는 개발 모드(DCB_DEV_MODE=1)에서만 의미가 있습니다.
"""

from __future__ import annotations

import datetime as dt
import sys

from sqlalchemy import select

from app.db import Base, SessionLocal, engine, init_db
from app.domain.meal import calculate_meal_settlement
from app.models import (
    BudgetCategory,
    Department,
    ExpenseEntry,
    Retreat,
    ScheduleDay,
    ScheduleItem,
    Task,
    User,
)

DEPARTMENTS = ["총무팀", "홍보팀", "찬양팀", "새가족팀", "미디어팀"]

CATEGORIES = [
    ("홍보", "포스터", "인쇄비", 300_000),
    ("홍보", "굿즈", "티셔츠", 1_200_000),
    ("시스템", "음향", "장비 렌탈", 800_000),
    ("장소비", "숙소", "리조트 대관", 4_000_000),
    ("식비", "본행사 식사", "자율배식", 2_500_000),
    ("강사료", "주강사", None, 700_000),
    ("그 외", "수련회 준비지원", "모임 식사비", 1_000_000),
]

USERS = [
    ("김총무", "01011112222", "admin", "총무팀"),
    ("이홍보", "01022223333", "dept_lead", "홍보팀"),
    ("박찬양", "01033334444", "dept_lead", "찬양팀"),
    ("최부원", "01044445555", "member", "홍보팀"),
    ("정전도사", "01055556666", "viewer", None),
]

SCHEDULE = [
    ("선발대", -1, [("14:00", "17:00", "숙소 세팅", "리조트 로비"), ("18:00", "19:00", "선발대 식사", "식당")]),
    ("1일차", 0, [("15:00", "16:00", "등록/입실", "리조트 로비"),
                  ("19:30", "21:30", "1일차 집회", "대강당"),
                  ("22:00", "23:00", "조모임", "각 숙소")]),
    ("2일차", 1, [("07:30", "08:30", "아침 식사", "식당"),
                  ("10:00", "12:00", "말씀 세미나", "대강당"),
                  ("14:00", "17:00", "레크리에이션", "운동장"),
                  ("19:30", "22:00", "2일차 집회", "대강당")]),
    ("3일차", 2, [("09:00", "10:30", "파송 예배", "대강당"), ("11:00", "12:00", "퇴실/정리", "숙소")]),
]

TASKS = [
    ("포스터 시안 확정", "홍보팀", -30, "완료"),
    ("포스터 인쇄 발주", "홍보팀", -20, "진행중"),
    ("굿즈 티셔츠 사이즈 취합", "홍보팀", -14, "대기"),
    ("음향 장비 렌탈 견적 비교", "미디어팀", -21, "완료"),
    ("찬양 콘티 확정", "찬양팀", -10, "진행중"),
    ("새가족 조편성", "새가족팀", -7, "대기"),
    ("숙소 최종 인원 통보", "총무팀", -5, "피드백요청"),
    ("차량 배차표 작성", "총무팀", -3, "대기"),
    ("강사님 사례비 준비", "총무팀", -2, "대기"),
    ("영수증 취합 및 정산", "총무팀", 7, "대기"),
]

MEAL_EXPENSES = [
    ("홍보팀", "이홍보", "국민 123456-01-123456", 130_600, 12, "모임 식사비-1", -25),
    ("홍보팀", "이홍보", "국민 123456-01-123456", 68_900, 9, "모임 식사비-2", -18),
    ("찬양팀", "박찬양", "신한 110-234-567890", 84_000, 8, "모임 식사비-1", -15),
]

GENERAL_EXPENSES = [
    ("홍보", "포스터", 285_000, "수련회계좌", "포스터 200부 인쇄", -19),
    ("시스템", "음향", 750_000, "수련회계좌", "음향 장비 3일 렌탈", -12),
    ("장소비", "숙소", 3_800_000, "수련회계좌", "리조트 대관 계약금", -40),
]


def seed() -> None:
    init_db()
    today = dt.date.today()

    with SessionLocal() as db:
        if db.scalars(select(Retreat)).first():
            print("이미 데이터가 있습니다. 초기화하려면 --reset 옵션을 쓰세요.")
            return

        retreat = Retreat(
            name="2026 여름수련회 Belong",
            start_date=today + dt.timedelta(days=30),
            end_date=today + dt.timedelta(days=32),
            meal_subsidy_per_person=8_000,
        )
        db.add(retreat)
        db.flush()

        depts = {}
        for i, name in enumerate(DEPARTMENTS):
            dept = Department(retreat_id=retreat.id, name=name, sort_order=i)
            db.add(dept)
            db.flush()
            depts[name] = dept

        cats = {}
        for i, (l1, l2, l3, amount) in enumerate(CATEGORIES):
            cat = BudgetCategory(
                retreat_id=retreat.id,
                level1=l1,
                level2=l2,
                level3=l3,
                planned_amount=amount,
                sort_order=i,
            )
            db.add(cat)
            db.flush()
            cats[(l1, l2)] = cat

        users = {}
        for name, phone, role, dept_name in USERS:
            user = User(
                name=name,
                phone_number=phone,
                role=role,
                department_id=depts[dept_name].id if dept_name else None,
                bank_account="국민 123456-01-123456" if role != "viewer" else None,
            )
            db.add(user)
            db.flush()
            users[name] = user

        start = retreat.start_date
        for order, (label, offset, items) in enumerate(SCHEDULE):
            day = ScheduleDay(
                retreat_id=retreat.id,
                label=label,
                date=start + dt.timedelta(days=offset),
                sort_order=order,
            )
            db.add(day)
            db.flush()
            for s, e, title, place in items:
                db.add(
                    ScheduleItem(
                        schedule_day_id=day.id,
                        title=title,
                        start_time=s,
                        end_time=e,
                        location=place,
                    )
                )

        assignees = {"홍보팀": "이홍보", "찬양팀": "박찬양", "총무팀": "김총무"}
        tasks_by_title = {}
        for title, dept_name, offset, status in TASKS:
            assignee = users.get(assignees.get(dept_name, ""))
            task = Task(
                retreat_id=retreat.id,
                title=title,
                department_id=depts[dept_name].id,
                assignee_id=assignee.id if assignee else None,
                due_date=start + dt.timedelta(days=offset),
                status=status,
                blocked_by_task_ids=[],
                related_department_ids=[],
            )
            db.add(task)
            db.flush()
            tasks_by_title[title] = task

        receipt_no = 0
        meal_cat = cats[("그 외", "수련회 준비지원")]
        for dept_name, payer, account, amount, head, label, offset in MEAL_EXPENSES:
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
                    expense_date=today + dt.timedelta(days=offset),
                    amount=amount,
                    department_id=depts[dept_name].id,
                    payer_name=payer,
                    payer_account=account,
                    paid=False,
                    is_meal_expense=True,
                    meal_headcount=head,
                    meal_attendee_names=["박민준", "홍성헌", "민주아"][: min(head, 3)],
                    subsidy_amount=settlement.subsidy_amount,
                    personal_burden_amount=settlement.personal_burden_amount,
                )
            )

        for l1, l2, amount, payer, note, offset in GENERAL_EXPENSES:
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
                    expense_date=today + dt.timedelta(days=offset),
                    amount=amount,
                    payer_name=payer,
                    note=note,
                    paid=True,
                    paid_date=today + dt.timedelta(days=offset + 2),
                    subsidy_amount=amount,
                )
            )

        db.commit()

        seed_phase2(db, retreat, depts, users, tasks_by_title, today)

    print("데모 데이터를 만들었습니다. (Phase 1 + Phase 2)")
    print("\n로그인용 전화번호 (개발 모드에서는 인증코드가 화면에 표시됩니다):")
    for name, phone, role, dept in USERS:
        print(f"  {phone}  {name:5s} {role:10s} {dept or '-'}")




# ==========================================================================
# Phase 2 데모 데이터
# ==========================================================================

CHECKLISTS = [
    ("1일차 집회 비품", "찬양팀", [
        ("무선마이크", "4개", True),
        ("마이크 배터리", "AA 20개", True),
        ("인이어 모니터", "2세트", False),
        ("보면대", "5개", False),
    ]),
    ("등록 데스크 준비물", "총무팀", [
        ("명찰 + 목걸이", "180개", True),
        ("네임펜", "10자루", False),
        ("현금 잔돈", "20만원", False),
        ("영수증 보관 파일", "1개", False),
    ]),
]

MEETING_ITEMS = [
    ("안건", "숙소 최종 인원 확정 시점", None, None, None),
    ("안건", "굿즈 티셔츠 발주 수량", None, None, None),
    ("결정사항", "숙소 인원은 7/10까지 확정해서 리조트에 통보한다", None, None, None),
    ("결정사항", "티셔츠는 여유분 10% 포함해서 발주한다", None, None, None),
    ("액션아이템", "인쇄소 견적 3곳 비교해서 공유", "홍보팀", "이홍보", -18),
    ("액션아이템", "티셔츠 사이즈 최종 취합", "홍보팀", "최부원", -14),
    ("액션아이템", "리조트에 최종 인원 통보", "총무팀", "김총무", -5),
]


def seed_phase2(db, retreat, depts, users, tasks_by_title, today):
    """선후행 의존성 · 확인 요청 · 파일 · 체크리스트 · 회의록 데모."""
    import datetime as _dt

    from app.models import (
        Checklist,
        ChecklistItem,
        FileAsset,
        FileVersion,
        Meeting,
        MeetingItem,
        ReviewRequest,
    )

    # 1) 선후행 의존성: 시안 확정 → 인쇄 발주 (선행이 아직 진행중이라 후행은 막힘)
    design = tasks_by_title.get("포스터 시안 확정")
    printing = tasks_by_title.get("포스터 인쇄 발주")
    goods = tasks_by_title.get("굿즈 티셔츠 사이즈 취합")
    if design and printing:
        printing.blocked_by_task_ids = [design.id]
    if printing and goods:
        # 인쇄 발주가 끝나야 굿즈 발주도 진행 (2단계 체인)
        goods.blocked_by_task_ids = [printing.id]

    # 2) 파일: 포스터 v1 → v2, 찬양팀에 확인 요청 대기 중
    poster = FileAsset(
        retreat_id=retreat.id,
        department_id=depts["홍보팀"].id,
        task_id=design.id if design else None,
        title="수련회 포스터",
        description="A2 인쇄용 최종 시안",
        status="검토요청",
        created_by_id=users["이홍보"].id,
    )
    db.add(poster)
    db.flush()

    from app.config import ASSET_DIR

    poster_versions = [
        # (원본 파일명, 메모, 며칠 전, 그라데이션 색 — 버전마다 실제로 다른 이미지)
        ("poster_v1.png", "1차 시안 — 색감 확인 부탁", 21, (31, 58, 95), (47, 125, 109)),
        ("poster_v2.png", "2차 — 문구 수정 반영", 14, (94, 52, 120), (214, 132, 74)),
    ]
    for version_no, (name, note, days_ago, top, bottom) in enumerate(poster_versions, start=1):
        stored_name = f"demo-poster-v{version_no}.png"
        size = make_demo_png(ASSET_DIR / stored_name, top_rgb=top, bottom_rgb=bottom)
        db.add(
            FileVersion(
                file_asset_id=poster.id,
                version_no=version_no,
                original_name=name,
                stored_name=stored_name,
                size_bytes=size,
                note=note,
                uploaded_by_id=users["이홍보"].id,
                uploaded_by_name="이홍보",
                uploaded_at=_dt.datetime.now() - _dt.timedelta(days=days_ago),
            )
        )

    cue = FileAsset(
        retreat_id=retreat.id,
        department_id=depts["찬양팀"].id,
        title="1일차 집회 큐시트",
        status="작업중",
        created_by_id=users["박찬양"].id,
    )
    db.add(cue)
    db.flush()

    cue_stored = "demo-cue-v1.xlsx"
    cue_size = make_demo_xlsx(
        ASSET_DIR / cue_stored,
        title="1일차 집회",
        rows=[
            ("19:30", "오프닝 찬양 3곡", "찬양팀", "인이어 체크 19:10"),
            ("19:50", "광고 및 공지", "총무팀", "PPT 준비"),
            ("20:00", "말씀", "주강사", "무선마이크 2번"),
            ("20:40", "결단 찬양", "찬양팀", "조명 어둡게"),
            ("21:10", "조모임 안내", "새가족팀", "조 편성표 배부"),
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
            uploaded_by_id=users["박찬양"].id,
            uploaded_by_name="박찬양",
        )
    )

    # 3) 확인 요청: 홍보팀 → 찬양팀 (대기), 홍보팀 → 미디어팀 (승인 완료)
    db.add(
        ReviewRequest(
            retreat_id=retreat.id,
            file_asset_id=poster.id,
            department_id=depts["찬양팀"].id,
            requester_id=users["이홍보"].id,
            requester_name="이홍보",
            message="포스터에 들어간 찬양팀 소개 문구 확인 부탁드려요",
        )
    )
    if design:
        db.add(
            ReviewRequest(
                retreat_id=retreat.id,
                task_id=design.id,
                department_id=depts["미디어팀"].id,
                requester_id=users["이홍보"].id,
                requester_name="이홍보",
                message="영상 썸네일도 같은 톤으로 갈지 확인 부탁",
                status="승인",
                responder_id=users["김총무"].id,
                responder_name="김총무",
                response_comment="같은 톤으로 진행하겠습니다",
                responded_at=_dt.datetime.now() - _dt.timedelta(days=3),
            )
        )

    # 4) 체크리스트
    for order, (name, dept_name, items) in enumerate(CHECKLISTS):
        checklist = Checklist(
            retreat_id=retreat.id,
            name=name,
            department_id=depts[dept_name].id,
            sort_order=order,
        )
        db.add(checklist)
        db.flush()
        for item_order, (label, quantity, checked) in enumerate(items):
            db.add(
                ChecklistItem(
                    checklist_id=checklist.id,
                    label=label,
                    quantity=quantity,
                    checked=checked,
                    checked_by_id=users["김총무"].id if checked else None,
                    checked_by_name="김총무" if checked else None,
                    checked_at=_dt.datetime.now() if checked else None,
                    sort_order=item_order,
                )
            )

    # 5) 회의록 + 액션아이템 (일부만 할 일로 전환된 상태 = 현실적인 모습)
    meeting = Meeting(
        retreat_id=retreat.id,
        title="3차 총무팀 준비 회의",
        meeting_date=today - _dt.timedelta(days=20),
        attendee_names=["김총무", "이홍보", "박찬양", "최부원"],
        body="예산 집행 현황 공유 후 부서별 준비 상황 점검.\n숙소·식사 관련 결정 필요 사항 정리.",
        created_by_id=users["김총무"].id,
    )
    db.add(meeting)
    db.flush()

    for order, (kind, content, dept_name, assignee_name, offset) in enumerate(MEETING_ITEMS):
        db.add(
            MeetingItem(
                meeting_id=meeting.id,
                kind=kind,
                content=content,
                department_id=depts[dept_name].id if dept_name else None,
                assignee_id=users[assignee_name].id if assignee_name else None,
                due_date=(today + _dt.timedelta(days=offset)) if offset else None,
                sort_order=order,
            )
        )

    db.commit()


# --------------------------------------------------------------------------
# 데모용 실제 파일 생성
#
# 예전에는 파일명과 크기만 DB에 넣고 디스크에는 아무것도 쓰지 않아서,
# 데모 파일을 내려받으면 404가 났고 화면에는 없는 파일의 크기가 표시됐다.
# 이제는 실제로 열리는 파일을 만들어 두고, 기록하는 크기도 실제 크기를 쓴다.
# 외부 라이브러리를 새로 늘리지 않으려고 PNG는 표준 라이브러리로 직접 만든다.
# --------------------------------------------------------------------------


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    import struct
    import zlib

    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def make_demo_png(path, *, width=480, height=640, top_rgb=(31, 58, 95), bottom_rgb=(47, 125, 109)) -> int:
    """세로 그라데이션 PNG 를 만든다. 실제로 열리는 이미지 파일."""
    import struct
    import zlib

    rows = bytearray()
    for y in range(height):
        ratio = y / max(1, height - 1)
        pixel = bytes(
            int(top_rgb[i] + (bottom_rgb[i] - top_rgb[i]) * ratio) for i in range(3)
        )
        rows.append(0)  # 필터 타입 (None)
        rows.extend(pixel * width)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)
    return len(data)


def make_demo_xlsx(path, *, title: str, rows: list) -> int:
    """실제로 엑셀에서 열리는 큐시트 파일."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(["시간", "순서", "담당", "비고"])
    for row in rows:
        ws.append(list(row))
    for column, width in zip("ABCD", (12, 24, 12, 28)):
        ws.column_dimensions[column].width = width
    wb.save(path)
    return path.stat().st_size


if __name__ == "__main__":
    if "--reset" in sys.argv:
        Base.metadata.drop_all(engine)
        print("기존 데이터를 삭제했습니다.")
    seed()
