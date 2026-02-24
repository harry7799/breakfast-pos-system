from __future__ import annotations

import logging
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    ComboDrinkItem,
    ComboRule,
    ComboSideOption,
    Ingredient,
    MenuItem,
    RecipeLine,
    User,
)
from app.schemas import UserRole
from app.security import hash_password

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 完整菜單品項 (75 items)
# ---------------------------------------------------------------------------
MENU_ITEMS: list[tuple[str, float]] = [
    # PASTA
    ("[PASTA] 松子粒(素)", 125.0),
    ("[PASTA] 菇菇(素)", 145.0),
    ("[PASTA] 100%黑豬肉", 145.0),
    ("[PASTA] 100%菲瑞牛", 145.0),
    ("[PASTA] 花蛤", 150.0),
    ("[PASTA] 100%炸雞條", 150.0),
    ("[PASTA] 100%醬燒雞腿", 160.0),
    ("[PASTA] 100%舒肥雞胸", 160.0),
    # RICE_STEW
    ("[RICE_STEW] 黑豬醬", 90.0),
    ("[RICE_STEW] 菇菇(蛋素)", 90.0),
    # RICE_SAUCE
    ("[RICE_SAUCE] 杏鮑菇菇(素)", 90.0),
    ("[RICE_SAUCE] 100%梅花豬", 90.0),
    ("[RICE_SAUCE] 100%炸雞條", 95.0),
    ("[RICE_SAUCE] 100%菲瑞牛飯", 105.0),
    ("[RICE_SAUCE] 100%醬燒雞腿", 135.0),
    ("[RICE_SAUCE] 100%舒肥雞胸", 150.0),
    # RICE_DON
    ("[RICE_DON] 洋蔥醬燒豬", 115.0),
    ("[RICE_DON] 洋蔥醬燒牛肋條", 135.0),
    # UDON
    ("[UDON] 100%黑胡椒", 90.0),
    ("[UDON] 杏鮑菇菇(素)", 100.0),
    ("[UDON] 100%黑豬肉", 100.0),
    ("[UDON] 黑豬肉黑胡椒", 110.0),
    ("[UDON] 杏鮑菇黑胡椒醬", 110.0),
    # WRAP
    ("[WRAP] 原味(素)", 50.0),
    ("[WRAP] 玉米(素)", 60.0),
    ("[WRAP] 薯餅(素)", 70.0),
    ("[WRAP] 杏鮑菇(素)", 75.0),
    ("[WRAP] 梅花豬", 75.0),
    ("[WRAP] 菲瑞牛", 80.0),
    ("[WRAP] 鮪魚玉米大板燒", 80.0),
    # TOAST_EGG
    ("[TOAST_EGG] 玉米(素)", 55.0),
    ("[TOAST_EGG] 薯餅(素)", 65.0),
    ("[TOAST_EGG] 鮪魚玉米", 70.0),
    ("[TOAST_EGG] 杏鮑菇(素)", 75.0),
    ("[TOAST_EGG] 梅花豬", 75.0),
    ("[TOAST_EGG] 菲瑞牛", 80.0),
    ("[TOAST_EGG] 炸雞條", 85.0),
    ("[TOAST_EGG] 舒肥雞胸", 110.0),
    # TURNIP
    ("[TURNIP] 蘿蔔糕X2+煎蛋", 50.0),
    ("[TURNIP] 梅花豬蘿蔔糕(蛋)", 85.0),
    ("[TURNIP] 菲瑞牛蘿蔔糕(蛋)", 90.0),
    ("[TURNIP] 醬燒雞腿蘿蔔糕(蛋)", 115.0),
    ("[TURNIP] 舒肥雞胸蘿蔔糕(蛋)", 120.0),
    # SALAD
    ("[SALAD] 菲瑞牛(蛋)", 160.0),
    ("[SALAD] 醬燒雞腿(蛋)", 165.0),
    ("[SALAD] 舒肥雞胸(蛋)", 170.0),
    # JAM_TOAST
    ("[JAM_TOAST] 吉比花生醬(蛋奶素)", 45.0),
    ("[JAM_TOAST] 綜合堅果醬(蛋奶素)", 50.0),
    # SNACK
    ("[SNACK] 荷包蛋", 15.0),
    ("[SNACK] 薯餅一片(素)", 25.0),
    ("[SNACK] 港式蘿蔔糕(葷)", 45.0),
    ("[SNACK] 地瓜(素)", 45.0),
    ("[SNACK] 有機高麗菜沙拉", 50.0),
    ("[SNACK] 花蛤湯", 50.0),
    ("[SNACK] 脆薯條", 50.0),
    ("[SNACK] 100%炸雞條", 60.0),
    # DRINKS
    ("有機蔗糖紅茶 (M)", 30.0),
    ("有機蔗糖紅茶 (L)", 35.0),
    ("三種成份奶茶 (M)", 50.0),
    ("三種成份奶茶 (L)", 60.0),
    ("豆漿(非基改黃豆) (M)", 30.0),
    ("豆漿紅茶(糖) (M)", 30.0),
    ("原味冬瓜飲 (L)", 35.0),
    ("冬瓜鳳梨果汁 (L)", 55.0),
    ("冬瓜百香果果汁 (L)", 55.0),
    ("冬瓜檸檬果汁 (L)", 55.0),
    ("三種成份果汁(鳳梨) (L)", 55.0),
    ("三種成份果汁(百香果) (L)", 55.0),
    ("三種成份果汁(檸檬) (L)", 55.0),
    ("有機美式咖啡 (M)", 60.0),
    ("有機美式咖啡 (L)", 75.0),
    ("有機拿鐵(100%奶粉) (M)", 70.0),
    ("有機拿鐵(100%奶粉) (L)", 85.0),
    ("100%牛奶 (M)", 50.0),
    ("生機洛神乾果粒 (M)", 50.0),
]

# ---------------------------------------------------------------------------
# 套餐規則 (2 combos) — side_options 共用
# ---------------------------------------------------------------------------
_SHARED_SIDE_OPTIONS: list[tuple[str, str]] = [
    ("A", "100%炸雞條"),
    ("B", "脆薯"),
    ("C", "有機蔬菜番茄沙拉"),
    ("D", "有機蔬菜青檸沙拉"),
    ("E", "地瓜"),
    ("F", "花蛤湯"),
    ("G", "薯餅*2片"),
]

_SHARED_ELIGIBLE_DRINKS: list[str] = [
    "有機蔗糖紅茶 (M)",
    "有機蔗糖紅茶 (L)",
    "豆漿(非基改黃豆) (M)",
    "豆漿紅茶(糖) (M)",
    "原味冬瓜飲 (L)",
]

COMBO_RULES: list[dict] = [
    {
        "code": "SET60",
        "name": "60元套餐",
        "bundle_price": 60.0,
        "max_drink_price": 35.0,
        "side_choice_count": 1,
        "raw_rule_text": "35元以下飲品+A-G 選一種.",
    },
    {
        "code": "SET95",
        "name": "95元套餐",
        "bundle_price": 95.0,
        "max_drink_price": 35.0,
        "side_choice_count": 2,
        "raw_rule_text": "35元以下飲品+A-G 選二種.",
    },
]


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
        logger.warning(
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


# ---------------------------------------------------------------------------
# 基本食材 + 配方（供庫存扣減功能使用）
# ---------------------------------------------------------------------------
SEED_INGREDIENTS: list[dict] = [
    {"name": "雞蛋", "unit": "pcs", "current_stock": 120, "reorder_level": 20, "cost_per_unit": 5},
    {"name": "吐司片", "unit": "pcs", "current_stock": 240, "reorder_level": 40, "cost_per_unit": 3},
    {"name": "玉米粒", "unit": "g", "current_stock": 3000, "reorder_level": 500, "cost_per_unit": 0.05},
    {"name": "紅茶茶葉", "unit": "g", "current_stock": 1500, "reorder_level": 300, "cost_per_unit": 0.1},
    {"name": "鮮奶", "unit": "ml", "current_stock": 30000, "reorder_level": 5000, "cost_per_unit": 0.03},
    {"name": "糖", "unit": "g", "current_stock": 5000, "reorder_level": 800, "cost_per_unit": 0.02},
]

# menu_item_name → [(ingredient_name, quantity), ...]
SEED_RECIPES: dict[str, list[tuple[str, float]]] = {
    "[TOAST_EGG] 玉米(素)": [
        ("吐司片", 2),
        ("雞蛋", 1),
        ("玉米粒", 30),
    ],
    "有機蔗糖紅茶 (M)": [
        ("紅茶茶葉", 5),
        ("糖", 12),
    ],
    "三種成份奶茶 (M)": [
        ("紅茶茶葉", 5),
        ("鮮奶", 220),
        ("糖", 12),
    ],
}


def _seed_menu(db: Session) -> None:
    """Seed the full 75-item menu."""
    menu_objs = [MenuItem(name=name, price=price, is_active=True) for name, price in MENU_ITEMS]
    db.add_all(menu_objs)
    db.flush()
    logger.info("Seeded %d menu items.", len(menu_objs))


def _seed_ingredients_and_recipes(db: Session) -> None:
    """Seed ingredients and recipe lines."""
    ing_objs = [
        Ingredient(**data) for data in SEED_INGREDIENTS
    ]
    db.add_all(ing_objs)
    db.flush()

    ing_by_name = {ing.name: ing for ing in ing_objs}
    item_by_name: dict[str, MenuItem] = {}
    for item_name in SEED_RECIPES:
        item = db.scalar(select(MenuItem).where(MenuItem.name == item_name))
        if item:
            item_by_name[item_name] = item

    for item_name, lines in SEED_RECIPES.items():
        menu_item = item_by_name.get(item_name)
        if not menu_item:
            logger.warning("Recipe target menu item not found: %s", item_name)
            continue
        for ing_name, qty in lines:
            ing = ing_by_name.get(ing_name)
            if not ing:
                logger.warning("Ingredient not found: %s", ing_name)
                continue
            db.add(RecipeLine(menu_item_id=menu_item.id, ingredient_id=ing.id, quantity=qty))

    db.flush()
    logger.info("Seeded %d ingredients and recipes for %d items.", len(ing_objs), len(SEED_RECIPES))


def _seed_combo_rules(db: Session) -> None:
    """Seed combo rules with eligible drinks + side options."""
    # Build name→MenuItem lookup for drink linking
    drink_lookup: dict[str, MenuItem] = {}
    for drink_name in _SHARED_ELIGIBLE_DRINKS:
        item = db.scalar(select(MenuItem).where(MenuItem.name == drink_name))
        if item:
            drink_lookup[drink_name] = item
        else:
            logger.warning("Combo eligible drink not found in menu: %s", drink_name)

    for rule_data in COMBO_RULES:
        combo = ComboRule(
            code=rule_data["code"],
            name=rule_data["name"],
            bundle_price=rule_data["bundle_price"],
            max_drink_price=rule_data["max_drink_price"],
            drink_choice_count=1,
            side_choice_count=rule_data["side_choice_count"],
            is_active=True,
            raw_rule_text=rule_data["raw_rule_text"],
        )
        db.add(combo)
        db.flush()

        # Link eligible drinks
        for sort_idx, drink_name in enumerate(_SHARED_ELIGIBLE_DRINKS):
            if drink_name in drink_lookup:
                db.add(
                    ComboDrinkItem(
                        combo_rule_id=combo.id,
                        menu_item_id=drink_lookup[drink_name].id,
                        sort_order=sort_idx,
                    )
                )

        # Add side options
        for sort_idx, (code, name) in enumerate(_SHARED_SIDE_OPTIONS):
            db.add(
                ComboSideOption(
                    combo_rule_id=combo.id,
                    code=code,
                    name=name,
                    sort_order=sort_idx,
                )
            )

        db.flush()

    logger.info("Seeded %d combo rules.", len(COMBO_RULES))


def seed_database(db: Session) -> None:
    seed_users(db)

    has_data = db.scalar(select(MenuItem.id).limit(1))
    if has_data:
        db.commit()
        return

    _seed_menu(db)
    _seed_ingredients_and_recipes(db)
    _seed_combo_rules(db)
    db.commit()
