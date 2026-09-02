"""Extension module loading helpers."""

import importlib.util
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from core.extensions_core.extensions_defs import ExtensionManifest, TrustLevel

from ..sandbox.import_guard import get_import_guard
from ..token_mgmt.capability_token import get_enforcer


def _validate_entry_path(manifest: ExtensionManifest) -> Path | None:
    if not manifest.entry or not manifest.directory:
        manifest.status = "rejected"
        manifest.status_message = "entry または directory が未指定"
        return None

    from core.extensions_core.entry_path import resolve_extension_entry
    try:
        entry_path = resolve_extension_entry(manifest.directory, manifest.entry)
    except (OSError, ValueError):
        manifest.status = "rejected"
        manifest.status_message = f"安全なエントリファイルが見つかりません: {manifest.entry}"
        logger.error(f"{manifest.name}: {manifest.status_message}")
        return None
    return entry_path


def _validate_python_syntax(manifest: ExtensionManifest, entry_path: Path) -> bool:
    import ast

    try:
        source = entry_path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(entry_path))
        return True
    except SyntaxError as e:
        manifest.status = "rejected"
        manifest.status_message = f"構文エラー ({manifest.entry} 行{e.lineno}): {e.msg}"
        logger.error(f"{manifest.name}: {manifest.status_message}")
        return False
    except Exception as e:
        manifest.status = "rejected"
        manifest.status_message = f"ファイル読み取りエラー: {e}"
        logger.error(f"{manifest.name}: {manifest.status_message}")
        return False


def load_extension_module(manifest: ExtensionManifest):
    """Load extension entry module with syntax validation."""
    if manifest.trust_level != TrustLevel.TRUSTED:
        # Keep the guard here as well as lifecycle orchestration: direct callers
        # must never import unverified extension code.
        from .lifecycle_sandbox import sandbox_gate, should_isolate
        if not sandbox_gate(manifest):
            return None
        if should_isolate(manifest):
            manifest.status = "pending_isolation"
            manifest.status_message = "Extension must be loaded in an isolated process"
            return None
    entry_path = _validate_entry_path(manifest)
    if entry_path is None:
        return None
    if not _validate_python_syntax(manifest, entry_path):
        return None

    module_name = f"ext_{manifest.name.replace('-', '_')}"
    try:
        # Treat extension directory as a package to enable relative imports
        ext_dir = manifest.directory
        spec = importlib.util.spec_from_file_location(
            module_name,
            str(entry_path),
            submodule_search_locations=[str(ext_dir)],
        )
        if spec is None or spec.loader is None:
            manifest.status = "rejected"
            manifest.status_message = "モジュールspecの生成に失敗"
            return None
        module = importlib.util.module_from_spec(spec)
        # Set __package__ to enable from .xxx import yyy
        module.__package__ = module_name
        module.__path__ = [str(ext_dir)]
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        manifest.status = "loaded"
        manifest.status_message = ""

        # Inject Capability Token info into L1/L2 extensions
        _inject_sandbox_context(module, manifest)

        # Register L1/L2 extensions with ImportGuard
        _register_import_guard(manifest, module_name)

        return module
    except Exception as e:
        manifest.status = "error"
        manifest.status_message = f"読み込みエラー: {e}"
        logger.error(f"{manifest.name}: {manifest.status_message}", exc_info=True)
        sys.modules.pop(module_name, None)
        return None


def _register_import_guard(manifest: ExtensionManifest, module_name: str) -> None:
    """Register L1/L2 extension with ImportGuard."""
    if manifest.trust_level == TrustLevel.TRUSTED:
        return

    try:
        guard = get_import_guard()
        enforcer = get_enforcer()
        tokens = enforcer.get_tokens(manifest.name)
        granted = set(tokens.keys()) if tokens else set()
        guard.register_extension(manifest.name, module_name, granted)
    except Exception as exc:
        logger.debug(
            f"{manifest.name}: import guard registration skipped: {exc}"
        )


def _inject_sandbox_context(module, manifest: ExtensionManifest) -> None:
    """Inject sandbox context into L1/L2 extensions.

    module._capability_tokens: dict of issued tokens
    module._sandbox_caller: caller name used by ServiceRegistry.get()
    """
    if manifest.trust_level == TrustLevel.TRUSTED:
        return

    try:
        enforcer = get_enforcer()
        tokens = enforcer.get_tokens(manifest.name)
        module._capability_tokens = tokens
        module._sandbox_caller = manifest.name
    except Exception as exc:
        logger.debug(
            f"{manifest.name}: sandbox context injection skipped: {exc}"
        )
