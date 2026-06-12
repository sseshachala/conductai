#!/usr/bin/env python3
"""
Generate app/dsl/schema/v1.yaml from the Pydantic models in app/dsl/schema.py.

Usage (from apps/api/):
    python scripts/generate_schema.py           # regenerate in-place
    python scripts/generate_schema.py --check   # CI mode: fail if out of sync
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

API_ROOT  = Path(__file__).parent.parent          # apps/api/
SCHEMA_PY = API_ROOT / "app" / "dsl" / "schema.py"
OUT_PATH  = API_ROOT / "app" / "dsl" / "schema" / "v1.yaml"


def _load_workflow():
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))
    from app.dsl.schema import Workflow  # noqa: PLC0415
    return Workflow


def _deref(schema: dict, defs: dict) -> dict:
    """Inline $ref entries so the YAML is self-contained."""
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return _deref(defs.get(name, {}), defs)
    result = {}
    for k, v in schema.items():
        if k == "$defs":
            continue
        if isinstance(v, dict):
            result[k] = _deref(v, defs)
        elif isinstance(v, list):
            result[k] = [_deref(i, defs) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result


def generate() -> str:
    Workflow = _load_workflow()
    raw   = Workflow.model_json_schema()
    defs  = raw.get("$defs", {})
    clean = _deref(raw, defs)

    header = (
        "# AUTO-GENERATED — do not edit by hand.\n"
        "# Source of truth: apps/api/app/dsl/schema.py\n"
        "# Regenerate:  cd apps/api && python scripts/generate_schema.py\n"
        "# CI check:    cd apps/api && python scripts/generate_schema.py --check\n"
        "#\n"
        "# JSON Schema (Pydantic-derived) for Conduct DSL v1 playbooks.\n"
    )
    return header + yaml.dump(clean, default_flow_style=False, allow_unicode=True, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if v1.yaml is out of sync")
    args = parser.parse_args()

    generated = generate()

    if args.check:
        current = OUT_PATH.read_text() if OUT_PATH.exists() else ""
        if current != generated:
            print("✗  app/dsl/schema/v1.yaml is out of sync with schema.py")
            print("   Run:  cd apps/api && python scripts/generate_schema.py")
            sys.exit(1)
        print("✓  app/dsl/schema/v1.yaml is up to date")
    else:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(generated)
        print(f"✓  Written {OUT_PATH}  ({generated.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
