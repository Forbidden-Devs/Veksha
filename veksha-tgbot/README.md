# veksha-tgbot

Billing companion bot: sells Veksha subscription plans as **Telegram Stars**
invoices and reports completed payments to the backend over an authenticated
webhook (`POST /api/billing/telegram/webhook`, header `X-Veksha-Bot-Secret`).

All state (account links, subscriptions, payment ledger) lives in the
backend; the bot is stateless and uses long polling — no public URL needed.
It exposes `GET /healthz` on `PORT` for deployment readiness checks.

## Run

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="123:abc"            # from @BotFather
export VEKSHA_BACKEND_URL="http://127.0.0.1:8000"
export VEKSHA_BOT_WEBHOOK_SECRET="..."         # = backend TELEGRAM_BOT_WEBHOOK_SECRET
python bot.py
```

The backend needs `TELEGRAM_BOT_USERNAME` (bot username without `@`, used to
build the `t.me/<bot>?start=<code>` deep link) and
`TELEGRAM_BOT_WEBHOOK_SECRET` set to the same secret.

## Commands

- `/start <code>` — link a Veksha account and immediately open the invoice
  for the feature selection made in the extension
- `/plans` — объясняет, как выбрать функции в Veksha
- `/status` — current plan and expiry
- `/paysupport` — refund/support info (required by Telegram for paid bots)

Per-feature prices live in the backend database and are frozen in an opaque
checkout before the deep link opens. Bot does not offer a separate bundle
checkout: every new invoice is created only from the selection frozen by the
backend.

## Railway

Create a service from `/veksha-tgbot` and use `veksha-tgbot/railway.toml`.
Set `TELEGRAM_BOT_TOKEN`, `VEKSHA_BACKEND_URL` and
`VEKSHA_BOT_WEBHOOK_SECRET`. Run exactly one replica: Telegram long polling
must not be consumed concurrently by multiple bot instances.

## Payment flow

1. `pre_checkout_query` — rejected unless the account, selected feature set,
   and frozen Stars amount still match the backend checkout.
2. `successful_payment` — webhook `{"event": "payment", ...}` with the
   `telegram_payment_charge_id`; the backend applies it idempotently and
   extends the subscription.
3. If the webhook cannot be delivered after retries, the user gets the charge
   id for `/paysupport` — the payment can be re-applied manually later.
