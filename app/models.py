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


# ==========================================================================
# Phase 2 — 안전망 강화
# ==========================================================================

FILE_STATUSES = ("작업중", "검토요청", "승인", "반려")
REVIEW_STATUSES = ("대기", "승인", "반려")
MEETING_ITEM_KINDS = ("안건", "결정사항", "액션아이템")


class Notification(Base):
    """앱 안에서 보이는 알림.

    웹 푸시가 실패하거나 구독을 안 한 사용자도 놓치지 않도록,
    푸시와 별개로 항상 DB에 남긴다. (단일 실패점 제거 원칙)
    """

    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    retreat_id: Mapped[int | None] = mapped_column(
        ForeignKey("retreats.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 같은 상황으로 매일 중복 알림이 쌓이지 않게 하는 키
    dedupe_key: Mapped[str] = mapped_column(String(120))
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    pushed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)

    user: Mapped[User] = relationship()


class PushSubscription(Base):
    """브라우저 웹 푸시 구독 정보."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(500), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    last_failed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship()


class FileAsset(Base):
    """부서별 작업 파일 (포스터·큐시트·영상 등). 버전 이력을 갖는다."""

    __tablename__ = "file_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    retreat_id: Mapped[int] = mapped_column(ForeignKey("retreats.id", ondelete="CASCADE"))
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="작업중")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    department: Mapped[Department | None] = relationship()
    task: Mapped[Task | None] = relationship()
    versions: Mapped[list[FileVersion]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
        order_by="FileVersion.version_no.desc()",
    )

    @property
    def latest(self) -> FileVersion | None:
        return self.versions[0] if self.versions else None


class FileVersion(Base):
    __tablename__ = "file_versions"
    __table_args__ = (UniqueConstraint("file_asset_id", "version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    file_asset_id: Mapped[int] = mapped_column(
        ForeignKey("file_assets.id", ondelete="CASCADE")
    )
    version_no: Mapped[int] = mapped_column(Integer)
    original_name: Mapped[str] = mapped_column(String(300))
    stored_name: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    asset: Mapped[FileAsset] = relationship(back_populates="versions")


class ReviewRequest(Base):
    """부서 간 확인 요청 — 할 일 또는 파일에 대해 관련 부서의 승인/반려를 받는다."""

    __tablename__ = "review_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    retreat_id: Mapped[int] = mapped_column(ForeignKey("retreats.id", ondelete="CASCADE"))
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    file_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("file_assets.id", ondelete="CASCADE"), nullable=True
    )
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE")
    )
    requester_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requester_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="대기")
    responder_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    responder_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    response_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    task: Mapped[Task | None] = relationship()
    file_asset: Mapped[FileAsset | None] = relationship()
    department: Mapped[Department] = relationship()

    @property
    def subject(self) -> str:
        if self.task is not None:
            return self.task.title
        if self.file_asset is not None:
            return self.file_asset.title
        return "(삭제된 항목)"


class Checklist(Base):
    """비품·준비물 체크리스트. Task와 별개지만 Task에 종속시킬 수도 있다."""

    __tablename__ = "checklists"

    id: Mapped[int] = mapped_column(primary_key=True)
    retreat_id: Mapped[int] = mapped_column(ForeignKey("retreats.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    department: Mapped[Department | None] = relationship()
    task: Mapped[Task | None] = relationship()
    items: Mapped[list[ChecklistItem]] = relationship(
        back_populates="checklist",
        cascade="all, delete-orphan",
        order_by="ChecklistItem.sort_order, ChecklistItem.id",
    )

    @property
    def checked_count(self) -> int:
        return sum(1 for item in self.items if item.checked)

    @property
    def progress_pct(self) -> float:
        if not self.items:
            return 0.0
        return round(self.checked_count / len(self.items) * 100, 1)


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_id: Mapped[int] = mapped_column(
        ForeignKey("checklists.id", ondelete="CASCADE")
    )
    label: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    checked_by_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    checked_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    checklist: Mapped[Checklist] = relationship(back_populates="items")


class Meeting(Base):
    """회의록. 수련회와 무관한 일반 회의도 담을 수 있게 retreat_id는 선택."""

    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    retreat_id: Mapped[int | None] = mapped_column(
        ForeignKey("retreats.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    meeting_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    attendee_names: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    items: Mapped[list[MeetingItem]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="MeetingItem.sort_order, MeetingItem.id",
    )


class MeetingItem(Base):
    """안건 / 결정사항 / 액션아이템. 액션아이템은 Task로 전환할 수 있다."""

    __tablename__ = "meeting_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20), default="안건")
    content: Mapped[str] = mapped_column(Text)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    converted_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    meeting: Mapped[Meeting] = relationship(back_populates="items")
    department: Mapped[Department | None] = relationship()
    assignee: Mapped[User | None] = relationship()
    converted_task: Mapped[Task | None] = relationship()
