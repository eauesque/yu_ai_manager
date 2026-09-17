"""LoRA Dataset Manager Blueprint and route registration."""

from __future__ import annotations

from pathlib import Path

from quart import Blueprint

_TEMPLATE_DIR = str(Path(__file__).resolve().parent.parent / "templates")


def create_lora_dataset_blueprint(import_name: str) -> Blueprint:
    """Create and configure the Blueprint with all routes."""
    bp = Blueprint(
        "lora_dataset",
        import_name,
        template_folder=_TEMPLATE_DIR,
        url_prefix="/ext/lora-dataset",
    )

    # Import and register route handlers
    from . import api_export, api_presets, api_projects, api_train

    api_projects.register(bp)
    api_export.register(bp)
    api_train.register(bp)
    api_presets.register(bp)

    # Page route
    @bp.route("/")
    async def lora_dataset_page():
        from quart import render_template
        return await render_template("lora_dataset/lora_dataset.html")

    return bp
