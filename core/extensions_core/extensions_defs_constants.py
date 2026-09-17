"""Constants for extension system."""


MANIFEST_NAMES_JSON = ("extension.json",)
MANIFEST_NAMES_YAML = ("extension.yml", "extension.yaml")

HOOK_DEFINITIONS: dict[str, str] = {
    "on_scan_file": "exclusive",
    "on_normalize_tags": "chain",
    "on_export_record": "chain",
    "on_search_filter": "chain",
    "on_db_migrate": "chain",
    "on_build_sections": "collect",  # additive: each extension returns its own sections
}

VALID_TYPES = {"importer", "transformer", "exporter", "ui_widget", "general"}

VALID_CATEGORIES = {
    "metadata",      # Metadata extraction (importer)
    "bridge",        # External tool integration bridge
    "prompt",        # Prompt-related tools
    "ai",            # AI / hardware acceleration
    "library",       # Library management & browsing
    "system",        # System & infrastructure
}

# Category display order (for UI sorting)
CATEGORY_ORDER = [
    "metadata",
    "ai",
    "bridge",
    "prompt",
    "library",
    "system",
]

# Capabilities that extensions can declare (legacy compatibility)
VALID_CAPABILITIES: set[str] = {
    "db:read",
    "db:write",
    "fs:read",
    "fs:write",
    "event_bus",
    "network",
    "subprocess",
}

# Extension Sandbox: permission system (Phase 1)
VALID_PERMISSIONS: set[str] = {
    "db:read", "db:write",
    "fs:read:own", "fs:read:scan_roots", "fs:read:any",
    "fs:write:own", "fs:write:data", "fs:write:any",
    "network:local", "network:internet",
    "subprocess",
    "event_bus",
    "config:read", "config:write",
    "blueprint:api", "blueprint:page",
}

META_ARGS = frozenset(
    {
        "--help",
        "-h",
        "--version",
        "-V",
        "--verbose",
        "-v",
        "--quiet",
        "-q",
        "--debug",
        "--config",
    }
)
