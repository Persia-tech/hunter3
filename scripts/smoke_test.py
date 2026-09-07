#!/usr/bin/env python3
"""Non-destructive post-deployment API smoke checks."""
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_PATHS = (
    "/api/assets",
    "/api/market-temperature",
    "/api/bitcoin-research-state",
)


def get(base_url: str, path: str, init_data: str | None = None):
    headers = {"X-Telegram-Init-Data": init_data} if init_data is not None else {}
    request = Request(base_url.rstrip("/") + path, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else None
    except HTTPError as exc:
        return exc.code, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--init-data", required=True, help="Short-lived Telegram WebApp init data")
    args = parser.parse_args()
    failures: list[str] = []

    try:
        status, body = get(args.base_url, "/health")
        if status != 200 or body != {"status": "ok"}:
            failures.append(f"/health: expected 200 status payload, got {status}")

        unauthenticated, _ = get(args.base_url, "/api/assets")
        if unauthenticated not in (401, 403):
            failures.append(f"authentication: expected 401/403 without init data, got {unauthenticated}")

        responses = {}
        for path in API_PATHS:
            status, body = get(args.base_url, path, args.init_data)
            responses[path] = body
            if status >= 500:
                failures.append(f"{path}: returned {status}")
            elif status != 200:
                failures.append(f"{path}: expected 200, got {status}")

        research = responses.get("/api/bitcoin-research-state")
        if not isinstance(research, dict):
            failures.append("bitcoin state: response is not an object")
        else:
            missing = {"as_of", "quantile", "mvrv", "top_stage2"} - research.keys()
            if missing:
                failures.append("bitcoin state: missing " + ", ".join(sorted(missing)))
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        failures.append(f"request failed: {exc}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("PASS: health, authentication, and read-only API smoke checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
