"""db.py — PostgreSQL storage for users and per-user knowledge bases.

The KB is stored as a JSON document per user — normalizing
words/topics into tables is deferred until the FSRS rework changes the word
schema anyway.

Auth model: `username` is a generated internal account id (the user-facing
name lives in settings.display_name); registration returns a bearer token.
Every request must present the token; the username is derived server-side.
Google identities map onto the same accounts (identities table).
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from psycopg import IntegrityError

from database import database

log = logging.getLogger(__name__)

_initialized = False
_init_lock = threading.Lock()


def _conn():
    global _initialized
    if _initialized:
        return database
    with _init_lock:
        if _initialized:
            return database
        conn = database
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                   username TEXT PRIMARY KEY,
                   token    TEXT UNIQUE NOT NULL,
                   created  DOUBLE PRECISION NOT NULL
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS kb (
                   username TEXT PRIMARY KEY,
                   data     TEXT NOT NULL,
                   updated  DOUBLE PRECISION NOT NULL
               )"""
        )
        # External identities (Google, …) linked to local accounts. A user may
        # register by username first and link Google later, or be created
        # directly by the first Google sign-in.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS identities (
                   provider TEXT NOT NULL,
                   subject  TEXT NOT NULL,
                   email    TEXT NOT NULL DEFAULT '',
                   username TEXT NOT NULL,
                   created  DOUBLE PRECISION NOT NULL,
                   PRIMARY KEY (provider, subject)
               )"""
        )
        # Browser-neutral Google OAuth handshakes. Only a SHA-256 hash of the
        # opaque flow id is stored; completed results are short-lived and are
        # deleted as soon as the extension consumes them.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS google_oauth_flows (
                   state_key TEXT PRIMARY KEY,
                   poll_key  TEXT UNIQUE NOT NULL,
                   mode     TEXT NOT NULL,
                   username TEXT,
                   status   TEXT NOT NULL DEFAULT 'pending',
                   result   TEXT NOT NULL DEFAULT '',
                   error    TEXT NOT NULL DEFAULT '',
                   created  DOUBLE PRECISION NOT NULL
               )"""
        )
        # One row per review; the raw material for FSRS weight optimization
        # and review-history UI. stability/difficulty are post-review values,
        # retrievability is the predicted recall just before the review
        # (NULL for the first review of a word).
        conn.execute(
            """CREATE TABLE IF NOT EXISTS review_log (
                   id             BIGSERIAL PRIMARY KEY,
                   username       TEXT NOT NULL,
                   lexical_item_id TEXT,
                   word           TEXT NOT NULL,
                   ts             DOUBLE PRECISION NOT NULL,
                   rating         INTEGER NOT NULL,
                   outcome        TEXT NOT NULL,
                   task_type      TEXT NOT NULL DEFAULT '',
                   elapsed_days   DOUBLE PRECISION NOT NULL,
                   scheduled_days DOUBLE PRECISION NOT NULL,
                   stability      DOUBLE PRECISION NOT NULL,
                   difficulty     DOUBLE PRECISION NOT NULL,
                   retrievability DOUBLE PRECISION
               )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_review_log_user_ts ON review_log (username, ts)"
        )
        conn.execute(
            "ALTER TABLE review_log ADD COLUMN IF NOT EXISTS lexical_item_id TEXT"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_review_log_user_item "
            "ON review_log (username, lexical_item_id)"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS user_settings (
                   username           TEXT PRIMARY KEY,
                   display_name       TEXT NOT NULL DEFAULT '',
                   native_lang        TEXT NOT NULL DEFAULT '',
                   active_target_lang TEXT NOT NULL DEFAULT '',
                   reminder_level     INTEGER NOT NULL DEFAULT 2,
                   mining_same_level  INTEGER NOT NULL DEFAULT 2,
                   mining_higher_level INTEGER NOT NULL DEFAULT 1,
                   FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
               )"""
        )
        conn.execute(
            "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS "
            "mining_same_level INTEGER NOT NULL DEFAULT 2"
        )
        conn.execute(
            "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS "
            "mining_higher_level INTEGER NOT NULL DEFAULT 1"
        )
        # Remove the retired coercive-reminder flag from existing databases.
        conn.execute("ALTER TABLE user_settings DROP COLUMN IF EXISTS " + "over" + "seer")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS user_languages (
                   username TEXT NOT NULL,
                   lang     TEXT NOT NULL,
                   level    TEXT NOT NULL,
                   goals    TEXT NOT NULL DEFAULT '',
                   prompt   TEXT NOT NULL DEFAULT '',
                   position INTEGER NOT NULL,
                   PRIMARY KEY (username, lang),
                   FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
               )"""
        )
        # Reading Sessions are started deliberately. Observations are tied to
        # their session id, so ordinary browsing can never populate this data.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS reading_sessions (
                   session_id TEXT PRIMARY KEY,
                   username   TEXT NOT NULL,
                   language   TEXT NOT NULL,
                   source_url TEXT NOT NULL DEFAULT '',
                   started_at DOUBLE PRECISION NOT NULL,
                   ended_at   DOUBLE PRECISION,
                   FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
               )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_reading_sessions_user_lang "
            "ON reading_sessions (username, language)"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS reading_session_words (
                   session_id TEXT NOT NULL,
                   word       TEXT NOT NULL,
                   domain     TEXT NOT NULL,
                   count      INTEGER NOT NULL DEFAULT 0,
                   last_seen  DOUBLE PRECISION NOT NULL,
                   PRIMARY KEY (session_id, word, domain),
                   FOREIGN KEY (session_id) REFERENCES reading_sessions(session_id) ON DELETE CASCADE
               )"""
        )
        # Passive observations cannot be attributed to a deliberate session.
        conn.execute("DROP TABLE IF EXISTS " + "word_" + "freq")
        # Paid subscription state. One row per user; `tier` is a plan family
        # from entitlements.py, `expires_at` a unix timestamp — an expired row
        # simply means the free tier again (rows are never deleted).
        conn.execute(
            """CREATE TABLE IF NOT EXISTS subscriptions (
                   username   TEXT PRIMARY KEY,
                   tier       TEXT NOT NULL,
                   expires_at DOUBLE PRECISION NOT NULL,
                   features   TEXT NOT NULL DEFAULT '',
                   updated    DOUBLE PRECISION NOT NULL,
                   FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
               )"""
        )
        # Empty means the legacy Premium bundle (all paid features).
        conn.execute(
            "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS "
            "features TEXT NOT NULL DEFAULT ''"
        )
        # Telegram accounts linked for billing: payments arriving from this
        # telegram_user_id credit the linked Veksha account.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS telegram_links (
                   telegram_user_id INTEGER PRIMARY KEY,
                   username         TEXT NOT NULL,
                   created          DOUBLE PRECISION NOT NULL
               )"""
        )
        # Short-lived single-use codes carried in the bot deep link
        # (t.me/<bot>?start=<code>) to prove account ownership.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS telegram_link_codes (
                   code     TEXT PRIMARY KEY,
                   username TEXT NOT NULL,
                   created  DOUBLE PRECISION NOT NULL
               )"""
        )
        # Ledger of Telegram Stars payments; the UNIQUE charge id makes the
        # payment webhook idempotent (Telegram/bot may deliver twice).
        conn.execute(
            """CREATE TABLE IF NOT EXISTS star_payments (
                   id                         BIGSERIAL PRIMARY KEY,
                   telegram_payment_charge_id TEXT UNIQUE NOT NULL,
                   telegram_user_id           INTEGER NOT NULL,
                   username                   TEXT NOT NULL,
                   plan_id                    TEXT NOT NULL,
                   stars_amount               INTEGER NOT NULL,
                   ts                         DOUBLE PRECISION NOT NULL
               )"""
        )
        # Manually-issued promo codes (e.g. testers, giveaways): redeeming one
        # grants Premium for `days` via the same subscriptions table payment
        # does. `redemptions` is a denormalized counter capped at
        # `max_redemptions`, kept in sync with promo_redemptions under the
        # same transaction.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS promo_codes (
                   code            TEXT PRIMARY KEY,
                   days            DOUBLE PRECISION NOT NULL,
                   max_redemptions INTEGER NOT NULL,
                   redemptions     INTEGER NOT NULL DEFAULT 0,
                   features        TEXT NOT NULL DEFAULT '',
                   created         DOUBLE PRECISION NOT NULL,
                   note            TEXT NOT NULL DEFAULT ''
               )"""
        )
        conn.execute(
            "ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS "
            "features TEXT NOT NULL DEFAULT ''"
        )
        # One row per (code, username): the primary key stops a user from
        # redeeming the same code twice.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS promo_redemptions (
                   code        TEXT NOT NULL,
                   username    TEXT NOT NULL,
                   redeemed_at DOUBLE PRECISION NOT NULL,
                   PRIMARY KEY (code, username)
               )"""
        )
        # Per-feature monthly prices are mutable through the admin API. The
        # initial values preserve the old 100-Star full-bundle price.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS feature_prices (
                   feature       TEXT PRIMARY KEY,
                   stars_monthly INTEGER NOT NULL CHECK(stars_monthly > 0),
                   updated       DOUBLE PRECISION NOT NULL
               )"""
        )
        now = time.time()
        conn.executemany(
            "INSERT INTO feature_prices (feature, stars_monthly, updated) "
            "VALUES (%s,%s,%s) ON CONFLICT (feature) DO NOTHING",
            [
                ("grammar_lens", 40, now),
                ("immersion", 35, now),
                ("dual_subtitles", 25, now),
            ],
        )
        # Opaque checkout snapshots lock the chosen features and amount before
        # Telegram opens. A paid checkout cannot be replayed with a new charge.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS billing_checkouts (
                   code             TEXT PRIMARY KEY,
                   username         TEXT NOT NULL,
                   features         TEXT NOT NULL,
                   stars_amount     INTEGER NOT NULL,
                   days             DOUBLE PRECISION NOT NULL,
                   telegram_user_id INTEGER,
                   paid             INTEGER NOT NULL DEFAULT 0,
                   created          DOUBLE PRECISION NOT NULL
               )"""
        )
        # Quizlet exports tracking: records which words have been exported to Quizlet
        conn.execute(
            """CREATE TABLE IF NOT EXISTS quizlet_exports (
                   id        BIGSERIAL PRIMARY KEY,
                   username  TEXT NOT NULL,
                   word      TEXT NOT NULL,
                   exported_at DOUBLE PRECISION NOT NULL,
                   FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE,
                   UNIQUE(username, word)
               )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_quizlet_exports_user ON quizlet_exports (username)"
        )
        # One row per successful OpenAI request. Token counts come from the
        # provider response rather than local estimates, so cached responses
        # and failed calls do not inflate the totals.
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ai_usage (
                   id                BIGSERIAL PRIMARY KEY,
                   username          TEXT NOT NULL,
                   call_name         TEXT NOT NULL,
                   model             TEXT NOT NULL,
                   prompt_tokens     INTEGER NOT NULL,
                   completion_tokens INTEGER NOT NULL,
                   total_tokens      INTEGER NOT NULL,
                   cached_tokens     INTEGER NOT NULL DEFAULT 0,
                   reasoning_tokens  INTEGER NOT NULL DEFAULT 0,
                   created           DOUBLE PRECISION NOT NULL,
                   FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
               )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_ai_usage_user_created "
            "ON ai_usage (username, created DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_ai_usage_created ON ai_usage (created DESC)"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS admin_query_audit (
                   id          BIGSERIAL PRIMARY KEY,
                   query_text  TEXT NOT NULL,
                   succeeded   INTEGER NOT NULL,
                   row_count   INTEGER NOT NULL DEFAULT 0,
                   duration_ms DOUBLE PRECISION NOT NULL,
                   error       TEXT NOT NULL DEFAULT '',
                   created     DOUBLE PRECISION NOT NULL
               )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_admin_query_audit_created "
            "ON admin_query_audit (created DESC)"
        )
        _initialized = True
    return database


def healthcheck() -> None:
    """Raise when PostgreSQL cannot serve a trivial query."""
    row = _conn().execute("SELECT 1").fetchone()
    if row != (1,):
        raise RuntimeError("database healthcheck returned an unexpected result")


# ---------------------------------------------------------------------------
# Users / tokens
# ---------------------------------------------------------------------------

def create_user(username: str) -> Optional[str]:
    """Register a user and return their bearer token, or None if the name is taken."""
    token = secrets.token_urlsafe(32)
    try:
        # The transaction commits on success and rolls back on exception.
        with _conn() as c:
            c.execute(
                "INSERT INTO users (username, token, created) VALUES (%s,%s,%s)",
                (username, token, time.time()),
            )
        return token
    except IntegrityError:
        return None


def token_owner(token: str) -> Optional[str]:
    """Return the username owning this token, or None."""
    if not token:
        return None
    row = _conn().execute("SELECT username FROM users WHERE token=%s", (token,)).fetchone()
    return row[0] if row else None


def user_exists(username: str) -> bool:
    row = _conn().execute("SELECT 1 FROM users WHERE username=%s", (username,)).fetchone()
    return row is not None


def user_token(username: str) -> Optional[str]:
    """The bearer token of an existing user (re-issued at Google login)."""
    row = _conn().execute("SELECT token FROM users WHERE username=%s", (username,)).fetchone()
    return row[0] if row else None


def user_has_account_activity(username: str) -> bool:
    """Whether an account has durable activity that must prevent automatic
    identity recovery/reassignment."""
    checks = (
        ("review_log", "username"),
        ("reading_sessions", "username"),
        ("user_languages", "username"),
        ("subscriptions", "username"),
        ("telegram_links", "username"),
        ("star_payments", "username"),
        ("promo_redemptions", "username"),
        ("ai_usage", "username"),
    )
    conn = _conn()
    return any(
        conn.execute(f"SELECT 1 FROM {table} WHERE {column}=%s LIMIT 1", (username,)).fetchone()
        is not None
        for table, column in checks
    )


# ---------------------------------------------------------------------------
# External identities (Google OAuth)
# ---------------------------------------------------------------------------

def identity_owner(provider: str, subject: str) -> Optional[str]:
    row = _conn().execute(
        "SELECT username FROM identities WHERE provider=%s AND subject=%s",
        (provider, subject),
    ).fetchone()
    return row[0] if row else None


def identity_link(provider: str, subject: str, email: str, username: str) -> bool:
    """Attach an external identity to a user. False if the identity is already
    linked (concurrent login race) — re-read identity_owner in that case."""
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO identities (provider, subject, email, username, created) VALUES (%s,%s,%s,%s,%s)",
                (provider, subject, email, username, time.time()),
            )
        return True
    except IntegrityError:
        return False


def identity_reassign(
    provider: str,
    subject: str,
    from_username: str,
    to_username: str,
    email: str,
) -> bool:
    """Move an identity from one exact owner to another, atomically."""
    with _conn() as c:
        cur = c.execute(
            "UPDATE identities SET username=%s, email=%s "
            "WHERE provider=%s AND subject=%s AND username=%s",
            (to_username, email, provider, subject, from_username),
        )
    return cur.rowcount == 1


def identity_for_user(username: str, provider: str) -> Optional[dict]:
    row = _conn().execute(
        "SELECT subject, email FROM identities WHERE provider=%s AND username=%s",
        (provider, username),
    ).fetchone()
    return {"subject": row[0], "email": row[1]} if row else None


# ---------------------------------------------------------------------------
# Short-lived browser-neutral OAuth handshakes
# ---------------------------------------------------------------------------

def oauth_flow_create(state_key: str, poll_key: str, mode: str, username: Optional[str]) -> None:
    with _conn() as c:
        c.execute("DELETE FROM google_oauth_flows WHERE created<%s", (time.time() - 900,))
        c.execute(
            "INSERT INTO google_oauth_flows (state_key, poll_key, mode, username, created) VALUES (%s,%s,%s,%s,%s)",
            (state_key, poll_key, mode, username, time.time()),
        )


def oauth_flow_get(state_key: str) -> Optional[dict]:
    row = _conn().execute(
        "SELECT mode, username, status, result, error, created "
        "FROM google_oauth_flows WHERE state_key=%s",
        (state_key,),
    ).fetchone()
    if row is None or row[5] < time.time() - 600:
        return None
    return {
        "mode": row[0], "username": row[1], "status": row[2],
        "result": row[3], "error": row[4], "created": row[5],
    }


def oauth_flow_finish(state_key: str, *, result: Optional[dict] = None, error: str = "") -> bool:
    """Finish a pending flow exactly once. Returns False for stale/replayed state."""
    status = "complete" if result is not None else "error"
    payload = json.dumps(result, separators=(",", ":")) if result is not None else ""
    with _conn() as c:
        cur = c.execute(
            "UPDATE google_oauth_flows SET status=%s, result=%s, error=%s "
            "WHERE state_key=%s AND status='pending' AND created>=%s",
            (status, payload, error, state_key, time.time() - 600),
        )
    return cur.rowcount == 1


def oauth_flow_take(poll_key: str, mode: str, username: Optional[str] = None) -> Optional[dict]:
    """Read flow state; atomically delete and return a terminal result."""
    row = _conn().execute(
        "SELECT state_key FROM google_oauth_flows WHERE poll_key=%s", (poll_key,)
    ).fetchone()
    if row is None:
        return None
    state_key = row[0]
    flow = oauth_flow_get(state_key)
    if flow is None or flow["mode"] != mode:
        return None
    if mode == "link" and flow["username"] != username:
        return None
    if flow["status"] == "pending":
        return {"status": "pending"}
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM google_oauth_flows WHERE state_key=%s AND status=%s",
            (state_key, flow["status"]),
        )
    if cur.rowcount != 1:
        return None
    if flow["status"] == "complete":
        return {"status": "complete", "result": json.loads(flow["result"])}
    return {"status": "error", "error": flow["error"] or "failed"}


def delete_user_data(username: str) -> None:
    """Wipe learning data while keeping the account and token."""
    with _conn() as c:
        c.execute("DELETE FROM kb WHERE username=%s", (username,))
        c.execute("DELETE FROM review_log WHERE username=%s", (username,))
        c.execute(
            "DELETE FROM reading_session_words WHERE session_id IN "
            "(SELECT session_id FROM reading_sessions WHERE username=%s)",
            (username,),
        )
        c.execute("DELETE FROM reading_sessions WHERE username=%s", (username,))


def settings_get(username: str) -> Optional[dict]:
    row = _conn().execute(
        "SELECT display_name, native_lang, active_target_lang, reminder_level, "
        "mining_same_level, mining_higher_level "
        "FROM user_settings WHERE username=%s", (username,),
    ).fetchone()
    if row is None:
        return None
    languages = _conn().execute(
        "SELECT lang, level, goals, prompt FROM user_languages "
        "WHERE username=%s ORDER BY position", (username,),
    ).fetchall()
    return {
        "display_name": row[0],
        "native_lang": row[1],
        "target_lang": row[2],
        "reminder_level": row[3],
        "mining_same_level_examples": row[4],
        "mining_higher_level_examples": row[5],
        "language_settings": {
            lang: {"level": level, "goals": goals, "prompt": prompt}
            for lang, level, goals, prompt in languages
        },
    }


def settings_set(username: str, settings: Any) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO user_settings "
            "(username, display_name, native_lang, active_target_lang, reminder_level, "
            "mining_same_level, mining_higher_level) VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (username) DO UPDATE SET "
            "display_name=excluded.display_name, native_lang=excluded.native_lang, "
            "active_target_lang=excluded.active_target_lang, reminder_level=excluded.reminder_level, "
            "mining_same_level=excluded.mining_same_level, "
            "mining_higher_level=excluded.mining_higher_level",
            (username, settings.display_name, settings.native_lang, settings.target_lang,
             settings.reminder_level,
             settings.mining_same_level_examples, settings.mining_higher_level_examples),
        )
        c.execute("DELETE FROM user_languages WHERE username=%s", (username,))
        c.executemany(
            "INSERT INTO user_languages (username, lang, level, goals, prompt, position) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            [
                (username, lang, prefs["level"], prefs.get("goals", ""), prefs.get("prompt", ""), position)
                for position, (lang, prefs) in enumerate(settings.language_settings.items())
            ],
        )


def purge_all_users() -> None:
    """Destructively remove every account and all account-owned data."""
    with _conn() as c:
        for table in (
            "google_oauth_flows", "identities", "review_log", "reading_session_words",
            "reading_sessions",
            "kb", "user_languages", "user_settings",
            "subscriptions", "telegram_links", "telegram_link_codes",
            "star_payments", "promo_redemptions", "promo_codes", "ai_usage", "users",
        ):
            c.execute(f"DELETE FROM {table}")


# ---------------------------------------------------------------------------
# AI usage
# ---------------------------------------------------------------------------

def ai_usage_record(
    username: str,
    call_name: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cached_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> None:
    """Persist provider-reported token usage for one successful AI call."""
    values = list(max(0, int(value or 0)) for value in (
        prompt_tokens, completion_tokens, total_tokens, cached_tokens, reasoning_tokens,
    ))
    if not values[2]:
        values[2] = values[0] + values[1]
    with _conn() as c:
        c.execute(
            "INSERT INTO ai_usage "
            "(username, call_name, model, prompt_tokens, completion_tokens, total_tokens, "
            "cached_tokens, reasoning_tokens, created) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (username, call_name[:120], model[:120], *values, time.time()),
        )


def _ai_usage_summary(since: float | None = None) -> dict:
    where = "WHERE created >= %s" if since is not None else ""
    params = (since,) if since is not None else None
    row = _conn().execute(
        "SELECT COUNT(*), COUNT(DISTINCT username), "
        "COALESCE(SUM(prompt_tokens),0), COALESCE(SUM(completion_tokens),0), "
        "COALESCE(SUM(total_tokens),0), COALESCE(SUM(cached_tokens),0), "
        f"COALESCE(SUM(reasoning_tokens),0) FROM ai_usage {where}",
        params,
    ).fetchone()
    return {
        "requests": row[0], "active_users": row[1],
        "prompt_tokens": row[2], "completion_tokens": row[3],
        "total_tokens": row[4], "cached_tokens": row[5],
        "reasoning_tokens": row[6],
    }


def ai_usage_stats(days: int = 30, user_limit: int = 100) -> dict:
    """Aggregate AI usage for the admin dashboard."""
    days = max(1, min(days, 366))
    cutoff = time.time() - days * 86400
    users = _conn().execute(
        "SELECT a.username, COALESCE(NULLIF(s.display_name, ''), a.username), "
        "COUNT(*), SUM(a.prompt_tokens), SUM(a.completion_tokens), SUM(a.total_tokens), "
        "SUM(a.cached_tokens), SUM(a.reasoning_tokens), MAX(a.created) "
        "FROM ai_usage a LEFT JOIN user_settings s ON s.username=a.username "
        "GROUP BY a.username, s.display_name ORDER BY SUM(a.total_tokens) DESC LIMIT %s",
        (max(1, min(user_limit, 500)),),
    ).fetchall()
    daily_rows = _conn().execute(
        "SELECT to_char(to_timestamp(created) AT TIME ZONE 'UTC', 'YYYY-MM-DD'), "
        "COUNT(*), COUNT(DISTINCT username), SUM(total_tokens) "
        "FROM ai_usage WHERE created >= %s GROUP BY 1 ORDER BY 1",
        (cutoff,),
    ).fetchall()
    daily_by_date = {row[0]: row[1:] for row in daily_rows}
    today = datetime.now(timezone.utc).date()
    daily = []
    for offset in range(days - 1, -1, -1):
        date = (today - timedelta(days=offset)).isoformat()
        row = daily_by_date.get(date, (0, 0, 0))
        daily.append({"date": date, "requests": row[0], "active_users": row[1], "total_tokens": row[2]})
    operation_rows = _conn().execute(
        "SELECT call_name, model, COUNT(*), SUM(total_tokens) FROM ai_usage "
        "WHERE created >= %s GROUP BY call_name, model ORDER BY SUM(total_tokens) DESC LIMIT 30",
        (cutoff,),
    ).fetchall()
    return {
        "period_days": days,
        "all_time": _ai_usage_summary(),
        "period": _ai_usage_summary(cutoff),
        "daily": daily,
        "users": [
            {
                "username": row[0], "display_name": row[1], "requests": row[2],
                "prompt_tokens": row[3], "completion_tokens": row[4],
                "total_tokens": row[5], "cached_tokens": row[6],
                "reasoning_tokens": row[7], "last_used": row[8],
            }
            for row in users
        ],
        "operations": [
            {"call_name": row[0], "model": row[1], "requests": row[2], "total_tokens": row[3]}
            for row in operation_rows
        ],
    }


# ---------------------------------------------------------------------------
# Read-only admin SQL console
# ---------------------------------------------------------------------------

_ADMIN_QUERY_START = re.compile(r"^(select|with|explain|show|values|table)\b", re.IGNORECASE)
_ADMIN_QUERY_BLOCKED = re.compile(
    r"\b(pg_advisory|pg_terminate_backend|pg_cancel_backend|pg_reload_conf|"
    r"pg_rotate_logfile|pg_log_backend_memory_contexts|pg_read_file|"
    r"pg_read_binary_file|pg_ls_dir|lo_import|lo_export|dblink|set_config)\w*\s*\(",
    re.IGNORECASE,
)


def validate_admin_query(sql: str) -> str:
    """Accept a single inspection statement; PostgreSQL enforces read-only too."""
    query = sql.strip()
    if query.endswith(";"):
        query = query[:-1].rstrip()
    if not query:
        raise ValueError("SQL-запрос пуст.")
    if len(query) > 20_000:
        raise ValueError("SQL-запрос слишком длинный (максимум 20 000 символов).")
    if ";" in query:
        raise ValueError("Разрешён только один SQL-запрос без внутренних точек с запятой.")
    if not _ADMIN_QUERY_START.match(query):
        raise ValueError("Разрешены только SELECT, WITH, EXPLAIN, SHOW, VALUES и TABLE.")
    if _ADMIN_QUERY_BLOCKED.search(query):
        raise ValueError("Этот вызов PostgreSQL недоступен в диагностической консоли.")
    return query


def _admin_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 20_000 else value[:20_000] + "…[обрезано]"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        rendered = "\\x" + bytes(value).hex()
        return rendered if len(rendered) <= 20_000 else rendered[:20_000] + "…[обрезано]"
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_admin_json_value(item) for item in value[:500]]
    if isinstance(value, dict):
        return {
            str(key): _admin_json_value(item)
            for key, item in list(value.items())[:500]
        }
    return str(value)


def admin_readonly_query(sql: str, limit: int = 200, timeout_ms: int = 3000) -> dict:
    """Execute one bounded statement in a PostgreSQL read-only transaction."""
    query = validate_admin_query(sql)
    limit = max(1, min(limit, 500))
    timeout_ms = max(100, min(timeout_ms, 10_000))
    started = time.perf_counter()
    with _conn() as c:
        read_only = c.execute("SET TRANSACTION READ ONLY")
        read_only.close()
        timeout = c.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (str(timeout_ms),),
        )
        timeout.close()
        cursor = c.execute(query)
        try:
            if cursor.description is None:
                raise ValueError("Запрос не вернул табличный результат.")
            columns = [column.name for column in cursor.description]
            raw_rows = cursor.fetchmany(limit + 1)
        finally:
            cursor.close()
    truncated = len(raw_rows) > limit
    rows = []
    output_size = 0
    for raw_row in raw_rows[:limit]:
        row = [_admin_json_value(value) for value in raw_row]
        row_size = len(json.dumps(row, ensure_ascii=False, default=str))
        if output_size + row_size > 1_000_000:
            truncated = True
            break
        rows.append(row)
        output_size += row_size
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def admin_query_audit_record(
    sql: str,
    succeeded: bool,
    row_count: int,
    duration_ms: float,
    error: str = "",
) -> None:
    """Record SQL-console activity without depending on the query transaction."""
    with _conn() as c:
        c.execute(
            "INSERT INTO admin_query_audit "
            "(query_text, succeeded, row_count, duration_ms, error, created) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (sql[:4000], int(succeeded), row_count, duration_ms, error[:1000], time.time()),
        )


# ---------------------------------------------------------------------------
# Knowledge-base documents
# ---------------------------------------------------------------------------

def kb_get(username: str) -> Optional[dict]:
    row = _conn().execute("SELECT data FROM kb WHERE username=%s", (username,)).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        log.exception("[db] corrupt KB document for %r", username)
        return None


def kb_set(username: str, data: dict) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO kb (username, data, updated) VALUES (%s,%s,%s) "
            "ON CONFLICT (username) DO UPDATE SET data=excluded.data, updated=excluded.updated",
            (username, json.dumps(data, ensure_ascii=False), time.time()),
        )


# ---------------------------------------------------------------------------
# Review log (FSRS)
# ---------------------------------------------------------------------------

def review_log_add(
    username: str,
    lexical_item_id: str,
    word: str,
    ts: float,
    rating: int,
    outcome: str,
    task_type: str,
    elapsed_days: float,
    scheduled_days: float,
    stability: float,
    difficulty: float,
    retrievability: Optional[float],
) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO review_log
               (username, lexical_item_id, word, ts, rating, outcome, task_type,
                elapsed_days, scheduled_days, stability, difficulty, retrievability)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (username, lexical_item_id, word, ts, rating, outcome, task_type,
             elapsed_days, scheduled_days, stability, difficulty, retrievability),
        )


def review_log_recent(
    username: str,
    word: Optional[str] = None,
    lexical_item_id: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Latest reviews, newest first (optionally for a single word)."""
    sql = (
        "SELECT lexical_item_id, word, ts, rating, outcome, task_type, elapsed_days,"
        " scheduled_days, stability, difficulty, retrievability"
        " FROM review_log WHERE username=%s"
    )
    args: list = [username]
    if word is not None:
        sql += " AND word=%s"
        args.append(word)
    if lexical_item_id is not None:
        sql += " AND lexical_item_id=%s"
        args.append(lexical_item_id)
    sql += " ORDER BY ts DESC LIMIT %s"
    args.append(max(1, min(int(limit), 500)))

    cols = ("item_id", "word", "ts", "rating", "outcome", "task_type", "elapsed_days",
            "scheduled_days", "stability", "difficulty", "retrievability")
    return [dict(zip(cols, row)) for row in _conn().execute(sql, args).fetchall()]


def review_log_counts(username: str) -> dict[str, int]:
    rows = _conn().execute(
        "SELECT task_type, COUNT(*) FROM review_log WHERE username=%s GROUP BY task_type",
        (username,),
    ).fetchall()
    anki = sum(count for task_type, count in rows if task_type == "anki")
    training = sum(count for task_type, count in rows if task_type != "anki")
    return {"anki_reviews": anki, "training_reviews": training}


def review_log_delete_user(username: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM review_log WHERE username=%s", (username,))


# ---------------------------------------------------------------------------
# Deliberate Reading Sessions
# ---------------------------------------------------------------------------

def reading_session_start(
    session_id: str, username: str, language: str, source_url: str, ts: float
) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO reading_sessions "
            "(session_id, username, language, source_url, started_at) VALUES (%s,%s,%s,%s,%s)",
            (session_id, username, language, source_url, ts),
        )


def reading_session_end(session_id: str, username: str, ts: float) -> bool:
    with _conn() as c:
        cur = c.execute(
            "UPDATE reading_sessions SET ended_at=%s "
            "WHERE session_id=%s AND username=%s AND ended_at IS NULL",
            (ts, session_id, username),
        )
    return cur.rowcount == 1


def reading_session_observe(
    session_id: str, username: str, counts: dict[str, int], domain: str, ts: float
) -> bool:
    if not counts:
        return True
    with _conn() as c:
        active = c.execute(
            "SELECT 1 FROM reading_sessions "
            "WHERE session_id=%s AND username=%s AND ended_at IS NULL",
            (session_id, username),
        ).fetchone()
        if active is None:
            return False
        c.executemany(
            """INSERT INTO reading_session_words (session_id, word, domain, count, last_seen)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (session_id, word, domain)
               DO UPDATE SET count = reading_session_words.count + excluded.count,
                             last_seen = excluded.last_seen""",
            [(session_id, word, domain, n, ts) for word, n in counts.items()],
        )
    return True


def reading_session_vocabulary(username: str, language: str, limit: int) -> list[dict]:
    """Aggregate words observed only during the user's Reading Sessions."""
    totals = _conn().execute(
        """SELECT w.word, SUM(w.count) AS total
           FROM reading_session_words w JOIN reading_sessions s USING (session_id)
           WHERE s.username=%s AND s.language=%s
           GROUP BY w.word ORDER BY total DESC LIMIT %s""",
        (username, language, max(1, min(int(limit), 500))),
    ).fetchall()
    if not totals:
        return []

    words = [word for word, _ in totals]
    placeholders = ",".join("%s" for _ in words)
    domain_rows = _conn().execute(
        f"""SELECT w.word, w.domain, SUM(w.count)
            FROM reading_session_words w JOIN reading_sessions s USING (session_id)
            WHERE s.username=%s AND s.language=%s AND w.word IN ({placeholders})
            GROUP BY w.word, w.domain""",
        (username, language, *words),
    ).fetchall()
    domains_by_word: dict[str, dict[str, int]] = {}
    for word, domain, count in domain_rows:
        domains_by_word.setdefault(word, {})[domain] = count

    return [
        {"word": word, "count": total, "domains": domains_by_word.get(word, {})}
        for word, total in totals
    ]


# ---------------------------------------------------------------------------
# Subscriptions / Telegram billing
# ---------------------------------------------------------------------------

def subscription_get(username: str) -> Optional[dict]:
    row = _conn().execute(
        "SELECT tier, expires_at, features FROM subscriptions WHERE username=%s", (username,)
    ).fetchone()
    return {"tier": row[0], "expires_at": row[1], "features": row[2]} if row else None


def subscription_extend(
    username: str,
    tier: str,
    days: float,
    features: Optional[list[str]] = None,
) -> float:
    """Grant `tier` for `days` more days and return the new expiry.

    An active subscription of the same tier is extended from its current
    expiry; anything else (no row, expired, different tier) starts from now.
    """
    now = time.time()
    current = subscription_get(username)
    base = now
    if current and current["tier"] == tier and current["expires_at"] > now:
        base = current["expires_at"]
    expires_at = base + days * 86400.0
    encoded_features = "" if features is None else json.dumps(sorted(set(features)), separators=(",", ":"))
    with _conn() as c:
        c.execute(
            "INSERT INTO subscriptions (username, tier, expires_at, features, updated) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (username) DO UPDATE SET "
            "tier=excluded.tier, expires_at=excluded.expires_at, "
            "features=excluded.features, updated=excluded.updated",
            (username, tier, expires_at, encoded_features, now),
        )
    return expires_at


def subscription_cancel(username: str) -> None:
    """End paid access immediately while retaining an auditable row."""
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO subscriptions (username, tier, expires_at, features, updated) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (username) DO UPDATE SET "
            "tier=excluded.tier, expires_at=excluded.expires_at, "
            "features=excluded.features, updated=excluded.updated",
            (username, "free", now, "[]", now),
        )


def feature_prices_get() -> list[dict]:
    rows = _conn().execute(
        "SELECT feature, stars_monthly, updated FROM feature_prices ORDER BY feature"
    ).fetchall()
    return [
        {"feature": row[0], "stars_monthly": row[1], "updated": row[2]}
        for row in rows
    ]


def feature_price_set(feature: str, stars_monthly: int) -> dict:
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO feature_prices (feature, stars_monthly, updated) VALUES (%s,%s,%s) "
            "ON CONFLICT (feature) DO UPDATE SET "
            "stars_monthly=excluded.stars_monthly, updated=excluded.updated",
            (feature, stars_monthly, now),
        )
    return {"feature": feature, "stars_monthly": stars_monthly, "updated": now}


def billing_checkout_create(
    username: str,
    code: str,
    features: list[str],
    stars_amount: int,
    days: float = 31,
) -> None:
    with _conn() as c:
        c.execute("DELETE FROM billing_checkouts WHERE username=%s AND paid=0", (username,))
        c.execute(
            "INSERT INTO billing_checkouts "
            "(code, username, features, stars_amount, days, created) VALUES (%s,%s,%s,%s,%s,%s)",
            (code, username, json.dumps(sorted(set(features))), stars_amount, days, time.time()),
        )


def billing_checkout_get(code: str) -> Optional[dict]:
    row = _conn().execute(
        "SELECT username, features, stars_amount, days, telegram_user_id, paid, created "
        "FROM billing_checkouts WHERE code=%s",
        (code,),
    ).fetchone()
    if not row:
        return None
    return {
        "code": code,
        "username": row[0],
        "features": json.loads(row[1]),
        "stars_amount": row[2],
        "days": row[3],
        "telegram_user_id": row[4],
        "paid": bool(row[5]),
        "created": row[6],
    }


def billing_checkout_link(code: str, telegram_user_id: int) -> Optional[dict]:
    with _conn() as c:
        cur = c.execute(
            "UPDATE billing_checkouts SET telegram_user_id=%s "
            "WHERE code=%s AND telegram_user_id IS NULL AND paid=0",
            (telegram_user_id, code),
        )
    return billing_checkout_get(code) if cur.rowcount == 1 else None


def billing_checkout_mark_paid(code: str, telegram_user_id: int) -> bool:
    with _conn() as c:
        cur = c.execute(
            "UPDATE billing_checkouts SET paid=1 "
            "WHERE code=%s AND telegram_user_id=%s AND paid=0",
            (code, telegram_user_id),
        )
    return cur.rowcount == 1


def promo_code_create(
    code: str,
    days: float,
    max_redemptions: int = 1,
    note: str = "",
    features: Optional[list[str]] = None,
) -> bool:
    """Mint a promo code. Returns False if the code already exists."""
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO promo_codes "
                "(code, days, max_redemptions, redemptions, features, created, note) "
                "VALUES (%s,%s,%s,0,%s,%s,%s)",
                (code, days, max_redemptions, json.dumps(features or []), time.time(), note),
            )
        return True
    except IntegrityError:
        return False


def promo_code_redeem(code: str, username: str) -> tuple[str, Optional[float]]:
    """Atomically claim one use of `code` for `username`.

    Returns (status, days): status is "ok", "invalid" (unknown code),
    "exhausted" (all uses already claimed), or "already_redeemed" (this user
    redeemed this code before). `days` is only set when status == "ok" — the
    caller still has to grant it via subscription_extend.

    The redemption count is claimed via a conditional UPDATE rather than a
    read-then-write, so two concurrent redemptions of the same code can't
    both slip through and push `redemptions` past `max_redemptions`.
    """
    with _conn() as c:
        cur = c.execute(
            "UPDATE promo_codes SET redemptions = redemptions + 1 "
            "WHERE code=%s AND redemptions < max_redemptions",
            (code,),
        )
        if cur.rowcount == 0:
            exists = c.execute("SELECT 1 FROM promo_codes WHERE code=%s", (code,)).fetchone()
            if not exists:
                return "invalid", None
            # An exhausted code the user themselves redeemed should read as
            # "already redeemed", not "someone claimed it all".
            mine = c.execute(
                "SELECT 1 FROM promo_redemptions WHERE code=%s AND username=%s",
                (code, username),
            ).fetchone()
            return ("already_redeemed" if mine else "exhausted"), None

        claimed = c.execute(
            "INSERT INTO promo_redemptions (code, username, redeemed_at) VALUES (%s,%s,%s) "
            "ON CONFLICT (code, username) DO NOTHING",
            (code, username, time.time()),
        )
        if claimed.rowcount == 0:
            # Already redeemed by this user — release the slot we just claimed.
            c.execute("UPDATE promo_codes SET redemptions = redemptions - 1 WHERE code=%s", (code,))
            return "already_redeemed", None

        days = c.execute("SELECT days FROM promo_codes WHERE code=%s", (code,)).fetchone()[0]
    return "ok", days


def promo_code_features(code: str) -> list[str]:
    row = _conn().execute("SELECT features FROM promo_codes WHERE code=%s", (code,)).fetchone()
    if not row or not row[0]:
        return []
    return json.loads(row[0])


def promo_codes_get(limit: int = 100) -> list[dict]:
    """Return recent promo codes for the authenticated admin dashboard."""
    rows = _conn().execute(
        "SELECT code, days, max_redemptions, redemptions, features, created, note "
        "FROM promo_codes ORDER BY created DESC LIMIT %s",
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [
        {
            "code": row[0],
            "days": row[1],
            "max_redemptions": row[2],
            "redemptions": row[3],
            "features": json.loads(row[4] or "[]"),
            "created": row[5],
            "note": row[6],
        }
        for row in rows
    ]


def telegram_link_code_create(username: str, code: str) -> None:
    with _conn() as c:
        # One outstanding code per user: a fresh request invalidates the old link.
        c.execute("DELETE FROM telegram_link_codes WHERE username=%s", (username,))
        c.execute(
            "INSERT INTO telegram_link_codes (code, username, created) VALUES (%s,%s,%s)",
            (code, username, time.time()),
        )


def telegram_link_code_consume(code: str, max_age_seconds: float) -> Optional[str]:
    """Redeem a link code: returns its username and deletes it, or None if
    the code is unknown or older than `max_age_seconds`."""
    with _conn() as c:
        row = c.execute(
            "SELECT username, created FROM telegram_link_codes WHERE code=%s", (code,)
        ).fetchone()
        if row is None:
            return None
        c.execute("DELETE FROM telegram_link_codes WHERE code=%s", (code,))
        if time.time() - row[1] > max_age_seconds:
            return None
        return row[0]


def telegram_link_set(telegram_user_id: int, username: str) -> None:
    """Bind a Telegram account to a user (rebinding overwrites)."""
    with _conn() as c:
        c.execute(
            "INSERT INTO telegram_links (telegram_user_id, username, created) "
            "VALUES (%s,%s,%s) ON CONFLICT (telegram_user_id) DO UPDATE SET "
            "username=excluded.username, created=excluded.created",
            (telegram_user_id, username, time.time()),
        )


def telegram_link_owner(telegram_user_id: int) -> Optional[str]:
    row = _conn().execute(
        "SELECT username FROM telegram_links WHERE telegram_user_id=%s",
        (telegram_user_id,),
    ).fetchone()
    return row[0] if row else None


def telegram_linked_user_ids(username: str) -> list[int]:
    rows = _conn().execute(
        "SELECT telegram_user_id FROM telegram_links WHERE username=%s", (username,)
    ).fetchall()
    return [row[0] for row in rows]


def star_payment_record(
    charge_id: str,
    telegram_user_id: int,
    username: str,
    plan_id: str,
    stars_amount: int,
) -> bool:
    """Insert a payment; False when this charge id was already recorded
    (duplicate webhook delivery — the caller must not re-apply it)."""
    try:
        with _conn() as c:
            c.execute(
                """INSERT INTO star_payments
                   (telegram_payment_charge_id, telegram_user_id, username,
                    plan_id, stars_amount, ts)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (charge_id, telegram_user_id, username, plan_id, stars_amount, time.time()),
            )
        return True
    except IntegrityError:
        return False


def star_payment_exists(charge_id: str) -> bool:
    return _conn().execute(
        "SELECT 1 FROM star_payments WHERE telegram_payment_charge_id=%s", (charge_id,)
    ).fetchone() is not None
def history_get(username: str) -> list[dict]:
    row = _conn().execute("SELECT data FROM chat_history WHERE username=%s", (username,)).fetchone()
    if row is None:
        return []
    try:
        loaded: Any = json.loads(row[0])
        return loaded if isinstance(loaded, list) else []
    except Exception:
        return []


def history_set(username: str, history: list[dict]) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO chat_history (username, data, updated) VALUES (%s,%s,%s) "
            "ON CONFLICT (username) DO UPDATE SET data=excluded.data, updated=excluded.updated",
            (username, json.dumps(history, ensure_ascii=False), time.time()),
        )


# ---------------------------------------------------------------------------
# Quizlet exports
# ---------------------------------------------------------------------------

def quizlet_export_mark(username: str, item_ids: list[str]) -> None:
    """Mark lexical meanings as exported using their stable identifiers."""
    if not item_ids:
        return
    now = time.time()
    with _conn() as c:
        c.executemany(
            "INSERT INTO quizlet_exports (username, word, exported_at) "
            "VALUES (%s,%s,%s) ON CONFLICT (username, word) DO NOTHING",
            [(username, item_id, now) for item_id in item_ids],
        )


def quizlet_is_exported(username: str, item_id: str) -> bool:
    """Check if a lexical meaning has been exported to Quizlet."""
    row = _conn().execute(
        "SELECT 1 FROM quizlet_exports WHERE username=%s AND word=%s",
        (username, item_id),
    ).fetchone()
    return row is not None
