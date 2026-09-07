import pytest

from backend.app.config import ConfigurationError, validate_production_environment


def test_production_requires_explicit_configuration(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    for name in ("DATABASE_URL", "TELEGRAM_BOT_TOKEN", "MINI_APP_URL", "MINI_APP_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigurationError, match="DATABASE_URL.*TELEGRAM_BOT_TOKEN.*MINI_APP_URL"):
        validate_production_environment()


def test_production_rejects_local_auth_bypass(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    for name in ("DATABASE_URL", "TELEGRAM_BOT_TOKEN", "MINI_APP_URL", "MINI_APP_ORIGINS"):
        monkeypatch.setenv(name, "configured")
    monkeypatch.setenv("LOCAL_DEV_AUTH_BYPASS", "1")
    with pytest.raises(ConfigurationError, match="must be disabled"):
        validate_production_environment()
