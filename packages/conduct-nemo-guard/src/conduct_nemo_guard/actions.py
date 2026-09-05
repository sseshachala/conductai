"""NeMo Guardrails Colang action.

Exposes ``conduct_guard_check`` so any Colang flow can invoke the
Conduct runtime policy layer mid-conversation. Register once at
startup:

.. code-block:: python

    from nemoguardrails import LLMRails, RailsConfig
    from conduct_nemo_guard.actions import register_actions

    config = RailsConfig.from_path("./rails")
    rails = LLMRails(config)
    register_actions(rails)

Then reference the action in Colang:

.. code-block:: colang

    define flow policy_gate
      $decision = execute conduct_guard_check(tool_name="ask_bot")
      if $decision.verdict == "block"
        bot inform_blocked_by_policy
        stop
"""
from __future__ import annotations

import logging
import os
from typing import Any

from conduct_nemo_guard._client import GuardCheckClient, GuardCheckError
from conduct_nemo_guard._decisions import GuardDecision

log = logging.getLogger(__name__)

# Process-wide client so the underlying httpx pool is reused across every
# Colang invocation. Reset with :func:`reset_client` in tests.
_client: GuardCheckClient | None = None


def _get_client() -> GuardCheckClient:
    global _client
    if _client is None:
        token = os.environ.get("CONDUCT_AGENT_TOKEN")
        if not token:
            raise ValueError(
                "conduct_nemo_guard: CONDUCT_AGENT_TOKEN not set. Export a "
                "cond_agt_* token before starting your NeMo app."
            )
        _client = GuardCheckClient(
            api_url=os.environ.get("CONDUCT_API_URL", "https://api.conductai.ai"),
            agent_token=token,
            workspace_id=os.environ.get("CONDUCT_WORKSPACE_ID"),
            surface="nemo",
        )
    return _client


def reset_client() -> None:
    """Clear the cached client. Useful in tests that swap env vars."""
    global _client
    _client = None


async def conduct_guard_check(
    tool_name: str = "colang_flow",
    tool_input: dict[str, Any] | None = None,
    prompt: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Colang-callable action. Runs ``guard_check`` against Conduct.

    Returns a dict with ``verdict``, ``rule_id``, ``message``, and the
    raw text so Colang flows can pattern-match on the result::

        define flow policy_gate
          $decision = execute conduct_guard_check(tool_name="ask_bot")
          if $decision.verdict == "block"
            bot inform_blocked_by_policy
            stop
    """
    client = _get_client()
    # ponytail: server-side pattern matcher greps json.dumps(tool_input),
    # not `prompt`. Fold prompt into tool_input so match_pattern hits user text.
    merged_input = dict(tool_input or {})
    if prompt is not None and "prompt" not in merged_input:
        merged_input["prompt"] = prompt
    try:
        raw = await client.guard_check(
            tool_name=tool_name,
            tool_input=merged_input,
            session_id=session_id,
            prompt=prompt,
        )
    except GuardCheckError as e:
        log.warning("conduct_guard_check: eval error %s — returning block", e)
        decision = GuardDecision(
            verdict="block",
            raw=str(e),
            message="Conduct Guard policy-eval error (fail_closed).",
        )
    except Exception as e:  # network, timeout, unexpected
        log.warning("conduct_guard_check: transport error %s — returning block", e)
        decision = GuardDecision(
            verdict="block",
            raw=str(e),
            message="Conduct Guard is unreachable (fail_closed).",
        )
    else:
        decision = GuardDecision.parse(raw)

    return {
        "verdict": decision.verdict,
        "rule_id": decision.rule_id,
        "message": decision.message,
        "raw": decision.raw,
    }


async def conduct_guard_verdict(
    tool_name: str = "colang_flow",
    prompt: str | None = None,
    session_id: str | None = None,
) -> str:
    """Scalar-return sibling of :func:`conduct_guard_check`. Returns just
    the verdict string ("allow" | "block" | "approval" | "warning" |
    "advisory" | "unknown") so Colang input rails can branch with a
    plain string compare — some Colang versions don't do attribute
    access on dict return values."""
    result = await conduct_guard_check(
        tool_name=tool_name, prompt=prompt, session_id=session_id
    )
    return result["verdict"]


def register_actions(rails: Any) -> None:
    """Register the Colang actions this plugin ships with an ``LLMRails``
    instance.

    ``rails`` is duck-typed against ``nemoguardrails.LLMRails`` so the
    package stays importable without ``nemoguardrails`` installed —
    matches the pattern in ``conduct_litellm_guard`` (LiteLLM stays
    optional there too).
    """
    rails.register_action(conduct_guard_check, name="conduct_guard_check")
    rails.register_action(conduct_guard_verdict, name="conduct_guard_verdict")
