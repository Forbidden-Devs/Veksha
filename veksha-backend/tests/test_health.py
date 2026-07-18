"""Health endpoint checks must stay local and avoid all external APIs."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


def test_healthcheck_route_is_registered():
    assert any(route.path == "/healthz" for route in main.app.routes)


def test_healthcheck_reports_running_revision(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "test-revision")
    result = asyncio.run(main.healthz())
    assert result == {
        "status": "ok",
        "service": "backend",
        "revision": "test-revision",
    }
