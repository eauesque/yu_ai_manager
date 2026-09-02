"""Anomaly detection hooks for interceptor recording."""

from .interceptor_recording_common import logger


def run_anomaly_detection(tool_name: str, params: dict, is_error: bool) -> None:
    try:
        from core.agent_safety.anomaly_detector import get_anomaly_detector
        batch_size = 1
        items = params.get("items") or params.get("file_ids")
        if isinstance(items, list):
            batch_size = len(items)
        get_anomaly_detector().record(tool_name, params, is_error=is_error, batch_size=batch_size)
    except Exception:
        # Anomaly detection that quietly stopped running looks exactly like
        # anomaly detection that found nothing.
        logger.warning("anomaly detection did not run for %s", tool_name, exc_info=True)
