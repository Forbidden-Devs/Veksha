# veksha-tgbot

Billing companion bot: sells Veksha subscription plans as **Telegram Stars**
invoices and reports completed payments to the backend over an authenticated
webhook (`POST /api/billing/telegram/webhook`, header `X-Veksha-Bot-Secret`).

All state (account links, subscriptions, payment ledger) lives in the
backend; the bot is stateless and uses long polling — no public URL needed.

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

- `/start <code>` — link a Veksha account (deep link from the app's
  Settings → Subscription)
- `/plans` — plan buttons → Stars invoice (currency `XTR`)
- `/status` — current plan and expiry
- `/paysupport` — refund/support info (required by Telegram for paid bots)

Plans and prices are defined once in `veksha-backend/entitlements.py`
(`PLANS`) and fetched by the bot via `GET /api/billing/plans`.

## Payment flow

1. `pre_checkout_query` — rejected unless the Telegram account is linked.
2. `successful_payment` — webhook `{"event": "payment", ...}` with the
   `telegram_payment_charge_id`; the backend applies it idempotently and
   extends the subscription.
3. If the webhook cannot be delivered after retries, the user gets the charge
   id for `/paysupport` — the payment can be re-applied manually later.
