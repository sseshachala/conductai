"""Disposable real HTTP fixtures shared by the adapter and Gateway harnesses."""
import json
import socket
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

import phase2_harness


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def serve(app):
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        assert server.started, "HTTP fixture failed to start"
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), "HTTP fixture failed to stop"


class Fixture:
    def __init__(self, actions=("mcp.guard_check", "mcp.guard_check_prompt")):
        self.base = phase2_harness.main()
        from app.modules.auth.federation.router import router
        from app.modules.auth.federation.delegation_router import router as delegation
        from app.mcp.http import router as mcp
        from app.modules.guard.routers.mcp import router as legacy
        from app.modules.auth.federation import verifier
        import app.tools.registrations.guard  # noqa: F401
        self.app = FastAPI()
        for route in (router, delegation, mcp, legacy):
            self.app.include_router(route)
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.jwk = dict(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key())), kid="http-fixture")
        self.original_fetch = verifier.DEFAULT_CACHE.fetch
        verifier.DEFAULT_CACHE.fetch = lambda _: {"keys": [self.jwk]}
        self.config = dict(self.base["config"], status="active")
        self.actions = list(actions)
        self.principals, self.grants = {}, {}
        self.binding = str(uuid4())
        self.prefix = f"/workspaces/{self.base['workspace']}/federation"
        with TestClient(self.app) as client:
            self.put(client, self.base["path"], {"expected_revision": 2, "config": self.config})
            approval = {"expected_revision": 0, "status": "active", "actions": self.actions}
            self.put(client, self.prefix + "/bindings/" + self.binding,
                     dict(approval, caller_id=self.base["caller_id"], connection_id=self.base["connection"]))
            for subject in ("alice", "bob"):
                self.principals[subject], self.grants[subject] = str(uuid4()), str(uuid4())
                self.put(client, self.prefix + "/principals/" + self.principals[subject],
                         dict(approval, issuer=self.config["issuer"], subject=subject, kind="human"))
                self.put(client, self.prefix + "/grants/" + self.grants[subject],
                         dict(approval, binding_id=self.binding, principal_id=self.principals[subject],
                              expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()))

    def put(self, client, path, body):
        response = client.put(path, headers=self.base["headers"], json=body)
        assert response.status_code == 200, (response.status_code, response.text)
        return response.json()

    def token(self, subject="alice", **claims):
        payload = dict(iss=self.config["issuer"], aud=self.config["audience"], sub=subject,
                       exp=int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()))
        payload.update(claims)
        return jwt.encode(payload, self.key, algorithm="RS256", headers={"kid": "http-fixture", "typ": "at+jwt"})

    def headers(self, subject="alice", **claims):
        return {**self.base["headers"], "Conduct-Federation-Connection": self.base["connection"],
                "Conduct-Subject-Token": self.token(subject, **claims)}

    def close(self):
        from app.modules.auth.federation import verifier
        verifier.DEFAULT_CACHE.fetch = self.original_fetch
