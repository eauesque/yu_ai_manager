"""Ring buffer for application log entries with SSE streaming support."""

from __future__ import annotations

import contextlib
import logging
import sys
import threading
from collections import deque
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field

from core.infra_core.log_scrub import scrub_secrets


@dataclass(slots=True)
class LogEntry:
    """Single log entry stored in the ring buffer."""

    timestamp: float
    level: str
    source: str
    message: str
    seq: int = field(default=0)

    def to_dict(self) -> dict:
        return asdict(self)


class LogRingBuffer:
    """Thread-safe ring buffer for log entries.

    Supports blocking iteration via ``stream_from()`` for SSE consumers.
    """

    def __init__(self, maxlen: int = 1000) -> None:
        self._buf: deque[LogEntry] = deque(maxlen=maxlen)
        self._cond = threading.Condition()
        self._seq = 0

    # ---- write side ----

    def append(self, entry: LogEntry) -> None:
        # Scrub on the way in, not on the way out. Authorization decides who may
        # read this buffer; it does not decide whether a PIN belonged in it. A
        # secret that never enters cannot leak through a reader that forgot to
        # call the scrubber -- and the fleet stream hands these lines to a
        # remote peer.
        entry.message = scrub_secrets(entry.message)
        with self._cond:
            self._seq += 1
            entry.seq = self._seq
            self._buf.append(entry)
            self._cond.notify_all()

    # ---- read side ----

    def recent(
        self, limit: int = 200, level: str | None = None
    ) -> list[dict]:
        """Return the most recent *limit* entries (optionally filtered)."""
        _min = _level_num(level) if level else 0
        with self._cond:
            items = [
                e for e in self._buf
                if logging.getLevelName(e.level.upper()) >= _min
            ]
        return [e.to_dict() for e in items[-limit:]]

    def get_since(self, after_seq: int, level: str | None = None) -> list[dict]:
        """Return entries since *after_seq* without blocking."""
        _min = _level_num(level) if level else 0
        with self._cond:
            batch = [
                e for e in self._buf
                if e.seq > after_seq
                and logging.getLevelName(e.level.upper()) >= _min
            ]
        return [e.to_dict() for e in batch]

    def stream_from(
        self,
        after_seq: int = 0,
        timeout: float = 30.0,
        level: str | None = None,
    ) -> Iterator[list[dict]]:
        """Yield batches of new entries (blocks until available).

        Caller should iterate in a loop; each yield returns a list of
        new entries since *after_seq*.  Returns empty list on timeout
        (useful for heartbeat).
        """
        _min = _level_num(level) if level else 0
        # Use a list to allow mutation inside the lambda without B023
        seq = [after_seq]
        while True:
            with self._cond:
                self._cond.wait_for(
                    lambda: self._seq > seq[0] or self._closed_flag(),
                    timeout=timeout,
                )
                batch = [
                    e for e in self._buf
                    if e.seq > seq[0]
                    and logging.getLevelName(e.level.upper()) >= _min
                ]
                if batch:
                    seq[0] = batch[-1].seq
            yield [e.to_dict() for e in batch]

    def _closed_flag(self) -> bool:
        # Always False; exists so wait_for has a secondary predicate
        return False

    @property
    def last_seq(self) -> int:
        with self._cond:
            return self._seq


class RingBufferHandler(logging.Handler):
    """Python logging handler that feeds into a :class:`LogRingBuffer`."""

    def __init__(self, ring: LogRingBuffer) -> None:
        super().__init__()
        self._ring = ring

    def _safe_message(self, record: logging.LogRecord, exc: BaseException) -> str:
        try:
            base = record.getMessage()
        except BaseException as msg_exc:
            base = f"<log message formatting failed: {type(msg_exc).__name__}: {msg_exc}>"

        if record.exc_info:
            exc_type, exc_value, _tb = record.exc_info
            exc_name = getattr(exc_type, "__name__", str(exc_type))
            exc_text = str(exc_value) if exc_value is not None else ""
            base = f"{base}\n[{exc_name}] {exc_text}" if exc_text else f"{base}\n[{exc_name}]"

        return (
            f"{base}\n"
            f"[log formatting failed: {type(exc).__name__}: {exc}]"
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = LogEntry(
                timestamp=record.created,
                level=record.levelname,
                source=record.name,
                message=self.format(record),
            )
            self._ring.append(entry)
        except BaseException as exc:
            try:
                entry = LogEntry(
                    timestamp=record.created,
                    level=record.levelname,
                    source=record.name,
                    message=self._safe_message(record, exc),
                )
                self._ring.append(entry)
            except BaseException:
                with contextlib.suppress(BaseException):
                    sys.stderr.write(
                        f"[RingBufferHandler] emit failed for {record.name}: "
                        f"{type(exc).__name__}: {exc}\n"
                    )


def _level_num(name: str | None) -> int:
    if not name:
        return 0
    return logging.getLevelName(name.upper())


# ---- Module-level singleton ----
log_ring = LogRingBuffer()
