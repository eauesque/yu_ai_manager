"""Settings Management API — Bitwarden vault integration routes.

Handles bw-status, bw-folders, push-to-bw, and bw-mapping DELETE endpoints.
"""

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_vault_bw_routes(bp) -> None:
    """Register Bitwarden-related routes on the given blueprint."""

    # -- Bitwarden status --------------------------------------------------

    @bp.route("/api/settings/bw-status")
    async def api_settings_bw_status():
        """Return Bitwarden CLI status."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core.bw_store import get_bw_status
        return api_result(await run_db_sync(get_bw_status), 200)

    # -- Bitwarden folder list ---------------------------------------------

    @bp.route("/api/settings/secrets/bw-folders")
    async def api_secrets_bw_folders():
        """Return available Bitwarden folders."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core import bw_store

        if not bw_store.is_available():
            return api_error(
                "Bitwarden CLI (bw) が利用できません", 503, code="bw_unavailable",
            )

        folders = await run_db_sync(bw_store.list_folders)
        return api_result({"folders": folders}, 200)

    # -- Bitwarden batch write ---------------------------------------------

    @bp.route("/api/settings/secrets/push-to-bw", methods=["POST"])
    async def api_secrets_push_to_bw():
        """Batch-write secrets to Bitwarden and save bw_secrets mapping."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err

        from core.configuration.json_rw import load_config_json, save_config_json
        from core.settings_core import bw_store
        from core.settings_core.secret_store import decrypt, is_encrypted
        from core.settings_core.settings_schema import (
            SETTINGS_SCHEMA,
            resolve_dotted_key,
        )

        if not bw_store.is_available():
            return api_error(
                "Bitwarden CLI (bw) が利用できません", 503, code="bw_unavailable",
            )

        body = await request.get_json(silent=True)
        if not body:
            return api_error(
                "リクエストボディが必要です", 400, code="bad_request",
            )

        folder_id = body.get("folder_id")  # None allowed (no folder specified)
        item_name = body.get("item_name", "YU AI Manager")

        def _push(fid, iname):
            config = load_config_json()

            secrets_to_push = {}
            try:
                for s in SETTINGS_SCHEMA:
                    if not s.secret:
                        continue
                    raw = resolve_dotted_key(config, s.key)
                    if raw is None or raw == "":
                        continue
                    plaintext = decrypt(str(raw)) if is_encrypted(str(raw)) else str(raw)
                    if plaintext:
                        secrets_to_push[s.key] = plaintext

                if not secrets_to_push:
                    return {"error": "no_secrets"}

                result = bw_store.push_secrets_to_bw(fid, iname, secrets_to_push)
                if not result["success"]:
                    return {"error": "bw_push_failed", "message": result["message"]}
            finally:
                # Clear plaintext secrets from memory
                secrets_to_push.clear()

            config["bw_secrets"] = result["mappings"]
            save_config_json(config)
            bw_store.clear_cache()

            return {
                "ok": True,
                "message": result["message"],
                "pushed_keys": list(result["mappings"].keys()),
                "mappings": result["mappings"],
            }

        res = await run_db_sync(_push, folder_id, item_name)

        if res.get("error") == "no_secrets":
            return api_error(
                "書き込み対象のシークレットがありません", 400, code="no_secrets",
            )
        if res.get("error") == "bw_push_failed":
            return api_error(res["message"], 500, code="bw_push_failed")

        return api_result({
            "message": res["message"],
            "pushed_keys": res["pushed_keys"],
            "mappings": res["mappings"],
        }, 200)

    # -- Delete Bitwarden URI mapping --------------------------------------

    @bp.route("/api/settings/bw-mapping/<path:key>", methods=["DELETE"])
    async def api_settings_bw_mapping_delete(key: str):
        """Remove a key from bw_secrets mapping (revert to local encryption)."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err

        def _delete_bw_mapping(k):
            from core.configuration.json_rw import load_config_json, save_config_json
            config = load_config_json()
            bw_map = config.get("bw_secrets", {})
            if not isinstance(bw_map, dict) or k not in bw_map:
                return False
            del bw_map[k]
            if not bw_map:
                config.pop("bw_secrets", None)
            save_config_json(config)
            return True

        found = await run_db_sync(_delete_bw_mapping, key)
        if not found:
            return api_error("Key not in bw_secrets mapping", 404, code="not_found")
        return api_result({"key": key, "unlinked": True}, 200)
