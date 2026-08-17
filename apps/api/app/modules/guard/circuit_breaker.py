"""Circuit breaker for outbound provider calls.

State machine (per key):
  CLOSED    — normal traffic; count consecutive failures
  OPEN      — reject all calls immediately; after recovery_timeout, probe
  HALF_OPEN — allow up to half_open_max_calls test calls; recover on all-success

Wired into routers/proxy.py::_forward: call allow() before the upstream
request, record_success/record_failure after the response is classified.

In-memory, per-process. State resets on restart (which is equivalent to a
manual breaker reset — acceptable for a v1). Not persisted.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Callable


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerState:
    state: State = State.CLOSED
    consecutive_failures: int = 0
    opened_at: float = 0.0
    half_open_probes: int = 0
    half_open_successes: int = 0


TransitionHook = Callable[[str, State, State], None]


class CircuitBreaker:
    """Per-key breaker.

    Defaults tuned for LLM upstreams: 5 consecutive failures trip; 30s
    quiet period; then up to 3 probes to confirm recovery.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._clock = clock
        self._states: dict[str, BreakerState] = {}
        self._lock = Lock()
        self._hooks: list[TransitionHook] = []

    def register_transition_hook(self, hook: TransitionHook) -> None:
        """Register a callback: (key, from_state, to_state). Called under lock."""
        self._hooks.append(hook)

    def _get(self, key: str) -> BreakerState:
        st = self._states.get(key)
        if st is None:
            st = BreakerState()
            self._states[key] = st
        return st

    def _transition(self, key: str, st: BreakerState, to: State) -> None:
        frm = st.state
        if frm == to:
            return
        st.state = to
        if to == State.OPEN:
            st.opened_at = self._clock()
            st.half_open_probes = 0
            st.half_open_successes = 0
        elif to == State.HALF_OPEN:
            st.half_open_probes = 0
            st.half_open_successes = 0
        elif to == State.CLOSED:
            st.consecutive_failures = 0
            st.half_open_probes = 0
            st.half_open_successes = 0
        for hook in self._hooks:
            try:
                hook(key, frm, to)
            except Exception:  # noqa: BLE001
                # Notification failures must not crash the breaker
                pass

    def allow(self, key: str) -> bool:
        """Return True if a call is allowed; increments probe counter in HALF_OPEN."""
        with self._lock:
            st = self._get(key)
            if st.state == State.CLOSED:
                return True
            if st.state == State.OPEN:
                if self._clock() - st.opened_at >= self.recovery_timeout:
                    self._transition(key, st, State.HALF_OPEN)
                    st.half_open_probes = 1
                    return True
                return False
            # HALF_OPEN
            if st.half_open_probes >= self.half_open_max_calls:
                return False
            st.half_open_probes += 1
            return True

    def record_success(self, key: str) -> None:
        with self._lock:
            st = self._get(key)
            if st.state == State.CLOSED:
                st.consecutive_failures = 0
                return
            if st.state == State.HALF_OPEN:
                st.half_open_successes += 1
                if st.half_open_successes >= self.half_open_max_calls:
                    self._transition(key, st, State.CLOSED)
                return
            # OPEN — a success here is unusual (a leaked call). Ignore.

    def record_failure(self, key: str) -> None:
        with self._lock:
            st = self._get(key)
            if st.state == State.CLOSED:
                st.consecutive_failures += 1
                if st.consecutive_failures >= self.failure_threshold:
                    self._transition(key, st, State.OPEN)
                return
            if st.state == State.HALF_OPEN:
                # Any failure during probe returns to OPEN
                self._transition(key, st, State.OPEN)
                return
            # OPEN — refresh timer so the recovery window restarts.
            st.opened_at = self._clock()

    def state(self, key: str) -> State:
        with self._lock:
            return self._get(key).state

    def snapshot(self, key: str) -> dict:
        with self._lock:
            st = self._get(key)
            return {
                "key": key,
                "state": st.state.value,
                "consecutive_failures": st.consecutive_failures,
                "opened_at": st.opened_at,
                "half_open_probes": st.half_open_probes,
                "half_open_successes": st.half_open_successes,
                "recovery_timeout_s": self.recovery_timeout,
                "failure_threshold": self.failure_threshold,
                "half_open_max_calls": self.half_open_max_calls,
            }

    def reset(self, key: str | None = None) -> None:
        """Test helper — clear one key or all keys."""
        with self._lock:
            if key is None:
                self._states.clear()
            else:
                self._states.pop(key, None)


import logging

_log = logging.getLogger(__name__)


def _default_log_hook(key: str, frm: State, to: State) -> None:
    """Log every state change once. Callers can register additional hooks
    (Slack, PagerDuty) via CircuitBreaker.register_transition_hook."""
    level = logging.WARNING if to == State.OPEN else logging.INFO
    _log.log(level, "guard.circuit_breaker.transition key=%s from=%s to=%s",
             key, frm.value, to.value)


# Process-global instance for the proxy call path.
_global_breaker: CircuitBreaker | None = None


def get_breaker() -> CircuitBreaker:
    global _global_breaker
    if _global_breaker is None:
        _global_breaker = CircuitBreaker()
        _global_breaker.register_transition_hook(_default_log_hook)
    return _global_breaker
