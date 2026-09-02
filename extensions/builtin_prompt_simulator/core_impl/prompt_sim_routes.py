"""Core route registration for prompt simulator."""

from __future__ import annotations

import logging
from importlib import import_module as _im

from quart import jsonify, render_template, request

from core.prompt.convert import expand_dynamic_prompt

from .dp_probability import analyze_dp_choices
from .emphasis_weight import analyze_emphasis

logger = logging.getLogger(__name__)
sd_nai_engine = _im("extensions.builtin_sd_nai_convert.core_impl.sd_nai_convert_engine")
sd_nai_warnings = _im("extensions.builtin_sd_nai_convert.core_impl.sd_nai_syntax_warnings")


from core.web.auth_helpers import require_admin_scope as _require_admin_scope

_MAX_PROMPT_CHARS = 8192  # per-prompt character limit


def register_prompt_sim_routes(bp):
    @bp.route("/")
    async def simulator_ui():
        return await render_template("simulator.html")

    @bp.route("/manager")
    async def wildcard_manager_ui():
        return await render_template("wildcard_manager.html")

    @bp.route("/dp-analyze", methods=["POST"])
    async def api_dp_analyze():
        data = await request.get_json(silent=True) or {}
        prompt = data.get("prompt", "")
        if not isinstance(prompt, str):
            return jsonify({"error": "prompt must be a string"}), 400
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400
        if len(prompt) > _MAX_PROMPT_CHARS:
            return jsonify({"error": f"Prompt too long (max {_MAX_PROMPT_CHARS} chars)", "code": "prompt_too_long"}), 400
        try:
            return jsonify({"groups": analyze_dp_choices(prompt)})
        except Exception:
            logger.exception("Prompt simulator DP analyze failed")
            return jsonify({"error": "Dynamic prompt analysis failed"}), 500

    @bp.route("/emphasis", methods=["POST"])
    async def api_emphasis():
        data = await request.get_json(silent=True) or {}
        prompt = data.get("prompt", "")
        if not isinstance(prompt, str):
            return jsonify({"error": "prompt must be a string"}), 400
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400
        if len(prompt) > _MAX_PROMPT_CHARS:
            return jsonify({"error": f"Prompt too long (max {_MAX_PROMPT_CHARS} chars)", "code": "prompt_too_long"}), 400
        try:
            return jsonify({"tokens": analyze_emphasis(prompt)})
        except Exception:
            logger.exception("Prompt simulator emphasis analyze failed")
            return jsonify({"error": "Emphasis analysis failed"}), 500

    @bp.route("/convert", methods=["POST"])
    async def api_convert():
        data = await request.get_json(silent=True) or {}
        prompt = data.get("prompt", "")
        mode = data.get("mode", "")
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400
        if len(prompt) > _MAX_PROMPT_CHARS:
            return jsonify({"error": f"Prompt too long (max {_MAX_PROMPT_CHARS} chars)", "code": "prompt_too_long"}), 400
        if mode not in ("nai_to_sd", "sd_to_nai", "expand"):
            return jsonify({"error": "Invalid mode", "code": "invalid_mode"}), 400
        try:
            warnings = []
            if mode in ("nai_to_sd", "sd_to_nai"):
                warnings = sd_nai_warnings.detect_syntax_warnings(prompt, mode)
            if mode == "nai_to_sd":
                result = sd_nai_engine.convert_nai_to_sd(prompt)
            elif mode == "sd_to_nai":
                result = sd_nai_engine.convert_sd_to_nai(prompt)
            else:
                result = expand_dynamic_prompt(prompt, data.get("seed"), wildcards=data.get("wildcards") or None)
            resp = {"result": result}
            if warnings:
                resp["warnings"] = warnings
            return jsonify(resp)
        except Exception:
            logger.exception("Prompt simulator conversion failed")
            return jsonify({"error": "Prompt conversion failed", "code": "convert_failed"}), 500

    @bp.route("/danbooru-ac", methods=["GET"])
    async def api_danbooru_autocomplete():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        q = request.args.get("q", "").strip()
        if not q or len(q) < 2:
            return jsonify({"tags": []})
        limit = min(request.args.get("limit", 10, type=int) or 10, 20)
        try:
            import asyncio
            import json as _json
            import urllib.parse
            import urllib.request

            url = "https://danbooru.donmai.us/autocomplete.json?" + urllib.parse.urlencode(
                {"search[query]": q, "search[type]": "tag_query", "limit": limit}
            )
            req = urllib.request.Request(url, headers={"User-Agent": "YU-AI-Manager/1.0"})

            def _fetch() -> object:
                # Off the event loop on purpose. `urlopen`'s timeout does not
                # bound `getaddrinfo`, so with egress blocked this call hangs
                # well past 5s -- and on the loop it takes every unrelated
                # route down with it. That is the v4.682.10 hang, same shape.
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return _json.loads(resp.read())

            data = await asyncio.to_thread(_fetch)
            return jsonify(
                {
                    "tags": [{"name": item.get("label", ""), "count": item.get("post_count", 0)} for item in data if item.get("label")]
                }
            )
        except Exception:
            return jsonify({"tags": []})
