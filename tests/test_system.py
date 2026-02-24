import os
from pathlib import Path
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_breakfast.db"
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key"
sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app, clear_rate_limits
from app.seed import seed_database

client = TestClient(app)


def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)


def find_item(rows: list[dict], key: str, value: str) -> dict:
    for row in rows:
        if row[key] == value:
            return row
    raise AssertionError(f"Cannot find row where {key}={value}")


def auth_headers(username: str, password: str) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def setup_function() -> None:
    clear_rate_limits()
    reset_db()


def test_auth_and_role_guard() -> None:
    staff_headers = auth_headers("staff1", "staff1234")

    me_res = client.get("/api/auth/me", headers=staff_headers)
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "staff"

    analytics_res = client.get("/api/analytics/overview", headers=staff_headers)
    assert analytics_res.status_code == 403


def test_login_rate_limit_blocks_excessive_attempts() -> None:
    for _ in range(10):
        res = client.post("/api/auth/login", json={"username": "staff1", "password": "wrong-password"})
        assert res.status_code == 401

    blocked = client.post("/api/auth/login", json={"username": "staff1", "password": "wrong-password"})
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many login attempts. Please try again later."


def test_login_rate_limit_does_not_count_successful_logins() -> None:
    for _ in range(12):
        res = client.post("/api/auth/login", json={"username": "staff1", "password": "staff1234"})
        assert res.status_code == 200


def test_login_rate_limit_isolated_by_username() -> None:
    for _ in range(10):
        res = client.post("/api/auth/login", json={"username": "staff1", "password": "wrong-password"})
        assert res.status_code == 401

    other_user = client.post("/api/auth/login", json={"username": "manager1", "password": "manager1234"})
    assert other_user.status_code == 200


def test_order_auto_pay_deduct_inventory() -> None:
    staff_headers = auth_headers("staff1", "staff1234")
    manager_headers = auth_headers("manager1", "manager1234")

    before_ingredients = client.get("/api/inventory/ingredients", headers=manager_headers).json()
    egg_before = find_item(before_ingredients, "name", "Egg")["current_stock"]
    bread_before = find_item(before_ingredients, "name", "Bread Slice")["current_stock"]

    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    toast = find_item(menu_items, "name", "Ham Egg Toast")

    response = client.post(
        "/api/orders",
        headers=staff_headers,
        json={
            "source": "takeout",
            "auto_pay": True,
            "items": [{"menu_item_id": toast["id"], "quantity": 2}],
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert created["payment_status"] == "paid"
    assert created["total_amount"] == 130

    after_ingredients = client.get("/api/inventory/ingredients", headers=manager_headers).json()
    egg_after = find_item(after_ingredients, "name", "Egg")["current_stock"]
    bread_after = find_item(after_ingredients, "name", "Bread Slice")["current_stock"]

    assert egg_after == egg_before - 2
    assert bread_after == bread_before - 4


def test_kitchen_can_update_status() -> None:
    staff_headers = auth_headers("staff1", "staff1234")
    kitchen_headers = auth_headers("kitchen1", "kitchen1234")

    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    milk_tea = find_item(menu_items, "name", "Milk Tea")

    create_res = client.post(
        "/api/orders",
        headers=staff_headers,
        json={
            "source": "dine_in",
            "auto_pay": False,
            "items": [{"menu_item_id": milk_tea["id"], "quantity": 1}],
        },
    )
    assert create_res.status_code == 201
    order_id = create_res.json()["id"]

    status_res = client.post(
        f"/api/orders/{order_id}/status",
        headers=kitchen_headers,
        json={"status": "preparing"},
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "preparing"


def test_analytics_overview_with_manager() -> None:
    staff_headers = auth_headers("staff1", "staff1234")
    manager_headers = auth_headers("manager1", "manager1234")

    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    toast = find_item(menu_items, "name", "Ham Egg Toast")

    order_res = client.post(
        "/api/orders",
        headers=staff_headers,
        json={
            "source": "takeout",
            "auto_pay": True,
            "items": [{"menu_item_id": toast["id"], "quantity": 1}],
        },
    )
    assert order_res.status_code == 201

    analytics_res = client.get("/api/analytics/overview", headers=manager_headers)
    assert analytics_res.status_code == 200
    payload = analytics_res.json()
    assert payload["total_orders"] >= 1
    assert payload["total_revenue"] >= 65
    assert any(item["menu_item_name"] == "Ham Egg Toast" for item in payload["top_items"])


def test_insufficient_inventory_blocks_auto_pay_order() -> None:
    staff_headers = auth_headers("staff1", "staff1234")
    manager_headers = auth_headers("manager1", "manager1234")

    ingredients = client.get("/api/inventory/ingredients", headers=manager_headers).json()
    egg = find_item(ingredients, "name", "Egg")
    set_stock_res = client.put(
        f"/api/inventory/ingredients/{egg['id']}",
        headers=manager_headers,
        json={"current_stock": 0},
    )
    assert set_stock_res.status_code == 200

    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    toast = find_item(menu_items, "name", "Ham Egg Toast")

    order_res = client.post(
        "/api/orders",
        headers=staff_headers,
        json={
            "source": "takeout",
            "auto_pay": True,
            "items": [{"menu_item_id": toast["id"], "quantity": 1}],
        },
    )
    assert order_res.status_code == 409
    payload = order_res.json()
    assert payload["detail"]["message"] == "Insufficient inventory"
    assert any(row["ingredient_name"] == "Egg" for row in payload["detail"]["shortages"])

    orders_res = client.get("/api/orders", headers=staff_headers)
    assert orders_res.status_code == 200
    assert orders_res.json() == []


def test_cancelled_order_restores_inventory() -> None:
    staff_headers = auth_headers("staff1", "staff1234")
    kitchen_headers = auth_headers("kitchen1", "kitchen1234")
    manager_headers = auth_headers("manager1", "manager1234")

    before_ingredients = client.get("/api/inventory/ingredients", headers=manager_headers).json()
    egg_before = find_item(before_ingredients, "name", "Egg")["current_stock"]

    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    toast = find_item(menu_items, "name", "Ham Egg Toast")

    create_res = client.post(
        "/api/orders",
        headers=staff_headers,
        json={
            "source": "takeout",
            "auto_pay": True,
            "items": [{"menu_item_id": toast["id"], "quantity": 2}],
        },
    )
    assert create_res.status_code == 201
    order_id = create_res.json()["id"]

    after_pay_ingredients = client.get("/api/inventory/ingredients", headers=manager_headers).json()
    egg_after_pay = find_item(after_pay_ingredients, "name", "Egg")["current_stock"]
    assert egg_after_pay == egg_before - 2

    cancel_res = client.post(
        f"/api/orders/{order_id}/status",
        headers=kitchen_headers,
        json={"status": "cancelled"},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    after_cancel_ingredients = client.get("/api/inventory/ingredients", headers=manager_headers).json()
    egg_after_cancel = find_item(after_cancel_ingredients, "name", "Egg")["current_stock"]
    assert egg_after_cancel == egg_before


def test_audit_logs_capture_actions() -> None:
    owner_headers = auth_headers("owner1", "owner1234")
    manager_headers = auth_headers("manager1", "manager1234")

    create_user_res = client.post(
        "/api/auth/users",
        headers=owner_headers,
        json={
            "username": "audittest",
            "password": "audittest123",
            "role": "staff",
            "is_active": True,
        },
    )
    assert create_user_res.status_code == 201

    logs_res = client.get("/api/audit/logs?limit=100", headers=manager_headers)
    assert logs_res.status_code == 200
    logs = logs_res.json()
    actions = [row["action"] for row in logs]
    assert "auth.login" in actions
    assert "user.create" in actions


def test_amend_paid_order_adjusts_inventory_delta() -> None:
    staff_headers = auth_headers("staff1", "staff1234")
    manager_headers = auth_headers("manager1", "manager1234")

    ingredients_before = client.get("/api/inventory/ingredients", headers=manager_headers).json()
    egg_before = find_item(ingredients_before, "name", "Egg")["current_stock"]

    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    toast = find_item(menu_items, "name", "Ham Egg Toast")

    create_res = client.post(
        "/api/orders",
        headers=staff_headers,
        json={
            "source": "takeout",
            "auto_pay": True,
            "items": [{"menu_item_id": toast["id"], "quantity": 1}],
        },
    )
    assert create_res.status_code == 201
    order_id = create_res.json()["id"]

    amend_res = client.post(
        f"/api/orders/{order_id}/amend",
        headers=staff_headers,
        json={
            "items": [{"menu_item_id": toast["id"], "quantity": 3}],
        },
    )
    assert amend_res.status_code == 200
    payload = amend_res.json()
    assert payload["order"]["total_amount"] == 195
    assert payload["diff"]["quantity_changed"][0]["before_quantity"] == 1
    assert payload["diff"]["quantity_changed"][0]["after_quantity"] == 3

    ingredients_after_grow = client.get("/api/inventory/ingredients", headers=manager_headers).json()
    egg_after_grow = find_item(ingredients_after_grow, "name", "Egg")["current_stock"]
    assert egg_after_grow == egg_before - 3

    amend_back_res = client.post(
        f"/api/orders/{order_id}/amend",
        headers=staff_headers,
        json={
            "items": [{"menu_item_id": toast["id"], "quantity": 1}],
        },
    )
    assert amend_back_res.status_code == 200
    payload_back = amend_back_res.json()
    assert payload_back["order"]["total_amount"] == 65
    assert payload_back["diff"]["quantity_changed"][0]["before_quantity"] == 3
    assert payload_back["diff"]["quantity_changed"][0]["after_quantity"] == 1

    ingredients_after_shrink = client.get("/api/inventory/ingredients", headers=manager_headers).json()
    egg_after_shrink = find_item(ingredients_after_shrink, "name", "Egg")["current_stock"]
    assert egg_after_shrink == egg_before - 1


def test_kitchen_can_view_low_stock() -> None:
    manager_headers = auth_headers("manager1", "manager1234")
    kitchen_headers = auth_headers("kitchen1", "kitchen1234")
    staff_headers = auth_headers("staff1", "staff1234")

    ingredients = client.get("/api/inventory/ingredients", headers=manager_headers).json()
    egg = find_item(ingredients, "name", "Egg")

    update_res = client.put(
        f"/api/inventory/ingredients/{egg['id']}",
        headers=manager_headers,
        json={"current_stock": 10},
    )
    assert update_res.status_code == 200

    kitchen_res = client.get("/api/inventory/low-stock", headers=kitchen_headers)
    assert kitchen_res.status_code == 200
    assert any(row["ingredient_name"] == "Egg" for row in kitchen_res.json())

    staff_res = client.get("/api/inventory/low-stock", headers=staff_headers)
    assert staff_res.status_code == 403


def test_manager_can_create_and_update_combo_rule() -> None:
    manager_headers = auth_headers("manager1", "manager1234")
    staff_headers = auth_headers("staff1", "staff1234")

    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    milk_tea = find_item(menu_items, "name", "Milk Tea")

    create_res = client.post(
        "/api/menu/combos",
        headers=manager_headers,
        json={
            "code": "set40",
            "name": "40 Drink Set",
            "bundle_price": 40,
            "max_drink_price": 40,
            "drink_choice_count": 1,
            "side_choice_count": 1,
            "eligible_drink_item_ids": [milk_tea["id"]],
            "side_options": [{"code": "A", "name": "French Fries"}],
            "raw_rule_text": "<=40 drink + choose one side",
            "is_active": True,
        },
    )
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["code"] == "SET40"
    assert created["eligible_drinks"][0]["menu_item_id"] == milk_tea["id"]
    combo_id = created["id"]

    list_res = client.get("/api/menu/combos", headers=staff_headers)
    assert list_res.status_code == 200
    assert any(row["id"] == combo_id for row in list_res.json())

    update_res = client.put(
        f"/api/menu/combos/{combo_id}",
        headers=manager_headers,
        json={
            "side_choice_count": 2,
            "side_options": [
                {"code": "A", "name": "French Fries"},
                {"code": "B", "name": "Soup"},
            ],
            "is_active": False,
        },
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["side_choice_count"] == 2
    assert len(updated["side_options"]) == 2
    assert updated["is_active"] is False

    inactive_list_res = client.get("/api/menu/combos?active_only=false", headers=staff_headers)
    assert inactive_list_res.status_code == 200
    assert any(row["id"] == combo_id and row["is_active"] is False for row in inactive_list_res.json())


def test_staff_cannot_create_combo_rule() -> None:
    staff_headers = auth_headers("staff1", "staff1234")
    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    milk_tea = find_item(menu_items, "name", "Milk Tea")

    res = client.post(
        "/api/menu/combos",
        headers=staff_headers,
        json={
            "code": "SET403",
            "name": "Forbidden Set",
            "bundle_price": 40,
            "drink_choice_count": 1,
            "side_choice_count": 0,
            "eligible_drink_item_ids": [milk_tea["id"]],
            "side_options": [],
        },
    )
    assert res.status_code == 403


def test_combo_order_uses_bundle_price_not_sum_of_items() -> None:
    manager_headers = auth_headers("manager1", "manager1234")
    staff_headers = auth_headers("staff1", "staff1234")

    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    milk_tea = find_item(menu_items, "name", "Milk Tea")
    toast = find_item(menu_items, "name", "Ham Egg Toast")

    combo_res = client.post(
        "/api/menu/combos",
        headers=manager_headers,
        json={
            "code": "SET60B",
            "name": "60 Bundle",
            "bundle_price": 60,
            "max_drink_price": 60,
            "drink_choice_count": 1,
            "side_choice_count": 1,
            "eligible_drink_item_ids": [milk_tea["id"]],
            "side_options": [{"code": "A", "name": "Any Side"}],
            "is_active": True,
        },
    )
    assert combo_res.status_code == 201
    combo_id = combo_res.json()["id"]

    order_res = client.post(
        "/api/orders",
        headers=staff_headers,
        json={
            "source": "takeout",
            "auto_pay": False,
            "items": [],
            "combos": [
                {
                    "combo_id": combo_id,
                    "drink_item_ids": [milk_tea["id"]],
                    "side_item_ids": [toast["id"]],
                }
            ],
        },
    )
    assert order_res.status_code == 201
    created = order_res.json()
    assert created["payment_status"] == "unpaid"
    assert created["total_amount"] == 60
    assert round(sum(row["line_total"] for row in created["items"]), 2) == 60


def test_order_number_collision_retries_and_succeeds() -> None:
    from app.services import orders as order_service

    staff_headers = auth_headers("staff1", "staff1234")
    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    milk_tea = find_item(menu_items, "name", "Milk Tea")

    sequence = iter(["ODTESTDUP1", "ODTESTDUP1", "ODTESTOK2"])
    original = order_service.generate_order_number
    order_service.generate_order_number = lambda: next(sequence)
    try:
        first_res = client.post(
            "/api/orders",
            headers=staff_headers,
            json={
                "source": "takeout",
                "auto_pay": False,
                "items": [{"menu_item_id": milk_tea["id"], "quantity": 1}],
            },
        )
        assert first_res.status_code == 201
        assert first_res.json()["order_number"] == "ODTESTDUP1"

        second_res = client.post(
            "/api/orders",
            headers=staff_headers,
            json={
                "source": "takeout",
                "auto_pay": False,
                "items": [{"menu_item_id": milk_tea["id"], "quantity": 1}],
            },
        )
        assert second_res.status_code == 201
        assert second_res.json()["order_number"] == "ODTESTOK2"
    finally:
        order_service.generate_order_number = original


def test_pickup_board_public_endpoint_returns_active_pickup_orders() -> None:
    staff_headers = auth_headers("staff1", "staff1234")
    kitchen_headers = auth_headers("kitchen1", "kitchen1234")

    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    milk_tea = find_item(menu_items, "name", "Milk Tea")

    create_res = client.post(
        "/api/orders",
        headers=staff_headers,
        json={
            "source": "takeout",
            "auto_pay": True,
            "items": [{"menu_item_id": milk_tea["id"], "quantity": 1}],
        },
    )
    assert create_res.status_code == 201
    order_id = create_res.json()["id"]

    preparing_res = client.post(
        f"/api/orders/{order_id}/status",
        headers=kitchen_headers,
        json={"status": "preparing"},
    )
    assert preparing_res.status_code == 200

    board_res = client.get("/api/orders/pickup-board?minutes=180&limit=50")
    assert board_res.status_code == 200
    rows = board_res.json()
    assert any(row["id"] == order_id and row["status"] == "preparing" for row in rows)


def test_shift_open_and_close_summary() -> None:
    manager_headers = auth_headers("manager1", "manager1234")
    staff_headers = auth_headers("staff1", "staff1234")

    open_res = client.post(
        "/api/shift/open",
        headers=manager_headers,
        json={"shift_name": "早班", "opening_cash": 100},
    )
    assert open_res.status_code == 201
    assert open_res.json()["status"] == "open"

    menu_items = client.get("/api/menu/items", headers=staff_headers).json()
    toast = find_item(menu_items, "name", "Ham Egg Toast")
    milk_tea = find_item(menu_items, "name", "Milk Tea")

    cash_order = client.post(
        "/api/orders",
        headers=staff_headers,
        json={
            "source": "takeout",
            "auto_pay": True,
            "payment_method": "cash",
            "items": [{"menu_item_id": toast["id"], "quantity": 1}],
        },
    )
    assert cash_order.status_code == 201

    line_pay_order = client.post(
        "/api/orders",
        headers=staff_headers,
        json={
            "source": "takeout",
            "auto_pay": True,
            "payment_method": "line_pay",
            "items": [{"menu_item_id": milk_tea["id"], "quantity": 1}],
        },
    )
    assert line_pay_order.status_code == 201

    close_res = client.post(
        "/api/shift/close",
        headers=manager_headers,
        json={"actual_cash": 165},
    )
    assert close_res.status_code == 200
    payload = close_res.json()
    assert payload["status"] == "closed"
    assert payload["paid_order_count"] == 2
    assert payload["total_revenue"] == 105
    assert payload["cash_revenue"] == 65
    assert payload["non_cash_revenue"] == 40
    assert payload["expected_cash"] == 165
    assert payload["cash_difference"] == 0
