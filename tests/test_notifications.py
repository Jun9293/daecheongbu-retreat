"""알림 생성/수신자 결정 테스트.

푸시 구독 여부와 무관하게 앱 안에는 항상 알림이 남아야 한다 (단일 실패점 제거).
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.domain.escalation import RISK_OVERDUE, RISK_UNASSIGNED, Risk
from app.notifications import (
    notify,
    recipients_for_risk,
    run_risk_scan,
    unread_count,
)

TODAY = dt.date(2026, 7, 1)


def _people(db: Session, retreat: models.Retreat) -> dict[str, models.User]:
    depts = {d.name: d for d in retreat.departments}
    people = {
        "총무": models.User(
            name="김총무", phone_number="01011112222", role="admin",
            department_id=depts["총무팀"].id
        ),
        "홍보리더": models.User(
            name="이홍보", phone_number="01022223333", role="dept_lead",
            department_id=depts["홍보팀"].id
        ),
        "홍보원": models.User(
            name="최부원", phone_number="01044445555", role="member",
            department_id=depts["홍보팀"].id
        ),
        "찬양리더": models.User(
            name="박찬양", phone_number="01033334444", role="dept_lead",
            department_id=depts["찬양팀"].id
        ),
        "열람": models.User(name="정전도사", phone_number="01055556666", role="viewer"),
    }
    db.add_all(people.values())
    db.commit()
    return people


def _task(db: Session, retreat, dept_id, **kwargs) -> models.Task:
    task = models.Task(
        retreat_id=retreat.id,
        title=kwargs.pop("title", "포스터 인쇄 발주"),
        department_id=dept_id,
        blocked_by_task_ids=[],
        related_department_ids=[],
        **kwargs,
    )
    db.add(task)
    db.commit()
    return task


# ------------------------------------------------------------------ 수신자 결정


def test_담당자와_같은_부서원_모두에게_알린다(db: Session, sample_retreat):
    people = _people(db, sample_retreat)
    hongbo = next(d for d in sample_retreat.departments if d.name == "홍보팀")
    task = _task(db, sample_retreat, hongbo.id, assignee_id=people["홍보리더"].id)

    risk = Risk(kind=RISK_OVERDUE, task=task, message="지연", dedupe_key="k")
    ids = {u.id for u in recipients_for_risk(db, risk)}

    assert people["홍보리더"].id in ids
    assert people["홍보원"].id in ids
    assert people["찬양리더"].id not in ids


def test_에스컬레이션_대상이면_총무팀에도_알린다(db: Session, sample_retreat):
    people = _people(db, sample_retreat)
    hongbo = next(d for d in sample_retreat.departments if d.name == "홍보팀")
    task = _task(db, sample_retreat, hongbo.id, assignee_id=None)

    risk = Risk(
        kind=RISK_UNASSIGNED, task=task, message="담당자 없음",
        dedupe_key="k", escalate_to_admin=True,
    )
    ids = {u.id for u in recipients_for_risk(db, risk)}

    assert people["총무"].id in ids


def test_담당자가_없으면_부서원에게라도_알린다(db: Session, sample_retreat):
    people = _people(db, sample_retreat)
    hongbo = next(d for d in sample_retreat.departments if d.name == "홍보팀")
    task = _task(db, sample_retreat, hongbo.id, assignee_id=None)

    risk = Risk(kind=RISK_OVERDUE, task=task, message="지연", dedupe_key="k")
    ids = {u.id for u in recipients_for_risk(db, risk)}

    assert people["홍보리더"].id in ids
    assert people["홍보원"].id in ids


def test_열람전용_계정에게는_알림을_보내지_않는다(db: Session, sample_retreat):
    people = _people(db, sample_retreat)
    hongbo = next(d for d in sample_retreat.departments if d.name == "홍보팀")
    task = _task(db, sample_retreat, hongbo.id, assignee_id=None)

    risk = Risk(kind=RISK_OVERDUE, task=task, message="지연", dedupe_key="k", escalate_to_admin=True)
    ids = {u.id for u in recipients_for_risk(db, risk)}

    assert people["열람"].id not in ids


def test_부서가_없는_할일은_총무팀_소관이다(db: Session, sample_retreat):
    people = _people(db, sample_retreat)
    task = _task(db, sample_retreat, None, assignee_id=None)

    risk = Risk(kind=RISK_OVERDUE, task=task, message="지연", dedupe_key="k")
    ids = {u.id for u in recipients_for_risk(db, risk)}

    assert people["총무"].id in ids


# ------------------------------------------------------------------ 알림 생성


def test_알림을_만들면_읽지_않음으로_쌓인다(db: Session, sample_retreat):
    people = _people(db, sample_retreat)

    notify(
        db,
        users=[people["홍보리더"]],
        retreat_id=sample_retreat.id,
        kind="테스트",
        title="확인 필요",
        body="본문",
        link="/tasks",
        dedupe_key="test:1",
    )

    assert unread_count(db, people["홍보리더"]) == 1


def test_같은_dedupe_키로는_중복_알림이_쌓이지_않는다(db: Session, sample_retreat):
    people = _people(db, sample_retreat)

    for _ in range(3):
        notify(
            db,
            users=[people["홍보리더"]],
            retreat_id=sample_retreat.id,
            kind="테스트",
            title="확인 필요",
            dedupe_key="test:1",
        )

    assert unread_count(db, people["홍보리더"]) == 1


def test_다른_사용자에게는_같은_키라도_각각_쌓인다(db: Session, sample_retreat):
    people = _people(db, sample_retreat)

    notify(
        db,
        users=[people["홍보리더"], people["홍보원"]],
        retreat_id=sample_retreat.id,
        kind="테스트",
        title="확인 필요",
        dedupe_key="test:1",
    )

    assert unread_count(db, people["홍보리더"]) == 1
    assert unread_count(db, people["홍보원"]) == 1


# ------------------------------------------------------------------ 전체 스캔


def test_스캔하면_기한_지난_할일이_지연으로_바뀌고_알림이_생긴다(db: Session, sample_retreat):
    people = _people(db, sample_retreat)
    hongbo = next(d for d in sample_retreat.departments if d.name == "홍보팀")
    task = _task(
        db, sample_retreat, hongbo.id,
        assignee_id=people["홍보리더"].id,
        due_date=TODAY - dt.timedelta(days=2),
        status="진행중",
    )

    created = run_risk_scan(db, retreat=sample_retreat, today=TODAY)

    db.refresh(task)
    assert task.status == "지연"
    assert created > 0
    assert unread_count(db, people["홍보리더"]) > 0
    assert unread_count(db, people["총무"]) > 0  # 지연은 총무팀에도 에스컬레이션


def test_같은_날_두_번_스캔해도_알림이_두_배가_되지_않는다(db: Session, sample_retreat):
    people = _people(db, sample_retreat)
    hongbo = next(d for d in sample_retreat.departments if d.name == "홍보팀")
    _task(
        db, sample_retreat, hongbo.id,
        assignee_id=people["홍보리더"].id,
        due_date=TODAY - dt.timedelta(days=2),
    )

    run_risk_scan(db, retreat=sample_retreat, today=TODAY)
    first = unread_count(db, people["홍보리더"])
    run_risk_scan(db, retreat=sample_retreat, today=TODAY)

    assert unread_count(db, people["홍보리더"]) == first


def test_위험이_없으면_알림도_생기지_않는다(db: Session, sample_retreat):
    people = _people(db, sample_retreat)
    hongbo = next(d for d in sample_retreat.departments if d.name == "홍보팀")
    _task(
        db, sample_retreat, hongbo.id,
        assignee_id=people["홍보리더"].id,
        due_date=TODAY + dt.timedelta(days=30),
    )

    created = run_risk_scan(db, retreat=sample_retreat, today=TODAY)

    assert created == 0
    assert db.scalars(select(models.Notification)).all() == []
