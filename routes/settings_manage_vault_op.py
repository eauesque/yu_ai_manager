"""Settings Management API — 1Password vault integration routes.

Handles op-status, op-mapping DELETE, op-vaults, and push-to-op endpoints.
"""

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_vault_op_routes(bp) -> None:
    """Register 1Password-related routes on the given blueprint."""

    # -- 1Password status --------------------------------------------------

    @bp.route("/api/settings/op-status")
    async def api_settings_op_status():
        """Return 1Password CLI status."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core.op_store import get_op_status
        return api_result(await run_db_sync(get_op_status), 200)

    # -- Delete 1Password URI mapping --------------------------------------

    @bp.route("/api/settings/op-mapping/<path:key>", methods=["DELETE"])
    async def api_settings_op_mapping_delete(key: str):
        """Remove a key from op_secrets mapping (revert to local encryption)."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err

        def _delete_op_mapping(k):
            from core.configuration.json_rw import load_config_json, save_config_json
            config = load_config_json()
            op_map = config.get("op_secrets", {})
            if not isinstance(op_map, dict) or k not in op_map:
                return False
            del op_map[k]
            if not op_map:
                config.pop("op_secrets", None)
            save_config_json(config)
            return True

        found = await run_db_sync(_delete_op_mapping, key)
        if not found:
            return api_error("Key not in op_secrets mapping", 404, code="not_found")
        return api_result({"key": key, "unlinked": True}, 200)

    # -- 1Password vault list ----------------------------------------------

    @bp.route("/api/settings/secrets/op-vaults")
    async def api_secrets_op_vaults():
        """Return available 1Password vaults."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core import op_store

        if not op_store.is_available():
            return api_error(
                "1Password CLI (op) が利用できません", 503, code="op_unavailable",
            )

        vaults = await run_db_sync(op_store.list_vaults)
        return api_result({"vaults": vaults}, 200)

    # -- 1Password batch write ---------------------------------------------

    @bp.route("/api/settings/secrets/push-to-op", methods=["POST"])
    async def api_secrets_push_to_op():
        """Batch-write secrets to 1Password and save op_secrets mapping."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err

        from core.configuration.json_rw import load_config_json, save_config_json
        from core.settings_core import op_store
        from core.settings_core.secret_store import decrypt, is_encrypted
        from core.settings_core.settings_schema import (
            SETTINGS_SCHEMA,
            resolve_dotted_key,
        )

        if not op_store.is_available():
            return api_error(
                "1Password CLI (op) が利用できません", 503, code="op_unavailable",
            )

        body = await request.get_json(silent=True)
        if not body or "vault" not in body:
            return api_error(
                "リクエストボディに 'vault' が必要です", 400, code="bad_request",
            )

        vault_name = body["vault"]
        item_title = body.get("item_title", "YU AI Manager")
        remove_local = body.get("remove_local", False)

        def _push(vname, ititle, rm_local):
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

                result = op_store.push_secrets_to_op(vname, ititle, secrets_to_push)
                if not result["success"]:
                    return {"error": "op_push_failed", "message": result["message"]}
            finally:
                # Clear plaintext secrets from memory
                secrets_to_push.clear()

            op_map = config.setdefault("op_secrets", {})
            for key, uri in result["uris"].items():
                op_map[key] = uri

            if rm_local:
                for key in result["uris"]:
                    parts = key.split(".")
                    current = config
                    for part in parts[:-1]:
                        if isinstance(current, dict):
                            current = current.get(part, {})
                        else:
                            break
                    if isinstance(current, dict) and parts[-1] in current:
                        del current[parts[-1]]

            save_config_json(config)
            op_store.clear_cache()

            return {
                "ok": True,
                "message": result["message"],
                "pushed_keys": list(result["uris"].keys()),
                "uris": result["uris"],
                "remove_local": rm_local,
            }

        res = await run_db_sync(_push, vault_name, item_title, remove_local)

        if res.get("error") == "no_secrets":
            return api_error(
                "書き込み対象のシークレットがありません", 400, code="no_secrets",
            )
        if res.get("error") == "op_push_failed":
            return api_error(res["message"], 500, code="op_push_failed")

        return api_result({
            "message": res["message"],
            "pushed_keys": res["pushed_keys"],
            "uris": res["uris"],
            "remove_local": res["remove_local"],
        }, 200)
