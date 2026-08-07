#!/usr/bin/env python3
"""Copy an existing Veksha SQLite installation into DATABASE_URL.

The import is idempotent: rows with the same primary key are updated. Run it
while the backend is stopped so that SQLite doesn't change during the copy.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MAIN_TABLES = (
    "users",
    "kb",
    "identities",
    "google_oauth_flows",
    "review_log",
    "user_settings",
    "user_languages",
    "reading_sessions",
    "reading_session_words",
    "subscriptions",
    "telegram_links",
    "telegram_link_codes",
    "star_payments",
    "promo_codes",
    "promo_redemptions",
    "feature_prices",
    "billing_checkouts",
)


def _table_exists(source: sqlite3.Connection, table: str) -> bool:
    return source.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _copy_table(source: sqlite3.Connection, destination, table: str) -> int:
    if not _table_exists(source, table):
        return 0
    info = source.execute(f'PRAGMA table_info("{table}")').fetchall()
    destination_columns = {
        row[0]
        for row in destination.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s",
            (table,),
        ).fetchall()
    }
    columns = [row[1] for row in info if row[1] in destination_columns]
    if not columns:
        return 0
    primary_key = [
        column
        for _, column in sorted(
            (row[5], row[1])
            for row in info
            if row[5] and row[1] in destination_columns
        )
    ]
    source_columns = ", ".join(f'"{column}"' for column in columns)
    rows = source.execute(f'SELECT {source_columns} FROM "{table}"').fetchall()
    if not rows:
        return 0

    assignments = [
        sql.SQL("{} = excluded.{}").format(sql.Identifier(column), sql.Identifier(column))
        for column in columns
        if column not in primary_key
    ]
    conflict = sql.SQL(" DO NOTHING")
    if primary_key and assignments:
        conflict = sql.SQL(" ({}) DO UPDATE SET {}").format(
            sql.SQL(", ").join(map(sql.Identifier, primary_key)),
            sql.SQL(", ").join(assignments),
        )
    elif primary_key:
        conflict = sql.SQL(" ({}) DO NOTHING").format(
            sql.SQL(", ").join(map(sql.Identifier, primary_key))
        )

    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT{}").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        conflict,
    )
    destination.executemany(statement, rows)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.getenv("VEKSHA_DATA_DIR", Path(__file__).resolve().parents[1] / "data")),
    )
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL"):
        parser.error("DATABASE_URL must point at the destination PostgreSQL database")

    import db

    db.healthcheck()

    sources = (
        (args.data_dir / "veksha.db", MAIN_TABLES),
    )
    copied = 0
    with db.database as destination:
        for path, tables in sources:
            if not path.exists():
                print(f"skip missing {path}")
                continue
            with sqlite3.connect(path) as source:
                for table in tables:
                    count = _copy_table(source, destination, table)
                    copied += count
                    print(f"{table}: {count}")

        for table in ("review_log", "star_payments"):
            destination.execute(
                sql.SQL(
                    "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                    "COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {}"
                ).format(sql.Identifier(table)),
                (table,),
            )

    print(f"copied {copied} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
