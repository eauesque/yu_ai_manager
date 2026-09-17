"""Explicit registration order for MCP tool hub modules.

Hubs are tagged with one or more profiles. ``YU_MCP_PROFILES`` selects which
profiles are registered, so a session can expose a workable slice of the ~630
tools instead of all of them. Unset (or ``all``) keeps the historical
behaviour of registering everything.
"""
from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

ENV_VAR = "YU_MCP_PROFILES"
ALL = "all"

#: Profile names that may appear in ``YU_MCP_PROFILES``.
KNOWN_PROFILES = frozenset(
    {
        "core",  # library, search, settings, scan, stats — the daily set
        "tagging",  # WD/Hailo/YOLO taggers and image analysis
        "generate",  # SD / ComfyUI / NAI bridges and the prompt library
        "llm",  # chat, chatlog, OCR, speech-to-text
        "agent",  # agent safety, extensions, scheduler, webhooks
        "devops",  # GitHub, fleet, gateway, mesh, debug
        "social",  # SNS share, markdown viewer
        "training",  # LoRA dataset building
    }
)


@dataclass(frozen=True)
class ToolRegistration:
    module_name: str
    function_name: str
    profiles: frozenset[str] = field(default_factory=lambda: frozenset({"core"}))

    def load(self) -> Callable:
        module = importlib.import_module(f"{__package__}.{self.module_name}")
        return getattr(module, self.function_name)


def _p(*names: str) -> frozenset[str]:
    return frozenset(names)


TOOL_REGISTRATIONS = [
    ToolRegistration("agent_safety_tools", "register_agent_safety_tools", _p("agent")),
    ToolRegistration("analysis_tools", "register_analysis_tools", _p("tagging")),
    ToolRegistration("archive_cleanup_tools", "register_archive_cleanup_tools", _p("core")),
    ToolRegistration("auto_scan_tools", "register_auto_scan_tools", _p("devops")),
    ToolRegistration("backup_tools", "register_backup_tools", _p("core")),
    ToolRegistration("boss_mode_tools", "register_boss_mode_tools", _p("agent")),
    ToolRegistration("chatlog_tools", "register_chatlog_tools", _p("llm")),
    ToolRegistration("comfyui_bridge_tools", "register_comfyui_bridge_tools", _p("generate")),
    ToolRegistration("cross_search_tools", "register_cross_search_tools", _p("core")),
    ToolRegistration("debug_tools", "register_debug_tools", _p("devops")),
    ToolRegistration("diagnostics_tools", "register_diagnostics_tools", _p("core")),
    ToolRegistration("dnd_tools", "register_dnd_tools", _p("core")),
    ToolRegistration("download_tools", "register_download_tools", _p("core")),
    ToolRegistration("duplicate_tools", "register_duplicate_tools", _p("core")),
    ToolRegistration("extension_tools", "register_extension_tools", _p("agent")),
    ToolRegistration("favorites_tools", "register_favorites_tools", _p("core")),
    ToolRegistration("fleet_tools", "register_fleet_tools", _p("devops")),
    ToolRegistration("freeze_pullback_tools", "register_freeze_pullback_tools", _p("devops")),
    ToolRegistration("gateway_tools", "register_gateway_tools", _p("devops")),
    ToolRegistration("github_tools", "register_github_tools", _p("devops")),
    ToolRegistration("hailo_chat_tools", "register_hailo_chat_tools", _p("llm")),
    ToolRegistration("hailo_genai_tools", "register_hailo_genai_tools", _p("llm")),
    ToolRegistration("hailo_tagger_tools", "register_hailo_tagger_tools", _p("tagging")),
    ToolRegistration("help_tools", "register_help_tools", _p("core")),
    ToolRegistration("lan_share_tools", "register_lan_share_tools", _p("devops")),
    ToolRegistration("llm_tools", "register_llm_tools", _p("llm")),
    ToolRegistration("lora_dataset_tools", "register_lora_dataset_tools", _p("training")),
    ToolRegistration("mcp_client_tools", "register_mcp_client_tools", _p("agent")),
    ToolRegistration("md_viewer_tools", "register_md_viewer_tools", _p("social")),
    ToolRegistration(
        "mesh_inference_toggle_tools", "register_mesh_inference_toggle_tools", _p("devops")
    ),
    ToolRegistration("mesh_inference_tools", "register_mesh_inference_tools", _p("devops")),
    ToolRegistration("misc_tools", "register_misc_tools", _p("core")),
    ToolRegistration("monthly_report_tools", "register_monthly_report_tools", _p("core")),
    ToolRegistration("nai_bridge_tools", "register_nai_bridge_tools", _p("generate")),
    ToolRegistration("ocr_tools", "register_ocr_tools", _p("llm")),
    ToolRegistration("profiles_tools", "register_profiles_tools", _p("core")),
    ToolRegistration("prompt_library_tools", "register_prompt_library_tools", _p("generate")),
    ToolRegistration("prompt_sim_tools", "register_prompt_sim_tools", _p("generate")),
    ToolRegistration("prompt_syntax_tools", "register_prompt_syntax_tools", _p("generate")),
    ToolRegistration("s2t_tools", "register_s2t_tools", _p("llm")),
    ToolRegistration("scan_roots_tools", "register_scan_roots_tools", _p("core")),
    ToolRegistration("scheduler_tools", "register_scheduler_tools", _p("agent")),
    ToolRegistration("sd_bridge_tools", "register_sd_bridge_tools", _p("generate")),
    ToolRegistration("sd_nai_convert_tools", "register_sd_nai_convert_tools", _p("generate")),
    ToolRegistration("semantic_tools", "register_semantic_tools", _p("core")),
    ToolRegistration("settings_tools", "register_settings_tools", _p("core")),
    ToolRegistration("sns_share_tools", "register_sns_share_tools", _p("social")),
    ToolRegistration("source_tools", "register_source_tools", _p("core")),
    ToolRegistration("stats_tools", "register_stats_tools", _p("core")),
    ToolRegistration("svg_tools", "register_svg_tools", _p("core")),
    ToolRegistration("tag_dict_tools", "register_tag_dict_tools", _p("core")),
    ToolRegistration("tagger_servers_tools", "register_tagger_servers_tools", _p("tagging")),
    ToolRegistration("trophy_tools", "register_trophy_tools", _p("core")),
    ToolRegistration("ui_tools", "register_ui_tools", _p("core")),
    ToolRegistration("update_tools", "register_update_tools", _p("core")),
    ToolRegistration("wait_tools", "register_wait_tools", _p("core")),
    ToolRegistration("wd_tagger_tools", "register_wd_tagger_tools", _p("tagging")),
    ToolRegistration("webhook_tools", "register_webhook_tools", _p("agent")),
    ToolRegistration("yolo_detect_tools", "register_yolo_detect_tools", _p("tagging")),
    ToolRegistration("yolo_stream_tools", "register_yolo_stream_tools", _p("tagging")),
]


def parse_profiles(raw: str | None) -> frozenset[str] | None:
    """Parse ``YU_MCP_PROFILES``. Returns ``None`` to mean "register everything".

    Raises ValueError on an unknown name so a typo cannot silently shrink the
    tool surface to nothing.
    """
    if raw is None:
        return None
    wanted = {part.strip().lower() for part in raw.split(",") if part.strip()}
    if not wanted or ALL in wanted:
        return None
    unknown = wanted - KNOWN_PROFILES
    if unknown:
        raise ValueError(
            f"{ENV_VAR}: unknown profile(s) {sorted(unknown)}; "
            f"known profiles are {sorted(KNOWN_PROFILES)} (or '{ALL}')"
        )
    return frozenset(wanted)


def selected_registrations(
    profiles: frozenset[str] | None = None,
) -> list[ToolRegistration]:
    if profiles is None:
        return list(TOOL_REGISTRATIONS)
    return [r for r in TOOL_REGISTRATIONS if r.profiles & profiles]


def iter_tool_registrars() -> Iterator[Callable]:
    profiles = parse_profiles(os.environ.get(ENV_VAR))
    for registration in selected_registrations(profiles):
        yield registration.load()
