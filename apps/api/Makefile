.PHONY: schema schema-check

# Regenerate app/dsl/schema/v1.yaml from schema.py (source of truth)
schema:
	python scripts/generate_schema.py

# CI gate: fail if v1.yaml is out of sync with schema.py
schema-check:
	python scripts/generate_schema.py --check
