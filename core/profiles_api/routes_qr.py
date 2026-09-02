"""Profile QR export/import API routes."""

import json
import logging

from quart import request

from core.configuration.profiles import (
    create_profile,
    export_for_qr,
    load_profile,
    save_profile,
    validate_profile_name,
)
from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope
from core.web.auth_helpers import require_pin as _require_pin

logger = logging.getLogger(__name__)


def register_profiles_qr_routes(bp):
    """Register profile QR export/import endpoints."""

    @bp.route("/api/profiles/<name>/export", methods=["GET"])
    async def api_profiles_export(name: str):
        auth_err = _require_pin()
        if auth_err:
            return auth_err
        scope_err = _require_admin_scope()
        if scope_err:
            return scope_err
        try:
            data = await run_db_sync(export_for_qr, name)
        except ValueError as exc:
            logger.warning("Profile export failed for %s: %s", name, exc)
            return api_error("Profile not found", 404, code="profile_not_found")

        qr_payload = {
            "schema": "yu://profile/1",
            "profile": data,
        }
        return api_success({"qr_data": json.dumps(qr_payload, ensure_ascii=False)})

    @bp.route("/api/profiles/import-preview", methods=["POST"])
    async def api_profiles_import_preview():
        auth_err = _require_pin()
        if auth_err:
            return auth_err
        body, err = await require_json_dict(request)
        if err:
            from core.infra_core.api_errors import api_result
            return api_result(err[0], err[1])

        raw = body.get("qr_data", "")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return api_error("Invalid QR data format", 400, code="invalid_qr")

        if not isinstance(parsed, dict) or "profile" not in parsed:
            return api_error("QR data must contain a 'profile' key", 400, code="invalid_qr")

        incoming = parsed["profile"]
        name = incoming.get("name", "")
        name_err = validate_profile_name(name)
        if name_err:
            return api_error(name_err, 400, code="invalid_profile_name")

        existing = await run_db_sync(load_profile, name)
        if existing:
            # Compute diff
            diff = {}
            all_keys = set(existing) | set(incoming)
            for k in sorted(all_keys):
                old_val = existing.get(k)
                new_val = incoming.get(k)
                if old_val != new_val:
                    diff[k] = {"old": old_val, "new": new_val}
            return api_success({
                "mode": "existing",
                "name": name,
                "label": incoming.get("label", name),
                "diff": diff,
            })
        else:
            return api_success({
                "mode": "new",
                "name": name,
                "label": incoming.get("label", name),
                "preview": incoming,
            })

    @bp.route("/api/profiles/import", methods=["POST"])
    async def api_profiles_import():
        auth_err = _require_pin()
        if auth_err:
            return auth_err
        body, err = await require_json_dict(request)
        if err:
            from core.infra_core.api_errors import api_result
            return api_result(err[0], err[1])

        raw = body.get("qr_data", "")
        mode = body.get("mode", "full")  # full / diff / new
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return api_error("Invalid QR data format", 400, code="invalid_qr")

        if not isinstance(parsed, dict) or "profile" not in parsed:
            return api_error("QR data must contain a 'profile' key", 400, code="invalid_qr")

        incoming = parsed["profile"]
        name = incoming.get("name", "")
        name_err = validate_profile_name(name)
        if name_err:
            return api_error(name_err, 400, code="invalid_profile_name")

        existing = await run_db_sync(load_profile, name)

        if mode == "new" and existing:
            return api_error(f"Profile '{name}' already exists", 409, code="profile_exists")

        if existing and mode == "diff":
            # Merge only changed keys
            merged = dict(existing)
            merged.update(incoming)
            await run_db_sync(save_profile, name, merged)
            return api_success({"imported": name, "mode": "diff"})
        elif existing and mode == "full":
            # Full overwrite
            await run_db_sync(save_profile, name, incoming)
            return api_success({"imported": name, "mode": "full"})
        else:
            # New profile
            try:
                await run_db_sync(
                    create_profile,
                    name,
                    incoming.get("label", name),
                    incoming.get("description", ""),
                    incoming,
                )
            except ValueError as exc:
                logger.warning("Profile import failed for %s: %s", name, exc)
                return api_error("Profile import failed", 400, code="import_failed")
            return api_success({"imported": name, "mode": "new"}, 201)
