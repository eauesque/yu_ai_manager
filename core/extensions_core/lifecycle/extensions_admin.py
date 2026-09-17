"""Common extension management operations (separated from routes layer)."""

import logging
import re
import subprocess
import sys
from pathlib import Path

from core.configuration.config_lock import config_lock
from core.configuration.json_rw import candidate_config_paths, load_config_json, save_config_json
from core.settings_core.secret_store import encrypt

logger = logging.getLogger(__name__)

# Absolute path from project root (CWD-independent). Existing tests
# monkeypatch this attribute directly (tests/basic/test_extension_lifecycle_config.py,
# tests/extensions/lan_cowork/test_bootstrap_remove_deprecated.py) and
# extensions/builtin_lan_cowork/lan_cowork_ext.py imports it by name, so the
# symbol itself must keep this exact name -- only how _config_path() resolves
# it may change.
_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config.json"


def _config_path() -> Path:
    """Resolve the active config path, honoring a --config override.

    Reads _CONFIG_PATH as a plain module global specifically so
    monkeypatch.setattr(module, "_CONFIG_PATH", ...) in existing tests keeps
    working unchanged (Python resolves the bare name against the module's
    globals dict at call time). The process-wide override set via
    set_default_config_path() -- needed because this module used to ignore
    --config entirely, letting an isolated harness/test process mutate the
    real repo config.json via this hardcoded absolute path (Codex stop-time
    review, 2026-08-30) -- is checked first, but only when no test has
    monkeypatched _CONFIG_PATH out from under the default; if _CONFIG_PATH
    no longer equals the module's own compile-time default, an explicit
    monkeypatch is in effect and takes precedence over the override.
    """
    from core.configuration.json_rw import _config_path_override

    if _config_path_override and _CONFIG_PATH == _CONFIG_PATH_COMPILE_DEFAULT:
        return Path(_config_path_override).resolve()
    if _CONFIG_PATH != _CONFIG_PATH_COMPILE_DEFAULT:
        return _CONFIG_PATH
    for path in candidate_config_paths():
        if Path(path).exists():
            return Path(path).resolve()
    return _CONFIG_PATH


_CONFIG_PATH_COMPILE_DEFAULT = _CONFIG_PATH


# Patterns that are dangerous in requirements.txt
_DANGEROUS_REQ_PATTERNS = re.compile(
    r"^\s*(--(index-url|extra-index-url|find-links|trusted-host)\b"
    r"|https?://"
    r"|git\+"
    r"|svn\+"
    r"|hg\+"
    r"|bzr\+)",
    re.IGNORECASE,
)
_SECRET_FIELD_TOKENS = ("secret", "token", "password", "api_key", "apikey")


def _is_secret_field(field_name: str) -> bool:
    lowered = str(field_name or "").strip().lower()
    return any(token in lowered for token in _SECRET_FIELD_TOKENS)


def _validate_requirements(content: str) -> str | None:
    """Check requirements.txt for dangerous directives. Returns error or None."""
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _DANGEROUS_REQ_PATTERNS.search(stripped):
            return f"Line {i}: disallowed directive: {stripped[:80]}"
    return None


def install_requirements(ext_dir: Path) -> dict | None:
    """Run pip install -r if requirements.txt exists."""
    req_path = ext_dir / "requirements.txt"
    if not req_path.exists():
        return None

    content = req_path.read_text(encoding="utf-8").strip()
    if not content:
        return None

    # Validate for dangerous directives
    req_err = _validate_requirements(content)
    if req_err:
        return {"status": "error", "detail": f"requirements.txt rejected: {req_err}"}

    pkg_count = len([line for line in content.splitlines() if line.strip() and not line.strip().startswith("#")])

    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pip", "install",
                "-r", str(req_path),
                "--break-system-packages",
                "--quiet",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300
        )
        if result.returncode != 0:
            return {"status": "error", "detail": result.stderr[:500], "packages": pkg_count}
        return {"status": "ok", "packages": pkg_count}
    except FileNotFoundError:
        return {"status": "error", "detail": "pip not found"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "detail": "pip install timed out (300s)", "packages": pkg_count}


def git_pull_ff_only(ext_dir: Path, timeout: int = 60):
    """Execute git pull --ff-only."""
    return subprocess.run(
        ["git", "-C", str(ext_dir), "pull", "--ff-only"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )


def persist_extension_state(name: str, enabled: bool) -> None:
    with config_lock():
        config = load_config_json(str(_config_path()))
        ext_config = config.setdefault("extensions", {})
        ext_config.setdefault(name, {})["enabled"] = enabled
        save_config_json(config, str(_config_path()))


def get_extension_config_value(ext_name: str, field_name: str, default=None):
    if not _config_path().exists():
        return default
    config = load_config_json(str(_config_path()))
    return config.get("extensions", {}).get(ext_name, {}).get(field_name, default)


def save_extension_config_values(ext_name: str, values: dict) -> None:
    with config_lock():
        config = load_config_json(str(_config_path()))
        ext_config = config.setdefault("extensions", {}).setdefault(ext_name, {})
        for field_name, value in values.items():
            if _is_secret_field(field_name) and isinstance(value, str):
                if "****" in value or "..." in value:
                    continue
                value = encrypt(value)
            ext_config[field_name] = value
        save_config_json(config, str(_config_path()))


def validate_config_value(cf, value) -> str | None:
    field_type = str(cf.type or "").strip().lower()
    if field_type in {"bool", "boolean"}:
        if not isinstance(value, bool):
            return f"Expected bool, got {type(value).__name__}"
    elif field_type == "enum":
        if value not in cf.options:
            return f"Invalid option '{value}'. Allowed: {cf.options}"
    elif field_type in {"int", "integer"}:
        if not isinstance(value, int):
            return f"Expected int, got {type(value).__name__}"
        if cf.range and len(cf.range) == 2 and (value < cf.range[0] or value > cf.range[1]):
            return f"Out of range [{cf.range[0]}, {cf.range[1]}]"
    elif field_type in {"float", "number"}:
        if not isinstance(value, (int, float)):
            return f"Expected number, got {type(value).__name__}"
        if cf.range and len(cf.range) == 2 and (value < cf.range[0] or value > cf.range[1]):
            return f"Out of range [{cf.range[0]}, {cf.range[1]}]"
    elif field_type in {"str", "string"} and not isinstance(value, str):
        return f"Expected str, got {type(value).__name__}"
    return None


def delete_extension_config_value(ext_name: str, field_name: str) -> None:
    """Remove a single config key from an extension's config section.

    No-op if the key or extension section does not exist.
    save_config_json uses tempfile + os.replace() (atomic write) so a crash
    during write cannot corrupt config.json.
    """
    with config_lock():
        config = load_config_json(str(_config_path()))
        ext_section = config.get("extensions", {}).get(ext_name)
        if ext_section is not None and field_name in ext_section:
            del ext_section[field_name]
            save_config_json(config, str(_config_path()))
            logger.info(
                "Removed deprecated config key: extensions.%s.%s",
                ext_name,
                field_name,
            )
