from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from urllib import error, request


class ApiError(RuntimeError):
    pass


def _full_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _api_json(
    method: str,
    base_url: str,
    path: str,
    timeout: int,
    token: str | None = None,
    payload: dict | list | None = None,
):
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(_full_url(base_url, path), data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            if not body:
                return None
            return json.loads(body)
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        detail = raw
        try:
            parsed = json.loads(raw)
            detail = parsed.get("detail", parsed)
        except json.JSONDecodeError:
            pass
        raise ApiError(f"{method} {path} failed ({exc.code}): {detail}") from exc
    except error.URLError as exc:
        raise ApiError(f"{method} {path} failed: {exc.reason}") from exc


def _as_bool(value: object, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError(f"expected boolean but got {type(value).__name__}")


def _as_int(value: object, *, field: str, min_value: int = 0, max_value: int = 100) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be integer, got {value!r}") from exc
    if parsed < min_value or parsed > max_value:
        raise ValueError(f"{field} must be in [{min_value}, {max_value}], got {parsed}")
    return parsed


def _as_price(value: object, *, field: str, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric, got {value!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be > 0, got {parsed}")
    return round(parsed, 2)


def _clean_name(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _clean_side_options(raw_options: object, *, combo_code: str) -> list[dict]:
    if raw_options is None:
        return []
    if not isinstance(raw_options, list):
        raise ValueError(f"combo_rules[{combo_code}].side_options must be list")

    clean_options: list[dict] = []
    seen_codes: set[str] = set()
    for idx, option in enumerate(raw_options, start=1):
        if not isinstance(option, dict):
            raise ValueError(f"combo_rules[{combo_code}].side_options[{idx}] must be object")
        code = _clean_name(option.get("code"), field=f"combo_rules[{combo_code}].side_options[{idx}].code").upper()
        name = _clean_name(option.get("name"), field=f"combo_rules[{combo_code}].side_options[{idx}].name")
        if code in seen_codes:
            raise ValueError(f"combo_rules[{combo_code}] duplicate side option code: {code}")
        seen_codes.add(code)
        clean_options.append({"code": code, "name": name})
    return clean_options


def _clean_eligible_drink_names(raw_names: object, *, combo_code: str) -> list[str]:
    if raw_names is None:
        return []
    if not isinstance(raw_names, list):
        raise ValueError(f"combo_rules[{combo_code}].drink_rule.eligible_drinks must be list")
    clean_names: list[str] = []
    for idx, raw_name in enumerate(raw_names, start=1):
        name = _clean_name(raw_name, field=f"combo_rules[{combo_code}].drink_rule.eligible_drinks[{idx}]")
        clean_names.append(name)
    duplicates = [name for name, count in Counter(clean_names).items() if count > 1]
    if duplicates:
        raise ValueError(f"combo_rules[{combo_code}] duplicate eligible drink names: {sorted(duplicates)}")
    return clean_names


def load_payload(path: Path) -> tuple[list[dict], list[dict]]:
    if not path.exists():
        raise FileNotFoundError(f"payload file not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    raw_items = data.get("menu_items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("payload.menu_items must be a non-empty list")

    clean_items: list[dict] = []
    seen_names: set[str] = set()
    for idx, row in enumerate(raw_items, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"menu_items[{idx}] must be object")
        name = _clean_name(row.get("name"), field=f"menu_items[{idx}].name")
        if name in seen_names:
            raise ValueError(f"duplicate menu item name in payload: {name}")
        seen_names.add(name)
        clean_items.append(
            {
                "name": name,
                "price": _as_price(row.get("price"), field=f"menu_items[{idx}].price"),
                "is_active": _as_bool(row.get("is_active"), default=True),
            }
        )

    raw_combo_rules = data.get("combo_rules", [])
    if raw_combo_rules is None:
        raw_combo_rules = []
    if not isinstance(raw_combo_rules, list):
        raise ValueError("payload.combo_rules must be list when present")

    clean_combo_rules: list[dict] = []
    seen_combo_codes: set[str] = set()
    for idx, raw_combo in enumerate(raw_combo_rules, start=1):
        if not isinstance(raw_combo, dict):
            raise ValueError(f"combo_rules[{idx}] must be object")
        code = _clean_name(raw_combo.get("code"), field=f"combo_rules[{idx}].code").upper()
        if code in seen_combo_codes:
            raise ValueError(f"duplicate combo code in payload: {code}")
        seen_combo_codes.add(code)
        name = _clean_name(raw_combo.get("name"), field=f"combo_rules[{idx}].name")
        bundle_price = _as_price(raw_combo.get("bundle_price"), field=f"combo_rules[{idx}].bundle_price")
        is_active = _as_bool(raw_combo.get("is_active"), default=True)
        raw_rule_text = raw_combo.get("raw_rule_text")
        raw_rule_text = str(raw_rule_text).strip() if raw_rule_text else None

        drink_rule = raw_combo.get("drink_rule") or {}
        if not isinstance(drink_rule, dict):
            raise ValueError(f"combo_rules[{idx}].drink_rule must be object")
        max_drink_price = drink_rule.get("max_price", raw_combo.get("max_drink_price"))
        if max_drink_price is not None and str(max_drink_price).strip() == "":
            max_drink_price = None
        max_drink_price = _as_price(max_drink_price, field=f"combo_rules[{idx}].drink_rule.max_price", allow_none=True)
        drink_choice_count = _as_int(
            drink_rule.get("choice_count", raw_combo.get("drink_choice_count", 1)),
            field=f"combo_rules[{idx}].drink_rule.choice_count",
            min_value=0,
            max_value=20,
        )
        eligible_drink_names = _clean_eligible_drink_names(drink_rule.get("eligible_drinks"), combo_code=code)

        side_rule = raw_combo.get("side_rule") or {}
        if not isinstance(side_rule, dict):
            raise ValueError(f"combo_rules[{idx}].side_rule must be object")
        side_choice_count = _as_int(
            side_rule.get("choice_count", raw_combo.get("side_choice_count", 0)),
            field=f"combo_rules[{idx}].side_rule.choice_count",
            min_value=0,
            max_value=20,
        )
        side_options = _clean_side_options(side_rule.get("options", raw_combo.get("side_options")), combo_code=code)

        if eligible_drink_names and drink_choice_count > len(eligible_drink_names):
            raise ValueError(
                f"combo_rules[{code}] drink_choice_count cannot exceed eligible_drinks length"
            )
        if side_options and side_choice_count > len(side_options):
            raise ValueError(
                f"combo_rules[{code}] side_choice_count cannot exceed side_options length"
            )

        clean_combo_rules.append(
            {
                "code": code,
                "name": name,
                "bundle_price": bundle_price,
                "max_drink_price": max_drink_price,
                "drink_choice_count": drink_choice_count,
                "side_choice_count": side_choice_count,
                "eligible_drink_names": eligible_drink_names,
                "side_options": side_options,
                "raw_rule_text": raw_rule_text,
                "is_active": is_active,
            }
        )

    return clean_items, clean_combo_rules


def login(base_url: str, username: str, password: str, timeout: int) -> str:
    payload = {"username": username, "password": password}
    data = _api_json("POST", base_url, "/api/auth/login", timeout=timeout, payload=payload)
    if not isinstance(data, dict) or "access_token" not in data:
        raise ApiError("login response missing access_token")
    return str(data["access_token"])


def fetch_existing_menu(base_url: str, token: str, timeout: int) -> dict[str, dict]:
    rows = _api_json(
        "GET",
        base_url,
        "/api/menu/items?active_only=false",
        timeout=timeout,
        token=token,
    )
    if not isinstance(rows, list):
        raise ApiError("GET /api/menu/items returned invalid payload")
    mapped: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        mapped[name] = row
    return mapped


def fetch_existing_combos(base_url: str, token: str, timeout: int) -> dict[str, dict]:
    rows = _api_json(
        "GET",
        base_url,
        "/api/menu/combos?active_only=false",
        timeout=timeout,
        token=token,
    )
    if not isinstance(rows, list):
        raise ApiError("GET /api/menu/combos returned invalid payload")
    mapped: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code", "")).strip().upper()
        if not code:
            continue
        mapped[code] = row
    return mapped


def sync_menu_items(
    base_url: str,
    token: str,
    timeout: int,
    menu_items: list[dict],
    dry_run: bool,
) -> dict[str, int]:
    existing = fetch_existing_menu(base_url, token, timeout)
    stats = {"created": 0, "updated": 0, "unchanged": 0}

    for item in menu_items:
        current = existing.get(item["name"])
        if current is None:
            if dry_run:
                print(f"[DRY-RUN] CREATE menu item {item['name']} @ {item['price']}")
            else:
                created = _api_json("POST", base_url, "/api/menu/items", timeout=timeout, token=token, payload=item)
                if isinstance(created, dict):
                    existing[item["name"]] = created
            stats["created"] += 1
            continue

        update_payload: dict[str, object] = {}
        current_price = round(float(current.get("price", 0)), 2)
        if current_price != item["price"]:
            update_payload["price"] = item["price"]

        current_active = bool(current.get("is_active", True))
        if current_active != item["is_active"]:
            update_payload["is_active"] = item["is_active"]

        if update_payload:
            if dry_run:
                print(f"[DRY-RUN] UPDATE menu item {item['name']} -> {update_payload}")
            else:
                item_id = int(current["id"])
                updated = _api_json(
                    "PUT",
                    base_url,
                    f"/api/menu/items/{item_id}",
                    timeout=timeout,
                    token=token,
                    payload=update_payload,
                )
                if isinstance(updated, dict):
                    existing[item["name"]] = updated
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1

    return stats


def _build_combo_payload(combo: dict, menu_by_name: dict[str, dict]) -> dict:
    missing_drinks = sorted([name for name in combo["eligible_drink_names"] if name not in menu_by_name])
    if missing_drinks:
        raise ApiError(
            f"Combo {combo['code']} references unknown eligible drinks: {missing_drinks}"
        )
    eligible_drink_item_ids = [int(menu_by_name[name]["id"]) for name in combo["eligible_drink_names"]]
    return {
        "code": combo["code"],
        "name": combo["name"],
        "bundle_price": combo["bundle_price"],
        "max_drink_price": combo["max_drink_price"],
        "drink_choice_count": combo["drink_choice_count"],
        "side_choice_count": combo["side_choice_count"],
        "eligible_drink_item_ids": eligible_drink_item_ids,
        "side_options": combo["side_options"],
        "raw_rule_text": combo["raw_rule_text"],
        "is_active": combo["is_active"],
    }


def _normalize_combo_state(row: dict) -> dict:
    raw_drinks = row.get("eligible_drinks", [])
    if not isinstance(raw_drinks, list):
        raw_drinks = []
    raw_options = row.get("side_options", [])
    if not isinstance(raw_options, list):
        raw_options = []

    return {
        "name": str(row.get("name", "")).strip(),
        "bundle_price": round(float(row.get("bundle_price", 0)), 2),
        "max_drink_price": round(float(row.get("max_drink_price", 0)), 2)
        if row.get("max_drink_price") is not None
        else None,
        "drink_choice_count": int(row.get("drink_choice_count", 0)),
        "side_choice_count": int(row.get("side_choice_count", 0)),
        "eligible_drink_item_ids": [int(drink.get("menu_item_id")) for drink in raw_drinks if "menu_item_id" in drink],
        "side_options": [
            {
                "code": str(opt.get("code", "")).strip().upper(),
                "name": str(opt.get("name", "")).strip(),
            }
            for opt in raw_options
        ],
        "raw_rule_text": str(row.get("raw_rule_text", "")).strip() or None,
        "is_active": bool(row.get("is_active", True)),
    }


def _normalize_combo_payload(payload: dict) -> dict:
    return {
        "name": payload["name"],
        "bundle_price": payload["bundle_price"],
        "max_drink_price": payload["max_drink_price"],
        "drink_choice_count": payload["drink_choice_count"],
        "side_choice_count": payload["side_choice_count"],
        "eligible_drink_item_ids": payload["eligible_drink_item_ids"],
        "side_options": payload["side_options"],
        "raw_rule_text": payload["raw_rule_text"],
        "is_active": payload["is_active"],
    }


def sync_combo_rules(
    base_url: str,
    token: str,
    timeout: int,
    combo_rules: list[dict],
    menu_by_name: dict[str, dict],
    dry_run: bool,
) -> dict[str, int]:
    stats = {"created": 0, "updated": 0, "unchanged": 0}
    existing_by_code = fetch_existing_combos(base_url, token, timeout)

    for combo in combo_rules:
        desired_payload = _build_combo_payload(combo, menu_by_name)
        existing = existing_by_code.get(combo["code"])
        if existing is None:
            if dry_run:
                print(f"[DRY-RUN] CREATE combo {combo['code']} ({combo['name']})")
            else:
                created = _api_json(
                    "POST",
                    base_url,
                    "/api/menu/combos",
                    timeout=timeout,
                    token=token,
                    payload=desired_payload,
                )
                if isinstance(created, dict):
                    existing_by_code[combo["code"]] = created
            stats["created"] += 1
            continue

        current_state = _normalize_combo_state(existing)
        desired_state = _normalize_combo_payload(desired_payload)
        if current_state == desired_state:
            stats["unchanged"] += 1
            continue

        combo_id = int(existing["id"])
        if dry_run:
            print(f"[DRY-RUN] UPDATE combo {combo['code']} -> /api/menu/combos/{combo_id}")
        else:
            updated = _api_json(
                "PUT",
                base_url,
                f"/api/menu/combos/{combo_id}",
                timeout=timeout,
                token=token,
                payload=desired_payload,
            )
            if isinstance(updated, dict):
                existing_by_code[combo["code"]] = updated
        stats["updated"] += 1

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch import menu + combo rules into Breakfast Store System API.")
    parser.add_argument(
        "--file",
        default="imports/menu_202602_api_payload.json",
        help="Path to payload json file.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API base URL.",
    )
    parser.add_argument("--username", default="manager1", help="Login username (manager/owner).")
    parser.add_argument("--password", default="manager1234", help="Login password.")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing data.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload_file = Path(args.file)

    try:
        menu_items, combo_rules = load_payload(payload_file)
        token = login(args.base_url, args.username, args.password, args.timeout)
        menu_stats = sync_menu_items(args.base_url, token, args.timeout, menu_items, args.dry_run)
        menu_by_name = fetch_existing_menu(args.base_url, token, args.timeout)
        combo_stats = sync_combo_rules(
            args.base_url,
            token,
            args.timeout,
            combo_rules,
            menu_by_name,
            args.dry_run,
        )
    except (ApiError, FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    print("=== Import Summary ===")
    print(f"source_file: {payload_file}")
    print(f"dry_run: {args.dry_run}")
    print(f"menu_items.total: {len(menu_items)}")
    print(f"menu_items.created: {menu_stats['created']}")
    print(f"menu_items.updated: {menu_stats['updated']}")
    print(f"menu_items.unchanged: {menu_stats['unchanged']}")
    print(f"combo_rules.total: {len(combo_rules)}")
    print(f"combo_rules.created: {combo_stats['created']}")
    print(f"combo_rules.updated: {combo_stats['updated']}")
    print(f"combo_rules.unchanged: {combo_stats['unchanged']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
