import os

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://veksha:veksha@localhost:5432/veksha",
)
os.environ.setdefault("ADMIN_DATABASE_SECRET", "test-database-secret")
os.environ.setdefault("ADMIN_API_SECRET", "test-admin-secret")
os.environ.setdefault("TELEGRAM_BOT_USERNAME", "veksha_test_bot")
os.environ.setdefault("TELEGRAM_BOT_WEBHOOK_SECRET", "test-secret")


@pytest.fixture(scope="session", autouse=True)
def clean_database():
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
