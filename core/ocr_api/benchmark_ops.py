"""OCR API -- benchmark and community profiles."""

from __future__ import annotations

import logging
from pathlib import Path

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

logger = logging.getLogger(__name__)


def register(bp: Blueprint) -> None:
    """Register routes on the Blueprint."""


    # ── Benchmark ──

    @bp.route("/api/ocr/benchmark/cases", methods=["GET"])
    async def api_ocr_benchmark_cases():
        """List available benchmark cases."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        benchmark_dir = request.args.get("dir", "")

        def _list_cases():
            from core.ocr_core.benchmark import load_benchmark_set
            cases = load_benchmark_set(benchmark_dir or None)
            return {
                "cases": [
                    {
                        "image": Path(c.image_path).name,
                        "task": c.task,
                        "language": c.language,
                        "expected_length": len(c.expected_text),
                        "tags": c.tags,
                    }
                    for c in cases
                ],
                "total": len(cases),
            }

        try:
            return api_result(await run_db_sync(_list_cases))
        except ValueError as exc:
            return api_error(str(exc), 400)

    # ── Community profiles ──

    @bp.route("/api/ocr/profiles", methods=["GET"])
    async def api_ocr_profiles():
        """List model profiles."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        def _list():
            from core.ocr_core.profiles import list_profiles
            return list_profiles()

        return api_result({"profiles": await run_db_sync(_list)})

    @bp.route("/api/ocr/profiles/fetch", methods=["POST"])
    async def api_ocr_profiles_fetch():
        """Fetch and merge community profiles."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        body = await request.get_json(silent=True) or {}
        url = body.get("url", "")
        if not url:
            return api_error("url is required", 400)

        def _fetch():
            from core.ocr_core.profiles import merge_community_profiles
            return merge_community_profiles(url, save=True)

        try:
            result = await run_db_sync(_fetch)
        except RuntimeError as exc:
            logger.warning("OCR community profile fetch failed for %s: %s", url, exc)
            msg = str(exc) or "Profile fetch failed"
            status = 400 if msg == "Blocked address" or "http/https" in msg.lower() else 500
            return api_error(msg, status)

        return api_result(result)

    @bp.route("/api/ocr/profiles/<model_prefix>", methods=["PUT"])
    async def api_ocr_profile_update(model_prefix: str):
        """Manually update a model profile."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        body = await request.get_json(silent=True) or {}
        scores = body.get("scores", {})
        if not scores:
            return api_error("scores is required", 400)

        def _update():
            from core.ocr_core.profiles import update_model_profile
            update_model_profile(model_prefix, scores)

        await run_db_sync(_update)
        return api_result({"model": model_prefix, "scores": scores})
