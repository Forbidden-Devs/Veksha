"""
entitlements.py — subscription tiers, plans and feature gating.

Single source of truth for what a paid subscription unlocks:

  TIERS            — known tiers; "free" is implicit for everyone.
  PREMIUM_FEATURES — feature flags granted by the premium tier. Features not
                     listed here are available to every user.
  PLANS            — purchasable plans (Telegram Stars); the companion bot
                     fetches these via GET /api/billing/plans so prices live
                     only here.

Gate an endpoint by adding a dependency:

    @router.post("/api/thing", dependencies=[Depends(require_feature("thing"))])

A user without the feature gets HTTP 402 with detail.code
"subscription_required" — clients key their upgrade prompt off that code.
"""
from __future__ import annotations

import time

from fastapi import Depends, HTTPException

import db
import config
from auth import current_user

TIER_FREE = "free"
TIER_PREMIUM = "premium"

# Feature flags gated behind the premium tier. Everything else is free.
PREMIUM_FEATURES: frozenset[str] = frozenset({
    "grammar_lens",     # POST /api/grammar-lens/analyze
    "immersion",        # POST /api/immersion/analyze
    "dual_subtitles",   # POST /api/subtitles/translate
})

# Purchasable plans. `stars` is the Telegram Stars (XTR) price; `days` the
# granted subscription length. Titles/descriptions are what the bot shows in
# the invoice (Telegram invoices are not localized per-user anyway).
PLANS: list[dict] = [
    {
        "id": "premium_1m",
        "tier": TIER_PREMIUM,
        "days": 31,
        "stars": 100,
        "title": "Veksha Premium — 1 month",
        "description": "Grammar Lens, page immersion and dual subtitles for one month.",
    },
    {
        "id": "premium_3m",
        "tier": TIER_PREMIUM,
        "days": 93,
        "stars": 250,
        "title": "Veksha Premium — 3 months",
        "description": "Grammar Lens, page immersion and dual subtitles for three months.",
    },
    {
        "id": "premium_12m",
        "tier": TIER_PREMIUM,
        "days": 366,
        "stars": 800,
        "title": "Veksha Premium — 12 months",
        "description": "Grammar Lens, page immersion and dual subtitles for a full year.",
    },
]


def plan_by_id(plan_id: str) -> dict | None:
    return next((p for p in PLANS if p["id"] == plan_id), None)


def subscription_of(username: str) -> tuple[str, float | None]:
    """Effective (tier, expires_at) — expired subscriptions read as free."""
    sub = db.subscription_get(username)
    if sub and sub["expires_at"] > time.time():
        return sub["tier"], sub["expires_at"]
    return TIER_FREE, None


def features_of(tier: str) -> list[str]:
    return sorted(PREMIUM_FEATURES) if tier == TIER_PREMIUM else []


def has_feature(username: str, feature: str) -> bool:
    if feature not in PREMIUM_FEATURES:
        return True
    if config.DEV_ALL_FEATURES:
        return True
    tier, _ = subscription_of(username)
    return tier == TIER_PREMIUM


def require_feature(feature: str):
    """FastAPI dependency: 402 unless the current user's tier has `feature`."""

    async def _check(username: str = Depends(current_user)) -> str:
        if not has_feature(username, feature):
            raise HTTPException(
                status_code=402,
                detail={"code": "subscription_required", "feature": feature},
            )
        return username

    return _check
