from types import SimpleNamespace

import pytest

from scripts import refresh_market_temperature as refresh


@pytest.mark.asyncio
async def test_refresh_rolls_back_failed_asset_and_continues(monkeypatch):
    session = SimpleNamespace()
    class SessionContext:
        def __enter__(self): return session
        def __exit__(self, *_args): return None
    class Repository:
        def __init__(self, _session): self.rollbacks = 0; self.commits = 0
        def rollback(self): self.rollbacks += 1
        def commit(self): self.commits += 1
        def get_alert_state(self, _rule_id): return None
    repositories = []
    def repository_factory(value):
        result = Repository(value); repositories.append(result); return result
    class Provider:
        def completed_weekly_history(self, symbol, years):
            if symbol == "FAIL": raise RuntimeError("provider")
            return [object()]
        def daily_history(self, symbol, years): return [object()]
        def full_history(self, symbol): return [object()]
    class Processor:
        def __init__(self, _repository): pass
        def process_temperature(self, _temperature, **_kwargs): return []
    assets = [SimpleNamespace(symbol="FAIL"), SimpleNamespace(symbol="OK")]
    monkeypatch.setattr(refresh, "SessionLocal", lambda: SessionContext())
    monkeypatch.setattr(refresh, "MarketRepository", repository_factory)
    monkeypatch.setattr(refresh, "YFinanceProvider", Provider)
    monkeypatch.setattr(refresh, "AlertProcessor", Processor)
    monkeypatch.setattr(refresh, "MARKET_ASSETS", assets)
    monkeypatch.setattr(refresh, "calculate_temperature", lambda *args, **kwargs: object())
    result = await refresh.refresh_market_temperature()
    assert (result.processed, result.failed) == (1, 1)
    assert repositories[0].rollbacks == 1 and repositories[0].commits == 1
