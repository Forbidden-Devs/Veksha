import os

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://veksha:veksha@localhost:5432/veksha",
)


@pytest.fixture(scope="session", autouse=True)
def clean_database():
    import db

    db.purge_all_users()
    with db._conn() as connection:
        connection.execute("DELETE FROM billing_checkouts")
        connection.execute(
            "UPDATE feature_prices SET stars_monthly = CASE feature "
            "WHEN 'grammar_lens' THEN 40 WHEN 'immersion' THEN 35 "
            "WHEN 'dual_subtitles' THEN 25 ELSE stars_monthly END"
        )
    yield
