import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import localization_catalogs as catalogues


def configure_workspace(monkeypatch, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "ui_locales.json").write_text(
        json.dumps({"schema_version": 1, "required": ["en", "ru"], "beta": []}),
        "utf-8",
    )
    monkeypatch.setattr(catalogues, "SEED_DIR", data)
    monkeypatch.setattr(catalogues, "POLICY_PATH", data / "ui_locales.json")
    monkeypatch.setattr(catalogues, "META_PATH", data / "i18n_source_hashes.json")
    monkeypatch.setattr(catalogues, "DRAFT_DIR", data / "i18n_drafts")
    monkeypatch.setattr(catalogues.i18n, "UI_STRINGS", {"welcome": "Welcome, {name}!"})
    return data


def test_publish_validates_placeholders_and_tracks_source(monkeypatch, tmp_path):
    data = configure_workspace(monkeypatch, tmp_path)
    catalogues.save_draft("ru", {"welcome": "Привет, {name}!"})
    catalogues.publish("ru")

    assert json.loads((data / "i18n_ru.json").read_text("utf-8")) == {
        "welcome": "Привет, {name}!",
    }
    assert catalogues.catalogue_status("ru")["untracked"] == 0


def test_publish_rejects_a_broken_placeholder(monkeypatch, tmp_path):
    configure_workspace(monkeypatch, tmp_path)
    catalogues.save_draft("ru", {"welcome": "Привет!"})
    with pytest.raises(ValueError, match="Placeholder mismatch"):
        catalogues.publish("ru")


def test_changed_source_requires_a_new_draft(monkeypatch, tmp_path):
    data = configure_workspace(monkeypatch, tmp_path)
    catalogues.save_draft("ru", {"welcome": "Привет, {name}!"})
    catalogues.publish("ru")
    monkeypatch.setattr(catalogues.i18n, "UI_STRINGS", {"welcome": "Hello, {name}!"})

    assert catalogues.catalogue_status("ru")["stale"] == 1
    with pytest.raises(ValueError, match="generate a draft"):
        catalogues.publish("ru")
