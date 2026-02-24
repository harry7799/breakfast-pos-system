"""Add shift session table and order payment method.

Revision ID: 20260215_0003
Revises: 20260213_0002
Create Date: 2026-02-15 12:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260215_0003"
down_revision = "20260213_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    order_columns = {col["name"] for col in inspector.get_columns("orders")} if "orders" in existing_tables else set()
    if "payment_method" not in order_columns:
        op.add_column(
            "orders",
            sa.Column("payment_method", sa.String(length=20), nullable=False, server_default="cash"),
        )

    if "shift_sessions" not in existing_tables:
        op.create_table(
            "shift_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("shift_name", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
            sa.Column("opening_cash", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("expected_cash", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("actual_cash", sa.Float(), nullable=True),
            sa.Column("cash_difference", sa.Float(), nullable=True),
            sa.Column("paid_order_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("total_revenue", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("cash_revenue", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("non_cash_revenue", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("refund_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("opened_by_user_id", sa.Integer(), nullable=False),
            sa.Column("opened_by_username", sa.String(length=80), nullable=False),
            sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
            sa.Column("closed_by_username", sa.String(length=80), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["opened_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"]),
        )
        op.create_index("ix_shift_sessions_id", "shift_sessions", ["id"])
        op.create_index("ix_shift_sessions_status", "shift_sessions", ["status"])
        op.create_index("ix_shift_sessions_opened_by_user_id", "shift_sessions", ["opened_by_user_id"])
        op.create_index("ix_shift_sessions_closed_by_user_id", "shift_sessions", ["closed_by_user_id"])
        op.create_index("ix_shift_sessions_opened_at", "shift_sessions", ["opened_at"])
        op.create_index("ix_shift_sessions_closed_at", "shift_sessions", ["closed_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "shift_sessions" in existing_tables:
        op.drop_index("ix_shift_sessions_closed_at", table_name="shift_sessions")
        op.drop_index("ix_shift_sessions_opened_at", table_name="shift_sessions")
        op.drop_index("ix_shift_sessions_closed_by_user_id", table_name="shift_sessions")
        op.drop_index("ix_shift_sessions_opened_by_user_id", table_name="shift_sessions")
        op.drop_index("ix_shift_sessions_status", table_name="shift_sessions")
        op.drop_index("ix_shift_sessions_id", table_name="shift_sessions")
        op.drop_table("shift_sessions")

    if "orders" in existing_tables:
        order_columns = {col["name"] for col in inspector.get_columns("orders")}
        if "payment_method" in order_columns:
            with op.batch_alter_table("orders", recreate="always") as batch_op:
                batch_op.drop_column("payment_method")
