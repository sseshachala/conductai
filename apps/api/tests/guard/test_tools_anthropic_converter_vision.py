"""#2166 PR 2 — vision content conversion tests for the canonical ↔ Anthropic
converter, plus the server-side HTTPS fetch guards on image URLs.

Split from ``test_tools_anthropic_converter.py``.
"""
from __future__ import annotations

from app.modules.guard.tools_anthropic_converter import (
    canonical_to_anthropic,
)


# ─── #2166 PR 2 — vision content conversion ────────────────────────


class TestVisionConversion:
    """Anthropic-target ``image_url`` → ``image`` block conversion."""

    def test_https_url_fetched_and_base64_encoded(self, monkeypatch) -> None:
        # Anthropic's URL-source support is inconsistent across model
        # versions + adapters (LiteLLM, Bedrock passthrough), so the
        # converter fetches HTTPS URLs server-side and emits base64.
        # Mock the fetch so this stays a unit test.
        from app.modules.guard import tools_anthropic_converter as _mod
        def _fake_fetch(url):
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": "ZmFrZS1ieXRlcw==",
                },
            }
        monkeypatch.setattr(_mod, "_fetch_and_encode_image", _fake_fetch)
        req = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "what's this?"},
                    {"type": "image_url", "image_url": {
                        "url": "https://example.com/pic.png",
                    }},
                ],
            }],
        }
        out = canonical_to_anthropic(req)
        content = out["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "what's this?"}
        assert content[1]["type"] == "image"
        assert content[1]["source"]["type"] == "base64"
        assert content[1]["source"]["media_type"] == "image/png"
        assert content[1]["source"]["data"] == "ZmFrZS1ieXRlcw=="

    def test_data_url_becomes_base64_source(self) -> None:
        req = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [{
                "role": "user",
                "content": [{"type": "image_url", "image_url": {
                    "url": "data:image/jpeg;base64,QUFBQQ==",
                }}],
            }],
        }
        out = canonical_to_anthropic(req)
        block = out["messages"][0]["content"][0]
        assert block["type"] == "image"
        assert block["source"] == {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": "QUFBQQ==",
        }

    def test_data_url_with_charset_media_type_stripped(self) -> None:
        # data:image/png;charset=utf-8;base64,... — only the media
        # type up to the first ``;`` counts; charset extras are dropped.
        req = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [{
                "role": "user",
                "content": [{"type": "image_url", "image_url": {
                    "url": "data:image/png;charset=utf-8;base64,QUFBQQ==",
                }}],
            }],
        }
        out = canonical_to_anthropic(req)
        block = out["messages"][0]["content"][0]
        assert block["source"]["media_type"] == "image/png"

    def test_mixed_text_and_multiple_images_preserved_in_order(self) -> None:
        req = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "compare"},
                    {"type": "image_url", "image_url": {"url": "https://a/1.png"}},
                    {"type": "image_url", "image_url": {"url": "https://b/2.png"}},
                    {"type": "text", "text": "and describe"},
                ],
            }],
        }
        # Both images resolve via the fetch path — mock to keep this
        # a unit test. Verifies ordering + count survive the fetch,
        # not the fetch itself (that's covered in TestFetchGuards).
        from app.modules.guard import tools_anthropic_converter as _mod
        calls: list[str] = []
        def _fake_fetch(url):
            calls.append(url)
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": f"data-{len(calls)}",
                },
            }
        # monkeypatch is unavailable here (this test method doesn't
        # take the fixture); patch on the module directly and restore.
        _orig = _mod._fetch_and_encode_image
        _mod._fetch_and_encode_image = _fake_fetch
        try:
            out = canonical_to_anthropic(req)
        finally:
            _mod._fetch_and_encode_image = _orig
        content = out["messages"][0]["content"]
        assert [p["type"] for p in content] == ["text", "image", "image", "text"]
        # Fetch called in the same order the parts appeared.
        assert calls == ["https://a/1.png", "https://b/2.png"]
        assert content[1]["source"]["type"] == "base64"
        assert content[2]["source"]["type"] == "base64"

    def test_string_content_still_passes_through(self) -> None:
        # Baseline — non-multimodal content still works unchanged.
        req = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [{"role": "user", "content": "plain text"}],
        }
        out = canonical_to_anthropic(req)
        assert out["messages"][0] == {"role": "user", "content": "plain text"}


class TestFetchGuards:
    """Server-side HTTPS fetch guards on the vision converter."""

    def _run_fetch(self, url: str, *, mock_response=None, raises=None):
        import httpx
        from app.modules.guard import tools_anthropic_converter as _mod

        class _MockClient:
            def __init__(self, *a, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get(self, url):
                if raises is not None:
                    raise raises
                return mock_response

        orig_client = httpx.Client
        httpx.Client = _MockClient
        try:
            return _mod._fetch_and_encode_image(url)
        finally:
            httpx.Client = orig_client

    def _mock_resp(self, status: int, content_type: str, body: bytes,
                   final_url: str = "https://example.com/img"):
        class R:
            def __init__(self):
                self.status_code = status
                self.headers = {"content-type": content_type}
                self.content = body
                # The fetch code now reads ``response.url`` for the
                # post-redirect scheme check. Default to an https URL so
                # tests that don't care about redirects don't have to
                # pass one explicitly.
                self.url = final_url
        return R()

    def test_happy_path(self) -> None:
        import base64 as _b64
        out = self._run_fetch(
            "https://example.com/x.png",
            mock_response=self._mock_resp(200, "image/png", b"pixel"),
        )
        assert out["type"] == "image"
        assert out["source"]["media_type"] == "image/png"
        assert out["source"]["data"] == _b64.b64encode(b"pixel").decode("ascii")

    def test_non_https_rejected(self) -> None:
        # Defense in depth — the caller already refuses http/file, but
        # the fetch guard asserts scheme too.
        assert self._run_fetch("http://example.com/x.png") is None

    def test_4xx_response_dropped(self) -> None:
        out = self._run_fetch(
            "https://example.com/missing.png",
            mock_response=self._mock_resp(404, "image/png", b""),
        )
        assert out is None

    def test_non_image_content_type_rejected(self) -> None:
        # Server returned HTML — refuse.
        out = self._run_fetch(
            "https://example.com/oops",
            mock_response=self._mock_resp(200, "text/html", b"<html></html>"),
        )
        assert out is None

    def test_content_type_with_charset_parsed_correctly(self) -> None:
        # Real servers send ``image/png; charset=UTF-8`` on occasion.
        out = self._run_fetch(
            "https://example.com/pic.png",
            mock_response=self._mock_resp(200, "image/png; charset=UTF-8", b"px"),
        )
        assert out is not None
        assert out["source"]["media_type"] == "image/png"

    def test_oversize_body_dropped(self) -> None:
        # 20MB + 1 byte tips the cap.
        from app.modules.guard.tools_anthropic_converter import _IMAGE_FETCH_MAX_BYTES
        out = self._run_fetch(
            "https://example.com/big.png",
            mock_response=self._mock_resp(200, "image/png", b"x" * (_IMAGE_FETCH_MAX_BYTES + 1)),
        )
        assert out is None

    def test_network_error_dropped_not_raised(self) -> None:
        import httpx
        out = self._run_fetch(
            "https://example.com/timeout.png",
            raises=httpx.ConnectTimeout("simulated"),
        )
        assert out is None

    def test_bad_content_dropped_not_raised(self) -> None:
        # Any exception during fetch — no exception escapes.
        out = self._run_fetch(
            "https://example.com/x.png",
            raises=ValueError("garbage"),
        )
        assert out is None

    def _mock_resp_with_url(self, status, content_type, body, final_url):
        class R:
            def __init__(self):
                self.status_code = status
                self.headers = {"content-type": content_type}
                self.content = body
                self.url = final_url
        return R()

    def test_followed_redirect_to_https_ok(self) -> None:
        # picsum.photos 302 → their CDN. httpx.Client(follow_redirects=True)
        # returns the FINAL response. Verify we accept it as long as
        # the final URL is still https and content-type is image/*.
        out = self._run_fetch(
            "https://picsum.photos/512",
            mock_response=self._mock_resp_with_url(
                200, "image/jpeg", b"jpegbytes",
                final_url="https://fastly.picsum.photos/id/1/512/512.jpg",
            ),
        )
        assert out is not None
        assert out["source"]["media_type"] == "image/jpeg"

    def test_final_url_downgraded_to_http_rejected(self) -> None:
        # A redirect chain that ends on http:// (not https://) is
        # refused post-redirect even though the initial URL was
        # https. Defense against redirect-based scheme downgrade.
        out = self._run_fetch(
            "https://example.com/img",
            mock_response=self._mock_resp_with_url(
                200, "image/png", b"px",
                final_url="http://internal.example.com/leak.png",
            ),
        )
        assert out is None
