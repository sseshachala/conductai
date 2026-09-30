"""Shared opt-in MCP/Gateway/LiteLLM checks for the existing E2E runners."""
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit

SMOKE_PATH = Path(__file__).resolve().parents[1] / "conduct_smoke_test.py"


def add_arguments(parser):
    parser.add_argument("--transport-config", type=Path, help="CLI config for optional shared transport checks")
    parser.add_argument("--transport-ca", help="Trusted test CA PEM; TLS verification remains enabled")
    parser.add_argument("--inference", action="store_true", help="Opt in to real, potentially billable transport inference")
    parser.add_argument("--gateway-url", help="Gateway OpenAI-compatible base URL")
    parser.add_argument("--litellm-url", help="LiteLLM OpenAI-compatible base URL")
    parser.add_argument("--model")
    parser.add_argument("--gateway-model")
    parser.add_argument("--litellm-model")
    parser.add_argument("--blocked-prompt", help="Harmless prompt matching a dedicated blocking rule")
    parser.add_argument("--block-marker", help="Unique blocking-rule marker expected in error response")
    parser.add_argument("--fault-tests", action="store_true", help="Interactive dependency-outage/recovery checks on disposable services")
    parser.add_argument("--gateway-fault-marker")
    parser.add_argument("--litellm-fault-marker", default="fail_closed")
    parser.add_argument("--delegation-config", type=Path, help="Non-secret live IdP/principal test configuration")
    parser.add_argument("--test-revocation", action="store_true", help="Pause for operator revocation of a disposable delegation grant")
    parser.add_argument("--manual-browser", action="store_true")


def smoke_module():
    spec = importlib.util.spec_from_file_location("conduct_transport_smoke", SMOKE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_target(config, target):
    """Prevent an isolated local test from accidentally reusing a SaaS login."""
    smoke = smoke_module()
    def endpoint(value):
        try:
            return smoke.endpoint(value)
        except smoke.CheckFailed:
            raise ValueError("Invalid transport endpoint") from None
    api = endpoint(config.get("api_url") or config.get("server") or "")
    urls = [api] + [config[key] for key in ("web_url", "mcp_url", "gateway_url", "proxy_url") if config.get(key)]
    for url in urls:
        parsed = urlsplit(endpoint(url))
        if target == "local":
            valid = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        elif target == "saas":
            valid = (parsed.scheme == "https" and parsed.port in (None, 443)
                     and parsed.hostname in ("api.conductai.ai", "app.conductai.ai", "gateway.conductai.ai"))
        else:
            valid = False
        if not valid:
            raise ValueError("CLI endpoints do not match the selected local/SaaS runner")


def validate_arguments(args, target):
    if not args.transport_config:
        raise ValueError("--transport-config is required for transport checks")
    try:
        config = json.loads(args.transport_config.read_text())
        validate_target(config, target)
    except (OSError, ValueError, AttributeError):
        raise ValueError("Transport config is unreadable, invalid, or belongs to another deployment") from None
    if bool(args.blocked_prompt) != bool(args.block_marker):
        raise ValueError("Supply --blocked-prompt and --block-marker together")
    if args.test_revocation and not args.delegation_config:
        raise ValueError("--test-revocation requires --delegation-config")
    if args.delegation_config:
        try:
            delegated = json.loads(args.delegation_config.read_text())
            validate_target({"api_url": delegated["api_url"]}, target)
            if delegated["api_url"].rstrip("/") != (config.get("api_url") or config.get("server")).rstrip("/"):
                raise ValueError()
        except (OSError, ValueError, KeyError, AttributeError):
            raise ValueError("Delegation config must use the same API deployment") from None


def run(args, target):
    validate_arguments(args, target)
    argv = ["--config", str(args.transport_config)]
    for name in ("gateway_url", "litellm_url", "model", "gateway_model", "litellm_model", "blocked_prompt", "block_marker",
                 "gateway_fault_marker", "litellm_fault_marker"):
        if getattr(args, name, None):
            argv.extend(["--" + name.replace("_", "-"), getattr(args, name)])
    if args.transport_ca:
        argv.extend(["--ca", args.transport_ca])
    if args.inference:
        argv.append("--inference")
    if args.fault_tests:
        argv.append("--fault-tests")
    print(f"Shared transport checks: {target}; skipped checks are not acceptance passes", flush=True)
    module = smoke_module()
    try:
        result = module.main(argv)
        if result or not args.delegation_config:
            if not args.delegation_config:
                print("SKIP live delegation/revocation: provide --delegation-config")
            return result
        spec = importlib.util.spec_from_file_location("conduct_live_delegation", SMOKE_PATH.parent / "federation/live.py")
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        live_args = ["--config", str(args.delegation_config)]
        if args.transport_ca:
            live_args.extend(["--ca", args.transport_ca])
        if args.manual_browser:
            live_args.append("--manual-browser")
        if args.test_revocation:
            live_args.append("--revoke")
        try:
            return live.main(live_args)
        except (live.TestError, OSError, ValueError, EOFError):
            print("Live delegation failed; details omitted to protect credentials")
            return 1
    except (module.CheckFailed, OSError, ValueError, EOFError) as exc:
        # Avoid raw network exceptions, config contents, and response bodies.
        print(f"Transport checks stopped ({type(exc).__name__}); credentials omitted", flush=True)
        return 1
