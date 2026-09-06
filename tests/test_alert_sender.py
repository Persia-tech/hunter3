from types import SimpleNamespace

import pytest

from bot import alert_sender


@pytest.mark.asyncio
async def test_sender_marks_notification_only_after_success(monkeypatch):
    sent = []
    class Bot:
        def __init__(self, token): self.token = token
        async def send_message(self, **kwargs): sent.append(kwargs)
    monkeypatch.setattr(alert_sender, "Bot", Bot)
    state = SimpleNamespace(last_notified_at=None, updated_at=None)
    notification = SimpleNamespace(delivery_channel="telegram", telegram_user_id="42", symbol="BTC-USD",
        metric="opportunity_score", operator="above", current_value=70,
        evaluation=SimpleNamespace(entered=True, exited=False))
    await alert_sender.send_alert_notification(notification, state, token="token")
    assert sent and state.last_notified_at is not None


@pytest.mark.asyncio
async def test_sender_does_not_mark_failed_delivery(monkeypatch):
    class Bot:
        def __init__(self, token): pass
        async def send_message(self, **kwargs): raise RuntimeError("network")
    monkeypatch.setattr(alert_sender, "Bot", Bot)
    state = SimpleNamespace(last_notified_at=None, updated_at=None)
    notification = SimpleNamespace(delivery_channel="telegram", telegram_user_id="42", symbol="BTC-USD",
        metric="score", operator="above", current_value=70,
        evaluation=SimpleNamespace(entered=True, exited=False))
    with pytest.raises(RuntimeError):
        await alert_sender.send_alert_notification(notification, state, token="token")
    assert state.last_notified_at is None
