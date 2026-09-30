"""Run disposable on-prem acceptance checks; never treat missing evidence as a pass."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
FIELDS = {"ca", "cli_config", "delegation_config", "gateway_url", "gateway_model",
          "litellm_url", "litellm_model", "blocked_prompt", "block_marker",
          "gateway_fault_marker", "litellm_fault_marker"}
ATTESTATIONS = {"self_hosted_idp", "egress_blocked_services_and_clients",
                "cold_start_without_downloads", "internal_inference_only",
                "network_logs_reviewed", "zero_provider_calls_during_denial",
                "jwks_outage_rotation_verified", "customer_url_browser_verified"}


def https_url(value):
    url = urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment):
        raise ValueError("Endpoints must be HTTPS without credentials, query or fragment")
    url.port
    return url


def load_plan(path):
    plan = json.loads(path.read_text())
    if not isinstance(plan, dict) or set(plan) != FIELDS:
        raise ValueError("Plan must contain exactly the documented non-secret fields")
    if any(not isinstance(v, str) or not v.strip() for v in plan.values()):
        raise ValueError("Every plan field requires a nonempty string")
    for key in ("ca", "cli_config", "delegation_config"):
        resolved = (path.parent / plan[key]).resolve()
        if not resolved.is_file():
            raise ValueError("Referenced CA/config file missing")
        plan[key] = str(resolved)
    cli = json.loads(Path(plan["cli_config"]).read_text())
    delegated = json.loads(Path(plan["delegation_config"]).read_text())
    api = https_url(cli.get("api_url") or cli.get("server") or "")
    other = https_url(delegated.get("api_url", ""))
    if (api.scheme, api.netloc, api.path.rstrip("/")) != (other.scheme, other.netloc, other.path.rstrip("/")):
        raise ValueError("CLI and delegation must target the same installation")
    for key in ("gateway_url", "litellm_url"):
        https_url(plan[key])
    https_url(delegated.get("issuer", ""))
    return plan


def commands(plan, stage):
    python = sys.executable
    all_stages = stage in ("all", "airgap")
    result = []
    if all_stages or stage == "console":
        result.append(("console", [python, str(ROOT / "tools/console-e2e/browser.py"),
            "--ca", plan["ca"], "--allow-fixture-mutations"]))
    if all_stages or stage == "delegation":
        result.append(("delegation", [python, str(ROOT / "tools/federation/live.py"),
            "--config", plan["delegation_config"], "--ca", plan["ca"], "--manual-browser", "--revoke"]))
    if all_stages or stage == "outages":
        args = [python, str(ROOT / "tools/conduct_smoke_test.py"), "--config", plan["cli_config"],
                "--ca", plan["ca"], "--inference", "--fault-tests"]
        for key in ("gateway_url", "gateway_model", "litellm_url", "litellm_model",
                    "blocked_prompt", "block_marker", "gateway_fault_marker", "litellm_fault_marker"):
            args.extend(["--" + key.replace("_", "-"), plan[key]])
        result.append(("outages", args))
    return result


def evidence(path):
    raw = path.read_bytes()
    doc = json.loads(raw)
    if not isinstance(doc, dict) or set(doc) != ATTESTATIONS or any(v is not True for v in doc.values()):
        raise ValueError("All documented air-gap attestations must be explicitly true after verification")
    return hashlib.sha256(raw).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--stage", choices=("console", "delegation", "outages", "airgap", "all"), default="all")
    parser.add_argument("--check", action="store_true", help="Validate plan only; never runs tests")
    parser.add_argument("--allow-disposable-tests", action="store_true")
    parser.add_argument("--airgap-evidence", type=Path, help="Operator-reviewed attestations, not machine proof")
    parser.add_argument("--report", type=Path, help="New report file; existing files are never overwritten")
    args = parser.parse_args(argv)
    plan = load_plan(args.plan.resolve())
    if args.check:
        print("Plan valid. No services contacted; no acceptance checks passed.")
        return 0
    if not args.allow_disposable_tests or not sys.stdin.isatty():
        parser.error("Interactive terminal and --allow-disposable-tests required")
    if not args.report:
        parser.error("A new --report path is required")
    needs_airgap = args.stage in ("all", "airgap")
    if needs_airgap and not args.airgap_evidence:
        parser.error("all/airgap requires --airgap-evidence; use individual stages for connected testing")
    digest = evidence(args.airgap_evidence) if needs_airgap else None
    print("Dedicated services only. Tests mutate fixtures/grants and can incur inference costs.")
    if input("Confirm disposable acceptance targets (type TEST): ") != "TEST":
        return 2
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "stage": args.stage,
              "status": "incomplete", "checks": [],
              "airgap": {"status": "operator_attested" if digest else "not_verified",
                         "evidence_sha256": digest},
              "limits": ["Not HPE certification", "Console automation targets the localhost fixture",
                         "Network isolation and provider logs require independent operator review"]}
    # Exclusive creation protects configs and existing acceptance records from overwrite.
    with args.report.open("x") as output:
        try:
            for label, command in commands(plan, args.stage):
                code = subprocess.run(command, cwd=ROOT, check=False).returncode
                report["checks"].append({"name": label, "status": "passed" if code == 0 else "failed"})
                if code:
                    report["status"] = "failed"
                    return 1
            report["status"] = "checks_passed_operator_attested" if digest else "checks_passed_airgap_pending"
            print(report["status"])
            return 0
        finally:
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            json.dump(report, output, indent=2)
            output.write("\n")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, EOFError):
        raise SystemExit("Acceptance setup stopped; verify plan/evidence/files. Configuration values omitted.")
    except KeyboardInterrupt:
        raise SystemExit(130)
