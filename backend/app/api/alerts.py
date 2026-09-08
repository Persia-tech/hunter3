"""Authenticated API routes for Hunter2 alert rules."""

from __future__ import annotations

import os
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Response,
    status,
)
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.security import get_telegram_user_id
from backend.app.db.database import SessionLocal
from backend.app.db.models import AlertRule


router = APIRouter(
    prefix="/api/alerts",
    tags=["alerts"],
)


NUMERIC_OPERATORS = {
    "above",
    "above_or_equal",
    "below",
    "below_or_equal",
    "equal",
    "crossed_above",
    "crossed_below",
}

TEXT_OPERATORS = {
    "equal",
    "not_equal",
    "changed_to",
    "changed_from",
}


class AlertRuleCreate(BaseModel):
    scope_type: Literal[
        "symbol",
        "asset_class",
        "all",
    ] = "symbol"

    scope_value: str | None = Field(
        default=None,
        max_length=128,
    )

    metric: str = Field(
        min_length=1,
        max_length=64,
    )

    operator: str = Field(
        min_length=1,
        max_length=32,
    )

    numeric_value: float | None = None

    text_value: str | None = Field(
        default=None,
        max_length=128,
    )

    notify_on_enter: bool = True
    notify_on_exit: bool = False

    cooldown_minutes: int = Field(
        default=0,
        ge=0,
        le=10080,
    )

    delivery_channel: Literal[
        "telegram"
    ] = "telegram"

    @model_validator(mode="after")
    def validate_rule(
        self,
    ) -> "AlertRuleCreate":
        if self.scope_type == "all":
            self.scope_value = None

        elif (
            not self.scope_value
            or not self.scope_value.strip()
        ):
            raise ValueError(
                "scope_value is required "
                "for symbol and asset_class rules"
            )

        has_numeric = (
            self.numeric_value is not None
        )

        has_text = (
            self.text_value is not None
        )

        if has_numeric == has_text:
            raise ValueError(
                "Exactly one of numeric_value "
                "or text_value is required"
            )

        if (
            has_numeric
            and self.operator
            not in NUMERIC_OPERATORS
        ):
            raise ValueError(
                "Unsupported numeric operator: "
                f"{self.operator}"
            )

        if (
            has_text
            and self.operator
            not in TEXT_OPERATORS
        ):
            raise ValueError(
                "Unsupported text operator: "
                f"{self.operator}"
            )

        if self.scope_value is not None:
            self.scope_value = (
                self.scope_value.strip()
            )

        self.metric = self.metric.strip()

        if self.text_value is not None:
            self.text_value = (
                self.text_value.strip()
            )

        return self


class AlertRuleUpdate(BaseModel):
    enabled: bool


class AlertRuleResponse(BaseModel):
    id: int
    scope_type: str
    scope_value: str | None
    metric: str
    operator: str
    numeric_value: float | None
    text_value: str | None
    enabled: bool
    notify_on_enter: bool
    notify_on_exit: bool
    cooldown_minutes: int
    delivery_channel: str


def get_db():
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


def _local_dev_auth_enabled() -> bool:
    return os.getenv("LOCAL_DEV_AUTH_BYPASS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def require_telegram_user(
    init_data: Annotated[
        str | None,
        Header(
            alias="X-Telegram-Init-Data"
        ),
    ] = None,
) -> str:
    """Return authenticated Telegram user id.

    Local browser development can opt in to an explicit bypass with
    LOCAL_DEV_AUTH_BYPASS=1. The bypass is disabled by default and should never
    be enabled in production.
    """
    if _local_dev_auth_enabled():
        return os.getenv("LOCAL_DEV_USER_ID", "local-dev-user").strip() or "local-dev-user"

    token = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "",
    ).strip()

    if not token:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Telegram authentication "
                "is not configured"
            ),
        )

    user_id = get_telegram_user_id(
        init_data or "",
        token,
    )

    if user_id is None:
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Invalid Telegram session",
        )

    return user_id


def serialize_rule(
    rule: AlertRule,
) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=rule.id,
        scope_type=rule.scope_type,
        scope_value=rule.scope_value,
        metric=rule.metric,
        operator=rule.operator,
        numeric_value=rule.numeric_value,
        text_value=rule.text_value,
        enabled=rule.enabled,
        notify_on_enter=(
            rule.notify_on_enter
        ),
        notify_on_exit=(
            rule.notify_on_exit
        ),
        cooldown_minutes=(
            rule.cooldown_minutes
        ),
        delivery_channel=(
            rule.delivery_channel
        ),
    )


@router.get(
    "",
    response_model=list[
        AlertRuleResponse
    ],
)
def list_alert_rules(
    telegram_user_id: str = Depends(
        require_telegram_user
    ),
    session: Session = Depends(
        get_db
    ),
) -> list[AlertRuleResponse]:
    statement = (
        select(AlertRule)
        .where(
            AlertRule.telegram_user_id
            == telegram_user_id
        )
        .order_by(
            AlertRule.id
        )
    )

    rules = session.scalars(
        statement
    ).all()

    return [
        serialize_rule(rule)
        for rule in rules
    ]


@router.post(
    "",
    response_model=AlertRuleResponse,
    status_code=(
        status.HTTP_201_CREATED
    ),
)
def create_alert_rule(
    request: AlertRuleCreate,
    telegram_user_id: str = Depends(
        require_telegram_user
    ),
    session: Session = Depends(
        get_db
    ),
) -> AlertRuleResponse:
    rule = AlertRule(
        telegram_user_id=(
            telegram_user_id
        ),
        scope_type=(
            request.scope_type
        ),
        scope_value=(
            request.scope_value
        ),
        metric=request.metric,
        operator=request.operator,
        numeric_value=(
            request.numeric_value
        ),
        text_value=(
            request.text_value
        ),
        enabled=True,
        notify_on_enter=(
            request.notify_on_enter
        ),
        notify_on_exit=(
            request.notify_on_exit
        ),
        cooldown_minutes=(
            request.cooldown_minutes
        ),
        delivery_channel=(
            request.delivery_channel
        ),
    )

    try:
        session.add(rule)
        session.commit()
        session.refresh(rule)
    except Exception:
        session.rollback()
        raise

    return serialize_rule(rule)


@router.patch(
    "/{rule_id}",
    response_model=AlertRuleResponse,
)
def update_alert_rule(
    rule_id: int,
    request: AlertRuleUpdate,
    telegram_user_id: str = Depends(
        require_telegram_user
    ),
    session: Session = Depends(
        get_db
    ),
) -> AlertRuleResponse:
    statement = select(
        AlertRule
    ).where(
        AlertRule.id == rule_id,
        AlertRule.telegram_user_id
        == telegram_user_id,
    )

    rule = session.scalar(
        statement
    )

    if rule is None:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Alert rule not found",
        )

    rule.enabled = request.enabled

    try:
        session.commit()
        session.refresh(rule)
    except Exception:
        session.rollback()
        raise

    return serialize_rule(rule)


@router.delete(
    "/{rule_id}",
    status_code=(
        status.HTTP_204_NO_CONTENT
    ),
    response_class=Response,
)
def delete_alert_rule(
    rule_id: int,
    telegram_user_id: str = Depends(
        require_telegram_user
    ),
    session: Session = Depends(
        get_db
    ),
) -> Response:
    statement = select(
        AlertRule
    ).where(
        AlertRule.id == rule_id,
        AlertRule.telegram_user_id
        == telegram_user_id,
    )

    rule = session.scalar(
        statement
    )

    if rule is None:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Alert rule not found",
        )

    try:
        session.delete(rule)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return Response(
        status_code=(
            status.HTTP_204_NO_CONTENT
        )
    )
