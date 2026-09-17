#!/usr/bin/env python3
"""Bounded concurrent stress test for the Gateway v2.

Reads token + server from ``~/.conduct/config.json`` (same as
``smoke_gateway.py``). Fires N requests at concurrency C against a
published profile, then reports latency distribution, status
breakdown, and an estimated dollar cost.

Safety belts (always on):
  - Max wall time (default 90s)
  - Max total requests (--total)
  - Kill switch when non-2xx rate > 5% AND at least 20 requests fired
  - Small ``max_tokens`` so provider cost stays bounded

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


async def _fire_one_async(session, url, headers, body):
    t0 = time.monotonic()
    try:
        async with session.post(url, headers=headers, json=body) as r:
            data = await r.read()
            return r.status, time.monotonic() - t0, data
    except asyncio.TimeoutError:
        return 599, time.monotonic() - t0, b"timeout"
    except Exception as e:
        return 598, time.monotonic() - t0, str(e).encode()


async def _run_async(url, token, model, total, concurrency, max_tokens,
                     use_stream, max_wall, prompt):
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    statuses: Counter = Counter()
    input_tokens_seen = 0
    output_tokens_seen = 0
    kill = False
    started = time.monotonic()

    body_template = {
        "model": model,
        "max_tokens": max_tokens,
        "stream": use_stream,
        "messages": [{"role": "user", "content": prompt}],
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:

        async def _bounded_fire(_i: int):
            nonlocal kill, input_tokens_seen, output_tokens_seen
            # Pre-acquire cheap short-circuit (avoids piling up on the
            # semaphore when we already know we're stopping). The real
            # authoritative check happens post-acquire below.
            if kill or time.monotonic() - started > max_wall:
                return
            async with sem:
                # Re-check AFTER acquiring the semaphore. Without this the
                # kill switch is racy — tasks that queued for the semaphore
                # before the switch fired would still dispatch. Same for
                # the wall-clock deadline.
                if kill or time.monotonic() - started > max_wall:
                    if time.monotonic() - started > max_wall and not kill:
                        kill = True
                    return
                status, lat, resp = await _fire_one_async(
                    session, url, headers, body_template
                )
            latencies.append(lat)
            statuses[status] += 1
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
                bad = sum(v for k, v in statuses.items() if not (200 <= k < 300))
                if bad / fired > 0.05:
                    if not kill:
                        print(f"\n  kill-switch: non-2xx rate {bad/fired:.1%} at {fired} requests",
                              file=sys.stderr)
                    kill = True

        tasks = [_bounded_fire(i) for i in range(total)]
        await asyncio.gather(*tasks)

    return latencies, statuses, input_tokens_seen, output_tokens_seen, kill


def _report(latencies, statuses, input_tok, output_tok, killed, wall):
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
    if input_tok or output_tok:
        cost = (
            input_tok  * _SONNET_INPUT_PER_MTOK  / 1_000_000 +
            output_tok * _SONNET_OUTPUT_PER_MTOK / 1_000_000
        )
        print(f"  tokens          in={input_tok}  out={output_tok}")
        print(f"  est cost        ${cost:.4f} (Sonnet pricing)")
    else:
        print("  tokens          not tracked (streaming or blocked)")
    if killed:
        print()
        print("  kill-switch fired mid-run — see status codes above")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", help="Full cond-<code>-<alias> string")
    ap.add_argument("--total", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--max-tokens", type=int, default=5)
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    ap.add_argument("--max-wall", type=int, default=90)
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
        ))
    except KeyboardInterrupt:
        print("\n^C — cancelled", file=sys.stderr)
        return 130

    wall = time.monotonic() - started
    _report(*results, wall=wall)
    return 0


if __name__ == "__main__":
    sys.exit(main())
