import asyncio
import os
import sys

os.environ.setdefault("TELEGRAM_BOT_USERNAME", "veksha_test_bot")
os.environ.setdefault("TELEGRAM_BOT_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("ADMIN_API_SECRET", "test-admin-secret")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from llm import _base
from usage_context import set_usage_user


def _user(name: str) -> str:
    assert db.create_user(name)
    return name


def test_ai_usage_aggregates_by_user_and_period():
    first = _user("ai_usage_first")
    second = _user("ai_usage_second")
    db.ai_usage_record(first, "translate_selection", "gpt-test", 100, 20, 120, 30, 5)
    db.ai_usage_record(first, "translate_selection", "gpt-test", 50, 10, 60)
    db.ai_usage_record(second, "grammar_lens", "gpt-smart", 200, 80, 280)

    stats = db.ai_usage_stats()
    assert stats["all_time"]["requests"] >= 3
    assert stats["period"]["total_tokens"] >= 460
    users = {row["username"]: row for row in stats["users"]}
    assert users[first]["requests"] == 2
    assert users[first]["total_tokens"] == 180
    assert users[first]["cached_tokens"] == 30
    assert users[second]["total_tokens"] == 280
    operations = {(row["call_name"], row["model"]): row for row in stats["operations"]}
    assert operations[("translate_selection", "gpt-test")]["requests"] == 2
    assert len(stats["daily"]) == 30


def test_base_call_records_provider_usage(monkeypatch):
    username = _user("ai_usage_base_call")
    set_usage_user(username)
    recorded = []

    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def raise_for_status(self):
            return None

        async def json(self):
            return {
                "choices": [{"message": {"content": " done "}}],
                "usage": {
                    "prompt_tokens": 15,
                    "completion_tokens": 7,
                    "total_tokens": 22,
                    "prompt_tokens_details": {"cached_tokens": 4},
                    "completion_tokens_details": {"reasoning_tokens": 2},
                },
            }

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(_base.aiohttp, "ClientSession", FakeSession)
    monkeypatch.setattr(_base, "_headers", lambda: {})
    monkeypatch.setattr(_base.db, "ai_usage_record", lambda **kwargs: recorded.append(kwargs))

    result = asyncio.run(_base._call("system", "user", call_name="test_call", model="gpt-test"))
    assert result == "done"
    assert recorded == [{
        "username": username,
        "call_name": "test_call",
        "model": "gpt-test",
        "prompt_tokens": 15,
        "completion_tokens": 7,
        "total_tokens": 22,
        "cached_tokens": 4,
        "reasoning_tokens": 2,
    }]
