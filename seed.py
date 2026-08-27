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
        for title, dept_name, offset, status in TASKS:
            assignee = users.get(assignees.get(dept_name, ""))
            db.add(
                Task(
                    retreat_id=retreat.id,
                    title=title,
                    department_id=depts[dept_name].id,
                    assignee_id=assignee.id if assignee else None,
                    due_date=start + dt.timedelta(days=offset),
                    status=status,
                    blocked_by_task_ids=[],
                    related_department_ids=[],
                )
            )

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

    print("데모 데이터를 만들었습니다.")
    print("\n로그인용 전화번호 (개발 모드에서는 인증코드가 화면에 표시됩니다):")
    for name, phone, role, dept in USERS:
        print(f"  {phone}  {name:5s} {role:10s} {dept or '-'}")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        Base.metadata.drop_all(engine)
        print("기존 데이터를 삭제했습니다.")
    seed()
