"""Launch a disposable console login test; credentials are never written to files."""
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
COMPOSE = ["rtk", "docker", "compose", "--project-name", "conduct-console-e2e",
           "--env-file", os.devnull, "-f", str(ROOT / "compose.yml")]


def metadata(issuer):
    parsed = urlsplit(issuer)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("An HTTPS realm issuer without credentials is required")
    with urllib.request.urlopen(issuer + "/.well-known/openid-configuration", timeout=20) as response:
        body = response.read(65537)
    if len(body) > 65536:
        raise ValueError("Discovery document too large")
    doc = json.loads(body)
    if doc.get("issuer") != issuer:
        raise ValueError("Discovery issuer mismatch")
    jwks = urlsplit(doc["jwks_uri"])
    if jwks.scheme != "https" or jwks.netloc != parsed.netloc or jwks.query or jwks.fragment:
        raise ValueError("Expected same-origin HTTPS JWKS URL for this test")
    return doc


def run(args, env, **kwargs):
    return subprocess.run(COMPOSE + args, env=env, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--client-id", default="conduct-console-proxy")
    parser.add_argument("--admin-subject", required=True)
    parser.add_argument("--viewer-subject", required=True)
    parser.add_argument("--check", action="store_true", help="Validate discovery and Compose; do not start services")
    args = parser.parse_args()
    issuer = args.issuer.rstrip("/")
    if (not args.admin_subject.strip() or not args.viewer_subject.strip()
            or args.admin_subject == args.viewer_subject):
        raise ValueError("Two distinct subjects are required")
    doc = metadata(issuer)
    # Do not inherit production API keys, Clerk settings, or Compose overrides.
    env = {k: v for k, v in os.environ.items()
           if k in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
                    "TMPDIR", "SSH_AUTH_SOCK")}
    env.update({
        "CONSOLE_OIDC_ISSUER": issuer,
        "CONSOLE_OIDC_CLIENT_ID": args.client_id,
        "CONSOLE_OIDC_JWKS_URL": doc["jwks_uri"],
        "TEST_ADMIN_SUBJECT": args.admin_subject,
        "TEST_VIEWER_SUBJECT": args.viewer_subject,
        "CONSOLE_PROXY_SECRET": secrets.token_urlsafe(48),
        "ENCRYPTION_KEY": secrets.token_urlsafe(48),
        "OAUTH2_PROXY_COOKIE_SECRET": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "OAUTH2_PROXY_CLIENT_SECRET": "configuration-check-only",
    })
    run(["config", "--quiet"], env)
    if args.check:
        print("PASS: realm discovery and Compose syntax. Browser authentication not tested.")
        return
    if not sys.stdin.isatty():
        raise ValueError("Run in your terminal so the secret can be entered without echo")
    existing = run(["ps", "--all", "--quiet"], env, capture_output=True, text=True)
    if existing.stdout.strip():
        raise ValueError("This test project already has containers; review them before starting a fresh run")
    print("Building isolated test images. This can take several minutes.", flush=True)
    run(["build", "api", "web"], env)
    secret = getpass.getpass("Skycloak console client secret (hidden): ")
    if not secret or secret != secret.strip():
        raise ValueError("Client secret is empty or contains surrounding whitespace")
    env["OAUTH2_PROXY_CLIENT_SECRET"] = secret
    print("Credentials use container environments, visible to local Docker administrators; no secret files are created.")
    try:
        run(["up", "-d", "postgres", "redis"], env)
        run(["run", "--rm", "api", "python", "/harness/console_bootstrap.py"], env)
        run(["up", "-d", "api", "web", "proxy", "ingress"], env)
        print("Services started, not yet verified. Console: https://localhost:3443")
        print("Next: explicitly trust the test CA, then verify browser login. Do not bypass certificate errors.")
        print("Keep this terminal open. Press Enter when finished to remove ONLY these test containers and test data.")
        input()
    finally:
        run(["down"], env)
    print("Test containers/data removed. Local CA volume retained for explicit review/removal.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        # Avoid printing exception details from HTTP/auth responses or subprocess environments.
        print(f"Setup stopped ({type(exc).__name__}); no credentials printed.", file=sys.stderr)
        raise SystemExit(1)
