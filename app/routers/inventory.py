from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.database import get_db
from app.models import Ingredient, StockMovement, User
from app.schemas import (
    IngredientCreate,
    IngredientOut,
    IngredientUpdate,
    LowStockOut,
    StockMovementCreate,
    StockMovementOut,
    UserRole,
)
from app.services.inventory import apply_manual_movement, get_low_stock_rows
from app.services.audit import create_audit_log

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/ingredients", response_model=list[IngredientOut])
def list_ingredients(
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> list[Ingredient]:
    return db.scalars(select(Ingredient).order_by(Ingredient.id)).all()


@router.post("/ingredients", response_model=IngredientOut, status_code=201)
def create_ingredient(
    payload: IngredientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> Ingredient:
    exists = db.scalar(select(Ingredient).where(Ingredient.name == payload.name))
    if exists:
        raise HTTPException(status_code=409, detail="Ingredient already exists")
    row = Ingredient(**payload.model_dump())
    db.add(row)
    db.flush()
    create_audit_log(
        db,
        actor=current_user,
        action="inventory.ingredient.create",
        entity_type="ingredient",
        entity_id=row.id,
        payload=payload.model_dump(),
    )
    db.commit()
    db.refresh(row)
    return row


@router.put("/ingredients/{ingredient_id}", response_model=IngredientOut)
def update_ingredient(
    ingredient_id: int,
    payload: IngredientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> Ingredient:
    row = db.get(Ingredient, ingredient_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    changes = payload.model_dump(exclude_unset=True)

    # If current_stock is being set directly, create a stock movement for audit trail
    if "current_stock" in changes and changes["current_stock"] is not None:
        old_stock = row.current_stock
        new_stock = float(changes.pop("current_stock"))
        if new_stock < 0:
            raise HTTPException(status_code=400, detail="current_stock cannot be negative")
        delta = new_stock - old_stock
        if abs(delta) > 1e-9:
            from app.services.inventory import create_movement
            from app.schemas import MovementType
            create_movement(
                db,
                ingredient=row,
                movement_type=MovementType.adjustment.value,
                quantity=delta,
                reference="MANUAL_OVERRIDE",
                notes=f"Direct stock set from {old_stock:.2f} to {new_stock:.2f}",
            )

    for key, value in changes.items():
        setattr(row, key, value)
    create_audit_log(
        db,
        actor=current_user,
        action="inventory.ingredient.update",
        entity_type="ingredient",
        entity_id=row.id,
        payload=changes,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/movements", response_model=StockMovementOut, status_code=201)
def create_stock_movement(
    payload: StockMovementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> StockMovement:
    movement = apply_manual_movement(
        db,
        ingredient_id=payload.ingredient_id,
        movement_type=payload.movement_type,
        quantity=payload.quantity,
        unit_cost=payload.unit_cost,
        reference=payload.reference,
        notes=payload.notes,
    )
    create_audit_log(
        db,
        actor=current_user,
        action="inventory.movement.create",
        entity_type="stock_movement",
        entity_id=movement.id,
        payload=payload.model_dump(),
    )
    db.commit()
    db.refresh(movement)
    return movement


@router.get("/movements", response_model=list[StockMovementOut])
def list_stock_movements(
    limit: int = 100,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> list[StockMovement]:
    capped = max(1, min(limit, 500))
    return db.scalars(
        select(StockMovement).order_by(StockMovement.created_at.desc()).limit(capped),
    ).all()


@router.get("/low-stock", response_model=list[LowStockOut])
def list_low_stock(
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(UserRole.kitchen, UserRole.manager, UserRole.owner)),
) -> list[dict]:
    return get_low_stock_rows(db)
