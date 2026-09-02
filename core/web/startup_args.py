"""Argument/config resolution helpers for web_ui startup."""

import argparse
import os
from pathlib import Path
from typing import Any


def build_webui_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tag Database Web UI")
    parser.add_argument("--db",
                        default=os.environ.get("TAGDB_DB", "data/tags.db"),
                        help="Path to tags.db (default: data/tags.db, env: TAGDB_DB)")
    parser.add_argument("--config",
                        default=os.environ.get("TAGDB_CONFIG"),
                        help="Path to config.json (env: TAGDB_CONFIG)")
    parser.add_argument("--host", default=None, help="Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Port (default: 5000)")
    parser.add_argument("--lan", action="store_true", help="Enable LAN access (bind to 0.0.0.0)")
    parser.add_argument("--pin", type=str, default=None, help="Require PIN for access (e.g. --pin 1234)")
    parser.add_argument("--allow-restart", action="store_true", help="Enable /api/server/restart (security-gated)")
    parser.add_argument(
        "--allow-remote-restart",
        action="store_true",
        help="Allow /api/server/restart from non-local clients (requires restart token)",
    )
    parser.add_argument(
        "--restart-token",
        type=str,
        default=None,
        help="Shared token for remote restart API (required when remote restart is enabled)",
    )
    parser.add_argument(
        "--debug-log",
        choices=("on", "off"),
        help="Structured debug log on/off (same as TAGDB_DEBUG=1/0)",
    )
    parser.add_argument(
        "--debug-log-file",
        help="Debug log file path (same as TAGDB_DEBUG_LOG)",
    )
    parser.add_argument(
        "--debug-log-max-mb",
        type=int,
        help="Debug log max size in MB (same as TAGDB_DEBUG_LOG_MAX_MB)",
    )
    parser.add_argument(
        "--debug-log-backups",
        type=int,
        help="Debug log backup generations (same as TAGDB_DEBUG_LOG_BACKUPS)",
    )
    parser.add_argument(
        "--debug-log-stdout",
        choices=("on", "off"),
        help="Debug log stdout on/off (same as TAGDB_DEBUG_STDOUT=1/0)",
    )
    parser.add_argument(
        "--trusted-proxy-auth",
        action="store_true",
        help="Trust X-Remote-User header from proxy (requires trusted proxy IP)",
    )
    parser.add_argument("--profile", type=str,
                        default=os.environ.get("TAGDB_PROFILE"),
                        help="Activate a named profile from config.json (env: TAGDB_PROFILE)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--mode", choices=("full", "gateway", "server"), default=None,
        help="Server mode: full (default), gateway (lightweight), or server (inference node)",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Disable WebUI routes (API only)",
    )
    parser.add_argument(
        "--safe-mode",
        action="store_true",
        help="Start with repair-safe subsystems only",
    )
    return parser


def apply_debug_env_from_args(args: argparse.Namespace) -> None:
    if args.debug_log is not None:
        os.environ["TAGDB_DEBUG"] = "1" if args.debug_log == "on" else "0"
    if args.debug_log_file is not None:
        os.environ["TAGDB_DEBUG_LOG"] = str(args.debug_log_file)
    if args.debug_log_max_mb is not None:
        os.environ["TAGDB_DEBUG_LOG_MAX_MB"] = str(args.debug_log_max_mb)
    if args.debug_log_backups is not None:
        os.environ["TAGDB_DEBUG_LOG_BACKUPS"] = str(args.debug_log_backups)
    if args.debug_log_stdout is not None:
        os.environ["TAGDB_DEBUG_STDOUT"] = "1" if args.debug_log_stdout == "on" else "0"


def resolve_config_path(cfg_path: str | None) -> str | None:
    """The config file this launch uses, in yu-server's order.

    config.toml comes first, matching `main.rs`'s startup resolution and
    `json_rw.candidate_config_paths()`. Before this, startup read config.json
    while the settings API read config.toml, so one running server could take
    its scan roots from one file and its settings from another -- and
    switching to fast mode moved the startup half to the other file too.
    """
    if cfg_path:
        return cfg_path
    for candidate in ("config.toml", "config.json", "tagdb_config.json"):
        if Path(candidate).exists():
            return candidate
    return None


def resolve_server_bind_host(args: argparse.Namespace, server_cfg: dict[str, Any]) -> str:
    """Resolve only the bind host -- no PIN decryption.

    Extracted out of resolve_server_bind_and_pin() so a caller that only
    needs the host (e.g. scripts/fast_mode.py's firewall-exception
    predicate, which runs before core.paths.init_app_paths()) never risks
    the RuntimeError that config.json's encrypted "enc:" PIN path raises via
    secret_store.decrypt() -> get_data_dir(). Pure extraction: behaviour is
    unchanged, see test_resolve_server_bind_host_matches_bind_and_pin.

    Precedence: explicit CLI flag > config.json > hardcoded default.
    args.host defaults to None so an explicit --host (even one matching the
    hardcoded default) is never silently overridden by config.json.
    """
    effective_host = args.host if args.host is not None else server_cfg.get("host") or "127.0.0.1"
    if args.lan or server_cfg.get("lan", False):
        effective_host = "0.0.0.0"
    return effective_host


def resolve_server_bind_and_pin(args: argparse.Namespace, server_cfg: dict[str, Any]) -> tuple[str, int, str | None, str]:
    effective_pin: str | None = None
    pin_source = "none"

    # args.port defaults to None so an explicit --port (even one matching
    # the hardcoded default) is never silently overridden by config.json.
    effective_port = args.port if args.port is not None else server_cfg.get("port") or 5000

    # PIN resolution: CLI --pin > env YU_TAURI_PIN > config.json
    if args.pin is not None:
        p = str(args.pin).strip()
        effective_pin = p if p else None
        pin_source = "cli"
    elif os.environ.get("YU_TAURI_PIN"):
        effective_pin = os.environ["YU_TAURI_PIN"].strip()
        pin_source = "env"
    else:
        p = str(server_cfg.get("pin") or "").strip()
        if p:
            # Decrypt the encrypted PIN
            from core.settings_core.secret_store import decrypt
            p = decrypt(p)
            effective_pin = p
            pin_source = "config"

    effective_host = resolve_server_bind_host(args, server_cfg)

    return effective_host, int(effective_port), effective_pin, pin_source
