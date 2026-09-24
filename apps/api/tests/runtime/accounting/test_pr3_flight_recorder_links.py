"""PR 3 self-checks — Flight Recorder deep-link contract.

Owned by #2209; #2069 will subscribe when it ships. Pin the URL scheme,
the blank-URL fallback, and the trailing-slash normalization so this
side of the contract stays stable across future edits.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import settings
from app.runtime.accounting import (
    flight_recorder_attempt_url,
    flight_recorder_enabled,
    flight_recorder_request_url,
)


# ─── Disabled by default (blank base URL) ──────────────────────────────


def test_flight_recorder_disabled_when_base_url_blank(monkeypatch):
    monkeypatch.setattr(settings, "flight_recorder_base_url", "")
    assert flight_recorder_enabled() is False
    assert flight_recorder_request_url(uuid.uuid4()) is None
    assert flight_recorder_attempt_url(uuid.uuid4(), 0) is None


def test_flight_recorder_disabled_when_base_url_only_whitespace(monkeypatch):
    monkeypatch.setattr(settings, "flight_recorder_base_url", "   ")
    assert flight_recorder_enabled() is False
    assert flight_recorder_request_url(uuid.uuid4()) is None


# ─── URL scheme when enabled ───────────────────────────────────────────


def test_request_url_matches_published_scheme(monkeypatch):
    monkeypatch.setattr(
        settings, "flight_recorder_base_url", "https://flight.conductai.ai"
    )
    req_id = uuid.uuid4()
    assert flight_recorder_request_url(req_id) == (
        f"https://flight.conductai.ai/requests/{req_id}"
    )


def test_attempt_url_matches_published_scheme(monkeypatch):
    monkeypatch.setattr(
        settings, "flight_recorder_base_url", "https://flight.conductai.ai"
    )
    req_id = uuid.uuid4()
    assert flight_recorder_attempt_url(req_id, 2) == (
        f"https://flight.conductai.ai/requests/{req_id}/attempts/2"
    )


def test_attempt_url_handles_ordinal_zero(monkeypatch):
    """Winning attempt's placeholder gets ordinal 0 in the reconciler +
    v1 legacy path. URL must include the explicit '0'."""
    monkeypatch.setattr(
        settings, "flight_recorder_base_url", "https://flight.conductai.ai"
    )
    req_id = uuid.uuid4()
    assert "/attempts/0" in flight_recorder_attempt_url(req_id, 0)


def test_trailing_slash_on_base_url_stripped(monkeypatch):
    """Ops env vars often accumulate trailing slashes; the helper must
    normalize so we don't emit double slashes."""
    monkeypatch.setattr(
        settings, "flight_recorder_base_url", "https://flight.conductai.ai/"
    )
    req_id = uuid.uuid4()
    url = flight_recorder_request_url(req_id)
    assert url is not None
    assert "//requests/" not in url


def test_request_url_accepts_both_uuid_and_string(monkeypatch):
    monkeypatch.setattr(
        settings, "flight_recorder_base_url", "https://flight.conductai.ai"
    )
    req_id = uuid.uuid4()
    assert (
        flight_recorder_request_url(req_id)
        == flight_recorder_request_url(str(req_id))
    )


def test_attempt_ordinal_coerced_to_int(monkeypatch):
    """Callers might pass Session 6H's ordinal from a dict where JSONB
    could round-trip it as float. Coerce so the URL doesn't contain
    '/attempts/2.0'."""
    monkeypatch.setattr(
        settings, "flight_recorder_base_url", "https://flight.conductai.ai"
    )
    req_id = uuid.uuid4()
    assert flight_recorder_attempt_url(req_id, 2.0).endswith("/attempts/2")


# ─── Contract stability pins ──────────────────────────────────────────


def test_module_exports_public_api():
    """Callers import from app.runtime.accounting, not the internal
    module. Pin the top-level re-exports so a future refactor cannot
    silently break Lens's import path."""
    from app.runtime.accounting import (
        flight_recorder_attempt_url as top_a,
        flight_recorder_enabled as top_e,
        flight_recorder_request_url as top_r,
    )
    assert callable(top_a) and callable(top_e) and callable(top_r)


def test_url_scheme_documented_in_module_docstring():
    """The scheme is contract — must be documented in the module
    docstring so future readers see the shape without having to
    reverse-engineer the helper."""
    from app.runtime.accounting import flight_recorder_links

    doc = flight_recorder_links.__doc__ or ""
    assert "{base}/requests/{request_id}" in doc
    assert "{base}/requests/{request_id}/attempts/{attempt_ordinal}" in doc


def test_settings_field_present():
    """Pin the settings field so ops env-var wiring doesn't drift."""
    assert hasattr(settings, "flight_recorder_base_url")
    # Empty by default so nothing changes for existing deploys.
    from app.core.config import Settings

    assert Settings.model_fields["flight_recorder_base_url"].default == ""
