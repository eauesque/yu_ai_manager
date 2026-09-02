"""Anomaly detection pattern implementations.

Contains the individual detection algorithms used by AnomalyDetector:
1. Repetition detection (consecutive identical calls)
2. Batch size spike detection
3. Error-ignore detection (retry after errors)
4. Behavior shift detection (read->write ratio change)
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from core.agent_safety.anomaly_detector_types import (
    SEVERITY_CRITICAL,
    SEVERITY_SUSPICIOUS,
    SEVERITY_WARNING,
    AnomalyAlert,
    _ActionRecord,
)

logger = logging.getLogger(__name__)


class AnomalyPatternsMixin:
    """Mixin class providing anomaly detection pattern methods.

    Expects the host class to have:
      - _history: deque of _ActionRecord
      - max_identical_consecutive, max_same_tool_per_window,
        window_sec, batch_size_spike_factor, max_retry_after_error,
        read_write_ratio_shift, behavior_window: config params
    """

    def _detect(self, latest: _ActionRecord) -> list[AnomalyAlert]:
        """Run all detection patterns. Must be called with _lock held."""
        alerts: list[AnomalyAlert] = []

        alert = self._detect_repetition(latest)
        if alert:
            alerts.append(alert)

        alert = self._detect_batch_spike(latest)
        if alert:
            alerts.append(alert)

        alert = self._detect_error_ignore(latest)
        if alert:
            alerts.append(alert)

        alert = self._detect_behavior_shift(latest)
        if alert:
            alerts.append(alert)

        return alerts

    def _detect_repetition(self, latest: _ActionRecord) -> AnomalyAlert | None:
        """Pattern 1: Consecutive identical tool+params calls."""
        consecutive = 0
        for rec in reversed(self._history):
            if rec.tool_name == latest.tool_name and rec.params_hash == latest.params_hash:
                consecutive += 1
            else:
                break

        if consecutive >= self.max_identical_consecutive:
            return AnomalyAlert(
                severity=SEVERITY_CRITICAL if consecutive >= self.max_identical_consecutive * 2 else SEVERITY_WARNING,
                pattern="repetition",
                message=(
                    f"同一操作が {consecutive} 回連続で実行されています "
                    f"(tool={latest.tool_name})"
                ),
                tool_name=latest.tool_name,
            )

        # Same-tool high frequency check
        now = latest.timestamp
        window_start = now - self.window_sec
        same_tool_count = sum(
            1 for r in self._history
            if r.tool_name == latest.tool_name and r.timestamp >= window_start
        )
        if same_tool_count >= self.max_same_tool_per_window:
            return AnomalyAlert(
                severity=SEVERITY_WARNING,
                pattern="high_frequency",
                message=(
                    f"{latest.tool_name} が {self.window_sec} 秒間に "
                    f"{same_tool_count} 回呼び出されました"
                ),
                tool_name=latest.tool_name,
            )

        return None

    def _detect_batch_spike(self, latest: _ActionRecord) -> AnomalyAlert | None:
        """Pattern 2: Sudden increase in batch size."""
        if latest.batch_size <= 1:
            return None

        # Calculate average batch size of recent same-tool calls
        same_tool_batches = [
            r.batch_size for r in self._history
            if r.tool_name == latest.tool_name and r.batch_size > 0
            and r is not latest  # Exclude the latest
        ]

        if len(same_tool_batches) < 3:
            return None

        avg_batch = sum(same_tool_batches) / len(same_tool_batches)
        if avg_batch > 0 and latest.batch_size >= avg_batch * self.batch_size_spike_factor:
            return AnomalyAlert(
                severity=SEVERITY_WARNING,
                pattern="batch_spike",
                message=(
                    f"{latest.tool_name} のバッチサイズが急増: "
                    f"{latest.batch_size} (平均 {avg_batch:.0f} の "
                    f"{latest.batch_size / avg_batch:.1f} 倍)"
                ),
                tool_name=latest.tool_name,
            )

        return None

    def _detect_error_ignore(self, latest: _ActionRecord) -> AnomalyAlert | None:
        """Pattern 3: Retry after consecutive errors without change."""
        if latest.is_error:
            return None

        # Check if recent same-tool calls had consecutive errors
        error_streak = 0
        for rec in reversed(list(self._history)[:-1]):  # Exclude the latest
            if rec.tool_name == latest.tool_name:
                if rec.is_error:
                    error_streak += 1
                else:
                    break
            else:
                break

        if error_streak >= self.max_retry_after_error:
            return AnomalyAlert(
                severity=SEVERITY_WARNING,
                pattern="error_ignore",
                message=(
                    f"{latest.tool_name} が {error_streak} 回連続エラー後にリトライされました"
                ),
                tool_name=latest.tool_name,
            )

        return None

    def _detect_behavior_shift(self, latest: _ActionRecord) -> AnomalyAlert | None:
        """Pattern 4: Sudden shift from read-heavy to write-heavy operations."""
        history_list = list(self._history)
        if len(history_list) < self.behavior_window * 2:
            return None

        # Compare first half and second half windows
        half = len(history_list) // 2
        first_half = history_list[:half]
        second_half = history_list[half:]

        first_write_ratio = sum(1 for r in first_half if r.is_write) / len(first_half) if first_half else 0
        second_write_ratio = sum(1 for r in second_half if r.is_write) / len(second_half) if second_half else 0

        shift = second_write_ratio - first_write_ratio
        if shift >= self.read_write_ratio_shift and second_write_ratio > 0.5:
            return AnomalyAlert(
                severity=SEVERITY_SUSPICIOUS,
                pattern="behavior_shift",
                message=(
                    f"操作パターンが急変: 書き込み比率 "
                    f"{first_write_ratio:.0%} → {second_write_ratio:.0%} "
                    f"(+{shift:.0%})"
                ),
                tool_name=latest.tool_name,
            )

        return None

    def _handle_alert(self, alert: AnomalyAlert) -> None:
        """Execute actions based on alert severity."""
        if alert.severity == SEVERITY_CRITICAL:
            # Transition circuit breaker to open state
            try:
                from core.agent_safety.circuit_breaker import get_circuit_breaker
                cb = get_circuit_breaker()
                cb.trip(f"Anomaly detected: {alert.pattern}")
            except Exception:
                # `_elevated` is set either way below, so a failure here leaves
                # the code believing it escalated while the breaker is closed.
                logger.error(
                    "anomaly %s did not trip the circuit breaker", alert.pattern, exc_info=True
                )
            self._elevated = True

        if alert.severity in (SEVERITY_WARNING, SEVERITY_CRITICAL):
            self._elevated = True

        # Send SSE event
        try:
            from core.event_bus import emit
            emit("agent.anomaly_detected", {
                "severity": alert.severity,
                "pattern": alert.pattern,
                "message": alert.message,
                "tool_name": alert.tool_name,
            })
        except Exception:
            logger.warning("anomaly event was not emitted", exc_info=True)

        # Notify Audit Bureau (independent, one-way)
        try:
            from core.agent_safety.audit_bureau import get_audit_bureau
            get_audit_bureau().on_anomaly_detected(
                pattern=alert.pattern,
                severity=alert.severity,
                tool_name=alert.tool_name,
                message=alert.message,
            )
        except Exception:
            # An anomaly nobody recorded leaves no trace it was ever seen.
            logger.warning("audit bureau was not notified of the anomaly", exc_info=True)

    @staticmethod
    def _stable_hash(params: dict) -> str:
        """Generate a stable hash for parameter comparison."""
        try:
            raw = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            raw = str(params)
        # Dedup key for parameter comparison, not a security primitive.
        return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
