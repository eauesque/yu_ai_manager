"""Tool Classification Master -- classifies MCP tools by safety level.

Level 0 (auto):    Read operations. No approval required.
Level 1 (notify):  Write operations. Notification after execution.
Level 2 (approve): Destructive/irreversible. Approval required before execution.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Safety level constants
LEVEL_AUTO = 0
LEVEL_NOTIFY = 1
LEVEL_APPROVE = 2

LEVEL_NAMES = {
    LEVEL_AUTO: "auto",
    LEVEL_NOTIFY: "notify",
    LEVEL_APPROVE: "approve",
}
NAME_TO_LEVEL = {v: k for k, v in LEVEL_NAMES.items()}

# Prefix-based automatic classification rules
_AUTO_PREFIXES = (
    "get_", "list_", "search_", "find_", "debug_",
    "text_search", "semantic_search", "semantic_backend_info",
    "semantic_index_status",
    "wd_tagger_model_status", "wd_tagger_stats",
    "wd_tagger_get_", "wd_tagger_untagged",
    "wd_tagger_vlm_models",
    "get_analysis_config", "get_analysis_result", "get_analysis_stats",
    "agent_status", "agent_journal", "agent_circuit_breaker_status",
    "agent_budget_status",
)

_APPROVE_PREFIXES = (
    "delete_", "remove_", "archive_cleanup_execute",
    "uninstall_", "restore_backup",
    "share_to_", "install_",
)

# Explicit classification for individual tools
_EXPLICIT_LEVELS: dict[str, int] = {
    # Level 2: approve
    "add_scan_root": LEVEL_APPROVE,
    "remove_scan_root": LEVEL_APPROVE,
    "toggle_scan_root": LEVEL_APPROVE,
    "set_extension_config": LEVEL_APPROVE,
    "toggle_extension": LEVEL_APPROVE,
    "create_backup": LEVEL_APPROVE,
    "restore_backup": LEVEL_APPROVE,
    "agent_kill": LEVEL_APPROVE,
    "agent_resume": LEVEL_APPROVE,
    "archive_cleanup_execute": LEVEL_APPROVE,
    "shutdown_server": LEVEL_APPROVE,
    "clear_scan_history": LEVEL_APPROVE,
    "secrets_rotate": LEVEL_APPROVE,

    # Level 1: notify
    "llm_backend_disable": LEVEL_NOTIFY,
    "llm_backend_enable": LEVEL_NOTIFY,
    "agent_audit_acknowledge": LEVEL_NOTIFY,
    "rate_images": LEVEL_NOTIFY,
    "set_tags": LEVEL_NOTIFY,
    "split_tags": LEVEL_NOTIFY,
    "set_annotations": LEVEL_NOTIFY,
    "add_to_collection": LEVEL_NOTIFY,
    "remove_from_collection": LEVEL_NOTIFY,
    "create_collection": LEVEL_NOTIFY,
    "create_prompt": LEVEL_NOTIFY,
    "update_prompt": LEVEL_NOTIFY,
    "trigger_scan": LEVEL_NOTIFY,
    "scan_directory": LEVEL_NOTIFY,
    "wd_tagger_tag_file": LEVEL_NOTIFY,
    "wd_tagger_batch": LEVEL_NOTIFY,
    "wd_tagger_delete_tags": LEVEL_NOTIFY,
    "wd_tagger_delete_tags_batch": LEVEL_NOTIFY,
    "wd_tagger_delete_profile": LEVEL_NOTIFY,
    "wd_tagger_create_profile": LEVEL_NOTIFY,
    "wd_tagger_update_profile": LEVEL_NOTIFY,
    "wd_tagger_set_active_model": LEVEL_NOTIFY,
    "start_lora_training": LEVEL_NOTIFY,
    "export_lora_dataset": LEVEL_NOTIFY,
    "preview_lora_train_command": LEVEL_AUTO,
    "analyze_image": LEVEL_NOTIFY,
    "analyze_batch": LEVEL_NOTIFY,
    "compute_hashes": LEVEL_NOTIFY,
    "semantic_index_start": LEVEL_NOTIFY,
    "semantic_index_stop": LEVEL_NOTIFY,
    "import_chat_log": LEVEL_NOTIFY,
    "reprocess_chat_logs": LEVEL_NOTIFY,
    "set_md_scan_roots": LEVEL_NOTIFY,
    "batch_download_zip": LEVEL_NOTIFY,
    "generate_freeze_pullback": LEVEL_NOTIFY,

    # Level 0: auto (explicitly overridden tools)
    "agent_budget_reset": LEVEL_AUTO,
    "agent_circuit_breaker_reset": LEVEL_AUTO,

    # Pre-existing tools missing explicit classification — Level 2
    "secrets_export": LEVEL_APPROVE,
    "secrets_import": LEVEL_APPROVE,
    "migrate_secrets_to_keychain": LEVEL_APPROVE,
    "agent_undo": LEVEL_APPROVE,

    # Pre-existing tools missing explicit classification — Level 1
    "agent_anomaly_reset": LEVEL_NOTIFY,
}

# Cache for config.json override settings
_config_overrides: dict[str, int] = {}


def configure(config: dict) -> None:
    """Load safety level override settings from config.json."""
    global _config_overrides
    _config_overrides.clear()
    overrides = (
        config.get("agent_safety", {})
        .get("tool_safety_levels", {})
        .get("overrides", {})
    )
    for tool_name, level_name in overrides.items():
        if isinstance(level_name, str) and level_name in NAME_TO_LEVEL:
            _config_overrides[tool_name] = NAME_TO_LEVEL[level_name]


def classify(tool_name: str) -> int:
    """Return safety level for a tool name.

    Priority: config override > explicit classification > prefix rules > default (auto)
    """
    # 1. config.json overrides
    if tool_name in _config_overrides:
        return _config_overrides[tool_name]

    # 2. Explicit classification table
    if tool_name in _EXPLICIT_LEVELS:
        return _EXPLICIT_LEVELS[tool_name]

    # 3. Prefix-based automatic classification
    if tool_name.startswith(_AUTO_PREFIXES):
        return LEVEL_AUTO

    if tool_name.startswith(_APPROVE_PREFIXES):
        return LEVEL_APPROVE

    # Bridge tools require approval
    if "_bridge_" in tool_name:
        return LEVEL_APPROVE

    # Write prefixes default to notify
    _notify_prefixes = (
        "set_", "add_", "create_", "update_", "rate_",
        "trigger_", "scan_", "import_", "compute_",
        "switch_", "toggle_",
    )
    if tool_name.startswith(_notify_prefixes):
        return LEVEL_NOTIFY

    # Default: auto (treated as read)
    return LEVEL_AUTO


def classify_name(tool_name: str) -> str:
    """Return the safety level name for a tool name."""
    return LEVEL_NAMES[classify(tool_name)]


def get_all_overrides() -> dict[str, str]:
    """Return current config overrides with level names."""
    return {k: LEVEL_NAMES[v] for k, v in _config_overrides.items()}


def get_classification_summary() -> dict[str, list]:
    """Return a summary of all explicitly classified tools."""
    result: dict[str, list] = {"auto": [], "notify": [], "approve": []}
    for tool_name, level in _EXPLICIT_LEVELS.items():
        result[LEVEL_NAMES[level]].append(tool_name)
    for tool_name, level in _config_overrides.items():
        name = LEVEL_NAMES[level]
        if tool_name not in result[name]:
            result[name].append(tool_name)
    for key in result:
        result[key].sort()
    return result
