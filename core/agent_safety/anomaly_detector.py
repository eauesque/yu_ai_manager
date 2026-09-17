"""Anomaly Detector -- statistical anomaly pattern detection.

Separate from Circuit Breaker threshold checks, performs advanced
behavioral pattern analysis.

Detection patterns:
1. Repetition (consecutive identical tool+params)
2. Impact scope expansion (batch size spikes)
3. Error-ignore (retry after errors)
4. Behavior shift (read-heavy to write-heavy)

Confidence levels: suspicious / warning / critical

This module re-exports types and patterns from sub-modules
to maintain backward compatibility.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from core.agent_safety.anomaly_detector_patterns import (
    AnomalyPatternsMixin,
)

# Re-export types and constants for backward compatibility
from core.agent_safety.anomaly_detector_types import (  # noqa: F401
    SEVERITY_CRITICAL,
    SEVERITY_SUSPICIOUS,
    SEVERITY_WARNING,
    AnomalyAlert,
    _ActionRecord,
)

logger = logging.getLogger(__name__)


class AnomalyDetector(AnomalyPatternsMixin):
    """Statistical anomaly pattern detection."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: deque[_ActionRecord] = deque(maxlen=200)
        self._alerts: deque[AnomalyAlert] = deque(maxlen=100)
        self._elevated = False  # HITL escalation flag (set on warning or above)

        # Configurable parameters
        self.max_identical_consecutive = 5
        self.max_same_tool_per_window = 20
        self.window_sec = 60
        self.batch_size_spike_factor = 5.0
        self.max_retry_after_error = 3
        self.read_write_ratio_shift = 0.3
        self.behavior_window = 20

    def configure(self, config: dict) -> None:
        """Load thresholds from config.json."""
        ad_cfg = config.get("agent_safety", {}).get("anomaly_detection", {})
        if not ad_cfg:
            return
        for key in (
            "max_identical_consecutive", "max_same_tool_per_window",
            "window_sec", "max_retry_after_error", "behavior_window",
        ):
            if key in ad_cfg and isinstance(ad_cfg[key], (int, float)):
                setattr(self, key, ad_cfg[key])
        if "batch_size_spike_factor" in ad_cfg:
            self.batch_size_spike_factor = float(ad_cfg["batch_size_spike_factor"])
        if "read_write_ratio_shift" in ad_cfg:
            self.read_write_ratio_shift = float(ad_cfg["read_write_ratio_shift"])

    def record(
        self,
        tool_name: str,
        params: dict,
        is_error: bool = False,
        batch_size: int = 1,
    ) -> list[AnomalyAlert]:
        """Record an action and detect anomalies.

        Returns:
            List of detected alerts (empty list = normal)
        """
        from core.agent_safety.budget_tracker import classify_tool

        is_write = classify_tool(tool_name) != "read"
        params_hash = self._stable_hash(params)
        record = _ActionRecord(
            tool_name=tool_name,
            params_hash=params_hash,
            is_error=is_error,
            is_write=is_write,
            timestamp=time.time(),
            batch_size=batch_size,
        )

        with self._lock:
            self._history.append(record)
            alerts = self._detect(record)
            for alert in alerts:
                self._alerts.append(alert)

        # Actions based on severity
        for alert in alerts:
            self._handle_alert(alert)

        return alerts

    def is_elevated(self) -> bool:
        """Check if warning-level or above anomaly has been detected."""
        return self._elevated

    def clear_elevation(self) -> None:
        """Clear the HITL escalation flag."""
        self._elevated = False

    def get_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return alert history."""
        with self._lock:
            return [
                {
                    "severity": a.severity,
                    "pattern": a.pattern,
                    "message": a.message,
                    "tool_name": a.tool_name,
                    "timestamp": a.timestamp,
                }
                for a in list(self._alerts)[-limit:]
            ]

    def status(self) -> dict[str, Any]:
        """Return detection status."""
        with self._lock:
            severity_counts: dict[str, int] = {}
            for a in self._alerts:
                severity_counts[a.severity] = severity_counts.get(a.severity, 0) + 1
            return {
                "history_size": len(self._history),
                "total_alerts": len(self._alerts),
                "alerts_by_severity": severity_counts,
                "elevated": self._elevated,
                "recent_alerts": [
                    {
                        "severity": a.severity,
                        "pattern": a.pattern,
                        "message": a.message,
                        "tool_name": a.tool_name,
                    }
                    for a in list(self._alerts)[-5:]
                ],
            }

    def reset(self) -> None:
        """Clear history and alerts."""
        with self._lock:
            self._history.clear()
            self._alerts.clear()
            self._elevated = False


# Singleton
_detector: AnomalyDetector | None = None
_detector_lock = threading.Lock()


def get_anomaly_detector() -> AnomalyDetector:
    """Get the AnomalyDetector singleton."""
    global _detector
    if _detector is None:
        with _detector_lock:
            if _detector is None:
                detector = AnomalyDetector()
                try:
                    from core.configuration import get_config_value
                    cfg = {"agent_safety": get_config_value("agent_safety", {})}
                    detector.configure(cfg)
                except Exception:
                    # Defaults here are looser than an operator's own settings.
                    logger.warning(
                        "anomaly detector thresholds fell back to defaults", exc_info=True
                    )
                _detector = detector
    return _detector
