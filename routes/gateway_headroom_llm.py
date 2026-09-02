"""Gateway LLM proxy for headroom (/headroom/*).

Two-layer auth — each host carries its own upstream credential:
  ANTHROPIC_BASE_URL=http://<host>:<port>/headroom
  Proxy-Authorization: Bearer <gateway headroom:read key>  (gateway auth — consumed here, stripped)
  Authorization:       Bearer <client OAuth / api key>      (passed through to headroom → Anthropic)

The gateway never holds the upstream credential; x-api-key also passes through.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

import httpx
from quart import Blueprint, Response, request

from core.gateway.auth import extract_bearer, get_auth
from core.gateway.errors import openai_error
from core.gateway.headroom_proxy import get_upstream_auth_key, get_upstream_base_url
from core.gateway.scopes import Scope
from core.web.proxy_prefixes import proxy_origin_allowed

logger = logging.getLogger(__name__)
bp = Blueprint("gateway_headroom_llm", __name__, url_prefix="/headroom")

# Strip the gateway's Proxy-Authorization (consumed here). Authorization (the
# client's own upstream credential) and x-api-key are intentionally kept.
_REQ_STRIP = frozenset({
    "host",
    "connection", "keep-alive", "te", "trailers",
    "transfer-encoding", "upgrade",
    "proxy-authenticate", "proxy-authorization",
})
_RESP_STRIP = frozenset({
    "connection", "keep-alive", "te", "trailers",
    "transfer-encoding", "upgrade",
    # httpx auto-decompresses gzip/br; forwarding these headers would mismatch the body
    "content-encoding",
    "content-length",  # unknown / changes after decompression; let Quart rechunk
})
_MAX_BODY = 10 * 1024 * 1024  # 10 MiB
_KEEPALIVE_INTERVAL = 25.0    # seconds; used for both pre-connect and mid-stream keepalive


def _auth() -> tuple[Response, int] | None:
    """Proxy-Authorization carries the gateway key (consumed here, required).

    /headroom/* is an API-only path with no browser session flow, so a valid
    gateway key in Proxy-Authorization is mandatory. Authorization is the
    client's own upstream credential, passed through untouched — it must NEVER
    be used for gateway auth.
    """
    bearer = extract_bearer(request.headers.get("Proxy-Authorization"), None)
    if bearer is None:
        return openai_error("Unauthorized", "invalid_api_key", 401, "authentication_error")
    auth = get_auth()
    result = auth.check_request(
        bearer=bearer,
        remote_addr=request.remote_addr or "",
        allow_loopback_bypass=False,
    )
    if result is None:
        return openai_error("Unauthorized", "invalid_api_key", 401, "authentication_error")
    if not auth.has_scope(result, Scope.HEADROOM_READ):
        return openai_error("Insufficient scope", "insufficient_scope", 403, param=str(Scope.HEADROOM_READ))
    return None


def _is_sse_request(body: bytes) -> bool:
    """Return True if the JSON body requests a streaming Anthropic Completions response."""
    try:
        data = json.loads(body)
        return bool(data.get("stream")) if isinstance(data, dict) else False
    except (json.JSONDecodeError, ValueError):
        return False


async def _sse_generate(
    method: str,
    upstream_url: str,
    fwd_headers: dict[str, str],
    raw_body: bytes,
    params: object,
):
    """SSE generator that emits keepalive pings during headroom's pre-upstream phase.

    headroom runs compression + memory injection synchronously before connecting to
    Anthropic (up to ~75 s with large contexts). During this phase the gateway
    receives nothing from headroom, so NAT/TCP idle timeouts cut the client
    connection before the first real byte arrives.

    By pre-committing to 200 + text/event-stream and doing the upstream connect
    inside this generator, we can emit ': keepalive' SSE comment lines every
    _KEEPALIVE_INTERVAL seconds to keep the link alive. Errors from headroom are
    relayed as SSE error events so the client still gets a structured response.
    """
    t0 = time.monotonic()
    # No read/write timeout: long thinking phases can stay silent for minutes;
    # only the TCP connect to headroom is bounded.
    client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5.0))

    # Phase 1: connect to headroom, yielding keepalive every _KEEPALIVE_INTERVAL s
    connect_event = asyncio.Event()
    connect_result: list = []

    async def _do_connect() -> None:
        try:
            req_obj = client.build_request(
                method, upstream_url,
                headers=fwd_headers, content=raw_body or None, params=params,
            )
            result = await client.send(req_obj, stream=True, follow_redirects=False)
            connect_result.append(("ok", result))
        except Exception as exc:
            connect_result.append(("err", exc))
        finally:
            connect_event.set()

    connect_task = asyncio.create_task(_do_connect())
    while not connect_event.is_set():
        try:
            await asyncio.wait_for(connect_event.wait(), timeout=_KEEPALIVE_INTERVAL)
        except TimeoutError:
            yield b": keepalive\n\n"
        except asyncio.CancelledError:
            connect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await connect_task
            await client.aclose()
            raise

    kind, payload = connect_result[0]
    if kind == "err":
        exc = payload
        await client.aclose()
        if isinstance(exc, httpx.ConnectError):
            msg, etype = "headroom not reachable", "connection_error"
        elif isinstance(exc, httpx.TimeoutException):
            msg, etype = "headroom timed out", "timeout"
        else:
            msg, etype = str(exc), "proxy_error"
        logger.error("[gateway:headroom_llm] sse-early connect: %s", exc)
        safe = msg.replace("\\", "\\\\").replace('"', '\\"')[:200]
        yield f'data: {{"error":{{"message":"{safe}","type":"{etype}"}}}}\n\ndata: [DONE]\n\n'.encode()
        return

    upstream = payload
    is_sse = "text/event-stream" in upstream.headers.get("content-type", "")
    if not is_sse:
        # headroom returned non-SSE (error JSON, wrong content-type) — relay as SSE error
        try:
            body_bytes = await upstream.aread()
            relay = body_bytes.decode(errors="replace")[:500].replace("\\", "\\\\").replace('"', '\\"')
        except Exception:
            relay = f"upstream status {upstream.status_code}"
        await upstream.aclose()
        await client.aclose()
        yield (
            f'data: {{"error":{{"message":"{relay}",'
            f'"type":"upstream_error","status":{upstream.status_code}}}}}\n\n'
            f"data: [DONE]\n\n"
        ).encode()
        return

    # Phase 2: stream SSE chunks with mid-stream keepalive (pitfall 4)
    status = "incomplete"
    done_seen = False
    n = 0
    tail = b""
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def _pump() -> None:
        try:
            async for chunk in upstream.aiter_bytes():
                await queue.put(chunk)
        except Exception as exc:
            logger.debug("[gateway:headroom_llm] pump: %s", exc)
        finally:
            await queue.put(None)

    pump_task = asyncio.create_task(_pump())
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_INTERVAL)
            except TimeoutError:
                yield b": keepalive\n\n"
                continue
            if chunk is None:
                break
            n += 1
            yield chunk
            tail = (tail + chunk)[-48:]
            if b"data: [DONE]\n" in tail:
                done_seen = True
                break
        status = "complete"
    except asyncio.CancelledError:
        status = "client-cancelled"
        raise
    except Exception as exc:
        status = f"error:{type(exc).__name__}:{exc}"
    finally:
        pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await pump_task
        elapsed = time.monotonic() - t0
        logger.info(
            "[gateway:headroom_llm] stream end status=%s chunks=%d done_seen=%s elapsed=%.1fs",
            status, n, done_seen, elapsed,
        )
        await upstream.aclose()
        await client.aclose()


@bp.route("/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE"], strict_slashes=False)
async def proxy_headroom(subpath: str) -> Response:
    err = _auth()
    if err:
        return err
    if not proxy_origin_allowed(request):
        return openai_error("Forbidden", "forbidden", 403)

    fwd_headers = {k: v for k, v in request.headers.items() if k.lower() not in _REQ_STRIP}
    fwd_headers["X-Forwarded-For"] = request.remote_addr or ""
    # Force no compression: httpx auto-decompresses, so gzip from headroom would
    # leave Content-Encoding/Content-Length headers that no longer match the body.
    fwd_headers["Accept-Encoding"] = "identity"
    # The client's Authorization (its own OAuth / api key) passes through untouched.
    # Only fall back to a server-configured upstream key when the client sent none.
    if not any(k.lower() == "authorization" for k in fwd_headers):
        upstream_key = get_upstream_auth_key()
        if upstream_key:
            fwd_headers["Authorization"] = f"Bearer {upstream_key}"

    raw_body = await request.get_data()
    if len(raw_body) > _MAX_BODY:
        return openai_error("Body too large", "body_too_large", 413)

    upstream_url = get_upstream_base_url() + f"/{subpath}"

    # SSE streaming request: pre-commit 200+text/event-stream so early keepalive can
    # flow during headroom's pre-upstream phase (compression + memory injection, up to
    # ~75 s). Without this, NAT/TCP idle timeouts cut the client connection before the
    # first real SSE byte arrives. Errors from headroom are relayed as SSE error events.
    if _is_sse_request(raw_body):
        sse_headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
        resp = Response(
            _sse_generate(request.method, upstream_url, fwd_headers, raw_body, request.args),
            status=200,
            headers=sse_headers,
        )
        # Long thinking phases easily exceed Quart's RESPONSE_TIMEOUT (default 60 s);
        # streaming responses must never be cut by it.
        resp.timeout = None
        return resp

    # Non-SSE (model listing, non-stream completions): existing connect-then-stream flow.
    # No read/write timeout — non-stream completions with long thinking exceed any
    # fixed budget; only the TCP connect is bounded.
    client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5.0))
    try:
        req_obj = client.build_request(
            request.method,
            upstream_url,
            headers=fwd_headers,
            content=raw_body or None,
            params=request.args,
        )
        upstream = await client.send(req_obj, stream=True, follow_redirects=False)
    except httpx.ConnectError:
        await client.aclose()
        return openai_error("headroom not reachable", "connection_error", 502)
    except httpx.TimeoutException:
        await client.aclose()
        return openai_error("headroom timed out", "timeout", 504)
    except Exception as exc:
        logger.error("[gateway:headroom_llm] connect: %s", exc)
        await client.aclose()
        return openai_error(str(exc), "proxy_error", 502)

    resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in _RESP_STRIP}
    is_sse = "text/event-stream" in upstream.headers.get("content-type", "")

    async def generate():
        status = "incomplete"
        done_seen = False
        n = 0
        t0 = time.monotonic()
        tail = b""
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def _pump() -> None:
            try:
                async for chunk in upstream.aiter_bytes():
                    await queue.put(chunk)
            except Exception as exc:
                logger.debug("[gateway:headroom_llm] pump: %s", exc)
            finally:
                await queue.put(None)

        pump_task = asyncio.create_task(_pump())
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_INTERVAL)
                except TimeoutError:
                    if is_sse:
                        yield b": keepalive\n\n"
                    continue
                if chunk is None:
                    break
                n += 1
                yield chunk
                if is_sse:
                    tail = (tail + chunk)[-48:]
                    if b"data: [DONE]\n" in tail:
                        # SSE stream done. headroom keeps its HTTP response open
                        # during _finalize_stream_response(); closing here prevents
                        # undici's ~60s body-timeout from firing on the client side.
                        done_seen = True
                        break
            status = "complete"
        except asyncio.CancelledError:
            # Client disconnected — Quart/hypercorn cancelled this generator.
            status = "client-cancelled"
            raise
        except Exception as exc:
            status = f"error:{type(exc).__name__}:{exc}"
        finally:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pump_task
            elapsed = time.monotonic() - t0
            logger.info(
                "[gateway:headroom_llm] stream end status=%s chunks=%d done_seen=%s elapsed=%.1fs",
                status, n, done_seen, elapsed,
            )
            await upstream.aclose()
            await client.aclose()

    resp = Response(generate(), status=upstream.status_code, headers=resp_headers)
    # Disable Quart's RESPONSE_TIMEOUT here too — non-stream completions with long
    # thinking can take well over 60 s before headroom returns the full body.
    resp.timeout = None
    return resp
