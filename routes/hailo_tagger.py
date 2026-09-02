"""Hailo Remote Tagger API routes.

Delegates image tagging to a remote Hailo AI HAT inference server (e.g. Raspberry Pi 5).
The host sends the image as multipart/form-data, receives tag JSON, and writes results to DB.
"""

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync

bp = Blueprint("hailo_tagger", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def _parse_bool_field(data: dict, key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _parse_int_field(
    data: dict,
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = data.get(key, default)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return value


_HAILO_BLOCKED_HOSTNAMES = frozenset({"metadata.google.internal", "metadata.goog"})


def _validate_hailo_endpoint_url(url: str) -> str | None:
    """Validate the Hailo Remote Tagger endpoint URL.

    Unlike the shared ``validate_openai_compat_url`` (which gates loopback and
    private ranges together behind one ``allow_local`` flag), the Hailo
    Tagger inherently targets a LAN device (e.g. a Raspberry Pi on
    192.168.x.x): private ranges must be allowed, but loopback/link-local/
    metadata targets must still be blocked, since those would let this write
    endpoint be used to probe or hit the server's own local services (SSRF).
    Mirrors Rust's ``validate_hailo_endpoint_url`` in hailo_tagger.rs.
    """
    import socket
    from ipaddress import IPv6Address, ip_address
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL"
    if parsed.scheme not in ("http", "https"):
        return "Only http/https URLs are allowed"
    hostname = parsed.hostname or ""
    if not hostname:
        return "No hostname specified"
    if hostname.lower() in _HAILO_BLOCKED_HOSTNAMES:
        return "Blocked address"
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        # Unresolvable hostname: let the later connection attempt fail
        # instead of blocking here (matches the shared validator's behavior).
        return None
    for _family, _type, _proto, _canonname, sockaddr in infos:
        try:
            ip = ip_address(sockaddr[0].split("%", 1)[0])
        except ValueError:
            continue
        # Normalize IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) to plain IPv4
        # first — otherwise the loopback/link-local checks below can be
        # bypassed entirely.
        if isinstance(ip, IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if ip.is_unspecified or ip.is_loopback or ip.is_link_local:
            return "Blocked address"
        # Private LAN ranges (e.g. 192.168.x.x, 10.x.x.x) are intentionally
        # allowed — that's the documented, intended use case.
    return None


# -- Config ---------------------------------------------------------------

@bp.route("/api/hailo-tagger/config", methods=["GET"])
async def api_ht_config_get():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    def _get():
        from core.configuration.json_rw import load_config_json
        cfg = load_config_json(None)
        ht = cfg.get("hailo_tagger", {})
        return {
            "enabled": ht.get("enabled", False),
            "endpoint_url": ht.get("endpoint_url", ""),
            "threshold": ht.get("threshold", 0.35),
            "timeout": ht.get("timeout", 30),
        }
    return api_result({"config": await run_db_sync(_get)})


@bp.route("/api/hailo-tagger/config", methods=["POST"])
async def api_ht_config_save():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("JSON object required", 400, code="invalid_json")

    def _save(d):
        from core.configuration.json_rw import load_config_json, save_config_json

        for key in ("enabled",):
            if key in d and not isinstance(d[key], bool):
                raise ValueError(f"{key} must be a boolean")
        if "endpoint_url" in d:
            endpoint_url = str(d["endpoint_url"]).strip()
            err = _validate_hailo_endpoint_url(endpoint_url)
            if err:
                raise ValueError(f"endpoint_url: {err}")
        if "threshold" in d:
            val = d["threshold"]
            if not isinstance(val, (int, float)) or not 0.0 <= float(val) <= 1.0:
                raise ValueError("threshold must be a number between 0.0 and 1.0")
        if "timeout" in d:
            val = d["timeout"]
            if not isinstance(val, int) or not 1 <= val <= 300:
                raise ValueError("timeout must be an integer between 1 and 300")

        cfg = load_config_json(None)
        ht = cfg.setdefault("hailo_tagger", {})
        if "enabled" in d:
            ht["enabled"] = d["enabled"]
        if "endpoint_url" in d:
            ht["endpoint_url"] = str(d["endpoint_url"]).strip()
        if "threshold" in d:
            ht["threshold"] = round(float(d["threshold"]), 2)
        if "timeout" in d:
            ht["timeout"] = int(d["timeout"])
        save_config_json(cfg)
        return ht

    try:
        saved = await run_db_sync(_save, data)
    except ValueError as exc:
        return api_error(str(exc), 400, code="invalid_value")
    return api_result({"config": saved})


# -- Status / connection test ---------------------------------------------

@bp.route("/api/hailo-tagger/status", methods=["GET"])
async def api_ht_status():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    def _status():
        from core.configuration.json_rw import load_config_json
        cfg = load_config_json(None)
        ht = cfg.get("hailo_tagger", {})
        enabled = ht.get("enabled", False)
        url = ht.get("endpoint_url", "").strip()
        if not enabled or not url:
            return {"enabled": enabled, "reachable": False, "reason": "not_configured"}
        import urllib.request
        from urllib.parse import urlparse

        from core.hailo_tagger_core.http_client import (
            HAILO_NO_REDIRECT_OPENER,
            pinned_dns,
            resolve_hailo_host,
        )
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            infos = resolve_hailo_host(hostname, port)
            req = urllib.request.Request(
                url.rstrip("/") + "/health",
                method="GET",
                headers={"User-Agent": "YU-AI-Manager/1.0"},
            )
            with pinned_dns(hostname, infos), HAILO_NO_REDIRECT_OPENER.open(req, timeout=5):
                pass
            return {"enabled": True, "reachable": True, "endpoint_url": url}
        except Exception as exc:
            return {"enabled": True, "reachable": False, "reason": str(exc), "endpoint_url": url}

    return api_result(await run_db_sync(_status))


# -- Single file tagging --------------------------------------------------

@bp.route("/api/hailo-tagger/tag/<int:file_id>", methods=["POST"])
async def api_ht_tag_one(file_id):
    data = await request.get_json(silent=True) or {}
    try:
        force = _parse_bool_field(data, "force", False)
    except ValueError as exc:
        return api_error(str(exc), 400, code="invalid_value")

    def _tag(fid, force_flag):
        from core.hailo_tagger_core.single_ops import tag_one_file
        return tag_one_file(fid, force=force_flag)

    result = await run_db_sync(_tag, file_id, force)
    if "error" in result:
        return api_error(
            result["error"],
            result.get("status_code", 400),
            code=result.get("code", "tag_error"),
        )
    return api_result(result)


# -- Batch -----------------------------------------------------------------

@bp.route("/api/hailo-tagger/batch", methods=["POST"])
async def api_ht_batch():
    data = await request.get_json(silent=True) or {}
    file_ids = data.get("file_ids")
    try:
        limit = _parse_int_field(data, "limit", default=100, minimum=1, maximum=500)
        force = _parse_bool_field(data, "force", False)
    except ValueError as exc:
        return api_error(str(exc), 400, code="invalid_value")

    if file_ids is not None and not isinstance(file_ids, list):
        return api_error("file_ids must be a list", 400, code="invalid_input")
    if isinstance(file_ids, list) and len(file_ids) > 500:
        return api_error("file_ids max 500", 400, code="batch_too_large")

    def _batch(fids, lim, force_flag):
        from core.hailo_tagger_core.batch_ops import run_batch_tagging
        return run_batch_tagging(file_ids=fids, limit=lim, force=force_flag)

    result = await run_db_sync(_batch, file_ids, limit, force)
    if "error" in result:
        return api_error(result["error"], 409, code=result.get("code", "batch_error"))
    return api_result(result)


# -- Tag CRUD -------------------------------------------------------------

@bp.route("/api/hailo-tagger/tags/<int:file_id>", methods=["GET"])
async def api_ht_tags_get(file_id):
    def _get(fid):
        from core.hailo_tagger_core.store import get_hailo_tags
        return get_hailo_tags(fid)

    tags = await run_db_sync(_get, file_id)
    return api_result({"file_id": file_id, "tags": tags})


@bp.route("/api/hailo-tagger/tags/<int:file_id>", methods=["DELETE"])
async def api_ht_tags_delete(file_id):
    def _del(fid):
        from core.hailo_tagger_core.store import delete_hailo_tags
        return delete_hailo_tags(fid)

    count = await run_db_sync(_del, file_id)
    return api_result({"file_id": file_id, "deleted": count})
