import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from writing_systems import writing_system_profile


def test_new_alphabet_starts_with_transcription_and_an_alphabet_course():
    profile = writing_system_profile("en", "ru", "a1", "")

    assert profile.kind == "new_alphabet"
    assert profile.script == "cyrl"
    assert profile.literacy_stage == "not_started"
    assert profile.transcription_mode == "always"
    assert profile.course_available


def test_completed_alphabet_course_keeps_transcription_available_on_demand():
    profile = writing_system_profile("en", "el", "a1", "mastered")

    assert profile.kind == "new_alphabet"
    assert profile.transcription_mode == "on_demand"


def test_latin_diacritics_use_a_smaller_early_level_route():
    beginner = writing_system_profile("en", "vi", "a2", "")
    advanced = writing_system_profile("en", "vi", "b1", "")

    assert beginner.kind == "latin_extended"
    assert beginner.literacy_stage == "learning"
    assert beginner.transcription_mode == "always"
    assert advanced.transcription_mode == "on_demand"


def test_same_script_with_language_specific_letters_gets_a_small_route():
    profile = writing_system_profile("ru", "uk", "a1", "")

    assert profile.kind == "script_variant"
    assert profile.transcription_mode == "always"
    assert profile.course_available


def test_logographic_and_mixed_systems_remain_outside_the_shared_scheme():
    for language in ("zh", "ja"):
        profile = writing_system_profile("en", language, "a1", "")
        assert profile.kind == "unsupported"
        assert not profile.course_available
