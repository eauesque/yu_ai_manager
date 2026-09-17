"""Validation helpers for extension definitions."""

from collections.abc import Sequence

from core.extensions_core.extensions_defs_constants import META_ARGS
from core.extensions_core.extensions_defs_models import ExtensionManifest


def validate_cli_gui_parity(manifest: ExtensionManifest, cli_args: Sequence[str]) -> list[str]:
    errors = []
    effective_cli = set()
    for arg in cli_args:
        if (arg.startswith("--") or (arg.startswith("-") and len(arg) == 2)) and arg not in META_ARGS:
            effective_cli.add(arg)

    schema_flags = set()
    for cf in manifest.config_schema.values():
        if cf.cli_flag:
            schema_flags.add(cf.cli_flag)

    cli_only = effective_cli - schema_flags
    schema_only = schema_flags - effective_cli

    if cli_only:
        errors.append(f"CLI args not defined in config_schema: {', '.join(sorted(cli_only))}")
    if schema_only:
        errors.append(f"config_schema not implemented in CLI args: {', '.join(sorted(schema_only))}")
    return errors
