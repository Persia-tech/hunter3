"""Provider-independent workload validation for historical calculations."""

from datetime import date

from backend.app.config import (
    MAX_COMPARISON_WORK_UNITS,
    MAX_DAILY_YEARS,
    MAX_DCA_PURCHASES,
    MAX_WEEKLY_YEARS,
)
from backend.app.models.dca import DCAFrequency
from backend.app.services.dca_dates import generate_dca_dates


class RequestLimitError(ValueError):
    """Raised when a valid strategy exceeds production workload limits."""


def validate_dca_workload(
    start_date: date, end_date: date, frequency: DCAFrequency
) -> int:
    """Validate period and schedule size before any market-data request."""

    if frequency is DCAFrequency.DAILY and _after_years(start_date, MAX_DAILY_YEARS) < end_date:
        raise RequestLimitError("For Daily DCA, choose a period of 10 years or less.")
    if (
        frequency is DCAFrequency.WEEKLY
        and _after_years(start_date, MAX_WEEKLY_YEARS) < end_date
    ):
        raise RequestLimitError("For Weekly DCA, choose a period of 20 years or less.")
    count = len(generate_dca_dates(start_date, end_date, frequency))
    if count > MAX_DCA_PURCHASES:
        raise RequestLimitError(
            "That strategy creates too many purchase points. "
            "Please choose a shorter period or lower frequency."
        )
    return count


def validate_comparison_workload(asset_count: int, purchase_count: int) -> None:
    if asset_count * purchase_count > MAX_COMPARISON_WORK_UNITS:
        raise RequestLimitError(
            "That comparison is too large. Choose fewer assets, a shorter period, "
            "or a lower frequency."
        )


def _after_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


