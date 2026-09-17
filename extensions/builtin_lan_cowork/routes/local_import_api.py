"""Local-side import control endpoints (session management + execute trigger)."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from quart import Blueprint, jsonify, request

from core.infra_core.api_request import require_json_model
from core.web.auth_route_policy import auth_route
from extensions.builtin_lan_cowork.routes.request_models import (
    LocalImportExecuteRequest,
    LocalImportIndexRequest,
    LocalImportSessionCreateRequest,
)

logger = logging.getLogger(__name__)
_AUTH_PREFIX = "/ext/lan_cowork"


def _path_is_or_under(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _project_root() -> Path:
    return Path(__file__).resolve(strict=False).parents[3]


def _sensitive_import_bases() -> list[Path]:
    bases = [
        _project_root(),
        Path.home() / "AppData",
    ]
    if Path("/").exists():
        bases.extend(
            Path(p)
            for p in (
                "/etc",
                "/bin",
                "/sbin",
                "/boot",
                "/dev",
                "/proc",
                "/run",
                "/sys",
                "/lib",
                "/lib64",
                "/usr/bin",
                "/usr/sbin",
                "/usr/lib",
                "/usr/lib64",
                "/usr/local/bin",
                "/usr/local/lib",
                "/usr/share/applications",
                "/usr/local/share/applications",
            )
        )
    if sys.platform == "win32":
        for env_name in ("APPDATA", "LOCALAPPDATA"):
            if env_value := os.environ.get(env_name):
                bases.append(Path(env_value))
        bases.extend(
            Path(p)
            for p in (
                r"C:\Windows",
                r"C:\Program Files",
                r"C:\Program Files (x86)",
            )
        )
    resolved_bases = [base.resolve(strict=False) for base in bases]
    return [base for base in resolved_bases if base != Path(base.anchor)]


def _under_home_dot_dir(path: Path) -> bool:
    try:
        rel = path.relative_to(Path.home().resolve(strict=False))
    except ValueError:
        return False
    return bool(rel.parts and rel.parts[0].startswith("."))


def _validate_import_folder(import_folder: str) -> tuple[Path | None, str | None]:
    """Resolve and reject sensitive write targets while keeping normal media folders valid."""
    if "\x00" in import_folder:
        return None, "import_folder is not allowed"
    try:
        resolved = Path(import_folder).resolve(strict=False)
    except OSError as exc:
        return None, f"invalid import_folder: {exc}"

    if resolved == Path(resolved.anchor):
        return None, "import_folder is not allowed"
    if _under_home_dot_dir(resolved):
        return None, "import_folder is not allowed"
    if any(_path_is_or_under(resolved, base) for base in _sensitive_import_bases()):
        return None, "import_folder is not allowed"
    return resolved, None


def register_routes(bp: Blueprint, get_manager, *, session_guard) -> None:

    async def _call_import_session(method_name: str, *args, **kwargs):
        from ..core_impl.import_session import ImportSession

        method = getattr(ImportSession, method_name)
        if ImportSession.threadsafe_provider():
            return await asyncio.to_thread(method, *args, **kwargs)
        return method(*args, **kwargs)

    @auth_route(bp, "/api/peer/import/sessions", methods=["GET"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def list_import_sessions():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        sessions = await _call_import_session("list_all")
        return jsonify({"ok": True, "sessions": sessions})

    @auth_route(bp, "/api/peer/import/session/<session_id>", methods=["GET"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def get_import_session(session_id: str):
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        s = await _call_import_session("get", session_id)
        if s is None:
            return jsonify({"ok": False, "error": "session not found"}), 404
        return jsonify({"ok": True, "session": s})

    @auth_route(bp, "/api/peer/import/session", methods=["POST"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def create_import_session():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        data, err = await require_json_model(request, LocalImportSessionCreateRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        peer_id = data.peer_id
        peer_name = data.peer_name
        mode = data.mode
        import_folder = data.import_folder
        options = data.options

        folder, folder_err = _validate_import_folder(import_folder)
        if folder_err:
            return jsonify({"ok": False, "error": folder_err}), 400
        assert folder is not None
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return jsonify({"ok": False, "error": f"cannot create import_folder: {e}"}), 400

        sid = await _call_import_session(
            "create",
            peer_id=peer_id, peer_name=peer_name,
            mode=mode, import_folder=str(folder), options=options,
        )
        return jsonify({"ok": True, "session_id": sid})

    @auth_route(bp, "/api/peer/import/execute", methods=["POST"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def execute_import():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        data, err = await require_json_model(request, LocalImportExecuteRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        session_id = data.session_id
        file_ids = data.file_ids  # None = all

        from ..core_impl.import_session import ImportSession
        s = await _call_import_session("get", session_id)
        if s is None:
            return jsonify({"ok": False, "error": "session not found"}), 404

        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503

        peer = mgr.registry.get(s["peer_id"])
        if peer is None:
            return jsonify({"ok": False, "error": "peer not in registry"}), 404

        import_folder, folder_err = _validate_import_folder(str(s["import_folder"]))
        if folder_err:
            return jsonify({"ok": False, "error": folder_err}), 400
        assert import_folder is not None
        try:
            import_folder.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return jsonify({"ok": False, "error": f"cannot create import_folder: {e}"}), 400

        # Ensure we are registered with the remote peer so require_peer_auth passes.
        # This is a no-op if the remote already knows us; upsert is idempotent.
        import logging as _logging
        _log = _logging.getLogger(__name__)
        local = mgr.local_peer
        reg_ok, reg_body = await mgr.transport.send(
            peer, "/api/peer/register",
            data={"host": local.api_host, "port": local.api_port},
        )
        if not reg_ok:
            _log.warning(
                "Self-registration with %s:%d failed (local=%s:%d): %s",
                peer.api_host, peer.api_port,
                local.api_host, local.api_port,
                reg_body,
            )
            return jsonify({
                "ok": False,
                "error": f"self-registration failed: {reg_body.get('error', reg_body)}",
            }), 502

        mode = s["mode"]
        if mode == "diff":
            after_rowid = s.get("last_seen_rowid") or 0
            ok, meta = await mgr.transport.fetch_json(
                peer, f"/api/peer/import/diff?after_rowid={after_rowid}"
            )
        elif mode == "selective" and file_ids is not None:
            ok, meta = await mgr.transport.fetch_json(peer, "/api/peer/import/meta?mode=full")
            if ok and file_ids:
                fid_set = set(file_ids)
                meta["files"] = [f for f in meta.get("files", []) if f["id"] in fid_set]
        else:
            ok, meta = await mgr.transport.fetch_json(peer, "/api/peer/import/meta?mode=full")

        if not ok:
            _log.warning(
                "Fetch meta from %s:%d failed (mode=%s, local=%s:%d, peer_id=%s): %s",
                peer.api_host, peer.api_port, mode,
                local.api_host, local.api_port, local.peer_id, meta,
            )
            status = meta.get("status")
            err = meta.get("error") or "unknown error"
            detail = f"HTTP {status}: {err}" if status else err
            return jsonify({
                "ok": False,
                "error": f"failed to fetch meta from remote: {detail}",
            }), 502

        import asyncio

        from ..core_impl.import_executor import ImportExecutor
        options = s.get("options", {})

        local_peer_id = mgr.local_peer.peer_id
        from ..core_impl.import_transfer import _SESSION_DOWNLOAD_LIMIT

        claimed = await _call_import_session("claim_execution", session_id, _SESSION_DOWNLOAD_LIMIT)
        if not claimed:
            return jsonify({"ok": False, "error": "session already executed"}), 409

        async def _run():
            try:
                await ImportExecutor.run(
                    session_id=session_id, peer=peer, meta=meta,
                    import_folder=import_folder, options=options,
                    local_peer_id=local_peer_id,
                    execution_claimed=True,
                )
            except Exception as exc:
                logger.exception("Import executor failed: %s", exc)
                if ImportSession.threadsafe_provider():
                    await asyncio.to_thread(ImportSession.update, session_id, status="failed")
                else:
                    ImportSession.update(session_id, status="failed")

        asyncio.get_event_loop().create_task(_run())
        return jsonify({"ok": True, "message": "import started", "session_id": session_id})

    @auth_route(bp, "/api/peer/import/index", methods=["POST"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def fetch_index():
        """Fetch lightweight index from remote and create a session for selective import."""
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        data, err = await require_json_model(request, LocalImportIndexRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        peer_id = data.peer_id
        import_folder = data.import_folder
        options = data.options

        folder, folder_err = _validate_import_folder(import_folder)
        if folder_err:
            return jsonify({"ok": False, "error": folder_err}), 400
        assert folder is not None

        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503

        peer = mgr.registry.get(peer_id)
        if peer is None:
            return jsonify({"ok": False, "error": "peer not in registry"}), 404

        ok, index_data = await mgr.transport.fetch_json(peer, "/api/peer/import/meta?mode=index")
        if not ok:
            return jsonify({"ok": False, "error": "failed to fetch index"}), 502

        sid = await _call_import_session(
            "create",
            peer_id=peer_id, peer_name=peer.name, mode="selective",
            import_folder=str(folder), options=options,
        )
        return jsonify({"ok": True, "session_id": sid, "index": index_data})
