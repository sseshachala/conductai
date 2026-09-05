"""NeMo Guardrails LLM provider that routes generation through Conduct.

Placeholder for the 0.1.0 release. The action-only integration in
``actions.py`` covers the fast path — every Colang flow can gate on
Guard verdicts today.

The provider lands in a follow-up so NeMo installations can also route
their LLM generation through the Conduct proxy with a single line of
``config.yml``:

.. code-block:: yaml

    models:
      - type: main
        engine: conduct
        parameters:
          model: claude-sonnet-4-6

That change gets every generation onto the same hash-chained audit
ledger as Colang actions and MCP tool calls, without customers having
to swap their model bindings.

See the plugin epic for delivery timing:
https://github.com/sseshachala/conductai/issues/1620
"""
from __future__ import annotations


class ConductLLM:
    """Placeholder. See module docstring — provider lands in a follow-up
    once NeMo's provider registration surface for arbitrary OpenAI-compat
    endpoints is exercised in-tree.

    Users who need LLM-level routing today can point NeMo at the Conduct
    OpenAI-compat proxy via the existing ``openai`` engine + a custom
    ``api_base``:

    .. code-block:: yaml

        models:
          - type: main
            engine: openai
            model: claude-sonnet-4-6
            parameters:
              api_base: https://api.conductai.ai/proxy/openai
              api_key: $CONDUCT_AGENT_TOKEN

    That covers the common case until the native ``engine: conduct``
    ships.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "conduct_nemo_guard.llm_provider.ConductLLM is not implemented "
            "in 0.1.0. Use the action-based integration in "
            "conduct_nemo_guard.actions, or point NeMo at the Conduct "
            "OpenAI-compat proxy via engine: openai + api_base — see "
            "the module docstring."
        )
