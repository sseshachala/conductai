"""Conduct Guard as a LiteLLM guardrail.

Point LiteLLM at Guard and every LLM call routed through your LiteLLM
proxy is policy-checked before the upstream request goes out. Block,
warn, audit, or trigger a HITL approval — the exact same rules that
apply to Claude Code / Cursor / Copilot sessions, now applied to any
LiteLLM-fronted traffic.

Basic usage in a LiteLLM ``config.yaml``::

    guardrails:
      - guardrail_name: conduct-guard
        litellm_params:
          guardrail: conduct_litellm_guard.ConductGuard
          mode: pre_call
          api_url: https://api.conductai.ai
          agent_token: os.environ/CONDUCT_AGENT_TOKEN
          fail_mode: fail_closed
"""
from conduct_litellm_guard.guardrail import ConductGuard, GuardDecision

__version__ = "0.1.0"
__all__ = ["ConductGuard", "GuardDecision", "__version__"]
