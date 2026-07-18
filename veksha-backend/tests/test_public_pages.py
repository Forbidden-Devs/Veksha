"""Smoke tests for the public OAuth branding and legal pages."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import privacy  # noqa: E402


def test_homepage_has_branding_links():
    page = asyncio.run(privacy.homepage())
    assert "<h1>Veksha</h1>" in page
    assert 'href="/privacy"' in page
    assert 'href="/terms"' in page
    assert "Google sign-in" in page


def test_privacy_has_public_contact():
    page = asyncio.run(privacy.privacy_policy())
    assert "Veksha Privacy Policy" in page
    assert "danfromomsk@gmail.com" in page


def test_terms_cover_accounts_and_ai():
    page = asyncio.run(privacy.terms_of_service())
    assert "Veksha Terms of Service" in page
    assert "AI-generated information" in page
    assert "another browser or device" in page


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
