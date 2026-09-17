"""Page rendering routes (HTML views)."""

from pathlib import Path

from jinja2 import TemplateNotFound
from quart import Blueprint, current_app, render_template, send_from_directory

from core.update_api.policy import get_version_string as get_version

_PROJECT_ROOT_PATH = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = str(_PROJECT_ROOT_PATH)


def _detect_python_executable() -> str:
    """Resolve the python executable path that Claude Desktop should call.

    Prefers uv-managed `.venv/`, falls back to legacy `venv/`. Returns an
    absolute path; emits empty string if neither exists so the UI can show
    a placeholder instead of a broken path.
    """
    import sys as _sys
    candidates: list[Path] = []
    if _sys.platform.startswith("win"):
        candidates = [
            _PROJECT_ROOT_PATH / ".venv" / "Scripts" / "python.exe",
            _PROJECT_ROOT_PATH / "venv" / "Scripts" / "python.exe",
        ]
    else:
        candidates = [
            _PROJECT_ROOT_PATH / ".venv" / "bin" / "python3",
            _PROJECT_ROOT_PATH / ".venv" / "bin" / "python",
            _PROJECT_ROOT_PATH / "venv" / "bin" / "python3",
            _PROJECT_ROOT_PATH / "venv" / "bin" / "python",
        ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ""


_PYTHON_EXECUTABLE = _detect_python_executable()

bp = Blueprint("pages", __name__)


def _redirect_308(url: str):
    """308 empty-body redirect matching the Rust native frontend (parity).

    axum's ``Redirect::permanent`` emits a bodyless 308; Quart's ``redirect()``
    would emit an HTML body, so build a minimal Response to keep parity exact
    with crates/yu-server/src/frontend.rs.
    """
    from quart import Response
    resp = Response(b"", status=308)
    resp.headers["Location"] = url
    return resp


@bp.route("/")
async def index():
    """Main page."""
    return await render_template("index.html", active="search")


@bp.route("/search")
async def search_page():
    """Search page (for dashboard UI; other UIs redirect to /)."""
    try:
        return await render_template("search.html", active="search")
    except TemplateNotFound:
        # 308 empty-body redirect: parity with Rust native frontend.rs
        return _redirect_308("/")


@bp.route("/stats")
async def stats():
    """Stats page."""
    return await render_template("stats.html", active="stats")


@bp.route("/story")
async def story():
    """Story page."""
    return await render_template("story.html", active="story")


@bp.route("/tools")
async def tools_page():
    """Tools page."""
    return await render_template("tools.html", active="tools")


@bp.route("/extensions")
async def extensions_page():
    """Extension Manager page."""
    return await render_template("extensions.html", active="extensions")


@bp.route("/settings")
async def settings_page():
    """Settings page."""
    return await render_template("settings.html", active="settings",
        project_root=_PROJECT_ROOT,
        python_executable=_PYTHON_EXECUTABLE,
    )


@bp.route("/diagnostics")
async def diagnostics_page():
    """Diagnostics and bug report export page."""
    return await render_template("diagnostics.html", active="diagnostics")


@bp.route("/update")
async def update_page():
    """Signed update package page."""
    return await render_template("update.html", active="diagnostics")


@bp.route("/gateway")
async def gateway_page():
    """Gateway backend management page."""
    return await render_template("gateway.html", active="gateway", version=get_version())


@bp.route("/headroom")
async def headroom_page():
    """Headroom proxy statistics page."""
    return await render_template("headroom.html", active="headroom")


@bp.route("/inspect")
async def inspect_page():
    """Metadata inspection page."""
    return await render_template("inspect.html", active="inspect")


@bp.route("/report")
async def report_page():
    """Monthly report page."""
    return await render_template("report.html", active="report")


@bp.route("/scheduler")
async def scheduler_page():
    """Task scheduler page."""
    return await render_template("scheduler.html", active="scheduler")


@bp.route("/llm-router")
async def llm_router_page():
    """LLM Router admin dashboard."""
    return await render_template("llm_router.html", active="llm_router")


@bp.route("/sweep/<sweep_id>")
async def sweep_view_page(sweep_id: str):
    """Dedicated comparison view for a single Sweep run.

    The page hydrates client-side from ``/api/sweep/info`` +
    ``/api/sweep/files`` (a ``?from=<file_id>`` query string supplies the
    folder hint that ``/api/sweep/files`` requires).
    """
    return await render_template(
        "sweep_view.html", active="sweep_view", sweep_id=sweep_id,
    )


@bp.route("/mesh-inference")
async def mesh_inference_page():
    """Mesh inference disable matrix dashboard."""
    return await render_template("mesh_inference.html", active="mesh_inference")


@bp.route("/lan-cowork")
async def lan_cowork_page():
    """LAN Cowork peer import dashboard."""
    return await render_template("lan_cowork.html", active="lan_cowork")


@bp.route("/lan-cowork/peers")
async def lan_cowork_peers_redirect():
    """Redirect legacy URL to extension blueprint."""
    return _redirect_308("/ext/lan_cowork/peers")


@bp.route("/scan-jobs")
async def scan_jobs_page():
    """Scan history and active jobs page."""
    return await render_template("scan_jobs.html", active="scan_jobs")


@bp.route("/scan_jobs")
async def scan_jobs_legacy_redirect():
    """Legacy underscore URL → canonical hyphen URL."""
    return _redirect_308("/scan-jobs")


@bp.route("/agent-journal")
async def agent_journal_page():
    """Agent operation journal page."""
    return await render_template("agent_journal.html", active="tools")


@bp.route("/agent_journal")
async def agent_journal_legacy_redirect():
    """Legacy underscore URL → canonical hyphen URL."""
    return _redirect_308("/agent-journal")


@bp.route("/agent-memory")
async def agent_memory_page():
    """Agent Memory dashboard — read-only view of agentmemory state."""
    return await render_template("agent_memory.html", active="agent_memory")


@bp.route("/agent_memory")
async def agent_memory_legacy_redirect():
    """Legacy underscore URL → canonical hyphen URL."""
    return _redirect_308("/agent-memory")


@bp.route("/crypto_tools")
async def crypto_tools_legacy_redirect():
    """Legacy underscore URL → canonical hyphen URL."""
    return _redirect_308("/crypto-tools")


@bp.route("/llm_router")
async def llm_router_legacy_redirect():
    """Legacy underscore URL → canonical hyphen URL."""
    return _redirect_308("/llm-router")


@bp.route("/mesh_inference")
async def mesh_inference_legacy_redirect():
    """Legacy underscore URL → canonical hyphen URL."""
    return _redirect_308("/mesh-inference")


@bp.route("/lan_cowork")
async def lan_cowork_legacy_redirect():
    """Legacy underscore URL → canonical hyphen URL."""
    return _redirect_308("/lan-cowork")


@bp.route("/github")
async def github_legacy_redirect():
    """Legacy URL → GitHub Integration extension page."""
    return _redirect_308("/ext/github")


@bp.route("/sw.js")
async def service_worker():
    """Service Worker — parity with Rust frontend.rs serve_sw()."""
    from quart import Response
    sw_path = _PROJECT_ROOT_PATH / "ui" / "default" / "static" / "sw.js"
    if not sw_path.exists():
        return Response(b"", status=404)
    body = sw_path.read_text(encoding="utf-8")
    resp = Response(body, status=200, mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@bp.route("/favicon.ico")
async def favicon():
    """favicon.ico → SVG or PNG fallback (checks active UI then default)"""
    import os

    from core.ui_core.resolver import get_ui_paths
    # Build search paths: active UI static folder, then default UI
    candidates = []
    active_static = current_app.static_folder
    if active_static:
        candidates.append(active_static)
    active_ui = current_app.config.get("ACTIVE_UI", "default")
    if active_ui != "default":
        candidates.append(str(get_ui_paths(active_ui)["static_folder"]))
    candidates.append(str(get_ui_paths("default")["static_folder"]))
    for static_dir in candidates:
        for name, mime in [("favicon.svg", "image/svg+xml"), ("favicon.png", "image/png")]:
            if os.path.exists(os.path.join(static_dir, name)):
                return await send_from_directory(static_dir, name, mimetype=mime)
    return await send_from_directory(
        str(get_ui_paths("default")["static_folder"]), "favicon.svg", mimetype="image/svg+xml"
    )
