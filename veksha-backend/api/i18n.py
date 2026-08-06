"""Read-only access to reviewed static catalogues."""
from fastapi import APIRouter

import i18n

router = APIRouter()


@router.get("/api/i18n/{lang}")
async def api_get_i18n(lang: str) -> dict[str, str]:
    return i18n.load_catalog(lang)
