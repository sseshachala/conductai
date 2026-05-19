"""
Canonical filename convention for workflow YAML.

Each workflow in a workspace gets its own YAML file. We slugify the workflow
name and append ``-delegator.yml`` so that:

  - committing multiple workflows into one repo still produces unique paths
    (e.g. ``ai-ready-autopilot-delegator.yml`` lives next to
    ``release-notes-delegator.yml``);
  - the file is grep-able as a Delegator artifact regardless of which workflow
    it represents;
  - the customer can override the actual ``source_path`` to whatever they
    want — this is only the *suggested* default.

Mirror of ``apps/web/src/lib/yaml-filename.ts``. Kept in two places because
the canvas needs it before any API round-trip; the backend needs it for
``Content-Disposition`` headers and any future CLI export.
"""
from __future__ import annotations

import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_workflow_name(name: str | None) -> str:
    """Lowercase, collapse non-alphanumerics to hyphens, trim, cap at 80 chars."""
    if not name:
        return "workflow"
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return (slug or "workflow")[:80]


def yaml_filename_for(name: str | None) -> str:
    """Return the canonical filename: ``<projectname>-delegator.yml``."""
    return f"{slugify_workflow_name(name)}-delegator.yml"
