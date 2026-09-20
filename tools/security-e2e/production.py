"""Run bounded production security canaries from this machine."""
import argparse
import os
import re
import shutil
import subprocess
from contextlib import nullcontext
from pathlib import Path

from dotenv import dotenv_values
from otp_broker import DEFAULT_TOKEN_FILE, GmailClient, OtpBrokerError, authorize, discover_client_file, serve

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = (
    "PROD_E2E_A_EMAIL",
    "PROD_E2E_A_PASSWORD",
    "PROD_E2E_B_EMAIL",
    "PROD_E2E_B_PASSWORD",
)


def playwright_command() -> list[str]:
    command = ["npx", "playwright", "test", "--config", "playwright.production-security.config.ts"]
    return ["rtk", "proxy", *command] if shutil.which("rtk") else command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--allow-disposable-workspaces", action="store_true")
    parser.add_argument("--grep", help="Run only production canaries matching this pattern")
    parser.add_argument("--gateway-preflight", action="store_true", help="Read-only Gateway fixture check; no cleanup, mutations, or inference")
    parser.add_argument("--authorize-gmail", action="store_true")
    parser.add_argument("--gmail-client-file", type=Path)
    parser.add_argument("--gmail-token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--manual-otp", action="store_true")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    try:
        if args.authorize_gmail:
            client_file = args.gmail_client_file or discover_client_file()
            authorize(client_file, args.gmail_token_file)
            return 0
    except OtpBrokerError as error:
        parser.error(str(error))
    if args.credentials_file is None:
        parser.error("--credentials-file is required unless --authorize-gmail is used")
    if not args.allow_disposable_workspaces and not args.gateway_preflight:
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
    environment["PROD_E2E_HEADLESS"] = "0" if args.headed else "1"
    environment["PROD_E2E_GATEWAY_PREFLIGHT"] = "1" if args.gateway_preflight else "0"

    command = playwright_command()
    if args.gateway_preflight:
        command.extend(["--grep", "@prod-gateway-fixture"])
    elif args.grep:
        command.extend(["--grep", args.grep])
    try:
        if args.manual_otp:
            broker = nullcontext(None)
        else:
            client_file = args.gmail_client_file or discover_client_file()
            broker = serve(
                GmailClient(client_file, args.gmail_token_file),
                {environment["PROD_E2E_A_EMAIL"], environment["PROD_E2E_B_EMAIL"]},
            )
        with broker as connection:
            secrets_to_redact = [environment[key] for key in ALLOWED]
            if connection:
                environment["PROD_E2E_OTP_BROKER_URL"], environment["PROD_E2E_OTP_BROKER_TOKEN"] = connection
                secrets_to_redact.append(connection[1])
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
                    for value in secrets_to_redact:
                        line = line.replace(value, "[redacted]")
                    print(line, end="", flush=True)
                return process.wait()
    except OtpBrokerError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
