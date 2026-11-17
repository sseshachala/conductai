"""Drain daemon round-trip smoke — mock POST server + real ensure_drain_daemon.

Called from .github/workflows/cli-smoke-windows.yml. Exits nonzero if the daemon
does not POST an event to the local mock server within 15 seconds.

The daemon only delivers journal entries addressed to the configured API origin
and posts them with the configured agent token (#1927), so config.json is pointed
at the mock server for the duration of the check and restored afterwards.
"""
import http.server
import json
import socketserver
import sys
import threading
import time
from pathlib import Path

from conduct_cli.hooks import base


def main() -> int:
    received: list[bytes] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length)
            if self.path == "/guard/events" and self.headers.get("Authorization", "").startswith("Bearer "):
                received.append(body)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a, **kw):
            pass

    srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    mock_origin = f"http://127.0.0.1:{port}"
    original_config = base.CONFIG_PATH.read_text()
    cfg = json.loads(original_config)
    cfg["api_url"] = mock_origin
    base.CONFIG_PATH.write_text(json.dumps(cfg))
    try:
        base.JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        base.journal_append('{"kind":"smoke_test"}', mock_origin, "/guard/events")

        hook_py = Path.home() / ".conduct" / "hook.py"
        if not hook_py.exists():
            print(f"FAIL: hook.py missing at {hook_py}", file=sys.stderr)
            return 1
        base.ensure_drain_daemon(hook_module_path=hook_py)

        for _ in range(30):
            if received:
                break
            time.sleep(0.5)
    finally:
        base.CONFIG_PATH.write_text(original_config)
        srv.shutdown()

    if not received:
        print("FAIL: drain daemon did not POST within 15s", file=sys.stderr)
        return 1
    print(f"OK - mock server received {len(received)} event(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
