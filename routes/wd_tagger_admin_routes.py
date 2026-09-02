"""Admin and model-management routes for WD-Tagger."""

import asyncio
import json
import re

from quart import jsonify, request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_local

_PROFILE_JSON_MAX_BYTES = 1024 * 1024
_ID_RE_HTTP = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _serialize_profile_safe(profile, meta=None):
    """Serialize a TaggerProfile for the /api/wd-tagger/profiles endpoint."""
    out = {
        "id": profile.id,
        "display_name": profile.display_name,
        "model_id": profile.model_id,
        "adapter_family": profile.adapter_family,
        "backend": profile.backend,
        "builtin": profile.builtin,
    }
    out["categories_mode"] = profile.categories_mode
    out["threshold_source"] = {"type": profile.threshold_source.get("type")}
    if meta is not None:
        out["origin"] = meta["origin"]
        out["overrides_builtin"] = meta["overrides_builtin"]
    return out


def register_admin_routes(bp, wt_importer, require_admin_scope, logger):
    @bp.route("/_internal/wd-tagger/profiles-changed", methods=["POST"])
    async def _internal_wd_tagger_profiles_changed():
        err = require_local("wd-tagger profiles changed notify")
        if err:
            return err
        from extensions.builtin_wd_tagger.core_impl.registry import TaggerRegistry

        await asyncio.to_thread(TaggerRegistry.get().reload)
        return api_result({"ok": True})

    @bp.route("/api/wd-tagger/profiles", methods=["GET"])
    async def api_wt_profiles_get():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        def _list_profiles():
            from core.services_core import wd_active_model
            from extensions.builtin_wd_tagger.core_impl.registry import TaggerRegistry

            available_ids = wd_active_model.list_available_model_ids()
            profiles = []
            for profile, meta in TaggerRegistry.get().list_profiles_with_metadata():
                serialized = _serialize_profile_safe(profile, meta)
                serialized["has_tags"] = (
                    profile.id in available_ids
                    or profile.model_id in available_ids
                )
                profiles.append(serialized)
            return {
                "profiles": profiles,
                "active_model_id": wd_active_model.get_active_wd_model_id(),
            }

        return api_result(await run_db_sync(_list_profiles))

    @bp.route("/api/wd-tagger/profiles/<id_>", methods=["GET"])
    async def api_wt_profile_get(id_: str):
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        if not _ID_RE_HTTP.match(id_):
            return api_error("invalid id", 400, code="invalid_id")

        from core.services_core import wd_tagger_profile_store as store

        try:
            result = await asyncio.to_thread(store.serialize_profile_full, id_)
        except store.NotFoundError:
            return api_error("not found", 404, code="not_found")
        except store.InvalidIdError:
            return api_error("invalid id", 400, code="invalid_id")
        return api_result(result)

    async def _read_profile_body():
        if request.content_length and request.content_length > _PROFILE_JSON_MAX_BYTES:
            return None, api_error("profile too large", 413, code="profile_too_large")
        raw = await request.get_data(cache=False, as_text=False)
        if len(raw) > _PROFILE_JSON_MAX_BYTES:
            return None, api_error("profile too large", 413, code="profile_too_large")
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            body = json.loads(text)
        except (UnicodeDecodeError, ValueError) as exc:
            return None, api_error(
                f"invalid json: {exc}",
                400,
                code="validation_failed",
            )
        return body, None

    @bp.route("/api/wd-tagger/profiles", methods=["POST"])
    async def api_wt_profile_create():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        body, err = await _read_profile_body()
        if err:
            return err
        if not isinstance(body, dict):
            return api_error("validation failed", 400, code="validation_failed")
        body_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(body_id, str) or not _ID_RE_HTTP.match(body_id):
            return api_error("invalid id", 400, code="invalid_id")

        from core.services_core import wd_tagger_profile_store as store

        try:
            result = await asyncio.to_thread(store.create_profile, body)
        except store.ValidationFailedError as exc:
            return api_error(
                "validation failed",
                400,
                code="validation_failed",
                extra={"errors": exc.errors},
            )
        except store.IdConflictError as exc:
            return api_error(f"id conflict: {exc.id_}", 409, code="id_conflict")
        except store.InvalidIdError:
            return api_error("invalid id", 400, code="invalid_id")
        except store.ProfileTooLargeError:
            return api_error("profile too large", 413, code="profile_too_large")
        return api_result(result)

    @bp.route("/api/wd-tagger/profiles/<id_>", methods=["PUT"])
    async def api_wt_profile_update(id_: str):
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        if not _ID_RE_HTTP.match(id_):
            return api_error("invalid id", 400, code="invalid_id")

        body, err = await _read_profile_body()
        if err:
            return err
        if not isinstance(body, dict):
            return api_error("validation failed", 400, code="validation_failed")

        from core.services_core import wd_tagger_profile_store as store

        try:
            result = await asyncio.to_thread(store.update_profile, id_, body)
        except store.NotFoundError:
            return api_error("not found", 404, code="not_found")
        except store.IdImmutableError:
            return api_error("id immutable", 400, code="id_immutable")
        except store.BuiltinReadOnlyError:
            return api_error("builtin is read-only", 403, code="builtin_read_only")
        except store.ValidationFailedError as exc:
            return api_error(
                "validation failed",
                400,
                code="validation_failed",
                extra={"errors": exc.errors},
            )
        except store.InvalidIdError:
            return api_error("invalid id", 400, code="invalid_id")
        except store.ProfileTooLargeError:
            return api_error("profile too large", 413, code="profile_too_large")
        return api_result(result)

    @bp.route("/api/wd-tagger/profiles/<id_>", methods=["DELETE"])
    async def api_wt_profile_delete(id_: str):
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        if not _ID_RE_HTTP.match(id_):
            return api_error("invalid id", 400, code="invalid_id")

        from core.services_core import wd_tagger_profile_store as store

        try:
            await asyncio.to_thread(store.delete_profile, id_)
        except store.NotFoundError:
            return api_error("not found", 404, code="not_found")
        except store.BuiltinReadOnlyError:
            return api_error("builtin is read-only", 403, code="builtin_read_only")
        except store.InUseError as exc:
            return api_error(
                "profile is active model",
                409,
                code="in_use",
                extra={"active_model_id": exc.active_model_id},
            )
        except store.InvalidIdError:
            return api_error("invalid id", 400, code="invalid_id")
        return api_result({"deleted": True})

    @bp.route("/api/wd-tagger/profiles/<id_>/test", methods=["POST"])
    async def api_wt_profile_test(id_: str):
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        if not _ID_RE_HTTP.match(id_):
            return api_error("invalid id", 400, code="invalid_id")

        from core.services_core import wd_tagger_profile_store as store

        try:
            result = await asyncio.to_thread(store.dry_run_download, id_)
        except store.NotFoundError:
            return api_error("not found", 404, code="not_found")
        except store.InvalidIdError:
            return api_error("invalid id", 400, code="invalid_id")

        if not result.get("ok"):
            code = result.get("code", "validation_failed")
            status = {
                "timeout": 408,
                "ssrf_blocked": 502,
                "hf_unavailable": 502,
            }.get(code, 400)
            return api_error(
                result.get("detail", code),
                status,
                code=code,
                extra={"files": result.get("files", [])},
            )
        return api_result(result)

    @bp.route("/api/wd-tagger/active-model", methods=["GET"])
    async def api_wt_active_model_get():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        from core.services_core import wd_active_model

        result = await run_db_sync(
            lambda: {
                "active_model_id": wd_active_model.get_active_wd_model_id(),
                "available_models": wd_active_model.list_available_models(),
            }
        )
        return api_result(result)

    @bp.route("/api/wd-tagger/active-model", methods=["PUT"])
    async def api_wt_active_model_put():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        from core.services_core import wd_active_model

        data = await request.get_json(silent=True)
        if data is None:
            return api_error("Invalid JSON body", 400, code="invalid_json")
        if not isinstance(data, dict):
            return api_error(
                "model_id must be a string or null",
                400,
                code="invalid_model_id",
            )
        try:
            model_id = wd_active_model.validate_model_id(data.get("model_id"))
        except ValueError as exc:
            return api_error(str(exc), 400, code="invalid_model_id")

        if model_id is not None:
            exists = await run_db_sync(
                wd_active_model.model_is_known_for_activation,
                model_id,
            )
            if not exists:
                return api_error("Unknown WD model", 400, code="unknown_model")

        await run_db_sync(wd_active_model.set_active_wd_model_id, model_id)
        return api_result({"active_model_id": model_id})

    @bp.route("/api/wd-tagger/xmp/<int:file_id>", methods=["GET"])
    async def api_wt_xmp_read(file_id):
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        def _read_xmp(fid):
            from core.services_core.db_state import get_readonly_db

            con = get_readonly_db()
            row = con.execute(
                "SELECT path FROM files WHERE id = ? AND is_deleted = 0",
                (fid,),
            ).fetchone()
            if not row:
                return None
            get_xmp_info = wt_importer("xmp_read").get_xmp_info
            return get_xmp_info(row["path"])

        info = await run_db_sync(_read_xmp, file_id)
        if info is None:
            return api_error("File not found", 404, code="file_not_found")
        return api_result({"file_id": file_id, "xmp": info})

    @bp.route("/api/wd-tagger/vlm/test", methods=["GET"])
    async def api_wt_vlm_test():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        url = request.args.get("url", "").strip()
        if not url:
            return api_error("url parameter required", 400, code="missing_url")

        from core.analysis.openai_compat_utils import (  # type: ignore[reportAttributeAccessIssue]
            check_openai_compat_connection,
            validate_openai_compat_url,
        )

        err = validate_openai_compat_url(url, allow_local=True)
        if err:
            return api_error(err, 400, code="invalid_url")

        # Outer bound: `list_openai_compat_models` carries a socket timeout,
        # but that does not cover `getaddrinfo` -- a hostname that cannot be
        # resolved (or a resolver that cannot be reached) stalls past it. A
        # connection test that never returns is worse than one that says no.
        try:
            result = await asyncio.wait_for(
                run_db_sync(
                    lambda: check_openai_compat_connection(url, allow_local=True)
                ),
                timeout=6.0,
            )
        except TimeoutError:
            result = {
                "connected": False,
                "models": [],
                "error": "Connection timeout",
            }
        return api_result(result)

    @bp.route("/api/wd-tagger/vlm/models", methods=["GET"])
    async def api_wt_vlm_models():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        url = request.args.get("url", "").strip()
        if not url:
            return api_error("url parameter required", 400, code="missing_url")

        from core.analysis.openai_compat_utils import (  # type: ignore[reportAttributeAccessIssue]
            list_openai_compat_models,
            validate_openai_compat_url,
        )

        err = validate_openai_compat_url(url, allow_local=True)
        if err:
            return api_error(err, 400, code="invalid_url")

        try:
            models = await run_db_sync(list_openai_compat_models, url, allow_local=True)
            return api_result({"models": models})
        except Exception as exc:
            logger.warning(
                "WD-Tagger VLM model listing failed for %s: %s",
                url,
                exc,
            )
            return api_error(
                "VLM connection failed",
                502,
                code="vlm_connection_error",
            )

    @bp.route("/api/wd-tagger/model/download", methods=["POST"])
    async def api_wt_model_download():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        from extensions.builtin_wd_tagger.core_impl import (
            model_download as _model_download,
        )
        from extensions.builtin_wd_tagger.core_impl.registry import TaggerRegistry

        data = await request.get_json(silent=True) or {}
        profile_id = data.get("profile_id")
        legacy_model_id = data.get("model_id")
        if not isinstance(legacy_model_id, str):
            legacy_model_id = data.get("repo")

        if not isinstance(profile_id, str) and not isinstance(legacy_model_id, str):
            return api_error(
                "profile_id required (model_id legacy bridge also accepted)",
                400,
                code="missing_id",
            )

        reg = TaggerRegistry.get()
        profile = None
        deprecated = False
        deprecation_key: str | None = None

        if isinstance(profile_id, str):
            try:
                profile = reg.resolve(profile_id)
            except LookupError:
                return api_error(
                    f"Unknown profile_id: {profile_id!r}",
                    404,
                    code="profile_not_found",
                    extra={"profile_id": profile_id},
                )
        else:
            assert isinstance(legacy_model_id, str)  # narrowed by Line 214 check
            candidates = reg.find_all_by_model_id(legacy_model_id)
            if len(candidates) == 0:
                return api_error(
                    f"Unknown model_id: {legacy_model_id!r}",
                    404,
                    code="profile_not_found",
                    extra={"profile_id": legacy_model_id},
                )
            if len(candidates) > 1:
                return api_error(
                    f"Ambiguous model_id {legacy_model_id!r}: {len(candidates)} profiles match. "
                    "Use profile_id instead.",
                    400,
                    code="ambiguous_model_id",
                    extra={
                        "profile_id": legacy_model_id,
                        "matches": [p.id for p in candidates],
                    },
                )
            profile = candidates[0]
            deprecated = True
            deprecation_key = legacy_model_id

        try:
            result = await run_db_sync(
                _model_download.download_model_for_profile, profile
            )
        except Exception as exc:
            logger.warning(
                "WD-Tagger model download failed for %s: %s",
                profile.id, exc,
            )
            return api_error(
                "Model download failed",
                500,
                code="download_failed",
            )

        payload = {
            "ok": True,
            "error": None,
            "data": None,
            "profile_id": result.profile_id,
            "cache_dir": str(result.cache_dir),
            "downloaded": result.downloaded,
            "skipped_optional": [list(t) for t in result.skipped_optional],
            "failed_optional": [list(t) for t in result.failed_optional],
        }
        response = jsonify(payload)
        if deprecated:
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = "v4.196.0"
            response.headers["Warning"] = (
                f'299 - "model_id={deprecation_key!r} is deprecated; '
                'use profile_id. Removed in v4.196.0."'
            )
        return response

    @bp.route("/api/wd-tagger/model/status", methods=["GET"])
    async def api_wt_model_status():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        get_config = wt_importer("config_ops").get_config
        download_mod = wt_importer("model_download")
        known_models = download_mod.KNOWN_MODELS
        config = get_config()
        key = (
            request.args.get("profile_id")
            or request.args.get("model_id")
            or request.args.get("repo")
            or config.get("model", "SmilingWolf/wd-swinv2-tagger-v3")
        )

        profile = None
        try:
            from extensions.builtin_wd_tagger.core_impl.registry import TaggerRegistry

            reg = TaggerRegistry.get()
            profile = reg.resolve(key) if request.args.get("profile_id") else reg.resolve_any(key)
        except LookupError:
            if request.args.get("profile_id"):
                return api_error(
                    f"Unknown profile_id: {key!r}",
                    404,
                    code="profile_not_found",
                    extra={"profile_id": key},
                )
        if profile is not None:
            status = await run_db_sync(download_mod.get_model_status_for_profile, profile)
        else:
            status = await run_db_sync(download_mod.get_model_status, key)
        status["known_models"] = known_models
        return api_result(status)
