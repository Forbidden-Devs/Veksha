"""Health endpoint checks must stay local and avoid all external APIs."""

import asyncio
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


def test_healthcheck_route_is_registered():
    assert any(route.path == "/healthz" for route in main.app.routes)


def test_removed_chat_route_is_not_registered():
    assert all(getattr(route, "path", None) != "/api/message" for route in main.app.routes)


def test_database_console_cors_preflight_allows_database_secret_header():
    response = TestClient(main.app).options(
        "/api/admin/database/query",
        headers={
            "Origin": "http://localhost:4173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "content-type,x-veksha-admin-secret,x-veksha-database-secret"
            ),
        },
    )

    assert response.status_code == 200
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "x-veksha-database-secret" in allowed_headers


def test_healthcheck_reports_running_revision(monkeypatch):
    monkeypatch.setenv("VEKSHA_REVISION", "test-revision")
    result = asyncio.run(main.healthz())
    assert result == {
        "status": "ok",
        "service": "backend",
        "revision": "test-revision",
    }
