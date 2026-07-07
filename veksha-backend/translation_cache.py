"""Short one/two-word translation cache.

Two layers, both keyed identically:
  * an always-on in-process LRU — works with zero setup, so repeated
    translations are instant even on local/dev where no Redis is running;
  * Redis, used additionally when REDIS_URL is configured (shared across
    workers and restarts in production).

Only one- and two-word selections are cached (see is_cacheable).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from collections import OrderedDict
from typing import Any

from config import REDIS_URL, TRANSLATION_CACHE_TTL_SECONDS
from db_cache import cache_get, cache_set

log = logging.getLogger(__name__)

_redis: Any = None
_redis_retry_after = 0.0
_WORD_RE = re.compile(r"\S+")

# In-process fallback cache: key -> (expiry_epoch, result). Bounded LRU.
_MEM_MAX = 1000
_mem: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()


def _mem_get(key: str) -> dict | None:
    entry = _mem.get(key)
    if entry is None:
        return None
    expiry, result = entry
    if expiry < time.time():
        _mem.pop(key, None)
        return None
    _mem.move_to_end(key)
    return result


def _mem_set(key: str, result: dict) -> None:
    _mem[key] = (time.time() + TRANSLATION_CACHE_TTL_SECONDS, result)
    _mem.move_to_end(key)
    while len(_mem) > _MEM_MAX:
        _mem.popitem(last=False)


def is_cacheable(text: str) -> bool:
    """Cache only non-empty selections containing one or two words."""
    return 1 <= len(_WORD_RE.findall(text.strip())) <= 2


def _cache_key(
    source_lang: str,
    target_lang: str,
    text: str,
    bidirectional: bool,
) -> str:
    normalized_text = " ".join(
        unicodedata.normalize("NFKC", text).casefold().split()
    )
    payload = json.dumps(
        {
            "source_lang": source_lang.lower(),
            "target_lang": target_lang.lower(),
            "bidirectional": bidirectional,
            "text": normalized_text,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"veksha:translation:v1:{digest}"


async def _get_redis() -> Any:
    global _redis, _redis_retry_after

    if not REDIS_URL or time.monotonic() < _redis_retry_after:
        return None
    if _redis is not None:
        return _redis

    try:
        from redis.asyncio import Redis

        _redis = Redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        await _redis.ping()
        log.info("[translation_cache] Redis cache enabled")
        return _redis
    except Exception as exc:
        _redis = None
        _redis_retry_after = time.monotonic() + 30
        log.warning("[translation_cache] Redis unavailable; cache disabled: %s", exc)
        return None


async def get_translation(
    source_lang: str,
    target_lang: str,
    text: str,
    bidirectional: bool,
) -> dict | None:
    if not is_cacheable(text):
        return None

    key = _cache_key(source_lang, target_lang, text, bidirectional)

    # L1 — in-process cache (instant, no external dependency).
    mem = _mem_get(key)
    if mem is not None:
        log.info("[translation_cache] hit (memory) key=%s", key)
        return mem

    # L2 — SQLite (persistent across restarts, no server).
    db = await cache_get("tr", key)
    if isinstance(db, dict) and db.get("translation"):
        _mem_set(key, db)
        log.info("[translation_cache] hit (sqlite) key=%s", key)
        return db

    # L3 — Redis, if configured (shared across workers).
    client = await _get_redis()
    if client is None:
        return None
    try:
        cached = await client.get(key)
        if not cached:
            return None
        result = json.loads(cached)
        if not isinstance(result, dict) or not result.get("translation"):
            return None
        _mem_set(key, result)
        await cache_set("tr", key, result)
        log.info("[translation_cache] hit (redis) key=%s", key)
        return result
    except Exception as exc:
        log.warning("[translation_cache] read failed: %s", exc)
        return None


async def set_translation(
    source_lang: str,
    target_lang: str,
    text: str,
    bidirectional: bool,
    result: dict,
) -> None:
    if not is_cacheable(text) or not result.get("translation"):
        return

    key = _cache_key(source_lang, target_lang, text, bidirectional)
    _mem_set(key, result)
    await cache_set("tr", key, result)

    client = await _get_redis()
    if client is None:
        return
    try:
        await client.set(
            key,
            json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            ex=TRANSLATION_CACHE_TTL_SECONDS,
        )
        log.info("[translation_cache] stored key=%s", key)
    except Exception as exc:
        log.warning("[translation_cache] write failed: %s", exc)
