"""Safe translation of application catalogue strings."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol


_PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    key: str
    source: str


@dataclass(frozen=True, slots=True)
class CatalogTranslationRequest:
    entries: tuple[CatalogEntry, ...]
    target_language: str


@dataclass(frozen=True, slots=True)
class CatalogTranslationDraft:
    key: str
    value: str


class CatalogTranslationProvider(Protocol):
    async def translate_catalog(
        self, request: CatalogTranslationRequest
    ) -> tuple[CatalogTranslationDraft, ...]: ...


class TranslateCatalog:
    def __init__(self, provider: CatalogTranslationProvider) -> None:
        self._provider = provider

    async def execute(self, request: CatalogTranslationRequest) -> dict[str, str]:
        if not request.entries:
            return {}
        if len(request.entries) > 50:
            raise ValueError("catalog translation batch is too large")
        target = request.target_language.strip().lower().replace("_", "-")
        if not 2 <= len(target) <= 35:
            raise ValueError("catalog target language is invalid")
        sources: dict[str, str] = {}
        for entry in request.entries:
            key = entry.key.strip()
            if not key or key in sources:
                raise ValueError("catalog keys must be non-empty and unique")
            if not entry.source.strip():
                raise ValueError("catalog source strings must not be empty")
            sources[key] = entry.source

        normalized = CatalogTranslationRequest(
            tuple(CatalogEntry(key, value) for key, value in sources.items()), target
        )
        drafts = await self._provider.translate_catalog(normalized)
        result: dict[str, str] = {}
        for draft in drafts:
            source = sources.get(draft.key)
            value = draft.value.strip()
            if source is None or draft.key in result or not value:
                continue
            if Counter(_PLACEHOLDER.findall(source)) != Counter(
                _PLACEHOLDER.findall(value)
            ):
                continue
            if len(value) > max(500, len(source) * 6):
                continue
            result[draft.key] = value
        return result
