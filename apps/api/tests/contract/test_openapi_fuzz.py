"""OpenAPI contract fuzzing via Schemathesis (#1260).

Auto-generates property-based tests from the FastAPI OpenAPI spec. Every
future endpoint added to the app gets fuzz coverage automatically — no
per-endpoint test to write.

## What this asserts (automatically, per endpoint)

For every random valid input Schemathesis generates:

- **No 5xx** — server never crashes on well-formed input. An unhandled
  ``AttributeError`` or ``KeyError`` in an auth dep that bubbles to 500
  instead of 401 (like today's cluster A+B fixed in PR #1373) fails here.
- **Response matches declared schema** — if the OpenAPI spec says a
  response has ``{"id": int, "name": string}``, the actual response must
  have those fields with those types. Catches drift when a field is
  renamed/removed but the spec still lists it.
- **Declared status codes are reachable** — endpoints declaring ``201``
  or ``204`` must actually produce them under valid inputs.

## Scope tonight

Fuzzes an INCLUDE-list of stable public endpoints (health, OAuth metadata,
playbook catalog, pack catalog). Auth-required endpoints are deferred until
a followup PR wires credential injection (issue #1260, "Approach step 4").

## To add an endpoint

1. Add the path pattern to ``INCLUDED_PATHS`` below.
2. Run locally: ``pytest tests/contract/test_openapi_fuzz.py -v``.
3. If Schemathesis flags a real bug, fix the handler.
4. If Schemathesis flags a spec drift (response shape mismatch), update the
   Pydantic model annotations so the spec regenerates correctly.
5. If it's a false-positive, add to ``EXCLUDED_PATHS`` with a comment.

Rewriting hand-written contract tests (``tests/test_contracts.py``) as this
INCLUDE-list grows is a follow-up cleanup — see #1260 "Prior art".
"""
from __future__ import annotations

import os
import re

# Env vars must be set before importing app.main. Values are placeholders —
# tests never open a real connection (Schemathesis runs against the ASGI app
# in-process). Real values come from the CI job env.
os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL", "sqlite:///:memory:"))
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

import pytest
import schemathesis
from hypothesis import settings
from schemathesis.specs.openapi.checks import unsupported_method

from app.main import app

# Checks we deliberately exclude:
# - unsupported_method: FastAPI returns 422 for undeclared HTTP verbs (validation
#   error on empty body) rather than 405. That's a framework-level nit, not a
#   real bug. Add back if we ever add per-router method allow-lists.
_EXCLUDED_CHECKS = [unsupported_method]

# --- Included paths (exact match against OpenAPI path templates) ---
# Add stable, side-effect-free, auth-free endpoints here. Verify each is
# actually declared in the OpenAPI spec (some /healthz etc. don't exist).
INCLUDED_PATHS = [
    "/health",
    "/health/sandbox",
    "/.well-known/oauth-protected-resource/mcp",
    "/.well-known/oauth-protected-resource/guard/mcp",
    "/compliance/packs/catalog",
    "/compliance/packs/available",
    "/workflows/playbooks",
    "/workflows/playbooks/{slug}",
    # /projects/templates is public per check_auth_coverage but reads DB;
    # add back once CI Postgres availability is confirmed for this test.
]

# --- Excluded (false-positive graveyard) ---
# Endpoints that legitimately return non-2xx under fuzz inputs. One-line reason each.
EXCLUDED_PATHS: list[str] = [
    # (none yet — add here as edge cases surface)
]

_EXCLUDE_SET = set(EXCLUDED_PATHS)


# Schemathesis 4.x API: from_asgi consumes the ASGI app directly — no server needed.
schema = schemathesis.openapi.from_asgi("/openapi.json", app)


@schema.include(path=INCLUDED_PATHS).parametrize()
@settings(deadline=None, max_examples=25)  # small budget per endpoint keeps CI < 5min
def test_openapi_fuzz(case):
    """One test per (path, method) — parametrized by Schemathesis + Hypothesis.

    ``case.call_and_validate()`` runs the request through the ASGI app and
    asserts response against the OpenAPI schema. Any 5xx or schema mismatch
    fails this test with a reproducible seed for local repro.
    """
    if case.path in _EXCLUDE_SET:
        pytest.skip(f"excluded by test filter: {case.path}")
    case.call_and_validate(excluded_checks=_EXCLUDED_CHECKS)
