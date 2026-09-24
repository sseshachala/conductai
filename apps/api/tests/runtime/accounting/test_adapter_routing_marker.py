"""Verify the ``routes_through_gateway`` marker used by brain_block to
decide whether to fire its own shadow_write for a workflow LLM call
(#2209 Session 6b — resolves Session 5's deferred double-count concern).
"""

from __future__ import annotations


def test_gateway_profile_client_routes_through_gateway():
    """The gateway_profile adapter goes through Gateway HTTP, which fires
    Session 4's shadow_write. brain_block must skip its own hook when this
    marker is True to avoid double-counting.

    Import via ``app.runtime.llm_client`` (the re-export used by production
    callers). Importing ``app.runtime.adapters.gateway_profile`` directly
    trips a pre-existing circular import on this codebase.
    """
    from app.runtime.llm_client import GatewayProfileClient

    assert getattr(GatewayProfileClient, "routes_through_gateway", False) is True


def test_direct_adapters_do_not_route_through_gateway():
    """Direct-provider adapters get brain_block's shadow hook — they don't
    hit Gateway, so no Session 4 receipt exists for their attempts."""
    from app.runtime.adapters.anthropic import AnthropicClient
    from app.runtime.adapters.openai import OpenAIClient
    from app.runtime.adapters.perplexity import PerplexityClient
    from app.runtime.adapters.together import TogetherClient

    assert getattr(AnthropicClient, "routes_through_gateway", False) is False
    assert getattr(OpenAIClient, "routes_through_gateway", False) is False
    assert getattr(PerplexityClient, "routes_through_gateway", False) is False
    # TogetherClient extends OpenAIClient; inherits the default False.
    assert getattr(TogetherClient, "routes_through_gateway", False) is False


def test_getattr_default_false_survives_unknown_adapter():
    """A hypothetical future adapter that doesn't set the marker defaults
    to False (brain_block fires shadow_write). Documented via test so
    behavior can't drift silently."""

    class _FutureAdapter:
        pass

    assert getattr(_FutureAdapter, "routes_through_gateway", False) is False


def test_marker_survives_instance():
    """Class attribute is inherited by instances — brain_block reads via
    ``getattr(llm, ...)`` on the instance, not the class. Skip ``__init__``
    (which requires many args) via ``object.__new__``."""
    from app.runtime.llm_client import GatewayProfileClient

    inst = object.__new__(GatewayProfileClient)
    assert getattr(inst, "routes_through_gateway", False) is True
