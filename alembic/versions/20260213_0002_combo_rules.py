"""Add combo rule tables.

Revision ID: 20260213_0002
Revises: 20260213_0001
Create Date: 2026-02-13 23:58:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260213_0002"
down_revision = "20260213_0001"
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

    if "combo_rules" not in existing_tables:
        op.create_table(
            "combo_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=40), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("bundle_price", sa.Float(), nullable=False),
            sa.Column("max_drink_price", sa.Float(), nullable=True),
            sa.Column("drink_choice_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("side_choice_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("raw_rule_text", sa.String(length=300), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("code", name="uq_combo_rules_code"),
        )
        op.create_index("ix_combo_rules_id", "combo_rules", ["id"])
        op.create_index("ix_combo_rules_code", "combo_rules", ["code"])
        op.create_index("ix_combo_rules_name", "combo_rules", ["name"])
    else:
        if not has_index("combo_rules", "ix_combo_rules_id"):
            op.create_index("ix_combo_rules_id", "combo_rules", ["id"])
        if not has_index("combo_rules", "ix_combo_rules_code"):
            op.create_index("ix_combo_rules_code", "combo_rules", ["code"])
        if not has_index("combo_rules", "ix_combo_rules_name"):
            op.create_index("ix_combo_rules_name", "combo_rules", ["name"])

    if "combo_drink_items" not in existing_tables:
        op.create_table(
            "combo_drink_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("combo_rule_id", sa.Integer(), nullable=False),
            sa.Column("menu_item_id", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.ForeignKeyConstraint(["combo_rule_id"], ["combo_rules.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["menu_item_id"], ["menu_items.id"]),
            sa.UniqueConstraint("combo_rule_id", "menu_item_id", name="uq_combo_drink_item"),
        )
        op.create_index("ix_combo_drink_items_combo_rule_id", "combo_drink_items", ["combo_rule_id"])
    else:
        if not has_index("combo_drink_items", "ix_combo_drink_items_combo_rule_id"):
            op.create_index("ix_combo_drink_items_combo_rule_id", "combo_drink_items", ["combo_rule_id"])

    if "combo_side_options" not in existing_tables:
        op.create_table(
            "combo_side_options",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("combo_rule_id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.ForeignKeyConstraint(["combo_rule_id"], ["combo_rules.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("combo_rule_id", "code", name="uq_combo_side_code"),
        )
        op.create_index("ix_combo_side_options_combo_rule_id", "combo_side_options", ["combo_rule_id"])
    else:
        if not has_index("combo_side_options", "ix_combo_side_options_combo_rule_id"):
            op.create_index("ix_combo_side_options_combo_rule_id", "combo_side_options", ["combo_rule_id"])


def downgrade() -> None:
    op.drop_index("ix_combo_side_options_combo_rule_id", table_name="combo_side_options")
    op.drop_table("combo_side_options")

    op.drop_index("ix_combo_drink_items_combo_rule_id", table_name="combo_drink_items")
    op.drop_table("combo_drink_items")

    op.drop_index("ix_combo_rules_name", table_name="combo_rules")
    op.drop_index("ix_combo_rules_code", table_name="combo_rules")
    op.drop_index("ix_combo_rules_id", table_name="combo_rules")
    op.drop_table("combo_rules")
