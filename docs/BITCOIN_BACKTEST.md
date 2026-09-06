# Bitcoin cycle backtest

The Bitcoin cycle backtest is designed to validate the price-only scoring engine before any decision rules or on-chain metrics are added.

## Rules

- Daily BTC-USD observations are the master timeline.
- Scores are calculated every day.
- Weekly indicators use only completed Sunday-ended weeks.
- A historical score receives only data available through that historical date.
- Future returns and future 365-day extremes are attached after scoring and are validation labels only.
- Full available BTC-USD history is requested from 2014-09-17 onward.

## Run

```powershell
python scripts\backtest_bitcoin_cycle.py
```

The script prints known cycle checkpoints, yearly score extremes, and the latest score. It also writes the complete daily result set to:

`reports/bitcoin_cycle_backtest.csv`

## Validation goal

Use the historical output to determine whether Opportunity scores consistently rise near favorable long-term accumulation periods and whether Overheat scores consistently rise near major cycle tops. Tune thresholds only after reviewing historical performance, and then compare the same test with free on-chain metrics added as a separate layer.
