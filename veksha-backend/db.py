"""db.py — SQLite storage for users, per-user KB, and chat history.

Replaces the per-user JSON files in data/. One database file
(data/veksha.db), WAL mode, one connection per thread (same pattern as
db_cache.py). The KB is stored as a JSON document per user — normalizing
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
import os
import secrets
import sqlite3
import threading
import time
from typing import Any, Optional

from config import DATA_DIR

log = logging.getLogger(__name__)

_DB_PATH = os.path.join(DATA_DIR, "veksha.db")
_local = threading.local()


def _conn() -> sqlite3.Connection:
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(_DB_PATH, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                   username TEXT PRIMARY KEY,
                   token    TEXT UNIQUE NOT NULL,
                   created  REAL NOT NULL
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS kb (
                   username TEXT PRIMARY KEY,
                   data     TEXT NOT NULL,
                   updated  REAL NOT NULL
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS chat_history (
                   username TEXT PRIMARY KEY,
                   data     TEXT NOT NULL,
                   updated  REAL NOT NULL
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
                   created  REAL NOT NULL,
                   PRIMARY KEY (provider, subject)
               )"""
        )
        # One row per review; the raw material for FSRS weight optimization
        # and review-history UI. stability/difficulty are post-review values,
        # retrievability is the predicted recall just before the review
        # (NULL for the first review of a word).
        conn.execute(
            """CREATE TABLE IF NOT EXISTS review_log (
                   id             INTEGER PRIMARY KEY AUTOINCREMENT,
                   username       TEXT NOT NULL,
                   word           TEXT NOT NULL,
                   ts             REAL NOT NULL,
                   rating         INTEGER NOT NULL,
                   outcome        TEXT NOT NULL,
                   task_type      TEXT NOT NULL DEFAULT '',
                   elapsed_days   REAL NOT NULL,
                   scheduled_days REAL NOT NULL,
                   stability      REAL NOT NULL,
                   difficulty     REAL NOT NULL,
                   retrievability REAL
               )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_review_log_user_ts ON review_log (username, ts)"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS user_settings (
                   username           TEXT PRIMARY KEY,
                   display_name       TEXT NOT NULL DEFAULT '',
                   native_lang        TEXT NOT NULL DEFAULT '',
                   active_target_lang TEXT NOT NULL DEFAULT '',
                   reminder_level     INTEGER NOT NULL DEFAULT 2,
                   overseer           INTEGER NOT NULL DEFAULT 0,
                   voice_enabled      INTEGER NOT NULL DEFAULT 1,
                   FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
               )"""
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(user_settings)").fetchall()}
        if "voice_enabled" not in columns:
            conn.execute("ALTER TABLE user_settings ADD COLUMN voice_enabled INTEGER NOT NULL DEFAULT 1")
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
        conn.commit()
        _local.conn = conn
    return conn


# ---------------------------------------------------------------------------
# Users / tokens
# ---------------------------------------------------------------------------

def create_user(username: str) -> Optional[str]:
    """Register a user and return their bearer token, or None if the name is taken."""
    token = secrets.token_urlsafe(32)
    try:
        # `with conn` commits on success and rolls back on exception — without
        # the rollback a failed INSERT would keep the write transaction open
        # and block every later write ("database is locked").
        with _conn() as c:
            c.execute(
                "INSERT INTO users (username, token, created) VALUES (?,?,?)",
                (username, token, time.time()),
            )
        return token
    except sqlite3.IntegrityError:
        return None


def token_owner(token: str) -> Optional[str]:
    """Return the username owning this token, or None."""
    if not token:
        return None
    row = _conn().execute("SELECT username FROM users WHERE token=?", (token,)).fetchone()
    return row[0] if row else None


def user_exists(username: str) -> bool:
    row = _conn().execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
    return row is not None


def user_token(username: str) -> Optional[str]:
    """The bearer token of an existing user (re-issued at Google login)."""
    row = _conn().execute("SELECT token FROM users WHERE username=?", (username,)).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# External identities (Google OAuth)
# ---------------------------------------------------------------------------

def identity_owner(provider: str, subject: str) -> Optional[str]:
    row = _conn().execute(
        "SELECT username FROM identities WHERE provider=? AND subject=?",
        (provider, subject),
    ).fetchone()
    return row[0] if row else None


def identity_link(provider: str, subject: str, email: str, username: str) -> bool:
    """Attach an external identity to a user. False if the identity is already
    linked (concurrent login race) — re-read identity_owner in that case."""
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO identities (provider, subject, email, username, created) VALUES (?,?,?,?,?)",
                (provider, subject, email, username, time.time()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def identity_for_user(username: str, provider: str) -> Optional[dict]:
    row = _conn().execute(
        "SELECT subject, email FROM identities WHERE provider=? AND username=?",
        (provider, username),
    ).fetchone()
    return {"subject": row[0], "email": row[1]} if row else None


def delete_user_data(username: str) -> None:
    """Wipe KB, chat history and review log (keeps the account/token)."""
    with _conn() as c:
        c.execute("DELETE FROM kb WHERE username=?", (username,))
        c.execute("DELETE FROM chat_history WHERE username=?", (username,))
        c.execute("DELETE FROM review_log WHERE username=?", (username,))


def settings_get(username: str) -> Optional[dict]:
    row = _conn().execute(
        "SELECT display_name, native_lang, active_target_lang, reminder_level, overseer, voice_enabled "
        "FROM user_settings WHERE username=?", (username,),
    ).fetchone()
    if row is None:
        return None
    languages = _conn().execute(
        "SELECT lang, level, goals, prompt FROM user_languages "
        "WHERE username=? ORDER BY position", (username,),
    ).fetchall()
    return {
        "display_name": row[0],
        "native_lang": row[1],
        "target_lang": row[2],
        "reminder_level": row[3],
        "overseer": bool(row[4]),
        "voice_enabled": bool(row[5]),
        "language_settings": {
            lang: {"level": level, "goals": goals, "prompt": prompt}
            for lang, level, goals, prompt in languages
        },
    }


def settings_set(username: str, settings: Any) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO user_settings "
            "(username, display_name, native_lang, active_target_lang, reminder_level, overseer, voice_enabled) "
            "VALUES (?,?,?,?,?,?,?)",
            (username, settings.display_name, settings.native_lang, settings.target_lang,
             settings.reminder_level, int(settings.overseer), int(settings.voice_enabled)),
        )
        c.execute("DELETE FROM user_languages WHERE username=?", (username,))
        c.executemany(
            "INSERT INTO user_languages (username, lang, level, goals, prompt, position) "
            "VALUES (?,?,?,?,?,?)",
            [
                (username, lang, prefs["level"], prefs.get("goals", ""), prefs.get("prompt", ""), position)
                for position, (lang, prefs) in enumerate(settings.language_settings.items())
            ],
        )


def purge_all_users() -> None:
    """Destructively remove every account and all account-owned data."""
    with _conn() as c:
        for table in ("identities", "review_log", "chat_history", "kb", "user_languages", "user_settings", "users"):
            c.execute(f"DELETE FROM {table}")


# ---------------------------------------------------------------------------
# KB / chat history documents
# ---------------------------------------------------------------------------

def kb_get(username: str) -> Optional[dict]:
    row = _conn().execute("SELECT data FROM kb WHERE username=?", (username,)).fetchone()
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
            "INSERT OR REPLACE INTO kb (username, data, updated) VALUES (?,?,?)",
            (username, json.dumps(data, ensure_ascii=False), time.time()),
        )


# ---------------------------------------------------------------------------
# Review log (FSRS)
# ---------------------------------------------------------------------------

def review_log_add(
    username: str,
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
               (username, word, ts, rating, outcome, task_type,
                elapsed_days, scheduled_days, stability, difficulty, retrievability)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (username, word, ts, rating, outcome, task_type,
             elapsed_days, scheduled_days, stability, difficulty, retrievability),
        )


def review_log_recent(username: str, word: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Latest reviews, newest first (optionally for a single word)."""
    sql = (
        "SELECT word, ts, rating, outcome, task_type, elapsed_days,"
        " scheduled_days, stability, difficulty, retrievability"
        " FROM review_log WHERE username=?"
    )
    args: list = [username]
    if word is not None:
        sql += " AND word=?"
        args.append(word)
    sql += " ORDER BY ts DESC LIMIT ?"
    args.append(max(1, min(int(limit), 500)))

    cols = ("word", "ts", "rating", "outcome", "task_type", "elapsed_days",
            "scheduled_days", "stability", "difficulty", "retrievability")
    return [dict(zip(cols, row)) for row in _conn().execute(sql, args).fetchall()]


def review_log_counts(username: str) -> dict[str, int]:
    rows = _conn().execute(
        "SELECT task_type, COUNT(*) FROM review_log WHERE username=? GROUP BY task_type",
        (username,),
    ).fetchall()
    anki = sum(count for task_type, count in rows if task_type == "anki")
    training = sum(count for task_type, count in rows if task_type != "anki")
    return {"anki_reviews": anki, "training_reviews": training}


def review_log_delete_user(username: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM review_log WHERE username=?", (username,))


def history_get(username: str) -> list[dict]:
    row = _conn().execute("SELECT data FROM chat_history WHERE username=?", (username,)).fetchone()
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
            "INSERT OR REPLACE INTO chat_history (username, data, updated) VALUES (?,?,?)",
            (username, json.dumps(history, ensure_ascii=False), time.time()),
        )
