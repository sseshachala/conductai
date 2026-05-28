"""
ModelRouter — V1 rules-based model selection.

Resolves (playbook_slug, block_task_category, routing_preference) → (model_id, reason).

Design principles:
- Deterministic: same inputs always produce same output
- Never raises: returns a safe default on any unexpected input
- Logged: always returns a reason string for the run trace

V2 will replace the static policy with outcome-scored selection once
enough run data accumulates per (playbook_slug × model) combination.
See issue #314.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

# ── Model IDs ────────────────────────────────────────────────────────────────

SONNET   = "claude-sonnet-4-6"
OPUS     = "claude-opus-4-7"
HAIKU    = "claude-haiku-4-5-20251001"

# ── Task categories (derived from playbook slug) ──────────────────────────────

_SLUG_TO_CATEGORY: dict[str, str] = {
    "autopilot_quick":        "code_implementation",
    "autopilot_full":         "code_implementation",
    "autopilot_approved":     "code_implementation",
    "dependency_updater":     "code_implementation",
    "security_patch_updater": "code_implementation",
    "pr_reviewer":            "code_review",
    "copilot_reviewer":       "code_review",
    "security_scanner":       "security",
    "issue_triage":           "triage",
    "ci_notify":              "triage",
    "flaky_test_detective":   "triage",
    "release_notes":          "summarization",
    "release_readiness":      "code_review",
    "incident_responder":     "reasoning",
    "postmortem_drafter":     "summarization",
    "docs_drift_detector":    "summarization",
    "terraform_reviewer":     "reasoning",
}

# ── Static policy: (task_category, routing_preference) → (model_id, reason) ─

_POLICY: dict[tuple[str, str], tuple[str, str]] = {
    # code_implementation — needs strong tool use + multi-file reasoning
    ("code_implementation", "quality"):  (OPUS,    "code implementation benefits from strongest reasoning"),
    ("code_implementation", "balanced"): (SONNET,  "balanced model for code implementation"),
    ("code_implementation", "speed"):    (SONNET,  "sonnet is fast enough for code tasks"),
    ("code_implementation", "cost"):     (SONNET,  "haiku lacks multi-file tool use; sonnet is minimum viable"),

    # code_review — diff reasoning, precise feedback
    ("code_review", "quality"):  (OPUS,    "code review benefits from strongest reasoning model"),
    ("code_review", "balanced"): (SONNET,  "balanced model for code review"),
    ("code_review", "speed"):    (SONNET,  "sonnet handles diffs well at speed"),
    ("code_review", "cost"):     (HAIKU,   "haiku sufficient for structured code review output"),

    # security — must not miss findings; cost secondary
    ("security", "quality"):  (OPUS,    "security scanning requires highest-precision model"),
    ("security", "balanced"): (OPUS,    "security scanning: quality always preferred over cost"),
    ("security", "speed"):    (SONNET,  "sonnet for security when speed is prioritized"),
    ("security", "cost"):     (SONNET,  "haiku too weak for security; sonnet minimum viable"),

    # triage — classification, labeling, simple decisions
    ("triage", "quality"):  (SONNET,  "sonnet sufficient for structured triage tasks"),
    ("triage", "balanced"): (SONNET,  "balanced model for triage"),
    ("triage", "speed"):    (HAIKU,   "haiku ideal for fast triage classification"),
    ("triage", "cost"):     (HAIKU,   "haiku cost-optimal for simple triage tasks"),

    # summarization — extraction and formatting, not reasoning
    ("summarization", "quality"):  (SONNET,  "sonnet more than sufficient for summarization"),
    ("summarization", "balanced"): (SONNET,  "balanced model for summarization"),
    ("summarization", "speed"):    (HAIKU,   "haiku fast and accurate for summarization"),
    ("summarization", "cost"):     (HAIKU,   "haiku cost-optimal for summarization"),

    # reasoning — log analysis, incident response, complex decisions
    ("reasoning", "quality"):  (OPUS,    "reasoning tasks benefit from strongest model"),
    ("reasoning", "balanced"): (SONNET,  "balanced model for reasoning tasks"),
    ("reasoning", "speed"):    (SONNET,  "sonnet balances speed and reasoning depth"),
    ("reasoning", "cost"):     (SONNET,  "haiku lacks reasoning depth; sonnet minimum viable"),
}

# Defaults when category or preference is not matched
_CATEGORY_DEFAULT: dict[str, tuple[str, str]] = {
    "code_implementation": (SONNET, "default: balanced model for code implementation"),
    "code_review":         (SONNET, "default: balanced model for code review"),
    "security":            (OPUS,   "default: strongest model for security tasks"),
    "triage":              (HAIKU,  "default: cost-efficient model for triage"),
    "summarization":       (HAIKU,  "default: cost-efficient model for summarization"),
    "reasoning":           (SONNET, "default: balanced model for reasoning"),
}

_GLOBAL_DEFAULT = (SONNET, "default: balanced model")


def resolve(
    playbook_slug: str | None,
    routing_preference: str | None,
    explicit_model: str | None = None,
) -> tuple[str, str]:
    """
    Return (model_id, routing_reason).

    Priority:
    1. explicit_model on the block — user pinned a specific model
    2. Static policy lookup: (task_category, routing_preference)
    3. Category default
    4. Global default (sonnet)
    """
    try:
        # 1. Pinned model
        if explicit_model:
            return explicit_model, "user-pinned model"

        pref = (routing_preference or "balanced").lower()
        if pref == "auto":
            pref = "balanced"

        # 2. Resolve category from slug
        category = _SLUG_TO_CATEGORY.get(playbook_slug or "", "") if playbook_slug else ""

        if category:
            model, reason = _POLICY.get((category, pref), _CATEGORY_DEFAULT.get(category, _GLOBAL_DEFAULT))
        else:
            # Unknown slug — fall back by preference only
            pref_defaults: dict[str, tuple[str, str]] = {
                "quality":  (OPUS,   "quality preference: strongest model"),
                "balanced": (SONNET, "balanced preference: default model"),
                "speed":    (SONNET, "speed preference: sonnet is fast"),
                "cost":     (HAIKU,  "cost preference: efficient model"),
            }
            model, reason = pref_defaults.get(pref, _GLOBAL_DEFAULT)

        log.debug("model_router.resolved", slug=playbook_slug, pref=pref, category=category, model=model)
        return model, reason

    except Exception as e:
        log.warning("model_router.error", error=str(e))
        return SONNET, "fallback: routing error"
