from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException

from api import reading_sessions as api


@dataclass
class Settings:
    target_lang: str = "en"


@dataclass
class Lexicon:
    items: list = field(default_factory=list)

    def all(self):
        return tuple(self.items)


@dataclass
class Storage:
    settings: Settings = field(default_factory=Settings)
    lexicon: Lexicon = field(default_factory=Lexicon)


@pytest.mark.asyncio
async def test_start_creates_an_explicit_session(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "get_storage", lambda _username: Storage())
    monkeypatch.setattr(api.db, "reading_session_start", lambda *args: calls.append(args))

    result = await api.start_reading_session(
        api.StartRequest(source_url="https://example.test/article"),
        "tester",
    )

    assert result.session_id
    assert calls[0][1:4] == ("tester", "en", "https://example.test/article")


@pytest.mark.asyncio
async def test_observation_requires_the_active_session(monkeypatch):
    monkeypatch.setattr(api, "get_storage", lambda _username: Storage())
    monkeypatch.setattr(api.db, "reading_session_observe", lambda *_args: False)

    with pytest.raises(HTTPException) as error:
        await api.observe_reading_session(
            api.ObserveRequest(session_id="closed", text="A deliberately selected difficult passage", domain="example.test"),
            "tester",
        )

    assert error.value.status_code == 409
