"""HTTP routes for retag jobs (Phase 2b).

Spec: docs/superpowers/specs/2026-05-10-tagger-pluggable-models-design.md § 5.1, 5.2

5 endpoints (all POST):
  /api/wd-tagger/retag/single   — sync, returns result inline
  /api/wd-tagger/retag/batch    — async, scope=batch (file_ids list)
  /api/wd-tagger/retag/backfill — async, scope=backfill (scan_root + force)
  /api/wd-tagger/retag/query    — async, scope=query (existing search params)
  /api/wd-tagger/retag/cancel   — cancel running retag job
"""

from __future__ import annotations

import logging
from typing import Any

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from routes.wd_tagger_route_utils import parse_bool_field, parse_int_field

logger = logging.getLogger(__name__)

MAX_FILE_IDS_PER_BATCH = 500
MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 64


def _parse_thresholds(data: dict[str, Any]) -> dict[str, float]:
    raw = data.get("thresholds") or {}
    if not isinstance(raw, dict):
        raise ValueError("thresholds must be an object")
    return {
        "general": float(raw.get("general", 0.35)),
        "character": float(raw.get("character", 0.85)),
    }


def register_retag_routes(bp, require_admin_scope, _logger):
    """Register /api/wd-tagger/retag/* routes on the given blueprint."""

    @bp.route("/api/wd-tagger/retag/single", methods=["POST"])
    async def api_retag_single():
        if auth_err := require_admin_scope():
            return auth_err

        data = await request.get_json(silent=True) or {}
        try:
            file_id = int(data["file_id"])
            model_id = str(data["model_id"]).strip()
            if not model_id:
                raise ValueError("model_id required")
            thresholds = _parse_thresholds(data)
            overwrite = parse_bool_field(data, "overwrite_same_model", True)
            set_active = parse_bool_field(data, "set_active", True)
        except (KeyError, TypeError, ValueError) as exc:
            return api_error(str(exc), 400, code="invalid_input")

        from extensions.builtin_wd_tagger.core_impl.retag_jobs import start_single

        try:
            result = await run_db_sync(
                start_single,
                file_id=file_id,
                model_id=model_id,
                thresholds=thresholds,
                overwrite_same_model=overwrite,
                auto_set_active=set_active,
            )
        except LookupError as exc:
            return api_error(str(exc), 404, code="file_not_found")
        except Exception:
            logger.exception("retag/single failed")
            return api_error("Internal error", 500, code="retag_failed")

        return api_result({"data": result})

    @bp.route("/api/wd-tagger/retag/batch", methods=["POST"])
    async def api_retag_batch():
        return await _start_async("batch", await request.get_json(silent=True) or {})

    @bp.route("/api/wd-tagger/retag/backfill", methods=["POST"])
    async def api_retag_backfill():
        return await _start_async("backfill", await request.get_json(silent=True) or {})

    @bp.route("/api/wd-tagger/retag/query", methods=["POST"])
    async def api_retag_query():
        return await _start_async("query", await request.get_json(silent=True) or {})

    @bp.route("/api/wd-tagger/retag/cancel", methods=["POST"])
    async def api_retag_cancel():
        if auth_err := require_admin_scope():
            return auth_err
        from core.jobs_core.jobs import job_manager

        if job_manager.cancel_job("wd_tagger"):
            return api_result({"data": {"status": "cancelling"}})
        return api_error("No running retag job", 404, code="job_not_running")

    async def _start_async(scope: str, data: dict[str, Any]):
        if auth_err := require_admin_scope():
            return auth_err

        try:
            model_id = str(data["model_id"]).strip()
            if not model_id:
                raise ValueError("model_id required")
            thresholds = _parse_thresholds(data)
            batch_size = parse_int_field(
                data,
                "batch_size",
                default=8,
                minimum=MIN_BATCH_SIZE,
                maximum=MAX_BATCH_SIZE,
            )
            limit = parse_int_field(
                data,
                "limit",
                default=0,
                minimum=0,
                maximum=1_000_000,
            )
            set_active = parse_bool_field(data, "set_active", True)
        except (KeyError, TypeError, ValueError) as exc:
            return api_error(str(exc), 400, code="invalid_input")

        kwargs: dict[str, Any] = {
            "scope": scope,
            "model_id": model_id,
            "thresholds": thresholds,
            "batch_size": batch_size,
            "limit": limit,
            "auto_set_active": set_active,
        }

        if scope == "batch":
            file_ids = data.get("file_ids")
            if not isinstance(file_ids, list):
                return api_error("file_ids must be a list", 400, code="invalid_input")
            if len(file_ids) > MAX_FILE_IDS_PER_BATCH:
                return api_error(
                    f"file_ids max {MAX_FILE_IDS_PER_BATCH}",
                    400,
                    code="batch_too_large",
                )
            kwargs["file_ids"] = file_ids
        elif scope == "backfill":
            kwargs["scan_root"] = str(data.get("scan_root", ""))
            try:
                kwargs["force"] = parse_bool_field(data, "force", False)
            except ValueError as exc:
                return api_error(str(exc), 400, code="invalid_input")
        elif scope == "query":
            query_params = data.get("query_params") or {}
            if not isinstance(query_params, dict):
                return api_error(
                    "query_params must be an object",
                    400,
                    code="invalid_input",
                )
            kwargs["query_params"] = query_params
            kwargs["search_fn"] = _build_search_fn()

        from extensions.builtin_wd_tagger.core_impl.retag_jobs import start_batch

        try:
            result = start_batch(**kwargs)
        except Exception:
            logger.exception("retag/%s failed", scope)
            return api_error("Internal error", 500, code="retag_failed")

        if "error" in result:
            return api_error(
                result["error"],
                409,
                code=result.get("code", "retag_error"),
            )
        return api_result({"data": result})


def _build_search_fn():
    """Create a search_fn closure that delegates to build_search_response."""

    def _search(query_params: dict[str, Any]) -> list[int]:
        try:
            from core.search_api.search_response import build_search_response
        except ImportError:
            logger.warning("build_search_response not importable; query scope returns empty")
            return []
        try:
            response: Any = build_search_response(dict(query_params))
            payload, status = response
        except Exception:
            logger.exception("query scope: build_search_response raised")
            return []
        if status != 200 or not isinstance(payload, dict):
            return []
        raw_results = payload.get("results") or []
        results = raw_results if isinstance(raw_results, list) else []
        ids: list[int] = []
        for item in results:
            try:
                ids.append(int(item["id"]))
            except (KeyError, TypeError, ValueError):
                continue
        return ids

    return _search
