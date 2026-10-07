"""Regression: the rich TUI's first frame must render (guard_cfg NameError)."""
import pytest

pytest.importorskip("rich")

from conduct_cli.commands import sessions


class _OneFrameLive:
    """Stand-in for rich.live.Live: render one frame, then simulate Ctrl+C."""

    def __init__(self, *a, **kw):
        self.frames = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def update(self, renderable):
        self.frames.append(renderable)
        raise KeyboardInterrupt


def test_render_tui_first_frame(monkeypatch):
    import rich.live

    monkeypatch.setattr(sessions, "_load_config", lambda: {})
    monkeypatch.setattr(sessions, "_load_sessions", lambda: [])
    monkeypatch.setattr(sessions, "_fetch_runs", lambda cfg: [])
    monkeypatch.setattr(sessions, "_fetch_guard_activity", lambda cfg: [])
    monkeypatch.setattr(rich.live, "Live", _OneFrameLive)

    sessions._render_tui([])  # NameError here before the fix
