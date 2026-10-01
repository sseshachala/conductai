"""Online, one-shot fixture approval. No cache and no changes to installed rules."""

import hashlib
import json
from pathlib import Path
from uuid import UUID
import urllib.parse
import urllib.request

from conduct_cli.deployment import api_url
from conduct_cli.hooks.base import load_config


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fingerprint(tool_name, tool_input, cwd):
    """Bind the complete structured edit and resolved test path, not a substring."""
    if not isinstance(tool_name, str):
        raise ValueError("A tool name is required")
    name = tool_name.lower().rsplit(".", 1)[-1]
    if name not in {"write", "edit", "apply_patch"} or not isinstance(tool_input, dict):
        raise ValueError("Only structured single-file test writes can be reviewed")
    root = Path(cwd)
    if not root.is_absolute():
        raise ValueError("An absolute working directory is required")
    if name == "apply_patch":
        patch = (
            tool_input.get("patch")
            or tool_input.get("input")
            or tool_input.get("command")
        )
        if not isinstance(patch, str):
            raise ValueError("A structured patch is required")
        lines = patch.splitlines()
        if not lines or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
            raise ValueError("A complete patch is required")
        operations = [
            line
            for line in lines
            if line.startswith(
                (
                    "*** Add File: ",
                    "*** Update File: ",
                    "*** Delete File: ",
                    "*** Move to: ",
                )
            )
        ]
        if len(operations) != 1 or not operations[0].startswith(
            ("*** Add File: ", "*** Update File: ")
        ):
            raise ValueError("Only one test file may be changed")
        path = operations[0].split(": ", 1)[1]
    else:
        path = tool_input.get("file_path") or tool_input.get("path")
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ValueError("A target test file is required")
    target = (root / path).resolve()
    if not {"tests", "test", "__tests__"}.intersection(target.parts):
        raise ValueError("Fixture approval is restricted to test directories")
    payload = {
        "version": 1,
        "tool_name": tool_name.lower(),
        "tool_input": tool_input,
        "cwd": str(root.resolve()),
        "target": str(target),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    if len(encoded) > 256 * 1024:
        raise ValueError("Fixture edit exceeds review limits")
    return hashlib.sha256(encoded).hexdigest()


def consume(tool_name, tool_input, cwd):
    """Unavailable, mismatched, expired or malformed responses never relax a block."""
    try:
        digest = fingerprint(tool_name, tool_input, cwd)
        cfg = load_config()
        workspace = str(UUID(cfg["workspace_id"]))
        token = cfg.get("agent_token")
        if not token:
            return False
        url = (
            api_url(cfg)
            + "/guard/fixture-approvals/consume?"
            + urllib.parse.urlencode({"workspace_id": workspace})
        )
        request = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps({"action_digest": digest}).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
            },
        )
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(request, timeout=3) as response:
            if response.status != 200:
                return False
            result = json.loads(response.read(4097))
        return (
            result.get("approved") is True
            and result.get("action_digest") == digest
            and result.get("rule_id") == "no-private-key"
            and bool(UUID(result["id"]))
        )
    except Exception:
        return False
