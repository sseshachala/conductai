"""Drain daemon round-trip smoke — mock POST server + real ensure_drain_daemon.

Called from .github/workflows/cli-smoke-windows.yml. Exits nonzero if the daemon
does not POST an event to the local mock server within 15 seconds.
"""
import http.server
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
            received.append(self.rfile.read(length))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a, **kw):
            pass

    srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    base.JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    base.journal_append('{"kind":"smoke_test"}', f"http://127.0.0.1:{port}/events")

    hook_py = Path.home() / ".conduct" / "hook.py"
    if not hook_py.exists():
        print(f"FAIL: hook.py missing at {hook_py}", file=sys.stderr)
        return 1
    base.ensure_drain_daemon(hook_module_path=hook_py)

    for _ in range(30):
        if received:
            break
        time.sleep(0.5)
    srv.shutdown()

    if not received:
        print("FAIL: drain daemon did not POST within 15s", file=sys.stderr)
        return 1
    print(f"OK - mock server received {len(received)} event(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
