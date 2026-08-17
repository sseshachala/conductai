"""Input normalization pipeline for Guard rule matching.

Strips zero-width chars, normalises Unicode homoglyphs, decodes Base64 blocks,
and detects ROT13. Rules matched against normalised variants catch subtle
evasions that per-rule regex on raw text would miss.

Constants and functions ported (with adaptation) from
poojakira/mcp-agent-security-gateway (MIT). See CAPABILITY_INVENTORY.md.
"""
from __future__ import annotations

import base64
import codecs
import re
import unicodedata
from dataclasses import dataclass, field


ZERO_WIDTH_CHARS: frozenset[str] = frozenset({
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\ufeff",  # byte order mark / zero-width no-break space
    "\u2060",  # word joiner
    "\u180e",  # mongolian vowel separator
    "\u200e",  # left-to-right mark
    "\u200f",  # right-to-left mark
})

BIDI_CHARS: frozenset[str] = frozenset({
    "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
    "\u2066", "\u2067", "\u2068", "\u2069",
})

_STRIP_CHARS: frozenset[str] = ZERO_WIDTH_CHARS | BIDI_CHARS

HOMOGLYPH_MAP: dict[str, str] = {
    # Cyrillic lookalikes
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
    "\u0441": "c", "\u0443": "y", "\u0445": "x", "\u0456": "i",
    "\u0458": "j", "\u04bb": "h",
    "\u0410": "A", "\u0412": "B", "\u0415": "E", "\u041a": "K",
    "\u041c": "M", "\u041d": "H", "\u041e": "O", "\u0420": "P",
    "\u0421": "C", "\u0422": "T", "\u0425": "X",
    # Greek lookalikes
    "\u03b1": "a", "\u03bf": "o", "\u03c1": "p", "\u03b5": "e",
    "\u0391": "A", "\u0392": "B", "\u0395": "E", "\u0397": "H",
    "\u0399": "I", "\u039a": "K", "\u039c": "M", "\u039d": "N",
    "\u039f": "O", "\u03a1": "P", "\u03a4": "T", "\u03a5": "Y",
    "\u03a7": "X",
    # Dashes normalised to ASCII hyphen
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
}

_BASE64_BLOCK_RE = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")

_ROT13_MARKERS = re.compile(
    r"(vtaber|sbetrg|flfgrz|bireevqr|olcnff|qvfertneq|eriyrny|cebzcg|vafgehpgvbaf)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Variant:
    """One text variant produced by the normaliser.

    `text` is the transformed content. `transforms` names the transformers
    that fired (empty for the raw pass-through). `source` marks how the
    text was reached — original, base64-decoded, or rot13-decoded.
    """
    text: str
    transforms: tuple[str, ...] = field(default_factory=tuple)
    source: str = "original"


def strip_evasion_chars(text: str) -> str:
    """Remove zero-width and bidi override characters."""
    if not text:
        return text
    return "".join(ch for ch in text if ch not in _STRIP_CHARS)


def normalize_homoglyphs(text: str) -> str:
    """Apply NFKC then explicit Cyrillic/Greek homoglyph map."""
    if not text:
        return text
    text = unicodedata.normalize("NFKC", text)
    return "".join(HOMOGLYPH_MAP.get(ch, ch) for ch in text)


def decode_base64_blocks(text: str) -> list[str]:
    """Find and decode long Base64-looking blocks that yield printable UTF-8."""
    decoded: list[str] = []
    for m in _BASE64_BLOCK_RE.finditer(text):
        candidate = m.group(0)
        pad = (-len(candidate)) % 4
        padded = candidate + "=" * pad
        try:
            raw = base64.b64decode(padded, validate=True)
            result = raw.decode("utf-8", errors="strict")
        except (ValueError, UnicodeDecodeError):
            continue
        if len(result) < 4:
            continue
        printable = sum(1 for c in result if c.isprintable() or c.isspace())
        if printable / len(result) > 0.7:
            decoded.append(result)
    return decoded


def decode_rot13_if_marked(text: str) -> str | None:
    """If ROT13 markers are present, return the ROT13-decoded text."""
    if _ROT13_MARKERS.search(text):
        return codecs.decode(text, "rot_13")
    return None


def normalize(text: str) -> list[Variant]:
    """Full pipeline. Returns variants a rule matcher should scan.

    Order:
      1. Original (untouched) — so anomaly-pattern rules still fire
      2. Stripped + homoglyph-normalised
      3. Each Base64 block that decodes to printable UTF-8 (normalised)
      4. ROT13-decoded (if marker phrases suggest ROT13 obfuscation)

    Callers should short-circuit on first match. Empty input → single
    empty Variant.
    """
    if not text:
        return [Variant(text=text)]

    variants: list[Variant] = [Variant(text=text)]

    stripped = strip_evasion_chars(text)
    normalized = normalize_homoglyphs(stripped)
    if normalized != text:
        applied: list[str] = []
        if stripped != text:
            applied.append("strip_evasion_chars")
        if normalized != stripped:
            applied.append("normalize_homoglyphs")
        variants.append(Variant(text=normalized, transforms=tuple(applied)))

    for decoded in decode_base64_blocks(normalized):
        inner = normalize_homoglyphs(strip_evasion_chars(decoded))
        variants.append(Variant(
            text=inner,
            transforms=("base64_decode", "normalize_homoglyphs"),
            source="base64_decoded",
        ))

    rot13 = decode_rot13_if_marked(normalized)
    if rot13:
        variants.append(Variant(
            text=rot13,
            transforms=("rot13_decode",),
            source="rot13_decoded",
        ))

    return variants
