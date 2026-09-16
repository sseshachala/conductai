"""Reviewer's post-merge audit findings: Z1 + Z2.

Z1 — v2 exception path with durable-audit OFF was losing audit rows
because the fix used ``background.add_task(_record_audit, ...)`` and
FastAPI only drains queued background tasks after a normal response.
A ``raise`` propagating to FastAPI's error handler skipped the queue
entirely. Fix runs the audit call via ``asyncio.to_thread`` before
re-raising, so the row lands regardless of whether the response
completes.

Z2 — the durable-on streaming wrapper enforced the profile deadline
via ``asyncio.wait_for`` per chunk (Y3), but the durable-off wrapper
still used a plain ``async for`` that could block indefinitely on a
stalled upstream. Timeout enforcement should be independent of
recording mode.

Both are source-level regression guards — the write mechanics are
covered by the underlying audit-writer suite; here we lock the
handler wiring so a future edit can't reintroduce either regression.
"""
from __future__ import annotations

from pathlib import Path


_HANDLER_SRC = (
    Path(__file__).resolve().parents[2]
    / "app" / "modules" / "guard" / "gateway_handler.py"
).read_text(encoding="utf-8")


# ─── Z1 ───────────────────────────────────────────────────────────────


def test_exception_path_uses_synchronous_to_thread_not_background():
    """The v2 exception-path elif branch must use
    ``asyncio.to_thread(_record_audit, ...)``, NOT
    ``background.add_task(_record_audit, ...)``. background.add_task
    only fires after a normal response — an exception in the handler
    means the task never runs, and the audit row is lost.

    Guards against a future edit that "cleans up" the sync-in-thread
    pattern back to background scheduling."""
    # Locate the exception handler that fires when durable is off.
    start = _HANDLER_SRC.index("except BaseException as _forward_exc")
    end = _HANDLER_SRC.index("finally:", start)
    block = _HANDLER_SRC[start:end]

    # The elif fallback must exist.
    assert "elif _v2_plan is not None:" in block, (
        "exception handler must have the v2-fallback elif branch"
    )

    # And it must run the audit call synchronously in a thread.
    assert "_asyncio.to_thread" in block or "asyncio.to_thread" in block, (
        "exception-path audit fallback must use asyncio.to_thread "
        "so the writer runs BEFORE the exception re-raises. "
        "background.add_task is unsafe here — the queue is not "
        "drained when the response is an exception."
    )

    # AND it must NOT USE background.add_task for the v2 fallback —
    # that was the original Y2 bug the reviewer flagged in Z1. Strip
    # ``#`` comment lines before scanning so the explanatory comment
    # that references the old pattern doesn't false-positive.
    elif_idx = block.index("elif _v2_plan is not None:")
    elif_block = block[elif_idx:]
    non_comment_lines = [
        ln for ln in elif_block.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    non_comment = "\n".join(non_comment_lines)
    assert "background.add_task" not in non_comment, (
        "v2 exception-path fallback must NOT use background.add_task "
        "— queued tasks are silently dropped when the response is a "
        "raised exception. Use asyncio.to_thread(_record_audit, ...) "
        "instead so the row lands before re-raise."
    )


# ─── Z2 ───────────────────────────────────────────────────────────────


def test_stream_record_legacy_takes_deadline_kwarg():
    """The durable-off streaming wrapper must accept
    ``stream_deadline_seconds`` so the deadline enforcement isn't
    coupled to the audit flag. Reviewer's finding: stalled streams
    with durable-off hung past ``timeout_seconds``."""
    from app.modules.guard import gateway_handler
    import inspect
    sig = inspect.signature(gateway_handler._wrap_v2_stream_record_legacy)
    assert "stream_deadline_seconds" in sig.parameters, (
        "_wrap_v2_stream_record_legacy must accept stream_deadline_seconds "
        "so streaming timeout is enforced whether durable-audit is on "
        "or off. Y3 fixed this for the durable-on wrapper only; the "
        "durable-off wrapper needs the same coverage."
    )


def test_stream_record_legacy_wraps_chunk_fetch_in_wait_for():
    """The wrapper must actually use ``asyncio.wait_for`` around
    chunk fetches — a signature that just accepts the kwarg but
    ignores it would silently regress. Source-scan for the wait_for
    call inside the wrapper body."""
    from app.modules.guard import gateway_handler
    import inspect
    src = inspect.getsource(gateway_handler._wrap_v2_stream_record_legacy)
    assert "wait_for" in src, (
        "durable-off streaming wrapper must call asyncio.wait_for on "
        "the chunk fetch. Without it a stalled upstream blocks past "
        "the profile deadline (Y3 fix for durable-on)."
    )
    assert "TimeoutError" in src, (
        "wrapper must translate wait_for's TimeoutError into a "
        "recorded failure with execution_status='timeout'."
    )


def test_handler_passes_deadline_to_record_legacy_wrapper():
    """Symmetric to the durable-on wiring — the handler MUST pass the
    profile's timeout_seconds to the durable-off wrapper. Regressing
    this would leave the wrapper accepting the kwarg but never
    getting a value → deadline enforcement silently disabled."""
    # Locate the call site — find the OPEN paren, then walk forward
    # tracking depth until the matching close. The inner ``str(...)``
    # and similar nested calls would trip a naive first-close scan.
    idx = _HANDLER_SRC.index("_wrap_v2_stream_record_legacy(")
    depth = 0
    j = idx
    while j < len(_HANDLER_SRC):
        c = _HANDLER_SRC[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    call = _HANDLER_SRC[idx : j + 1]
    assert "stream_deadline_seconds=" in call, (
        "handler must pass stream_deadline_seconds to "
        "_wrap_v2_stream_record_legacy (mirrors the durable-on wire "
        "for Y3). Absent → wrapper accepts the kwarg but never gets "
        "a value → deadline enforcement silently off for durable-off "
        "workspaces."
    )
