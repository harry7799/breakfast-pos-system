from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth import require_roles
from app.database import get_db
from app.models import Order, User
from app.schemas import (
    OrderAmendRequest,
    OrderAmendResponse,
    OrderCreate,
    OrderOut,
    OrderPayRequest,
    OrderStatusUpdate,
    PickupBoardOrderOut,
    UserRole,
)
from app.services.audit import create_audit_log
from app.services.orders import amend_order, create_order, fetch_order_with_items, pay_order, update_order_status
from app.ws import manager

router = APIRouter(prefix="/orders", tags=["orders"])


def _load_order_or_404(db: Session, order_id: int) -> Order:
    row = fetch_order_with_items(db, order_id)
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    return row


@router.get("", response_model=list[OrderOut])
def list_orders(
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(UserRole.staff, UserRole.kitchen, UserRole.manager, UserRole.owner)),
) -> list[Order]:
    capped = max(1, min(limit, 500))
    stmt = select(Order).options(joinedload(Order.items)).order_by(Order.created_at.desc()).limit(capped)
    if status:
        stmt = stmt.where(Order.status == status)
    rows = db.execute(stmt).scalars().unique().all()
    return rows


@router.get("/pickup-board", response_model=list[PickupBoardOrderOut])
def pickup_board(
    minutes: int = 180,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[Order]:
    capped_minutes = max(10, min(minutes, 720))
    capped_limit = max(1, min(limit, 300))
    since = datetime.now(timezone.utc) - timedelta(minutes=capped_minutes)

    stmt = (
        select(Order)
        .where(Order.created_at >= since)
        .where(Order.status.in_(["preparing", "ready", "completed"]))
        .order_by(Order.created_at.desc())
        .limit(capped_limit)
    )
    return db.scalars(stmt).all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(UserRole.staff, UserRole.kitchen, UserRole.manager, UserRole.owner)),
) -> Order:
    return _load_order_or_404(db, order_id)


@router.post("", response_model=OrderOut, status_code=201)
async def create_new_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.staff, UserRole.manager, UserRole.owner)),
) -> Order:
    try:
        row, low_stock = create_order(db, payload)
        create_audit_log(
            db,
            actor=current_user,
            action="order.create",
            entity_type="order",
            entity_id=row.id,
            payload={
                "source": row.source,
                "payment_status": row.payment_status,
                "total_amount": row.total_amount,
                "item_count": len(row.items),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    row = _load_order_or_404(db, row.id)
    await manager.broadcast(
        {
            "event": "order_created",
            "order_id": row.id,
            "order_number": row.order_number,
            "status": row.status,
            "payment_status": row.payment_status,
            "total_amount": row.total_amount,
            "low_stock": low_stock,
        },
    )
    return row


@router.post("/{order_id}/pay", response_model=OrderOut)
async def pay_order_now(
    order_id: int,
    payload: OrderPayRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.staff, UserRole.manager, UserRole.owner)),
) -> Order:
    row = _load_order_or_404(db, order_id)
    try:
        low_stock = pay_order(db, row, payload.payment_method if payload else None)
        create_audit_log(
            db,
            actor=current_user,
            action="order.pay",
            entity_type="order",
            entity_id=row.id,
            payload={
                "payment_status": row.payment_status,
                "payment_method": row.payment_method,
                "low_stock_count": len(low_stock),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    row = _load_order_or_404(db, order_id)
    await manager.broadcast(
        {
            "event": "order_paid",
            "order_id": row.id,
            "order_number": row.order_number,
            "status": row.status,
            "payment_status": row.payment_status,
            "low_stock": low_stock,
        },
    )
    return row


@router.post("/{order_id}/amend", response_model=OrderAmendResponse)
async def amend_order_now(
    order_id: int,
    payload: OrderAmendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.staff, UserRole.manager, UserRole.owner)),
) -> OrderAmendResponse:
    row = _load_order_or_404(db, order_id)
    try:
        updated, diff, low_stock = amend_order(db, row, payload)
        has_changes = bool(diff.added or diff.removed or diff.quantity_changed)
        diff_payload = diff.model_dump() if has_changes else {}
        if has_changes:
            create_audit_log(
                db,
                actor=current_user,
                action="order.amend",
                entity_type="order",
                entity_id=updated.id,
                payload=diff_payload,
            )
            db.commit()
    except Exception:
        db.rollback()
        raise

    if has_changes:
        updated = _load_order_or_404(db, updated.id)
        await manager.broadcast(
            {
                "event": "order_amended",
                "order_id": updated.id,
                "order_number": updated.order_number,
                "status": updated.status,
                "payment_status": updated.payment_status,
                "diff": diff_payload,
                "low_stock": low_stock,
            },
        )
    return OrderAmendResponse(order=updated, diff=diff)


@router.post("/{order_id}/status", response_model=OrderOut)
async def change_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.kitchen, UserRole.manager, UserRole.owner)),
) -> Order:
    row = _load_order_or_404(db, order_id)
    try:
        updated = update_order_status(db, row, payload.status)
        create_audit_log(
            db,
            actor=current_user,
            action="order.status.change",
            entity_type="order",
            entity_id=updated.id,
            payload={"status": updated.status},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    updated = _load_order_or_404(db, updated.id)
    await manager.broadcast(
        {
            "event": "order_status_changed",
            "order_id": updated.id,
            "order_number": updated.order_number,
            "status": updated.status,
            "payment_status": updated.payment_status,
        },
    )
    return updated
