"""builtin-prompt-syntax Extension -- prompt syntax highlighting and analysis

Blueprint:
  /ext/syntax/engine.js     -- tokenizer and syntax recognition engine
  /ext/syntax/widget.js     -- editor widget
  /ext/syntax/style.css     -- stylesheet
  /ext/syntax/analyze  API  -- server-side syntax analysis (Python)

Syntax analysis is done in client-side JS; no scan/inspect hooks needed.
"""

import sys
from pathlib import Path

_ext_dir = Path(__file__).resolve().parent
if str(_ext_dir) not in sys.path:
    sys.path.insert(0, str(_ext_dir))

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from prompt_syntax_analyze import analyze_prompt_text
from prompt_syntax_assets import build_engine_js, build_style_css, build_widget_js

_EXT_DIR = _ext_dir


def get_blueprint():
    """Quart Blueprint -- static asset serving + analysis API."""
    from quart import Blueprint, Response, jsonify, request

    bp = Blueprint(
        "ext_prompt_syntax",
        __name__,
    )

    @bp.route("/engine.js")
    async def serve_engine():
        return Response(build_engine_js(_EXT_DIR), mimetype="application/javascript")

    @bp.route("/widget.js")
    async def serve_widget():
        return Response(build_widget_js(_EXT_DIR), mimetype="application/javascript")

    @bp.route("/style.css")
    async def serve_style():
        return Response(build_style_css(_EXT_DIR), mimetype="text/css")

    @bp.route("/analyze", methods=["POST"])
    async def api_analyze():
        """Server-side syntax analysis (simple analysis on Python side)

        主にバッチ処理やCLI向け。通常のUI表示はクライアントサイドJS。
        """
        data = await request.get_json(silent=True) or {}
        payload, status = analyze_prompt_text(data.get("text", ""))
        return jsonify(payload), status

    return bp
