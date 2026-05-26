import json
import sys
import urllib.request
import urllib.error

RED   = "\033[31m"
RESET = "\033[0m"
DEV_WORKSPACE = "00000000-0000-0000-0000-000000000001"


def headers(workspace_id: str, token=None, content_type="application/json", api_key=None) -> dict:
    h = {"Content-Type": content_type, "X-Workspace-Id": workspace_id}
    if api_key:
        h["X-Api-Key"] = api_key
    elif token:
        h["Authorization"] = f"Bearer {token}"
    return h


def req(method: str, url: str, hdrs: dict, body=None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw).get("detail", raw)
        except Exception:
            detail = raw
        print(f"{RED}HTTP {e.code}: {detail}{RESET}")
        sys.exit(1)


def req_text(method: str, url: str, hdrs: dict, body_text: str) -> dict:
    r = urllib.request.Request(url, data=body_text.encode(), headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw).get("detail", raw)
        except Exception:
            detail = raw
        print(f"{RED}HTTP {e.code}: {detail}{RESET}")
        sys.exit(1)


def stream(url: str, hdrs: dict | None = None):
    """Yield parsed SSE data dicts."""
    r = urllib.request.Request(url, headers=hdrs or {})
    try:
        resp = urllib.request.urlopen(r)
    except urllib.error.HTTPError as e:
        print(f"{RED}Stream {e.code}: {e.read().decode()}{RESET}")
        sys.exit(1)

    buf = b""
    while True:
        chunk = resp.read(1)
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
