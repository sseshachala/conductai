"""Conduct Guard as a NeMo Guardrails plugin.

Two integration hooks:

* **Colang action** ``conduct_guard_check`` — call Guard mid-flow from
  any Colang script. Verdicts (``allow`` / ``block`` / ``warning`` /
  ``approval``) return to the flow so rails can branch on them.
* **LLM provider** ``engine: conduct`` — route NeMo's LLM traffic
  through the Conduct proxy so every generation is policy-checked and
  audited alongside your rails. Placeholder in ``llm_provider.py``;
  action-only integration in ``actions.py`` covers the fast path.

Basic ``config.yml``::

    models:
      - type: main
        engine: openai
        model: gpt-4o-mini

    rails:
      input:
        flows:
          - conduct_guard_check

Both hooks read the Conduct agent token from ``CONDUCT_AGENT_TOKEN``
and the API base from ``CONDUCT_API_URL`` (default
``https://api.conductai.ai``).
"""
from conduct_nemo_guard._decisions import (
    ConductGuardBlocked,
    GuardDecision,
    Verdict,
)

__version__ = "0.1.0"
__all__ = [
    "ConductGuardBlocked",
    "GuardDecision",
    "Verdict",
    "__version__",
]
