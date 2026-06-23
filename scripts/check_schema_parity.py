#!/usr/bin/env python3
"""Schema parity check — catch drift between BE and FE block schemas in CI.

Reads:
  - apps/api/app/runtime/block_schemas.py (BE — canonical for validation)
  - apps/web/src/lib/config-schemas.ts    (FE — drives form rendering)

For each (block-type, field-key) declared in BOTH, asserts:
  - Required flags match (one side can't say required when the other doesn't)

For trigger subtypes, walks both files' nested subtype declarations.

Doesn't flag fields declared in only one side — those are intentional (BE
validates structural fields that don't render in the form, FE has form-only
fields like routingPreference that don't need server validation). But if
the same key appears on both sides with different `required` semantics,
the validator and form will disagree → "missing required field" lies.

Exit codes:
  0 — schemas consistent
  1 — mismatches detected (lists them and exits non-zero for CI)

Usage:
  python3 scripts/check_schema_parity.py
  # In CI: add to .github/workflows/ci.yml
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BE_FILE = ROOT / "apps" / "api" / "app" / "runtime" / "block_schemas.py"
FE_FILE = ROOT / "apps" / "web" / "src" / "lib" / "config-schemas.ts"


def parse_backend() -> dict[str, dict[str, bool]]:
    """Return {block_key: {field_key: required}} for the backend schema."""
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    from app.runtime.block_schemas import BLOCK_SCHEMAS  # type: ignore

    out: dict[str, dict[str, bool]] = {}
    for btype, defn in BLOCK_SCHEMAS.items():
        for f in defn.get("fields", []):
            out.setdefault(btype, {})[f["key"]] = bool(f.get("required", False))
        for st, st_def in (defn.get("subtypes") or {}).items():
            block_key = f"{btype}.{st}"
            for f in st_def.get("fields", []):
                out.setdefault(block_key, {})[f["key"]] = bool(f.get("required", False))
    return out


def parse_frontend() -> dict[str, dict[str, bool]]:
    """Return {block_key: {field_key: required}} for the frontend schema.

    Best-effort regex parse — we only extract `key:` and `required:` fields
    from each subtype/block block. Misses some complex constructions but
    catches the high-volume drift cases.
    """
    src = FE_FILE.read_text()

    def fields_for_block(block_text: str) -> dict[str, bool]:
        # Each field object: {  key: "...", ..., required: true|false, ... }
        out: dict[str, bool] = {}
        # Match outermost braces and grab their key+required
        for m in re.finditer(r"\{[^{}]*key:\s*\"([^\"]+)\"[^{}]*\}", block_text):
            body = m.group(0)
            key = m.group(1)
            req = bool(re.search(r"required:\s*true\b", body))
            out[key] = req
        return out

    out: dict[str, dict[str, bool]] = {}

    # TRIGGER_CONFIG = { manual: {...}, github_issue_labeled: {...}, ... }
    trig_m = re.search(r"TRIGGER_CONFIG[^=]*=\s*\{", src)
    if trig_m:
        # Walk until matching }
        depth = 0
        start = trig_m.end() - 1
        for i in range(start, len(src)):
            c = src[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    trig_text = src[start:i + 1]
                    break
        # Each top-level subtype declaration
        for sm in re.finditer(r"(\w+):\s*\{\s*label:[^,]*,\s*fields:\s*\[", trig_text):
            st_name = sm.group(1)
            # walk to matching ]
            depth_b = 0
            idx = trig_text.find("[", sm.end() - 1)
            for j in range(idx, len(trig_text)):
                if trig_text[j] == "[":
                    depth_b += 1
                elif trig_text[j] == "]":
                    depth_b -= 1
                    if depth_b == 0:
                        out[f"trigger.{st_name}"] = fields_for_block(trig_text[idx + 1:j])
                        break

    # BLOCK_CONFIG_SCHEMAS = { brain: [...], logic: [...], ... }
    bcs_m = re.search(r"BLOCK_CONFIG_SCHEMAS[^=]*=\s*\{", src)
    if bcs_m:
        depth = 0
        start = bcs_m.end() - 1
        for i in range(start, len(src)):
            c = src[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    bcs_text = src[start:i + 1]
                    break
        for sm in re.finditer(r"(\w+):\s*\[", bcs_text):
            block_name = sm.group(1)
            depth_b = 0
            idx = bcs_text.find("[", sm.end() - 1)
            for j in range(idx, len(bcs_text)):
                if bcs_text[j] == "[":
                    depth_b += 1
                elif bcs_text[j] == "]":
                    depth_b -= 1
                    if depth_b == 0:
                        out[block_name] = fields_for_block(bcs_text[idx + 1:j])
                        break

    return out


def main() -> int:
    be = parse_backend()
    fe = parse_frontend()

    drift: list[str] = []
    # Trigger subtypes — BE uses 'trigger.github_issue_labeled', FE same naming
    for block_key in sorted(set(be.keys()) | set(fe.keys())):
        be_fields = be.get(block_key, {})
        fe_fields = fe.get(block_key, {})
        common = set(be_fields.keys()) & set(fe_fields.keys())
        for fk in sorted(common):
            if be_fields[fk] != fe_fields[fk]:
                drift.append(
                    f"  {block_key}.{fk}: BE required={be_fields[fk]} vs FE required={fe_fields[fk]}"
                )

    if drift:
        print("Schema drift detected — same key, different required semantics:\n")
        for line in drift:
            print(line)
        print("\nFix: make the BE (apps/api/.../block_schemas.py) and FE")
        print("(apps/web/src/lib/config-schemas.ts) agree on the required flag.")
        return 1

    print(f"Schema parity OK — {sum(len(v) for v in be.values())} BE fields, "
          f"{sum(len(v) for v in fe.values())} FE fields, no required-flag drift")
    return 0


if __name__ == "__main__":
    sys.exit(main())
