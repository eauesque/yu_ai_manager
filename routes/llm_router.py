"""HTTP Blueprint for the LLM router — Anthropic + OpenAI compatible /v1/* endpoints."""

from __future__ import annotations

import hashlib as _hashlib
import json
import logging
import time as _time
import uuid as _uuid
from collections.abc import Callable
from datetime import UTC, datetime

from quart import Blueprint, Response, request

from core.gateway.audit import AuditRecord, get_writer
from core.gateway.auth import get_auth
from core.gateway.scopes import Scope
from core.llm_router import dispatch as dispatch_mod
from core.llm_router.driver import Driver
from core.llm_router.errors import (
    BackendDisabledError,
    BackendNotFoundError,
    BackendTimeoutError,
    BackendUnreachableError,
    LLMRouterError,
    NotImplementedFeatureError,
    TranslationError,
)
from core.llm_router.models import BackendInfo, StreamState
from core.llm_router.state import get_catalog
from core.llm_router.translate import (
    anthropic_request_to_openai,
    openai_chunk_to_anthropic_events,
    openai_response_to_anthropic,
)
from core.llm_router.type_guards import is_finite_number as _is_finite_number
from core.llm_router.type_guards import is_integer as _is_integer

logger = logging.getLogger("routes.llm_router")

bp = Blueprint("llm_router", __name__, url_prefix="/v1")

def configure_auth(cfg: dict) -> None:
    """Kept for backward compat — GatewayAuth is loaded from app startup hook."""


def _extract_bearer() -> str | None:
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        return h[len("Bearer "):]
    return request.headers.get("x-api-key") or None


def _check_auth() -> tuple | None:
    """Return an error response tuple if auth fails, else None."""
    auth = get_auth()
    result = auth.check_request(bearer=_extract_bearer(), remote_addr=request.remote_addr or "")
    if result is None:
        return _openai_error("invalid api key", "invalid_api_key", 401)
    request._gw_auth = result  # type: ignore[attr-defined]
    return None


@bp.before_request
async def _bp_auth():
    err = _check_auth()
    if err is not None:
        return err


def _default_driver_factory(backend: BackendInfo) -> Driver:
    return Driver(base_url=backend.base_url, api_key=backend.api_key, timeout=60.0)


# Module-level swappable factory for tests
_driver_factory: Callable[[BackendInfo], Driver] = _default_driver_factory


def _openai_error(message: str, code: str, http_status: int) -> tuple[Response, int]:
    return (
        Response(
            json.dumps(
                {"error": {"message": message, "type": "invalid_request_error", "code": code}},
                ensure_ascii=False,
            ),
            content_type="application/json",
        ),
        http_status,
    )


def _anthropic_error(message: str, type_: str, http_status: int) -> tuple[Response, int]:
    return (
        Response(
            json.dumps(
                {"type": "error", "error": {"type": type_, "message": message}},
                ensure_ascii=False,
            ),
            content_type="application/json",
        ),
        http_status,
    )


def _openai_stream_error(message: str) -> bytes:
    payload = {
        "error": {
            "message": message,
            "type": "api_error",
            "code": "server_error",
        }
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _anthropic_stream_error(message: str) -> bytes:
    payload = {"type": "error", "error": {"type": "api_error", "message": message}}
    return f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _anthropic_message_stop() -> bytes:
    return b'event: message_stop\ndata: {"type": "message_stop"}\n\n'


# The disabled error intentionally uses `type: "backend_disabled"` instead of
# the usual `type: "invalid_request_error"` convention, and carries an extra
# `reason` field. This lets OpenAI-compatible clients (Claude Code, Continue,
# etc.) distinguish an administratively-disabled backend from other 5xx errors
# without parsing the human-readable message. Keep the dedicated helper
# because the generic _openai_error cannot express the extra fields.
def _openai_disabled_error(alias: str) -> tuple[Response, int]:
    return (
        Response(
            json.dumps(
                {
                    "error": {
                        "message": f"backend '{alias}' is administratively disabled",
                        "type": "backend_disabled",
                        "code": "backend_disabled",
                        "reason": "administratively_disabled",
                    }
                },
                ensure_ascii=False,
            ),
            content_type="application/json",
        ),
        503,
    )


def _validate_openai_chat_request(body: dict) -> str | None:
    model = body.get("model")
    if model is not None and not isinstance(model, str):
        return "model must be a string"
    messages = body.get("messages")
    if messages is not None:
        if not isinstance(messages, list):
            return "messages must be an array"
        if not all(isinstance(msg, dict) for msg in messages):
            return "messages entries must be objects"
    for field in ("temperature", "top_p"):
        if field in body and not _is_finite_number(body[field]):
            return f"{field} must be a finite number"
    if "max_tokens" in body and not _is_integer(body["max_tokens"]):
        return "max_tokens must be an integer"
    return None


@bp.route("/chat/completions", methods=["POST"])
async def chat_completions():
    raw_body = await request.get_json(silent=True)
    body = raw_body if isinstance(raw_body, dict) else {}

    _gw = getattr(request, "_gw_auth", None)
    if _gw is not None and not get_auth().has_scope(_gw, Scope.LLM_CHAT):
        return _openai_error("insufficient scope", "insufficient_scope", 403)
    if raw_body is not None and not isinstance(raw_body, dict):
        return _openai_error("request body must be an object", "invalid_request", 400)
    if err := _validate_openai_chat_request(body):
        return _openai_error(err, "invalid_request", 400)
    target = body.get("model")
    if not target:
        return _openai_error("model is required", "invalid_request", 400)

    if _gw is not None and target and not get_auth().model_allowed(_gw, target):
        return _openai_error(f"model {target!r} not allowed", "model_not_found", 404)
    _t0 = _time.monotonic()

    try:
        if body.get("stream"):
            stream_iter = await dispatch_mod.dispatch(
                target=target,
                openai_request=body,
                stream=True,
                catalog=get_catalog(),
                driver_factory=_driver_factory,
            )

            async def gen():
                try:
                    async for chunk in stream_iter:
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode()
                    yield b"data: [DONE]\n\n"
                except LLMRouterError as exc:
                    logger.error("[llm_router] chat_completions stream aborted: %s", exc)
                    yield _openai_stream_error(str(exc))
                    yield b"data: [DONE]\n\n"
                except Exception as exc:
                    logger.exception("[llm_router] chat_completions stream failed: %s", exc)
                    yield _openai_stream_error("stream failed")
                    yield b"data: [DONE]\n\n"

            return Response(gen(), content_type="text/event-stream")

        result = await dispatch_mod.dispatch(
            target=target,
            openai_request=body,
            stream=False,
            catalog=get_catalog(),
            driver_factory=_driver_factory,
        )
        _gw2 = getattr(request, "_gw_auth", None)
        _writer = get_writer()
        if _writer and _gw2:
            _hash_fields = {k: body.get(k) for k in ("messages", "tools", "tool_choice") if k in body}
            _sha = _hashlib.sha256(
                json.dumps(_hash_fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            ).hexdigest()
            _writer.emit(AuditRecord(
                request_id=str(_uuid.uuid4()),
                timestamp=datetime.now(UTC),
                client_ip=request.remote_addr or "",
                auth_key_id=_gw2.key_id,
                endpoint=request.path,
                method=request.method,
                status_code=200,
                latency_ms=int((_time.monotonic() - _t0) * 1000),
                model=body.get("model"),
                backend_id="ollama",
                stream=body.get("stream", False),
                prompt_sha256=_sha,
            ))
        return Response(json.dumps(result, ensure_ascii=False), content_type="application/json")

    except BackendDisabledError as exc:
        logger.info("[llm_router] dispatch blocked: %s is disabled", exc.alias)
        return _openai_disabled_error(exc.alias)
    except BackendNotFoundError as exc:
        return _openai_error(str(exc), "model_not_found", 404)
    except NotImplementedFeatureError as exc:
        return _openai_error(str(exc), "not_implemented", 501)
    except BackendTimeoutError as exc:
        return _openai_error(str(exc), "server_error", 504)
    except BackendUnreachableError as exc:
        return _openai_error(str(exc), "server_error", 502)
    except (TranslationError, LLMRouterError) as exc:
        logger.warning("[llm_router] chat_completions failed: %s", exc)
        return _openai_error(str(exc), "server_error", 502)


@bp.route("/messages", methods=["POST"])
async def messages():
    raw_body = await request.get_json(silent=True)
    body = raw_body if isinstance(raw_body, dict) else {}

    _gw_msg = getattr(request, "_gw_auth", None)
    if _gw_msg is not None and not get_auth().has_scope(_gw_msg, Scope.LLM_MESSAGES):
        from core.gateway.errors import openai_error as _gw_err
        return _gw_err("insufficient scope", "insufficient_scope", 403)
    if raw_body is not None and not isinstance(raw_body, dict):
        return _anthropic_error("request body must be an object", "invalid_request_error", 400)
    target = body.get("model")
    if target is not None and not isinstance(target, str):
        return _anthropic_error("model must be a string", "invalid_request_error", 400)
    if not target:
        return _anthropic_error("model is required", "invalid_request_error", 400)

    if _gw_msg is not None and target and not get_auth().model_allowed(_gw_msg, target):
        from core.gateway.errors import openai_error as _gw_err
        return _gw_err(f"model {target!r} not allowed", "model_not_found", 404)
    _t0_msg = _time.monotonic()

    try:
        openai_body = anthropic_request_to_openai(body)
    except NotImplementedFeatureError as exc:
        return _anthropic_error(str(exc), "not_implemented", 501)
    except TranslationError as exc:
        return _anthropic_error(str(exc), "invalid_request_error", 400)

    try:
        if body.get("stream"):
            stream_iter = await dispatch_mod.dispatch(
                target=target,
                openai_request=openai_body,
                stream=True,
                catalog=get_catalog(),
                driver_factory=_driver_factory,
            )

            async def gen():
                state = StreamState()
                try:
                    async for chunk in stream_iter:
                        for event in openai_chunk_to_anthropic_events(chunk, state, requested_model=target):
                            yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
                except LLMRouterError as exc:
                    logger.error("[llm_router] messages stream aborted: %s", exc)
                    yield _anthropic_stream_error(str(exc))
                    yield _anthropic_message_stop()
                except Exception as exc:
                    logger.exception("[llm_router] messages stream failed: %s", exc)
                    yield _anthropic_stream_error("stream failed")
                    yield _anthropic_message_stop()

            return Response(gen(), content_type="text/event-stream")

        openai_resp = await dispatch_mod.dispatch(
            target=target,
            openai_request=openai_body,
            stream=False,
            catalog=get_catalog(),
            driver_factory=_driver_factory,
        )
        anthropic_resp = openai_response_to_anthropic(openai_resp, requested_model=target)
        _gw_msg2 = getattr(request, "_gw_auth", None)
        _writer_msg = get_writer()
        if _writer_msg and _gw_msg2:
            _hash_fields_msg = {k: body.get(k) for k in ("system", "messages", "tools", "tool_choice") if k in body}
            _sha_msg = _hashlib.sha256(
                json.dumps(_hash_fields_msg, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            ).hexdigest()
            _writer_msg.emit(AuditRecord(
                request_id=str(_uuid.uuid4()),
                timestamp=datetime.now(UTC),
                client_ip=request.remote_addr or "",
                auth_key_id=_gw_msg2.key_id,
                endpoint=request.path,
                method=request.method,
                status_code=200,
                latency_ms=int((_time.monotonic() - _t0_msg) * 1000),
                model=body.get("model"),
                backend_id="ollama",
                stream=body.get("stream", False),
                prompt_sha256=_sha_msg,
            ))
        return Response(json.dumps(anthropic_resp, ensure_ascii=False), content_type="application/json")

    except BackendDisabledError as exc:
        logger.info("[llm_router] dispatch blocked: %s is disabled", exc.alias)
        return _anthropic_error(
            f"backend '{exc.alias}' is administratively disabled",
            "backend_disabled",
            503,
        )
    except BackendNotFoundError as exc:
        return _anthropic_error(str(exc), "not_found_error", 404)
    except NotImplementedFeatureError as exc:
        return _anthropic_error(str(exc), "not_implemented", 501)
    except BackendTimeoutError as exc:
        return _anthropic_error(str(exc), "api_error", 504)
    except BackendUnreachableError as exc:
        return _anthropic_error(str(exc), "api_error", 502)
    except (TranslationError, LLMRouterError) as exc:
        logger.warning("[llm_router] messages failed: %s", exc)
        return _anthropic_error(str(exc), "api_error", 502)


# Register meta endpoints (splits file size; shares bp)
import routes.llm_router_meta  # noqa: F401, E402
