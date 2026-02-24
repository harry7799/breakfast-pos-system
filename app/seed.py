from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Ingredient, MenuItem, RecipeLine, User
from app.schemas import UserRole
from app.security import hash_password


def seed_users(db: Session) -> None:
    has_users = db.scalar(select(User.id).limit(1))
    if has_users:
        return

    if settings.is_production:
        # In production, only create owner with a random password printed to logs
        temp_password = secrets.token_urlsafe(16)
        db.add(
            User(
                username="owner1",
                password_hash=hash_password(temp_password),
                role=UserRole.owner.value,
                is_active=True,
            ),
        )
        import logging
        logging.getLogger(__name__).warning(
            "Created initial owner account: owner1 / %s  — change this password immediately!",
            temp_password,
        )
    else:
        default_users = [
            ("staff1", "staff1234", UserRole.staff.value),
            ("kitchen1", "kitchen1234", UserRole.kitchen.value),
            ("manager1", "manager1234", UserRole.manager.value),
            ("owner1", "owner1234", UserRole.owner.value),
        ]
        for username, password, role in default_users:
            db.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                    is_active=True,
                ),
            )
    db.flush()


def seed_database(db: Session) -> None:
    seed_users(db)

    has_data = db.scalar(select(MenuItem.id).limit(1))
    if has_data:
        db.commit()
        return

    ingredients = [
        Ingredient(name="Egg", unit="pcs", current_stock=120, reorder_level=20, cost_per_unit=5),
        Ingredient(name="Bread Slice", unit="pcs", current_stock=240, reorder_level=40, cost_per_unit=3),
        Ingredient(name="Ham", unit="slice", current_stock=90, reorder_level=20, cost_per_unit=8),
        Ingredient(name="Tea Leaves", unit="g", current_stock=1500, reorder_level=300, cost_per_unit=0.1),
        Ingredient(name="Milk", unit="ml", current_stock=30000, reorder_level=5000, cost_per_unit=0.03),
        Ingredient(name="Sugar", unit="g", current_stock=5000, reorder_level=800, cost_per_unit=0.02),
    ]
    db.add_all(ingredients)
    db.flush()

    ingredient_by_name = {ing.name: ing for ing in ingredients}

    menu_items = [
        MenuItem(name="Ham Egg Toast", price=65),
        MenuItem(name="Milk Tea", price=40),
        MenuItem(name="Cheese Egg Toast", price=60),
    ]
    db.add_all(menu_items)
    db.flush()

    item_by_name = {item.name: item for item in menu_items}

    recipe_lines = [
        RecipeLine(
            menu_item_id=item_by_name["Ham Egg Toast"].id,
            ingredient_id=ingredient_by_name["Bread Slice"].id,
            quantity=2,
        ),
        RecipeLine(
            menu_item_id=item_by_name["Ham Egg Toast"].id,
            ingredient_id=ingredient_by_name["Egg"].id,
            quantity=1,
        ),
        RecipeLine(
            menu_item_id=item_by_name["Ham Egg Toast"].id,
            ingredient_id=ingredient_by_name["Ham"].id,
            quantity=1,
        ),
        RecipeLine(
            menu_item_id=item_by_name["Milk Tea"].id,
            ingredient_id=ingredient_by_name["Tea Leaves"].id,
            quantity=5,
        ),
        RecipeLine(
            menu_item_id=item_by_name["Milk Tea"].id,
            ingredient_id=ingredient_by_name["Milk"].id,
            quantity=220,
        ),
        RecipeLine(
            menu_item_id=item_by_name["Milk Tea"].id,
            ingredient_id=ingredient_by_name["Sugar"].id,
            quantity=12,
        ),
        RecipeLine(
            menu_item_id=item_by_name["Cheese Egg Toast"].id,
            ingredient_id=ingredient_by_name["Bread Slice"].id,
            quantity=2,
        ),
        RecipeLine(
            menu_item_id=item_by_name["Cheese Egg Toast"].id,
            ingredient_id=ingredient_by_name["Egg"].id,
            quantity=1,
        ),
    ]
    db.add_all(recipe_lines)
    db.commit()
