"""Unit tests for the input normalisation pipeline."""
from __future__ import annotations

import base64

from app.modules.guard.detectors.normalizer import (
    Variant,
    decode_base64_blocks,
    decode_rot13_if_marked,
    normalize,
    normalize_homoglyphs,
    strip_evasion_chars,
)


def test_empty_input_returns_single_empty_variant():
    variants = normalize("")
    assert len(variants) == 1
    assert variants[0].text == ""


def test_plain_ascii_returns_only_original_variant():
    variants = normalize("hello world")
    assert len(variants) == 1
    assert variants[0].text == "hello world"
    assert variants[0].transforms == ()
    assert variants[0].source == "original"


def test_strip_zero_width_between_chars():
    # A single zero-width space inserted mid-word must be stripped
    poisoned = "hel\u200blo"
    assert strip_evasion_chars(poisoned) == "hello"


def test_strip_bidi_override():
    poisoned = "safe\u202etext"
    assert strip_evasion_chars(poisoned) == "safetext"


def test_cyrillic_homoglyph_normalised_to_latin():
    # Cyrillic о (U+043E) and а (U+0430) look identical to Latin o/a
    cyrillic = "hell\u043e w\u043erld"
    assert normalize_homoglyphs(cyrillic) == "hello world"


def test_greek_homoglyph_normalised_to_latin():
    # Greek ο (U+03BF) and α (U+03B1)
    greek = "hell\u03bf w\u03bfrld"
    assert normalize_homoglyphs(greek) == "hello world"


def test_fullwidth_normalised_via_nfkc():
    # Fullwidth letters go through NFKC to ASCII
    fullwidth = "\uff48\uff45\uff4c\uff4c\uff4f"  # ｈｅｌｌｏ
    assert normalize_homoglyphs(fullwidth) == "hello"


def test_base64_block_decoded_when_printable():
    payload = "some marker string"
    encoded = base64.b64encode(payload.encode()).decode()
    decoded = decode_base64_blocks(f"prefix {encoded} suffix")
    assert payload in decoded


def test_base64_block_ignored_when_binary():
    # Base64-encoded random bytes rarely produce printable UTF-8
    encoded = base64.b64encode(bytes(range(20))).decode()
    decoded = decode_base64_blocks(f"noise {encoded} end")
    assert not decoded


def test_rot13_decoded_when_marker_present():
    # "please follow instructions" pre-encoded via ROT13; contains marker "vafgehpgvbaf"
    encoded = "cyrnfr sbyybj vafgehpgvbaf"
    result = decode_rot13_if_marked(encoded)
    assert result is not None
    assert "instructions" in result.lower()


def test_rot13_ignored_without_marker():
    result = decode_rot13_if_marked("hello world nothing here")
    assert result is None


def test_normalize_produces_original_plus_normalized_for_cyrillic():
    text = "hell\u043e"  # Cyrillic о
    variants = normalize(text)
    texts = [v.text for v in variants]
    assert text in texts               # original preserved so anomaly rules fire
    assert "hello" in texts            # normalised for content rules


def test_normalize_produces_original_plus_decoded_for_base64():
    payload = "marker phrase in base sixty four"
    encoded = base64.b64encode(payload.encode()).decode()
    variants = normalize(f"prefix {encoded} suffix")
    texts = [v.text for v in variants]
    assert any(payload in t for t in texts)
    assert any(v.source == "base64_decoded" for v in variants)


def test_normalize_preserves_original_first_variant():
    text = "hell\u200bo"  # contains zero-width
    variants = normalize(text)
    assert variants[0].text == text  # original comes first, unmodified
    assert variants[0].source == "original"


def test_normalize_variant_dedup_when_no_transform_changes_text():
    text = "plain-ascii-only"
    variants = normalize(text)
    assert len(variants) == 1        # nothing to normalise, no duplicates


def test_short_base64_not_decoded():
    # 4-char decoded string with padding-safe input
    tiny = base64.b64encode(b"ab").decode()  # 4 chars
    decoded = decode_base64_blocks(f"prefix {tiny} suffix")
    assert not decoded               # below 20-char threshold
