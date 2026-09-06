from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.alerts import get_db, require_telegram_user
from backend.app.api.dca import create_app
from backend.app.db.database import Base
from backend.app.db.models import AlertRule, MarketSnapshot
from backend.app.db.repository import MarketRepository


def database():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def snapshot(symbol, as_of, score):
    return MarketSnapshot(symbol=symbol, name=symbol, asset_class="crypto", as_of=as_of,
        current_price=100, opportunity_score=score, overheat_score=10, classification="Neutral",
        trend="Falling", divergence="None", weekly_rsi=None, previous_weekly_rsi=None,
        stochastic_rsi=None, previous_stochastic_rsi=None, sma_200w=None, distance_200w_percent=None,
        ath=100, drawdown_percent=0, sma_200d=None, sma_10m=None, momentum_12m=None,
        recovery_signal=False, history_status="Insufficient History")


def client_for(session, user="1"):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[require_telegram_user] = lambda: user
    return TestClient(app)


def test_repository_and_market_temperature_api_return_latest_only():
    session = database(); now = datetime.now(timezone.utc)
    session.add_all([snapshot("BTC-USD", now - timedelta(hours=1), 1), snapshot("BTC-USD", now, 2)])
    session.commit()
    assert MarketRepository(session).get_latest_market_snapshot("btc-usd").opportunity_score == 2
    response = client_for(session).get("/api/market-temperature")
    assert response.status_code == 200
    assert len(response.json()) == 1 and response.json()[0]["opportunity_score"] == 2
    assert client_for(session).get("/api/market-temperature/MISSING").status_code == 404


def test_alert_crud_is_owner_scoped_and_delete_is_empty_204():
    session = database(); owner = client_for(session, "owner")
    payload = {"scope_type":"symbol", "scope_value":"BTC-USD", "metric":"opportunity_score",
               "operator":"above", "numeric_value":50, "notify_on_enter":True,
               "notify_on_exit":False, "cooldown_minutes":0, "delivery_channel":"telegram"}
    created = owner.post("/api/alerts", json=payload)
    assert created.status_code == 201
    rule_id = created.json()["id"]
    assert client_for(session, "foreign").patch(f"/api/alerts/{rule_id}", json={"enabled":False}).status_code == 404
    assert client_for(session, "foreign").delete(f"/api/alerts/{rule_id}").status_code == 404
    deleted = owner.delete(f"/api/alerts/{rule_id}")
    assert deleted.status_code == 204 and deleted.content == b""
