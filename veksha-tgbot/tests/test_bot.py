"""Small, network-free checks for the Telegram companion bot."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot  # noqa: E402


def _sender(language_code: str):
    return SimpleNamespace(from_user=SimpleNamespace(language_code=language_code))


def test_translations_follow_telegram_language():
    assert "Choose a plan" in bot.t(_sender("en-US"), "plans_title")
    assert "Выберите план" in bot.t(_sender("ru-RU"), "plans_title")


def test_unknown_language_falls_back_to_english():
    assert bot.t(_sender("de-DE"), "backend_down") == bot.STRINGS["en"]["backend_down"]


def test_expiry_format_is_stable():
    assert bot.fmt_until(None) == "—"
    assert bot.fmt_until(0) == "—"
