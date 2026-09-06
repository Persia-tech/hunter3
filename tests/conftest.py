import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-token-for-local-tests")
