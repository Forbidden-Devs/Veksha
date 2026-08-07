"""Language ordering and active-language persistence tests."""
import asyncio
import os
import sys
import tempfile

os.environ["VEKSHA_DATA_DIR"] = tempfile.mkdtemp(prefix="veksha-settings-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.auth as auth_api  # noqa: E402
import api.settings as settings_api  # noqa: E402
import api.goal_v2 as goal_api  # noqa: E402
import db  # noqa: E402


def test_active_target_is_persisted_first_for_new_profile():
    account = asyncio.run(auth_api.api_register(
        auth_api.RegisterRequest(display_name="Language learner"),
    ))
    response = asyncio.run(settings_api.api_post_settings(
        settings_api.SettingsRequest(
            display_name="Language learner",
            english_level="a2",
            native_lang="ru",
            target_lang="de",
            target_langs=["de", "en"],
            # Deliberately send the object in the opposite order: the explicit
            # active target and target_langs must define the persisted order.
            language_settings={
                "en": {"level": "b1", "goals": "English", "prompt": ""},
                "de": {"level": "a2", "goals": "German", "prompt": ""},
            },
        ),
        account.username,
    ))

    assert response.target_lang == "de"
    assert response.target_langs == ["de", "en"]
    stored = db.settings_get(account.username)
    assert stored is not None
    assert stored["target_lang"] == "de"
    assert list(stored["language_settings"]) == ["de", "en"]
    assert response.writing_system is not None
    assert response.writing_system.kind == "new_alphabet"
    assert stored["language_settings"]["de"]["literacy_stage"] == "not_started"

    goal = asyncio.run(goal_api.api_create_goal(
        goal_api.CreateGoalRequest(
            statement="Learn to read German using the Latin alphabet",
            kind="alphabet",
        ),
        account.username,
    ))
    assert goal.kind == "alphabet"
    stored = db.settings_get(account.username)
    assert stored is not None
    assert stored["language_settings"]["de"]["literacy_stage"] == "learning"
