"""데이터 모델 (CLAUDE.md 2장 스키마 기준)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import DEFAULT_MEAL_SUBSIDY_PER_PERSON
from app.db import Base

TASK_STATUSES = ("대기", "진행중", "피드백요청", "완료", "지연")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


class Retreat(Base):
    __tablename__ = "retreats"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    cloned_from_retreat_id: Mapped[int | None] = mapped_column(
        ForeignKey("retreats.id"), nullable=True
    )
    meal_subsidy_per_person: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_MEAL_SUBSIDY_PER_PERSON
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    departments: Mapped[list[Department]] = relationship(
        back_populates="retreat",
        cascade="all, delete-orphan",
        order_by="Department.sort_order",
    )
    budget_categories: Mapped[list[BudgetCategory]] = relationship(
        back_populates="retreat",
        cascade="all, delete-orphan",
        order_by="BudgetCategory.sort_order",
    )
    schedule_days: Mapped[list[ScheduleDay]] = relationship(
        back_populates="retreat",
        cascade="all, delete-orphan",
        order_by="ScheduleDay.sort_order",
    )
    tasks: Mapped[list[Task]] = relationship(
        back_populates="retreat", cascade="all, delete-orphan"
    )
    expenses: Mapped[list[ExpenseEntry]] = relationship(
        back_populates="retreat", cascade="all, delete-orphan"
    )


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    retreat_id: Mapped[int] = mapped_column(ForeignKey("retreats.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    color_tag: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    retreat: Mapped[Retreat] = relationship(back_populates="departments")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(50))
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(20), default="member")
    bank_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    department: Mapped[Department | None] = relationship()


class AuthCode(Base):
    """전화번호 SMS 인증코드."""

    __tablename__ = "auth_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class BudgetCategory(Base):
    __tablename__ = "budget_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    retreat_id: Mapped[int] = mapped_column(ForeignKey("retreats.id", ondelete="CASCADE"))
    level1: Mapped[str] = mapped_column(String(100))  # 구분
    level2: Mapped[str] = mapped_column(String(100))  # 항목
    level3: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 세부항목
    planned_amount: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    retreat: Mapped[Retreat] = relationship(back_populates="budget_categories")
    expenses: Mapped[list[ExpenseEntry]] = relationship(back_populates="budget_category")

    @property
    def display_name(self) -> str:
        parts = [self.level1, self.level2]
        if self.level3:
            parts.append(self.level3)
        return " > ".join(p for p in parts if p)


class ExpenseEntry(Base):
    __tablename__ = "expense_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    retreat_id: Mapped[int] = mapped_column(ForeignKey("retreats.id", ondelete="CASCADE"))
    budget_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("budget_categories.id", ondelete="SET NULL"), nullable=True
    )
    # 기존 시트의 3단 세부항목 구조 그대로 보존
    level1: Mapped[str | None] = mapped_column(String(100), nullable=True)
    level2: Mapped[str | None] = mapped_column(String(100), nullable=True)
    level3a: Mapped[str | None] = mapped_column(String(100), nullable=True)
    level3b: Mapped[str | None] = mapped_column(String(100), nullable=True)
    level3c: Mapped[str | None] = mapped_column(String(100), nullable=True)

    receipt_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expense_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[int] = mapped_column(Integer, default=0)

    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    payer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    payer_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payer_account: Mapped[str | None] = mapped_column(String(100), nullable=True)

    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_file_url: Mapped[str | None] = mapped_column(String(300), nullable=True)

    is_meal_expense: Mapped[bool] = mapped_column(Boolean, default=False)
    meal_headcount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meal_attendee_names: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    subsidy_amount: Mapped[int] = mapped_column(Integer, default=0)
    personal_burden_amount: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    retreat: Mapped[Retreat] = relationship(back_populates="expenses")
    budget_category: Mapped[BudgetCategory | None] = relationship(back_populates="expenses")
    department: Mapped[Department | None] = relationship()

    @property
    def settlement_amount(self) -> int:
        """예산에서 실제로 집행되는 금액.

        식대는 지원금액만 수련회 예산에서 나가고 초과분은 개인부담이다.
        """
        return self.subsidy_amount if self.is_meal_expense else self.amount


class ScheduleDay(Base):
    __tablename__ = "schedule_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    retreat_id: Mapped[int] = mapped_column(ForeignKey("retreats.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(50))
    date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    retreat: Mapped[Retreat] = relationship(back_populates="schedule_days")
    items: Mapped[list[ScheduleItem]] = relationship(
        back_populates="day",
        cascade="all, delete-orphan",
        order_by="ScheduleItem.start_time",
    )


class ScheduleItem(Base):
    __tablename__ = "schedule_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_day_id: Mapped[int] = mapped_column(
        ForeignKey("schedule_days.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(200))
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM"
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )

    day: Mapped[ScheduleDay] = relationship(back_populates="items")
    department: Mapped[Department | None] = relationship()
    tasks: Mapped[list[Task]] = relationship(back_populates="schedule_item")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    retreat_id: Mapped[int] = mapped_column(ForeignKey("retreats.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    schedule_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedule_items.id", ondelete="SET NULL"), nullable=True
    )
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="대기")
    # Phase 2에서 UI/자동 상태 전환 로직을 붙인다. Phase 1은 데이터 구조만 마련.
    blocked_by_task_ids: Mapped[list[int] | None] = mapped_column(JSON, default=list)
    related_department_ids: Mapped[list[int] | None] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    retreat: Mapped[Retreat] = relationship(back_populates="tasks")
    department: Mapped[Department | None] = relationship()
    assignee: Mapped[User | None] = relationship()
    schedule_item: Mapped[ScheduleItem | None] = relationship(back_populates="tasks")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    retreat_id: Mapped[int | None] = mapped_column(
        ForeignKey("retreats.id", ondelete="CASCADE"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(20), default="user")  # user | claude
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(50))
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


class UserRetreatState(Base):
    """사용자가 마지막으로 보던 회차 (로그인 후 기본 화면용)."""

    __tablename__ = "user_retreat_states"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    retreat_id: Mapped[int] = mapped_column(ForeignKey("retreats.id", ondelete="CASCADE"))
