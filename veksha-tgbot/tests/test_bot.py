"""Small, network-free checks for the Telegram companion bot."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot  # noqa: E402


def _sender(language_code: str):
    return SimpleNamespace(from_user=SimpleNamespace(language_code=language_code))


def test_translations_follow_telegram_language():
    assert "Choose the features" in bot.t(_sender("en-US"), "plans_title")
    assert "Выберите нужные функции" in bot.t(_sender("ru-RU"), "plans_title")


def test_unknown_language_falls_back_to_english():
    assert bot.t(_sender("de-DE"), "backend_down") == bot.STRINGS["en"]["backend_down"]


def test_expiry_format_is_stable():
    assert bot.fmt_until(None) == "—"
    assert bot.fmt_until(0) == "—"


def test_config_validation_reports_missing_required_values():
    original = bot.BOT_TOKEN, bot.WEBHOOK_SECRET, bot.BACKEND_URL
    try:
        bot.BOT_TOKEN = ""
        bot.WEBHOOK_SECRET = ""
        bot.BACKEND_URL = "not-a-url"
        errors = bot.config_errors()
        assert len(errors) == 3
    finally:
        bot.BOT_TOKEN, bot.WEBHOOK_SECRET, bot.BACKEND_URL = original


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(
        (name, fn) for name, fn in globals().items() if name.startswith("test_")
    ):
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            import traceback
            print(f"FAIL {name}")
            traceback.print_exc()
    sys.exit(1 if failed else 0)
