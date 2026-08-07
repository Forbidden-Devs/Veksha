"""Static catalogue contract tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import i18n


def test_english_catalogue_is_the_complete_base():
    assert i18n.load_catalog("en") == {**i18n.UI_STRINGS, **i18n.BACKEND_STRINGS}


def test_static_catalogue_overrides_reviewed_strings_and_falls_back_by_key():
    catalogue = i18n.load_catalog("ru")
    assert catalogue["settings_title"] != i18n.UI_STRINGS["settings_title"]
    assert set(i18n.UI_STRINGS).issubset(catalogue)
    assert set(i18n.BACKEND_STRINGS).issubset(catalogue)


def test_unknown_language_uses_english_without_generation():
    assert i18n.load_catalog("zz") == {**i18n.UI_STRINGS, **i18n.BACKEND_STRINGS}
