"""Config read/write entrypoints used by core.config."""

import contextlib
import json
import logging
import os
import shutil
import tempfile
import tomllib
from pathlib import Path

from .json_repair import repair_json_backslashes

logger = logging.getLogger(__name__)


def _restrict_file_permissions(filepath: str) -> None:
    """Restrict file to owner-only access (best-effort).

    Unix: chmod 600.  Windows: no-op (NTFS inherits user ACL from parent).
    Previous icacls /inheritance:r approach broke os.replace() by removing
    the delete permission needed for atomic config saves.
    """
    if os.name != "nt":
        with contextlib.suppress(OSError):
            os.chmod(filepath, 0o600)


_config_path_override: str | None = None


def set_default_config_path(path: str | None) -> None:
    """Process-wide override for the default config path.

    Call once, as early as possible in startup -- before any load/save that
    omits an explicit path runs. A plain module global, not a Quart
    contextvar/app.config entry: bootstrap-time config reads and writes
    (profile/secret/wd-tagger migrations, extension registration, background
    watcher threads) all run outside any Quart app or request context, so
    resolving via current_app alone left every one of them defaulting to the
    literal CWD-relative "config.json" regardless of `--config` -- confirmed
    live: even after CONFIG_PATH-aware resolution was added, a parity-harness
    run with an isolated --config still touched the real repo config.json
    because these startup-path writers ran before any app context existed
    (2026-08-30).
    """
    global _config_path_override
    _config_path_override = path


_STANDARD_CONFIG_NAMES = ("config.toml", "config.json", "tagdb_config.json")


def _first_existing_standard_config() -> str | None:
    """The config file a read would land on with nothing else configured.

    Deliberately does not call candidate_config_paths(): that function asks
    _default_config_path(), and asking it back would recurse.
    """
    for name in _STANDARD_CONFIG_NAMES:
        if Path(name).exists():
            return name
    return None


def _default_config_path() -> str:
    """Resolve the config path the running process was started with.

    Checks the process-wide override set via set_default_config_path() first
    (covers bootstrap code and background threads), then falls back to the
    active Quart app's CONFIG_PATH (belt-and-suspenders for any caller that
    runs inside a request/app context before the override was ever set),
    then the file a read would actually land on -- config.toml before
    config.json -- so a caller with neither (CLI tools, tests without an app)
    writes to the file everything else reads. Returning the bare literal
    "config.json" there made those writers silently update a file that a
    read, stopping at config.toml, never reaches.
    """
    if _config_path_override:
        return _config_path_override
    try:
        from quart import current_app

        configured = current_app.config.get("CONFIG_PATH")
    except Exception:
        configured = None
    return configured or _first_existing_standard_config() or "config.json"


def is_toml_path(path: str | Path) -> bool:
    """True when the path names the TOML config format.

    Mirrors yu-server's `config_io::is_toml`. The format follows the file:
    writing JSON into a config.toml replaces the operator's file with
    something neither server can read back as TOML.
    """
    return Path(path).suffix == ".toml"


def _serialize_config(path: Path, config: dict) -> str:
    """Serialize according to the format the path names.

    Mirrors yu-server's `config_io::serialize`, including its refusal: TOML
    has no null, so a value that cannot be represented must raise rather than
    be dropped. A silent drop loses settings, and the loss is invisible until
    something reads the key back and finds it missing.
    """
    if is_toml_path(path):
        import tomli_w  # noqa: PLC0415 -- only needed on the TOML path

        try:
            return tomli_w.dumps(config)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"config is not representable as TOML: {exc}") from exc
    return json.dumps(config, indent=2, ensure_ascii=False)


def save_config_json(config: dict, config_path: str | None = None) -> None:
    """Atomically write the config, in the format its path names.

    Uses tempfile + os.replace() to prevent file loss on crash.
    Atomic rename is guaranteed on NTFS / ext4 / APFS.

    The format follows the destination, not the function's name: a read stops
    at the first existing candidate (config.toml before config.json), so a
    writer that always emitted JSON to config.json made every saved setting
    land in a file nothing reads. yu-server has always followed the path
    (`config_io::write`); this is the Python side catching up.
    """
    path = Path(config_path or _default_config_path()).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Serialize before creating the temp file: an unrepresentable value must
    # not leave a stray .tmp behind, and must never truncate the real file.
    text = _serialize_config(path, config)

    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=".config_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
        # config.json may contain API key hashes etc.,
        # so restrict file permissions
        _restrict_file_permissions(str(path))
    except BaseException:
        # Delete temporary file on write failure
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def candidate_config_paths(config_path: str | None = None) -> list[str]:
    """Every path a read considers, in the order it considers them.

    Kept as one list so a caller that wants to *report* which file is in
    effect cannot disagree with the loader about which file that is.
    """
    paths_to_try = []
    if config_path:
        paths_to_try.append(config_path)
    else:
        default = _default_config_path()
        if default != "config.json":
            paths_to_try.append(default)
        paths_to_try.append("config.toml")
    paths_to_try.extend(["config.json", "tagdb_config.json"])
    return paths_to_try


def effective_config_path(config_path: str | None = None) -> str | None:
    """The file a read actually returns, or None when none of them exist."""
    for p in candidate_config_paths(config_path):
        if Path(p).exists():
            return p
    return None


def shadowed_config_paths(config_path: str | None = None) -> list[str]:
    """Existing config files a read will never reach.

    A write goes to `_default_config_path()` while a read stops at the first
    existing candidate, so a config.toml sitting next to a config.json makes
    every saved setting invisible. Naming the ignored files is the difference
    between "the setting did nothing" and "the setting went somewhere nothing
    reads".
    """
    candidates = candidate_config_paths(config_path)
    existing = [p for p in candidates if Path(p).exists()]
    return existing[1:]


def load_config_json(config_path: str | None = None) -> dict:
    paths_to_try = candidate_config_paths(config_path)

    for p in paths_to_try:
        if Path(p).exists():
            if p.endswith(".toml"):
                try:
                    return tomllib.loads(Path(p).read_text(encoding="utf-8"))
                except Exception as e:
                    logger.error(f"{p} TOML parse failed: {e}")
                    return {"scan_roots": []}
            raw = Path(p).read_text(encoding="utf-8")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                try:
                    repaired = repair_json_backslashes(raw)
                    data = json.loads(repaired)
                    logger.warning(f"{p} had invalid escapes -- auto-repaired and saved")
                    save_config_json(data, p)
                    return data
                except Exception as e2:
                    logger.error(f"{p} repair failed: {e2}")
                    shutil.copy2(p, p + ".broken")
                    logger.info(f"Broken config backed up to {p}.broken")
                    return {"scan_roots": []}
    return {"scan_roots": []}
