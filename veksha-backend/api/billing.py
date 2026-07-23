"""
api/billing.py — subscriptions and the Telegram Stars billing bridge.

Client endpoints (Bearer):
  GET    /api/billing/status        → active feature selection and expiry
  GET    /api/billing/features      → per-feature monthly Stars prices
  POST   /api/billing/telegram/link → lock selection + amount; deep link to bot
  DELETE /api/billing/subscription  → end paid access
  POST   /api/billing/promo/redeem  → grant all or selected promo features

Companion-bot endpoints (X-Veksha-Bot-Secret header, no user token):
  GET  /api/billing/plans             → purchasable plans (entitlements.PLANS)
  POST /api/billing/telegram/webhook  → events from the bot:
        {"event": "link",    "code", "telegram_user_id"}
        {"event": "payment", "telegram_user_id", "telegram_payment_charge_id",
                             "plan_id", "stars_amount"}
        {"event": "status",  "telegram_user_id"}

Admin endpoints (X-Veksha-Admin-Secret header, see config.ADMIN_API_SECRET):
  GET  /api/billing/admin/overview               → prices and recent promos
  POST /api/billing/promo/create                 → scoped promo code
  PUT  /api/billing/features/{feature}/price     → change future checkout price

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


def _priced_plan(plan_id: str) -> Optional[dict]:
    """Legacy full-bundle plans, repriced from the per-feature DB catalog."""
    base = entitlements.plan_by_id(plan_id)
    if base is None:
        return None
    monthly_total = sum(row["stars_monthly"] for row in db.feature_prices_get())
    default_monthly = entitlements.PLANS[0]["stars"]
    plan = dict(base)
    plan["stars"] = max(1, round(monthly_total * base["stars"] / default_monthly))
    plan["features"] = sorted(entitlements.PREMIUM_FEATURES)
    return plan


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
            else entitlements.features_of_user(username)
        ),
        telegram_linked=bool(db.telegram_linked_user_ids(username)),
    )


class TelegramLinkResponse(BaseModel):
    code: str
    url: str  # t.me deep link that opens the companion bot


class TelegramLinkRequest(BaseModel):
    features: list[str] = Field(default_factory=list)


@router.post("/api/billing/telegram/link", response_model=TelegramLinkResponse)
async def api_billing_telegram_link(
    username: CurrentUser,
    req: Optional[TelegramLinkRequest] = None,
) -> TelegramLinkResponse:
    if not (config.TELEGRAM_BOT_USERNAME and config.TELEGRAM_BOT_WEBHOOK_SECRET):
        raise HTTPException(
            status_code=503,
            detail="Telegram billing is not configured on this server.",
        )
    requested = set(req.features if req else entitlements.PREMIUM_FEATURES)
    if not requested:
        raise HTTPException(status_code=400, detail="Select at least one feature.")
    if not requested <= entitlements.PREMIUM_FEATURES:
        raise HTTPException(status_code=400, detail="Unknown paid feature.")
    prices = {row["feature"]: row["stars_monthly"] for row in db.feature_prices_get()}
    if not requested <= prices.keys():
        raise HTTPException(status_code=503, detail="Feature pricing is incomplete.")
    amount = sum(prices[feature] for feature in requested)
    code = secrets.token_urlsafe(18)
    db.telegram_link_code_create(username, code)
    db.billing_checkout_create(username, code, sorted(requested), amount)
    return TelegramLinkResponse(
        code=code,
        url=f"https://t.me/{config.TELEGRAM_BOT_USERNAME}?start={code}",
    )


class BillingFeatureResponse(BaseModel):
    id: str
    stars_monthly: int


@router.get("/api/billing/features", response_model=list[BillingFeatureResponse])
async def api_billing_features(username: CurrentUser) -> list[BillingFeatureResponse]:
    del username
    prices = {row["feature"]: row["stars_monthly"] for row in db.feature_prices_get()}
    return [
        BillingFeatureResponse(id=feature, stars_monthly=prices[feature])
        for feature in sorted(entitlements.PREMIUM_FEATURES)
        if feature in prices
    ]


@router.delete("/api/billing/subscription", response_model=BillingStatusResponse)
async def api_billing_cancel(username: CurrentUser) -> BillingStatusResponse:
    db.subscription_cancel(username)
    return await api_billing_status(username)


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

    promo_features = db.promo_code_features(code)
    selected = promo_features or sorted(entitlements.PREMIUM_FEATURES)
    expires_at = db.subscription_extend(
        username, entitlements.TIER_PREMIUM, days, selected,
    )
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
    return {"plans": [_priced_plan(plan["id"]) for plan in entitlements.PLANS]}


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
        "features": entitlements.features_of_user(username),
    }


@router.post("/api/billing/telegram/webhook")
async def api_billing_telegram_webhook(
    req: BotWebhookRequest,
    x_veksha_bot_secret: Optional[str] = Header(None),
) -> dict:
    await bot_auth(x_veksha_bot_secret)

    if req.event == "link":
        checkout = db.billing_checkout_get(req.code)
        username = db.telegram_link_code_consume(
            req.code, config.TELEGRAM_LINK_CODE_TTL_SECONDS
        )
        if username is None:
            raise HTTPException(status_code=404, detail="Unknown or expired link code.")
        db.telegram_link_set(req.telegram_user_id, username)
        linked_checkout = db.billing_checkout_link(req.code, req.telegram_user_id)
        log.info("[billing] linked telegram %s to user %r", req.telegram_user_id, username)
        result = _bot_status(username)
        if checkout and linked_checkout:
            result["checkout"] = {
                "code": req.code,
                "features": linked_checkout["features"],
                "stars_amount": linked_checkout["stars_amount"],
                "days": linked_checkout["days"],
            }
        return result

    if req.event == "status":
        return _bot_status(db.telegram_link_owner(req.telegram_user_id))

    if req.event == "precheckout":
        username = db.telegram_link_owner(req.telegram_user_id)
        if username is None:
            raise HTTPException(status_code=409, detail="Telegram account is not linked.")
        if req.plan_id.startswith("checkout:"):
            checkout = db.billing_checkout_get(req.plan_id.removeprefix("checkout:"))
            valid = (
                checkout is not None
                and checkout["username"] == username
                and checkout["telegram_user_id"] == req.telegram_user_id
                and not checkout["paid"]
                and checkout["stars_amount"] == req.stars_amount
            )
        else:
            plan = _priced_plan(req.plan_id)
            valid = plan is not None and plan["stars"] == req.stars_amount
        if not valid:
            raise HTTPException(status_code=400, detail="Checkout is no longer valid.")
        return {"ok": True, "linked": True}

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
        checkout_code = req.plan_id.removeprefix("checkout:") if req.plan_id.startswith("checkout:") else ""
        checkout = db.billing_checkout_get(checkout_code) if checkout_code else None
        plan = _priced_plan(req.plan_id) if not checkout_code else None
        if checkout_code:
            if (
                checkout is None
                or checkout["username"] != username
                or checkout["telegram_user_id"] != req.telegram_user_id
                or (checkout["paid"] and not db.star_payment_exists(req.telegram_payment_charge_id))
            ):
                raise HTTPException(status_code=400, detail="Unknown or completed checkout.")
            if req.stars_amount != checkout["stars_amount"]:
                raise HTTPException(status_code=400, detail="Checkout amount mismatch.")
        if plan is None:
            if checkout is not None:
                plan = {
                    "id": f"checkout:{checkout_code}",
                    "tier": entitlements.TIER_PREMIUM,
                    "days": checkout["days"],
                    "stars": checkout["stars_amount"],
                    "features": checkout["features"],
                }
            else:
                log.error("[billing] payment with unknown plan %r (charge %r)",
                          req.plan_id, req.telegram_payment_charge_id)
                raise HTTPException(status_code=400, detail="Unknown plan.")
        if not checkout and req.stars_amount != plan["stars"]:
            raise HTTPException(status_code=400, detail="Plan amount mismatch.")
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
            selected_features = plan.get("features")
            db.subscription_extend(
                username, plan["tier"], plan["days"], selected_features,
            )
            if checkout_code:
                db.billing_checkout_mark_paid(checkout_code, req.telegram_user_id)
            log.info(
                "[billing] payment %r applied to tier %s",
                req.telegram_payment_charge_id,
                plan["tier"],
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
    features: list[str] = Field(default_factory=list)


@router.get("/api/billing/admin/overview")
async def api_billing_admin_overview(
    x_veksha_admin_secret: Optional[str] = Header(None),
) -> dict:
    await admin_auth(x_veksha_admin_secret)
    return {
        "features": db.feature_prices_get(),
        "promos": db.promo_codes_get(),
        "ai_usage": db.ai_usage_stats(),
    }


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

    selected = set(req.features)
    if not selected <= entitlements.PREMIUM_FEATURES:
        raise HTTPException(status_code=400, detail="Unknown paid feature.")
    created = db.promo_code_create(
        code, req.days, req.max_redemptions, req.note, sorted(selected),
    )
    if not created:
        raise HTTPException(status_code=409, detail="Code already exists.")
    log.info("[billing] promo code %r created: %s days, max %d redemptions",
              code, req.days, req.max_redemptions)
    return {
        "ok": True,
        "code": code,
        "days": req.days,
        "max_redemptions": req.max_redemptions,
        "features": sorted(selected),
    }


class FeaturePriceUpdateRequest(BaseModel):
    stars_monthly: int


@router.put("/api/billing/features/{feature}/price")
async def api_billing_feature_price_update(
    feature: str,
    req: FeaturePriceUpdateRequest,
    x_veksha_admin_secret: Optional[str] = Header(None),
) -> dict:
    await admin_auth(x_veksha_admin_secret)
    if feature not in entitlements.PREMIUM_FEATURES:
        raise HTTPException(status_code=404, detail="Unknown paid feature.")
    if req.stars_monthly < 1:
        raise HTTPException(status_code=400, detail="stars_monthly must be positive.")
    return db.feature_price_set(feature, req.stars_monthly)
