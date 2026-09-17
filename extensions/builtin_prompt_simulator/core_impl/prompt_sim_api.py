"""Quart blueprint factory facade for the Prompt Simulator extension."""

from __future__ import annotations

from quart import Blueprint

try:
    from .prompt_sim_routes import register_prompt_sim_routes
    from .prompt_sim_sweep_axes import register_sweep_axis_routes
    from .prompt_sim_wildcards import register_wildcard_routes
except ImportError:  # pragma: no cover - top-level extension import path
    from prompt_sim_routes import register_prompt_sim_routes
    from prompt_sim_sweep_axes import register_sweep_axis_routes
    from prompt_sim_wildcards import register_wildcard_routes


def create_prompt_simulator_blueprint(import_name: str):
    bp = Blueprint("ext_prompt_sim", import_name, template_folder="templates")
    register_prompt_sim_routes(bp)
    register_wildcard_routes(bp)
    register_sweep_axis_routes(bp)
    return bp
