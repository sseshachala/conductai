#!/usr/bin/env python3
"""Bounded concurrent stress test for the Gateway v2 canonical endpoint.

Posts against ``POST /gateway/v1/completions`` — the profile-native
canonical endpoint added by #2144. One URL, one body shape, regardless
of which upstream the profile targets. The gateway resolves the profile
server-side and routes; no ``--provider`` knob or wire-format branching
lives on the client anymore.

Reads token + server from ``~/.conduct/config.json`` (same as
``smoke_gateway.py``), fires N requests at concurrency C carrying one
profile identifier, then reports latency distribution, status breakdown,
and an estimated dollar cost.

Safety belts (always on):
  - ``--max-wall`` — whole-run wall-clock budget (default 90s)
  - ``--request-timeout`` — per-request client-side deadline (default 30s);
    independent from ``--max-wall``
  - Max total requests (--total)
  - Kill switch on the ADMITTED-request error rate (rejections excluded
    from both numerator + denominator — see ``_run_async`` for the P1
    rationale)
  - Small ``max_tokens`` so provider cost stays bounded

Report separates status codes from *categories*: admission-refused vs
budget-refused vs upstream-rate-limit vs upstream-5xx vs client_timeout.
Correlate categories with Flight Recorder before increasing load.

Usage:
    scripts/stress_gateway.py cond-e785vpmb-gpt-4o \\
        --total 1000 --concurrency 20

To send a specific prompt per request set ``--prompt-env VARNAME`` and
export the prompt in that env var (avoids embedding sensitive strings
in this file).

ponytail: streaming + tools intentionally NOT supported here. The
/completions endpoint rejects both in PR 1 of #2144. Upgrade path: land
the streaming follow-up on the server, then add ``--stream`` back.
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


# Fixed Sonnet-rate ballpark for a rough $ sanity check on the run. The
# canonical /completions endpoint can target any upstream, so a single
# hardcoded rate is deliberately approximate — the report labels it as
# such. Real per-profile cost lives in guard_audit_events.cost_usd_after.
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


# Buckets marked ``rejected=True`` were refused before upstream
# inference dispatch (best-effort, client-visible only). The reviewer's
# point on P2 #3: do not attribute an unclassified 429/503 to the
# upstream provider — Conduct also emits both codes for local rate
# limits, missing credentials, and audit failures. Default to
# ``unknown_origin`` when the body prefix does not name a layer.
_KNOWN_CONDUCT_ERROR_MARKERS = (
    ("conduct_gateway_admission_refused", "conduct_admission_refused", True),
    ("budget_reservation_refused",        "conduct_budget_refused",    True),
    ("conduct_guard_proxy",               "conduct_guard_proxy",       True),
    ("policy_block",                      "conduct_policy_block",      True),
    ("rate-limit",                        "conduct_rate_limit",        True),
    ("trial_exceeded",                    "conduct_trial_quota",       True),
)


def _classify_error(status: int, body: bytes) -> tuple[str, bool]:
    """Return ``(category, rejected_before_dispatch)``.

    A bucket flagged ``rejected=True`` did not reach upstream inference
    (best-effort, client-visible only). This distinction matters because
    the admitted-request error rate is the real production-readiness
    signal; rejections are a separate axis (backpressure / policy).

    Unclassified 429/503 map to ``unknown_origin`` — reviewer P2 #3.
    Conduct emits 429 for admission, local rate-limit rules, and trial
    quota; 503 for budget refusal, missing credentials, and audit
    failures. Do not guess the origin from status alone.
    """
    if 200 <= status < 300:
        return "ok", False
    if status == 599:
        return "client_timeout", False  # client aborted; upstream may have been called
    if status == 598:
        return "client_error", False    # transport failure client-side; unknown
    snippet = body[:512].decode("utf-8", "replace") if body else ""
    for marker, bucket, is_rejection in _KNOWN_CONDUCT_ERROR_MARKERS:
        if marker in snippet:
            return bucket, is_rejection
    # Guard's policy-block response uses HTTP 451.
    if status == 451:
        return "conduct_policy_block", True
    if status in (401, 403):
        return "conduct_auth", True
    if status in (429, 503):
        return "unknown_origin", False  # could be Conduct OR upstream — do not guess
    if 500 <= status < 600:
        return "upstream_5xx", False
    if 400 <= status < 500:
        return "client_4xx", False
    return "other", False


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


async def _run_async(url, token, profile, total, concurrency, max_tokens,
                     max_wall, prompt, request_timeout,
                     max_admitted_error_rate, max_rejection_rate,
                     kill_min_samples):
    """Run the load. Returns a dict of measurements.

    Reviewer P1s addressed:
      #1 rejections excluded from both numerator AND denominator of
         the kill-switch. Two independent thresholds:
         ``max_admitted_error_rate`` over admitted-only requests, and
         ``max_rejection_rate`` over all requests. Either fires.
      #2 ``max_wall`` is a real overall deadline. The task list is
         wrapped in ``asyncio.wait_for``; on timeout every in-flight
         coroutine is cancelled and the session is torn down.
    """
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    admitted_latencies: list[float] = []
    statuses: Counter = Counter()
    categories: Counter = Counter()
    admission_sample: str | None = None
    input_tokens_seen = 0
    output_tokens_seen = 0
    admitted = 0
    admitted_errors = 0
    rejections = 0
    successes = 0
    stop_reason: str | None = None  # 'admitted_error_rate' | 'rejection_rate' | 'wall_clock' | None
    started = time.monotonic()

    body_template = {
        "profile": profile,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:

        async def _bounded_fire(_i: int):
            nonlocal stop_reason, input_tokens_seen, output_tokens_seen
            nonlocal admission_sample, admitted, admitted_errors, rejections, successes
            if stop_reason is not None:
                return
            async with sem:
                if stop_reason is not None:
                    return
                status, lat, resp = await _fire_one_async(
                    session, url, headers, body_template, request_timeout,
                )
            latencies.append(lat)
            statuses[status] += 1
            category, is_rejection = _classify_error(status, resp)
            categories[category] += 1
            if category == "conduct_admission_refused" and admission_sample is None:
                admission_sample = resp[:200].decode("utf-8", "replace")
            # ponytail: single tick per completed request, on stderr so
            # stdout stays reserved for the final report. Prints "." for
            # a 2xx and the numeric status for anything else, followed by
            # a newline every 50 to keep terminals from wrapping. Cheap;
            # a hung run now looks obviously hung instead of silent.
            _tick = "." if 200 <= status < 300 else f"[{status}]"
            print(_tick, end="\n" if (sum(statuses.values()) % 50 == 0) else "",
                  file=sys.stderr, flush=True)
            if is_rejection:
                rejections += 1
            else:
                admitted += 1
                admitted_latencies.append(lat)
                if 200 <= status < 300:
                    successes += 1
                else:
                    admitted_errors += 1
            if status == 200:
                # Canonical response is OpenAI Chat Completions shape.
                # ``usage.prompt_tokens`` + ``usage.completion_tokens``
                # are the OpenAI keys; the older Anthropic-style
                # ``input_tokens`` / ``output_tokens`` keys are read as a
                # fallback so the report still tallies if the response
                # normalizer changes in a future PR.
                try:
                    payload = json.loads(resp)
                    usage = payload.get("usage") or {}
                    input_tokens_seen  += int(
                        usage.get("prompt_tokens", usage.get("input_tokens", 0))
                    )
                    output_tokens_seen += int(
                        usage.get("completion_tokens", usage.get("output_tokens", 0))
                    )
                except Exception:
                    pass
            fired = sum(statuses.values())
            if fired >= kill_min_samples:
                # P1 #1 fix: admitted-error rate is the real production
                # signal. Rejections are backpressure — a separate axis
                # so they can't dilute either numerator OR denominator.
                if admitted >= kill_min_samples:
                    aer = admitted_errors / admitted
                    if aer > max_admitted_error_rate and stop_reason is None:
                        print(
                            f"\n  kill-switch: admitted-error rate {aer:.1%} "
                            f"at {admitted} admitted / {fired} fired",
                            file=sys.stderr,
                        )
                        stop_reason = "admitted_error_rate"
                        return
                if max_rejection_rate < 1.0:
                    rr = rejections / fired
                    if rr > max_rejection_rate and stop_reason is None:
                        print(
                            f"\n  kill-switch: rejection rate {rr:.1%} "
                            f"at {fired} requests (threshold {max_rejection_rate:.1%})",
                            file=sys.stderr,
                        )
                        stop_reason = "rejection_rate"
                        return

        tasks = [asyncio.create_task(_bounded_fire(i)) for i in range(total)]
        # P1 #2 fix: real overall deadline. ``wait_for`` cancels the
        # gather on timeout; that cancellation propagates to every
        # child task, and ``aiohttp.ClientSession.__aexit__`` shuts
        # sockets down cleanly.
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=max_wall,
            )
        except asyncio.TimeoutError:
            if stop_reason is None:
                stop_reason = "wall_clock"
            for t in tasks:
                if not t.done():
                    t.cancel()
            # Bounded cleanup: give cancellations a short grace period
            # to run their aiohttp finalizers so socket state doesn't
            # leak into the next run.
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                pass

    return {
        "latencies":         latencies,
        "admitted_latencies": admitted_latencies,
        "statuses":          statuses,
        "categories":        categories,
        "admission_sample":  admission_sample,
        "input_tokens":      input_tokens_seen,
        "output_tokens":     output_tokens_seen,
        "admitted":          admitted,
        "admitted_errors":   admitted_errors,
        "rejections":        rejections,
        "successes":         successes,
        "stop_reason":       stop_reason,
    }


def _pct(sorted_seq, p):
    if not sorted_seq:
        return 0.0
    idx = min(len(sorted_seq) - 1, int(len(sorted_seq) * p))
    return sorted_seq[idx]


def _report(results: dict, wall: float, max_admitted_error_rate: float,
            max_rejection_rate: float) -> int:
    """Print the report and return a shell exit code.

    Reviewer P2 #4: throughput+latency previously mixed rejects with
    successes, giving unusable capacity numbers. Now we report:
      - all-requests throughput  (raw)
      - admitted req/s + latency (real capacity)
      - success req/s            (real usable capacity)
      - rejection rate           (backpressure axis)
      - admitted-error rate      (real fault axis, drives exit code)
    """
    latencies         = results["latencies"]
    admitted_lats     = results["admitted_latencies"]
    statuses          = results["statuses"]
    categories        = results["categories"]
    admission_sample  = results["admission_sample"]
    input_tok         = results["input_tokens"]
    output_tok        = results["output_tokens"]
    admitted          = results["admitted"]
    admitted_errors   = results["admitted_errors"]
    rejections        = results["rejections"]
    successes         = results["successes"]
    stop_reason       = results["stop_reason"]

    fired = sum(statuses.values())
    print()
    print(f"=== Stress report — {fired} requests in {wall:.1f}s ===")
    if fired == 0:
        print("no requests fired")
        return 1

    rps_all = fired / wall if wall > 0 else 0.0
    rps_admitted = admitted / wall if wall > 0 else 0.0
    rps_success = successes / wall if wall > 0 else 0.0
    rejection_rate = rejections / fired if fired else 0.0
    admitted_error_rate = admitted_errors / admitted if admitted else 0.0
    print(f"  throughput  all       {rps_all:.2f} req/s")
    print(f"  throughput  admitted  {rps_admitted:.2f} req/s  ({admitted}/{fired})")
    print(f"  throughput  success   {rps_success:.2f} req/s  ({successes}/{admitted})")
    print(f"  rejection rate        {rejection_rate:.1%}  ({rejections}/{fired})")
    print(f"  admitted-error rate   {admitted_error_rate:.1%}"
          f"  ({admitted_errors}/{admitted})")

    if admitted_lats:
        lat_sorted = sorted(admitted_lats)
        print("  admitted-request latency:")
        for label, p in (("p50", 0.50), ("p90", 0.90), ("p95", 0.95), ("p99", 0.99)):
            print(f"    {label:5s} {_pct(lat_sorted, p) * 1000:6.0f} ms")
        print(f"    max   {max(admitted_lats) * 1000:6.0f} ms")
    if latencies and len(latencies) != len(admitted_lats):
        # Show all-request latency too so operators can see rejection
        # speed vs admitted-request speed side-by-side.
        lat_sorted = sorted(latencies)
        print("  all-request latency (incl. rejections):")
        for label, p in (("p50", 0.50), ("p90", 0.90), ("p99", 0.99)):
            print(f"    {label:5s} {_pct(lat_sorted, p) * 1000:6.0f} ms")

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
            "conduct_policy_block",
            "conduct_rate_limit",
            "conduct_auth",
            "conduct_trial_quota",
            "conduct_guard_proxy",
            "unknown_origin",
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
        # ponytail: Sonnet's per-Mtok rate is a fixed ballpark, not the
        # profile's actual price. /completions can target any upstream
        # (GPT-4o, Claude, Perplexity, ...), so a single hardcoded rate
        # is a rough $ sanity check — not authoritative cost. If accurate
        # per-profile cost matters, pull it from the audit row's
        # cost_usd_after column instead.
        cost = (
            input_tok  * _SONNET_INPUT_PER_MTOK  / 1_000_000 +
            output_tok * _SONNET_OUTPUT_PER_MTOK / 1_000_000
        )
        print(f"  tokens          in={input_tok}  out={output_tok}")
        print(f"  est cost        ${cost:.4f} (Sonnet-rate ballpark; "
              f"actual varies by profile)")
    else:
        print("  tokens          not tracked (blocked or usage stripped)")

    print()
    exit_code = 0
    if stop_reason == "admitted_error_rate":
        print(f"  FAIL: admitted-error rate {admitted_error_rate:.1%} "
              f"exceeded {max_admitted_error_rate:.1%} — kill-switch fired mid-run")
        exit_code = 2
    elif stop_reason == "rejection_rate":
        print(f"  FAIL: rejection rate {rejection_rate:.1%} exceeded "
              f"{max_rejection_rate:.1%} — kill-switch fired mid-run")
        exit_code = 2
    elif stop_reason == "wall_clock":
        print("  wall-clock deadline reached — in-flight tasks were cancelled")
        # Not a fail on its own; use post-run rates to decide.
    else:
        print("  run completed")

    # Post-run enforcement: even if the kill-switch didn't fire (too
    # few samples), a completed run above threshold is a FAIL.
    if exit_code == 0 and admitted >= 1 and admitted_error_rate > max_admitted_error_rate:
        print(f"  FAIL: admitted-error rate {admitted_error_rate:.1%} "
              f"exceeded {max_admitted_error_rate:.1%} on complete run")
        exit_code = 2
    if exit_code == 0 and fired >= 1 and rejection_rate > max_rejection_rate:
        print(f"  FAIL: rejection rate {rejection_rate:.1%} exceeded "
              f"{max_rejection_rate:.1%} on complete run")
        exit_code = 2
    if exit_code == 0:
        print("  PASS")
    return exit_code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("profile", nargs="?",
                    help="Full cond-<code>-<alias> profile identifier. "
                         "The gateway resolves upstream, wire format, and "
                         "credentials server-side. Optional only with "
                         "--self-check.")
    ap.add_argument("--server", default=None,
                    help="Override server URL (e.g. https://gateway.conductai.ai). "
                         "Defaults to server in ~/.conduct/config.json.")
    ap.add_argument("--total", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--max-tokens", type=int, default=5)
    ap.add_argument("--max-wall", type=int, default=90,
                    help="Overall run deadline in seconds. In-flight tasks "
                         "are cancelled when this fires (real deadline, not "
                         "just a stop-new-dispatch flag).")
    ap.add_argument("--request-timeout", type=int, default=30,
                    help="Per-request client timeout in seconds. Recorded "
                         "as client_timeout (status 599). Independent from "
                         "--max-wall.")
    ap.add_argument("--max-admitted-error-rate", type=float, default=0.05,
                    help="Kill-switch threshold on the admitted-request "
                         "error rate. Default 0.05. Rejections (admission "
                         "refusals, budget refusals, policy blocks) are "
                         "excluded from BOTH numerator and denominator.")
    ap.add_argument("--max-rejection-rate", type=float, default=1.0,
                    help="Kill-switch threshold on rejection rate over ALL "
                         "requests. Default 1.0 (disabled). Set to e.g. 0.5 "
                         "for a normal-service test that fails when the "
                         "service backpressures more than half its traffic.")
    ap.add_argument("--kill-min-samples", type=int, default=20,
                    help="Minimum requests before either kill-switch may "
                         "fire. Default 20.")
    ap.add_argument("--prompt-env", default=None,
                    help="Env var holding the prompt to send (default: hard-coded pong)")
    ap.add_argument("--self-check", action="store_true",
                    help="Run inline self-check on the classifier + rate "
                         "math and exit. No network I/O.")
    args = ap.parse_args()

    if args.self_check:
        return _self_check()

    if not args.profile:
        print("error: profile is required (unless --self-check)", file=sys.stderr)
        return 1

    # Reject nonsensical inputs early (reviewer P1 #2 also asked for this).
    for name, value in (
        ("--max-wall", args.max_wall),
        ("--request-timeout", args.request_timeout),
        ("--total", args.total),
        ("--concurrency", args.concurrency),
        ("--kill-min-samples", args.kill_min_samples),
    ):
        if value <= 0:
            print(f"error: {name} must be > 0 (got {value})", file=sys.stderr)
            return 1
    for name, value in (
        ("--max-admitted-error-rate", args.max_admitted_error_rate),
        ("--max-rejection-rate", args.max_rejection_rate),
    ):
        if not (0.0 <= value <= 1.0):
            print(f"error: {name} must be in [0.0, 1.0] (got {value})", file=sys.stderr)
            return 1

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
    url = f"{server}/gateway/v1/completions"

    print(f"Target:      {url}")
    print(f"Profile:     {args.profile}")
    print(f"Total:       {args.total}  Concurrency: {args.concurrency}  max_tokens: {args.max_tokens}")
    print()

    started = time.monotonic()
    try:
        results = asyncio.run(_run_async(
            url=url, token=token, profile=args.profile,
            total=args.total, concurrency=args.concurrency,
            max_tokens=args.max_tokens,
            max_wall=args.max_wall,
            prompt=prompt,
            request_timeout=args.request_timeout,
            max_admitted_error_rate=args.max_admitted_error_rate,
            max_rejection_rate=args.max_rejection_rate,
            kill_min_samples=args.kill_min_samples,
        ))
    except KeyboardInterrupt:
        print("\n^C — cancelled", file=sys.stderr)
        return 130

    wall = time.monotonic() - started
    return _report(
        results, wall=wall,
        max_admitted_error_rate=args.max_admitted_error_rate,
        max_rejection_rate=args.max_rejection_rate,
    )


def _self_check() -> int:
    """Inline correctness check. Verifies:
      - classifier does not blame upstream for unclassified 429/503;
      - rejection-rate + admitted-error-rate are computed from
        disjoint denominators (reviewer P1 #1 reproducer);
      - report exit code is non-zero when either threshold is exceeded.
    """
    # Classifier basics.
    assert _classify_error(200, b'{"ok":true}') == ("ok", False)
    assert _classify_error(
        429, b'{"error":{"type":"conduct_gateway_admission_refused"}}'
    ) == ("conduct_admission_refused", True)
    assert _classify_error(
        503, b'{"type":"budget_reservation_refused"}'
    ) == ("conduct_budget_refused", True)
    # Reviewer P2 #3: unclassified 429/503 must not blame upstream.
    assert _classify_error(429, b'{}') == ("unknown_origin", False)
    assert _classify_error(503, b'') == ("unknown_origin", False)
    # Guard policy block.
    assert _classify_error(451, b'blocked') == ("conduct_policy_block", True)
    # Client timeout, client error preserved.
    assert _classify_error(599, b'timeout') == ("client_timeout", False)
    assert _classify_error(598, b'boom') == ("client_error", False)

    # Reviewer P1 #1 reproducer: 95 refusals + 4 admitted-errors + 1
    # success. The OLD math (bad excluded from numerator, rejections
    # still in denominator) yielded ~4% and never fired. The NEW math
    # bases the kill-switch on admitted-error-rate over admitted-only.
    fake_results = {
        "latencies":         [0.01] * 100,
        "admitted_latencies": [0.5] * 5,
        "statuses":          Counter({429: 95, 500: 4, 200: 1}),
        "categories":        Counter({
            "conduct_admission_refused": 95,
            "upstream_5xx": 4,
            "ok": 1,
        }),
        "admission_sample":  None,
        "input_tokens":      0,
        "output_tokens":     0,
        "admitted":          5,
        "admitted_errors":   4,
        "rejections":        95,
        "successes":         1,
        "stop_reason":       None,  # completed
    }
    # Redirect stdout for the assertion so this stays quiet on pass.
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exit_code = _report(
            fake_results, wall=1.0,
            max_admitted_error_rate=0.05,
            max_rejection_rate=1.0,
        )
    assert exit_code == 2, (
        f"expected FAIL exit code on 80% admitted-error rate, got {exit_code}\n"
        f"stdout:\n{buf.getvalue()}"
    )
    out = buf.getvalue()
    # Loose matches — report layout may pad columns.
    assert "80.0%" in out and "admitted-error rate" in out, out
    assert "95.0%" in out and "rejection rate" in out, out

    # Zero-admitted edge: only rejections. Should still be a fail
    # when --max-rejection-rate is set below the observed rate.
    fake_all_rejects = dict(fake_results)
    fake_all_rejects.update({
        "admitted": 0, "admitted_errors": 0, "successes": 0,
        "rejections": 100,
        "admitted_latencies": [],
        "statuses": Counter({429: 100}),
        "categories": Counter({"conduct_admission_refused": 100}),
    })
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exit_code = _report(
            fake_all_rejects, wall=1.0,
            max_admitted_error_rate=0.05,
            max_rejection_rate=0.5,
        )
    assert exit_code == 2, buf.getvalue()

    print("self-check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
