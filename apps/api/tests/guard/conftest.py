"""Shared fixtures for tests/guard."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest


@pytest.fixture
def stub_audit_chain():
    """Stub the DB-touching chain helpers for tests that drive finalize() with a mock session.

    The real helpers are covered against PostgreSQL in test_gateway_audit_chain_postgres.py.
    """
    with patch("app.modules.guard.models.chain_begin",
               return_value=(datetime.now(timezone.utc), "prev")) as begin, \
            patch("app.modules.guard.models.chain_seal_stored_row", return_value="hash") as seal:
        yield begin, seal
