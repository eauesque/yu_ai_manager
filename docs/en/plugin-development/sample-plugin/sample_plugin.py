"""
Sample Plugin -- YU AI Manager Extension template.

Usage:
  1. Copy the entire `sample-plugin/` folder into `extensions/`
  2. Restart the server
  3. The plugin appears in Settings > Extensions and in the nav sidebar

This file demonstrates:
  - Blueprint registration (get_blueprint)
  - API endpoint
  - Config reading
  - HTML page rendering
"""

from datetime import datetime

from core.extensions_core.extensions_admin import get_extension_config_value
from quart import Blueprint, jsonify, render_template_string

bp = Blueprint(
    "sample_plugin",
    __name__,
    template_folder="templates",
)

EXT_NAME = "sample-plugin"

PAGE_HTML = """
{% extends "_nav.html" %}
{% block title %}Sample Plugin{% endblock %}
{% block content %}
<div class="container" style="padding:20px;">
  <h1>Sample Plugin</h1>
  <p style="font-size:18px;">{{ greeting }}</p>
  {% if timestamp %}
  <p style="color:var(--muted);">Server time: {{ timestamp }}</p>
  {% endif %}
</div>
{% endblock %}
"""


@bp.route("/ext/sample/")
async def index():
    greeting = get_extension_config_value(EXT_NAME, "greeting", "Hello, World!")
    show_ts = get_extension_config_value(EXT_NAME, "show_timestamp", True)
    return await render_template_string(
        PAGE_HTML,
        greeting=greeting,
        # Naive on purpose: this file is documentation, and its output is
        # mirrored in the translated copies, which would drift.
        timestamp=datetime.now().isoformat() if show_ts else None,  # noqa: DTZ005
    )


@bp.route("/ext/sample/api/status")
async def api_status():
    return jsonify({"ok": True, "plugin": EXT_NAME, "version": "1.0.0"})


def get_blueprint():
    """Extension loader calls this to register the blueprint."""
    return bp
