"""Executable dependency rules for the independently rewritten core."""

from __future__ import annotations

import ast
from pathlib import Path


CORE = Path(__file__).parents[1]
FORBIDDEN_ROOTS = {
    "api",
    "aiohttp",
    "config",
    "database",
    "db",
    "db_cache",
    "fastapi",
    "lesson",
    "llm",
    "local_translate",
    "selection",
    "storage",
    "training",
    "translation_cache",
}


def test_new_core_does_not_import_legacy_or_transport_modules():
    violations: list[str] = []

    for path in CORE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported = [node.module]

            for module in imported:
                if module.split(".", 1)[0] in FORBIDDEN_ROOTS:
                    violations.append(f"{path.relative_to(CORE)}:{node.lineno} imports {module}")

    assert violations == []
