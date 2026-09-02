"""Settings Management API — Secret management routes.

Handles secrets/status, export, import, and migrate-keychain endpoints.
"""

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_secrets_routes(bp) -> None:
    """Register secret management routes on the given blueprint."""

    # -- Secrets status ----------------------------------------------------

    @bp.route("/api/settings/secrets/status")
    async def api_secrets_status():
        """Return encryption key backend status."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core.key_provider import get_status
        return api_result(await run_db_sync(get_status), 200)

    # -- Secrets export ----------------------------------------------------

    @bp.route("/api/settings/secrets/export", methods=["POST"])
    async def api_secrets_export():
        """Export encryption key as password-protected JSON."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core.key_export import export_key

        body = await request.get_json(silent=True)
        if not body or "password" not in body:
            return api_error(
                "Request body must contain 'password'", 400, code="bad_request",
            )

        result = await run_db_sync(export_key, body["password"])
        if not result["success"]:
            return api_error(result["message"], 400, code="export_failed")
        return api_result(result, 200)

    # -- Secrets import ----------------------------------------------------

    @bp.route("/api/settings/secrets/import", methods=["POST"])
    async def api_secrets_import():
        """Import encryption key from exported data."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core.key_export import import_key

        body = await request.get_json(silent=True)
        if not body or "export_data" not in body or "password" not in body:
            return api_error(
                "Request body must contain 'export_data' and 'password'",
                400,
                code="bad_request",
            )

        result = await run_db_sync(import_key, body["export_data"], body["password"])
        if not result["success"]:
            return api_error(result["message"], 400, code="import_failed")
        return api_result(result, 200)

    # -- Secrets migrate plaintext -----------------------------------------

    @bp.route("/api/settings/secrets/migrate", methods=["POST"])
    async def api_secrets_migrate():
        """Encrypt all plaintext secrets in config.json."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core.secret_store import migrate_plaintext_secrets
        count = await run_db_sync(migrate_plaintext_secrets)
        return api_result({"migrated": count}, 200)

    # -- Secrets migrate to keychain ---------------------------------------

    @bp.route("/api/settings/secrets/migrate-keychain", methods=["POST"])
    async def api_secrets_migrate_keychain():
        """Migrate encryption key from file backend to OS keychain."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core.key_provider import migrate_to_keychain

        result = await run_db_sync(migrate_to_keychain)
        if not result["success"]:
            return api_error(result["message"], 400, code="migration_failed")
        return api_result(result, 200)

    # -- Key rotation -------------------------------------------------------

    @bp.route("/api/settings/secrets/rotate", methods=["POST"])
    async def api_secrets_rotate():
        """Rotate the active Fernet key and re-encrypt all secret fields."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core.key_rotation import rotate_secrets

        result = await run_db_sync(rotate_secrets)
        if not result.get("ok"):
            return api_error(result.get("error", "ローテーション失敗"), 500, code="rotate_failed")
        return api_result(result, 200)

    # -- Key ring info -------------------------------------------------------

    @bp.route("/api/settings/secrets/keyring")
    async def api_secrets_keyring():
        """Return the list of key_ids in the ring and the active key_id."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core.key_provider import get_key_ring_info

        return api_result(await run_db_sync(get_key_ring_info), 200)
