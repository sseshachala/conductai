"""Unit tests for #2166 PR 1 — vision (image_url) content-part validation.

Pure-module tests, no HTTP layer. The shim wire-in is exercised at
integration test time; here we only pin the contract every call path
depends on.
"""
from __future__ import annotations

import base64

import pytest

from app.modules.guard.vision_validator import (
    MAX_DATA_URL_DECODED_BYTES,
    MAX_IMAGES_PER_MESSAGE,
    VisionValidationFailure,
    count_images,
    validate_content_parts,
)


# ─── helpers ────────────────────────────────────────────────────────


def _text(s: str) -> dict:
    return {"type": "text", "text": s}


def _https(url: str = "https://example.com/img.png", **extra) -> dict:
    img: dict = {"url": url}
    img.update(extra)
    return {"type": "image_url", "image_url": img}


def _data_url(size_bytes: int, media: str = "png") -> str:
    # base64 inflates by ~4/3; a payload of 4/3*size chars decodes to
    # roughly size bytes. Use a valid base64 alphabet so the payload
    # passes the base64.b64decode(validate=True) check.
    raw = b"A" * size_bytes
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/{media};base64,{encoded}"


# ─── validate_content_parts happy path ─────────────────────────────


class TestValidateContentPartsHappyPath:
    def test_single_text_part(self) -> None:
        validate_content_parts([_text("hello")], message_index=0)

    def test_single_https_image(self) -> None:
        validate_content_parts([_https()], message_index=0)

    def test_mixed_text_and_image(self) -> None:
        validate_content_parts(
            [_text("What's in this image?"), _https()],
            message_index=0,
        )

    def test_valid_data_url(self) -> None:
        url = _data_url(1024)  # 1KB
        validate_content_parts([_https(url=url)], message_index=0)

    @pytest.mark.parametrize("detail", ["auto", "low", "high"])
    def test_valid_detail_options(self, detail: str) -> None:
        validate_content_parts(
            [_https(detail=detail)],
            message_index=0,
        )


# ─── validate_content_parts rejection path ─────────────────────────


class TestValidateContentPartsRejections:
    def test_non_list_rejected(self) -> None:
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts("hello", message_index=0)  # type: ignore[arg-type]
        assert e.value.field == "messages[0].content"

    def test_empty_list_rejected(self) -> None:
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts([], message_index=0)
        assert "at least one part" in e.value.reason

    def test_non_dict_part_rejected(self) -> None:
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts(["not a dict"], message_index=0)  # type: ignore[list-item]
        assert e.value.field == "messages[0].content[0]"

    def test_unknown_type_rejected(self) -> None:
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts(
                [{"type": "video_url", "video_url": {"url": "x"}}],
                message_index=0,
            )
        assert e.value.field == "messages[0].content[0].type"

    def test_text_part_missing_text_rejected(self) -> None:
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts(
                [{"type": "text"}],  # no "text" key
                message_index=1,
            )
        assert e.value.field == "messages[1].content[0].text"


# ─── URL scheme allowlist (security-critical) ──────────────────────


class TestUrlSchemeAllowlist:
    def test_http_url_rejected(self) -> None:
        # SSRF + unencrypted-transfer risk.
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts(
                [_https(url="http://example.com/img.png")],
                message_index=0,
            )
        assert "unsupported URL scheme" in e.value.reason
        assert "http" in e.value.reason

    def test_file_url_rejected(self) -> None:
        # Local-file exfiltration from the gateway host.
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts(
                [_https(url="file:///etc/passwd")],
                message_index=0,
            )
        assert "unsupported URL scheme" in e.value.reason

    @pytest.mark.parametrize("url", [
        "ftp://example.com/img.png",
        "s3://bucket/img.png",
        "javascript:alert(1)",
        "/etc/passwd",
        "just-a-string",
        "data:application/pdf;base64,xxx",   # data URL but not image/*
        "data:text/plain;base64,xxx",
        "  https://example.com/img.png",     # leading whitespace not stripped
    ])
    def test_other_schemes_rejected(self, url: str) -> None:
        with pytest.raises(VisionValidationFailure):
            validate_content_parts([_https(url=url)], message_index=0)


# ─── data URL caps ────────────────────────────────────────────────


class TestDataUrlSizeCap:
    def test_small_data_url_ok(self) -> None:
        validate_content_parts(
            [_https(url=_data_url(1024))],
            message_index=0,
        )

    def test_near_limit_data_url_ok(self) -> None:
        # A payload just under the cap must pass. Using -1024 (not the
        # exact cap) because base64 padding + integer math makes the
        # approx-decoded estimate slightly conservative — testing that
        # a legitimate near-limit image doesn't get rejected.
        validate_content_parts(
            [_https(url=_data_url(MAX_DATA_URL_DECODED_BYTES - 1024))],
            message_index=0,
        )

    def test_oversize_data_url_rejected(self) -> None:
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts(
                [_https(url=_data_url(MAX_DATA_URL_DECODED_BYTES + 1024))],
                message_index=0,
            )
        assert "too large" in e.value.reason

    def test_non_base64_data_url_rejected(self) -> None:
        # data:image/png,<raw> without ;base64, is legal per RFC 2397
        # but we don't support it (size math becomes ambiguous).
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts(
                [_https(url="data:image/png,rawrawraw")],
                message_index=0,
            )
        assert "base64" in e.value.reason


# ─── image count cap ──────────────────────────────────────────────


class TestImageCountCap:
    def test_at_limit_ok(self) -> None:
        parts = [_https() for _ in range(MAX_IMAGES_PER_MESSAGE)]
        validate_content_parts(parts, message_index=0)

    def test_over_limit_rejected(self) -> None:
        parts = [_https() for _ in range(MAX_IMAGES_PER_MESSAGE + 1)]
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts(parts, message_index=0)
        assert "too many images" in e.value.reason


# ─── detail parameter validation ──────────────────────────────────


class TestDetailParameter:
    def test_omitted_is_ok(self) -> None:
        # No "detail" key = defaults to auto upstream.
        validate_content_parts([_https()], message_index=0)

    def test_invalid_detail_rejected(self) -> None:
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts(
                [_https(detail="ultra")],
                message_index=0,
            )
        assert "detail" in e.value.field
        assert "auto" in e.value.reason


# ─── https URL length sanity check ────────────────────────────────


class TestHttpsUrlLengthCap:
    def test_long_https_url_rejected(self) -> None:
        # 2049-char URL trips the length sanity cap.
        long_url = "https://example.com/" + ("x" * (2049 - len("https://example.com/")))
        assert len(long_url) == 2049
        with pytest.raises(VisionValidationFailure) as e:
            validate_content_parts(
                [_https(url=long_url)],
                message_index=0,
            )
        assert "too long" in e.value.reason


# ─── count_images helper (used by PR 2 estimator) ─────────────────


class TestCountImages:
    def test_zero_for_string_content(self) -> None:
        assert count_images("plain text") == 0

    def test_zero_for_none_content(self) -> None:
        assert count_images(None) == 0

    def test_counts_only_image_parts(self) -> None:
        content = [_text("caption"), _https(), _https(), _text("more caption")]
        assert count_images(content) == 2

    def test_zero_for_text_only_multimodal(self) -> None:
        content = [_text("a"), _text("b")]
        assert count_images(content) == 0
