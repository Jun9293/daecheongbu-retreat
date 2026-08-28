"""요청 단위 공용 의존성 (현재 회차 결정, 활동 로그)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ActivityLog, Retreat, User, UserRetreatState
from app.security import get_current_user


def resolve_retreat(db: Session, user: User, retreat_id: int | None) -> Retreat | None:
    """현재 보고 있는 회차를 결정한다.

    우선순위: URL 파라미터 > 마지막으로 보던 회차 > 가장 최근에 만든 회차
    """
    if retreat_id is not None:
        retreat = db.get(Retreat, retreat_id)
        if retreat is None:
            raise HTTPException(status_code=404, detail="회차를 찾을 수 없습니다.")
        remember_retreat(db, user, retreat)
        return retreat

    state = db.scalars(
        select(UserRetreatState).where(UserRetreatState.user_id == user.id)
    ).first()
    if state is not None:
        retreat = db.get(Retreat, state.retreat_id)
        if retreat is not None:
            return retreat

    # 보관 처리되지 않은 회차 중 개회일이 가장 늦은 것 = 지금 준비 중인 회차
    live = db.scalars(
        select(Retreat).where(~Retreat.is_archived).order_by(Retreat.start_date.desc())
    ).first()
    if live is not None:
        return live
    return db.scalars(select(Retreat).order_by(Retreat.start_date.desc())).first()


def remember_retreat(db: Session, user: User, retreat: Retreat) -> None:
    state = db.scalars(
        select(UserRetreatState).where(UserRetreatState.user_id == user.id)
    ).first()
    if state is None:
        db.add(UserRetreatState(user_id=user.id, retreat_id=retreat.id))
    else:
        state.retreat_id = retreat.id
    db.commit()


def get_current_retreat(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Retreat:
    raw = request.query_params.get("retreat_id")
    retreat = resolve_retreat(db, user, int(raw) if raw and raw.isdigit() else None)
    if retreat is None:
        raise HTTPException(status_code=404, detail="등록된 수련회 회차가 없습니다.")
    return retreat


def log_activity(
    db: Session,
    *,
    retreat_id: int | None,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    summary: str | None = None,
    before_value: dict | None = None,
    after_value: dict | None = None,
    actor_type: str = "user",
) -> None:
    db.add(
        ActivityLog(
            retreat_id=retreat_id,
            actor_type=actor_type,
            actor_id=actor.id if actor else None,
            actor_name=actor.name if actor else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            summary=summary,
            before_value=before_value,
            after_value=after_value,
        )
    )
    db.commit()


def all_retreats(db: Session) -> list[Retreat]:
    return list(db.scalars(select(Retreat).order_by(Retreat.start_date.desc())))
