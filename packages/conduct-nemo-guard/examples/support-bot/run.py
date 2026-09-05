"""Runnable end-to-end example for ``conduct-nemo-guard``.

Wires the ``conduct_guard_check`` action into a NeMo Guardrails
``LLMRails`` instance, then runs a single-turn conversation. On
BLOCKED / PENDING-approval verdicts the input rail short-circuits and
the model is never called.

Prereqs
-------
Export the tokens the plugin and the model need:

.. code-block:: bash

    export CONDUCT_AGENT_TOKEN=cond_agt_...
    export OPENAI_API_KEY=sk-...

Usage
-----
.. code-block:: bash

    python run.py "delete my account"
    python run.py "what are your support hours?"

The first message should trigger a BLOCKED / approval verdict once a
matching Guard rule is active; the second should pass and reach the
model. Both land as audit rows on the Conduct Guard Activity page.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parent


def _fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


async def _run(user_message: str) -> None:
    if not os.environ.get("CONDUCT_AGENT_TOKEN"):
        _fail(
            "CONDUCT_AGENT_TOKEN is not set. Mint a token at "
            "https://conductai.ai (Settings → Agent identities) and "
            "export it before running this example."
        )

    try:
        # Deferred so the CLI still prints a friendly error when the
        # optional dependency is missing.
        from nemoguardrails import LLMRails, RailsConfig  # type: ignore
    except ImportError as e:
        _fail(
            "nemoguardrails is not installed. Run "
            "`pip install nemoguardrails` (or "
            "`pip install conduct-nemo-guard[nemo]`) first. "
            f"Import error: {e}"
        )
        return  # unreachable, keeps type checkers happy

    from conduct_nemo_guard.actions import register_actions

    config = RailsConfig.from_path(str(CONFIG_DIR))
    rails = LLMRails(config)
    register_actions(rails)

    result = await rails.generate_async(
        messages=[{"role": "user", "content": user_message}],
    )
    if isinstance(result, dict):
        print(result.get("content", result))
    else:
        print(result)


def main() -> None:
    if len(sys.argv) < 2:
        _fail("usage: python run.py \"<user message>\"")
    asyncio.run(_run(" ".join(sys.argv[1:])))


if __name__ == "__main__":
    main()
