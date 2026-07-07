"""db.py — SQLite storage for users, per-user KB, and chat history.

Replaces the per-user JSON files in data/. One database file
(data/veksha.db), WAL mode, one connection per thread (same pattern as
db_cache.py). The KB is stored as a JSON document per user — normalizing
words/topics into tables is deferred until the FSRS rework changes the word
schema anyway.

Auth model: a user registers once with a self-chosen username and receives a
bearer token (returned only at registration). Every request must present the
token; the username is derived server-side.
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


def delete_user_data(username: str) -> None:
    """Wipe KB, chat history and review log (keeps the account/token)."""
    with _conn() as c:
        c.execute("DELETE FROM kb WHERE username=?", (username,))
        c.execute("DELETE FROM chat_history WHERE username=?", (username,))
        c.execute("DELETE FROM review_log WHERE username=?", (username,))


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
