"""AI context builder for /api/ai-context.

Does NOT import from core/web/ — csrf_note is injected as a plain string
by the web-layer route handler (routes/ai_context.py), keeping the
infra_core → web layer dependency direction clean.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Blueprint.name -> (capability_name, is_core)
# is_core=True : always registered via app_factory_blueprints.py;
#                missing at startup triggers a drift warning.
# is_core=False: extension BP or optional hardware feature;
#                missing triggers no warning (extension_load phase already reports it,
#                and Blueprint.name may be unbuilt when the import fails).
BLUEPRINT_CAPABILITY_MAP: dict[str, tuple[str, bool]] = {
    "llm_router":    ("llm_router",     True),
    "lan_cowork":    ("lan_cowork",      False),  # extension BP
    "hailo_tagger":  ("hailo",           False),  # optional hardware feature
    "wd_tagger":     ("wd_tagger",       False),  # optional hardware feature
    "analysis":      ("image_analysis",  True),
    "gateway_admin": ("gateway",         True),
    "scheduler":     ("scheduler",       True),
}

_SOFTWARE_NAME = "YU AI Manager"
# pyproject.toml description is a placeholder — hardcoded until pyproject is updated.
_SOFTWARE_DESC = "ローカルファースト AI 画像メタデータ管理ツール"

_cached_version: str | None = None


def _read_version() -> str:
    global _cached_version
    if _cached_version is not None:
        return _cached_version
    version_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
    try:
        _cached_version = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("VERSION ファイルが読めません")
        _cached_version = "unknown"
    return _cached_version


def check_blueprint_drift(registered_names: set[str]) -> None:
    """Warn when a core Blueprint is absent from app.blueprints.

    Call this after extension load completes (runtime_runner.py).
    Extension BPs (is_core=False) are silently skipped — their load
    failures are already reported by the extension_load phase.
    """
    for bp_name, (_, is_core) in BLUEPRINT_CAPABILITY_MAP.items():
        if is_core and bp_name not in registered_names:
            logger.warning(
                "BLUEPRINT_CAPABILITY_MAP drift: core BP %r が app.blueprints に未登録"
                " (リネームまたは削除の可能性)",
                bp_name,
            )


def build_ai_context(
    *,
    csrf_note: str,
    registered_names: set[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Build the data payload for GET /api/ai-context.

    Parameters
    ----------
    csrf_note:
        Human-readable CSRF description, generated from request_hooks.py constants
        by the web-layer caller.
    registered_names:
        ``set(app.blueprints.keys())`` — passed in to avoid web-layer import.
    config:
        In-memory config snapshot (from load_config_json). IO-free within this function.
    """
    version = _read_version()

    capabilities = [
        cap_name
        for bp_name, (cap_name, _) in BLUEPRINT_CAPABILITY_MAP.items()
        if bp_name in registered_names
    ]

    from core.infra_core.ai_context_hints import get_config_hints
    config_hints = get_config_hints(config)

    return {
        "software": {
            "name": _SOFTWARE_NAME,
            "version": version,
            "description": _SOFTWARE_DESC,
        },
        "capabilities": capabilities,
        "urls": {
            "settings_schema": "/api/settings/schema",
            "current_settings": "/api/settings/all",
            "openapi": "/api/openapi.json",
            # startup_log: added in Phase 3 when /api/startup-log is implemented
        },
        "diagnostics": {
            "doctor_start": {"method": "POST", "url": "/api/diagnostics/doctor"},
            "doctor_poll": {"method": "GET", "url": "/api/diagnostics/doctor/{job_id}"},
            "note": "POST で job を起動し、返された job_id を GET で polling して完了を確認する",
        },
        "csrf_note": csrf_note,
        "config_hints": config_hints,
    }
