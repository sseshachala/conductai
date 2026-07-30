"""Generate the checked-in ConductGuard enforcement evidence matrix."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
PACK_DIR = API_ROOT / "app/modules/guard/skill_packs"
OUTPUT_PATH = REPO_ROOT / "docs/modules/conductguard/enforcement_coverage.generated.md"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.modules.guard.enforcement import SURFACES, validate_pack


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_document() -> str:
    lines = [
        "<!-- GENERATED FILE: DO NOT EDIT DIRECTLY. -->",
        "<!-- Regenerate: cd apps/api && python3 scripts/generate_guard_enforcement_coverage.py -->",
        "",
        "# ConductGuard Enforcement Coverage",
        "",
        "This evidence matrix is generated from the versioned `enforcement` contract in "
        "`apps/api/app/modules/guard/skill_packs/*.json`. Surface status meanings:",
        "",
        "- `hard`: the surface prevents the matching action once traffic reaches that surface.",
        "- `conditional`: prevention requires the named installation, invocation, or runtime dependency.",
        "- `advisory`: the surface warns or records evidence but does not prevent the action.",
        "- `not_supported`: the current enforcer cannot evaluate the required content or semantics.",
        "",
    ]
    for path in sorted(PACK_DIR.glob("*.json")):
        pack = json.loads(path.read_text())
        validate_pack(pack, source=str(path))
        lines.extend([
            f"## {_cell(pack['name'])} (`{pack['slug']}` {pack['version']})",
            "",
            "| Rule | Proxy | Hook | MCP | Runtime | Guarantee |",
            "|---|---|---|---|---|---|",
        ])
        for rule in sorted(pack["rules"], key=lambda item: item["id"]):
            metadata = rule["enforcement"]
            evidence = metadata["guarantee"]
            if metadata["requires"]:
                evidence += " Requires: " + "; ".join(metadata["requires"]) + "."
            if metadata["known_limitations"]:
                evidence += " Limitations: " + "; ".join(metadata["known_limitations"]) + "."
            lines.append(
                "| `{rule}` | {proxy} | {hook} | {mcp} | {runtime} | {guarantee} |".format(
                    rule=_cell(rule["id"]),
                    guarantee=_cell(evidence),
                    **{surface: metadata[surface] for surface in SURFACES},
                )
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero if the checked-in document differs from generated output.",
    )
    args = parser.parse_args()
    rendered = render_document()
    if args.check:
        return 0 if OUTPUT_PATH.exists() and OUTPUT_PATH.read_text() == rendered else 1
    OUTPUT_PATH.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
