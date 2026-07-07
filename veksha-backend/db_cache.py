"""db_cache.py — persistent SQLite cache for reusable LLM outputs.

A single namespaced key->JSON table that survives restarts and is shared by all
users on this backend instance. Used as the durable layer for:

  ns="tr"      — short translations (under translation_cache's memory/Redis layers)
  ns="explain" — "Break down" / explanation popups
  ns="topic"   — generated topic vocabulary (reused across users)

SQLite is built into Python — no server, no install. Blocking calls are run in a
threadpool via asyncio.to_thread so they never stall the event loop. Each worker
thread keeps its own connection (sqlite connections are not shareable across
threads); WAL mode allows concurrent readers alongside a single writer.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import unicodedata
from typing import Any

from config import DATA_DIR, TRANSLATION_CACHE_TTL_SECONDS

log = logging.getLogger(__name__)

_DB_PATH = os.path.join(DATA_DIR, "cache.db")
_local = threading.local()


def make_key(*parts: str) -> str:
    """Stable cache key from arbitrary parts (NFKC + casefold + collapsed spaces)."""
    norm = [
        " ".join(unicodedata.normalize("NFKC", p).casefold().split())
        for p in parts
    ]
    digest = hashlib.sha256("\x1f".join(norm).encode("utf-8")).hexdigest()
    return digest


def _conn() -> sqlite3.Connection:
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(_DB_PATH, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS cache (
                   ns      TEXT NOT NULL,
                   key     TEXT NOT NULL,
                   value   TEXT NOT NULL,
                   expiry  REAL,
                   created REAL NOT NULL,
                   PRIMARY KEY (ns, key)
               )"""
        )
        conn.commit()
        _local.conn = conn
    return conn


def _get_sync(ns: str, key: str) -> Any | None:
    try:
        row = _conn().execute(
            "SELECT value, expiry FROM cache WHERE ns=? AND key=?", (ns, key)
        ).fetchone()
    except Exception as exc:
        log.warning("[db_cache] read failed ns=%s: %s", ns, exc)
        return None
    if row is None:
        return None
    value, expiry = row
    if expiry is not None and expiry < time.time():
        try:
            c = _conn()
            c.execute("DELETE FROM cache WHERE ns=? AND key=?", (ns, key))
            c.commit()
        except Exception:
            pass
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _set_sync(ns: str, key: str, value: Any, ttl: float | None) -> None:
    expiry = time.time() + ttl if ttl else None
    try:
        c = _conn()
        c.execute(
            "INSERT OR REPLACE INTO cache (ns, key, value, expiry, created) VALUES (?,?,?,?,?)",
            (ns, key, json.dumps(value, ensure_ascii=False, separators=(",", ":")), expiry, time.time()),
        )
        c.commit()
    except Exception as exc:
        log.warning("[db_cache] write failed ns=%s: %s", ns, exc)


async def cache_get(ns: str, key: str) -> Any | None:
    """Return the cached JSON value for (ns, key), or None on miss/expired."""
    return await asyncio.to_thread(_get_sync, ns, key)


async def cache_set(
    ns: str, key: str, value: Any, ttl: float | None = TRANSLATION_CACHE_TTL_SECONDS
) -> None:
    """Store a JSON-serializable value under (ns, key). ttl=None means no expiry."""
    await asyncio.to_thread(_set_sync, ns, key, value, ttl)
