"""Versioned lifecycle for reviewed UI localization catalogues."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import i18n


ROOT = Path(__file__).resolve().parent
SEED_DIR = ROOT / "data"
POLICY_PATH = SEED_DIR / "ui_locales.json"
META_PATH = SEED_DIR / "i18n_source_hashes.json"
DRAFT_DIR = SEED_DIR / "i18n_drafts"
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
LOCALE_CODE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]+)*$")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def policy() -> dict[str, Any]:
    raw = _read_json(POLICY_PATH, {})
    return {
        "schema_version": int(raw.get("schema_version", 1)),
        "required": tuple(dict.fromkeys(raw.get("required", ("en", "ru")))),
        "beta": tuple(dict.fromkeys(raw.get("beta", ()))),
    }


def validate_locale(locale: str) -> str:
    normalized = locale.strip().lower().replace("_", "-")
    rules = policy()
    known = {*rules["required"], *rules["beta"]}
    if not LOCALE_CODE.fullmatch(normalized) or normalized not in known:
        raise ValueError(f"Unknown UI locale: {locale}")
    return normalized


def _catalog_path(locale: str) -> Path:
    return SEED_DIR / f"i18n_{locale}.json"


def _draft_path(locale: str) -> Path:
    return DRAFT_DIR / f"i18n_{locale}.json"


def _published(locale: str) -> dict[str, str]:
    if locale == "en":
        return dict(i18n.UI_STRINGS)
    return _read_json(_catalog_path(locale), {})


def _candidate(locale: str) -> dict[str, str]:
    return _read_json(_draft_path(locale), _published(locale))


def _metadata() -> dict[str, dict[str, str]]:
    raw = _read_json(META_PATH, {})
    return raw if isinstance(raw, dict) else {}


def catalogue_status(locale: str) -> dict[str, Any]:
    rules = policy()
    tier = "required" if locale in rules["required"] else "beta"
    source = i18n.UI_STRINGS
    translated = _published(locale)
    tracked = _metadata().get(locale, {})
    missing = [key for key in source if not str(translated.get(key, "")).strip()]
    stale = [
        key for key in source
        if key in translated and key in tracked and tracked[key] != source_hash(source[key])
    ]
    untracked = [key for key in source if key in translated and key not in tracked]
    if locale == "en":
        missing, stale, untracked = [], [], []
    return {
        "locale": locale,
        "tier": tier,
        "total": len(source),
        "translated": len(source) - len(missing),
        "missing": len(missing),
        "stale": len(stale),
        "untracked": len(untracked),
        "complete": not missing and not stale and not untracked,
    }


def catalogue_statuses() -> dict[str, Any]:
    rules = policy()
    locales = tuple(dict.fromkeys((*rules["required"], *rules["beta"])))
    return {
        "schema_version": rules["schema_version"],
        "source_keys": len(i18n.UI_STRINGS),
        "locales": [catalogue_status(locale) for locale in locales],
    }


def pending_entries(locale: str) -> dict[str, str]:
    locale = validate_locale(locale)
    source = i18n.UI_STRINGS
    candidate = _candidate(locale)
    tracked = _metadata().get(locale, {})
    return {
        key: text for key, text in source.items()
        if not str(candidate.get(key, "")).strip()
        or (key in tracked and tracked[key] != source_hash(text))
    }


def save_draft(locale: str, translations: dict[str, str]) -> Path:
    locale = validate_locale(locale)
    unknown = set(translations) - set(i18n.UI_STRINGS)
    if unknown:
        raise ValueError(f"Unknown catalogue keys: {', '.join(sorted(unknown))}")
    candidate = _candidate(locale)
    candidate.update(translations)
    ordered = {key: candidate[key] for key in i18n.UI_STRINGS if key in candidate}
    _atomic_json(_draft_path(locale), ordered)
    return _draft_path(locale)


def publish(locale: str) -> Path:
    locale = validate_locale(locale)
    if locale == "en":
        raise ValueError("English is the source catalogue and cannot be published")
    if not _draft_path(locale).exists() and pending_entries(locale):
        raise ValueError("Catalogue has changed source strings; generate a draft before publishing")
    candidate = _candidate(locale)
    missing = [key for key in i18n.UI_STRINGS if not str(candidate.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Catalogue is incomplete: {len(missing)} key(s) missing")
    for key, source in i18n.UI_STRINGS.items():
        if Counter(PLACEHOLDER.findall(source)) != Counter(PLACEHOLDER.findall(candidate[key])):
            raise ValueError(f"Placeholder mismatch for {key}")
    ordered = {key: candidate[key] for key in i18n.UI_STRINGS}
    _atomic_json(_catalog_path(locale), ordered)
    metadata = _metadata()
    metadata[locale] = {key: source_hash(text) for key, text in i18n.UI_STRINGS.items()}
    _atomic_json(META_PATH, metadata)
    _draft_path(locale).unlink(missing_ok=True)
    return _catalog_path(locale)


def required_catalogues_are_ready() -> bool:
    return all(item["complete"] for item in catalogue_statuses()["locales"] if item["tier"] == "required")
