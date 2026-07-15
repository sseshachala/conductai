"""
Shared test fixtures + safety nets.

Tests should run without a real Postgres or Redis — these set env vars early
so the settings module picks up dev-safe defaults even if the developer hasn't
sourced an .env file.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `import app.*` resolve from the apps/api root so tests don't depend on
# the cwd they're invoked from.
HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")
