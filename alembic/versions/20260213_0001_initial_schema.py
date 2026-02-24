"""Initial schema with RBAC and audit logs.

Revision ID: 20260213_0001
Revises:
Create Date: 2026-02-13 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260213_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    def has_index(table_name: str, index_name: str) -> bool:
        if table_name not in inspector.get_table_names():
            return False
        return index_name in {idx["name"] for idx in inspector.get_indexes(table_name)}

    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=80), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("username", name="uq_users_username"),
        )
        op.create_index("ix_users_id", "users", ["id"])
        op.create_index("ix_users_username", "users", ["username"])
    else:
        if not has_index("users", "ix_users_id"):
            op.create_index("ix_users_id", "users", ["id"])
        if not has_index("users", "ix_users_username"):
            op.create_index("ix_users_username", "users", ["username"])

    if "menu_items" not in existing_tables:
        op.create_table(
            "menu_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("price", sa.Float(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("name", name="uq_menu_items_name"),
        )
        op.create_index("ix_menu_items_id", "menu_items", ["id"])
        op.create_index("ix_menu_items_name", "menu_items", ["name"])
    else:
        if not has_index("menu_items", "ix_menu_items_id"):
            op.create_index("ix_menu_items_id", "menu_items", ["id"])
        if not has_index("menu_items", "ix_menu_items_name"):
            op.create_index("ix_menu_items_name", "menu_items", ["name"])

    if "ingredients" not in existing_tables:
        op.create_table(
            "ingredients",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("unit", sa.String(length=20), nullable=False),
            sa.Column("current_stock", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("reorder_level", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("cost_per_unit", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("name", name="uq_ingredients_name"),
        )
        op.create_index("ix_ingredients_id", "ingredients", ["id"])
        op.create_index("ix_ingredients_name", "ingredients", ["name"])
    else:
        if not has_index("ingredients", "ix_ingredients_id"):
            op.create_index("ix_ingredients_id", "ingredients", ["id"])
        if not has_index("ingredients", "ix_ingredients_name"):
            op.create_index("ix_ingredients_name", "ingredients", ["name"])

    if "recipe_lines" not in existing_tables:
        op.create_table(
            "recipe_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("menu_item_id", sa.Integer(), nullable=False),
            sa.Column("ingredient_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.ForeignKeyConstraint(["menu_item_id"], ["menu_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"]),
            sa.UniqueConstraint("menu_item_id", "ingredient_id", name="uq_recipe_item_ingredient"),
        )

    if "orders" not in existing_tables:
        op.create_table(
            "orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_number", sa.String(length=40), nullable=False),
            sa.Column("source", sa.String(length=20), nullable=False, server_default="takeout"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("payment_status", sa.String(length=20), nullable=False, server_default="unpaid"),
            sa.Column("total_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("inventory_deducted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("order_number", name="uq_orders_order_number"),
        )
        op.create_index("ix_orders_id", "orders", ["id"])
        op.create_index("ix_orders_order_number", "orders", ["order_number"])
    else:
        if not has_index("orders", "ix_orders_id"):
            op.create_index("ix_orders_id", "orders", ["id"])
        if not has_index("orders", "ix_orders_order_number"):
            op.create_index("ix_orders_order_number", "orders", ["order_number"])

    if "order_items" not in existing_tables:
        op.create_table(
            "order_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("menu_item_id", sa.Integer(), nullable=False),
            sa.Column("menu_item_name", sa.String(length=120), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_price", sa.Float(), nullable=False),
            sa.Column("line_total", sa.Float(), nullable=False),
            sa.Column("note", sa.String(length=200), nullable=True),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["menu_item_id"], ["menu_items.id"]),
        )
        op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    else:
        if not has_index("order_items", "ix_order_items_order_id"):
            op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    if "stock_movements" not in existing_tables:
        op.create_table(
            "stock_movements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ingredient_id", sa.Integer(), nullable=False),
            sa.Column("movement_type", sa.String(length=20), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("unit_cost", sa.Float(), nullable=True),
            sa.Column("reference", sa.String(length=80), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"]),
        )
        op.create_index("ix_stock_movements_ingredient_id", "stock_movements", ["ingredient_id"])
    else:
        if not has_index("stock_movements", "ix_stock_movements_ingredient_id"):
            op.create_index("ix_stock_movements_ingredient_id", "stock_movements", ["ingredient_id"])

    if "audit_logs" not in existing_tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("actor_user_id", sa.Integer(), nullable=True),
            sa.Column("actor_username", sa.String(length=80), nullable=True),
            sa.Column("actor_role", sa.String(length=20), nullable=True),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("entity_type", sa.String(length=80), nullable=False),
            sa.Column("entity_id", sa.String(length=80), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
        op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
        op.create_index("ix_audit_logs_actor_username", "audit_logs", ["actor_username"])
        op.create_index("ix_audit_logs_actor_role", "audit_logs", ["actor_role"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
        op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
        op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
        op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    else:
        if not has_index("audit_logs", "ix_audit_logs_id"):
            op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
        if not has_index("audit_logs", "ix_audit_logs_actor_user_id"):
            op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
        if not has_index("audit_logs", "ix_audit_logs_actor_username"):
            op.create_index("ix_audit_logs_actor_username", "audit_logs", ["actor_username"])
        if not has_index("audit_logs", "ix_audit_logs_actor_role"):
            op.create_index("ix_audit_logs_actor_role", "audit_logs", ["actor_role"])
        if not has_index("audit_logs", "ix_audit_logs_action"):
            op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
        if not has_index("audit_logs", "ix_audit_logs_entity_type"):
            op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
        if not has_index("audit_logs", "ix_audit_logs_entity_id"):
            op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
        if not has_index("audit_logs", "ix_audit_logs_created_at"):
            op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_role", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_username", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_stock_movements_ingredient_id", table_name="stock_movements")
    op.drop_table("stock_movements")

    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")

    op.drop_index("ix_orders_order_number", table_name="orders")
    op.drop_index("ix_orders_id", table_name="orders")
    op.drop_table("orders")

    op.drop_table("recipe_lines")

    op.drop_index("ix_ingredients_name", table_name="ingredients")
    op.drop_index("ix_ingredients_id", table_name="ingredients")
    op.drop_table("ingredients")

    op.drop_index("ix_menu_items_name", table_name="menu_items")
    op.drop_index("ix_menu_items_id", table_name="menu_items")
    op.drop_table("menu_items")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
