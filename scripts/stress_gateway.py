#!/usr/bin/env python3
"""Bounded concurrent stress test for the Gateway v2.

Reads token + server from ``~/.conduct/config.json`` (same as
``smoke_gateway.py``). Fires N requests at concurrency C against a
published profile, then reports latency distribution, status
breakdown, and an estimated dollar cost.

Safety belts (always on):
  - ``--max-wall`` — whole-run wall-clock budget (default 90s)
  - ``--request-timeout`` — per-request client-side deadline (default 30s);
    independent from ``--max-wall``
  - Max total requests (--total)
  - Kill switch when the *real-error* rate > 5% AND at least 20 requests
    fired. Conduct admission refusals (our 429 backpressure layer) are
    excluded by default — they mean the service protected itself, not
    failed. Pass ``--kill-on-admission`` to count them.
  - Small ``max_tokens`` so provider cost stays bounded

Report separates status codes from *categories*: admission-refused vs
budget-refused vs upstream-rate-limit vs upstream-5xx vs client_timeout.
Correlate categories with Flight Recorder before increasing load.

Usage:
    scripts/stress_gateway.py cond-6zq8mzpc-claude-sonnet \\
        --total 1000 --concurrency 20

For streaming stress add ``--stream``. To send a specific prompt
per request set ``--prompt-env VARNAME`` and export the prompt in
that env var (avoids embedding sensitive strings in this file).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

try:
    import aiohttp
    _HAVE_AIOHTTP = True
except ImportError:
    _HAVE_AIOHTTP = False


# Cheap-model-cost estimate ($/1M tokens). Adjust if you point at a
# non-Sonnet profile.
_SONNET_INPUT_PER_MTOK  = 3.00
_SONNET_OUTPUT_PER_MTOK = 15.00


def _load_creds() -> tuple[str, str]:
    cfg_path = Path.home() / ".conduct" / "config.json"
    if not cfg_path.exists():
        print(f"error: {cfg_path} not found — run `conduct login`", file=sys.stderr)
        sys.exit(1)
    cfg = json.loads(cfg_path.read_text())
    token = cfg.get("agent_token")
    server = (cfg.get("server") or "https://api.conductai.ai").rstrip("/")
    if not token:
        print("error: no agent_token in config — run `conduct login`", file=sys.stderr)
        sys.exit(1)
    return token, server


_CLEAN_PROMPT = "Reply with the single word: pong"


def _classify_error(status: int, body: bytes) -> str:
    """Bucket a non-2xx response so the report separates admission
    refusals (our layer) from upstream rate limits, client timeouts,
    and unclassified errors. Reads the body prefix — Conduct admission
    refusals include ``conduct_gateway_admission_refused`` verbatim.
    """
    if 200 <= status < 300:
        return "ok"
    if status == 599:
        return "client_timeout"
    if status == 598:
        return "client_error"
    snippet = body[:256].decode("utf-8", "replace") if body else ""
    if "conduct_gateway_admission_refused" in snippet:
        return "conduct_admission_refused"
    if "budget_reservation_refused" in snippet:
        return "conduct_budget_refused"
    if status == 429:
        return "upstream_rate_limit"
    if status == 503:
        return "upstream_unavailable"
    if 500 <= status < 600:
        return "upstream_5xx"
    if 400 <= status < 500:
        return "client_4xx"
    return "other"


async def _fire_one_async(session, url, headers, body, request_timeout):
    t0 = time.monotonic()
    try:
        async with session.post(
            url, headers=headers, json=body,
            timeout=aiohttp.ClientTimeout(total=request_timeout),
        ) as r:
            data = await r.read()
            return r.status, time.monotonic() - t0, data
    except asyncio.TimeoutError:
        return 599, time.monotonic() - t0, b"timeout"
    except Exception as e:
        return 598, time.monotonic() - t0, str(e).encode()


async def _run_async(url, token, model, total, concurrency, max_tokens,
                     use_stream, max_wall, prompt, request_timeout,
                     include_admission_in_kill):
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    statuses: Counter = Counter()
    categories: Counter = Counter()
    admission_sample: str | None = None
    input_tokens_seen = 0
    output_tokens_seen = 0
    # Fix 8 (P1 #8): track the actual stop reason instead of reconstructing
    # from final statuses. 99 successes + 1 failure with wall-time stop
    # used to print "non-2xx rate exceeded 5%" because _report only saw
    # the boolean. Now the run records exactly why it stopped.
    stop_reason: str | None = None  # 'error_rate' | 'wall_clock' | None (completed)
    started = time.monotonic()

    body_template = {
        "model": model,
        "max_tokens": max_tokens,
        "stream": use_stream,
        "messages": [{"role": "user", "content": prompt}],
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Session-wide timeout is a hard ceiling; each request gets its own
    # ``request_timeout`` so ``--max-wall`` (whole-run) and per-request
    # deadlines are independent.
    async with aiohttp.ClientSession() as session:

        async def _bounded_fire(_i: int):
            nonlocal stop_reason, input_tokens_seen, output_tokens_seen
            nonlocal admission_sample
            if stop_reason is not None or time.monotonic() - started > max_wall:
                if stop_reason is None and time.monotonic() - started > max_wall:
                    stop_reason = "wall_clock"
                return
            async with sem:
                if stop_reason is not None or time.monotonic() - started > max_wall:
                    if stop_reason is None and time.monotonic() - started > max_wall:
                        stop_reason = "wall_clock"
                    return
                status, lat, resp = await _fire_one_async(
                    session, url, headers, body_template, request_timeout,
                )
            latencies.append(lat)
            statuses[status] += 1
            category = _classify_error(status, resp)
            categories[category] += 1
            if category == "conduct_admission_refused" and admission_sample is None:
                admission_sample = resp[:200].decode("utf-8", "replace")
            if status == 200 and not use_stream:
                try:
                    payload = json.loads(resp)
                    usage = payload.get("usage") or {}
                    input_tokens_seen  += int(usage.get("input_tokens", 0))
                    output_tokens_seen += int(usage.get("output_tokens", 0))
                except Exception:
                    pass
            fired = sum(statuses.values())
            if fired >= 20:
                # Distinguish admission-mediated backpressure from real
                # errors. When admission is protecting the service, 429s
                # from our layer aren't the same signal as upstream 5xx.
                if include_admission_in_kill:
                    bad = sum(v for k, v in statuses.items() if not (200 <= k < 300))
                else:
                    bad = sum(
                        v for cat, v in categories.items()
                        if cat not in ("ok", "conduct_admission_refused")
                    )
                if bad / fired > 0.05 and stop_reason is None:
                    print(
                        f"\n  kill-switch: real-error rate {bad/fired:.1%} "
                        f"at {fired} requests"
                        f"{' (admission refusals not counted)' if not include_admission_in_kill else ''}",
                        file=sys.stderr,
                    )
                    stop_reason = "error_rate"

        tasks = [_bounded_fire(i) for i in range(total)]
        await asyncio.gather(*tasks)

    return (latencies, statuses, categories, admission_sample,
            input_tokens_seen, output_tokens_seen, stop_reason)


def _report(latencies, statuses, categories, admission_sample,
            input_tok, output_tok, stop_reason, wall):
    fired = sum(statuses.values())
    print()
    print(f"=== Stress report — {fired} requests in {wall:.1f}s ===")
    if fired == 0:
        print("no requests fired")
        return
    rps = fired / wall if wall > 0 else 0
    print(f"  throughput      {rps:.1f} req/s")
    if latencies:
        lat_sorted = sorted(latencies)
        def _pct(p):
            return lat_sorted[min(len(lat_sorted) - 1, int(len(lat_sorted) * p))]
        print(f"  latency  p50   {_pct(0.50) * 1000:6.0f} ms")
        print(f"  latency  p90   {_pct(0.90) * 1000:6.0f} ms")
        print(f"  latency  p95   {_pct(0.95) * 1000:6.0f} ms")
        print(f"  latency  p99   {_pct(0.99) * 1000:6.0f} ms")
        print(f"  latency  max   {max(latencies) * 1000:6.0f} ms")
    print("  status codes:")
    for status, n in sorted(statuses.items()):
        marker = "OK" if 200 <= status < 300 else ("BLK" if status == 451 else "ERR")
        print(f"    [{marker}] {status}: {n}")
    if categories:
        print("  categories:")
        _cat_order = [
            "ok",
            "conduct_admission_refused",
            "conduct_budget_refused",
            "upstream_rate_limit",
            "upstream_unavailable",
            "upstream_5xx",
            "client_4xx",
            "client_timeout",
            "client_error",
            "other",
        ]
        for cat in _cat_order:
            n = categories.get(cat, 0)
            if n:
                print(f"    {cat:32s} {n}")
    if admission_sample:
        print(f"  admission_body_sample  {admission_sample}")
    if input_tok or output_tok:
        cost = (
            input_tok  * _SONNET_INPUT_PER_MTOK  / 1_000_000 +
            output_tok * _SONNET_OUTPUT_PER_MTOK / 1_000_000
        )
        print(f"  tokens          in={input_tok}  out={output_tok}")
        print(f"  est cost        ${cost:.4f} (Sonnet pricing)")
    else:
        print("  tokens          not tracked (streaming or blocked)")
    if stop_reason == "error_rate":
        print()
        print("  kill-switch fired mid-run — non-2xx rate exceeded 5%")
    elif stop_reason == "wall_clock":
        print()
        print("  wall-clock limit reached — remaining requests skipped")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", help="Full cond-<code>-<alias> string")
    ap.add_argument("--server", default=None,
                    help="Override server URL (e.g. https://gateway.conductai.ai). "
                         "Defaults to server in ~/.conduct/config.json.")
    ap.add_argument("--total", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--max-tokens", type=int, default=5)
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    ap.add_argument("--max-wall", type=int, default=90,
                    help="Whole-run wall-clock budget in seconds. Independent "
                         "from --request-timeout.")
    ap.add_argument("--request-timeout", type=int, default=30,
                    help="Per-request client timeout in seconds. Requests "
                         "exceeding this are recorded as client_timeout "
                         "(status 599). Independent from --max-wall.")
    ap.add_argument("--kill-on-admission", action="store_true",
                    help="Count Conduct admission refusals (429 with body "
                         "``conduct_gateway_admission_refused``) toward the "
                         "5%% kill-switch. Default is to exclude them: "
                         "admission is protecting the service, not failing.")
    ap.add_argument("--prompt-env", default=None,
                    help="Env var holding the prompt to send (default: hard-coded pong)")
    args = ap.parse_args()

    if not _HAVE_AIOHTTP:
        print("error: this script requires aiohttp. Install with: pip install aiohttp",
              file=sys.stderr)
        return 1

    prompt = _CLEAN_PROMPT
    if args.prompt_env:
        prompt = os.environ.get(args.prompt_env)
        if not prompt:
            print(f"error: env var {args.prompt_env} is not set", file=sys.stderr)
            return 1

    token, server = _load_creds()
    if args.server:
        server = args.server.rstrip("/")
    if args.provider == "anthropic":
        url = f"{server}/gateway/v1/anthropic/v1/messages"
    else:
        url = f"{server}/gateway/v1/openai/v1/chat/completions"

    print(f"Target:      {url}")
    print(f"Model:       {args.model}")
    print(f"Total:       {args.total}  Concurrency: {args.concurrency}  max_tokens: {args.max_tokens}")
    if args.stream:
        print("Streaming:   yes (cost tracking disabled)")
    print()

    started = time.monotonic()
    try:
        results = asyncio.run(_run_async(
            url=url, token=token, model=args.model,
            total=args.total, concurrency=args.concurrency,
            max_tokens=args.max_tokens,
            use_stream=args.stream, max_wall=args.max_wall,
            prompt=prompt,
            request_timeout=args.request_timeout,
            include_admission_in_kill=args.kill_on_admission,
        ))
    except KeyboardInterrupt:
        print("\n^C — cancelled", file=sys.stderr)
        return 130

    wall = time.monotonic() - started
    _report(*results, wall=wall)
    return 0


if __name__ == "__main__":
    sys.exit(main())
