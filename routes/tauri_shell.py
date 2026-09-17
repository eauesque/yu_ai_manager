"""Tauri shell endpoint."""
from quart import Blueprint, render_template

bp = Blueprint("tauri_shell", __name__)


@bp.route("/tauri-shell")
async def tauri_shell():
    return await render_template("tauri_shell.html")
