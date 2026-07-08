"""
api/auth.py — registration and Google sign-in endpoints.

  POST /api/auth/register    {"display_name"} → {"username", "token", "display_name"}
  POST /api/auth/google      {"id_token"} → {"username", "token", "display_name", "created"}
  POST /api/auth/google/link {"id_token"} (Bearer) → {"ok", "email"}

`username` is the internal account id (generated, immutable — every table is
keyed by it); the user-facing name lives in settings.display_name and is
freely editable. Accounts created before the split keep their old self-chosen
username as the id.

Registration issues the bearer token exactly once. Google sign-in re-issues
the same token on every login, so an account survives cleared extension
storage as long as it is linked to a Google identity. ID tokens are verified
through Google's tokeninfo endpoint (signature checked by Google;
audience/issuer checked here) — fine for our volume, switch to local JWKS
verification if traffic grows.
"""
from __future__ import annotations

import logging
import secrets

import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import config
import db
from auth import CurrentUser
from storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter()

_GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
_PROVIDER = "google"


class RegisterRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=64)


class RegisterResponse(BaseModel):
    username: str  # internal account id
    token: str
    display_name: str


def _create_account(display_name: str) -> tuple[str, str]:
    """Allocate an internal account id, create the user and store the display
    name in their settings. Returns (username, token)."""
    for _ in range(10):
        username = f"u_{secrets.token_hex(5)}"
        token = db.create_user(username)
        if token is not None:
            storage = get_storage(username)
            storage.settings.display_name = display_name.strip()
            storage.save()
            return username, token
    raise HTTPException(status_code=500, detail="Could not allocate an account id.")


@router.post("/api/auth/register", response_model=RegisterResponse, status_code=201)
async def api_register(req: RegisterRequest) -> RegisterResponse:
    display_name = req.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="Name must not be empty.")

    username, token = _create_account(display_name)
    log.info("[auth] registered user %r (display_name=%r)", username, display_name)
    return RegisterResponse(username=username, token=token, display_name=display_name)


# ---------------------------------------------------------------------------
# Google sign-in
# ---------------------------------------------------------------------------

class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., min_length=1)


class GoogleAuthResponse(BaseModel):
    username: str  # internal account id
    token: str
    display_name: str
    created: bool  # True when this login created a brand-new account


async def _verify_google_id_token(id_token: str) -> dict:
    """Validate a Google ID token and return its claims.

    Google's tokeninfo endpoint verifies the signature and expiry; we verify
    the audience (our client id) and issuer.
    """
    if not config.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not configured on this server (GOOGLE_CLIENT_ID).",
        )
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_GOOGLE_TOKENINFO_URL, params={"id_token": id_token}) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=401, detail="Invalid Google token.")
                claims = await resp.json()
    except HTTPException:
        raise
    except Exception as err:
        log.warning("[auth] Google tokeninfo request failed: %s", err)
        raise HTTPException(status_code=502, detail="Could not verify the Google token.")

    if claims.get("aud") != config.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=401, detail="Google token audience mismatch.")
    if claims.get("iss") not in _GOOGLE_ISSUERS:
        raise HTTPException(status_code=401, detail="Google token issuer mismatch.")
    if not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Google token has no subject.")
    return claims


def _display_name_from_claims(claims: dict) -> str:
    email = str(claims.get("email") or "")
    name = str(claims.get("name") or claims.get("given_name") or "").strip()
    if name:
        return name[:64]
    if "@" in email:
        return email.split("@")[0][:64]
    return "there"


def _display_name_of(username: str) -> str:
    settings = get_storage(username).settings
    return settings.display_name or username


def _google_login(claims: dict) -> GoogleAuthResponse:
    sub = str(claims["sub"])
    email = str(claims.get("email") or "")

    username = db.identity_owner(_PROVIDER, sub)
    if username is not None:
        token = db.user_token(username)
        if token is not None:
            return GoogleAuthResponse(
                username=username, token=token,
                display_name=_display_name_of(username), created=False,
            )
        log.warning("[auth] identity %r points to missing user %r, recreating", sub, username)

    display_name = _display_name_from_claims(claims)
    username, token = _create_account(display_name)
    if db.identity_link(_PROVIDER, sub, email, username):
        log.info("[auth] google sign-up: user %r (display_name=%r email=%r)", username, display_name, email)
        return GoogleAuthResponse(username=username, token=token, display_name=display_name, created=True)

    # Concurrent login already linked this identity — use its account.
    owner = db.identity_owner(_PROVIDER, sub)
    owner_token = db.user_token(owner) if owner else None
    if owner and owner_token:
        return GoogleAuthResponse(
            username=owner, token=owner_token,
            display_name=_display_name_of(owner), created=False,
        )
    raise HTTPException(status_code=500, detail="Could not link the Google identity.")


@router.post("/api/auth/google", response_model=GoogleAuthResponse)
async def api_auth_google(req: GoogleAuthRequest) -> GoogleAuthResponse:
    """Sign in with Google: returns the linked account (re-issuing its token)
    or creates a new one from the Google profile."""
    claims = await _verify_google_id_token(req.id_token)
    return _google_login(claims)


class AccountResponse(BaseModel):
    username: str  # internal account id
    display_name: str
    google_linked: bool
    google_email: str = ""


@router.get("/api/auth/account", response_model=AccountResponse)
async def api_auth_account(username: CurrentUser) -> AccountResponse:
    """Current account info for the Settings screen (id, name, Google link)."""
    ident = db.identity_for_user(username, _PROVIDER)
    return AccountResponse(
        username=username,
        display_name=_display_name_of(username),
        google_linked=ident is not None,
        google_email=(ident or {}).get("email", ""),
    )


@router.post("/api/auth/google/link")
async def api_auth_google_link(req: GoogleAuthRequest, username: CurrentUser) -> dict:
    """Attach a Google identity to the current (username-registered) account,
    so future Google logins resolve to it."""
    claims = await _verify_google_id_token(req.id_token)
    sub = str(claims["sub"])
    email = str(claims.get("email") or "")

    owner = db.identity_owner(_PROVIDER, sub)
    if owner == username:
        return {"ok": True, "email": email}
    if owner is not None:
        raise HTTPException(status_code=409, detail="This Google account is already linked to another user.")
    if not db.identity_link(_PROVIDER, sub, email, username):
        raise HTTPException(status_code=409, detail="This Google account is already linked to another user.")
    log.info("[auth] linked google identity to user %r (email=%r)", username, email)
    return {"ok": True, "email": email}
