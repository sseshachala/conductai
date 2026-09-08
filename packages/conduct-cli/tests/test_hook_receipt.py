"""#1712 PR 4 — hook-side receipt URL helpers.

The Claude Code hook mints a receipt id client-side and prints the URL in
a boxed callout. Backend `POST /guard/events` accepts the pre-minted id
so the audit row PK matches what the user saw on stderr.
"""
from __future__ import annotations

from conduct_cli.hooks.base import boxed_stderr, web_url_from_api


def test_web_url_from_api_strips_api_subdomain():
    assert web_url_from_api("https://api.conductai.ai") == "https://conductai.ai"
    assert web_url_from_api("https://api.conductai.ai/") == "https://conductai.ai"
    assert web_url_from_api("http://api.example.test") == "http://example.test"


def test_web_url_from_api_leaves_non_api_hosts_alone():
    # "myapi.example.com" is not an api-subdomain — must not be mangled
    assert web_url_from_api("https://myapi.example.com") == "https://myapi.example.com"
    assert web_url_from_api("https://conduct.internal") == "https://conduct.internal"


def test_boxed_stderr_wraps_message_and_receipt_url():
    box = boxed_stderr("[ConductGuard] Prompt contains PII", receipt_url="https://x/theguard/blocks/abc")
    lines = box.splitlines()
    # top + at least the message line + the receipt line + bottom
    assert lines[0].startswith("┌") and lines[0].endswith("┐")
    assert lines[-1].startswith("└") and lines[-1].endswith("┘")
    assert any("Prompt contains PII" in line for line in lines)
    assert any("→ Receipt: https://x/theguard/blocks/abc" in line for line in lines)


def test_boxed_stderr_without_receipt_still_boxes_message():
    box = boxed_stderr("[ConductGuard] budget hard cap reached")
    assert "→ Receipt:" not in box
    assert "budget hard cap reached" in box
    assert box.splitlines()[0].startswith("┌")
