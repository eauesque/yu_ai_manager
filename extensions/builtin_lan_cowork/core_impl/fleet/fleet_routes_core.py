"""Core info/UI/log-stream fleet route registrations."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import threading
import time
from urllib.parse import urlsplit

import httpx
from quart import jsonify, request

from core.web.api_rate_limit import get_client_ip
from core.web.auth_route_policy import auth_route

from ..peer_auth import authenticate_peer_request
from .fleet_route_deps import FleetCoreRouteDeps
from .fleet_route_guards import build_local_chief_getter, build_manager_getter, ensure_chief

logger = logging.getLogger(__name__)
_AUTH_PREFIX = "/ext/lan_cowork"

# Per-IP connection limiter for the local (non-relay) branch of
# /ext/lan_cowork/fleet/logs/stream. Mirrors routes/logs_api.py's
# `/api/logs/stream` limiter (same limit, same list-of-start-times +
# lock design) rather than the Rust core counter pattern, since this is
# the established idiom on the Python side for this exact class of
# resource (a long-lived SSE stream fed by the in-memory log ring).
# The relay branch (`relay_peer_logs`) has no local resource cost and is
# intentionally not limited here.
_MAX_FLEET_LOG_SSE_PER_IP = 3
_fleet_log_sse_starts: dict[str, list[float]] = {}
_fleet_log_sse_lock = threading.Lock()


async def relay_peer_logs(mgr, peer, *, lines: int, level, build_peer_relay_url):
    """Relay SSE from a peer node to the current client."""
    from .fleet_peer_http import build_peer_headers
    from .log_streamer import format_sse_line

    url = build_peer_relay_url(peer, lines=lines, level=level)
    parsed = urlsplit(url)
    headers = build_peer_headers(
        mgr,
        peer,
        requested_with="FleetRelay",
        method="GET",
        full_path=parsed.path,
        query_string=parsed.query,
        include_accept_sse=True,
    )

    async def generate():
        try:
            # An SSE relay must not have a read timeout -- the stream is
            # long-lived by design and a read deadline would cut it. Connect,
            # write and pool stay bounded: `timeout=None` disabled those too,
            # so an unreachable peer held the relay open indefinitely.
            timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:  # noqa: SIM117
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code != 200:
                        yield format_sse_line("error", {"error": f"peer returned {resp.status_code}"})
                        return
                    async for chunk in resp.aiter_text():
                        yield chunk
        except Exception:
            logger.debug("SSE relay disconnected")
        finally:
            yield "event: close\ndata: {}\n\n"

    return generate(), 200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }


def register_fleet_core_routes(
    bp,
    get_manager,
    deps: FleetCoreRouteDeps,
):
    auth_decorator = deps.auth_decorator
    session_ok = deps.session_ok
    fleet_cfg = deps.fleet_cfg
    repo_root = deps.repo_root
    check_log_stream_allowed = deps.check_log_stream_allowed
    build_peer_relay_url = deps.build_peer_relay_url

    require_manager = build_manager_getter(get_manager, message="LAN Cowork not enabled")
    require_local_chief = build_local_chief_getter(require_manager, session_ok, message="chief only")
    require_relay_chief = build_local_chief_getter(require_manager, session_ok, status_code=404)

    async def authorize_info_request(mgr):
        requester_peer_id = request.headers.get("X-Peer-Id", "").strip()
        if not requester_peer_id:
            return None, ({"error": "peer_id required"}, 401)

        peer = mgr.registry.get(requester_peer_id)
        if peer is None:
            return None, ({"error": "peer not registered"}, 401)
        return requester_peer_id, None

    def parse_log_stream_params():
        lines = min(int(request.args.get("lines", 200)), 1000)
        level = request.args.get("level") or None
        if level and level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            level = None
        return lines, level

    def authorize_local_log_stream(mgr, requester_peer_id: str):
        if not requester_peer_id:
            if not session_ok():
                return {"error": "session required"}, 401
            return None

        cfg = fleet_cfg(mgr)
        allowed, reason = check_log_stream_allowed(requester_peer_id, cfg)
        if not allowed:
            if reason == "remote_update_disabled":
                return {
                    "error": "remote_update_disabled",
                    "message": "remote fleet operations are disabled on this node",
                }, 403
            return {"error": "not_in_allowlist", "message": "not in allow_log_stream_from"}, 403
        return None

    def authorize_relay_log_stream():
        _mgr, failure = require_relay_chief()
        if not failure:
            return None
        if failure[1] == 403:
            return {"error": "not_chief"}, 404
        return failure

    @auth_route(bp, "/fleet/info", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @auth_decorator
    async def fleet_info():
        mgr, failure = require_manager()
        if failure:
            return jsonify(failure[0]), failure[1]

        _requester_peer_id, failure = await authorize_info_request(mgr)
        if failure:
            return jsonify(failure[0]), failure[1]

        cfg = fleet_cfg(mgr)
        roles: list = cfg.get("_roles_runtime", [])
        try:
            from .machine_info import collect

            data = await asyncio.to_thread(
                collect,
                version=mgr.local_peer.version,
                roles=roles,
                repo_path=repo_root,
                gpu_name=mgr.local_peer.gpu or "",
            )
            return jsonify(data)
        except ImportError:
            return jsonify({"error": "psutil_not_installed", "message": "psutil is required for fleet info"}), 500
        except Exception as exc:
            logger.exception("fleet_info collect failed")
            return jsonify({"error": "collection_failed", "message": str(exc)}), 500

    @bp.route("/fleet/peers", methods=["GET"])
    async def fleet_peers():
        mgr, failure = require_local_chief()
        if failure:
            return jsonify(failure[0]), failure[1]

        fm = getattr(mgr, "_fleet_manager", None)
        if fm is None:
            return jsonify({"error": "fleet_manager_not_running", "message": "FleetManager not initialized"}), 503

        force = request.args.get("force_refresh", "").lower() == "true"
        if force:
            await fm.refresh(force=True)
        return jsonify(fm.get_peers_snapshot())

    @bp.route("/fleet/ui")
    async def fleet_ui():
        mgr, failure = require_manager()
        if failure:
            return "", 404
        failure = ensure_chief(mgr, status_code=404)
        if failure:
            return "", 404

        html_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "ui", "fleet", "fleet.html")
        )
        if not os.path.exists(html_path):
            return "Fleet UI not found", 404

        from quart import current_app, g

        nonce = getattr(g, "csp_nonce", "") or ""
        def _read_html(path: str) -> str:
            with open(path, encoding="utf-8") as f:
                return f.read()

        html = await asyncio.to_thread(_read_html, html_path)
        html = html.replace("{{ csp_nonce }}", nonce)
        try:
            nav_tpl = current_app.jinja_env.get_template("_nav.html")
            nav_html = await nav_tpl.render_async(csp_nonce=nonce, active="fleet")
        except Exception:
            nav_html = ""
        html = html.replace("<!-- NAV_PLACEHOLDER -->", nav_html)
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    @auth_route(bp, "/fleet/logs/stream", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer_or_session")
    async def fleet_logs_stream():
        mgr, failure = require_manager()
        if failure:
            return jsonify({"error": "service_unavailable"}), 503

        peer_id = request.args.get("peer_id", "").strip()
        requester_peer_id = request.headers.get("X-Peer-Id", "").strip()

        if peer_id and peer_id != mgr.local_peer.peer_id:
            failure = authorize_relay_log_stream()
            if failure:
                return jsonify(failure[0]), failure[1]

            peer = mgr.registry.get(peer_id)
            if peer is None:
                return jsonify({"error": "peer_not_found"}), 404

            lines, level = parse_log_stream_params()
            return await relay_peer_logs(
                mgr,
                peer,
                lines=lines,
                level=level,
                build_peer_relay_url=build_peer_relay_url,
            )

        if requester_peer_id:
            failure = await authenticate_peer_request(mgr)
            if failure is not None:
                return failure

        failure = authorize_local_log_stream(mgr, requester_peer_id)
        if failure:
            return jsonify(failure[0]), failure[1]

        lines, level = parse_log_stream_params()

        ip = get_client_ip() or "unknown"
        now = time.monotonic()
        with _fleet_log_sse_lock:
            if len(_fleet_log_sse_starts.get(ip, [])) >= _MAX_FLEET_LOG_SSE_PER_IP:
                return jsonify({"error": "too_many_log_sse_connections"}), 429
            _fleet_log_sse_starts.setdefault(ip, []).append(now)

        from core.infra_core.log_ring_buffer import log_ring

        from .log_streamer import format_sse_line, iter_sse_events

        async def generate():
            try:
                async for entry in iter_sse_events(log_ring, lines=lines, level=level):
                    yield format_sse_line("log", entry)
            except asyncio.CancelledError:
                pass
            finally:
                with _fleet_log_sse_lock:
                    starts = _fleet_log_sse_starts.get(ip)
                    if starts:
                        with contextlib.suppress(ValueError):
                            starts.remove(now)
                        if not starts:
                            _fleet_log_sse_starts.pop(ip, None)
                yield "event: close\ndata: {}\n\n"

        return generate(), 200, {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
