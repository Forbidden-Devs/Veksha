"""db_cache.py — persistent PostgreSQL cache for reusable LLM outputs.

A single namespaced key->JSON table that survives restarts and is shared by all
users on this backend instance. It remains only for the legacy subtitle adapter
and will disappear when that adapter moves to the new provider boundary.

Blocking calls are run in a threadpool via asyncio.to_thread so they never stall
the event loop.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
import unicodedata
from typing import Any

from config import TRANSLATION_CACHE_TTL_SECONDS
from database import database

log = logging.getLogger(__name__)

_initialized = False
_init_lock = threading.Lock()


def make_key(*parts: str) -> str:
    """Stable cache key from arbitrary parts (NFKC + casefold + collapsed spaces)."""
    norm = [
        " ".join(unicodedata.normalize("NFKC", p).casefold().split())
        for p in parts
    ]
    digest = hashlib.sha256("\x1f".join(norm).encode("utf-8")).hexdigest()
    return digest


def _conn():
    global _initialized
    if _initialized:
        return database
    with _init_lock:
        if _initialized:
            return database
        with database as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS cache (
                   ns      TEXT NOT NULL,
                   key     TEXT NOT NULL,
                   value   TEXT NOT NULL,
                   expiry  DOUBLE PRECISION,
                   created DOUBLE PRECISION NOT NULL,
                   PRIMARY KEY (ns, key)
               )"""
            )
            _initialized = True
    return database


def _get_sync(ns: str, key: str) -> Any | None:
    try:
        row = _conn().execute(
            "SELECT value, expiry FROM cache WHERE ns=%s AND key=%s", (ns, key)
        ).fetchone()
    except Exception as exc:
        log.warning("[db_cache] read failed ns=%s: %s", ns, exc)
        return None
    if row is None:
        return None
    value, expiry = row
    if expiry is not None and expiry < time.time():
        try:
            with _conn() as c:
                c.execute("DELETE FROM cache WHERE ns=%s AND key=%s", (ns, key))
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
        with _conn() as c:
            c.execute(
                "INSERT INTO cache (ns, key, value, expiry, created) VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT (ns, key) DO UPDATE SET "
                "value=excluded.value, expiry=excluded.expiry, created=excluded.created",
                (ns, key, json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                 expiry, time.time()),
            )
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
