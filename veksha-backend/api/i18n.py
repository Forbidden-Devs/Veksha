"""
api/i18n.py — UI and backend string translation endpoints.

  GET  /api/i18n/{lang}     — cached translation (auto-fills missing keys)
  POST /api/i18n/translate  — full translation or delta for specific keys
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

import i18n

log = logging.getLogger(__name__)

router = APIRouter()


class I18nTranslateRequest(BaseModel):
    lang: str = Field(..., min_length=2, max_length=10)
    strings: dict[str, str] | None = None


@router.get("/api/i18n/{lang}")
async def api_get_i18n(lang: str) -> dict:
    """Returns the cached translation, auto-filling any keys added since the cache was built."""
    cached = i18n.load_cached(lang)
    if cached is None:
        cached = i18n.merge_translations({}, await i18n.generate_translation(lang))
        i18n.save_cache(lang, cached)
        log.info("[i18n] generated missing cache for lang=%r (%d strings)", lang, len(cached))
    if i18n.untranslated_strings(lang, cached):
        await i18n.ensure_cache_complete(lang)  # rate-limited internally
        cached = i18n.load_cached(lang) or cached
    return i18n.public_catalog(cached)


@router.post("/api/i18n/translate")
async def api_post_i18n_translate(req: I18nTranslateRequest) -> dict:
    """
    Without strings: full translation (with cache check).
    With strings: translate only the specified keys, merge into cache, return new ones.
    """
    if req.lang == "en":
        return {**i18n.UI_STRINGS, **i18n.BACKEND_STRINGS}

    if req.strings:
        translated = await i18n.translate_strings(req.lang, req.strings)
        cached = i18n.load_cached(req.lang) or {}
        i18n.save_cache(req.lang, i18n.merge_translations(cached, translated))
        log.info("[i18n] patched %d missing keys for lang=%r", len(translated), req.lang)
        return translated

    cached = i18n.load_cached(req.lang)
    if cached:
        # Explicit user request (language switch) — translate inline without
        # the ensure_cache_complete backoff.
        missing = i18n.untranslated_strings(req.lang, cached)
        if missing:
            log.info("[i18n] translating %d incomplete fields inline for lang=%r", len(missing), req.lang)
            new_strings = await i18n.translate_strings(req.lang, missing)
            if new_strings:
                cached = i18n.merge_translations(cached, new_strings)
                i18n.save_cache(req.lang, cached)
        return i18n.public_catalog(cached)

    translated = i18n.merge_translations({}, await i18n.generate_translation(req.lang))
    i18n.save_cache(req.lang, translated)
    log.info("[i18n] generated translation for lang=%r (%d strings)", req.lang, len(translated))
    return i18n.public_catalog(translated)
