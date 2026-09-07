# Production deployment checklist

## Required configuration

- Set `ENVIRONMENT=production` so startup validates production guardrails.
- Set `DATABASE_URL` to the migrated production PostgreSQL database; do not reuse a development database.
- Set `TELEGRAM_BOT_TOKEN` from BotFather in the backend, worker, and bot services. Never expose it through `VITE_*` variables.
- Set `MINI_APP_URL` to the deployed HTTPS frontend URL used by the Telegram bot.
- Set `MINI_APP_ORIGINS` to the exact comma-separated HTTPS frontend origins allowed by the API (origins only, with no path).
- Set frontend build variable `VITE_API_BASE_URL` to the deployed HTTPS API origin. Leave it empty only for a same-origin deployment.
- Keep `LOCAL_DEV_AUTH_BYPASS=0` (or unset) and do not set `LOCAL_DEV_USER_ID` in production. Startup rejects an enabled bypass in production.

## Deploy and verify

1. Run `python -m alembic upgrade head` against the production database.
2. Deploy the backend, alert refresh worker, Telegram bot, and frontend from the same revision.
3. Confirm `/health` is public and authenticated API calls reject missing or invalid Telegram init data.
4. Open the Mini App from Telegram and confirm assets, prices, Market Temperature, Bitcoin Overview, and alert CRUD load.
5. Run `python scripts/smoke_test.py --base-url https://YOUR-API --init-data 'VALID_TELEGRAM_INIT_DATA'` from a secure shell. Init data is short-lived; do not save it in source control or logs.
6. Confirm the scheduled market refresh runs and a test user's alert is delivered once on entry, then can be paused and deleted.
