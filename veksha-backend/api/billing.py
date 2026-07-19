"""
api/billing.py — subscriptions and the Telegram Stars billing bridge.

Client endpoints (Bearer):
  GET  /api/billing/status         → {tier, expires_at, features, telegram_linked}
  POST /api/billing/telegram/link  → {code, url}  (deep link into the bot)
  POST /api/billing/promo/redeem   → {code} → grants Premium if the code is valid

Companion-bot endpoints (X-Veksha-Bot-Secret header, no user token):
  GET  /api/billing/plans             → purchasable plans (entitlements.PLANS)
  POST /api/billing/telegram/webhook  → events from the bot:
        {"event": "link",    "code", "telegram_user_id"}
        {"event": "payment", "telegram_user_id", "telegram_payment_charge_id",
                             "plan_id", "stars_amount"}
        {"event": "status",  "telegram_user_id"}

Admin endpoint (X-Veksha-Admin-Secret header, see config.ADMIN_API_SECRET):
  POST /api/billing/promo/create  → mint a promo code for manual testing grants

Money never touches this backend: the bot collects Telegram Stars and reports
completed payments here. The webhook is idempotent — a payment is applied at
most once per telegram_payment_charge_id (see db.star_payment_record).

Accounts default to the free tier; a promo code is the only way to grant
Premium outside of a real payment.
"""
from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import config
import db
import entitlements
from auth import CurrentUser
from storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Client endpoints
# ---------------------------------------------------------------------------

class BillingStatusResponse(BaseModel):
    tier: str
    expires_at: Optional[float] = None
    features: list[str] = Field(default_factory=list)
    telegram_linked: bool = False


@router.get("/api/billing/status", response_model=BillingStatusResponse)
async def api_billing_status(username: CurrentUser) -> BillingStatusResponse:
    tier, expires_at = entitlements.subscription_of(username)
    return BillingStatusResponse(
        tier=tier,
        expires_at=expires_at,
        features=(
            sorted(entitlements.PREMIUM_FEATURES)
            if config.DEV_ALL_FEATURES
            else entitlements.features_of(tier)
        ),
        telegram_linked=bool(db.telegram_linked_user_ids(username)),
    )


class TelegramLinkResponse(BaseModel):
    code: str
    url: str  # t.me deep link that opens the companion bot


@router.post("/api/billing/telegram/link", response_model=TelegramLinkResponse)
async def api_billing_telegram_link(username: CurrentUser) -> TelegramLinkResponse:
    if not (config.TELEGRAM_BOT_USERNAME and config.TELEGRAM_BOT_WEBHOOK_SECRET):
        raise HTTPException(
            status_code=503,
            detail="Telegram billing is not configured on this server.",
        )
    code = secrets.token_urlsafe(16)
    db.telegram_link_code_create(username, code)
    return TelegramLinkResponse(
        code=code,
        url=f"https://t.me/{config.TELEGRAM_BOT_USERNAME}?start={code}",
    )


class PromoRedeemRequest(BaseModel):
    code: str


class PromoRedeemResponse(BaseModel):
    ok: bool
    tier: str
    expires_at: Optional[float] = None
    error: Optional[str] = None  # "invalid" | "exhausted" | "already_redeemed"


@router.post("/api/billing/promo/redeem", response_model=PromoRedeemResponse)
async def api_billing_promo_redeem(
    req: PromoRedeemRequest, username: CurrentUser,
) -> PromoRedeemResponse:
    code = req.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Missing code.")

    status, days = db.promo_code_redeem(code, username)
    if status != "ok":
        tier, _ = entitlements.subscription_of(username)
        return PromoRedeemResponse(ok=False, tier=tier, error=status)

    expires_at = db.subscription_extend(username, entitlements.TIER_PREMIUM, days)
    log.info("[billing] promo code %r redeemed by %r: premium until %s", code, username, expires_at)
    return PromoRedeemResponse(ok=True, tier=entitlements.TIER_PREMIUM, expires_at=expires_at)


# ---------------------------------------------------------------------------
# Companion-bot endpoints
# ---------------------------------------------------------------------------

async def bot_auth(x_veksha_bot_secret: Optional[str] = Header(None)) -> None:
    if not config.TELEGRAM_BOT_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Telegram billing is not configured.")
    if not secrets.compare_digest(x_veksha_bot_secret or "", config.TELEGRAM_BOT_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid bot secret.")


@router.get("/api/billing/plans")
async def api_billing_plans(
    x_veksha_bot_secret: Optional[str] = Header(None),
) -> dict:
    await bot_auth(x_veksha_bot_secret)
    return {"plans": entitlements.PLANS}


class BotWebhookRequest(BaseModel):
    event: str  # "link" | "payment" | "status"
    telegram_user_id: int
    code: str = ""                          # link
    plan_id: str = ""                       # payment
    telegram_payment_charge_id: str = ""    # payment
    stars_amount: int = 0                   # payment


def _bot_status(username: Optional[str]) -> dict:
    if username is None:
        return {"ok": True, "linked": False, "tier": entitlements.TIER_FREE, "expires_at": None}
    tier, expires_at = entitlements.subscription_of(username)
    display_name = get_storage(username).settings.display_name or username
    return {
        "ok": True,
        "linked": True,
        "tier": tier,
        "expires_at": expires_at,
        "display_name": display_name,
    }


@router.post("/api/billing/telegram/webhook")
async def api_billing_telegram_webhook(
    req: BotWebhookRequest,
    x_veksha_bot_secret: Optional[str] = Header(None),
) -> dict:
    await bot_auth(x_veksha_bot_secret)

    if req.event == "link":
        username = db.telegram_link_code_consume(
            req.code, config.TELEGRAM_LINK_CODE_TTL_SECONDS
        )
        if username is None:
            raise HTTPException(status_code=404, detail="Unknown or expired link code.")
        db.telegram_link_set(req.telegram_user_id, username)
        log.info("[billing] linked telegram %s to user %r", req.telegram_user_id, username)
        return _bot_status(username)

    if req.event == "status":
        return _bot_status(db.telegram_link_owner(req.telegram_user_id))

    if req.event == "payment":
        username = db.telegram_link_owner(req.telegram_user_id)
        if username is None:
            # Should not happen (the bot rejects pre-checkout for unlinked
            # users) — surface loudly so the payment can be resolved manually.
            log.error(
                "[billing] payment from unlinked telegram user %s (charge %r)",
                req.telegram_user_id, req.telegram_payment_charge_id,
            )
            raise HTTPException(status_code=409, detail="Telegram account is not linked.")
        plan = entitlements.plan_by_id(req.plan_id)
        if plan is None:
            log.error("[billing] payment with unknown plan %r (charge %r)",
                      req.plan_id, req.telegram_payment_charge_id)
            raise HTTPException(status_code=400, detail="Unknown plan.")
        if not req.telegram_payment_charge_id:
            raise HTTPException(status_code=400, detail="Missing charge id.")

        applied = db.star_payment_record(
            req.telegram_payment_charge_id,
            req.telegram_user_id,
            username,
            plan["id"],
            req.stars_amount,
        )
        if applied:
            expires_at = db.subscription_extend(username, plan["tier"], plan["days"])
            log.info(
                "[billing] payment %r: user %r → %s until %s (%s stars)",
                req.telegram_payment_charge_id, username, plan["tier"],
                expires_at, req.stars_amount,
            )
        else:
            log.warning("[billing] duplicate payment webhook %r ignored",
                        req.telegram_payment_charge_id)
        return _bot_status(username)

    raise HTTPException(status_code=400, detail=f"Unknown event {req.event!r}.")


# ---------------------------------------------------------------------------
# Admin endpoint (promo code issuance)
# ---------------------------------------------------------------------------

async def admin_auth(x_veksha_admin_secret: Optional[str] = Header(None)) -> None:
    if not config.ADMIN_API_SECRET:
        raise HTTPException(status_code=503, detail="Admin API is not configured.")
    if not secrets.compare_digest(x_veksha_admin_secret or "", config.ADMIN_API_SECRET):
        raise HTTPException(status_code=401, detail="Invalid admin secret.")


class PromoCreateRequest(BaseModel):
    code: str
    days: float
    max_redemptions: int = 1
    note: str = ""


@router.post("/api/billing/promo/create")
async def api_billing_promo_create(
    req: PromoCreateRequest,
    x_veksha_admin_secret: Optional[str] = Header(None),
) -> dict:
    await admin_auth(x_veksha_admin_secret)
    code = req.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Missing code.")
    if req.days <= 0:
        raise HTTPException(status_code=400, detail="days must be positive.")
    if req.max_redemptions < 1:
        raise HTTPException(status_code=400, detail="max_redemptions must be >= 1.")

    created = db.promo_code_create(code, req.days, req.max_redemptions, req.note)
    if not created:
        raise HTTPException(status_code=409, detail="Code already exists.")
    log.info("[billing] promo code %r created: %s days, max %d redemptions",
              code, req.days, req.max_redemptions)
    return {"ok": True, "code": code, "days": req.days, "max_redemptions": req.max_redemptions}
