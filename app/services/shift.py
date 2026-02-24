from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, ShiftSession, User
from app.schemas import ShiftCloseRequest, ShiftOpenRequest


def get_open_shift(db: Session) -> ShiftSession | None:
    return db.scalar(
        select(ShiftSession)
        .where(ShiftSession.status == "open")
        .order_by(ShiftSession.opened_at.desc()),
    )


def open_shift(db: Session, *, payload: ShiftOpenRequest, actor: User) -> ShiftSession:
    existing = get_open_shift(db)
    if existing:
        raise HTTPException(status_code=409, detail="An open shift already exists")

    row = ShiftSession(
        shift_name=payload.shift_name.strip(),
        status="open",
        opening_cash=round(payload.opening_cash, 2),
        expected_cash=round(payload.opening_cash, 2),
        opened_by_user_id=actor.id,
        opened_by_username=actor.username,
        notes=payload.notes.strip() if payload.notes else None,
    )
    db.add(row)
    db.flush()
    return row


def close_shift(db: Session, *, payload: ShiftCloseRequest, actor: User) -> ShiftSession:
    row = get_open_shift(db)
    if not row:
        raise HTTPException(status_code=409, detail="No open shift to close")

    now = datetime.now(timezone.utc)
    paid_orders = db.scalars(
        select(Order)
        .where(Order.paid_at.is_not(None))
        .where(Order.paid_at >= row.opened_at)
        .where(Order.paid_at <= now)
        .where(Order.payment_status == "paid"),
    ).all()

    refunded_orders = db.scalars(
        select(Order)
        .where(Order.updated_at >= row.opened_at)
        .where(Order.updated_at <= now)
        .where(Order.payment_status == "refunded"),
    ).all()

    total_revenue = round(sum(order.total_amount for order in paid_orders), 2)
    cash_revenue = round(
        sum(order.total_amount for order in paid_orders if order.payment_method == "cash"),
        2,
    )
    non_cash_revenue = round(total_revenue - cash_revenue, 2)
    refund_amount = round(sum(order.total_amount for order in refunded_orders), 2)
    expected_cash = round(row.opening_cash + cash_revenue, 2)
    actual_cash = round(payload.actual_cash, 2)
    cash_difference = round(actual_cash - expected_cash, 2)

    row.status = "closed"
    row.expected_cash = expected_cash
    row.actual_cash = actual_cash
    row.cash_difference = cash_difference
    row.paid_order_count = len(paid_orders)
    row.total_revenue = total_revenue
    row.cash_revenue = cash_revenue
    row.non_cash_revenue = non_cash_revenue
    row.refund_amount = refund_amount
    row.closed_by_user_id = actor.id
    row.closed_by_username = actor.username
    row.closed_at = now
    if payload.notes:
        row.notes = payload.notes.strip()

    db.flush()
    return row
