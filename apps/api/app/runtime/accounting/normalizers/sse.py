"""Chunk-safe Server-Sent Events parser.

Handles the framing quirks that the pre-Session-3 line-by-line extractor
missed:

- Chunk boundaries mid-line (buffer partial line to next feed)
- CRLF and LF line endings
- Multiple ``data:`` lines concatenated per event (SSE spec)
- Comments starting with ``:``
- Multi-byte UTF-8 split across chunks (decode is deferred to event dispatch)

Stateful: reuse one parser instance for a whole stream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class SSEEvent:
    """One dispatched SSE event."""

    event: str  # defaults to "message" per SSE spec
    data: str


class SSEParser:
    """Feed raw bytes chunks; iterate dispatched events."""

    def __init__(self) -> None:
        self._buffer = b""
        self._event: str | None = None
        self._data_lines: list[str] = []

    def feed(self, chunk: bytes) -> Iterator[SSEEvent]:
        """Feed one chunk and yield any complete events dispatched."""
        if not chunk:
            return
        self._buffer += chunk
        while True:
            newline_idx = self._buffer.find(b"\n")
            if newline_idx < 0:
                return
            raw_line = self._buffer[:newline_idx]
            self._buffer = self._buffer[newline_idx + 1 :]
            line = raw_line.rstrip(b"\r").decode("utf-8", errors="replace")
            if line == "":
                event = self._dispatch()
                if event is not None:
                    yield event
            elif line.startswith(":"):
                continue  # comment
            elif line.startswith("event:"):
                self._event = line[len("event:") :].lstrip()
            elif line.startswith("data:"):
                self._data_lines.append(line[len("data:") :].lstrip())
            elif line.startswith("id:") or line.startswith("retry:"):
                continue
            else:
                # Malformed lines (no field name) are ignored per SSE spec.
                continue

    def flush(self) -> Iterator[SSEEvent]:
        """Emit any buffered partial event. Call at end of stream."""
        if self._data_lines:
            event = self._dispatch()
            if event is not None:
                yield event

    def _dispatch(self) -> SSEEvent | None:
        if not self._data_lines:
            return None
        event = SSEEvent(
            event=self._event or "message",
            data="\n".join(self._data_lines),
        )
        self._event = None
        self._data_lines = []
        return event


def parse_all(payload: bytes) -> list[SSEEvent]:
    """Convenience for tests + one-shot use — parse a complete stream."""
    parser = SSEParser()
    events = list(parser.feed(payload))
    events.extend(parser.flush())
    return events
