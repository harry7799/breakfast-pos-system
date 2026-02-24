from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import require_roles
from app.database import get_db
from app.models import ComboDrinkItem, ComboRule, ComboSideOption, Ingredient, MenuItem, RecipeLine, User
from app.schemas import (
    ComboDrinkItemOut,
    ComboRuleCreate,
    ComboRuleOut,
    ComboRuleUpdate,
    ComboSideOptionIn,
    ComboSideOptionOut,
    MenuItemCreate,
    MenuItemOut,
    MenuItemUpdate,
    RecipeLineIn,
    RecipeLineOut,
    UserRole,
)
from app.services.audit import create_audit_log

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("/items", response_model=list[MenuItemOut])
def list_menu_items(
    active_only: bool = True,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(UserRole.staff, UserRole.kitchen, UserRole.manager, UserRole.owner)),
) -> list[MenuItem]:
    stmt = select(MenuItem)
    if active_only:
        stmt = stmt.where(MenuItem.is_active.is_(True))
    return db.scalars(stmt.order_by(MenuItem.id)).all()


def _combo_query():
    return (
        select(ComboRule)
        .options(
            joinedload(ComboRule.eligible_drinks).joinedload(ComboDrinkItem.menu_item),
            joinedload(ComboRule.side_options),
        )
        .order_by(ComboRule.id)
    )


def _load_combo_or_404(db: Session, combo_id: int) -> ComboRule:
    row = db.scalar(_combo_query().where(ComboRule.id == combo_id))
    if not row:
        raise HTTPException(status_code=404, detail="Combo rule not found")
    return row


def _normalize_side_options(side_options: list[ComboSideOptionIn]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    for option in side_options:
        code = option.code.strip().upper()
        name = option.name.strip()
        if not code:
            raise HTTPException(status_code=400, detail="Side option code cannot be empty")
        if not name:
            raise HTTPException(status_code=400, detail=f"Side option name cannot be empty for code {code}")
        if code in seen_codes:
            raise HTTPException(status_code=400, detail=f"Duplicate side option code: {code}")
        seen_codes.add(code)
        normalized.append({"code": code, "name": name})
    return normalized


def _validate_menu_item_ids(db: Session, menu_item_ids: list[int]) -> list[int]:
    if not menu_item_ids:
        return []

    duplicates = [item_id for item_id, count in Counter(menu_item_ids).items() if count > 1]
    if duplicates:
        raise HTTPException(status_code=400, detail=f"Duplicate menu item ids: {sorted(duplicates)}")

    ids = list(menu_item_ids)
    existing_rows = db.scalars(select(MenuItem).where(MenuItem.id.in_(ids))).all()
    existing_ids = {row.id for row in existing_rows}
    missing = sorted(set(ids) - existing_ids)
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown menu item ids: {missing}")

    inactive = sorted(row.id for row in existing_rows if not row.is_active)
    if inactive:
        raise HTTPException(status_code=400, detail=f"Inactive menu item ids are not allowed: {inactive}")

    return ids


def _validate_choice_counts(
    *,
    drink_choice_count: int,
    eligible_drink_count: int,
    side_choice_count: int,
    side_option_count: int,
) -> None:
    if eligible_drink_count > 0 and drink_choice_count > eligible_drink_count:
        raise HTTPException(
            status_code=400,
            detail="drink_choice_count cannot exceed eligible_drink_item_ids length",
        )
    if side_option_count > 0 and side_choice_count > side_option_count:
        raise HTTPException(
            status_code=400,
            detail="side_choice_count cannot exceed side_options length",
        )


def _combo_to_out(row: ComboRule) -> ComboRuleOut:
    drinks = sorted(row.eligible_drinks, key=lambda line: (line.sort_order, line.id))
    sides = sorted(row.side_options, key=lambda line: (line.sort_order, line.id))
    return ComboRuleOut(
        id=row.id,
        code=row.code,
        name=row.name,
        bundle_price=row.bundle_price,
        max_drink_price=row.max_drink_price,
        drink_choice_count=row.drink_choice_count,
        side_choice_count=row.side_choice_count,
        raw_rule_text=row.raw_rule_text,
        is_active=row.is_active,
        eligible_drinks=[
            ComboDrinkItemOut(
                menu_item_id=line.menu_item_id,
                menu_item_name=line.menu_item.name if line.menu_item else "",
            )
            for line in drinks
        ],
        side_options=[ComboSideOptionOut(code=line.code, name=line.name) for line in sides],
    )


@router.get("/combos", response_model=list[ComboRuleOut])
def list_combo_rules(
    active_only: bool = True,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(UserRole.staff, UserRole.kitchen, UserRole.manager, UserRole.owner)),
) -> list[ComboRuleOut]:
    stmt = _combo_query()
    if active_only:
        stmt = stmt.where(ComboRule.is_active.is_(True))
    rows = db.execute(stmt).scalars().unique().all()
    return [_combo_to_out(row) for row in rows]


@router.get("/combos/{combo_id}", response_model=ComboRuleOut)
def get_combo_rule(
    combo_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(UserRole.staff, UserRole.kitchen, UserRole.manager, UserRole.owner)),
) -> ComboRuleOut:
    row = _load_combo_or_404(db, combo_id)
    return _combo_to_out(row)


@router.post("/combos", response_model=ComboRuleOut, status_code=201)
def create_combo_rule(
    payload: ComboRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> ComboRuleOut:
    code = payload.code.strip().upper()
    name = payload.name.strip()
    raw_rule_text = payload.raw_rule_text.strip() if payload.raw_rule_text else None
    if not code:
        raise HTTPException(status_code=400, detail="Combo code cannot be empty")
    if not name:
        raise HTTPException(status_code=400, detail="Combo name cannot be empty")
    if db.scalar(select(ComboRule.id).where(ComboRule.code == code)):
        raise HTTPException(status_code=409, detail="Combo code already exists")

    eligible_drink_item_ids = _validate_menu_item_ids(db, payload.eligible_drink_item_ids)
    side_options = _normalize_side_options(payload.side_options)
    _validate_choice_counts(
        drink_choice_count=payload.drink_choice_count,
        eligible_drink_count=len(eligible_drink_item_ids),
        side_choice_count=payload.side_choice_count,
        side_option_count=len(side_options),
    )

    row = ComboRule(
        code=code,
        name=name,
        bundle_price=payload.bundle_price,
        max_drink_price=payload.max_drink_price,
        drink_choice_count=payload.drink_choice_count,
        side_choice_count=payload.side_choice_count,
        raw_rule_text=raw_rule_text,
        is_active=payload.is_active,
    )
    db.add(row)
    db.flush()

    for idx, menu_item_id in enumerate(eligible_drink_item_ids):
        db.add(
            ComboDrinkItem(
                combo_rule_id=row.id,
                menu_item_id=menu_item_id,
                sort_order=idx,
            ),
        )
    for idx, option in enumerate(side_options):
        db.add(
            ComboSideOption(
                combo_rule_id=row.id,
                code=option["code"],
                name=option["name"],
                sort_order=idx,
            ),
        )

    create_audit_log(
        db,
        actor=current_user,
        action="menu.combo.create",
        entity_type="combo_rule",
        entity_id=row.id,
        payload={
            "code": code,
            "name": name,
            "bundle_price": payload.bundle_price,
            "max_drink_price": payload.max_drink_price,
            "drink_choice_count": payload.drink_choice_count,
            "side_choice_count": payload.side_choice_count,
            "eligible_drink_item_ids": eligible_drink_item_ids,
            "side_options": side_options,
            "is_active": payload.is_active,
        },
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Combo rule conflicts with existing data")

    db.expire_all()
    refreshed = _load_combo_or_404(db, row.id)
    return _combo_to_out(refreshed)


@router.put("/combos/{combo_id}", response_model=ComboRuleOut)
def update_combo_rule(
    combo_id: int,
    payload: ComboRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> ComboRuleOut:
    row = _load_combo_or_404(db, combo_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _combo_to_out(row)

    if "code" in changes:
        code = str(changes["code"]).strip().upper()
        if not code:
            raise HTTPException(status_code=400, detail="Combo code cannot be empty")
        row.code = code
    if "name" in changes:
        name = str(changes["name"]).strip()
        if not name:
            raise HTTPException(status_code=400, detail="Combo name cannot be empty")
        row.name = name
    if "bundle_price" in changes:
        row.bundle_price = float(changes["bundle_price"])
    if "max_drink_price" in changes:
        row.max_drink_price = float(changes["max_drink_price"]) if changes["max_drink_price"] is not None else None
    if "drink_choice_count" in changes:
        row.drink_choice_count = int(changes["drink_choice_count"])
    if "side_choice_count" in changes:
        row.side_choice_count = int(changes["side_choice_count"])
    if "is_active" in changes:
        row.is_active = bool(changes["is_active"])
    if "raw_rule_text" in changes:
        raw_rule_text = changes["raw_rule_text"]
        row.raw_rule_text = str(raw_rule_text).strip() if raw_rule_text is not None else None

    if "eligible_drink_item_ids" in changes:
        next_ids = _validate_menu_item_ids(db, changes["eligible_drink_item_ids"] or [])
        row.eligible_drinks.clear()
        db.flush()
        for idx, menu_item_id in enumerate(next_ids):
            db.add(
                ComboDrinkItem(
                    combo_rule_id=row.id,
                    menu_item_id=menu_item_id,
                    sort_order=idx,
                ),
            )

    if "side_options" in changes:
        next_side_options = _normalize_side_options(payload.side_options or [])
        row.side_options.clear()
        db.flush()
        for idx, option in enumerate(next_side_options):
            db.add(
                ComboSideOption(
                    combo_rule_id=row.id,
                    code=option["code"],
                    name=option["name"],
                    sort_order=idx,
                ),
            )

    candidate_drink_count = (
        len(changes["eligible_drink_item_ids"] or [])
        if "eligible_drink_item_ids" in changes
        else len(row.eligible_drinks)
    )
    candidate_side_count = len(changes["side_options"] or []) if "side_options" in changes else len(row.side_options)
    _validate_choice_counts(
        drink_choice_count=row.drink_choice_count,
        eligible_drink_count=candidate_drink_count,
        side_choice_count=row.side_choice_count,
        side_option_count=candidate_side_count,
    )

    create_audit_log(
        db,
        actor=current_user,
        action="menu.combo.update",
        entity_type="combo_rule",
        entity_id=combo_id,
        payload=changes,
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Combo rule conflicts with existing data")

    db.expire_all()
    refreshed = _load_combo_or_404(db, combo_id)
    return _combo_to_out(refreshed)


@router.post("/items", response_model=MenuItemOut, status_code=201)
def create_menu_item(
    payload: MenuItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> MenuItem:
    exists = db.scalar(select(MenuItem).where(MenuItem.name == payload.name))
    if exists:
        raise HTTPException(status_code=409, detail="Menu item already exists")
    row = MenuItem(
        name=payload.name,
        price=payload.price,
        is_active=payload.is_active,
    )
    db.add(row)
    db.flush()
    create_audit_log(
        db,
        actor=current_user,
        action="menu.create",
        entity_type="menu_item",
        entity_id=row.id,
        payload={"name": row.name, "price": row.price, "is_active": row.is_active},
    )
    db.commit()
    db.refresh(row)
    return row


@router.put("/items/{item_id}", response_model=MenuItemOut)
def update_menu_item(
    item_id: int,
    payload: MenuItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> MenuItem:
    row = db.get(MenuItem, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Menu item not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)

    create_audit_log(
        db,
        actor=current_user,
        action="menu.update",
        entity_type="menu_item",
        entity_id=row.id,
        payload=data,
    )
    db.commit()
    db.refresh(row)
    return row


@router.delete("/items/{item_id}")
def delete_menu_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> dict[str, str]:
    row = db.get(MenuItem, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Menu item not found")

    create_audit_log(
        db,
        actor=current_user,
        action="menu.delete",
        entity_type="menu_item",
        entity_id=row.id,
        payload={"name": row.name, "price": row.price},
    )
    db.delete(row)
    db.commit()
    return {"message": "Menu item deleted successfully"}


@router.get("/items/{item_id}/recipe", response_model=list[RecipeLineOut])
def get_recipe(
    item_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> list[RecipeLineOut]:
    item = db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    rows = db.scalars(
        select(RecipeLine).where(RecipeLine.menu_item_id == item_id).order_by(RecipeLine.id),
    ).all()
    output: list[RecipeLineOut] = []
    for row in rows:
        ingredient = db.get(Ingredient, row.ingredient_id)
        if not ingredient:
            continue
        output.append(
            RecipeLineOut(
                ingredient_id=ingredient.id,
                ingredient_name=ingredient.name,
                quantity=row.quantity,
                unit=ingredient.unit,
            ),
        )
    return output


@router.put("/items/{item_id}/recipe", response_model=list[RecipeLineOut])
def replace_recipe(
    item_id: int,
    payload: list[RecipeLineIn],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> list[RecipeLineOut]:
    item = db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    ingredient_ids = {line.ingredient_id for line in payload}
    if ingredient_ids:
        existing_ingredient_ids = {
            row.id for row in db.scalars(select(Ingredient).where(Ingredient.id.in_(ingredient_ids))).all()
        }
        missing = ingredient_ids - existing_ingredient_ids
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown ingredient ids: {sorted(missing)}")

    db.query(RecipeLine).filter(RecipeLine.menu_item_id == item_id).delete()
    for line in payload:
        db.add(RecipeLine(menu_item_id=item_id, ingredient_id=line.ingredient_id, quantity=line.quantity))
    create_audit_log(
        db,
        actor=current_user,
        action="menu.recipe.replace",
        entity_type="menu_item",
        entity_id=item_id,
        payload={"lines": [line.model_dump() for line in payload]},
    )
    db.commit()

    return get_recipe(item_id=item_id, db=db)
