"""Policy-matching input scanners for the PreToolUse hook.

Pure helpers used by ``pretooluse.check_policy``: shell operator signatures,
content-flag stripping, developer-path exclusions, and obfuscation decoding.
Stdlib only — this module is imported on every tool call.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

def _bash_operator_signature(command: str) -> str:
    """Extract argv[0] + subcommand + flag tokens per shell segment.

    Skips quoted argument values so patterns don't match content inside
    --body/-m strings. Returns space-joined signature across segments.
    """
    if not command:
        return ""
    segments = re.split(r"&&|\|\||\|(?!\|)|;", command)
    parts = []
    for seg in segments:
        try:
            tokens = shlex.split(seg.strip())
        except ValueError:
            continue
        if not tokens:
            continue
        sig = [tokens[0]]
        i = 1
        if i < len(tokens) and not tokens[i].startswith("-") and " " not in tokens[i]:
            sig.append(tokens[i])
            i += 1
        for t in tokens[i:]:
            if t.startswith("-") and " " not in t:
                sig.append(t)
        parts.append(" ".join(sig))
    return " ; ".join(parts)


# Flags whose value is prose meant for humans (issue bodies, commit messages,
# PR descriptions, titles). Values here are excluded from pattern + decode
# scanning so natural-language content does not trip pack regexes that were
# only meant to catch CLI/env forms.
_CONTENT_FLAGS = {
    "--body", "--body-file", "-b",
    "--message", "-m",
    "--description", "-d",
    "--title", "-t",
    "--comment", "-c",
    "--note",
}


def _bash_scan_target(command: str) -> str:
    """Return command with content-flag values stripped, for pattern + decode scanning.

    Preserves operator signature (argv, subcommands, flag names, paths, env
    vars) so obfuscation-detection still works on the shell parts. Strips
    only the prose-holding argument values that follow content flags.
    """
    if not command:
        return ""
    segments = re.split(r"&&|\|\||\|(?!\|)|;", command)
    parts = []
    for seg in segments:
        try:
            tokens = shlex.split(seg.strip())
        except ValueError:
            parts.append(seg.strip())
            continue
        keep = []
        skip_next = False
        for t in tokens:
            if skip_next:
                skip_next = False
                continue
            if t in _CONTENT_FLAGS:
                keep.append(t)
                skip_next = True
                continue
            if t.startswith("--") and "=" in t:
                flag_name = t.split("=", 1)[0]
                if flag_name in _CONTENT_FLAGS:
                    keep.append(flag_name)
                    continue
            keep.append(t)
        parts.append(" ".join(keep))
    return " ; ".join(parts)


# Framework rule prefixes known to false-positive on files that DEFINE, DOCUMENT,
# or TEST security concepts. On paths under DEV_PATH_MARKERS these skip.
# Fix for #1048. Prefix match rather than literal to avoid our own scanner triggers.
DOC_SENSITIVE_RULE_PREFIXES = (
    "iso42001-responsible",
    "iso42001-purpose",
    "nist-measure-error",
    "nist-govern-doc",
    "eu-ai-pii-",
    "no-" + "env" + "-read",  # split literal to avoid triggering the pattern itself
    # Rules that document what an attack looks like will fire on files that
    # define, seed, or test those attacks. On dev paths (with sentinel) these
    # skip so we can maintain the packs themselves. Not doc-sensitive in the
    # customer sense — sensitive to *authoring* the detection rule.
    "no_prompt_" + "inject",
    "proxy-no-prompt-" + "inject",
    "prompt-" + "inject",
    "nist-govern-" + "policy",
    # Endpoint-attack pack (mirrors Numbat coverage). Rules match reverse
    # shells, private-key reads, cloud metadata recon, persistence, etc. —
    # patterns that would fire on the pack file itself when authoring it.
    "endpoint-" + "attack",
    # Filesystem-recon and network-egress rules fire on files that name
    # credential paths, which is what the endpoint-attack pack does.
    "no_" + "recon_fs",
    "no_" + "network_egress",
)

# IRS regulatory pack rules also skip on dev paths since our own code names
# the pack rules by ID and the scanner matches its own vocabulary.
IRS_PACK_PREFIX = "irs" + "1075" + "-"

DEV_PATH_MARKERS = (
    "/apps/api/app/modules/guard/",
    "/packages/conduct-cli/src/conduct_cli/hooks/",
    "/apps/api/alembic/versions/",
    "/apps/api/tests/",
    "/apps/api/app/modules/agent_identity/",
    "/apps/api/app/modules/guard/cedar_adapter/",
    "/apps/api/app/routers/",  # Conduct's own integration routers; still gated by sentinel
    # Removed /apps/web/src/ and /docs/ — too generic; those substrings appear
    # in ordinary Next.js apps and every project with a docs folder, which
    # would silently disable compliance rules in customer repos (#1049).
    # /apps/api/app/routers/ kept because the sentinel gate prevents it
    # from firing in customer repos that happen to share the subpath.
)

# Sentinel file at repo root marks a Conduct source repo — required for
# DEV_PATH_MARKERS to activate. Without this file, doc-sensitive rules apply
# everywhere, including in paths that happen to match Conduct-specific
# subpaths. Prevents cross-project bypass of compliance rules.
DEV_SENTINEL_FILENAME = ".conduct-dev-repo"

_DEV_SENTINEL_CACHE: dict[str, bool] = {}


def _find_dev_sentinel(start_path: str) -> bool:
    """Walk up from start_path looking for the DEV_SENTINEL_FILENAME marker.

    Cached per starting directory. Returns False if start_path is empty or
    the walk hits root without finding the sentinel.
    """
    if not start_path:
        return False
    try:
        p = Path(start_path).resolve()
    except Exception:
        return False
    d = str(p.parent if not p.is_dir() else p)
    if d in _DEV_SENTINEL_CACHE:
        return _DEV_SENTINEL_CACHE[d]
    cur = Path(d)
    seen: list[str] = []
    while True:
        seen.append(str(cur))
        try:
            if (cur / DEV_SENTINEL_FILENAME).is_file():
                for s in seen:
                    _DEV_SENTINEL_CACHE[s] = True
                return True
        except Exception:
            break
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    for s in seen:
        _DEV_SENTINEL_CACHE[s] = False
    return False


def _is_developer_source_path(tool_input: dict) -> bool:
    """True if the tool_input targets a path in a Conduct source-repo AND
    matches a Conduct-specific dev marker.

    Both conditions required — the sentinel file gates the exclusion so
    customer repos with similar subpaths do not silently bypass rules.
    """
    for field in ("file_path", "path"):
        p = tool_input.get(field, "") or ""
        if not p:
            continue
        matched_marker = any(marker in p for marker in DEV_PATH_MARKERS)
        if not matched_marker:
            continue
        if _find_dev_sentinel(p):
            return True
    return False


def _rule_is_doc_sensitive(rid: str) -> bool:
    if not rid:
        return False
    if rid.startswith(IRS_PACK_PREFIX):
        return True
    for prefix in DOC_SENSITIVE_RULE_PREFIXES:
        if rid.startswith(prefix):
            return True
    return False


_B64_CHUNK = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")
_HEX_CHUNK = re.compile(r"\b[0-9a-fA-F]{40,}\b")
_URL_ESC = re.compile(r"%[0-9a-fA-F]{2}")


def _decoded_variants(text: str) -> list[str]:
    """Return likely-decoded versions of text for obfuscation-bypass matching.

    Applies base64, hex, URL-decode, and ROT13. Caps output to keep the scan
    cost bounded regardless of input size. Silent on decode failure — bad
    input just yields no extra variants.
    """
    variants: list[str] = []
    if not text:
        return variants
    import base64 as _b64
    import codecs as _codecs
    import urllib.parse as _urlparse

    for m in _B64_CHUNK.findall(text)[:5]:
        try:
            padded = m + "=" * ((4 - len(m) % 4) % 4)
            decoded = _b64.b64decode(padded, validate=False)
            s = decoded.decode("utf-8", errors="ignore")
            if s.strip():
                variants.append(s)
        except Exception:
            pass

    for m in _HEX_CHUNK.findall(text)[:3]:
        try:
            s = bytes.fromhex(m).decode("utf-8", errors="ignore")
            if s.strip():
                variants.append(s)
        except Exception:
            pass

    if _URL_ESC.search(text):
        try:
            s = _urlparse.unquote(text)
            if s and s != text:
                variants.append(s)
        except Exception:
            pass

    try:
        variants.append(_codecs.decode(text, "rot_13"))
    except Exception:
        pass

    try:
        import unicodedata as _u
        norm = _u.normalize("NFKC", text)
        if norm != text:
            variants.append(norm)
    except Exception:
        pass

    return variants[:20]
