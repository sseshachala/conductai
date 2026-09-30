#!/usr/bin/env python3
"""Standalone, stdlib-only MCP/Gateway/LiteLLM smoke test.

Default: MCP only, using ~/.conduct/config.json. No commands are executed by
guard_check. Inference is opt-in and may incur provider charges. Provider keys
belong in the Gateway/LiteLLM server, not this script. Tokens are never printed.

Example:
  python3 tools/conduct_smoke_test.py --config /path/to/.conduct/config.json --ca /path/to/ca.crt
  python3 tools/conduct_smoke_test.py --inference --model MODEL --litellm-url http://localhost:4000/v1

--gateway-url is an OpenAI-compatible base ending in /openai/v1 (not /gateway/v1).
Gateway defaults to saved gateway_url + /openai/v1. LiteLLM requires its own URL
and credential (LITELLM_API_KEY env, or a hidden prompt). Never reuse a Conduct
credential for an arbitrary LiteLLM server.

Optional --blocked-prompt and --block-marker test a configured prompt-blocking
rule. Marker must identify that rule in the error response. Review server audit
and provider logs to establish that a blocked call never reached the provider.
This does not certify delegated identity, revocation, outages, or air-gapping.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


class CheckFailed(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CheckFailed("Redirect refused; use the exact endpoint URL")


def endpoint(value):
    parsed = urllib.parse.urlsplit(value)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query
            or parsed.fragment or any(c.isspace() for c in value) or "\\" in value):
        raise CheckFailed("Invalid endpoint URL")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and
            parsed.hostname in ("localhost", "127.0.0.1", "::1")):
        raise CheckFailed("HTTPS required except for loopback endpoints")
    try:
        parsed.port
    except ValueError:
        raise CheckFailed("Invalid endpoint port") from None
    return value.rstrip("/")


def decode(raw, content_type):
    text = raw.decode("utf-8")
    if "text/event-stream" in content_type:
        for event in text.replace("\r\n", "\n").split("\n\n"):
            data = "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
            if data and data != "[DONE]":
                item = json.loads(data)
                if isinstance(item, dict) and ("result" in item or "error" in item):
                    return item
        raise CheckFailed("No JSON-RPC response in SSE stream")
    return json.loads(text) if text else {}


class Client:
    def __init__(self, ca):
        context = ssl.create_default_context(cafile=ca)
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))

    def post(self, url, token, body, headers=None):
        request = urllib.request.Request(endpoint(url), data=json.dumps(body).encode(), headers={
            "Authorization": "Bearer " + token, "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream", **(headers or {}),
        })
        try:
            response = self.opener.open(request, timeout=60)
        except urllib.error.HTTPError as exc:
            response = exc
        except (OSError, urllib.error.URLError):
            raise CheckFailed("Connection/TLS failed; check service availability and trusted CA") from None
        with response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise CheckFailed("Response exceeds smoke-test size limit")
            try:
                data = decode(raw, response.headers.get("Content-Type", ""))
            except (ValueError, UnicodeError):
                data = None
            return response.status, data, response.headers


class MCP:
    def __init__(self, client, url, token, workspace):
        self.client, self.url, self.token = client, endpoint(url), token
        self.headers = {"X-Workspace-Id": workspace} if workspace else {}
        self.sequence = 0

    def call(self, method, params, notify=False):
        self.sequence += 1
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notify:
            body["id"] = self.sequence
        status, data, headers = self.client.post(self.url, self.token, body, self.headers)
        if not 200 <= status < 300:
            raise CheckFailed(f"MCP HTTP {status}")
        if headers.get("Mcp-Session-Id"):
            self.headers["Mcp-Session-Id"] = headers["Mcp-Session-Id"]
        if notify:
            return {}
        if not isinstance(data, dict) or data.get("id") != self.sequence or "error" in data:
            raise CheckFailed("Invalid or unsuccessful MCP JSON-RPC response")
        result = data.get("result")
        if not isinstance(result, dict) or result.get("isError"):
            raise CheckFailed("MCP tool returned an error")
        return result

    def check(self, tool, arguments, expected):
        result = self.call("tools/call", {"name": tool, "arguments": arguments})
        texts = [item["text"].strip() for item in result.get("content", [])
                 if item.get("type") == "text" and isinstance(item.get("text"), str)]
        if not texts:
            raise CheckFailed("MCP response has no policy verdict")
        verdict = "\n".join(texts)
        allowed = verdict.lower() in ("ok", "ok.") or verdict.startswith("ALLOWED")
        blocked = verdict.startswith("BLOCKED")
        if not (allowed if expected == "allow" else blocked):
            raise CheckFailed(f"Expected {expected} policy verdict; check workspace rules/audit")


def inference(client, url, token, model, prompt, run_id, block_marker=None, fault=False):
    status, data, _ = client.post(endpoint(url) + "/chat/completions", token, {
        "model": model, "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 32, "stream": False,
    }, {"X-Request-ID": run_id})
    if block_marker:
        statuses = (400, 403, 503) if fault else (400, 403)
        error = (data.get("error") or data.get("detail")) if isinstance(data, dict) else None
        if status not in statuses or not error or data.get("choices") or block_marker not in json.dumps(error):
            raise CheckFailed(f"Expected policy rejection with configured rule marker; HTTP {status}")
    elif not (status == 200 and isinstance(data, dict) and data.get("choices")):
        raise CheckFailed(f"Expected model response; HTTP {status}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path.home() / ".conduct/config.json")
    parser.add_argument("--ca", default=os.environ.get("SSL_CERT_FILE"))
    parser.add_argument("--inference", action="store_true", help="Opt in to real, potentially billable model requests")
    parser.add_argument("--gateway-url", help="Gateway OpenAI base URL; token prompted if different from saved Gateway")
    parser.add_argument("--litellm-url", help="LiteLLM OpenAI base URL, including /v1 if applicable")
    parser.add_argument("--model", help="Model alias available on both servers")
    parser.add_argument("--gateway-model")
    parser.add_argument("--litellm-model")
    parser.add_argument("--blocked-prompt", help="Harmless test text matching a configured prompt-block rule")
    parser.add_argument("--block-marker", help="Expected unique rule ID/error marker for the block test")
    parser.add_argument("--fault-tests", action="store_true", help="Interactive outage and recovery check; dedicated test services only")
    parser.add_argument("--gateway-fault-marker", help="Expected dependency-unavailable error marker")
    parser.add_argument("--litellm-fault-marker", default="fail_closed")
    args = parser.parse_args(argv)
    if bool(args.blocked_prompt) != bool(args.block_marker):
        parser.error("Supply --blocked-prompt and --block-marker together")
    if args.fault_tests and (not args.inference or not sys.stdin.isatty()):
        parser.error("Fault tests require --inference and an interactive terminal")
    cfg = json.loads(args.config.read_text())
    api = endpoint(cfg.get("api_url") or cfg.get("server") or "")
    token = cfg.get("agent_token")
    if not token:
        raise CheckFailed("No saved Conduct token; complete CLI login first")
    client = Client(args.ca)
    run_id = "conduct-smoke-" + str(uuid.uuid4())
    print(f"Run: {run_id}\nAPI: {api}")
    failures = []

    def run(label, check):
        try:
            check()
            print(f"PASS  {label}")
            return True
        except CheckFailed as exc:
            failures.append(label)
            print(f"FAIL  {label}: {exc}")
            return False

    mcp = MCP(client, cfg.get("mcp_url") or api + "/mcp", token, cfg.get("workspace_id"))

    def test_mcp():
        result = mcp.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                          "clientInfo": {"name": "conduct-smoke-test", "version": "1"}})
        mcp.headers["MCP-Protocol-Version"] = result.get("protocolVersion", "2024-11-05")
        mcp.call("notifications/initialized", {}, notify=True)
        names = {tool.get("name") for tool in mcp.call("tools/list", {}).get("tools", [])}
        if "guard_check" not in names:
            raise CheckFailed("guard_check missing from tools/list")
        mcp.check("guard_check", {"tool_name": "read_file", "tool_input": {"file_path": "README.md"}}, "allow")
        # This is policy input only. Nothing in the script executes this command.
        mcp.check("guard_check", {"tool_name": "bash", "tool_input": {"command": "rm -rf /"}}, "block")

    run("MCP initialize, list, allow and block", test_mcp)
    saved_gateway = cfg.get("gateway_url") or cfg.get("proxy_url")
    saved_base = endpoint(saved_gateway) + "/openai/v1" if saved_gateway else None
    gateway_url = args.gateway_url or saved_base
    for label, url, model in (("Gateway", gateway_url, args.gateway_model or args.model),
                              ("LiteLLM", args.litellm_url, args.litellm_model or args.model)):
        if not args.inference or not url:
            print(f"SKIP  {label}: {'use --inference to opt in' if not args.inference else 'endpoint not configured'}")
            continue
        url = endpoint(url)
        if not model:
            failures.append(label)
            print(f"FAIL  {label}: supply --model or the server-specific model option")
            continue
        credential = (token if label == "Gateway" and url == saved_base else
                      os.environ.get("LITELLM_API_KEY" if label == "LiteLLM" else "GATEWAY_API_KEY") or
                      getpass.getpass(f"{label} access token (hidden): "))
        positive = run(label + " inference", lambda: inference(client, url, credential, model, "Reply with hello.", run_id))
        if args.blocked_prompt:
            run(label + " policy rejection", lambda: inference(client, url, credential, model,
                args.blocked_prompt, run_id, args.block_marker))
        else:
            print(f"SKIP  {label} policy rejection: configure a rule and supply --blocked-prompt/--block-marker")
        if args.fault_tests:
            marker = args.gateway_fault_marker if label == "Gateway" else args.litellm_fault_marker
            if not positive or not marker:
                failures.append(label + " fault prerequisite")
                print(f"FAIL  {label} fault check: successful baseline and explicit dependency error marker required")
                continue
            confirmed = input(f"Confirm {label} is a disposable test service (type TEST): ")
            if confirmed != "TEST":
                failures.append(label + " fault consent")
                continue
            input(f"Make ONLY this test service's policy dependency unavailable; keep {label} running. Press Enter when ready. ")
            try:
                run(label + " fail closed", lambda: inference(client, url, credential, model,
                    "Reply with hello.", run_id, marker, fault=True))
            finally:
                input("Restore the test dependency, then press Enter to verify recovery. ")
            run(label + " recovery", lambda: inference(client, url, credential, model, "Reply with hello.", run_id))
        else:
            print(f"SKIP  {label} outage/recovery: requires --fault-tests and disposable services")
    print("Confirm audit/provider logs separately. Per-user delegation uses tools/federation/live.py.")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (CheckFailed, OSError, ValueError, EOFError) as exc:
        # Never print raw exceptions from credential-bearing requests/configuration.
        print(f"Stopped: {exc if isinstance(exc, CheckFailed) else type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
