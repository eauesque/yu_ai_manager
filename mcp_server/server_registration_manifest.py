"""Explicit registration order for MCP tool hub modules."""
from __future__ import annotations

import importlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolRegistration:
    module_name: str
    function_name: str

    def load(self) -> Callable:
        module = importlib.import_module(f"{__package__}.{self.module_name}")
        return getattr(module, self.function_name)


TOOL_REGISTRATIONS = [
    ToolRegistration("agent_safety_tools", "register_agent_safety_tools"),
    ToolRegistration("analysis_tools", "register_analysis_tools"),
    ToolRegistration("archive_cleanup_tools", "register_archive_cleanup_tools"),
    ToolRegistration("auto_scan_tools", "register_auto_scan_tools"),
    ToolRegistration("backup_tools", "register_backup_tools"),
    ToolRegistration("boss_mode_tools", "register_boss_mode_tools"),
    ToolRegistration("chatlog_tools", "register_chatlog_tools"),
    ToolRegistration("comfyui_bridge_tools", "register_comfyui_bridge_tools"),
    ToolRegistration("cross_search_tools", "register_cross_search_tools"),
    ToolRegistration("debug_tools", "register_debug_tools"),
    ToolRegistration("diagnostics_tools", "register_diagnostics_tools"),
    ToolRegistration("dnd_tools", "register_dnd_tools"),
    ToolRegistration("download_tools", "register_download_tools"),
    ToolRegistration("duplicate_tools", "register_duplicate_tools"),
    ToolRegistration("extension_tools", "register_extension_tools"),
    ToolRegistration("favorites_tools", "register_favorites_tools"),
    ToolRegistration("fleet_tools", "register_fleet_tools"),
    ToolRegistration("freeze_pullback_tools", "register_freeze_pullback_tools"),
    ToolRegistration("gateway_tools", "register_gateway_tools"),
    ToolRegistration("github_tools", "register_github_tools"),
    ToolRegistration("hailo_chat_tools", "register_hailo_chat_tools"),
    ToolRegistration("hailo_genai_tools", "register_hailo_genai_tools"),
    ToolRegistration("hailo_tagger_tools", "register_hailo_tagger_tools"),
    ToolRegistration("help_tools", "register_help_tools"),
    ToolRegistration("lan_share_tools", "register_lan_share_tools"),
    ToolRegistration("llm_tools", "register_llm_tools"),
    ToolRegistration("lora_dataset_tools", "register_lora_dataset_tools"),
    ToolRegistration("mcp_client_tools", "register_mcp_client_tools"),
    ToolRegistration("md_viewer_tools", "register_md_viewer_tools"),
    ToolRegistration("mesh_inference_toggle_tools", "register_mesh_inference_toggle_tools"),
    ToolRegistration("mesh_inference_tools", "register_mesh_inference_tools"),
    ToolRegistration("misc_tools", "register_misc_tools"),
    ToolRegistration("monthly_report_tools", "register_monthly_report_tools"),
    ToolRegistration("nai_bridge_tools", "register_nai_bridge_tools"),
    ToolRegistration("ocr_tools", "register_ocr_tools"),
    ToolRegistration("profiles_tools", "register_profiles_tools"),
    ToolRegistration("prompt_library_tools", "register_prompt_library_tools"),
    ToolRegistration("prompt_sim_tools", "register_prompt_sim_tools"),
    ToolRegistration("prompt_syntax_tools", "register_prompt_syntax_tools"),
    ToolRegistration("s2t_tools", "register_s2t_tools"),
    ToolRegistration("scan_roots_tools", "register_scan_roots_tools"),
    ToolRegistration("scheduler_tools", "register_scheduler_tools"),
    ToolRegistration("sd_bridge_tools", "register_sd_bridge_tools"),
    ToolRegistration("sd_nai_convert_tools", "register_sd_nai_convert_tools"),
    ToolRegistration("semantic_tools", "register_semantic_tools"),
    ToolRegistration("settings_tools", "register_settings_tools"),
    ToolRegistration("sns_share_tools", "register_sns_share_tools"),
    ToolRegistration("source_tools", "register_source_tools"),
    ToolRegistration("stats_tools", "register_stats_tools"),
    ToolRegistration("svg_tools", "register_svg_tools"),
    ToolRegistration("tag_dict_tools", "register_tag_dict_tools"),
    ToolRegistration("tagger_servers_tools", "register_tagger_servers_tools"),
    ToolRegistration("trophy_tools", "register_trophy_tools"),
    ToolRegistration("ui_tools", "register_ui_tools"),
    ToolRegistration("update_tools", "register_update_tools"),
    ToolRegistration("wait_tools", "register_wait_tools"),
    ToolRegistration("wd_tagger_tools", "register_wd_tagger_tools"),
    ToolRegistration("webhook_tools", "register_webhook_tools"),
    ToolRegistration("yolo_detect_tools", "register_yolo_detect_tools"),
    ToolRegistration("yolo_stream_tools", "register_yolo_stream_tools"),
]


def iter_tool_registrars() -> Iterator[Callable]:
    for registration in TOOL_REGISTRATIONS:
        yield registration.load()
