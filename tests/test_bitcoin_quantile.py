from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from backend.app.models.price import PriceRecord
from backend.app.services.bitcoin_quantile import (
    BitcoinQuantileModel,
    QuantileParameters,
    fit_bitcoin_quantile_model,
    percentile_from_bands,
    predict_quantile_bands,
)


def _manual_model() -> BitcoinQuantileModel:
    return BitcoinQuantileModel(
        anchor=date(2009, 1, 3),
        t_scale=3000.0,
        parameters=(
            QuantileParameters(0.10, 1.0, -2.0, 0.1, 1.0, 0.0),
            QuantileParameters(0.50, 1.1, -2.0, 0.1, 1.0, 0.0),
            QuantileParameters(0.90, 1.2, -2.0, 0.1, 1.0, 0.0),
        ),
    )


def test_predict_quantile_bands_are_monotone() -> None:
    bands = predict_quantile_bands(_manual_model(), date(2025, 1, 1))

    assert [quantile for quantile, _ in bands] == [0.10, 0.50, 0.90]
    prices = [price for _, price in bands]
    assert prices == sorted(prices)
    assert all(price > 0 for price in prices)


def test_percentile_from_bands_interpolates_and_clamps() -> None:
    bands = ((0.10, 100.0), (0.50, 1000.0), (0.90, 10000.0))

    assert percentile_from_bands(50.0, bands) == 0.0
    assert percentile_from_bands(20000.0, bands) == 100.0
    middle = percentile_from_bands(1000.0, bands)
    assert 49.9 <= middle <= 50.1


def test_fit_quantile_model_smoke_on_synthetic_history() -> None:
    start = date(2014, 1, 1)
    records = []
    for index in range(400):
        day = start + timedelta(days=index)
        price = 500.0 * (1.0 + index / 500.0) ** 3
        records.append(PriceRecord(date=day, price=Decimal(str(price))))

    model = fit_bitcoin_quantile_model(
        records,
        quantiles=(0.50,),
        initializations=1,
        maxiter=120,
    )

    assert len(model.parameters) == 1
    assert model.parameters[0].quantile == 0.50
    assert model.parameters[0].check_loss >= 0
