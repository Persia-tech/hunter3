"""Create initial database schema.

Revision ID: d4c67fe97b70
Revises:
Create Date: 2026-09-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4c67fe97b70"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("asset_class", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=False),
        sa.Column("opportunity_score", sa.Integer(), nullable=False),
        sa.Column("overheat_score", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(length=64), nullable=False),
        sa.Column("trend", sa.String(length=64), nullable=False),
        sa.Column("divergence", sa.String(length=64), nullable=False),
        sa.Column("weekly_rsi", sa.Float(), nullable=True),
        sa.Column("previous_weekly_rsi", sa.Float(), nullable=True),
        sa.Column("stochastic_rsi", sa.Float(), nullable=True),
        sa.Column("previous_stochastic_rsi", sa.Float(), nullable=True),
        sa.Column("sma_200w", sa.Float(), nullable=True),
        sa.Column("distance_200w_percent", sa.Float(), nullable=True),
        sa.Column("ath", sa.Float(), nullable=False),
        sa.Column("drawdown_percent", sa.Float(), nullable=False),
        sa.Column("sma_200d", sa.Float(), nullable=True),
        sa.Column("sma_10m", sa.Float(), nullable=True),
        sa.Column("momentum_12m", sa.Float(), nullable=True),
        sa.Column("recovery_signal", sa.Boolean(), nullable=False),
        sa.Column("history_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "symbol",
            "as_of",
            name="uq_market_snapshots_symbol_as_of",
        ),
    )
    op.create_index(
        op.f("ix_market_snapshots_symbol"),
        "market_snapshots",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        op.f("ix_market_snapshots_as_of"),
        "market_snapshots",
        ["as_of"],
        unique=False,
    )

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.String(length=64), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_value", sa.String(length=128), nullable=True),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("operator", sa.String(length=32), nullable=False),
        sa.Column("numeric_value", sa.Float(), nullable=True),
        sa.Column("text_value", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("notify_on_enter", sa.Boolean(), nullable=False),
        sa.Column("notify_on_exit", sa.Boolean(), nullable=False),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False),
        sa.Column("delivery_channel", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_alert_rules_telegram_user_id"),
        "alert_rules",
        ["telegram_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alert_rules_scope_type"),
        "alert_rules",
        ["scope_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alert_rules_scope_value"),
        "alert_rules",
        ["scope_value"],
        unique=False,
    )

    op.create_table(
        "alert_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("previous_numeric_value", sa.Float(), nullable=True),
        sa.Column("last_numeric_value", sa.Float(), nullable=True),
        sa.Column("previous_text_value", sa.String(length=128), nullable=True),
        sa.Column("last_text_value", sa.String(length=128), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["alert_rules.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id"),
    )
    op.create_index(
        op.f("ix_alert_states_rule_id"),
        "alert_states",
        ["rule_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_alert_states_rule_id"),
        table_name="alert_states",
    )
    op.drop_table("alert_states")

    op.drop_index(
        op.f("ix_alert_rules_scope_value"),
        table_name="alert_rules",
    )
    op.drop_index(
        op.f("ix_alert_rules_scope_type"),
        table_name="alert_rules",
    )
    op.drop_index(
        op.f("ix_alert_rules_telegram_user_id"),
        table_name="alert_rules",
    )
    op.drop_table("alert_rules")

    op.drop_index(
        op.f("ix_market_snapshots_as_of"),
        table_name="market_snapshots",
    )
    op.drop_index(
        op.f("ix_market_snapshots_symbol"),
        table_name="market_snapshots",
    )
    op.drop_table("market_snapshots")