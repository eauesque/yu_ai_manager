"""Hailo auto-reboot judge state machine.

Phase 0.5 is observation-only: it records state transitions and would-fire
events, but never calls reboot.

Phase 1+ handles reject staleness timeout, eager mode implementation,
subprocess(systemctl) actuator path, DB quiesce, and LAN cowork drain (Phase 5).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class AutoRebootState(StrEnum):
    IDLE = "idle"
    PREWARN = "prewarn"
    DRAINING = "draining"
    WOULD_FIRE = "would_fire"


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


@dataclass
class AutoRebootConfig:
    """Auto-reboot observation config.

    Phase 0.5 does not implement eager firing; eager input is gated to off in
    from_dict() until Phase 1+ adds the PREWARN shortcut semantics.
    """

    mode: str = "off"
    dry_run: bool = False
    prewarn_threshold_mb: int = 80
    prewarn_duration_seconds: int = 180
    drain_threshold_mb: int = 30
    drain_duration_seconds: int = 60
    drain_consecutive_rejects: int = 3
    fire_grace_seconds: int = 120
    poll_interval_seconds: int = 30
    min_uptime_minutes: int = 30
    max_reboots_per_day: int = 4
    cooldown_minutes: int = 15

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AutoRebootConfig:
        if not isinstance(raw, dict):
            raw = {}

        def _int(name: str, default: int, minimum: int = 1) -> int:
            try:
                return max(minimum, int(raw.get(name, default)))
            except (TypeError, ValueError):
                return default

        mode = str(raw.get("mode", "off")).lower()
        if mode not in {"off", "lazy", "eager"}:
            mode = "off"
        elif mode == "eager":
            logger.warning(
                "hailo_auto_reboot mode='eager' not implemented in Phase 0.5; "
                "falling back to 'off'"
            )
            mode = "off"

        return cls(
            mode=mode,
            dry_run=_bool(raw.get("dry_run", False)),
            prewarn_threshold_mb=_int("prewarn_threshold_mb", 80),
            prewarn_duration_seconds=_int("prewarn_duration_seconds", 180),
            drain_threshold_mb=_int("drain_threshold_mb", 30),
            drain_duration_seconds=_int("drain_duration_seconds", 60),
            drain_consecutive_rejects=_int("drain_consecutive_rejects", 3),
            fire_grace_seconds=_int("fire_grace_seconds", 120),
            poll_interval_seconds=_int("poll_interval_seconds", 30),
            min_uptime_minutes=_int("min_uptime_minutes", 30),
            max_reboots_per_day=_int("max_reboots_per_day", 4),
            cooldown_minutes=_int("cooldown_minutes", 15),
        )


@dataclass
class _SubThreshold:
    threshold_mb: int
    duration_seconds: int
    first_below_ts: float | None = None

    def update(self, free_mb: int | None, now_ts: float) -> bool:
        if free_mb is None or free_mb >= self.threshold_mb:
            self.first_below_ts = None
            return False
        if self.first_below_ts is None:
            self.first_below_ts = now_ts
            return False
        return (now_ts - self.first_below_ts) >= self.duration_seconds

    def reset(self) -> None:
        self.first_below_ts = None


class RejectTracker:
    """Thread-safe counter for consecutive observed HailoRT load failures."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._consecutive_rejects = 0
        self._total_rejects = 0
        self._last_reason: str | None = None
        self._last_free_mb: int | None = None
        self._last_required_mb: int | None = None
        self._last_reject_ts: float | None = None

    def record_reject(
        self,
        *,
        reason: str,
        free_mb: int | None,
        required_mb: int | None,
    ) -> None:
        with self._lock:
            self._consecutive_rejects += 1
            self._total_rejects += 1
            self._last_reason = reason
            self._last_free_mb = free_mb
            self._last_required_mb = required_mb
            self._last_reject_ts = time.time()

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_rejects = 0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "consecutive_rejects": self._consecutive_rejects,
                "total_rejects": self._total_rejects,
                "last_reason": self._last_reason,
                "last_free_mb": self._last_free_mb,
                "last_required_mb": self._last_required_mb,
                "last_reject_ts": self._last_reject_ts,
            }


class AutoRebootJudge:
    """Single-process auto-reboot observation state machine."""

    def __init__(
        self,
        config: AutoRebootConfig,
        cma_reader: Callable[[], int | None],
        reject_tracker: RejectTracker,
        event_logger: Callable[..., None],
        runtime_version_reader: Callable[[], str | None],
    ) -> None:
        self._cfg = config
        self._read_cma = cma_reader
        self._rejects = reject_tracker
        self._log_event = event_logger
        self._read_version = runtime_version_reader
        self._state = AutoRebootState.IDLE
        self._lock = threading.Lock()
        self._prewarn_track = _SubThreshold(
            config.prewarn_threshold_mb,
            config.prewarn_duration_seconds,
        )
        self._drain_track = _SubThreshold(
            config.drain_threshold_mb,
            config.drain_duration_seconds,
        )
        self._drain_entered_ts: float | None = None
        self._would_fire_count = 0
        self._prev_tick_ts: float | None = None

    def tick(self, now_ts: float | None = None) -> AutoRebootState:
        now = time.time() if now_ts is None else now_ts
        
        # Call side-effect functions outside the lock
        cma_free_mb = self._read_cma()
        reject_snapshot = self._rejects.snapshot()

        with self._lock:
            prev_tick_ts = self._prev_tick_ts
            seconds_since_prev_tick = None if prev_tick_ts is None else now - prev_tick_ts
            self._prev_tick_ts = now
            # Phase 1+ will separate state mutation from side-effect dispatch.
            reject_draining = (
                reject_snapshot["consecutive_rejects"]
                >= self._cfg.drain_consecutive_rejects
            )
            has_load_failure = reject_snapshot["consecutive_rejects"] > 0
            cma_prewarn = self._prewarn_track.update(cma_free_mb, now)
            cma_draining = self._drain_track.update(cma_free_mb, now)

            if (
                self._state in {AutoRebootState.DRAINING, AutoRebootState.WOULD_FIRE}
                and self._has_recovered(reject_snapshot)
            ):
                self._transition(
                    AutoRebootState.IDLE,
                    "drain_cleared",
                    now,
                    cma_free_mb,
                    reason="load_succeeded",
                    seconds_since_prev_tick=seconds_since_prev_tick,
                )
                self._prewarn_track.reset()
                self._drain_track.reset()
                self._drain_entered_ts = None
                return self._state

            if (
                self._state == AutoRebootState.PREWARN
                and (
                    not has_load_failure
                    or (cma_free_mb is not None and cma_free_mb >= self._cfg.prewarn_threshold_mb)
                )
            ):
                self._transition(
                    AutoRebootState.IDLE,
                    "prewarn_cleared",
                    now,
                    cma_free_mb,
                    reason="cma_recovered",
                    seconds_since_prev_tick=seconds_since_prev_tick,
                )
                self._prewarn_track.reset()
                self._drain_track.reset()
                self._drain_entered_ts = None
                return self._state

            if self._state == AutoRebootState.IDLE and has_load_failure and cma_prewarn:
                self._transition(
                    AutoRebootState.PREWARN,
                    "prewarn_entered",
                    now,
                    cma_free_mb,
                    reason="cma",
                    seconds_since_prev_tick=seconds_since_prev_tick,
                )

            if (
                self._state in {AutoRebootState.IDLE, AutoRebootState.PREWARN}
                and ((has_load_failure and cma_draining) or reject_draining)
            ):
                reason = "rejects" if reject_draining else "cma"
                self._transition(
                    AutoRebootState.DRAINING,
                    "drain_entered",
                    now,
                    cma_free_mb,
                    reason=reason,
                    seconds_since_prev_tick=seconds_since_prev_tick,
                )
                self._drain_entered_ts = now

            if (
                self._state == AutoRebootState.DRAINING
                and self._cfg.mode != "off"
                and self._drain_entered_ts is not None
                and (now - self._drain_entered_ts) >= self._cfg.fire_grace_seconds
            ):
                self._would_fire_count += 1
                self._transition(
                    AutoRebootState.WOULD_FIRE,
                    "would_fire",
                    now,
                    cma_free_mb,
                    reason="fire_grace_elapsed",
                    seconds_since_prev_tick=seconds_since_prev_tick,
                )

            return self._state

    def snapshot(self) -> dict[str, Any]:
        rejects = self._rejects.snapshot()
        with self._lock:
            state = self._state.value
            would_fire_count = self._would_fire_count
        return {
            "enabled": self._cfg.mode != "off",
            "mode": self._cfg.mode,
            "dry_run": self._cfg.dry_run,
            "state": state,
            "would_fire_count": would_fire_count,
            "consecutive_rejects": rejects["consecutive_rejects"],
            "hailo_runtime_version": self._read_version(),
        }

    def _transition(
        self,
        state: AutoRebootState,
        event: str,
        now_ts: float,
        cma_free_mb: int | None,
        *,
        reason: str,
        seconds_since_prev_tick: float | None,
    ) -> None:
        rejects_snapshot = self._rejects.snapshot()
        self._state = state
        self._log_event(
            event,
            cma_free_mb=cma_free_mb,
            hailo_runtime_version=self._read_version(),
            state=state.value,
            mode=self._cfg.mode,
            dry_run=self._cfg.dry_run,
            reason=reason,
            now_ts=now_ts,
            consecutive_rejects=rejects_snapshot["consecutive_rejects"],
            poll_interval_seconds=self._cfg.poll_interval_seconds,
            seconds_since_prev_tick=seconds_since_prev_tick,
        )
        if self._cfg.mode != "off" and event in {"drain_entered", "would_fire"}:
            from core.hailo_device_core.auto_reboot_logger import log_warning_summary

            log_warning_summary(
                event,
                state=state.value,
                mode=self._cfg.mode,
                dry_run=self._cfg.dry_run,
                cma_free_mb=cma_free_mb,
                consecutive_rejects=rejects_snapshot["consecutive_rejects"],
            )

    def _has_recovered(
        self,
        reject_snapshot: dict[str, Any],
    ) -> bool:
        rejects_recovered = reject_snapshot["consecutive_rejects"] == 0
        return rejects_recovered


_judge: AutoRebootJudge | None = None
_judge_lock = threading.Lock()
_reject_tracker: RejectTracker | None = None
_reject_tracker_lock = threading.Lock()


def register_judge(judge: AutoRebootJudge) -> None:
    global _judge
    with _judge_lock:
        _judge = judge


def get_judge() -> AutoRebootJudge | None:
    with _judge_lock:
        return _judge


def get_reject_tracker() -> RejectTracker:
    global _reject_tracker
    with _reject_tracker_lock:
        if _reject_tracker is None:
            _reject_tracker = RejectTracker()
        return _reject_tracker
