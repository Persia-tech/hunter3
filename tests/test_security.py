import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from backend.app.api.security import get_telegram_user_id, validate_init_data

TOKEN = "123456:test-token-for-local-tests"


def signed_data(*, auth_date=None, user_id=42, extra=None):
    values = {"auth_date": str(auth_date or int(time.time())), "user": json.dumps({"id": user_id})}
    values.update(extra or {})
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_signed_user_is_extracted_only_after_validation():
    data = signed_data()
    assert validate_init_data(data, TOKEN)
    assert get_telegram_user_id(data, TOKEN) == "42"
    assert get_telegram_user_id(data.replace("42", "99"), TOKEN) is None


def test_two_different_signed_users_authenticate_independently():
    user_a = signed_data(user_id=101)
    user_b = signed_data(user_id=202)
    assert get_telegram_user_id(user_a, TOKEN) == "101"
    assert get_telegram_user_id(user_b, TOKEN) == "202"
    assert user_a != user_b


def test_opportunity_catalog_accepts_every_valid_telegram_user(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.api.dca import create_app

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.delenv("LOCAL_DEV_AUTH_BYPASS", raising=False)
    client = TestClient(create_app())
    for user_id in (101, 202):
        response = client.get(
            "/api/opportunity-cost/products",
            headers={"X-Telegram-Init-Data": signed_data(user_id=user_id)},
        )
        assert response.status_code == 200
        assert response.json()["products"]


def test_opportunity_catalog_rejects_invalid_and_stale_sessions(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.api.dca import create_app

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.delenv("LOCAL_DEV_AUTH_BYPASS", raising=False)
    client = TestClient(create_app())
    invalid = signed_data(user_id=101).replace("101", "202")
    stale = signed_data(user_id=101, auth_date=int(time.time()) - 3601)
    assert client.get("/api/opportunity-cost/products", headers={"X-Telegram-Init-Data": invalid}).status_code == 401
    assert client.get("/api/opportunity-cost/products", headers={"X-Telegram-Init-Data": stale}).status_code == 401


def test_stale_future_and_duplicate_payloads_are_rejected():
    assert not validate_init_data(signed_data(auth_date=int(time.time()) - 3601), TOKEN)
    assert not validate_init_data(signed_data(auth_date=int(time.time()) + 31), TOKEN)
    assert not validate_init_data(signed_data() + "&user=%7B%22id%22%3A7%7D", TOKEN)


def test_local_dev_auth_bypass_is_explicit_and_shared_by_assets(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.api.dca import create_app

    monkeypatch.setenv("LOCAL_DEV_AUTH_BYPASS", "1")
    response = TestClient(create_app()).get("/api/assets")
    assert response.status_code == 200
    assert response.json()["assets"]


def test_local_dev_auth_bypass_is_off_by_default(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.api.dca import create_app

    monkeypatch.delenv("LOCAL_DEV_AUTH_BYPASS", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    response = TestClient(create_app()).get("/api/assets")
    assert response.status_code == 503
