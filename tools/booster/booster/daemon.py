"""
Booster daemon — keeps the embedding model warm and watches source files.

One process does two things:
  1. Listens on a Unix socket (.booster/daemon.sock), handles embed requests
     so MCP calls don't pay the model cold-start cost on every call.
  2. Watches source files for changes (watchdog), debounces 2s, then
     re-indexes changed files and rebuilds vectors.npy incrementally.

Start:  booster start
Stop:   booster stop
Status: booster status
"""
from __future__ import annotations

import json
import os
import signal
import socket
import threading
import time
from pathlib import Path

import numpy as np

_DEBOUNCE_S = 2.0
_SOCKET_NAME = "daemon.sock"
_PID_NAME = "daemon.pid"
_SKIP_DIRS = {"node_modules", ".venv", "__pycache__", ".git", ".booster", "worktrees", ".next", "dist", "build"}
_WATCH_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}


def _recv_line(conn: socket.socket) -> bytes:
    buf = b""
    while b"\n" not in buf:
        chunk = conn.recv(131072)
        if not chunk:
            break
        buf += chunk
    return buf.split(b"\n")[0]


class BoosterDaemon:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._booster_dir = root / ".booster"
        self._sock_path = self._booster_dir / _SOCKET_NAME
        self._pid_path = self._booster_dir / _PID_NAME
        self._pending: set[Path] = set()
        self._last_change = 0.0
        self._lock = threading.Lock()
        self._started_at = time.time()

    def _get_model(self):
        from booster.indexer import _get_embed_model
        return _get_embed_model()

    def _get_indexer(self):
        from booster.indexer import SymbolIndexer
        return SymbolIndexer(self.root)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vecs = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        vecs = vecs / norms
        return vecs.tolist()

    def _handle(self, conn: socket.socket) -> None:
        try:
            raw = _recv_line(conn)
            if not raw:
                return
            req = json.loads(raw)
            op = req.get("op")
            if op == "ping":
                resp = {"ok": True, "pid": os.getpid(),
                        "uptime": int(time.time() - self._started_at)}
            elif op == "embed":
                resp = {"vectors": self._embed(req["texts"])}
            elif op == "status":
                resp = {"pid": os.getpid(), "model": "all-MiniLM-L6-v2",
                        "uptime": int(time.time() - self._started_at),
                        "root": str(self.root)}
            else:
                resp = {"error": f"unknown op: {op}"}
            conn.sendall(json.dumps(resp).encode() + b"\n")
        except Exception:
            pass
        finally:
            conn.close()

    def _start_watcher(self) -> None:
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            return  # watchdog not installed — skip file watching

        daemon = self

        class _Handler(FileSystemEventHandler):
            def _maybe_queue(self, path_str: str) -> None:
                p = Path(path_str)
                if p.suffix not in _WATCH_EXTS:
                    return
                if any(part in _SKIP_DIRS for part in p.parts):
                    return
                with daemon._lock:
                    daemon._pending.add(p)
                    daemon._last_change = time.monotonic()

            def on_modified(self, event):
                if not event.is_directory:
                    self._maybe_queue(event.src_path)

            def on_created(self, event):
                if not event.is_directory:
                    self._maybe_queue(event.src_path)

        observer = Observer()
        observer.schedule(_Handler(), str(self.root), recursive=True)
        observer.start()

        def _reindex_worker() -> None:
            while True:
                time.sleep(0.5)
                now = time.monotonic()
                with self._lock:
                    if not self._pending:
                        continue
                    if (now - self._last_change) < _DEBOUNCE_S:
                        continue
                    paths = list(self._pending)
                    self._pending.clear()
                try:
                    indexer = self._get_indexer()
                    for p in paths:
                        try:
                            indexer.index_file(p)
                        except Exception:
                            pass
                    indexer.build_embeddings()
                except Exception:
                    pass

        t = threading.Thread(target=_reindex_worker, daemon=True)
        t.start()

    def run(self) -> None:
        self._booster_dir.mkdir(exist_ok=True)
        self._pid_path.write_text(str(os.getpid()))

        if self._sock_path.exists():
            self._sock_path.unlink()

        # Warm up the model before accepting connections
        self._get_model()

        self._start_watcher()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self._sock_path))
        server.listen(16)

        def _cleanup(sig, frame):
            server.close()
            for p in (self._sock_path, self._pid_path):
                if p.exists():
                    p.unlink()
            os._exit(0)

        signal.signal(signal.SIGTERM, _cleanup)
        signal.signal(signal.SIGINT, _cleanup)

        while True:
            try:
                conn, _ = server.accept()
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
            except OSError:
                break


# ── Public helpers used by indexer + CLI ─────────────────────────────────────

def daemon_embed(texts: list[str], root: Path) -> "np.ndarray | None":
    """Send embed request to running daemon. Returns None if daemon unavailable."""
    sock_path = root / ".booster" / _SOCKET_NAME
    if not sock_path.exists():
        return None
    try:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(5.0)
        conn.connect(str(sock_path))
        conn.sendall(json.dumps({"op": "embed", "texts": texts}).encode() + b"\n")
        raw = _recv_line(conn)
        conn.close()
        result = json.loads(raw)
        if "vectors" in result:
            return np.array(result["vectors"], dtype=np.float32)
    except Exception:
        pass
    return None


def daemon_ping(root: Path) -> dict | None:
    """Ping the daemon. Returns status dict or None if not running."""
    sock_path = root / ".booster" / _SOCKET_NAME
    if not sock_path.exists():
        return None
    try:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(2.0)
        conn.connect(str(sock_path))
        conn.sendall(json.dumps({"op": "ping"}).encode() + b"\n")
        raw = _recv_line(conn)
        conn.close()
        return json.loads(raw)
    except Exception:
        return None


def start_daemon(root: Path) -> "bool | str":
    """Launch daemon in background. Returns True if started, False if already running, error string on failure."""
    if daemon_ping(root) is not None:
        return False  # already running
    import subprocess, sys
    booster_dir = root / ".booster"
    booster_dir.mkdir(exist_ok=True)
    log_path = booster_dir / "daemon.log"
    log_file = open(log_path, "w")
    subprocess.Popen(
        [sys.executable, "-m", "booster.daemon", str(root)],
        start_new_session=True,
        stdout=log_file,
        stderr=log_file,
    )
    # Wait up to 5s for it to be ready
    for _ in range(20):
        time.sleep(0.25)
        if daemon_ping(root) is not None:
            log_file.close()
            return True
    log_file.close()
    tail = log_path.read_text().strip()[-800:] if log_path.exists() else ""
    return tail or "unknown error"


def stop_daemon(root: Path) -> bool:
    """Stop running daemon. Returns True if stopped."""
    pid_path = root / ".booster" / _PID_NAME
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        # Wait up to 3s for clean exit
        for _ in range(12):
            time.sleep(0.25)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
        return True
    except (ValueError, ProcessLookupError):
        pid_path.unlink(missing_ok=True)
        return False


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python -m booster.daemon <root>", file=sys.stderr)
        sys.exit(1)
    BoosterDaemon(Path(sys.argv[1])).run()
