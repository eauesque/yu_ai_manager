"""Restart-related startup config for Quart app."""

import argparse
import os
import sys
from typing import Any

from quart import Quart


def truthy(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on", "enabled")


def apply_restart_config(app: Quart, args: argparse.Namespace, server_cfg: dict[str, Any]) -> None:
    app.config["RESTART_EXEC_ARGS"] = [sys.executable, *sys.argv]

    env_restart = truthy(os.environ.get("TAGDB_ALLOW_RESTART"))
    cfg_restart = truthy(server_cfg.get("allow_restart", ""))
    app.config["RESTART_ENV_ENABLED"] = bool(args.allow_restart or env_restart or cfg_restart)
    if args.allow_restart:
        app.config["RESTART_ENABLE_SOURCE"] = "cli"
    elif env_restart:
        app.config["RESTART_ENABLE_SOURCE"] = "env"
    elif cfg_restart:
        app.config["RESTART_ENABLE_SOURCE"] = "config"
    else:
        app.config["RESTART_ENABLE_SOURCE"] = "none"

    env_remote_restart = truthy(os.environ.get("TAGDB_ALLOW_REMOTE_RESTART"))
    cfg_remote_restart = truthy(server_cfg.get("allow_remote_restart", ""))
    app.config["RESTART_REMOTE_ALLOWED"] = bool(
        args.allow_remote_restart or env_remote_restart or cfg_remote_restart
    )
    if args.allow_remote_restart:
        app.config["RESTART_REMOTE_SOURCE"] = "cli"
    elif env_remote_restart:
        app.config["RESTART_REMOTE_SOURCE"] = "env"
    elif cfg_remote_restart:
        app.config["RESTART_REMOTE_SOURCE"] = "config"
    else:
        app.config["RESTART_REMOTE_SOURCE"] = "none"

    restart_token = None
    restart_token_source = "none"
    if args.restart_token is not None:
        restart_token = str(args.restart_token).strip() or None
        restart_token_source = "cli"
    else:
        env_token = (os.environ.get("TAGDB_RESTART_TOKEN") or "").strip()
        if env_token:
            restart_token = env_token
            restart_token_source = "env"
        else:
            cfg_token = str(server_cfg.get("restart_token") or "").strip()
            if cfg_token:
                restart_token = cfg_token
                restart_token_source = "config"
    app.config["RESTART_REMOTE_TOKEN"] = restart_token
    app.config["RESTART_REMOTE_TOKEN_SOURCE"] = restart_token_source
