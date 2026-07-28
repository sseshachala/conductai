import json
import socket
import sys
import urllib.request
import urllib.error

RED   = "\033[31m"
RESET = "\033[0m"

_HINTS = {
    401: "run `conduct login` to re-authenticate",
    403: "check your permissions or run `conduct login`",
    404: "not found — check the agent name or run ID",
    429: "rate limited — wait a moment and try again",
}


def _friendly(code: int, detail: str) -> str:
    hint = _HINTS.get(code)
    if hint and hint.lower() not in detail.lower():
        return f"{detail} — {hint}"
    return detail


def headers(workspace_id: str, token=None, content_type="application/json") -> dict:
    h = {"Content-Type": content_type, "X-Workspace-Id": workspace_id}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def req(method: str, url: str, hdrs: dict, body=None, timeout: int = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw).get("detail", raw)
        except Exception:
            detail = raw
        print(f"{RED}{_friendly(e.code, detail)}{RESET}")
        sys.exit(1)
    except (socket.timeout, TimeoutError):
        print(f"{RED}Request timed out — check your network connection{RESET}")
        sys.exit(1)


def req_text(method: str, url: str, hdrs: dict, body_text: str, timeout: int = 30) -> dict:
    r = urllib.request.Request(url, data=body_text.encode(), headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw).get("detail", raw)
        except Exception:
            detail = raw
        print(f"{RED}{_friendly(e.code, detail)}{RESET}")
        sys.exit(1)
    except (socket.timeout, TimeoutError):
        print(f"{RED}Request timed out — check your network connection{RESET}")
        sys.exit(1)


def stream(url: str, hdrs=None):
    """Yield parsed SSE data dicts.

    Uses a socket read timeout to detect stalled streams. Server sends
    ': keepalive' pings every 15s, so a 60s timeout is safe.
    """
    r = urllib.request.Request(url, headers=hdrs or {})
    try:
        resp = urllib.request.urlopen(r, timeout=60)
    except urllib.error.HTTPError as e:
        msg = e.read().decode()
        raise RuntimeError(f"Stream {e.code}: {msg}")

    buf = b""
    while True:
        try:
            chunk = resp.read(1)
        except socket.timeout:
            raise RuntimeError(
                "Stream stalled (no data for 60s). The run may still be executing on the server — "
                "check `conduct runs list` or the UI."
            )
        if not chunk:
            break
        buf += chunk
        if buf.endswith(b"\n\n"):
            text = buf.decode().strip()
            buf  = b""
            event = "message"
            for line in text.splitlines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        data = {"raw": line[5:].strip()}
                    data.setdefault("kind", event)
                    yield data
            event = "message"


def find_or_create_workflow(server: str, name: str, hdrs: dict) -> str:
    for wf in req("GET", f"{server}/workflows", hdrs):
        if wf["name"] == name:
            return wf["id"]
    wf = req("POST", f"{server}/workflows", hdrs, {
        "name": name,
        "graph": {"nodes": [], "edges": []},
    })
    return wf["id"]
