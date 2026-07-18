"""
config.py — Veksha backend configuration.

OPENAI_API_KEY must be provided via environment variable (never commit keys).
"""
import os

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# Directory for all runtime data (SQLite databases, i18n catalogue caches).
# Point this at a persistent volume in production (e.g. /data on Railway) —
# the default lives inside the app checkout and is wiped on redeploy.
DATA_DIR: str = os.getenv(
    "VEKSHA_DATA_DIR", os.path.join(os.path.dirname(__file__), "data")
)

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

# Shared secret for admin-only endpoints (currently: promo code creation).
# Sent as the X-Veksha-Admin-Secret header. Empty = admin endpoints disabled
# (503) — set this in the server environment before minting promo codes.
ADMIN_API_SECRET = os.getenv("ADMIN_API_SECRET", "")

# Optional Redis cache for one- and two-word translations.
# Leave REDIS_URL empty to run without caching.
REDIS_URL = os.getenv("REDIS_URL", "")
TRANSLATION_CACHE_TTL_SECONDS = int(
    os.getenv("TRANSLATION_CACHE_TTL_SECONDS", str(30 * 24 * 60 * 60))
)

# Log level: DEBUG (includes full LLM request texts), INFO (default)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
RELOAD = os.getenv("RELOAD", "0").lower() in {"1", "true", "yes"}

# CORS: comma-separated origin list; "*" is fine for local development.
# In production set e.g. CORS_ALLOW_ORIGINS="chrome-extension://<id>,https://app.veksha.example"
CORS_ALLOW_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()
]

# Debug endpoints (/api/debug/*): enabled by default only for local runs.
# The Procfile passes the host as a CLI flag (env HOST stays unset), so the
# HOST check alone would enable debug in production — treat any Railway
# environment as non-local explicitly.
_IS_LOCAL_RUN = (
    os.getenv("HOST", "127.0.0.1") in ("127.0.0.1", "localhost")
    and not os.getenv("RAILWAY_ENVIRONMENT")
)
DEBUG_API = os.getenv(
    "VEKSHA_DEBUG_API", "1" if _IS_LOCAL_RUN else "0",
).lower() in {"1", "true", "yes"}

# ---------------------------------------------------------------------------
# Spaced repetition (FSRS-4.5, see fsrs.py)
# ---------------------------------------------------------------------------

# Target recall probability at review time. Intervals are chosen so that a
# word comes due when its predicted recall drops to this value.
FSRS_DESIRED_RETENTION = 0.9

# Interval clamp (days). The minimum keeps a freshly lapsed word from being
# re-asked in the same session; the maximum keeps schedules sane.
FSRS_MIN_INTERVAL_DAYS = 0.25
FSRS_MAX_INTERVAL_DAYS = 365.0

# Initial delay before the first review of an explicitly added word (days).
# After the first review the schedule is fully FSRS-driven.
FIRST_REVIEW_DELAY_DAYS = 1

# A word becomes "due" once next_review is within REVIEW_WINDOW_HOURS from
# now (or already in the past); see collect_train_word / due_count.
REVIEW_WINDOW_HOURS = 24

# ---------------------------------------------------------------------------
# Review reminders (polled by the extension via chrome.alarms)
# ---------------------------------------------------------------------------

# Recommended polling interval for /api/reminders by the extension.
SCHEDULER_INTERVAL_MINUTES = 60

# If the user has >= this many words due (or a topic with expired context),
# /api/reminders signals a reminder.
REMINDER_MIN_WORDS = 3
