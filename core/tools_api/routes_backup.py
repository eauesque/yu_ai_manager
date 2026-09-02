"""Route registration for database backup/restore APIs."""

import logging
import shutil
import sqlite3
import tempfile

try:
    from core.services_core.db_cipher import apply_key as _apply_key
    from core.services_core.db_cipher import sqlite3 as _sc
except ImportError:
    _sc = sqlite3  # type: ignore[assignment]
    def _apply_key(con) -> None: pass  # type: ignore[misc]
import contextlib
import time
from datetime import UTC, datetime
from pathlib import Path

from quart import request, send_file

from core.infra_core.api_errors import api_result
from core.infra_core.api_request import require_json_dict
from core.services_core.db_api import get_db_path
from core.services_core.db_async import run_db_sync
from core.tools_api.backup_ops import (
    create_backup_payload,
    delete_backup_payload,
    get_backup_status_payload,
    list_backups_payload,
    restore_backup_payload,
)
from core.web.auth_helpers import require_admin_scope as _require_admin_scope
from core.web.auth_helpers import require_local as _require_local

logger = logging.getLogger(__name__)


def register_tools_backup_routes(bp):
    """Register backup/restore related tool routes."""

    @bp.route("/api/tools/backup-download")
    async def api_tools_backup_download():
        blocked = _require_local("Database backup")
        if blocked:
            return blocked

        def _prepare_backup():
            db_path = get_db_path()
            if not db_path or not db_path.exists():
                return None, None
            try:
                con = _sc.connect(str(db_path))
                _apply_key(con)
                con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                con.close()
            except Exception:
                logger.warning("tools API step failed", exc_info=True)
            timestamp = datetime.now(tz=UTC).astimezone().strftime("%Y%m%d_%H%M%S")
            filename = f"tags_backup_{timestamp}.db"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")  # noqa: SIM115 — intentional: file lives beyond context
            tmp.close()
            shutil.copy2(str(db_path), tmp.name)
            return tmp.name, filename

        tmp_name, filename = await run_db_sync(_prepare_backup)
        if tmp_name is None:
            return api_result({"error": "Database not found"}, 404)

        response = await send_file(
            tmp_name,
            as_attachment=True,
            attachment_filename=filename,
            mimetype="application/x-sqlite3",
        )

        # Delete tempfile after response is sent
        @response.call_on_close
        def _cleanup():
            with contextlib.suppress(OSError):
                Path(tmp_name).unlink(missing_ok=True)

        return response

    @bp.route("/api/tools/restore", methods=["POST"])
    async def api_tools_restore():
        blocked = _require_local("Database restore")
        if blocked:
            return blocked
        files = await request.files
        if "file" not in files:
            return api_result({"error": "No file uploaded"}, 400)

        f = files["file"]
        if not f.filename or not f.filename.endswith(".db"):
            return api_result({"error": "File must have .db extension"}, 400)

        # Read uploaded file into temp location
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")  # noqa: SIM115 — intentional: file lives beyond context
        f.save(tmp.name)
        tmp.close()

        tmp_path_str = tmp.name

        def _validate_and_restore():
            tmp_path = Path(tmp_path_str)

            # Validate file is plaintext SQLite or SQLCipher-encrypted DB
            try:
                header = tmp_path.read_bytes()[:16]
                is_plaintext = header.startswith(b"SQLite format 3\000")
                # Try SQLCipher (encrypted backup created by our system)
                is_cipher = False
                if not is_plaintext:
                    try:
                        _test = _sc.connect(str(tmp_path))
                        _apply_key(_test)
                        _test.execute("SELECT count(*) FROM sqlite_master")
                        _test.close()
                        is_cipher = True
                    except Exception:
                        logger.warning("tools API step failed", exc_info=True)
                if not is_plaintext and not is_cipher:
                    tmp_path.unlink(missing_ok=True)
                    return {"error": "Not a valid SQLite file"}, 400
            except Exception:
                tmp_path.unlink(missing_ok=True)
                return {"error": "Failed to read uploaded file"}, 400

            # Validate 'files' table exists (try SQLCipher first, fall back to plaintext)
            try:
                con = _sc.connect(str(tmp_path))
                _apply_key(con)
                con.execute("PRAGMA trusted_schema = OFF")
                cur = con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
                )
                if not cur.fetchone():
                    con.close()
                    tmp_path.unlink(missing_ok=True)
                    return {"error": "Invalid database: 'files' table not found"}, 400
                dangerous = con.execute(
                    "SELECT type, name FROM sqlite_master WHERE type IN ('trigger', 'view')"
                ).fetchall()
                if dangerous:
                    names = ", ".join(f"{r[0]}:{r[1]}" for r in dangerous[:5])
                    con.close()
                    tmp_path.unlink(missing_ok=True)
                    return {"error": f"Database contains disallowed objects: {names}"}, 400
                con.close()
            except Exception as e:
                tmp_path.unlink(missing_ok=True)
                return {"error": f"Invalid SQLite file: {e}"}, 400

            # Backup existing DB before overwriting
            db_path = get_db_path()
            backup_suffix = f".backup_{int(time.time())}"
            backup_path = db_path.with_suffix(f".db{backup_suffix}")
            try:
                shutil.copy2(str(db_path), str(backup_path))
            except Exception as e:
                tmp_path.unlink(missing_ok=True)
                return {"error": f"Failed to backup current DB: {e}"}, 500

            # Overwrite current DB with uploaded file
            try:
                shutil.copy2(str(tmp_path), str(db_path))
            except Exception as e:
                tmp_path.unlink(missing_ok=True)
                return {"error": f"Failed to restore DB: {e}"}, 500

            tmp_path.unlink(missing_ok=True)

            return {
                "success": True,
                "message": "Database restored successfully",
                "backup": backup_path.name,
            }, 200

        payload, status = await run_db_sync(_validate_and_restore)
        return api_result(payload, status)

    # ── New managed backup endpoints ────────────────────────────────

    @bp.route("/api/tools/backup/create", methods=["POST"])
    async def api_tools_backup_create():
        blocked = _require_local("Backup create")
        if blocked:
            return blocked
        payload, status = await run_db_sync(create_backup_payload)
        return api_result(payload, status)

    @bp.route("/api/tools/backup/list")
    async def api_tools_backup_list():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        payload, status = await run_db_sync(list_backups_payload)
        return api_result(payload, status)

    @bp.route("/api/tools/backup/restore", methods=["POST"])
    async def api_tools_backup_restore():
        blocked = _require_local("Backup restore")
        if blocked:
            return blocked
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        payload, status = await run_db_sync(restore_backup_payload, data)
        return api_result(payload, status)

    @bp.route("/api/tools/backup/delete", methods=["POST"])
    async def api_tools_backup_delete():
        blocked = _require_local("Backup delete")
        if blocked:
            return blocked
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        payload, status = await run_db_sync(delete_backup_payload, data)
        return api_result(payload, status)

    @bp.route("/api/tools/backup/status")
    async def api_tools_backup_status():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        payload, status = await run_db_sync(get_backup_status_payload)
        return api_result(payload, status)
