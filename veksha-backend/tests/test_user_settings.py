from models import UserSettings


def test_onboarding_requires_two_distinct_languages() -> None:
    assert UserSettings(native_lang="ru", target_lang="en").is_onboarded()
    assert not UserSettings(native_lang="", target_lang="en").is_onboarded()
    assert not UserSettings(native_lang="en", target_lang="en").is_onboarded()
