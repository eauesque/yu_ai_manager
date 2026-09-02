"""Anomaly Detector shared types and constants.

Shared between anomaly_detector.py and anomaly_detector_patterns.py
to avoid circular imports.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Severity levels
SEVERITY_SUSPICIOUS = "suspicious"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"


@dataclass
class AnomalyAlert:
    """Anomaly detection alert."""
    severity: str  # suspicious / warning / critical
    pattern: str   # Detection pattern name
    message: str   # Description
    tool_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class _ActionRecord:
    """Internal action record for detection."""
    tool_name: str
    params_hash: str
    is_error: bool
    is_write: bool
    timestamp: float
    batch_size: int = 1
