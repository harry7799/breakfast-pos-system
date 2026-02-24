from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Ingredient, Order, OrderItem


def resolve_date_range(start_date: str | None, end_date: str | None) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    end = date.fromisoformat(end_date) if end_date else today
    start = date.fromisoformat(start_date) if start_date else end - timedelta(days=6)
    if start > end:
        raise ValueError("start_date cannot be after end_date")
    return start, end


def overview(db: Session, start_date: str | None = None, end_date: str | None = None) -> dict:
    start, end = resolve_date_range(start_date, end_date)
    start_dt = datetime.combine(start, datetime.min.time(), timezone.utc)
    end_dt = datetime.combine(end, datetime.max.time(), timezone.utc)

    paid_filter = and_(
        Order.payment_status == "paid",
        Order.created_at >= start_dt,
        Order.created_at <= end_dt,
    )

    revenue = db.scalar(select(func.coalesce(func.sum(Order.total_amount), 0.0)).where(paid_filter)) or 0.0
    order_count = db.scalar(select(func.count(Order.id)).where(paid_filter)) or 0

    top_rows = db.execute(
        select(
            OrderItem.menu_item_name,
            func.sum(OrderItem.quantity).label("qty"),
            func.sum(OrderItem.line_total).label("revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(paid_filter)
        .group_by(OrderItem.menu_item_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5),
    ).all()

    daily_rows = db.execute(
        select(
            func.date(Order.created_at).label("day"),
            func.sum(Order.total_amount).label("revenue"),
            func.count(Order.id).label("orders"),
        )
        .where(paid_filter)
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at)),
    ).all()

    low_stock_rows = db.scalars(
        select(Ingredient).where(Ingredient.current_stock <= Ingredient.reorder_level).order_by(Ingredient.current_stock),
    ).all()

    inventory_value = db.scalar(
        select(func.coalesce(func.sum(Ingredient.current_stock * Ingredient.cost_per_unit), 0.0)),
    ) or 0.0

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "total_revenue": round(float(revenue), 2),
        "total_orders": int(order_count),
        "average_ticket": round(float(revenue) / order_count, 2) if order_count else 0.0,
        "inventory_value": round(float(inventory_value), 2),
        "top_items": [
            {
                "menu_item_name": row.menu_item_name,
                "quantity": int(row.qty or 0),
                "revenue": round(float(row.revenue or 0), 2),
            }
            for row in top_rows
        ],
        "low_stock": [
            {
                "ingredient_name": row.name,
                "current_stock": round(row.current_stock, 2),
                "reorder_level": round(row.reorder_level, 2),
                "unit": row.unit,
            }
            for row in low_stock_rows
        ],
        "daily_sales": [
            {
                "day": str(row.day),
                "revenue": round(float(row.revenue or 0), 2),
                "orders": int(row.orders or 0),
            }
            for row in daily_rows
        ],
    }

