"""
Auth backend tests: registration with generated account ids, Google
login/signup/link logic with a stubbed token verifier (no network).

Run either way:
    python tests/test_google_auth.py
    pytest tests/
"""
import asyncio
import os
import sys
import tempfile

os.environ["VEKSHA_DATA_DIR"] = tempfile.mkdtemp(prefix="veksha-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import api.auth as auth_api  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from storage import get_storage  # noqa: E402


def _claims(sub: str, email: str = "john.doe@gmail.com", name: str = "") -> dict:
    claims = {"sub": sub, "email": email, "iss": "accounts.google.com", "aud": "test-client"}
    if name:
        claims["name"] = name
    return claims


def _login(claims: dict):
    orig = auth_api._verify_google_id_token

    async def fake_verify(_id_token: str) -> dict:
        return claims

    auth_api._verify_google_id_token = fake_verify
    try:
        return asyncio.run(auth_api.api_auth_google(auth_api.GoogleAuthRequest(id_token="stub")))
    finally:
        auth_api._verify_google_id_token = orig


def test_register_generates_internal_id_and_stores_display_name():
    resp = asyncio.run(auth_api.api_register(auth_api.RegisterRequest(display_name="Юра ")))
    assert resp.username.startswith("u_") and len(resp.username) == 12
    assert resp.display_name == "Юра"
    assert db.token_owner(resp.token) == resp.username
    assert get_storage(resp.username).settings.display_name == "Юра"

    # Same display name again — no collision, different account.
    resp2 = asyncio.run(auth_api.api_register(auth_api.RegisterRequest(display_name="Юра")))
    assert resp2.username != resp.username


def test_first_google_login_creates_account():
    resp = _login(_claims("sub-100", name="John Doe"))
    assert resp.created is True
    assert resp.username.startswith("u_")
    assert resp.display_name == "John Doe"
    assert get_storage(resp.username).settings.display_name == "John Doe"


def test_google_display_name_falls_back_to_email():
    resp = _login(_claims("sub-150", email="mary.sue@x.com"))
    assert resp.display_name == "mary.sue"


def test_second_login_returns_same_account_and_token():
    first = _login(_claims("sub-200", email="a@x.com", name="A"))
    second = _login(_claims("sub-200", email="a@x.com", name="A"))
    assert second.created is False
    assert (second.username, second.token) == (first.username, first.token)
    assert second.display_name == "A"


def test_link_to_existing_account():
    reg = asyncio.run(auth_api.api_register(auth_api.RegisterRequest(display_name="Veteran")))
    orig = auth_api._verify_google_id_token

    async def fake_verify(_):
        return _claims("sub-400", email="vet@x.com")

    auth_api._verify_google_id_token = fake_verify
    try:
        out = asyncio.run(auth_api.api_auth_google_link(
            auth_api.GoogleAuthRequest(id_token="stub"), reg.username))
        assert out == {"ok": True, "email": "vet@x.com"}
        # Linking is idempotent for the same user...
        out2 = asyncio.run(auth_api.api_auth_google_link(
            auth_api.GoogleAuthRequest(id_token="stub"), reg.username))
        assert out2["ok"] is True
        # ...and a Google login now recovers the account, token and name.
        resp = _login(_claims("sub-400", email="vet@x.com"))
        assert (resp.username, resp.token, resp.created) == (reg.username, reg.token, False)
        assert resp.display_name == "Veteran"
        # But another user cannot claim the same identity.
        intruder = asyncio.run(auth_api.api_register(auth_api.RegisterRequest(display_name="Intruder")))
        try:
            asyncio.run(auth_api.api_auth_google_link(
                auth_api.GoogleAuthRequest(id_token="stub"), intruder.username))
            assert False, "expected 409"
        except HTTPException as e:
            assert e.status_code == 409
    finally:
        auth_api._verify_google_id_token = orig


def test_unconfigured_server_returns_503():
    # The real verifier bails out before any network I/O when no client id is set.
    import config
    assert config.GOOGLE_CLIENT_ID == ""
    try:
        asyncio.run(auth_api._verify_google_id_token("whatever"))
        assert False, "expected 503"
    except HTTPException as e:
        assert e.status_code == 503


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
