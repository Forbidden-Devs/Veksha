"""
config.py — Veksha backend configuration.

OPENAI_API_KEY must be provided via environment variable (never commit keys).
"""
import os
from dataclasses import dataclass

TRUTHY = frozenset({"1", "true", "yes", "on"})


def env_text(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    value = env_text(name)
    return int(value) if value else default


def env_enabled(name: str, default: bool = False) -> bool:
    value = env_text(name)
    return value.lower() in TRUTHY if value else default


OPENAI_API_KEY: str = env_text("OPENAI_API_KEY")

# Directory for runtime files such as downloaded i18n catalogue caches.
DATA_DIR: str = os.getenv(
    "VEKSHA_DATA_DIR", os.path.join(os.path.dirname(__file__), "data")
)

# PostgreSQL is the durable store for accounts, learning state, billing data,
# review history and reusable LLM output caches. The runtime environment must
# provide DATABASE_URL explicitly.
DATABASE_URL = env_text("DATABASE_URL")
DATABASE_POOL_MIN_SIZE = env_int("DATABASE_POOL_MIN_SIZE", 1)
DATABASE_POOL_MAX_SIZE = env_int("DATABASE_POOL_MAX_SIZE", 10)

# OpenAI models
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")          # fast model for classification / short replies
OPENAI_SMART_MODEL = os.getenv("OPENAI_SMART_MODEL", "gpt-4.1")   # smarter model for content generation

# Google OAuth: the client ID whose ID tokens /api/auth/google accepts
# (audience check). Empty = Google sign-in disabled (503 from the endpoint).
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
# Must exactly match the HTTPS redirect URI registered on the Web application
# OAuth client in Google Cloud Console.
GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")

# Telegram billing companion bot (veksha-tgbot/). The bot authenticates its
# webhook calls to /api/billing/telegram/webhook with this shared secret;
# empty = Telegram billing disabled (503 from the billing link endpoint).
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")     # without @
TELEGRAM_BOT_WEBHOOK_SECRET = os.getenv("TELEGRAM_BOT_WEBHOOK_SECRET", "")

# How long a Telegram deep-link code (t.me/<bot>?start=<code>) stays valid.
TELEGRAM_LINK_CODE_TTL_SECONDS = int(
    os.getenv("TELEGRAM_LINK_CODE_TTL_SECONDS", str(15 * 60))
)

# Shared secret for billing-admin endpoints (catalog, prices, promo codes).
# Sent as the X-Veksha-Admin-Secret header. Empty = admin endpoints disabled
# (503) — set this in the server environment before minting promo codes.
ADMIN_API_SECRET = env_text("ADMIN_API_SECRET")

# Additional secret required by the read-only database console in the admin
# application. It must differ from ADMIN_API_SECRET so a leaked general admin
# credential does not automatically expose account data through SQL.
ADMIN_DATABASE_SECRET = env_text("ADMIN_DATABASE_SECRET")

# Optional Redis cache for one- and two-word translations.
# Leave REDIS_URL empty to run without caching.
REDIS_URL = env_text("REDIS_URL")

# Log level: DEBUG (includes full LLM request texts), INFO (default)
LOG_LEVEL = env_text("LOG_LEVEL", "INFO")

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

HOST = env_text("HOST", "127.0.0.1")
PORT = env_int("PORT", 8000)
RELOAD = env_enabled("RELOAD")

# CORS: comma-separated origin list; "*" is fine for local development.
# In production set e.g. CORS_ALLOW_ORIGINS="chrome-extension://<id>,https://app.veksha.example"
CORS_ALLOW_ORIGINS = list(filter(None, map(str.strip, env_text("CORS_ALLOW_ORIGINS", "*").split(","))))

# Debug endpoints (/api/debug/*): enabled by default only for local runs.
# HOST alone is not a reliable production signal. Deployments must set
# VEKSHA_ENVIRONMENT to a non-local value; local development may omit it.
_IS_LOCAL_RUN = (
    HOST in ("127.0.0.1", "localhost")
    and env_text("VEKSHA_ENVIRONMENT", "local").lower() == "local"
)
DEBUG_API = env_enabled("VEKSHA_DEBUG_API", _IS_LOCAL_RUN)

# Local extension development needs premium-gated flows (subtitles, Reading Coach,
# Grammar Lens) without configuring Telegram billing for every disposable DB.
DEV_ALL_FEATURES = env_enabled("VEKSHA_DEV_ALL_FEATURES", _IS_LOCAL_RUN)

# ---------------------------------------------------------------------------
# Spaced repetition (FSRS-4.5, see fsrs.py)
# ---------------------------------------------------------------------------

# Target recall probability at review time. Intervals are chosen so that a
# word comes due when its predicted recall drops to this value.
FSRS_DESIRED_RETENTION = 0.9

@dataclass(frozen=True, slots=True)
class ReviewPolicy:
    minimum_interval_days: float = 0.25
    maximum_interval_days: float = 365.0
    first_review_delay_days: float = 1.0
    due_window_hours: int = 24


REVIEW_POLICY = ReviewPolicy()
FSRS_MIN_INTERVAL_DAYS, FSRS_MAX_INTERVAL_DAYS = (
    REVIEW_POLICY.minimum_interval_days,
    REVIEW_POLICY.maximum_interval_days,
)
FIRST_REVIEW_DELAY_DAYS = REVIEW_POLICY.first_review_delay_days
REVIEW_WINDOW_HOURS = REVIEW_POLICY.due_window_hours

# ---------------------------------------------------------------------------
# Review reminders (polled by the extension via chrome.alarms)
# ---------------------------------------------------------------------------

# Recommended polling interval for /api/reminders by the extension.
SCHEDULER_INTERVAL_MINUTES, REMINDER_MIN_WORDS = 60, 3
