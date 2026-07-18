"""
api/auth.py — registration and Google sign-in endpoints.

  POST /api/auth/register    {"display_name"} → {"username", "token", "display_name"}
  POST /api/auth/google/start           → browser-neutral OAuth flow
  POST /api/auth/google/link/start      → link flow (Bearer)
  GET  /api/auth/google/callback        → HTTPS Google callback
  GET  /api/auth/google/[link/]status/* → one-time flow result

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
import hashlib
from urllib.parse import urlencode

import aiohttp
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import config
import db
from auth import CurrentUser
from storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter()

_GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
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


class GoogleFlowStartResponse(BaseModel):
    flow_id: str
    authorization_url: str
    expires_in: int = 600


def _flow_key(flow_id: str) -> str:
    return hashlib.sha256(flow_id.encode("utf-8")).hexdigest()


def _require_google_web_flow() -> None:
    missing = [
        name for name, value in (
            ("GOOGLE_CLIENT_ID", config.GOOGLE_CLIENT_ID),
            ("GOOGLE_CLIENT_SECRET", config.GOOGLE_CLIENT_SECRET),
            ("GOOGLE_OAUTH_REDIRECT_URI", config.GOOGLE_OAUTH_REDIRECT_URI),
        ) if not value
    ]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"Google sign-in is not configured on this server ({', '.join(missing)}).",
        )


def _start_google_flow(mode: str, username: str | None = None) -> GoogleFlowStartResponse:
    _require_google_web_flow()
    flow_id = secrets.token_urlsafe(32)
    state = secrets.token_urlsafe(32)
    db.oauth_flow_create(_flow_key(state), _flow_key(flow_id), mode, username)
    params = {
        'client_id': config.GOOGLE_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': config.GOOGLE_OAUTH_REDIRECT_URI,
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account',
    }
    authorization_url = f"{_GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"
    return GoogleFlowStartResponse(flow_id=flow_id, authorization_url=authorization_url)


async def _exchange_google_code(code: str) -> dict:
    _require_google_web_flow()
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(_GOOGLE_TOKEN_URL, data={
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": config.GOOGLE_OAUTH_REDIRECT_URI,
            }) as resp:
                payload = await resp.json(content_type=None)
                if resp.status != 200 or not payload.get("id_token"):
                    log.warning("[auth] Google code exchange failed (HTTP %s)", resp.status)
                    raise HTTPException(status_code=401, detail="Google authorization failed.")
    except HTTPException:
        raise
    except Exception as err:
        log.warning("[auth] Google code exchange request failed: %s", err)
        raise HTTPException(status_code=502, detail="Could not complete Google authorization.")
    return await _verify_google_id_token(str(payload["id_token"]))


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


def _google_link(claims: dict, username: str) -> dict:
    sub = str(claims["sub"])
    email = str(claims.get("email") or "")

    owner = db.identity_owner(_PROVIDER, sub)
    if owner == username:
        return {"ok": True, "email": email}
    if owner is not None:
        # Recovery for accounts orphaned by the old popup OAuth race: Google
        # created an account, the popup reopened on the stale name step, and
        # the user then registered a second local account. Only reclaim an
        # owner that never completed onboarding and contains no learning data.
        previous = get_storage(owner)
        if (
            not previous.settings.is_onboarded()
            and not previous.words
            and not previous.lesson_topics
            and not db.user_has_account_activity(owner)
            and db.identity_reassign(_PROVIDER, sub, owner, username, email)
        ):
            log.info(
                "[auth] moved google identity from pristine account %r to user %r",
                owner, username,
            )
            return {"ok": True, "email": email}
        raise HTTPException(status_code=409, detail="This Google account is already linked to another user.")
    if not db.identity_link(_PROVIDER, sub, email, username):
        raise HTTPException(status_code=409, detail="This Google account is already linked to another user.")
    log.info("[auth] linked google identity to user %r (email=%r)", username, email)
    return {"ok": True, "email": email}


@router.post("/api/auth/google/start", response_model=GoogleFlowStartResponse)
async def api_auth_google_start(response: Response) -> GoogleFlowStartResponse:
    """Start a browser-neutral login. Google returns only to our HTTPS
    callback; the extension receives the result by polling with flow_id."""
    response.headers["Cache-Control"] = "no-store"
    return _start_google_flow("login")


@router.post("/api/auth/google/link/start", response_model=GoogleFlowStartResponse)
async def api_auth_google_link_start(response: Response, username: CurrentUser) -> GoogleFlowStartResponse:
    response.headers["Cache-Control"] = "no-store"
    return _start_google_flow("link", username)


@router.get("/api/auth/google/callback", response_class=HTMLResponse)
async def api_auth_google_callback(
    state: str = Query(..., min_length=20, max_length=200),
    code: str | None = Query(None),
    error: str | None = Query(None),
) -> HTMLResponse:
    flow_key = _flow_key(state)
    flow = db.oauth_flow_get(flow_key)
    if flow is None or flow["status"] != "pending":
        raise HTTPException(status_code=400, detail="This sign-in request is invalid or expired.")

    if error or not code:
        db.oauth_flow_finish(flow_key, error="cancelled" if error == "access_denied" else "failed")
        return HTMLResponse(_oauth_result_page(False), status_code=400, headers={"Cache-Control": "no-store"})

    try:
        claims = await _exchange_google_code(code)
        if flow["mode"] == "link":
            result = _google_link(claims, str(flow["username"]))
        else:
            result = _google_login(claims).model_dump()
        if not db.oauth_flow_finish(flow_key, result=result):
            raise HTTPException(status_code=400, detail="This sign-in request was already used.")
    except HTTPException as exc:
        db.oauth_flow_finish(flow_key, error="taken" if exc.status_code == 409 else "failed")
        return HTMLResponse(
            _oauth_result_page(False), status_code=exc.status_code,
            headers={"Cache-Control": "no-store"},
        )
    return HTMLResponse(_oauth_result_page(True), headers={"Cache-Control": "no-store"})


def _oauth_result_page(success: bool) -> str:
    title = "Sign-in complete" if success else "Sign-in failed"
    message = (
        "You are signed in. You can return to Veksha; this tab will close automatically."
        if success else
        "Veksha could not complete sign-in. Return to the extension and try again."
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>body{{font:16px system-ui;margin:12vh auto;max-width:36rem;"
        "padding:2rem;color:#18211b;background:#f4f7f4}main{background:white;padding:2rem;"
        "border-radius:18px;box-shadow:0 8px 30px #16351b18}h1{font-size:1.5rem}</style></head>"
        f"<body><main><h1>{title}</h1><p>{message}</p></main></body></html>"
    )


@router.get("/api/auth/google/status/{flow_id}")
async def api_auth_google_status(flow_id: str, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    outcome = db.oauth_flow_take(_flow_key(flow_id), "login")
    if outcome is None:
        raise HTTPException(status_code=404, detail="Sign-in request not found or expired.")
    return outcome


@router.get("/api/auth/google/link/status/{flow_id}")
async def api_auth_google_link_status(flow_id: str, response: Response, username: CurrentUser) -> dict:
    response.headers["Cache-Control"] = "no-store"
    outcome = db.oauth_flow_take(_flow_key(flow_id), "link", username)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Sign-in request not found or expired.")
    return outcome


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
    return _google_link(claims, username)
