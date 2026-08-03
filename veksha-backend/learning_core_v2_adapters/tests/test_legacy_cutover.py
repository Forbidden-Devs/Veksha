import ast
import re
from pathlib import Path


BACKEND = Path(__file__).parents[2]


def test_main_composes_only_rewritten_learning_routers():
    tree = ast.parse((BACKEND / "main.py").read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "api"
        for alias in node.names
    }

    assert {"translate_v2", "training_v2", "lesson_v2", "reading_coach"} <= imports
    assert not {"translate", "training", "lesson", "immersion", "ci_meter"} & imports


def test_migration_flags_and_legacy_entrypoints_are_gone():
    sources = [
        BACKEND / "main.py",
        BACKEND / "api" / "settings.py",
        BACKEND / "api" / "translate_v2.py",
        BACKEND / "learning_core_v2_adapters" / "runtime.py",
    ]
    assert all(
        re.search(r"VEKSHA_CORE_V2_[A-Z_]+_ENABLED", path.read_text(encoding="utf-8"))
        is None
        for path in sources
    )

    removed = [
        "api/translate.py",
        "api/training.py",
        "api/lesson.py",
        "api/immersion.py",
        "api/immersion_v2.py",
        "api/immersion_contract.py",
        "api/ci_meter.py",
        "selection.py",
        "training.py",
        "lesson.py",
        "local_translate.py",
        "translation_cache.py",
        "db_cache.py",
        "llm/_base.py",
        "llm/grammar_lens.py",
        "llm/subtitles.py",
    ]
    assert all(not (BACKEND / relative).exists() for relative in removed)


def test_lexical_item_v2_has_no_legacy_word_projection():
    models_tree = ast.parse((BACKEND / "models.py").read_text(encoding="utf-8"))
    class_names = {
        node.name for node in ast.walk(models_tree) if isinstance(node, ast.ClassDef)
    }
    assert "Word" not in class_names

    production = [
        BACKEND / "storage.py",
        BACKEND / "api" / "training_v2.py",
        BACKEND / "learning_core_v2_adapters" / "practice.py",
    ]
    assert all("PracticeWord" not in path.read_text(encoding="utf-8") for path in production)
