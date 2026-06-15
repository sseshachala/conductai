"""
ModelRouter — V1 rules-based provider + model selection.

Resolves (playbook_slug, block_task_category, routing_preference) -> (provider, model_id, reason).

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

# ── Provider + model IDs ─────────────────────────────────────────────────────

SONNET   = "claude-sonnet-4-6"
OPUS     = "claude-opus-4-7"
HAIKU    = "claude-haiku-4-5-20251001"
GPT_41   = "gpt-4.1"
GPT_41_M = "gpt-4.1-mini"
SONAR          = "sonar"
SONAR_PRO      = "sonar-pro"
SONAR_REASONING = "sonar-reasoning-pro"

ANTHROPIC  = "anthropic"
OPENAI     = "openai"
PERPLEXITY = "perplexity"

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

# ── Static policy table: category → (quality, balanced, speed, cost) ─────────
# Each tuple: (provider, model). Preference index: 0=quality 1=balanced 2=speed 3=cost.

_PREFS = ("quality", "balanced", "speed", "cost")

_POLICY: dict[str, list[tuple[str, str]]] = {
    "code_implementation": [(ANTHROPIC, OPUS),   (ANTHROPIC, SONNET), (ANTHROPIC, SONNET), (OPENAI, GPT_41_M)],
    "code_review":         [(ANTHROPIC, OPUS),   (ANTHROPIC, SONNET), (OPENAI, GPT_41_M),  (OPENAI, GPT_41_M)],
    "security":            [(ANTHROPIC, OPUS),   (ANTHROPIC, OPUS),   (ANTHROPIC, SONNET), (ANTHROPIC, SONNET)],
    "triage":              [(ANTHROPIC, SONNET), (OPENAI, GPT_41_M),  (OPENAI, GPT_41_M),  (OPENAI, GPT_41_M)],
    "summarization":       [(ANTHROPIC, SONNET), (OPENAI, GPT_41_M),  (OPENAI, GPT_41_M),  (OPENAI, GPT_41_M)],
    "reasoning":           [(ANTHROPIC, OPUS),   (ANTHROPIC, SONNET), (ANTHROPIC, SONNET), (OPENAI, GPT_41_M)],
}

_GLOBAL_DEFAULT = (ANTHROPIC, SONNET, "default: balanced model")

_PROVIDER_MODEL_DEFAULTS: dict[str, dict[str, tuple[str, str]]] = {
    ANTHROPIC: {
        "code_implementation": (SONNET, "anthropic override: balanced default for code implementation"),
        "code_review":         (SONNET, "anthropic override: balanced default for code review"),
        "security":            (OPUS,   "anthropic override: strongest model for security"),
        "triage":              (SONNET, "anthropic override: balanced default for triage"),
        "summarization":       (SONNET, "anthropic override: balanced default for summarization"),
        "reasoning":           (SONNET, "anthropic override: balanced default for reasoning"),
        "unknown":             (SONNET, "anthropic override: balanced default model"),
    },
    OPENAI: {
        "code_implementation": (GPT_41_M, "openai override: efficient model for code implementation"),
        "code_review":         (GPT_41_M, "openai override: efficient model for code review"),
        "security":            (GPT_41,   "openai override: strongest available OpenAI model for security"),
        "triage":              (GPT_41_M, "openai override: efficient model for triage"),
        "summarization":       (GPT_41_M, "openai override: efficient model for summarization"),
        "reasoning":           (GPT_41,   "openai override: strongest available OpenAI model for reasoning"),
        "unknown":             (GPT_41_M, "openai override: balanced default model"),
    },
    PERPLEXITY: {
        "code_implementation": (SONAR_PRO,      "perplexity override: sonar-pro for code tasks"),
        "code_review":         (SONAR_PRO,      "perplexity override: sonar-pro for code review"),
        "security":            (SONAR_PRO,      "perplexity override: sonar-pro for security scanning"),
        "triage":              (SONAR,          "perplexity override: sonar for triage"),
        "summarization":       (SONAR,          "perplexity override: sonar for summarization"),
        "reasoning":           (SONAR_REASONING, "perplexity override: sonar-reasoning-pro for reasoning"),
        "unknown":             (SONAR,          "perplexity override: sonar default"),
    },
}


def _infer_provider(model: str) -> str:
    m = (model or "").lower()
    if m.startswith("gpt-"):
        return OPENAI
    if m.startswith("sonar"):
        return PERPLEXITY
    return ANTHROPIC


def resolve(
    playbook_slug: str | None,
    routing_preference: str | None,
    explicit_model: str | None = None,
    explicit_provider: str | None = None,
) -> tuple[str, str]:
    """
    Return (provider, model_id, routing_reason).

    Priority:
    1. explicit_model on the block — user pinned a specific model
    2. explicit_provider on the block — user pinned a provider, router picks a safe model for it
    3. Static policy lookup: (task_category, routing_preference)
    4. Category default
    5. Global default (sonnet)
    """
    try:
        # 1. Pinned model
        if explicit_model:
            return _infer_provider(explicit_model), explicit_model, "user-pinned model"

        pref = (routing_preference or "balanced").lower()
        if pref == "auto":
            pref = "balanced"

        # 2. Resolve category from slug
        category = _SLUG_TO_CATEGORY.get(playbook_slug or "", "") if playbook_slug else ""

        requested_provider = (explicit_provider or "").lower().strip()
        if requested_provider in (ANTHROPIC, OPENAI, PERPLEXITY):
            category_key = category or "unknown"
            model, reason = _PROVIDER_MODEL_DEFAULTS[requested_provider].get(
                category_key,
                _PROVIDER_MODEL_DEFAULTS[requested_provider]["unknown"],
            )
            log.debug(
                "model_router.provider_override",
                slug=playbook_slug,
                pref=pref,
                category=category_key,
                provider=requested_provider,
                model=model,
            )
            return requested_provider, model, reason

        if category and category in _POLICY:
            idx = _PREFS.index(pref) if pref in _PREFS else 1
            provider, model = _POLICY[category][idx]
            reason = f"{category}/{pref}: {provider} {model}"
        else:
            # Unknown slug — fall back by preference only
            pref_defaults: dict[str, tuple[str, str, str]] = {
                "quality":  (ANTHROPIC, OPUS,   "quality preference: strongest model"),
                "balanced": (ANTHROPIC, SONNET, "balanced preference: default model"),
                "speed":    (OPENAI,    GPT_41_M, "speed preference: efficient model"),
                "cost":     (OPENAI,    GPT_41_M, "cost preference: efficient model"),
            }
            provider, model, reason = pref_defaults.get(pref, _GLOBAL_DEFAULT)

        log.debug("model_router.resolved", slug=playbook_slug, pref=pref, category=category, provider=provider, model=model)
        return provider, model, reason

    except Exception as e:
        log.warning("model_router.error", error=str(e))
        return ANTHROPIC, SONNET, "fallback: routing error"
