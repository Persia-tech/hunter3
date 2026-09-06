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


def test_stale_future_and_duplicate_payloads_are_rejected():
    assert not validate_init_data(signed_data(auth_date=int(time.time()) - 3601), TOKEN)
    assert not validate_init_data(signed_data(auth_date=int(time.time()) + 31), TOKEN)
    assert not validate_init_data(signed_data() + "&user=%7B%22id%22%3A7%7D", TOKEN)
