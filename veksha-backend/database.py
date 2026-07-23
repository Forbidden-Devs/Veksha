"""Small synchronous PostgreSQL access layer shared by durable stores."""
from __future__ import annotations

import atexit
from contextlib import AbstractContextManager
import sys
import threading
from typing import Any

from psycopg import Connection
from psycopg.rows import tuple_row
from psycopg_pool import ConnectionPool

from config import DATABASE_POOL_MAX_SIZE, DATABASE_POOL_MIN_SIZE, DATABASE_URL

_pool: ConnectionPool[Connection[Any]] | None = None


def _get_pool() -> ConnectionPool[Connection[Any]]:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is required (for example "
                "postgresql://veksha:veksha@localhost:5432/veksha)"
            )
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=DATABASE_POOL_MIN_SIZE,
            max_size=DATABASE_POOL_MAX_SIZE,
            kwargs={"autocommit": True, "row_factory": tuple_row},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


atexit.register(close_pool)


class _Result:
    """Keep a pooled connection checked out until its result is consumed."""

    def __init__(self, lease: AbstractContextManager, cursor: Any) -> None:
        self._lease = lease
        self._cursor = cursor
        self.rowcount = cursor.rowcount
        if cursor.description is None:
            self.close()

    def fetchone(self) -> Any:
        try:
            return self._cursor.fetchone()
        finally:
            self.close()

    def fetchall(self) -> list[Any]:
        try:
            return self._cursor.fetchall()
        finally:
            self.close()

    def close(self) -> None:
        lease = getattr(self, "_lease", None)
        if lease is not None:
            self._lease = None
            self._cursor.close()
            lease.__exit__(None, None, None)

    def __del__(self) -> None:
        self.close()


class Database:
    """Compact facade used by the synchronous storage functions."""

    def __init__(self) -> None:
        self._local = threading.local()

    def execute(self, query: str, params: Any = None) -> Any:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            return connection.execute(query, params)
        lease = _get_pool().connection()
        connection = lease.__enter__()
        try:
            return _Result(lease, connection.execute(query, params))
        except Exception:
            lease.__exit__(*sys.exc_info())
            raise

    def executemany(self, query: str, params_seq: Any) -> Any:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            cursor = connection.cursor()
            cursor.executemany(query, params_seq)
            return cursor
        with _get_pool().connection() as connection:
            with connection.transaction():
                cursor = connection.cursor()
                cursor.executemany(query, params_seq)
                return cursor

    def __enter__(self) -> "Database":
        if getattr(self._local, "connection", None) is not None:
            raise RuntimeError("nested database transactions are not supported")
        self._local.lease = _get_pool().connection()
        self._local.connection = self._local.lease.__enter__()
        self._local.transaction = self._local.connection.transaction()
        self._local.transaction.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        transaction = self._local.transaction
        lease = self._local.lease
        try:
            transaction.__exit__(exc_type, exc, tb)
        finally:
            lease.__exit__(exc_type, exc, tb)
            self._local.transaction = None
            self._local.lease = None
            self._local.connection = None


database = Database()
