"""Stable HTTP payloads shared by both immersion implementations."""

from pydantic import BaseModel, Field


class ImmersionRequest(BaseModel):
    blocks: list[str] = Field(default_factory=list)


class ImmersionSentence(BaseModel):
    text: str
    cefr: str = ""
    translation: str = ""


class ImmersionBlock(BaseModel):
    sentences: list[ImmersionSentence] = Field(default_factory=list)


class ImmersionResponse(BaseModel):
    blocks: list[ImmersionBlock]
