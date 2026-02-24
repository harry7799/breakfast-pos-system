from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Ingredient, MenuItem, Order, RecipeLine, StockMovement
from app.schemas import MovementType

EPSILON = 1e-9


def create_movement(
    db: Session,
    ingredient: Ingredient,
    movement_type: MovementType | str,
    quantity: float,
    reference: str | None = None,
    unit_cost: float | None = None,
    notes: str | None = None,
) -> StockMovement:
    type_value = movement_type.value if isinstance(movement_type, MovementType) else str(movement_type)
    movement = StockMovement(
        ingredient_id=ingredient.id,
        movement_type=type_value,
        quantity=quantity,
        reference=reference,
        unit_cost=unit_cost,
        notes=notes,
    )
    db.add(movement)
    ingredient.current_stock += quantity
    if unit_cost is not None and unit_cost >= 0:
        ingredient.cost_per_unit = unit_cost
    return movement


def _ensure_non_negative_stock(ingredient: Ingredient, delta: float) -> None:
    projected = ingredient.current_stock + delta
    if projected < -EPSILON:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Insufficient stock for {ingredient.name}. "
                f"current={ingredient.current_stock:.2f}, required_change={delta:.2f}"
            ),
        )


def _get_low_stock_rows(db: Session) -> list[dict]:
    rows = db.scalars(
        select(Ingredient).where(Ingredient.current_stock <= Ingredient.reorder_level),
    ).all()
    return [
        {
            "ingredient_name": row.name,
            "current_stock": round(row.current_stock, 2),
            "reorder_level": round(row.reorder_level, 2),
            "unit": row.unit,
        }
        for row in rows
    ]


def get_low_stock_rows(db: Session) -> list[dict]:
    return _get_low_stock_rows(db)


def _collect_requirements_for_lines(db: Session, lines: list[dict[str, int]]) -> dict[int, dict]:
    required_by_ingredient: dict[int, dict] = {}
    for line in lines:
        menu_item = db.get(MenuItem, line["menu_item_id"])
        if not menu_item:
            continue
        recipe_lines = db.scalars(
            select(RecipeLine).where(RecipeLine.menu_item_id == menu_item.id),
        ).all()
        for recipe in recipe_lines:
            ingredient = db.get(Ingredient, recipe.ingredient_id)
            if not ingredient:
                continue
            required_qty = recipe.quantity * line["quantity"]
            if ingredient.id not in required_by_ingredient:
                required_by_ingredient[ingredient.id] = {
                    "ingredient": ingredient,
                    "required_qty": 0.0,
                }
            required_by_ingredient[ingredient.id]["required_qty"] += required_qty
    return required_by_ingredient


def _collect_order_requirements(db: Session, order: Order) -> dict[int, dict]:
    return _collect_requirements_for_lines(
        db,
        [
            {"menu_item_id": order_item.menu_item_id, "quantity": order_item.quantity}
            for order_item in order.items
        ],
    )


def _validate_requirements(required_by_ingredient: dict[int, dict]) -> None:
    shortages: list[dict] = []
    for row in required_by_ingredient.values():
        ingredient = row["ingredient"]
        required_qty = row["required_qty"]
        if ingredient.current_stock + EPSILON < required_qty:
            shortages.append(
                {
                    "ingredient_name": ingredient.name,
                    "current_stock": round(ingredient.current_stock, 2),
                    "required": round(required_qty, 2),
                    "unit": ingredient.unit,
                },
            )
    if shortages:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Insufficient inventory",
                "shortages": shortages,
            },
        )


def _lock_ingredients_for_update(db: Session, ingredient_ids: list[int]) -> None:
    if not ingredient_ids:
        return
    bind = db.get_bind()
    if not bind or bind.dialect.name == "sqlite":
        return
    db.execute(
        select(Ingredient.id).where(Ingredient.id.in_(ingredient_ids)).with_for_update(),
    ).all()


def apply_manual_movement(
    db: Session,
    *,
    ingredient_id: int,
    movement_type: MovementType,
    quantity: float,
    unit_cost: float | None = None,
    reference: str | None = None,
    notes: str | None = None,
) -> StockMovement:
    ingredient = db.get(Ingredient, ingredient_id)
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    if movement_type == MovementType.purchase:
        delta = abs(quantity)
    elif movement_type == MovementType.waste:
        delta = -abs(quantity)
    elif movement_type == MovementType.adjustment:
        delta = quantity
    else:
        raise HTTPException(status_code=400, detail="Unsupported movement type for manual operation")

    _ensure_non_negative_stock(ingredient, delta)
    movement = create_movement(
        db,
        ingredient=ingredient,
        movement_type=movement_type.value,
        quantity=delta,
        reference=reference,
        unit_cost=unit_cost,
        notes=notes,
    )
    db.flush()
    return movement


def deduct_inventory_for_order(db: Session, order: Order) -> list[dict]:
    if order.inventory_deducted_at:
        return _get_low_stock_rows(db)

    required_by_ingredient = _collect_order_requirements(db, order)
    _lock_ingredients_for_update(db, list(required_by_ingredient.keys()))
    for row in required_by_ingredient.values():
        db.refresh(row["ingredient"])
    _validate_requirements(required_by_ingredient)

    for row in required_by_ingredient.values():
        ingredient = row["ingredient"]
        required_qty = row["required_qty"]
        create_movement(
            db,
            ingredient=ingredient,
            movement_type=MovementType.usage.value,
            quantity=-required_qty,
            reference=f"ORDER:{order.order_number}",
        )

    order.inventory_deducted_at = datetime.now(timezone.utc)
    return _get_low_stock_rows(db)


def restore_inventory_for_cancelled_order(db: Session, order: Order) -> list[dict]:
    if not order.inventory_deducted_at:
        return _get_low_stock_rows(db)

    restore_reference = f"CANCEL:{order.order_number}"
    restored_count = db.scalar(
        select(func.count(StockMovement.id)).where(StockMovement.reference == restore_reference),
    ) or 0
    if restored_count > 0:
        return _get_low_stock_rows(db)

    required_by_ingredient = _collect_order_requirements(db, order)
    for row in required_by_ingredient.values():
        ingredient = row["ingredient"]
        required_qty = row["required_qty"]
        create_movement(
            db,
            ingredient=ingredient,
            movement_type=MovementType.adjustment.value,
            quantity=required_qty,
            reference=restore_reference,
            notes="Auto-restored due to order cancellation",
        )

    return _get_low_stock_rows(db)


def adjust_inventory_for_amended_order(
    db: Session,
    *,
    order: Order,
    previous_items: list[dict[str, int]],
    next_items: list[dict[str, int]],
) -> list[dict]:
    if not order.inventory_deducted_at:
        return _get_low_stock_rows(db)

    previous_requirements = _collect_requirements_for_lines(db, previous_items)
    next_requirements = _collect_requirements_for_lines(db, next_items)

    ingredient_ids = sorted(set(previous_requirements.keys()) | set(next_requirements.keys()))
    _lock_ingredients_for_update(db, ingredient_ids)

    shortages: list[dict] = []
    for ingredient_id in ingredient_ids:
        ingredient = (
            next_requirements.get(ingredient_id, previous_requirements.get(ingredient_id))["ingredient"]
        )
        db.refresh(ingredient)
        before_required = previous_requirements.get(ingredient_id, {}).get("required_qty", 0.0)
        after_required = next_requirements.get(ingredient_id, {}).get("required_qty", 0.0)
        increased_required = after_required - before_required
        if increased_required > EPSILON and ingredient.current_stock + EPSILON < increased_required:
            shortages.append(
                {
                    "ingredient_name": ingredient.name,
                    "current_stock": round(ingredient.current_stock, 2),
                    "required": round(increased_required, 2),
                    "unit": ingredient.unit,
                },
            )

    if shortages:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Insufficient inventory",
                "shortages": shortages,
            },
        )

    for ingredient_id in ingredient_ids:
        ingredient = (
            next_requirements.get(ingredient_id, previous_requirements.get(ingredient_id))["ingredient"]
        )
        before_required = previous_requirements.get(ingredient_id, {}).get("required_qty", 0.0)
        after_required = next_requirements.get(ingredient_id, {}).get("required_qty", 0.0)
        delta = after_required - before_required
        if delta > EPSILON:
            create_movement(
                db,
                ingredient=ingredient,
                movement_type=MovementType.usage.value,
                quantity=-delta,
                reference=f"AMEND:{order.order_number}",
                notes="Auto-adjusted due to order amendment",
            )
        elif delta < -EPSILON:
            create_movement(
                db,
                ingredient=ingredient,
                movement_type=MovementType.adjustment.value,
                quantity=-delta,
                reference=f"AMEND:{order.order_number}",
                notes="Auto-restored due to order amendment",
            )

    return _get_low_stock_rows(db)
