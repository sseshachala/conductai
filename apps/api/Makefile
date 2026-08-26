.PHONY: schema schema-check ci-py ci-py-fast ci-py-help

# Regenerate app/dsl/schema/v1.yaml from schema.py (source of truth)
schema:
	python scripts/generate_schema.py

# CI gate: fail if v1.yaml is out of sync with schema.py
# Also verifies BE block_schemas.py + FE config-schemas.ts agree on required flags.
schema-check:
	python scripts/generate_schema.py --check
	python ../../scripts/check_schema_parity.py

# ─────────────────────────────────────────────────────────────────────────────
# Local CI mirror
# ─────────────────────────────────────────────────────────────────────────────
#
# ci-py runs the API suite the same way .github/workflows/ci.yml does:
#   - fresh marshal_test database (isolated from your dev DB)
#   - alembic upgrade head + up/down cycle
#   - pytest tests/ -q --ignore=tests/test_guard.py -m 'not matrix'
#
# If a change passes `make ci-py` locally, it will pass the API job on CI —
# barring pure environment differences (Vercel deploy, npm-audit, pip-audit).
#
# Prereqs: docker postgres container running (marshal-postgres-1), python 3.11,
# and requirements.txt installed. Use `make ci-py-help` for a checklist.

CI_DATABASE_URL := postgresql://marshal:marshal@localhost:5432/marshal_test
CI_TEST_ENV := DATABASE_URL='$(CI_DATABASE_URL)' ANTHROPIC_API_KEY='sk-test'

ci-py:
	@docker ps --format '{{.Names}}' | grep -q '^marshal-postgres' || { \
		echo "✗ marshal-postgres container not running."; \
		echo "  Start it: cd .. && docker compose up -d postgres"; \
		exit 1; \
	}
	@echo "→ Reset marshal_test database (drops any prior state)..."
	@docker exec marshal-postgres-1 psql -U marshal -d postgres -c \
		'DROP DATABASE IF EXISTS marshal_test WITH (FORCE)' >/dev/null
	@docker exec marshal-postgres-1 psql -U marshal -d postgres -c \
		'CREATE DATABASE marshal_test' >/dev/null
	@echo "→ alembic upgrade head..."
	@$(CI_TEST_ENV) alembic upgrade head
	@echo "→ alembic downgrade -1 + upgrade head (catches broken downgrade paths)..."
	@$(CI_TEST_ENV) alembic downgrade -1
	@$(CI_TEST_ENV) alembic upgrade head
	@echo "→ pytest (same flags as CI: -q --ignore=tests/test_guard.py -m 'not matrix')..."
	@$(CI_TEST_ENV) python -m pytest tests/ -q --ignore=tests/test_guard.py -m 'not matrix'

# ci-py-fast: skip DB reset + migration cycle, just re-run pytest against the
# existing marshal_test DB. Use during iteration when schema hasn't changed.
# Assumes `make ci-py` ran at least once to seed the DB.
ci-py-fast:
	@$(CI_TEST_ENV) python -m pytest tests/ -q --ignore=tests/test_guard.py -m 'not matrix'

ci-py-help:
	@echo "make ci-py       — full run (DB reset + migrations + tests). ~2-3 min."
	@echo "make ci-py-fast  — pytest only, against existing marshal_test DB. ~30-60s."
	@echo ""
	@echo "Prereqs:"
	@echo "  1. docker postgres running:  cd .. && docker compose up -d postgres"
	@echo "  2. python 3.11 available"
	@echo "  3. pip install -r requirements.txt"
	@echo ""
	@echo "Notes:"
	@echo "  - Isolates from your dev DB (marshal) by using a separate DB (marshal_test)"
	@echo "  - Mirrors CI's -m 'not matrix' filter (skips ~600 endpoint×role tests)"
	@echo "  - Mirrors CI's --ignore=tests/test_guard.py (runs nightly, not per-commit)"
	@echo "  - Full matrix + guard tests run in .github/workflows/nightly.yml"
