import asyncio
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import db
from api import admin


ADMIN_SECRET = "test-admin-secret"
DATABASE_SECRET = "test-database-secret"


def _query(sql: str, database_secret: str = DATABASE_SECRET):
    return asyncio.run(admin.api_admin_database_query(
        admin.DatabaseQueryRequest(sql=sql),
        x_veksha_admin_secret=ADMIN_SECRET,
        x_veksha_database_secret=database_secret,
    ))


def test_database_console_requires_separate_secret():
    with pytest.raises(HTTPException) as caught:
        _query("SELECT 1", database_secret="wrong")
    assert caught.value.status_code == 401


def test_database_console_rejects_mutating_and_multiple_statements():
    for sql in ("DELETE FROM users", "SELECT 1; SELECT 2"):
        with pytest.raises(HTTPException) as caught:
            _query(sql)
        assert caught.value.status_code == 400


def test_database_console_executes_bounded_select_and_serializes_values():
    result = _query("SELECT 42 AS answer, NULL AS nothing, ARRAY[1,2] AS items")
    assert result.columns == ["answer", "nothing", "items"]
    assert result.rows == [[42, None, [1, 2]]]
    assert result.row_count == 1
    assert result.truncated is False
    assert result.duration_ms >= 0


def test_database_console_transaction_is_read_only():
    original = db.feature_prices_get()
    with pytest.raises(HTTPException) as caught:
        _query(
            "WITH changed AS (UPDATE feature_prices SET stars_monthly=1 RETURNING *) "
            "SELECT * FROM changed"
        )
    assert caught.value.status_code == 400
    assert db.feature_prices_get() == original


def test_database_secret_must_differ_from_admin_secret(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_DATABASE_SECRET", config.ADMIN_API_SECRET)
    with pytest.raises(HTTPException) as caught:
        _query("SELECT 1", database_secret=config.ADMIN_API_SECRET)
    assert caught.value.status_code == 503
