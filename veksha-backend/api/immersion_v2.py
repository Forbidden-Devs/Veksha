"""HTTP adapter for independently rewritten comprehensible-input analysis."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.immersion_contract import (
    ImmersionBlock,
    ImmersionRequest,
    ImmersionResponse,
    ImmersionSentence,
)
from auth import CurrentUser
from cefr import level_to_cefr
from entitlements import require_feature
from learning_core_v2.immersion import ImmersionContext
from learning_core_v2_adapters.runtime import build_immersion_analyzer
from storage import get_storage


router = APIRouter()


@router.post(
    "/api/immersion/analyze",
    response_model=ImmersionResponse,
    dependencies=[Depends(require_feature("immersion"))],
)
async def api_immersion_analyze(
    req: ImmersionRequest, username: CurrentUser
) -> ImmersionResponse:
    settings = get_storage(username).settings
    context = ImmersionContext(
        native_language=settings.native_lang or "en",
        learning_language=settings.target_lang or "en",
        learner_cefr=level_to_cefr(settings.english_level),
    )
    result = await build_immersion_analyzer().execute(req.blocks, context)
    return ImmersionResponse(
        blocks=[
            ImmersionBlock(
                sentences=[
                    ImmersionSentence(
                        text=sentence.text,
                        cefr=sentence.cefr,
                        translation=sentence.translation,
                    )
                    for sentence in block.sentences
                ]
            )
            for block in result
        ]
    )
