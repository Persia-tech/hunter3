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

## Multi-user Mini App access

There is no owner allowlist: every user is authenticated from the `user.id` in
Telegram's signed Web App `initData`. If one account works and another does not,
check the launch/configuration path rather than weakening authentication:

1. Set the **same** `TELEGRAM_BOT_TOKEN` on the bot and backend Railway services.
   Init data signed for a different bot token cannot validate.
2. Set the bot service's `MINI_APP_URL` to the current frontend HTTPS URL, and
   set the frontend's `VITE_API_BASE_URL` to the current backend HTTPS origin.
3. Set backend `MINI_APP_ORIGINS` to the exact frontend origin (scheme and host,
   no trailing path). Include every real preview/production frontend origin that
   should call the API.
4. In BotFather, use `/setmenubutton` for this bot (or restart the bot so its
   global menu-button setup runs) and select the same `MINI_APP_URL`. Do not share
   the raw Railway URL as the primary opening flow: an ordinary browser tab has
   no Telegram `initData`.
5. Have each user open the bot chat and press **Start** once, then launch
   **Open Hunter3** from the reply keyboard or persistent menu. Telegram bots
   cannot initiate a conversation with a user, while either Web App button
   supplies that user's independently signed `initData`.
6. Close and reopen the Mini App when a session is more than one hour old. Stale
   init data is deliberately rejected; it must not be cached or copied between
   users.

Never enable `LOCAL_DEV_AUTH_BYPASS` to solve a Telegram launch problem. For a
browser-only visual preview, enable it only on an explicitly non-production
backend deployment; production startup rejects it.
