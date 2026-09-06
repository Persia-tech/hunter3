# Review checklist

Before tuning score weights:

- Run the full test suite.
- Run `python scripts\backtest_bitcoin_cycle.py`.
- Review known historical tops and bottoms.
- Review yearly maximum Opportunity and Overheat scores.
- Check false positives, not only successful signals.
- Compare scores with 180-day, 365-day, and 730-day forward returns.
- Do not tune based only on the current BTC reading.
- Freeze a price-only baseline before adding on-chain metrics.
