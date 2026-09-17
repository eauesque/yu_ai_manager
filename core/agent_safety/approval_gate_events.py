import logging

logger = logging.getLogger(__name__)


def emit_approval_required(req) -> None:
    safe_params = {}
    for key, value in req.params.items():
        text = str(value)
        if len(text) > 200:
            text = text[:200] + "..."
        safe_params[key] = text
    try:
        from core.event_bus import emit

        emit(
            "agent.approval_required",
            {
                "request_id": req.request_id,
                "session_id": req.session_id,
                "tool_name": req.tool_name,
                "params": safe_params,
                "timeout": req.timeout,
            },
        )
    except Exception:
        # The approval prompt never reached the operator.
        logger.warning("approval request event was not emitted", exc_info=True)


def emit_notify(session_id: str, tool_name: str, params: dict) -> None:
    safe_params = {}
    for key, value in (params or {}).items():
        text = str(value)
        if len(text) > 200:
            text = text[:200] + "..."
        safe_params[key] = text
    try:
        from core.event_bus import emit

        emit(
            "agent.action",
            {
                "session_id": session_id,
                "tool": tool_name,
                "level": "notify",
                "params": safe_params,
            },
        )
    except Exception:
        logger.warning("approval notify event was not emitted", exc_info=True)
