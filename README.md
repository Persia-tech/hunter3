# Hunter3

Hunter3 is a production-oriented successor to Hunter2. The immutable
`reference/hunter2/` snapshot documents the baseline behavior; runtime code does
not import from it.

## Features and compatibility

- Telegram-authenticated DCA, asset comparison, lump-sum comparison, and current
  prices retain the Hunter2 endpoint and response contracts.
- Market Temperature retains Hunter2's completed-week RSI/Stochastic RSI,
  200-week SMA, 200-day SMA, approximate 10-month SMA, 12-month momentum, ATH
  drawdown, divergence, recovery, trend, scoring weights, and labels.
- The scheduler processes the same 20 assets independently, persists snapshots,
  evaluates transition alerts, delivers Telegram messages, rolls back an asset
  on failure, and continues with later assets.
- The Mini App adds persisted Market Temperature and alert-management views while
  retaining every Hunter2 DCA workflow.

Market Temperature, drawdown, and trend are deliberately distinct concepts.
Neither drawdown nor trend is presented as a substitute for the two temperature
scores.

## Local development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn backend.app.main:app --reload
```

In another shell:

```bash
cd frontend
npm ci
npm test
npm run dev
```

Run the bot with `python -m bot.app`; run one refresh with
`python -m scripts.refresh_market_temperature`.

## Notification delivery semantics

Alert state is marked notified only after Telegram confirms `send_message`. A
send failure rolls back that asset, so a later refresh retries it. Telegram can
succeed immediately before the database commit fails; in that narrow case the
same transition can be sent again. Delivery is therefore **at least once**, and
consumers should tolerate a rare duplicate. Exactly-once delivery would require
a transactional outbox plus idempotency support from the delivery provider.

## Separate Railway staging deployment (do not reuse Hunter1/Hunter2 services)

1. Create a new Railway project and a new PostgreSQL service.
2. Create a backend service from this repository using `Dockerfile.backend`.
   Set `DATABASE_URL`, a new `TELEGRAM_BOT_TOKEN`, and `MINI_APP_ORIGINS`.
3. Run `alembic upgrade head` against only the new Hunter3 database.
4. Create a frontend service using `Dockerfile.frontend`; set
   `VITE_API_BASE_URL` at build time to the new backend URL.
5. Create a bot service using `Dockerfile.worker` with start command
   `python -m bot.app`, the new bot token, and `MINI_APP_URL`.
6. Create a scheduler service using `Dockerfile.worker` with start command
   `python -m scripts.refresh_market_temperature` and an appropriate cron.
7. Verify `/health`, signed Mini App access, DCA workflows, stored snapshots,
   alert ownership, and Telegram delivery in staging before promoting anything.

Never point these services at an existing Hunter1 or Hunter2 database, bot, or
Railway service.
