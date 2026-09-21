"""Regression: HTTPException from _execute_v2 must NOT surface as UnboundLocalError.

Root cause (2026-09-21): the ``finally:`` block inside
``handle_gateway_request`` referenced ``_response`` in the settle-actuals
computation, but ``_response`` is only assigned inside the ``try:``
block after ``_execute_v2`` returns. When ``_execute_v2`` raises
(e.g. 502 for all-attempts-failed, 451 for policy block), Python
raises ``UnboundLocalError`` from the finally, masking the real
HTTPException as a generic 500 in the caller's outer handler.

Impact: EVERY 502/451 from a v2 profile with an active reservation
came back as an opaque 500 "internal error". Reproduced live during
vision PR 2 smoke test on Anthropic profile — the real error (URL-
source images rejected by LiteLLM SDK) was hidden by the 500.

Fix: initialise ``_response = None`` before the try, and guard the
finally's ``hasattr`` access with an ``is not None`` check.
"""
from __future__ import annotations

import pytest

# Static-analysis check on the source file itself. A functional test
# would need a full FastAPI + DB scaffold to reproduce the flow;
# grepping the actual source for the guard pattern is a cheap, direct
# proof that the fix is in place. Any refactor that removes the
# initialisation or the ``is not None`` guard will trip this test.


def _handler_source() -> str:
    from pathlib import Path
    import app.modules.guard.gateway_handler as _mod
    return Path(_mod.__file__).read_text()


class TestUnboundResponseGuard:
    def test_response_initialised_before_try(self) -> None:
        src = _handler_source()
        # The initialisation must appear inside handle_gateway_request,
        # before the ``try:`` block that assigns _response from
        # _execute_v2. Marker: the comment we left explaining WHY.
        assert "Initialise here so the" in src, (
            "expected the UnboundLocalError guard comment; the fix "
            "for the 2026-09-21 regression may have been reverted"
        )
        # And the actual assignment itself.
        assert "\n        _response = None\n" in src

    def test_finally_guards_response_before_hasattr(self) -> None:
        src = _handler_source()
        # The settle-actuals block must guard _response is not None
        # before hasattr. Bare hasattr(_response, "body") is what
        # produced UnboundLocalError.
        assert 'elif _response is not None and hasattr(_response, "body"):' in src, (
            "settle-actuals finally must guard _response is not None "
            "before reading .body; a bare hasattr risks UnboundLocalError "
            "when _execute_v2 raised before assignment"
        )

    def test_bare_hasattr_response_body_removed(self) -> None:
        src = _handler_source()
        # Belt-and-braces — no bare ``hasattr(_response, "body")`` should
        # remain anywhere in this file (any such site is a potential
        # UnboundLocalError on any raise-before-assignment path).
        assert 'elif hasattr(_response, "body"):' not in src, (
            "bare ``elif hasattr(_response, \"body\")`` reintroduced — "
            "always pair with ``_response is not None`` guard"
        )
