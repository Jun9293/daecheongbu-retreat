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

# 준비 단계 보드의 업무 분류 (CLAUDE.md 4-2)
TASK_KINDS = ("main", "sub", "schedule")
TASK_KIND_LABELS = {"main": "Main", "sub": "하위", "schedule": "일정"}

# 보드에서 쓰는 상태 (TASK_STATUSES 중 '피드백요청'을 뺀 4개)
RUN_STATUSES = ("대기", "진행중", "완료", "지연")


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
    # 회차가 바뀌어도 같은 부서임을 알아보기 위한 영속 식별자 (chongmuM, sketch ...).
    # 라이브러리 업무는 부서를 이 키로 가리킨다.
    key: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    color_tag: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    retreat: Mapped[Retreat] = relationship(back_populates="departments")

    @property
    def color(self) -> str:
        return self.color_tag or "#69726D"


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


# ==========================================================================
# 준비 단계 보드 — 업무 라이브러리(영속) + 회차별 실행 기록
# CLAUDE.md 6-1: TaskLibrary ──< TaskRun >── Retreat
# ==========================================================================


class TaskLibrary(Base):
    """회차에 속하지 않고 계속 남는 업무 정의.

    이번 회차에 하지 않아도 삭제하지 않는다. 실행 여부는 TaskRun.included 로만
    기록한다 — 그 기록이 다음 회차의 자동 분류 입력값이 된다.
    """

    __tablename__ = "task_library"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="main")  # main|sub|schedule
    parent_library_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_library.id", ondelete="SET NULL"), nullable=True
    )

    # 담당 부서는 회차마다 새로 만들어지므로 영속 키로 가리킨다
    default_department_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # 관련팀 (보드에서 점선 고스트 바로 나타날 부서들)
    related_department_keys: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    # 관련업무 — 방향이 없다. 양쪽에 서로 적는다.
    related_library_ids: Mapped[list[int] | None] = mapped_column(JSON, default=list)
    # 선행업무 — 방향이 있다. "저쪽이 끝나야 이쪽을 시작할 수 있다".
    # 가진 쪽에만 적는다. 양쪽에 적으면 한쪽만 지워졌을 때 어느 쪽이 맞는지 알 수 없다.
    # 후속("나를 기다리는 업무")은 저장하지 않고 조회할 때 계산한다.
    prerequisite_library_ids: Mapped[list[int] | None] = mapped_column(JSON, default=list)

    # ── 날짜의 상대 위치 (CLAUDE.md 6-4) ───────────────────────────────
    # anchor='week' → D-주차 일요일 기준 / 'open' → 개회일 기준
    date_anchor: Mapped[str] = mapped_column(String(10), default="week")
    default_d_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_offset_days: Mapped[int] = mapped_column(Integer, default=0)
    default_span_days: Mapped[int] = mapped_column(Integer, default=0)

    # 총무팀이 손으로 "이건 매 회차 반드시"라고 지정한 업무.
    # 실행 이력이 얕거나 아예 없어도 구멍 방지 경고가 작동하게 하는 장치다.
    always_required: Mapped[bool] = mapped_column(Boolean, default=False)

    origin: Mapped[str] = mapped_column(String(20), default="history")  # history|claude_suggestion
    suggestion_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 노션에서 옮기며 담당·분류를 바꾼 이유 (다음 담당자에게 남기는 기록)
    reclassification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 이 업무를 어떻게 진행하는지 — 회차가 바뀌어도 그대로 가는 규칙.
    # 논의는 그 회차의 사정이고, 규칙은 매번 같은 방식으로 하기 위한 것이다.
    rules: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    parent: Mapped[TaskLibrary | None] = relationship(remote_side="TaskLibrary.id")
    runs: Mapped[list[TaskRun]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )

    @property
    def kind_label(self) -> str:
        return TASK_KIND_LABELS.get(self.kind, self.kind)


class TaskRun(Base):
    """어떤 회차에서 그 업무를 실제로 어떻게 실행했는지."""

    __tablename__ = "task_runs"
    __table_args__ = (UniqueConstraint("library_id", "retreat_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("task_library.id", ondelete="CASCADE"), index=True
    )
    retreat_id: Mapped[int] = mapped_column(
        ForeignKey("retreats.id", ondelete="CASCADE"), index=True
    )
    # False 여도 행을 지우지 않는다. "이번엔 하지 않았다"는 것도 기록이다.
    included: Mapped[bool] = mapped_column(Boolean, default=True)

    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    d_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="대기")
    # 착수한 날. 상태가 '대기' 에서 처음 벗어날 때 찍고 되돌려도 지우지 않는다 —
    # 착수했다는 사실은 사라지지 않는다. 진단 패널이 '진행 불가' 와
    # '일부 진행 가능' 을 가르는 근거이며, 상태로 보면 담당자가 상태를 바꾸는
    # 것만으로 판정이 움직인다.
    started_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    blocked_by_run_ids: Mapped[list[int] | None] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    library: Mapped[TaskLibrary] = relationship(back_populates="runs")
    retreat: Mapped[Retreat] = relationship()
    department: Mapped[Department | None] = relationship()
    assignee: Mapped[User | None] = relationship()
    discussions: Mapped[list[DiscussionEntry]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="DiscussionEntry.authored_at, DiscussionEntry.id",
    )

    @property
    def title(self) -> str:
        return self.library.title


class DiscussionEntry(Base):
    """업무 하나에 쌓이는 논의 기록.

    기존 내용을 지우지 않고, 바뀐 내용을 새 기록으로 붙인다(supersedes).
    화면에서는 대체된 기록에 취소선이 그어진다 — 노션에서 쓰던 관례.
    """

    __tablename__ = "discussion_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), index=True
    )
    authored_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    supersedes_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("discussion_entries.id", ondelete="SET NULL"), nullable=True
    )
    # 이전 회차에서 참고용으로 따라온 기록 (기본은 접힌 상태로 보여준다)
    carried_from_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    run: Mapped[TaskRun] = relationship(back_populates="discussions")


# ==========================================================================
# 회차 준비 초안 — 각 팀이 자기 업무를 고르고, 총무팀이 모아 회차를 연다
# ==========================================================================

DRAFT_STATUSES = ("수집중", "생성완료", "취소")


class RetreatDraft(Base):
    """아직 회차가 되지 않은 준비 상태.

    총무팀이 혼자 다 고르면 각 팀의 사정이 반영되지 않는다. 회차 정보와 부서만
    먼저 정해 두고, 업무 선택은 각 팀에게 맡긴 뒤 모아서 연다.
    """

    __tablename__ = "retreat_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    open_date: Mapped[dt.date] = mapped_column(Date)
    close_date: Mapped[dt.date] = mapped_column(Date)
    meal_subsidy_per_person: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_MEAL_SUBSIDY_PER_PERSON
    )
    department_keys: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="수집중")
    created_retreat_id: Mapped[int | None] = mapped_column(
        ForeignKey("retreats.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    submissions: Mapped[list[DraftSubmission]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        order_by="DraftSubmission.id",
    )

    @property
    def is_open(self) -> bool:
        return self.status == "수집중"


class DraftSubmission(Base):
    """한 부서가 이번 회차에 하겠다고 고른 업무."""

    __tablename__ = "draft_submissions"
    __table_args__ = (UniqueConstraint("draft_id", "department_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("retreat_drafts.id", ondelete="CASCADE"), index=True
    )
    department_key: Mapped[str] = mapped_column(String(40))
    library_ids: Mapped[list[int] | None] = mapped_column(JSON, default=list)
    adopted_titles: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 임시저장은 saved_at 만, 제출까지 하면 submitted_at 이 찍힌다
    saved_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_by_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    draft: Mapped[RetreatDraft] = relationship(back_populates="submissions")

    @property
    def state(self) -> str:
        if self.submitted_at:
            return "제출"
        if self.saved_at:
            return "작성중"
        return "대기"
