"""데이터 모델 (CLAUDE.md 2장 스키마 기준)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
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


# 번호를 놓은 상태 (4-12). NULL 이 아니라 빈 문자열인 이유는 쓰던 SQLite 파일의
# `phone_number` 가 NOT NULL 이라서다 — 컬럼을 NULL 허용으로 바꾸려면 표를 통째로
#다시 만들어야 하는데, 운영 중인 파일에 그런 위험을 지울 이유가 없다.
NO_PHONE = ""


class User(Base):
    __tablename__ = "users"
    # **활성·비활성을 가리지 않고 '번호를 쥔 계정' 끼리만 겹치지 않으면 된다.**
    # 비활성 계정은 번호를 놓으므로(NO_PHONE) 여럿이 될 수 있고, 그래서 전체
    # 유니크가 아니라 **번호가 있는 행만** 보는 부분 인덱스를 쓴다.
    __table_args__ = (
        Index(
            "ix_users_phone_held",
            "phone_number",
            unique=True,
            sqlite_where=text("phone_number != ''"),
            postgresql_where=text("phone_number != ''"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 비었을 수 있다 — 비활성 계정은 번호를 놓는다. **로그인은 초대 링크로 하지
    # 번호로 하지 않으므로** 번호가 없어도 계정은 멀쩡하다.
    phone_number: Mapped[str] = mapped_column(String(20), default=NO_PHONE)
    # 놓기 전에 쓰던 번호. 되살릴 때 돌려주기 위한 것이고, 화면에서 "누구였는지"
    # 를 보여주는 근거이기도 하다 — 빈 칸으로 두면 알 수 없다.
    retired_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str] = mapped_column(String(50))
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(20), default="member")
    bank_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    department: Mapped[Department | None] = relationship()

    @property
    def holds_phone(self) -> bool:
        """번호를 쥐고 있는가. 겹침 검사는 이것이 참인 계정끼리만 한다."""
        return bool(self.phone_number)

    @property
    def shown_phone(self) -> str:
        """화면에 보일 번호. 놓았으면 원래 번호를 돌려준다 (표시용)."""
        return self.phone_number or (self.retired_phone or "")


class InviteToken(Base):
    """1회용 초대 링크 (CLAUDE.md 4-12).

    **원문을 저장하지 않는다.** 해시만 남기고 원문은 발급 화면에서 한 번만 보여준다 —
    DB 가 새면 링크가 그대로 새는 구조로 만들지 않기 위해서다.
    """

    __tablename__ = "invite_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    user: Mapped[User] = relationship(foreign_keys=[user_id])


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


class NotificationLog(Base):
    """푸시로 무엇을 보냈는지. 같은 말을 반복하지 않기 위한 기록 (CLAUDE.md 4-11).

    payload 에 그때의 상태와 판정을 남긴다 — 사정이 바뀌면 다시 보내야 하는데,
    무엇이 바뀌었는지 알려면 그때 무엇이었는지가 있어야 한다.
    """

    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("task_runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    sent_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, default=dict)

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
    # 실제로 끝난 날. end_date 는 계획된 마감이라 3주 늦게 끝나도 그 날짜로 읽힌다.
    # started_at 과 달리 '완료' 를 벗어나면 지운다 — 착수는 사실이지만 완료는 취소된다.
    completed_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
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
    # 회차별이다 — 새 회차의 run 은 자기 파일을 처음부터 다시 쌓는다
    attachments: Mapped[list[TaskAttachment]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="TaskAttachment.uploaded_at, TaskAttachment.id",
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
# 수련회 진행 (CLAUDE.md 5장)
#
# 준비 보드와 성격이 다르다. 보드는 몇 달에 걸쳐 천천히 보는 것이고, 이것은
# 현장에서 휴대폰으로 급히 보는 것이다 — 사람이 뛰어다니면서 한 손으로 누른다.
# ==========================================================================

# 일자 — 회차 길이에서 계산한다(app/domain/live.py). 여기엔 이름만 남긴다.
PROGRAM_DAYS = ("선발대", "1일차", "2일차", "폐회")

# 전 / 중 / 후 (5-2)
PROGRAM_PHASES = ("pre", "mid", "post")
PHASE_LABELS = {"pre": "준비", "mid": "진행", "post": "정리"}

# 총무팀 파트 (5-3) — 실제 일자별 시트의 열 구성 그대로.
# 여기에 봉사팀(헤브론·코람데오)이 맡는 항목이 더해진다.
PROGRAM_PARTS = (
    "행정", "현장관리", "비품", "음식", "재정", "교역자", "헤브론", "코람데오",
)

# 범위 (5-2) — 팀이 통째로 움직이는 것과 개인에게 붙는 것.
# 시트에서 온 구분이다: 봉사자 열은 "헤브론 집합"처럼 팀이 움직이고,
# 총무팀 파트 열은 "인원계수_온"처럼 개인 이름까지 붙는다.
PROGRAM_SCOPES = ("team", "person")

# 참가자가 함께하는가 (5-8). 전체일정 칸으로 갈지 봉사자 칸으로 갈지를 가른다.
PROGRAM_AUDIENCES = ("all", "staff")
# 정규 흐름인가, 총무팀이 뒤에서 돌리는 일인가.
# `ops` 는 봉사자 시간표에 넣지 않는다 — 그것이 그 표의 이유다.
PROGRAM_TRACKS = ("main", "ops")
SCOPE_LABELS = {"team": "팀", "person": "개인"}

# 화면에서 프로그램을 만들 때 이 셋을 고른다 (5-1).
# **뜻을 사람 말로 적어 둔다** — `audience=staff` 를 보고 무엇인지 알 수 있는
# 사람은 이걸 만든 사람뿐이다. 목록과 설명을 한자리에 두어야 한쪽만 늘지 않는다.
AUDIENCE_LABELS = {"all": "참가자와 함께", "staff": "봉사자만"}
AUDIENCE_HINTS = {
    "all": "참가자가 함께하는 일정입니다 — 봉사자 시간표의 전체일정 칸에 섭니다.",
    "staff": "봉사자끼리 하는 일입니다 — 봉사자 칸에 섭니다.",
}
TRACK_LABELS = {"main": "정규일정", "ops": "총무팀 작업"}
TRACK_HINTS = {
    "main": "시간표에 드러나는 일정입니다.",
    "ops": "뒤에서 도는 일입니다 — 봉사자 시간표에 넣지 않습니다.",
}
PARALLEL_HINT = "정규 일정 옆에서 따로 도는 프로그램입니다(새친구 등) — 칸의 오른쪽 열에 섭니다."

# 담당 칸에 이것이 적혀 있으면 개인이 아니라 묶음이다.
# 가져올 때 scope 가 없는 파일의 기준으로 쓴다 (5-2).
TEAM_WORDS = frozenset({
    "전체", "총무팀", "봉사자", "봉사팀", "헤브론", "코람데오",
    "총무팀 전체", "봉사자 전체", "다같이", "모두",
})


class Program(Base):
    """수련회 기간의 프로그램 하나.

    **회차별이다** — TaskRun 처럼 회차에 붙는다. 프로그램표는 매 회차 새로 만들고,
    지난 회차에서 통째로 복사해 온다(5-5).

    날짜를 저장하지 않고 `day`(선발대·1일차…)만 남긴다. 절대 날짜는 회차의
    개회일에서 매번 계산한다 — 라이브러리가 D-주차만 갖는 것과 같은 이유로,
    개회일이 바뀌면 프로그램표도 따라 움직여야 한다.
    """

    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    retreat_id: Mapped[int] = mapped_column(
        ForeignKey("retreats.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[str] = mapped_column(String(20))
    start_time: Mapped[str] = mapped_column(String(5))          # "HH:MM"
    # 끝나는 시각. **없으면 다음 프로그램 시작 전까지로 본다** (5-8) —
    # 실제 시트에 끝 시각이 적힌 것은 몇 개뿐이라 없는 것이 정상이다.
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    host: Mapped[str | None] = mapped_column(String(100), nullable=True)
    place: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 참가자가 함께하는가 (5-8). all 이면 전체일정 칸, staff 면 봉사자 칸.
    audience: Mapped[str | None] = mapped_column(String(10), nullable=True, default="all")
    # 정규 흐름인가(main), 총무팀이 뒤에서 돌리는 일인가(ops).
    track: Mapped[str | None] = mapped_column(String(10), nullable=True, default="main")
    # 정규 흐름 **옆에서 따로** 도는가 (새친구). 그 칸의 오른쪽 열로 뺀다.
    # 시각으로 추측하지 않는다 — 길이를 모르면 판단할 수 없다 (5-8 함정)
    parallel: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    retreat: Mapped[Retreat] = relationship()
    items: Mapped[list[ProgramItem]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
        order_by="ProgramItem.sort_order, ProgramItem.id",
    )

    # ALTER 로 붙은 컬럼들이라 기존 행에서는 NULL 이다. 읽는 자리는 늘 이것을 쓴다.
    @property
    def audience_key(self) -> str:
        return self.audience or "all"

    @property
    def track_key(self) -> str:
        return self.track or "main"

    @property
    def is_parallel(self) -> bool:
        return bool(self.parallel)


class ProgramItem(Base):
    """프로그램 하나에 붙는 실행 항목 (전 / 중 / 후)."""

    __tablename__ = "program_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    phase: Mapped[str] = mapped_column(String(4))               # pre | mid | post
    part_key: Mapped[str] = mapped_column(String(20))
    # **이름 문자열이다. User 로 잇지 않는다** — 현장에는 계정 없는 사람이 섞이고
    # (`하람` `서윤` `전체`) 실제 시트가 그렇게 쓰여 있다. 계정과 잇고 싶어지면
    # 그때 컬럼을 더한다.
    assignee_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # 팀이 통째로 움직이는 것인가, 개인에게 붙는 것인가 (5-2).
    #
    # **파트에서 계산하지 않고 컬럼으로 둔다.** 헤브론·코람데오가 팀이고 총무팀
    # 파트가 개인인 것은 대체로 맞지만 예외가 있다 — 총무팀 항목에도
    # "강당 의자 세팅_전체" 처럼 팀 단위가 섞이고, 봉사팀도 개인에게 붙는 일이
    # 생긴다. 계산으로 두면 그 예외를 표현할 방법이 없고 화면에서 고칠 수도 없다.
    #
    # 나중에 붙은 컬럼이라 기존 행에는 NULL 이다. 읽는 자리는 `scope_of()` 를 쓴다.
    scope: Mapped[str | None] = mapped_column(String(10), nullable=True, default="person")
    # **누른 시각을 남긴다.** 체크 여부만 남기면 끝난 뒤 "정리 항목이 몇 시에
    # 처리됐나" 를 볼 수 없다.
    done_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    done_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    program: Mapped[Program] = relationship(back_populates="items")
    done_by: Mapped[User | None] = relationship()

    @property
    def done(self) -> bool:
        return self.done_at is not None

    @property
    def scope_key(self) -> str:
        """ALTER 로 붙은 컬럼이라 기존 행은 NULL 이다. 읽는 자리는 늘 이것을 쓴다."""
        return self.scope or "person"

    @property
    def is_team(self) -> bool:
        return self.scope_key == "team"


class TaskAttachment(Base):
    """업무 하나에 붙는 첨부파일.

    **회차별이다.** TaskRun 에 붙으므로 새 회차를 열 때 업무는 따라와도
    파일은 따라오지 않는다. 논의 내역과 같은 취급이고, 업무 규칙과 다르다 —
    규칙은 "이 업무를 어떻게 하는가"라 회차를 넘어가지만, 첨부는 이번 회차의
    시안·견적·명단이라 다음 회차에 그대로 쓰면 오히려 틀린 자료가 된다.

    **파일 이름을 그대로 디스크에 쓰지 않는다.** 올린 이름은 여기 남기고
    실제 파일은 임의의 이름으로 저장한다 — 경로 조작(`../`), 같은 이름끼리의
    덮어쓰기, 한글 파일명 인코딩이 한꺼번에 사라진다.
    """

    __tablename__ = "task_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), index=True
    )
    original_name: Mapped[str] = mapped_column(String(300))
    stored_name: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    run: Mapped[TaskRun] = relationship(back_populates="attachments")

    @property
    def ext(self) -> str:
        """확장자. 목록에서 무슨 파일인지 한눈에 알아보는 표시."""
        _, dot, tail = self.original_name.rpartition(".")
        return tail.lower() if dot else ""


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
