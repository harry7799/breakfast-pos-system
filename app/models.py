from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_username: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    recipe_lines: Mapped[list["RecipeLine"]] = relationship(
        "RecipeLine",
        back_populates="menu_item",
        cascade="all, delete-orphan",
    )
    combo_drink_links: Mapped[list["ComboDrinkItem"]] = relationship(
        "ComboDrinkItem",
        back_populates="menu_item",
        cascade="all, delete-orphan",
    )


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    current_stock: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reorder_level: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_per_unit: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    recipe_lines: Mapped[list["RecipeLine"]] = relationship("RecipeLine", back_populates="ingredient")
    stock_movements: Mapped[list["StockMovement"]] = relationship(
        "StockMovement",
        back_populates="ingredient",
        cascade="all, delete-orphan",
    )


class RecipeLine(Base):
    __tablename__ = "recipe_lines"
    __table_args__ = (UniqueConstraint("menu_item_id", "ingredient_id", name="uq_recipe_item_ingredient"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)

    menu_item: Mapped[MenuItem] = relationship("MenuItem", back_populates="recipe_lines")
    ingredient: Mapped[Ingredient] = relationship("Ingredient", back_populates="recipe_lines")


class ComboRule(Base):
    __tablename__ = "combo_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    bundle_price: Mapped[float] = mapped_column(Float, nullable=False)
    max_drink_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    drink_choice_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    side_choice_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    raw_rule_text: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    eligible_drinks: Mapped[list["ComboDrinkItem"]] = relationship(
        "ComboDrinkItem",
        back_populates="combo_rule",
        cascade="all, delete-orphan",
    )
    side_options: Mapped[list["ComboSideOption"]] = relationship(
        "ComboSideOption",
        back_populates="combo_rule",
        cascade="all, delete-orphan",
    )


class ComboDrinkItem(Base):
    __tablename__ = "combo_drink_items"
    __table_args__ = (
        UniqueConstraint("combo_rule_id", "menu_item_id", name="uq_combo_drink_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    combo_rule_id: Mapped[int] = mapped_column(ForeignKey("combo_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    combo_rule: Mapped[ComboRule] = relationship("ComboRule", back_populates="eligible_drinks")
    menu_item: Mapped[MenuItem] = relationship("MenuItem", back_populates="combo_drink_links")


class ComboSideOption(Base):
    __tablename__ = "combo_side_options"
    __table_args__ = (
        UniqueConstraint("combo_rule_id", "code", name="uq_combo_side_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    combo_rule_id: Mapped[int] = mapped_column(ForeignKey("combo_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    combo_rule: Mapped[ComboRule] = relationship("ComboRule", back_populates="side_options")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(20), default="takeout")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid")
    payment_method: Mapped[str] = mapped_column(String(20), default="cash", nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    inventory_deducted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), nullable=False)
    menu_item_name: Mapped[str] = mapped_column(String(120), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    line_total: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    order: Mapped[Order] = relationship("Order", back_populates="items")
    menu_item: Mapped[MenuItem] = relationship("MenuItem")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"), nullable=False, index=True)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ingredient: Mapped[Ingredient] = relationship("Ingredient", back_populates="stock_movements")


class ShiftSession(Base):
    __tablename__ = "shift_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shift_name: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    opening_cash: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    expected_cash: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_cash: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_difference: Mapped[float | None] = mapped_column(Float, nullable=True)
    paid_order_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cash_revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    non_cash_revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    refund_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    opened_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    opened_by_username: Mapped[str] = mapped_column(String(80), nullable=False)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    closed_by_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
