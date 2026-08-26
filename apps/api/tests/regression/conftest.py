"""Regression harness shared fixtures.

Piggybacks on the parent tests/conftest.py for env setup (DATABASE_URL,
permissive require_permission shim, etc.). Adds a TestClient fixture that
mounts the real app.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def client() -> TestClient:
    from app.main import app  # noqa: WPS433 — imported after conftest env setup
    return TestClient(app)


def load_fixture(name: str) -> dict:
    """Load a fixture JSON file by name (without extension)."""
    path = FIXTURES_DIR / f"{name}.json"
    return json.loads(path.read_text())
