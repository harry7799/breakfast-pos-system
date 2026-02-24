from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.database import get_db
from app.models import ShiftSession, User
from app.schemas import ShiftCloseRequest, ShiftOpenRequest, ShiftSessionOut, UserRole
from app.services.audit import create_audit_log
from app.services.shift import close_shift, get_open_shift, open_shift
from app.ws import manager

router = APIRouter(prefix="/shift", tags=["shift"])


@router.get("/current", response_model=ShiftSessionOut | None)
def current_shift(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> ShiftSession | None:
    return get_open_shift(db)


@router.get("/history", response_model=list[ShiftSessionOut])
def shift_history(
    limit: int = 30,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> list[ShiftSession]:
    capped = max(1, min(limit, 120))
    return db.scalars(
        select(ShiftSession).order_by(ShiftSession.opened_at.desc()).limit(capped),
    ).all()


@router.post("/open", response_model=ShiftSessionOut, status_code=201)
async def open_new_shift(
    payload: ShiftOpenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> ShiftSession:
    row = open_shift(db, payload=payload, actor=current_user)
    create_audit_log(
        db,
        actor=current_user,
        action="shift.open",
        entity_type="shift_session",
        entity_id=row.id,
        payload={"shift_name": row.shift_name, "opening_cash": row.opening_cash},
    )
    db.commit()
    db.refresh(row)
    await manager.broadcast(
        {
            "event": "shift_opened",
            "shift_id": row.id,
            "shift_name": row.shift_name,
            "opened_by": row.opened_by_username,
            "opened_at": row.opened_at.isoformat(),
        },
    )
    return row


@router.post("/close", response_model=ShiftSessionOut)
async def close_current_shift(
    payload: ShiftCloseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> ShiftSession:
    row = close_shift(db, payload=payload, actor=current_user)
    create_audit_log(
        db,
        actor=current_user,
        action="shift.close",
        entity_type="shift_session",
        entity_id=row.id,
        payload={
            "actual_cash": row.actual_cash,
            "expected_cash": row.expected_cash,
            "cash_difference": row.cash_difference,
            "total_revenue": row.total_revenue,
            "paid_order_count": row.paid_order_count,
        },
    )
    db.commit()
    db.refresh(row)
    await manager.broadcast(
        {
            "event": "shift_closed",
            "shift_id": row.id,
            "shift_name": row.shift_name,
            "closed_by": row.closed_by_username,
            "closed_at": row.closed_at.isoformat() if row.closed_at else None,
            "total_revenue": row.total_revenue,
        },
    )
    return row
