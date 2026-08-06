import os
from urllib.parse import urlsplit

import pytest
from psycopg import Error as PsycopgError
from psycopg import connect

TEST_DATABASE_URL = os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://veksha:veksha@localhost:55432/veksha_test",
)
os.environ.setdefault("ADMIN_DATABASE_SECRET", "test-database-secret")
os.environ.setdefault("ADMIN_API_SECRET", "test-admin-secret")
os.environ.setdefault("TELEGRAM_BOT_USERNAME", "veksha_test_bot")
os.environ.setdefault("TELEGRAM_BOT_WEBHOOK_SECRET", "test-secret")


@pytest.fixture(scope="session", autouse=True)
def clean_database():
    database_name = urlsplit(TEST_DATABASE_URL).path.removeprefix("/")
    if not database_name.endswith("_test"):
        pytest.exit(
            f"Refusing to erase non-test database {database_name!r}; "
            "DATABASE_URL must name a database ending in '_test'."
        )
    try:
        with connect(TEST_DATABASE_URL, connect_timeout=3):
            pass
    except PsycopgError as error:
        pytest.exit(
            "Test PostgreSQL is unavailable. From the repository root run "
            "`docker compose --profile test up -d --wait postgres-test`, "
            f"then retry. PostgreSQL reported: {error}"
        )

    import db

    db.purge_all_users()
    with db._conn() as connection:
        connection.execute("DELETE FROM billing_checkouts")
        connection.execute(
            "UPDATE feature_prices SET stars_monthly = CASE feature "
            "WHEN 'pattern_workshop' THEN 40 WHEN 'reading_coach' THEN 35 "
            "WHEN 'dual_subtitles' THEN 25 ELSE stars_monthly END"
        )
    yield
