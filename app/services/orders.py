from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from random import randint

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import ComboRule, MenuItem, Order, OrderItem
from app.schemas import (
    OrderComboCreate,
    OrderAmendRequest,
    OrderCreate,
    OrderDiffLine,
    OrderDiffOut,
    OrderDiffQtyLine,
    PaymentMethod,
    OrderStatus,
    PaymentStatus,
)
from app.services.inventory import (
    adjust_inventory_for_amended_order,
    deduct_inventory_for_order,
    restore_inventory_for_cancelled_order,
)


def _load_active_menu_item(db: Session, menu_item_id: int) -> MenuItem:
    menu_item = db.get(MenuItem, menu_item_id)
    if not menu_item or not menu_item.is_active:
        raise HTTPException(status_code=400, detail=f"Menu item {menu_item_id} unavailable")
    return menu_item


def _allocate_weighted_line_totals(
    *,
    total_amount: float,
    weighted_keys: list[tuple[int, float]],
) -> dict[int, float]:
    if not weighted_keys:
        return {}
    base_sum = sum(weight for _, weight in weighted_keys)
    if base_sum <= 0:
        per_line = round(total_amount / len(weighted_keys), 2)
        allocated = {key: per_line for key, _ in weighted_keys}
    else:
        allocated: dict[int, float] = {}
        remaining = round(total_amount, 2)
        for key, weight in weighted_keys[:-1]:
            line_total = round(total_amount * (weight / base_sum), 2)
            allocated[key] = line_total
            remaining = round(remaining - line_total, 2)
        allocated[weighted_keys[-1][0]] = remaining
    return allocated


def _build_combo_order_lines(db: Session, combo_input: OrderComboCreate) -> list[dict]:
    combo = db.scalar(select(ComboRule).where(ComboRule.id == combo_input.combo_id))
    if not combo or not combo.is_active:
        raise HTTPException(status_code=400, detail=f"Combo rule {combo_input.combo_id} unavailable")

    drink_ids = [int(item_id) for item_id in combo_input.drink_item_ids]
    side_ids = [int(item_id) for item_id in combo_input.side_item_ids]

    if len(drink_ids) != combo.drink_choice_count:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Combo {combo.code} requires {combo.drink_choice_count} drink selections, "
                f"got {len(drink_ids)}"
            ),
        )
    if len(side_ids) != combo.side_choice_count:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Combo {combo.code} requires {combo.side_choice_count} side selections, "
                f"got {len(side_ids)}"
            ),
        )

    eligible_drink_ids = {row.menu_item_id for row in combo.eligible_drinks}
    invalid_drinks = sorted([item_id for item_id in drink_ids if item_id not in eligible_drink_ids])
    if invalid_drinks:
        raise HTTPException(
            status_code=400,
            detail=f"Combo {combo.code} has invalid drink item ids: {invalid_drinks}",
        )

    component_ids = drink_ids + side_ids
    if not component_ids:
        raise HTTPException(status_code=400, detail=f"Combo {combo.code} has no selected items")

    menu_items = db.scalars(select(MenuItem).where(MenuItem.id.in_(set(component_ids)))).all()
    menu_by_id = {item.id: item for item in menu_items}
    missing = sorted(set(component_ids) - set(menu_by_id.keys()))
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown menu item ids in combo {combo.code}: {missing}")
    inactive = sorted(item.id for item in menu_items if not item.is_active)
    if inactive:
        raise HTTPException(status_code=400, detail=f"Inactive menu item ids in combo {combo.code}: {inactive}")

    per_set_counts = Counter(component_ids)
    line_counts = {item_id: count * combo_input.quantity for item_id, count in per_set_counts.items()}
    weighted_keys = [
        (item_id, menu_by_id[item_id].price * line_counts[item_id])
        for item_id in line_counts.keys()
    ]
    line_totals = _allocate_weighted_line_totals(
        total_amount=round(combo.bundle_price * combo_input.quantity, 2),
        weighted_keys=weighted_keys,
    )

    lines: list[dict] = []
    note = f"[COMBO:{combo.code}]"
    for item_id, quantity in line_counts.items():
        line_total = round(line_totals[item_id], 2)
        unit_price = round(line_total / quantity, 2)
        lines.append(
            {
                "menu_item_id": item_id,
                "menu_item_name": menu_by_id[item_id].name,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total,
                "note": note,
            },
        )
    return lines


def generate_order_number() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"OD{timestamp}{randint(1000, 9999)}"


def _create_order_with_unique_number(
    db: Session,
    *,
    source: str,
    max_retries: int = 5,
) -> Order:
    for _ in range(max_retries):
        row = Order(
            order_number=generate_order_number(),
            source=source,
            status=OrderStatus.pending.value,
            payment_status=PaymentStatus.unpaid.value,
        )
        db.add(row)
        try:
            db.flush()
            return row
        except IntegrityError:
            db.rollback()
            continue
    raise HTTPException(status_code=503, detail="Failed to allocate unique order number. Please retry.")


def fetch_order_with_items(db: Session, order_id: int) -> Order | None:
    return db.scalar(
        select(Order)
        .options(joinedload(Order.items))
        .where(Order.id == order_id),
    )


def _normalize_note(note: str | None) -> str | None:
    if note is None:
        return None
    cleaned = note.strip()
    return cleaned if cleaned else None


def _build_amended_lines(db: Session, payload: OrderAmendRequest) -> list[dict]:
    aggregated: dict[tuple[int, str | None], dict] = {}

    for input_item in payload.items:
        menu_item = db.get(MenuItem, input_item.menu_item_id)
        if not menu_item or not menu_item.is_active:
            raise HTTPException(status_code=400, detail=f"Menu item {input_item.menu_item_id} unavailable")

        note = _normalize_note(input_item.note)
        key = (menu_item.id, note)
        if key not in aggregated:
            aggregated[key] = {
                "menu_item_id": menu_item.id,
                "menu_item_name": menu_item.name,
                "quantity": 0,
                "unit_price": menu_item.price,
                "note": note,
            }
        aggregated[key]["quantity"] += input_item.quantity

    return sorted(
        aggregated.values(),
        key=lambda row: (row["menu_item_name"], row["menu_item_id"], row["note"] or ""),
    )


def _snapshot_order_items(items: list[OrderItem]) -> dict[tuple[int, str | None], dict]:
    snapshot: dict[tuple[int, str | None], dict] = {}
    for item in items:
        key = (item.menu_item_id, _normalize_note(item.note))
        if key not in snapshot:
            snapshot[key] = {
                "menu_item_id": item.menu_item_id,
                "menu_item_name": item.menu_item_name,
                "quantity": 0,
                "note": _normalize_note(item.note),
            }
        snapshot[key]["quantity"] += item.quantity
    return snapshot


def _snapshot_amended_lines(lines: list[dict]) -> dict[tuple[int, str | None], dict]:
    return {
        (line["menu_item_id"], _normalize_note(line["note"])): {
            "menu_item_id": line["menu_item_id"],
            "menu_item_name": line["menu_item_name"],
            "quantity": line["quantity"],
            "note": _normalize_note(line["note"]),
        }
        for line in lines
    }


def _build_order_diff(before: dict[tuple[int, str | None], dict], after: dict[tuple[int, str | None], dict]) -> OrderDiffOut:
    added: list[OrderDiffLine] = []
    removed: list[OrderDiffLine] = []
    quantity_changed: list[OrderDiffQtyLine] = []

    keys = sorted(
        set(before.keys()) | set(after.keys()),
        key=lambda item: (item[0], item[1] or ""),
    )
    for key in keys:
        before_row = before.get(key)
        after_row = after.get(key)
        if before_row is None and after_row is not None:
            added.append(
                OrderDiffLine(
                    menu_item_name=after_row["menu_item_name"],
                    quantity=after_row["quantity"],
                    note=after_row["note"],
                ),
            )
            continue

        if after_row is None and before_row is not None:
            removed.append(
                OrderDiffLine(
                    menu_item_name=before_row["menu_item_name"],
                    quantity=before_row["quantity"],
                    note=before_row["note"],
                ),
            )
            continue

        if before_row and after_row and before_row["quantity"] != after_row["quantity"]:
            quantity_changed.append(
                OrderDiffQtyLine(
                    menu_item_name=after_row["menu_item_name"],
                    before_quantity=before_row["quantity"],
                    after_quantity=after_row["quantity"],
                    note=after_row["note"],
                ),
            )

    return OrderDiffOut(added=added, removed=removed, quantity_changed=quantity_changed)


def _replace_order_items(db: Session, order: Order, lines: list[dict]) -> None:
    order.items.clear()
    db.flush()

    total_amount = 0.0
    for line in lines:
        line_total = line["unit_price"] * line["quantity"]
        total_amount += line_total
        db.add(
            OrderItem(
                order_id=order.id,
                menu_item_id=line["menu_item_id"],
                menu_item_name=line["menu_item_name"],
                quantity=line["quantity"],
                unit_price=line["unit_price"],
                line_total=line_total,
                note=line["note"],
            ),
        )

    order.total_amount = round(total_amount, 2)
    db.flush()


def create_order(db: Session, payload: OrderCreate) -> tuple[Order, list[dict]]:
    order = _create_order_with_unique_number(db, source=payload.source.value)
    order.payment_method = payload.payment_method.value

    lines: list[dict] = []
    for input_item in payload.items:
        menu_item = _load_active_menu_item(db, input_item.menu_item_id)
        line_total = round(menu_item.price * input_item.quantity, 2)
        lines.append(
            {
                "menu_item_id": menu_item.id,
                "menu_item_name": menu_item.name,
                "quantity": input_item.quantity,
                "unit_price": menu_item.price,
                "line_total": line_total,
                "note": input_item.note,
            },
        )

    for combo_input in payload.combos:
        lines.extend(_build_combo_order_lines(db, combo_input))

    if not lines:
        raise HTTPException(status_code=400, detail="Order must include at least one item or combo")

    total = 0.0
    for line in lines:
        total += line["line_total"]
        db.add(
            OrderItem(
                order_id=order.id,
                menu_item_id=line["menu_item_id"],
                menu_item_name=line["menu_item_name"],
                quantity=line["quantity"],
                unit_price=line["unit_price"],
                line_total=line["line_total"],
                note=line["note"],
            ),
        )

    order.total_amount = round(total, 2)
    db.flush()

    low_stock = []
    if payload.auto_pay:
        payable_order = fetch_order_with_items(db, order.id) or order
        low_stock = pay_order(db, payable_order)

    refreshed = fetch_order_with_items(db, order.id)
    if not refreshed:
        raise HTTPException(status_code=500, detail="Failed to load order")
    return refreshed, low_stock


def pay_order(
    db: Session,
    order: Order,
    payment_method: PaymentMethod | str | None = None,
) -> list[dict]:
    if order.payment_status == PaymentStatus.paid.value:
        return []
    if payment_method:
        order.payment_method = (
            payment_method.value if isinstance(payment_method, PaymentMethod) else str(payment_method)
        )
    order.payment_status = PaymentStatus.paid.value
    order.paid_at = datetime.now(timezone.utc)
    return deduct_inventory_for_order(db, order)


def amend_order(db: Session, order: Order, payload: OrderAmendRequest) -> tuple[Order, OrderDiffOut, list[dict]]:
    if order.status in {OrderStatus.completed.value, OrderStatus.cancelled.value}:
        raise HTTPException(status_code=409, detail="Completed or cancelled orders cannot be amended")

    existing_snapshot = _snapshot_order_items(order.items)
    amended_lines = _build_amended_lines(db, payload)
    amended_snapshot = _snapshot_amended_lines(amended_lines)
    diff = _build_order_diff(existing_snapshot, amended_snapshot)

    is_noop = not diff.added and not diff.removed and not diff.quantity_changed
    if is_noop:
        return order, diff, []

    low_stock = adjust_inventory_for_amended_order(
        db,
        order=order,
        previous_items=[
            {"menu_item_id": item.menu_item_id, "quantity": item.quantity}
            for item in order.items
        ],
        next_items=[
            {"menu_item_id": line["menu_item_id"], "quantity": line["quantity"]}
            for line in amended_lines
        ],
    )
    _replace_order_items(db, order, amended_lines)

    refreshed = fetch_order_with_items(db, order.id)
    if not refreshed:
        raise HTTPException(status_code=500, detail="Failed to load updated order")
    return refreshed, diff, low_stock


def update_order_status(db: Session, order: Order, next_status: OrderStatus) -> Order:
    valid_transitions = {
        OrderStatus.pending.value: {OrderStatus.preparing.value, OrderStatus.cancelled.value},
        OrderStatus.preparing.value: {OrderStatus.ready.value, OrderStatus.cancelled.value},
        OrderStatus.ready.value: {OrderStatus.completed.value},
        OrderStatus.completed.value: set(),
        OrderStatus.cancelled.value: set(),
    }
    allowed = valid_transitions.get(order.status, set())
    if next_status.value not in allowed and next_status.value != order.status:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition from {order.status} to {next_status.value}",
        )

    order.status = next_status.value
    if next_status == OrderStatus.completed:
        order.completed_at = datetime.now(timezone.utc)
    if next_status == OrderStatus.cancelled:
        restore_inventory_for_cancelled_order(db, order)

    refreshed = fetch_order_with_items(db, order.id)
    if not refreshed:
        raise HTTPException(status_code=500, detail="Failed to load updated order")
    return refreshed
