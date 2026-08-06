import os
import sys

os.environ.setdefault("TELEGRAM_BOT_USERNAME", "veksha_test_bot")
os.environ.setdefault("TELEGRAM_BOT_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("ADMIN_API_SECRET", "test-admin-secret")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from learning_core_v2_adapters import runtime
from usage_context import set_usage_user


def _user(name: str) -> str:
    assert db.create_user(name)
    return name


def test_ai_usage_aggregates_by_user_and_period():
    first = _user("ai_usage_first")
    second = _user("ai_usage_second")
    db.ai_usage_record(first, "translate_selection", "gpt-test", 100, 20, 120, 30, 5)
    db.ai_usage_record(first, "translate_selection", "gpt-test", 50, 10, 60)
    db.ai_usage_record(second, "pattern_workshop", "gpt-smart", 200, 80, 280)

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


def test_core_provider_usage_records_by_active_user(monkeypatch):
    username = _user("ai_usage_base_call")
    set_usage_user(username)
    recorded = []
    monkeypatch.setattr(
        runtime.db, "ai_usage_record", lambda **kwargs: recorded.append(kwargs)
    )

    runtime._record_usage(
        "test_call",
        "gpt-test",
        {
            "input_tokens": 15,
            "output_tokens": 7,
            "total_tokens": 22,
            "input_tokens_details": {"cached_tokens": 4},
            "output_tokens_details": {"reasoning_tokens": 2},
        },
    )
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


def test_speech_usage_records_platform_units_by_user():
    username = _user("speech_usage_user")
    db.speech_usage_record(
        username=username,
        operation="tts",
        request_id="req_speech_test",
        provider="elevenlabs",
        model="eleven_flash_v2_5",
        characters=12,
        audio_bytes=3456,
        provider_request_id="provider_req_test",
    )

    row = db._conn().execute(
        "SELECT username, operation, request_id, provider, model, characters, "
        "audio_bytes, provider_request_id FROM speech_usage WHERE request_id=%s",
        ("req_speech_test",),
    ).fetchone()
    assert row == (
        username,
        "tts",
        "req_speech_test",
        "elevenlabs",
        "eleven_flash_v2_5",
        12,
        3456,
        "provider_req_test",
    )
