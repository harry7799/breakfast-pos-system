"""
Import menu items, ingredients, and recipes from the Excel spreadsheet.

Usage:
    python scripts/import_excel_menu.py
    python scripts/import_excel_menu.py --dry-run
    python scripts/import_excel_menu.py --file path/to/file.xlsx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

import openpyxl

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_XLSX = str(
    Path(__file__).resolve().parent.parent
    / "青青草原廚房_整理版ETHAEHTEHE菜單.xlsx"
)
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_USER = "manager1"
DEFAULT_PASS = "manager1234"

# Category -> group code (used as [TAG] prefix in item names for frontend categorization)
CATEGORY_GROUP = {
    "有機藜麥燉飯/義大利麵": "PASTA",
    "有機藜麥白飯(燴飯)": "RICE_STEW",
    "有機藜麥白飯(醬汁飯)": "RICE_SAUCE",
    "有機藜麥白飯(丼飯)": "RICE_DON",
    "鍋炒烏龍麵": "UDON",
    "虎皮蛋捲餅": "WRAP",
    "總匯吐司蛋": "TOAST_EGG",
    "蘿蔔糕特餐": "TURNIP",
    "有機高麗菜綜合沙拉": "SALAD",
    "果醬吐司(2片)": "JAM_TOAST",
    "點心": "SNACK",
    "茶類/奶茶": "DRINK",
    "冬瓜飲/果汁": "DRINK",
    "咖啡/熱飲": "DRINK",
}

# No longer needed — all food items get [TAG] prefix now
# CATEGORY_PREFIX removed

# Drink categories that need (M)/(L) size suffixes
DRINK_CATEGORIES = {"茶類/奶茶", "冬瓜飲/果汁", "咖啡/熱飲"}

# Categories to skip (not real menu items)
SKIP_CATEGORIES = {"60元套餐", "95元套餐", "點心代號說明"}

# Base veggies columns (5-9) — shared by all items in a category
BASE_VEGGIE_COLS = [5, 6, 7, 8, 9]


# ---------------------------------------------------------------------------
# Excel parsing
# ---------------------------------------------------------------------------
def parse_quantity_from_text(text: str) -> tuple[str, float]:
    """Extract ingredient name and quantity from text like '雞蛋(1個)' or '蘿蔔糕(2片)'."""
    m = re.match(r"^(.+?)\((\d+)[^)]*\)$", text)
    if m:
        return m.group(1), float(m.group(2))
    return text, 1.0


def parse_excel(xlsx_path: str) -> dict:
    """Parse the Excel file and return structured data."""
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["主食系列"]

    rows = []
    for row in ws.iter_rows(min_row=1, values_only=True):
        vals = [str(cell) if cell is not None else "" for cell in row]
        rows.append(vals)

    # Skip header row
    data_rows = rows[1:]

    # --- Pass 1: collect all raw items with category ---
    raw_items = []
    current_category = ""
    base_veggies: list[str] = []  # shared veggies for current category

    for vals in data_rows:
        category = vals[0].strip()
        item_name = vals[1].strip()
        price_str = vals[2].strip()
        price_l_str = vals[3].strip() if len(vals) > 3 else ""

        if not item_name:
            continue
        if category:
            current_category = category

        if current_category in SKIP_CATEGORIES:
            continue

        # Parse price
        price_m = float(price_str) if price_str and price_str.replace(".", "").isdigit() else 0
        price_l = float(price_l_str) if price_l_str and price_l_str.replace(".", "").isdigit() else 0

        # Check if this row defines base veggies (first item in category)
        row_veggies = [vals[c].strip() for c in BASE_VEGGIE_COLS if c < len(vals) and vals[c].strip()]
        if category and row_veggies:
            base_veggies = row_veggies
        elif category and not row_veggies:
            # New category without base veggies
            base_veggies = []

        # Collect ingredient columns (10-13)
        item_ingredients = []
        for c in range(10, min(14, len(vals))):
            ing = vals[c].strip()
            if ing:
                item_ingredients.append(ing)

        raw_items.append({
            "category": current_category,
            "raw_name": item_name,
            "price_m": price_m,
            "price_l": price_l,
            "base_veggies": list(base_veggies),
            "ingredients": item_ingredients,
        })

    # --- Pass 2: collect ingredient list from right-side columns (18-19) ---
    ingredient_list = []
    for vals in data_rows:
        if len(vals) > 19:
            ing_name = vals[18].strip()
            ing_unit = vals[19].strip()
        elif len(vals) > 18:
            ing_name = vals[18].strip()
            ing_unit = ""
        else:
            continue
        if ing_name and ing_name != "品項" and ing_unit and ing_unit != "單位":
            ingredient_list.append({"name": ing_name, "unit": ing_unit})

    # --- Pass 3: detect duplicate names and build final menu items ---
    name_counts: dict[str, list[str]] = {}
    for item in raw_items:
        name_counts.setdefault(item["raw_name"], []).append(item["category"])

    duplicates = {name for name, cats in name_counts.items() if len(cats) > 1}

    menu_items = []
    recipes = {}  # import_name -> list of ingredient texts

    for item in raw_items:
        cat = item["category"]
        group = CATEGORY_GROUP.get(cat, "")

        if cat in DRINK_CATEGORIES:
            # Drinks: create M and/or L variants
            if item["price_m"] > 0:
                name = f"{item['raw_name']} (M)"
                menu_items.append({"name": name, "price": item["price_m"], "is_active": True})
                recipes[name] = item["ingredients"]
            if item["price_l"] > 0:
                name = f"{item['raw_name']} (L)"
                menu_items.append({"name": name, "price": item["price_l"], "is_active": True})
                recipes[name] = item["ingredients"]
        else:
            # Food items — always use [TAG] prefix for frontend categorization
            group = CATEGORY_GROUP.get(cat, "")
            if group:
                name = f"[{group}] {item['raw_name']}"
            else:
                name = item["raw_name"]

            price = item["price_m"] if item["price_m"] > 0 else item["price_l"]
            if price <= 0:
                continue

            menu_items.append({"name": name, "price": price, "is_active": True})
            # Recipe = base veggies + specific ingredients
            all_ings = item["base_veggies"] + item["ingredients"]
            if all_ings:
                recipes[name] = all_ings

    # --- Pass 4: collect combo rules ---
    combo_rules = []
    side_options = []

    for vals in data_rows:
        cat = vals[0].strip()
        if cat == "點心代號說明":
            code = vals[1].strip()
            desc = vals[2].strip()
            if code and desc:
                side_options.append({"code": code, "name": desc})

    # Find eligible drinks (price <= 35)
    eligible_drinks = [
        item["name"] for item in menu_items
        if item["price"] <= 35 and any(
            item["name"].endswith(s) for s in [" (M)", " (L)"]
        )
    ]

    if side_options:
        combo_rules.append({
            "code": "SET60",
            "name": "60元套餐",
            "bundle_price": 60,
            "raw_rule_text": "35元以下飲品+A-G 選一種.",
            "drink_rule": {"max_price": 35, "eligible_drinks": eligible_drinks},
            "side_rule": {"choice_count": 1, "options": side_options},
        })
        combo_rules.append({
            "code": "SET95",
            "name": "95元套餐",
            "bundle_price": 95,
            "raw_rule_text": "35元以下飲品+A-G 選二種.",
            "drink_rule": {"max_price": 35, "eligible_drinks": eligible_drinks},
            "side_rule": {"choice_count": 2, "options": side_options},
        })

    return {
        "menu_items": menu_items,
        "combo_rules": combo_rules,
        "ingredient_list": ingredient_list,
        "recipes": recipes,
    }


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def api_call(method: str, url: str, token: str, data: dict | list | None = None) -> dict | list | None:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        print(f"  !! HTTP {e.code}: {body_text}")
        return None


def login(base_url: str, username: str, password: str) -> str:
    data = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        f"{base_url}/api/auth/login",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]


# ---------------------------------------------------------------------------
# Import logic
# ---------------------------------------------------------------------------
def _strip_tag(name: str) -> str:
    """Remove [TAG] prefix from a name for fuzzy matching."""
    m = re.match(r"^\[([A-Z_]+)\]\s*(.+)$", name)
    return m.group(2) if m else name


def sync_menu_items(base_url: str, token: str, items: list[dict], dry_run: bool) -> dict[str, int]:
    """Sync menu items, return name->id mapping.

    Matches by exact name first, then by stripped name (ignoring [TAG] prefix)
    to handle migration from untagged to tagged names.
    """
    existing = api_call("GET", f"{base_url}/api/menu/items?active_only=false", token) or []
    existing_by_name = {item["name"]: item for item in existing}
    # Build a lookup by stripped name for fuzzy matching
    existing_by_stripped = {}
    for item in existing:
        stripped = _strip_tag(item["name"])
        existing_by_stripped.setdefault(stripped, []).append(item)

    name_to_id: dict[str, int] = {}
    matched_ids: set[int] = set()
    created = updated = renamed = skipped = 0

    for item in items:
        name = item["name"]
        stripped = _strip_tag(name)

        # Try exact match first
        ex = existing_by_name.get(name)

        # If no exact match, try matching by stripped name
        if not ex:
            candidates = existing_by_stripped.get(stripped, [])
            # Pick the candidate whose price is closest (handles duplicates)
            for c in candidates:
                if c["id"] not in matched_ids:
                    ex = c
                    break

        if ex:
            matched_ids.add(ex["id"])
            changes = {}
            if ex["name"] != name:
                changes["name"] = name
            if abs(ex["price"] - item["price"]) > 0.01:
                changes["price"] = item["price"]
            if ex["is_active"] != item["is_active"]:
                changes["is_active"] = item["is_active"]

            if changes:
                action = "RENAME+UPDATE" if "name" in changes else "UPDATE"
                print(f"  {action}: {ex['name']} -> {name} ${item['price']}")
                if not dry_run:
                    result = api_call("PUT", f"{base_url}/api/menu/items/{ex['id']}", token, changes)
                    if result:
                        name_to_id[name] = result["id"]
                if "name" in changes:
                    renamed += 1
                else:
                    updated += 1
            else:
                skipped += 1
                name_to_id[name] = ex["id"]
        else:
            print(f"  CREATE: {name} ${item['price']}")
            if not dry_run:
                result = api_call("POST", f"{base_url}/api/menu/items", token, item)
                if result:
                    name_to_id[name] = result["id"]
            created += 1

    # Deactivate old items not in the new list
    deactivated = 0
    for ex in existing:
        if ex["id"] not in matched_ids and ex["id"] not in name_to_id.values():
            if ex["is_active"]:
                print(f"  DEACTIVATE: {ex['name']}")
                if not dry_run:
                    api_call("PUT", f"{base_url}/api/menu/items/{ex['id']}", token, {"is_active": False})
                deactivated += 1

    print(f"  菜單: {created} 新增, {renamed} 改名, {updated} 更新, {skipped} 不變, {deactivated} 停用")
    return name_to_id


def sync_ingredients(base_url: str, token: str, ingredients: list[dict], dry_run: bool) -> dict[str, int]:
    """Sync ingredients, return name->id mapping."""
    existing = api_call("GET", f"{base_url}/api/inventory/ingredients", token) or []
    existing_map = {ing["name"]: ing for ing in existing}
    name_to_id = {ing["name"]: ing["id"] for ing in existing}

    created = skipped = 0
    for ing in ingredients:
        name = ing["name"]
        if name in existing_map:
            skipped += 1
        else:
            print(f"  CREATE: {name} ({ing['unit']})")
            if not dry_run:
                result = api_call("POST", f"{base_url}/api/inventory/ingredients", token, {
                    "name": name,
                    "unit": ing["unit"],
                    "current_stock": 0,
                    "reorder_level": 10,
                    "cost_per_unit": 0,
                })
                if result:
                    name_to_id[name] = result["id"]
            created += 1

    print(f"  食材: {created} 新增, {skipped} 已存在")
    return name_to_id


def sync_recipes(
    base_url: str,
    token: str,
    recipes: dict[str, list[str]],
    menu_id_map: dict[str, int],
    ingredient_id_map: dict[str, int],
    dry_run: bool,
) -> None:
    """Set recipe lines for each menu item."""
    set_count = skip_count = 0

    for menu_name, ing_texts in recipes.items():
        menu_id = menu_id_map.get(menu_name)
        if not menu_id:
            continue

        lines = []
        for text in ing_texts:
            ing_name, qty = parse_quantity_from_text(text)
            ing_id = ingredient_id_map.get(ing_name)
            if ing_id:
                lines.append({"ingredient_id": ing_id, "quantity": qty})

        if not lines:
            skip_count += 1
            continue

        print(f"  RECIPE: {menu_name} → {len(lines)} 種食材")
        if not dry_run:
            api_call("PUT", f"{base_url}/api/menu/items/{menu_id}/recipe", token, lines)
        set_count += 1

    print(f"  配方: {set_count} 設定, {skip_count} 跳過(無匹配食材)")


def sync_combos(base_url: str, token: str, combos: list[dict], menu_id_map: dict[str, int], dry_run: bool) -> None:
    """Sync combo rules."""
    existing = api_call("GET", f"{base_url}/api/menu/combos?active_only=false", token) or []
    existing_map = {c["code"]: c for c in existing}

    created = updated = skipped = 0
    for combo in combos:
        code = combo["code"].upper()
        drink_names = combo.get("drink_rule", {}).get("eligible_drinks", [])
        drink_ids = [menu_id_map[n] for n in drink_names if n in menu_id_map]
        side_opts = combo.get("side_rule", {}).get("options", [])
        side_count = combo.get("side_rule", {}).get("choice_count", 0)

        payload = {
            "code": code,
            "name": combo["name"],
            "bundle_price": combo["bundle_price"],
            "max_drink_price": combo.get("drink_rule", {}).get("max_price"),
            "drink_choice_count": 1,
            "side_choice_count": side_count,
            "eligible_drink_item_ids": drink_ids,
            "side_options": side_opts,
            "raw_rule_text": combo.get("raw_rule_text", ""),
            "is_active": True,
        }

        if code in existing_map:
            ex = existing_map[code]
            print(f"  UPDATE: {code} {combo['name']}")
            if not dry_run:
                api_call("PUT", f"{base_url}/api/menu/combos/{ex['id']}", token, payload)
            updated += 1
        else:
            print(f"  CREATE: {code} {combo['name']}")
            if not dry_run:
                api_call("POST", f"{base_url}/api/menu/combos", token, payload)
            created += 1

    print(f"  套餐: {created} 新增, {updated} 更新")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Import Excel menu into the system")
    parser.add_argument("--file", default=DEFAULT_XLSX, help="Path to xlsx file")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--username", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASS)
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    args = parser.parse_args()

    print(f"[*] Excel: {args.file}")
    data = parse_excel(args.file)

    print(f"\n[i] 解析結果:")
    print(f"    菜單品項: {len(data['menu_items'])} 項")
    print(f"    食材清單: {len(data['ingredient_list'])} 種")
    print(f"    配方關聯: {len(data['recipes'])} 項")
    print(f"    套餐規則: {len(data['combo_rules'])} 組")

    if args.dry_run:
        print("\n[DRY RUN] 預覽模式，不會實際寫入\n")
    else:
        print()

    # Save generated payload for reference
    payload_path = Path(args.file).parent / "imports" / "menu_from_excel.json"
    payload_path.parent.mkdir(exist_ok=True)
    with open(payload_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[>] 已儲存解析結果: {payload_path}\n")

    # Login
    print("[*] 登入中...")
    token = login(args.base_url, args.username, args.password)
    print("    登入成功\n")

    # Phase 1: Menu items
    print("[1/4] 同步菜單品項")
    menu_id_map = sync_menu_items(args.base_url, token, data["menu_items"], args.dry_run)

    # Phase 2: Ingredients
    print("\n[2/4] 同步食材")
    ing_id_map = sync_ingredients(args.base_url, token, data["ingredient_list"], args.dry_run)

    # Phase 3: Recipes
    print("\n[3/4] 設定配方")
    sync_recipes(args.base_url, token, data["recipes"], menu_id_map, ing_id_map, args.dry_run)

    # Phase 4: Combos
    print("\n[4/4] 同步套餐規則")
    sync_combos(args.base_url, token, data["combo_rules"], menu_id_map, args.dry_run)

    print("\n[OK] 匯入完成!")


if __name__ == "__main__":
    main()
