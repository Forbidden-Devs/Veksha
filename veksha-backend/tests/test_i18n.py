"""
i18n catalogue maintenance tests: same-as-English convergence and the
auto-fill backoff. No LLM calls — translate_strings is stubbed.

Run either way:
    python tests/test_i18n.py
    pytest tests/
"""
import asyncio
import os
import sys
import tempfile

os.environ["VEKSHA_DATA_DIR"] = tempfile.mkdtemp(prefix="veksha-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n  # noqa: E402

KEY = "debug_title"  # arbitrary catalogue key
EN = i18n.UI_STRINGS[KEY]


def _full_catalog(lang: str = "xx") -> dict:
    """A catalogue with every key 'translated' (prefixed), except KEY == English."""
    cat = {k: f"[{lang}] {v}" for k, v in {**i18n.UI_STRINGS, **i18n.BACKEND_STRINGS}.items()}
    cat[KEY] = EN
    return cat


def test_equal_to_english_is_flagged_until_confirmed():
    cached = _full_catalog()
    missing = i18n.untranslated_strings("xx", cached)
    assert list(missing) == [KEY]

    # The LLM returns the English text as the translation — this must be
    # recorded so the key stops being flagged (previously: retried forever).
    merged = i18n.merge_translations(cached, {KEY: EN})
    assert i18n.untranslated_strings("xx", merged) == {}
    assert KEY in merged[i18n._META_SAME_AS_EN]

    # A later real translation clears the marker again.
    merged2 = i18n.merge_translations(merged, {KEY: "Отладка"})
    assert i18n._META_SAME_AS_EN not in merged2
    assert i18n.untranslated_strings("xx", merged2) == {}


def test_public_catalog_strips_meta():
    merged = i18n.merge_translations(_full_catalog(), {KEY: EN})
    public = i18n.public_catalog(merged)
    assert i18n._META_SAME_AS_EN not in public
    assert public[KEY] == EN


def test_ensure_cache_complete_backoff_and_convergence():
    async def run():
        lang = "zz"
        i18n.save_cache(lang, _full_catalog(lang))
        calls = 0

        async def fake_translate(_lang, strings):
            nonlocal calls
            calls += 1
            return {}  # LLM unavailable

        orig = i18n.translate_strings
        i18n.translate_strings = fake_translate
        try:
            i18n._ensure_last_attempt.clear()
            await i18n.ensure_cache_complete(lang)
            await i18n.ensure_cache_complete(lang)  # within backoff window
            assert calls == 1, f"expected 1 attempt, got {calls}"

            # Backoff expired, LLM works now and confirms the English text.
            async def ok_translate(_lang, strings):
                nonlocal calls
                calls += 1
                return {k: v for k, v in strings.items()}

            i18n.translate_strings = ok_translate
            i18n._ensure_last_attempt.clear()
            await i18n.ensure_cache_complete(lang)
            assert calls == 2

            # Converged: no missing keys, no further attempts even without backoff.
            i18n._ensure_last_attempt.clear()
            await i18n.ensure_cache_complete(lang)
            assert calls == 2, f"expected convergence, got extra attempt ({calls})"
        finally:
            i18n.translate_strings = orig

    asyncio.run(run())


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items()):
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError:
            failed += 1
            import traceback
            print(f"FAIL {name}")
            traceback.print_exc()
    sys.exit(1 if failed else 0)
