"""API error response helpers.

Purpose:
- Unify API error response format
- Maintain top-level `error` key for frontend backward compatibility
"""

from __future__ import annotations

from typing import Any

from quart import jsonify


def api_error(
    message: str,
    status: int = 400,
    *,
    code: str | None = None,
    detail: str | None = None,
    hint: str | None = None,
    extra: dict[str, Any] | None = None,
):
    """Return a consistent JSON error response.

    Response example:
      {
        "ok": false,
        "error": "...",
        "code": "...",
        "detail": "...",
        "hint": "..."
      }
    """
    payload: dict[str, Any] = {
        "ok": False,
        "error": message,  # backward-compatible key
    }
    if code:
        payload["code"] = code
    if detail:
        payload["detail"] = detail
    if hint:
        payload["hint"] = hint
    if extra:
        payload.update(extra)
    return jsonify(payload), status


def api_success(
    payload: dict[str, Any] | None = None,
    status: int = 200,
    *,
    data: Any = None,
):
    """Return a consistent JSON success response with legacy keys preserved."""
    body: dict[str, Any] = {
        "ok": True,
        "error": None,
        "data": data,
    }
    if payload:
        body.update(payload)
    return jsonify(body), status


def api_result(payload: Any, status: int = 200):
    """Normalize route payload into unified response shape.

    - success: includes `ok=true`, `error=null`, `data`
    - error: includes `ok=false`, `error=...`
    - keeps existing top-level keys for backward compatibility
    """
    if isinstance(payload, dict):
        if status >= 400 or payload.get("ok") is False:
            message = str(payload.get("error") or payload.get("message") or "Request failed")
            extra = dict(payload)
            extra.pop("error", None)
            # `message` is deliberately kept: a route that put one in its payload
            # meant it to reach the client. Dropping it left the search page
            # showing a bare "HTTP 404" (runner-core.ts reads errData.message,
            # never .error), and made Rust's {status, message} unmatchable.
            extra.pop("ok", None)
            return api_error(message, status, extra=extra)
        return api_success(payload, status, data=payload.get("data"))
    if status >= 400:
        return api_error(str(payload or "Request failed"), status)
    return api_success(status=status, data=payload)
