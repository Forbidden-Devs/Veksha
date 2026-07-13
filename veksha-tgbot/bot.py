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
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("veksha-tgbot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BACKEND_URL = os.getenv("VEKSHA_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
WEBHOOK_SECRET = os.getenv("VEKSHA_BOT_WEBHOOK_SECRET", "")

# ---------------------------------------------------------------------------
# Strings (EN base + RU), picked by the sender's Telegram language_code.
# ---------------------------------------------------------------------------

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": (
            "👋 This is the Veksha subscription bot.\n\n"
            "Open Veksha → Settings → Subscription and tap "
            "“Connect Telegram” to link your account, then use /plans to subscribe."
        ),
        "linked": "✅ Linked to your Veksha account <b>{name}</b>. Use /plans to subscribe.",
        "link_failed": (
            "❌ This link has expired or was already used. "
            "Open Veksha → Settings → Subscription and tap “Connect Telegram” again."
        ),
        "not_linked": (
            "You haven't linked a Veksha account yet. Open Veksha → Settings → "
            "Subscription and tap “Connect Telegram”."
        ),
        "plans_title": "Choose a plan (paid with Telegram Stars):",
        "plan_button": "{title} — {stars} ⭐",
        "status_free": "Your plan: <b>Free</b>. Use /plans to upgrade.",
        "status_paid": "Your plan: <b>{tier}</b>, active until <b>{until}</b>.",
        "paid": "🎉 Payment received! <b>{tier}</b> is active until <b>{until}</b>. Enjoy!",
        "paid_error": (
            "⚠️ Your payment went through, but I couldn't activate the subscription. "
            "Don't worry — it will be resolved. Contact support via /paysupport "
            "and mention this code: <code>{charge_id}</code>"
        ),
        "precheckout_not_linked": "Link your Veksha account first: open Veksha → Settings → Subscription.",
        "backend_down": "😔 The Veksha server is unreachable right now. Please try again in a minute.",
        "paysupport": (
            "Payment support: describe your issue and include your payment id. "
            "Refunds for Telegram Stars purchases are handled on request within 30 days."
        ),
    },
    "ru": {
        "welcome": (
            "👋 Это бот подписки Veksha.\n\n"
            "Откройте Veksha → Настройки → Подписка и нажмите "
            "«Привязать Telegram», затем используйте /plans для оформления."
        ),
        "linked": "✅ Привязан аккаунт Veksha <b>{name}</b>. Оформить подписку: /plans.",
        "link_failed": (
            "❌ Ссылка устарела или уже использована. Откройте Veksha → Настройки → "
            "Подписка и нажмите «Привязать Telegram» ещё раз."
        ),
        "not_linked": (
            "Аккаунт Veksha ещё не привязан. Откройте Veksha → Настройки → "
            "Подписка и нажмите «Привязать Telegram»."
        ),
        "plans_title": "Выберите план (оплата в Telegram Stars):",
        "plan_button": "{title} — {stars} ⭐",
        "status_free": "Ваш план: <b>Free</b>. Оформить подписку: /plans.",
        "status_paid": "Ваш план: <b>{tier}</b>, активен до <b>{until}</b>.",
        "paid": "🎉 Оплата получена! <b>{tier}</b> активен до <b>{until}</b>. Приятной учёбы!",
        "paid_error": (
            "⚠️ Оплата прошла, но активировать подписку не удалось. Не волнуйтесь — "
            "мы разберёмся. Напишите в /paysupport и укажите код: <code>{charge_id}</code>"
        ),
        "precheckout_not_linked": "Сначала привяжите аккаунт: Veksha → Настройки → Подписка.",
        "backend_down": "😔 Сервер Veksha сейчас недоступен. Попробуйте через минуту.",
        "paysupport": (
            "Поддержка по платежам: опишите проблему и приложите id платежа. "
            "Возвраты покупок за Telegram Stars делаются по запросу в течение 30 дней."
        ),
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

    async def plans(self) -> list[dict]:
        s = await self.session()
        async with s.get(f"{BACKEND_URL}/api/billing/plans") as resp:
            resp.raise_for_status()
            return (await resp.json())["plans"]

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
            tier=body["tier"].capitalize(), until=fmt_until(body["expires_at"]),
        ))
    else:
        await message.answer(t(message, "status_free"))


@dp.message(Command("plans"))
async def on_plans(message: Message) -> None:
    try:
        plans = await backend.plans()
    except Exception as err:
        log.warning("plans fetch failed: %s", err)
        await message.answer(t(message, "backend_down"))
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=t(message, "plan_button", title=p["title"], stars=p["stars"]),
            callback_data=f"buy:{p['id']}",
        )]
        for p in plans
    ])
    await message.answer(t(message, "plans_title"), reply_markup=keyboard)


@dp.callback_query(F.data.startswith("buy:"))
async def on_buy(query: CallbackQuery) -> None:
    plan_id = query.data.split(":", 1)[1]
    try:
        plans = await backend.plans()
    except Exception:
        await query.answer(t(query, "backend_down"), show_alert=True)
        return
    plan = next((p for p in plans if p["id"] == plan_id), None)
    if plan is None:
        await query.answer("Unknown plan.", show_alert=True)
        return
    await query.answer()
    # Telegram Stars invoice: currency XTR, empty provider token.
    await query.message.answer_invoice(
        title=plan["title"],
        description=plan["description"],
        payload=plan["id"],
        currency="XTR",
        prices=[LabeledPrice(label=plan["title"], amount=int(plan["stars"]))],
    )


@dp.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    """Last gate before Telegram charges the Stars: only linked accounts."""
    try:
        _, body = await backend.webhook({
            "event": "status",
            "telegram_user_id": query.from_user.id,
        })
        linked = bool(body.get("linked"))
    except Exception as err:
        log.warning("pre-checkout status failed: %s", err)
        await query.answer(ok=False, error_message=t(query, "backend_down"))
        return
    if not linked:
        await query.answer(ok=False, error_message=t(query, "precheckout_not_linked"))
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
                    tier=body["tier"].capitalize(), until=fmt_until(body.get("expires_at")),
                ))
                return
            log.error("payment webhook rejected (%s): %s", status, body)
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
    if not BOT_TOKEN or not WEBHOOK_SECRET:
        log.error("TELEGRAM_BOT_TOKEN and VEKSHA_BOT_WEBHOOK_SECRET are required.")
        sys.exit(1)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    try:
        await dp.start_polling(bot)
    finally:
        await backend.close()


if __name__ == "__main__":
    asyncio.run(main())
