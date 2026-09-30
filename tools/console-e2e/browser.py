"""Run real Keycloak browser canaries against the existing disposable console stack."""
import argparse
import getpass
import os
from pathlib import Path
import re
import subprocess
import sys
import warnings

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca", type=Path, required=True)
    parser.add_argument("--allow-fixture-mutations", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--grep")
    args = parser.parse_args()
    if not args.allow_fixture_mutations:
        parser.error("Explicit consent required: the viewer mapping is temporarily disabled then restored")
    if not args.ca.is_file():
        parser.error("Trusted test CA file required")
    warnings.simplefilter("error", getpass.GetPassWarning)
    environment = {k: v for k, v in os.environ.items() if k in
                   ("PATH", "HOME", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "PLAYWRIGHT_BROWSERS_PATH")}
    secrets = []
    for actor, default in (("ADMIN", "console-admin"), ("VIEWER", "console-viewerr"), ("UNMAPPED", "console-unmapped")):
        prefix = "CONSOLE_E2E_" + actor
        username = os.environ.get(prefix + "_USERNAME") or input(f"{actor} username [{default}]: ").strip() or default
        password = os.environ.get(prefix + "_PASSWORD") or getpass.getpass(f"{actor} password (hidden): ")
        if not password:
            parser.error("All three test accounts need passwords")
        environment[prefix + "_USERNAME"] = username
        environment[prefix + "_PASSWORD"] = password
        secrets.extend([username, password])
    environment.update({"NODE_EXTRA_CA_CERTS": str(args.ca.resolve()), "CONSOLE_E2E_ALLOW_MUTATION": "1",
                        "SSL_CERT_FILE": str(args.ca.resolve()),
                        "PYTHONPATH": str(ROOT / "packages/conduct-cli/src"),
                        "CONSOLE_E2E_PYTHON": sys.executable, "CONSOLE_E2E_HEADED": "1" if args.headed else "0"})
    command = ["rtk", "proxy", "node", "node_modules/@playwright/test/cli.js", "test",
               "--config", "playwright.console-security.config.ts"]
    if args.grep:
        command.extend(["--grep", args.grep])
    with subprocess.Popen(command, cwd=ROOT / "apps/web", env=environment, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
        for line in process.stdout:
            line = re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer [redacted]", line)
            line = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[redacted-jwt]", line)
            line = re.sub(r"\bcond_(?:agt|api|ref)_[A-Za-z0-9_-]+", "[redacted-token]", line)
            for secret in secrets:
                line = line.replace(secret, "[redacted]")
            print(line, end="", flush=True)
        return process.wait()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, EOFError, getpass.GetPassWarning):
        raise SystemExit("Browser test setup stopped; credentials omitted")
