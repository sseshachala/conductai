"""
Benchmark edition manager for the Conduct Eval Harness.

An "edition" is a frozen snapshot of eval scores committed to
``reports/baselines/``.  Editions are versioned by a slug such as
``edition-001``, written by the ``--publish`` CLI flag, and surfaced
through the ``/eval/benchmark/editions`` API.

Directory layout
----------------
  apps/api/reports/baselines/
    edition-001.json          — edition manifest (aggregate + per-playbook)
    pr_reviewer.json          — latest single-playbook baseline
    pr_reviewer_haiku.json    — model-specific baseline
    ...

Edition manifest format
-----------------------
  {
    "edition": "edition-001",
    "published_at": "2026-05-29T...",
    "model": "claude-haiku-4-5-20251001",
    "summary": { total_playbooks, passing, failing, average_pct },
    "playbooks": [ {slug, grade, pct, structural_score, quality_score}, ... ]
  }
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASELINES_DIR = Path(__file__).resolve().parent.parent / "reports" / "baselines"


# ── readers ───────────────────────────────────────────────────────────────────

def list_editions() -> list[dict[str, Any]]:
    """
    Return all committed edition manifests in baselines_dir, newest first.

    Only files matching ``edition-*.json`` are treated as edition manifests.
    Single-playbook baseline files (e.g. ``pr_reviewer.json``) are ignored here.
    """
    if not BASELINES_DIR.exists():
        return []

    editions: list[dict[str, Any]] = []
    for path in sorted(BASELINES_DIR.glob("edition-*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
            editions.append(_summarise_edition(data, path.stem))
        except (json.JSONDecodeError, KeyError):
            continue

    return editions


def get_edition(slug: str) -> dict[str, Any] | None:
    """
    Return a full edition manifest by slug (e.g. ``edition-001``).
    Returns None if the edition file does not exist.
    """
    if not BASELINES_DIR.exists():
        return None

    path = BASELINES_DIR / f"{slug}.json"
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def list_playbook_baselines() -> list[dict[str, Any]]:
    """
    Return all single-playbook baseline files (excludes edition manifests).
    Each entry includes slug, model, grade, pct, and published_at.
    """
    if not BASELINES_DIR.exists():
        return []

    baselines: list[dict[str, Any]] = []
    for path in sorted(BASELINES_DIR.glob("*.json")):
        if path.stem.startswith("edition-"):
            continue
        try:
            data = json.loads(path.read_text())
            baselines.append({
                "file": path.name,
                "slug": data.get("slug") or _slug_from_filename(path.stem),
                "model": data.get("model"),
                "baseline_published_at": data.get("baseline_published_at"),
                "grade": _first_grade(data),
                "pct": _first_pct(data),
            })
        except (json.JSONDecodeError, OSError):
            continue

    return baselines


def get_playbook_baseline(slug: str, model: str | None = None) -> dict[str, Any] | None:
    """
    Return the baseline for a single playbook, optionally filtered by model.
    """
    if not BASELINES_DIR.exists():
        return None

    filename = f"{slug}.json" if not model else f"{slug}_{model.replace('-', '_')}.json"
    path = BASELINES_DIR / filename
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ── writers ───────────────────────────────────────────────────────────────────

def publish_edition(
    report_dict: dict[str, Any],
    edition_slug: str,
    model: str | None = None,
) -> Path:
    """
    Write an edition manifest to baselines_dir/<edition_slug>.json.

    Parameters
    ----------
    report_dict:
        The ``_to_dict()`` output from an :class:`EvalReport`.
    edition_slug:
        Edition identifier, e.g. ``edition-001``.
    model:
        The model used during live eval, if any.

    Returns the path that was written.
    """
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {
        "edition": edition_slug,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "model": model or "structural-only",
        "source_report": report_dict,
        "summary": report_dict.get("summary", {}),
        "playbooks": [
            {
                "slug": p["slug"],
                "grade": p["grade"],
                "pct": p["pct"],
                "structural_score": p["structural_score"],
                "quality_score": p["quality_score"],
                "total_score": p["total_score"],
                "total_max": p["total_max"],
            }
            for p in report_dict.get("playbooks", [])
        ],
    }

    dest = BASELINES_DIR / f"{edition_slug}.json"
    dest.write_text(json.dumps(manifest, indent=2))
    return dest


def build_edition_manifest(
    edition: str,
    reports: dict[str, Any],
    playbook_filter: str | None = None,
) -> dict[str, Any]:
    """
    Build a multi-model edition manifest from a dict of ``{model: EvalReport}``.

    The manifest extends the single-model format with a ``models`` list so the
    benchmark UI can render per-model breakdowns without a schema change.

    Parameters
    ----------
    edition:
        Edition slug (e.g. ``"002"``).  The file will be named ``edition-002.json``.
    reports:
        ``{model_id: EvalReport}`` — one entry per model evaluated.
    playbook_filter:
        When set, only include the specified slug in the manifest.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Collect per-model results
    models_data: list[dict[str, Any]] = []
    all_playbook_slugs: set[str] = set()

    for model_id, report in reports.items():
        report_dict = report._to_dict()
        playbooks = report_dict.get("playbooks", [])
        if playbook_filter:
            playbooks = [p for p in playbooks if p.get("slug") == playbook_filter]
        for p in playbooks:
            all_playbook_slugs.add(p["slug"])
        models_data.append({
            "model": model_id,
            "summary": report_dict.get("summary", {}),
            "playbooks": [
                {
                    "slug": p["slug"],
                    "grade": p["grade"],
                    "pct": p["pct"],
                    "structural_score": p.get("structural_score", 0),
                    "quality_score": p.get("quality_score", 0),
                    "total_score": p.get("total_score", 0),
                    "total_max": p.get("total_max", 0),
                }
                for p in playbooks
            ],
        })

    # Primary model is the first (usually haiku); aggregate uses its scores
    primary = models_data[0] if models_data else {}

    return {
        "edition": f"edition-{edition}",
        "published_at": now,
        "model": primary.get("model", "multi-model"),
        "models": models_data,
        "summary": primary.get("summary", {}),
        "playbooks": primary.get("playbooks", []),
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _summarise_edition(data: dict[str, Any], stem: str) -> dict[str, Any]:
    """Extract a lightweight summary from an edition manifest."""
    return {
        "slug": data.get("edition") or stem,
        "published_at": data.get("published_at"),
        "model": data.get("model"),
        "summary": data.get("summary", {}),
        "playbook_count": len(data.get("playbooks", [])),
        "top_playbooks": sorted(
            data.get("playbooks", []),
            key=lambda p: -p.get("pct", 0),
        )[:5],
    }


def _slug_from_filename(stem: str) -> str:
    """``pr_reviewer_haiku`` -> ``pr_reviewer`` (strip model suffix heuristic)."""
    known_models = ["haiku", "sonnet", "opus", "gpt_4o", "gpt_4o_mini"]
    for m in known_models:
        if stem.endswith(f"_{m}"):
            return stem[: -(len(m) + 1)]
    return stem


def _first_grade(data: dict) -> str | None:
    playbooks = data.get("playbooks")
    if playbooks:
        return playbooks[0].get("grade")
    return data.get("grade")


def _first_pct(data: dict) -> float | None:
    playbooks = data.get("playbooks")
    if playbooks:
        return playbooks[0].get("pct")
    return data.get("pct")
