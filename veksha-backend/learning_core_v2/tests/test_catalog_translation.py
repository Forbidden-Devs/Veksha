import pytest

from learning_core_v2.catalog_translation import (
    CatalogEntry,
    CatalogTranslationDraft,
    CatalogTranslationRequest,
    TranslateCatalog,
)


pytestmark = pytest.mark.asyncio


class Provider:
    def __init__(self, drafts):
        self.drafts = drafts
        self.request = None

    async def translate_catalog(self, request):
        self.request = request
        return self.drafts


async def test_accepts_only_requested_keys_and_preserved_placeholders():
    provider = Provider(
        (
            CatalogTranslationDraft("welcome", "Привет, {name}!"),
            CatalogTranslationDraft("count", "Всего элементов"),
            CatalogTranslationDraft("unknown", "Лишнее"),
        )
    )

    result = await TranslateCatalog(provider).execute(
        CatalogTranslationRequest(
            (
                CatalogEntry("welcome", "Hello, {name}!"),
                CatalogEntry("count", "{n} items"),
            ),
            "RU",
        )
    )

    assert result == {"welcome": "Привет, {name}!"}
    assert provider.request.target_language == "ru"


async def test_empty_batch_skips_provider():
    provider = Provider(())

    result = await TranslateCatalog(provider).execute(
        CatalogTranslationRequest((), "ru")
    )

    assert result == {}
    assert provider.request is None


async def test_rejects_duplicate_keys():
    provider = Provider(())

    with pytest.raises(ValueError):
        await TranslateCatalog(provider).execute(
            CatalogTranslationRequest(
                (CatalogEntry("same", "One"), CatalogEntry("same", "Two")), "ru"
            )
        )
