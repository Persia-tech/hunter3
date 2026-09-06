"""SQLAlchemy models for market snapshots and flexible alert rules."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "as_of",
            name="uq_market_snapshots_symbol_as_of",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    asset_class: Mapped[str] = mapped_column(String(64))

    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    current_price: Mapped[float] = mapped_column(Float)

    opportunity_score: Mapped[int] = mapped_column(Integer)
    overheat_score: Mapped[int] = mapped_column(Integer)

    classification: Mapped[str] = mapped_column(String(64))
    trend: Mapped[str] = mapped_column(String(64))
    divergence: Mapped[str] = mapped_column(String(64))

    weekly_rsi: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_weekly_rsi: Mapped[float | None] = mapped_column(Float, nullable=True)

    stochastic_rsi: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_stochastic_rsi: Mapped[float | None] = mapped_column(Float, nullable=True)

    sma_200w: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_200w_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    ath: Mapped[float] = mapped_column(Float)
    drawdown_percent: Mapped[float] = mapped_column(Float)

    sma_200d: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma_10m: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_12m: Mapped[float | None] = mapped_column(Float, nullable=True)

    recovery_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    history_status: Mapped[str] = mapped_column(String(32), default="Complete")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)

    telegram_user_id: Mapped[str] = mapped_column(String(64), index=True)

    scope_type: Mapped[str] = mapped_column(
        String(32),
        default="symbol",
        index=True,
    )

    scope_value: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    metric: Mapped[str] = mapped_column(String(64))
    operator: Mapped[str] = mapped_column(String(32))

    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_value: Mapped[str | None] = mapped_column(String(128), nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    notify_on_enter: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_exit: Mapped[bool] = mapped_column(Boolean, default=False)

    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=0)

    delivery_channel: Mapped[str] = mapped_column(
        String(32),
        default="telegram",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    state: Mapped["AlertState"] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        uselist=False,
    )


class AlertState(Base):
    __tablename__ = "alert_states"

    id: Mapped[int] = mapped_column(primary_key=True)

    rule_id: Mapped[int] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    previous_numeric_value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    last_numeric_value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    previous_text_value: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    last_text_value: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    trigger_count: Mapped[int] = mapped_column(Integer, default=0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    rule: Mapped[AlertRule] = relationship(back_populates="state")