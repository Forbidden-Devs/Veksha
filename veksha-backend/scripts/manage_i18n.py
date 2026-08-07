#!/usr/bin/env python3
"""Audit, generate and publish static UI catalogues."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import localization_catalogs as catalogues
from learning_core_v2.catalog_translation import CatalogEntry, CatalogTranslationRequest
from learning_core_v2_adapters.runtime import build_catalog_translator


def show_status(as_json: bool) -> int:
    status = catalogues.catalogue_statuses()
    if as_json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(f"UI source: {status['source_keys']} keys")
        for item in status["locales"]:
            marker = "OK" if item["complete"] else "NEEDS WORK"
            print(
                f"{item['locale']:>3} {item['tier']:<8} "
                f"{item['translated']:>3}/{item['total']} "
                f"missing={item['missing']:<3} stale={item['stale']:<3} "
                f"untracked={item['untracked']:<3} {marker}"
            )
    return 0


async def generate(locale: str) -> int:
    pending = catalogues.pending_entries(locale)
    if not pending:
        print(f"{locale}: nothing to generate")
        return 0
    translator = build_catalog_translator()
    items = list(pending.items())
    for start in range(0, len(items), 50):
        batch = items[start:start + 50]
        translated = await translator.execute(CatalogTranslationRequest(
            entries=tuple(CatalogEntry(key, source) for key, source in batch),
            target_language=locale,
        ))
        if len(translated) != len(batch):
            missing = sorted(set(dict(batch)) - set(translated))
            raise RuntimeError(f"Provider omitted {len(missing)} key(s): {', '.join(missing)}")
        path = catalogues.save_draft(locale, translated)
        print(f"{locale}: generated {min(start + len(batch), len(items))}/{len(items)} -> {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("--json", action="store_true")
    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("locale")
    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("locale")
    subparsers.add_parser("check")
    args = parser.parse_args()

    if args.command == "status":
        return show_status(args.json)
    if args.command == "generate":
        return asyncio.run(generate(args.locale))
    if args.command == "publish":
        print(catalogues.publish(args.locale))
        return 0
    if args.command == "check":
        show_status(False)
        return 0 if catalogues.required_catalogues_are_ready() else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
