"""MCP Interceptor -- action recording, undo capture, and anomaly detection."""

from .interceptor_recording_anomaly import run_anomaly_detection
from .interceptor_recording_journal import (
    capture_undo_before,
    record_error,
    record_success,
    record_tool_action,
    summarize_result,
)

_record = record_tool_action
_run_anomaly_detection = run_anomaly_detection
_summarize_result = summarize_result

__all__ = [
    "_record",
    "capture_undo_before",
    "record_success",
    "record_error",
    "_run_anomaly_detection",
    "_summarize_result",
]
