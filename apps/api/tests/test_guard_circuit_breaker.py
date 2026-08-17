"""Unit tests for the guard circuit breaker state machine."""
from __future__ import annotations

from app.modules.guard.circuit_breaker import CircuitBreaker, State


class FakeClock:
    """Deterministic time source for state-transition tests."""
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_breaker(**kw):
    clock = FakeClock()
    b = CircuitBreaker(
        failure_threshold=kw.get("failure_threshold", 3),
        recovery_timeout=kw.get("recovery_timeout", 10.0),
        half_open_max_calls=kw.get("half_open_max_calls", 2),
        clock=clock,
    )
    return b, clock


def test_starts_closed_and_allows():
    b, _ = make_breaker()
    assert b.state("anthropic") == State.CLOSED
    assert b.allow("anthropic") is True


def test_success_resets_consecutive_failures():
    b, _ = make_breaker(failure_threshold=3)
    b.record_failure("anthropic")
    b.record_failure("anthropic")
    b.record_success("anthropic")
    b.record_failure("anthropic")
    b.record_failure("anthropic")
    # Still 2 consecutive failures, not 4 — success should have reset
    assert b.state("anthropic") == State.CLOSED


def test_trips_open_after_threshold_failures():
    b, _ = make_breaker(failure_threshold=3)
    b.record_failure("anthropic")
    assert b.state("anthropic") == State.CLOSED
    b.record_failure("anthropic")
    assert b.state("anthropic") == State.CLOSED
    b.record_failure("anthropic")
    assert b.state("anthropic") == State.OPEN


def test_open_state_rejects_calls():
    b, _ = make_breaker(failure_threshold=1)
    b.record_failure("anthropic")
    assert b.state("anthropic") == State.OPEN
    assert b.allow("anthropic") is False


def test_open_transitions_to_half_open_after_timeout():
    b, clock = make_breaker(failure_threshold=1, recovery_timeout=10.0)
    b.record_failure("anthropic")
    assert b.state("anthropic") == State.OPEN
    clock.advance(9.9)
    assert b.allow("anthropic") is False  # still inside window
    clock.advance(0.2)                     # cross threshold
    assert b.allow("anthropic") is True    # first probe
    assert b.state("anthropic") == State.HALF_OPEN


def test_half_open_allows_up_to_max_probes():
    b, clock = make_breaker(failure_threshold=1, recovery_timeout=10.0, half_open_max_calls=3)
    b.record_failure("anthropic")
    clock.advance(11)
    assert b.allow("anthropic") is True  # probe 1
    assert b.allow("anthropic") is True  # probe 2
    assert b.allow("anthropic") is True  # probe 3
    assert b.allow("anthropic") is False  # cap hit


def test_half_open_all_successes_close_the_breaker():
    b, clock = make_breaker(failure_threshold=3, recovery_timeout=10.0, half_open_max_calls=2)
    for _ in range(3):
        b.record_failure("anthropic")
    assert b.state("anthropic") == State.OPEN
    clock.advance(11)
    b.allow("anthropic")
    b.record_success("anthropic")
    assert b.state("anthropic") == State.HALF_OPEN
    b.allow("anthropic")
    b.record_success("anthropic")
    assert b.state("anthropic") == State.CLOSED
    # After close, the failure counter starts from zero — a single failure
    # under a threshold=3 config should not trip the breaker again.
    b.record_failure("anthropic")
    assert b.state("anthropic") == State.CLOSED


def test_half_open_any_failure_reopens():
    b, clock = make_breaker(failure_threshold=1, recovery_timeout=10.0, half_open_max_calls=3)
    b.record_failure("anthropic")
    clock.advance(11)
    b.allow("anthropic")       # probe 1
    b.record_success("anthropic")
    b.allow("anthropic")       # probe 2
    b.record_failure("anthropic")  # probe fails → back to OPEN
    assert b.state("anthropic") == State.OPEN


def test_open_failure_refreshes_the_recovery_window():
    b, clock = make_breaker(failure_threshold=1, recovery_timeout=10.0)
    b.record_failure("anthropic")
    opened_first = b.snapshot("anthropic")["opened_at"]
    clock.advance(5.0)
    b.record_failure("anthropic")  # another failure while OPEN
    opened_second = b.snapshot("anthropic")["opened_at"]
    assert opened_second > opened_first


def test_breakers_are_isolated_per_key():
    b, _ = make_breaker(failure_threshold=2)
    b.record_failure("anthropic")
    b.record_failure("anthropic")
    assert b.state("anthropic") == State.OPEN
    assert b.state("openai") == State.CLOSED
    assert b.allow("openai") is True


def test_transition_hook_fires_on_state_change():
    b, _ = make_breaker(failure_threshold=1)
    calls: list[tuple[str, State, State]] = []
    b.register_transition_hook(lambda k, f, t: calls.append((k, f, t)))
    b.record_failure("anthropic")
    assert calls == [("anthropic", State.CLOSED, State.OPEN)]


def test_transition_hook_exceptions_do_not_break_breaker():
    b, _ = make_breaker(failure_threshold=1)
    def raiser(*_): raise RuntimeError("notification down")
    b.register_transition_hook(raiser)
    # Should not raise
    b.record_failure("anthropic")
    assert b.state("anthropic") == State.OPEN


def test_snapshot_returns_current_state_fields():
    b, _ = make_breaker(failure_threshold=3)
    b.record_failure("anthropic")
    snap = b.snapshot("anthropic")
    assert snap["state"] == "closed"
    assert snap["consecutive_failures"] == 1
    assert snap["failure_threshold"] == 3
    assert snap["recovery_timeout_s"] == 10.0


def test_reset_clears_state():
    b, _ = make_breaker(failure_threshold=1)
    b.record_failure("anthropic")
    assert b.state("anthropic") == State.OPEN
    b.reset("anthropic")
    assert b.state("anthropic") == State.CLOSED
