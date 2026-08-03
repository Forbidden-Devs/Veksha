"""
bot.py — Veksha billing companion bot (Telegram Stars).

The bot is the only place money is handled: it sells subscription plans as
Telegram Stars invoices (currency XTR) and reports completed payments to the
Veksha backend over an authenticated webhook. The backend owns all state
(links, subscriptions, payment ledger); the bot itself is stateless and runs
on long polling — no public URL required.

Flow:
  1. The app requests a deep link (POST /api/billing/telegram/link) and opens
     t.me/<bot>?start=<code>.
  2. /start <code> → webhook {"event": "link"} → the Telegram account is
     bound to the Veksha account.
  3. /plans → invoice buttons → Telegram Stars payment.
  4. successful_payment → webhook {"event": "payment"} (idempotent by
     telegram_payment_charge_id) → the backend extends the subscription.

Environment:
  TELEGRAM_BOT_TOKEN          — from @BotFather
  VEKSHA_BACKEND_URL          — e.g. https://api.veksha.example (no trailing /)
  VEKSHA_BOT_WEBHOOK_SECRET   — must equal the backend's TELEGRAM_BOT_WEBHOOK_SECRET
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("veksha-tgbot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BACKEND_URL = os.getenv("VEKSHA_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
WEBHOOK_SECRET = os.getenv("VEKSHA_BOT_WEBHOOK_SECRET", "")
HEALTH_PORT = int(os.getenv("PORT", "8080"))

# ---------------------------------------------------------------------------
# Strings (EN base + RU), picked by the sender's Telegram language_code.
# ---------------------------------------------------------------------------

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": (
            "👋 This is the Veksha subscription bot.\n\n"
            "Choose paid features in Veksha and continue to payment. "
            "The selected set and exact price will appear here."
        ),
        "linked": "✅ Linked to your Veksha account <b>{name}</b>.",
        "checkout_title": "Veksha — selected features for 1 month",
        "checkout_description": "Selected features: {features}",
        "link_failed": (
            "❌ This link has expired or was already used. "
            "Open Veksha → Settings → Subscription and tap “Connect Telegram” again."
        ),
        "not_linked": (
            "You haven't linked a Veksha account yet. Open Veksha → Settings → "
            "Subscription and tap “Connect Telegram”."
        ),
        "plans_title": "Choose the features you need in Veksha → Settings → Subscription. The bot will show the exact invoice here.",
        "status_free": "Your plan: <b>Free</b>. Use /plans to learn how to upgrade.",
        "status_paid": "Your subscription is active until <b>{until}</b>. Features: {features}.",
        "paid": "🎉 Payment received! Active until <b>{until}</b>. Features: {features}.",
        "paid_error": (
            "⚠️ Your payment went through, but I couldn't activate the subscription. "
            "Don't worry — it will be resolved. Contact support via /paysupport "
            "and mention this code: <code>{charge_id}</code>"
        ),
        "precheckout_not_linked": "Link your Veksha account first: open Veksha → Settings → Subscription.",
        "precheckout_invalid": "This checkout has expired or its price changed. Please reopen it from Veksha.",
        "backend_down": "😔 The Veksha server is unreachable right now. Please try again in a minute.",
        "paysupport": (
            "Payment support: describe your issue and include your payment id. "
            "Refunds for Telegram Stars purchases are handled on request within 30 days."
        ),
    },
    "ru": {
        "welcome": (
            "👋 Это бот подписки Veksha.\n\n"
            "Выберите платные функции в Veksha и перейдите к оплате. "
            "Здесь появятся выбранный набор и точная сумма."
        ),
        "linked": "✅ Привязан аккаунт Veksha <b>{name}</b>.",
        "checkout_title": "Veksha — выбранные функции на 1 месяц",
        "checkout_description": "Выбранные функции: {features}",
        "link_failed": (
            "❌ Ссылка устарела или уже использована. Откройте Veksha → Настройки → "
            "Подписка и нажмите «Привязать Telegram» ещё раз."
        ),
        "not_linked": (
            "Аккаунт Veksha ещё не привязан. Откройте Veksha → Настройки → "
            "Подписка и нажмите «Привязать Telegram»."
        ),
        "plans_title": "Выберите нужные функции в Veksha → Настройки → Подписка. Точная сумма появится здесь.",
        "status_free": "Ваш план: <b>Free</b>. Команда /plans подскажет, как оформить подписку.",
        "status_paid": "Подписка активна до <b>{until}</b>. Функции: {features}.",
        "paid": "🎉 Оплата получена! Доступ до <b>{until}</b>. Функции: {features}.",
        "paid_error": (
            "⚠️ Оплата прошла, но активировать подписку не удалось. Не волнуйтесь — "
            "мы разберёмся. Напишите в /paysupport и укажите код: <code>{charge_id}</code>"
        ),
        "precheckout_not_linked": "Сначала привяжите аккаунт: Veksha → Настройки → Подписка.",
        "precheckout_invalid": "Эта форма оплаты устарела или цена изменилась. Откройте её заново из Veksha.",
        "backend_down": "😔 Сервер Veksha сейчас недоступен. Попробуйте через минуту.",
        "paysupport": (
            "Поддержка по платежам: опишите проблему и приложите id платежа. "
            "Возвраты покупок за Telegram Stars делаются по запросу в течение 30 дней."
        ),
    },
}

FEATURE_NAMES = {
    "en": {
        "grammar_lens": "Grammar Memory",
        "immersion": "Page immersion",
        "dual_subtitles": "Dual subtitles",
    },
    "ru": {
        "grammar_lens": "Grammar Memory",
        "immersion": "Погружение",
        "dual_subtitles": "Двойные субтитры",
    },
}


def t(msg_or_user, key: str, **kwargs: object) -> str:
    lang = (getattr(getattr(msg_or_user, "from_user", msg_or_user), "language_code", "") or "")[:2]
    table = STRINGS.get(lang, STRINGS["en"])
    return table.get(key, STRINGS["en"][key]).format(**kwargs)


def fmt_until(expires_at: float | None) -> str:
    if not expires_at:
        return "—"
    return time.strftime("%Y-%m-%d", time.localtime(expires_at))


def feature_names(msg_or_user, features: list[str]) -> str:
    lang = (getattr(getattr(msg_or_user, "from_user", msg_or_user), "language_code", "") or "")[:2]
    names = FEATURE_NAMES.get(lang, FEATURE_NAMES["en"])
    return ", ".join(names.get(feature, feature) for feature in features)


# ---------------------------------------------------------------------------
# Backend client
# ---------------------------------------------------------------------------

class Backend:
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"X-Veksha-Bot-Secret": WEBHOOK_SECRET},
            )
        return self._session

    async def webhook(self, payload: dict) -> tuple[int, dict]:
        s = await self.session()
        async with s.post(f"{BACKEND_URL}/api/billing/telegram/webhook", json=payload) as resp:
            body = await resp.json(content_type=None)
            return resp.status, body

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


backend = Backend()
dp = Dispatcher()


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@dp.message(CommandStart(deep_link=True))
async def on_start_link(message: Message, command: CommandObject) -> None:
    code = (command.args or "").strip()
    if not code:
        await message.answer(t(message, "welcome"))
        return
    try:
        status, body = await backend.webhook({
            "event": "link",
            "telegram_user_id": message.from_user.id,
            "code": code,
        })
    except Exception as err:
        log.warning("link webhook failed: %s", err)
        await message.answer(t(message, "backend_down"))
        return
    if status == 200 and body.get("linked"):
        await message.answer(t(message, "linked", name=body.get("display_name", "")))
        checkout = body.get("checkout")
        if checkout:
            features = feature_names(message, checkout["features"])
            await message.answer_invoice(
                title=t(message, "checkout_title"),
                description=t(message, "checkout_description", features=features),
                payload=f"checkout:{checkout['code']}",
                currency="XTR",
                prices=[LabeledPrice(
                    label=t(message, "checkout_title"),
                    amount=int(checkout["stars_amount"]),
                )],
            )
    else:
        await message.answer(t(message, "link_failed"))


@dp.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(t(message, "welcome"))


@dp.message(Command("status"))
async def on_status(message: Message) -> None:
    try:
        _, body = await backend.webhook({
            "event": "status",
            "telegram_user_id": message.from_user.id,
        })
    except Exception as err:
        log.warning("status webhook failed: %s", err)
        await message.answer(t(message, "backend_down"))
        return
    if not body.get("linked"):
        await message.answer(t(message, "not_linked"))
    elif body.get("expires_at"):
        await message.answer(t(
            message, "status_paid",
            until=fmt_until(body["expires_at"]),
            features=feature_names(message, body.get("features", [])),
        ))
    else:
        await message.answer(t(message, "status_free"))


@dp.message(Command("plans"))
async def on_plans(message: Message) -> None:
    await message.answer(t(message, "plans_title"))


@dp.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    """Last gate before Telegram charges the Stars: only linked accounts."""
    try:
        status, body = await backend.webhook({
            "event": "precheckout",
            "telegram_user_id": query.from_user.id,
            "plan_id": query.invoice_payload,
            "stars_amount": query.total_amount,
        })
        linked = status == 200 and bool(body.get("linked"))
    except Exception as err:
        log.warning("pre-checkout status failed: %s", err)
        await query.answer(ok=False, error_message=t(query, "backend_down"))
        return
    if not linked:
        await query.answer(ok=False, error_message=t(query, "precheckout_invalid"))
        return
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def on_paid(message: Message) -> None:
    payment = message.successful_payment
    payload = {
        "event": "payment",
        "telegram_user_id": message.from_user.id,
        "telegram_payment_charge_id": payment.telegram_payment_charge_id,
        "plan_id": payment.invoice_payload,
        "stars_amount": payment.total_amount,
    }
    # The Stars are already charged — retry hard before giving up.
    for attempt in range(5):
        try:
            status, body = await backend.webhook(payload)
            if status == 200:
                await message.answer(t(
                    message, "paid",
                    until=fmt_until(body.get("expires_at")),
                    features=feature_names(message, body.get("features", [])),
                ))
                return
            log.error("payment webhook rejected (%s): %s", status, body)
            if status < 500:
                break  # 4xx — retrying won't help
        except Exception as err:
            log.warning("payment webhook attempt %d failed: %s", attempt + 1, err)
            await asyncio.sleep(2 ** attempt)
    await message.answer(t(
        message, "paid_error", charge_id=payment.telegram_payment_charge_id,
    ))


@dp.message(Command("paysupport"))
async def on_paysupport(message: Message) -> None:
    await message.answer(t(message, "paysupport"))


async def main() -> None:
    errors = config_errors()
    if errors:
        log.error("Invalid configuration: %s", "; ".join(errors))
        sys.exit(1)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    runner = await start_health_server()
    try:
        await dp.start_polling(bot)
    finally:
        await backend.close()
        await runner.cleanup()


def config_errors() -> list[str]:
    errors = []
    if not BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN is required")
    if not WEBHOOK_SECRET:
        errors.append("VEKSHA_BOT_WEBHOOK_SECRET is required")
    if not BACKEND_URL.startswith(("http://", "https://")):
        errors.append("VEKSHA_BACKEND_URL must be an http(s) URL")
    return errors


async def start_health_server() -> web.AppRunner:
    app = web.Application()

    async def healthz(_: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "service": "telegram-bot",
            "revision": os.getenv("VEKSHA_REVISION", "local"),
        })

    app.router.add_get("/healthz", healthz)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", HEALTH_PORT).start()
    log.info("Health server listening on port %s", HEALTH_PORT)
    return runner


if __name__ == "__main__":
    asyncio.run(main())
