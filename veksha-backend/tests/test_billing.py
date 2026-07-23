"""
Billing tests: Telegram account linking, Stars payment webhook (idempotency),
subscription expiry and feature gating.

Run either way:
    python tests/test_billing.py
    pytest tests/
"""
import asyncio
import os
import sys
import tempfile
import time

os.environ["VEKSHA_DATA_DIR"] = tempfile.mkdtemp(prefix="veksha-test-")
os.environ["TELEGRAM_BOT_USERNAME"] = "veksha_test_bot"
os.environ["TELEGRAM_BOT_WEBHOOK_SECRET"] = "test-secret"
os.environ["ADMIN_API_SECRET"] = "test-admin-secret"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import config  # noqa: E402
import entitlements  # noqa: E402
import api.billing as billing  # noqa: E402
from fastapi import HTTPException  # noqa: E402

SECRET = "test-secret"
ADMIN_SECRET = "test-admin-secret"

# Exercise real free/premium transitions, not the local development bypass.
config.DEV_ALL_FEATURES = False


def _user(name: str) -> str:
    username = f"u_{name}"
    db.create_user(username)
    return username


def _webhook(payload: dict, secret: str = SECRET) -> dict:
    return asyncio.run(billing.api_billing_telegram_webhook(
        billing.BotWebhookRequest(**payload), x_veksha_bot_secret=secret,
    ))


def _link(username: str, telegram_user_id: int) -> dict:
    link = asyncio.run(billing.api_billing_telegram_link(username))
    assert link.url.endswith(link.code)
    return _webhook({"event": "link", "code": link.code,
                     "telegram_user_id": telegram_user_id})


def test_webhook_rejects_bad_secret():
    try:
        _webhook({"event": "status", "telegram_user_id": 1}, secret="wrong")
        assert False, "expected 401"
    except HTTPException as e:
        assert e.status_code == 401


def test_link_flow():
    username = _user("link")
    out = _link(username, 111)
    assert out["linked"] is True and out["tier"] == "free"
    assert db.telegram_link_owner(111) == username

    # A code is single-use.
    link = asyncio.run(billing.api_billing_telegram_link(username))
    _webhook({"event": "link", "code": link.code, "telegram_user_id": 111})
    try:
        _webhook({"event": "link", "code": link.code, "telegram_user_id": 222})
        assert False, "expected 404"
    except HTTPException as e:
        assert e.status_code == 404


def test_expired_code_is_rejected():
    username = _user("expired")
    link = asyncio.run(billing.api_billing_telegram_link(username))
    with db._conn() as c:
        c.execute("UPDATE telegram_link_codes SET created=%s WHERE code=%s",
                  (time.time() - 10_000, link.code))
    try:
        _webhook({"event": "link", "code": link.code, "telegram_user_id": 333})
        assert False, "expected 404"
    except HTTPException as e:
        assert e.status_code == 404


def test_payment_extends_subscription_and_is_idempotent():
    username = _user("pay")
    _link(username, 444)
    plan = entitlements.PLANS[0]
    payload = {
        "event": "payment", "telegram_user_id": 444,
        "telegram_payment_charge_id": "charge-1",
        "plan_id": plan["id"], "stars_amount": plan["stars"],
    }

    out = _webhook(payload)
    assert out["tier"] == plan["tier"]
    first_expiry = out["expires_at"]
    assert first_expiry > time.time() + (plan["days"] - 1) * 86400

    # Duplicate delivery of the same charge id must not extend again.
    out2 = _webhook(payload)
    assert out2["expires_at"] == first_expiry

    # A second (new) payment extends from the current expiry.
    out3 = _webhook({**payload, "telegram_payment_charge_id": "charge-2"})
    assert abs(out3["expires_at"] - (first_expiry + plan["days"] * 86400)) < 5


def test_payment_from_unlinked_user_is_409():
    try:
        _webhook({"event": "payment", "telegram_user_id": 999999,
                  "telegram_payment_charge_id": "charge-x",
                  "plan_id": entitlements.PLANS[0]["id"], "stars_amount": 1})
        assert False, "expected 409"
    except HTTPException as e:
        assert e.status_code == 409


def test_unknown_plan_is_400():
    username = _user("badplan")
    _link(username, 555)
    try:
        _webhook({"event": "payment", "telegram_user_id": 555,
                  "telegram_payment_charge_id": "charge-y",
                  "plan_id": "nope", "stars_amount": 1})
        assert False, "expected 400"
    except HTTPException as e:
        assert e.status_code == 400


def test_feature_gating_and_expiry():
    username = _user("gate")
    assert entitlements.has_feature(username, "grammar_lens") is False
    assert entitlements.has_feature(username, "anything_ungated") is True

    db.subscription_extend(username, entitlements.TIER_PREMIUM, 31)
    assert entitlements.has_feature(username, "grammar_lens") is True
    tier, expires_at = entitlements.subscription_of(username)
    assert tier == "premium" and expires_at is not None

    # Force-expire: back to free.
    with db._conn() as c:
        c.execute("UPDATE subscriptions SET expires_at=%s WHERE username=%s",
                  (time.time() - 1, username))
    assert entitlements.subscription_of(username) == ("free", None)
    assert entitlements.has_feature(username, "grammar_lens") is False

    # The gating dependency raises 402 with a machine-readable code.
    check = entitlements.require_feature("grammar_lens")
    try:
        asyncio.run(check(username))
        assert False, "expected 402"
    except HTTPException as e:
        assert e.status_code == 402
        assert e.detail["code"] == "subscription_required"


def test_local_development_feature_bypass_is_reported_to_client():
    username = _user("dev_features")
    config.DEV_ALL_FEATURES = True
    try:
        assert entitlements.has_feature(username, "dual_subtitles") is True
        out = asyncio.run(billing.api_billing_status(username))
        assert set(out.features) == set(entitlements.PREMIUM_FEATURES)
    finally:
        config.DEV_ALL_FEATURES = False


def test_billing_status_endpoint():
    username = _user("status")
    out = asyncio.run(billing.api_billing_status(username))
    assert (out.tier, out.expires_at, out.telegram_linked) == ("free", None, False)
    assert out.features == []

    _link(username, 666)
    db.subscription_extend(username, entitlements.TIER_PREMIUM, 31)
    out = asyncio.run(billing.api_billing_status(username))
    assert out.tier == "premium" and out.telegram_linked is True
    assert "grammar_lens" in out.features


def test_feature_checkout_grants_only_selected_features():
    username = _user("feature_checkout")
    requested = ["grammar_lens", "dual_subtitles"]
    link = asyncio.run(billing.api_billing_telegram_link(
        username, billing.TelegramLinkRequest(features=requested),
    ))
    linked = _webhook({"event": "link", "code": link.code, "telegram_user_id": 777})
    checkout = linked["checkout"]
    assert set(checkout["features"]) == set(requested)
    assert checkout["stars_amount"] == 65

    precheckout = _webhook({
        "event": "precheckout", "telegram_user_id": 777,
        "plan_id": f"checkout:{link.code}", "stars_amount": 65,
    })
    assert precheckout["ok"] is True

    paid = _webhook({
        "event": "payment", "telegram_user_id": 777,
        "telegram_payment_charge_id": "feature-charge-1",
        "plan_id": f"checkout:{link.code}", "stars_amount": 65,
    })
    assert set(paid["features"]) == set(requested)
    assert entitlements.has_feature(username, "grammar_lens") is True
    assert entitlements.has_feature(username, "dual_subtitles") is True
    assert entitlements.has_feature(username, "immersion") is False

    # The same Telegram charge remains idempotent, while a second charge
    # cannot replay an already completed checkout.
    duplicate = _webhook({
        "event": "payment", "telegram_user_id": 777,
        "telegram_payment_charge_id": "feature-charge-1",
        "plan_id": f"checkout:{link.code}", "stars_amount": 65,
    })
    assert duplicate["expires_at"] == paid["expires_at"]
    try:
        _webhook({
            "event": "payment", "telegram_user_id": 777,
            "telegram_payment_charge_id": "feature-charge-2",
            "plan_id": f"checkout:{link.code}", "stars_amount": 65,
        })
        assert False, "expected completed checkout rejection"
    except HTTPException as e:
        assert e.status_code == 400


def test_feature_prices_are_stored_and_admin_mutable():
    catalog = asyncio.run(billing.api_billing_features(_user("catalog")))
    assert {item.id: item.stars_monthly for item in catalog}["immersion"] == 35

    changed = asyncio.run(billing.api_billing_feature_price_update(
        "immersion", billing.FeaturePriceUpdateRequest(stars_monthly=37),
        x_veksha_admin_secret=ADMIN_SECRET,
    ))
    assert changed["stars_monthly"] == 37
    assert {row["feature"]: row["stars_monthly"] for row in db.feature_prices_get()}["immersion"] == 37
    db.feature_price_set("immersion", 35)


def test_subscription_can_be_cancelled():
    username = _user("cancel")
    db.subscription_extend(username, entitlements.TIER_PREMIUM, 31, ["immersion"])
    assert entitlements.has_feature(username, "immersion") is True
    out = asyncio.run(billing.api_billing_cancel(username))
    assert out.tier == "free" and out.features == [] and out.expires_at is None


# ---------------------------------------------------------------------------
# Promo codes
# ---------------------------------------------------------------------------

def _create_promo(code: str, days: float, max_redemptions: int = 1, secret: str = ADMIN_SECRET) -> dict:
    return asyncio.run(billing.api_billing_promo_create(
        billing.PromoCreateRequest(code=code, days=days, max_redemptions=max_redemptions),
        x_veksha_admin_secret=secret,
    ))


def _redeem_promo(code: str, username: str) -> billing.PromoRedeemResponse:
    return asyncio.run(billing.api_billing_promo_redeem(
        billing.PromoRedeemRequest(code=code), username,
    ))


def test_promo_create_requires_admin_secret():
    try:
        _create_promo("BADAUTH", 30, secret="wrong")
        assert False, "expected 401"
    except HTTPException as e:
        assert e.status_code == 401


def test_admin_overview_returns_prices_and_promos():
    _create_promo("OVERVIEW", 14, max_redemptions=3)
    out = asyncio.run(billing.api_billing_admin_overview(
        x_veksha_admin_secret=ADMIN_SECRET,
    ))
    assert {row["feature"] for row in out["features"]} == entitlements.PREMIUM_FEATURES
    promo = next(row for row in out["promos"] if row["code"] == "OVERVIEW")
    assert promo["days"] == 14 and promo["max_redemptions"] == 3
    assert "all_time" in out["ai_usage"] and "users" in out["ai_usage"]


def test_promo_redeem_grants_premium_without_affecting_others():
    other = _user("promo_control")
    assert entitlements.subscription_of(other) == ("free", None)

    _create_promo("WELCOME30", 30)
    username = _user("promo_redeem")
    assert entitlements.subscription_of(username) == ("free", None)

    out = _redeem_promo("welcome30", username)  # codes are case-insensitive
    assert out.ok is True and out.tier == "premium"
    assert out.expires_at > time.time() + 29 * 86400

    tier, expires_at = entitlements.subscription_of(username)
    assert tier == "premium" and expires_at == out.expires_at
    # Untouched accounts stay on the free tier without a code.
    assert entitlements.subscription_of(other) == ("free", None)


def test_promo_can_grant_selected_features_only():
    username = _user("promo_features")
    asyncio.run(billing.api_billing_promo_create(
        billing.PromoCreateRequest(
            code="GRAMMARONLY", days=10, features=["grammar_lens"],
        ),
        x_veksha_admin_secret=ADMIN_SECRET,
    ))
    out = _redeem_promo("GRAMMARONLY", username)
    assert out.ok is True
    assert entitlements.features_of_user(username) == ["grammar_lens"]

def test_promo_redeem_is_single_use_per_account():
    _create_promo("ONETIME", 7, max_redemptions=5)
    username = _user("promo_repeat")

    first = _redeem_promo("ONETIME", username)
    assert first.ok is True

    second = _redeem_promo("ONETIME", username)
    assert second.ok is False and second.error == "already_redeemed"


def test_promo_redeem_retry_of_own_exhausted_code_reads_already_redeemed():
    # A code fully exhausted by the user themselves reports "already_redeemed",
    # not "exhausted".
    _create_promo("SELFEXHAUST", 7, max_redemptions=1)
    username = _user("promo_self_exhaust")

    assert _redeem_promo("SELFEXHAUST", username).ok is True
    out = _redeem_promo("SELFEXHAUST", username)
    assert out.ok is False and out.error == "already_redeemed"


def test_promo_redeem_respects_max_redemptions():
    _create_promo("LIMITED", 7, max_redemptions=1)
    first_user = _user("promo_limit_1")
    second_user = _user("promo_limit_2")

    assert _redeem_promo("LIMITED", first_user).ok is True

    out = _redeem_promo("LIMITED", second_user)
    assert out.ok is False and out.error == "exhausted"
    assert entitlements.subscription_of(second_user) == ("free", None)


def test_promo_redeem_unknown_code():
    username = _user("promo_unknown")
    out = _redeem_promo("DOES-NOT-EXIST", username)
    assert out.ok is False and out.error == "invalid"
    assert entitlements.subscription_of(username) == ("free", None)


def test_promo_create_duplicate_code_is_409():
    _create_promo("DUPETEST", 10)
    try:
        _create_promo("DUPETEST", 10)
        assert False, "expected 409"
    except HTTPException as e:
        assert e.status_code == 409


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items()):
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError:
            failed += 1
            import traceback
            print(f"FAIL {name}")
            traceback.print_exc()
    sys.exit(1 if failed else 0)
