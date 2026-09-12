"""Run bounded production security canaries from this machine."""
import argparse
import os
import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = (
    "PROD_E2E_A_EMAIL",
    "PROD_E2E_A_PASSWORD",
    "PROD_E2E_B_EMAIL",
    "PROD_E2E_B_PASSWORD",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", required=True, type=Path)
    parser.add_argument("--allow-disposable-workspaces", action="store_true")
    parser.add_argument("--grep", help="Run only production canaries matching this pattern")
    args = parser.parse_args()
    if not args.allow_disposable_workspaces:
        parser.error("explicit --allow-disposable-workspaces consent is required")
    if not args.credentials_file.is_file():
        parser.error("credential file does not exist")

    values = dotenv_values(args.credentials_file, interpolate=False)
    environment = os.environ.copy()
    for key in ALLOWED:
        value = values.get(key)
        if not value or not value.strip():
            parser.error(f"missing required field: {key}")
        environment[key] = value.strip()
    if environment["PROD_E2E_A_EMAIL"] == environment["PROD_E2E_B_EMAIL"]:
        parser.error("production test accounts must be distinct")
    environment["PROD_E2E_ALLOW_MUTATION"] = "1"

    command = [
        "rtk", "proxy", "npx", "playwright", "test",
        "--config", "playwright.production-security.config.ts",
    ]
    if args.grep:
        command.extend(["--grep", args.grep])
    with subprocess.Popen(
        command,
        cwd=ROOT / "apps/web",
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            line = re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer [redacted]", line)
            for key in ALLOWED:
                line = line.replace(environment[key], "[redacted]")
            print(line, end="", flush=True)
        return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
