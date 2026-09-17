"""ExtensionImportGuard: Runtime import monitoring via sys.meta_path.

Complements the "judicial" function of the separation-of-powers Phase C.
Supplements static analysis (CodeVerifier) with dynamic import monitoring at runtime.

L0 (TRUSTED/builtin) is not registered, so it is fully bypassed.
"""

from __future__ import annotations

import contextlib
import logging
import sys
import threading

logger = logging.getLogger(__name__)


# Thread-local: prevent recursive import guard invocations
_guard_local = threading.local()


class ExtensionImportGuard:
    """Runtime import monitoring via sys.meta_path.

    Inspects imports of modules registered in IMPORT_PERMISSION_MAP
    and checks whether the calling extension has the required permissions.
    """

    def __init__(self) -> None:
        # ext_name -> module_name (ext_xxx format)
        self._ext_modules: dict[str, str] = {}
        # ext_name -> granted permissions set
        self._ext_permissions: dict[str, set[str]] = {}
        # ext_name -> denial count
        self._denial_counts: dict[str, int] = {}
        self._installed = False

    def register_extension(
        self,
        ext_name: str,
        module_name: str,
        granted_permissions: set[str],
    ) -> None:
        """Register an extension for import monitoring.

        Do not register L0 (builtin) extensions.

        Args:
            ext_name: Extension name
            module_name: Extension module name (ext_xxx format)
            granted_permissions: Set of approved permissions
        """
        self._ext_modules[ext_name] = module_name
        self._ext_permissions[ext_name] = set(granted_permissions)
        logger.debug(
            "ImportGuard: registered %s (module=%s, perms=%s)",
            ext_name,
            module_name,
            granted_permissions,
        )

    def unregister_extension(self, ext_name: str) -> None:
        """Unregister an extension from import monitoring."""
        self._ext_modules.pop(ext_name, None)
        self._ext_permissions.pop(ext_name, None)
        self._denial_counts.pop(ext_name, None)

    def find_module(self, fullname: str, path=None):
        """sys.meta_path protocol: called on import.

        Inspects imports of monitored modules and raises ImportError if
        permissions are insufficient. Returns None to delegate to the next finder.
        """
        # 1. Prevent re-entry (lazy import of IMPORT_PERMISSION_MAP can cause recursion)
        if getattr(_guard_local, "_in_guard", False):
            return None
        _guard_local._in_guard = True

        try:
            from core.extensions_core.validation.code_verifier import (
                IMPORT_PERMISSION_MAP,
            )
        except Exception:
            _guard_local._in_guard = False
            return None

        # 2. Pass through modules not in IMPORT_PERMISSION_MAP (O(1))
        required_perm = self._match_permission(fullname, IMPORT_PERMISSION_MAP)
        if required_perm is None:
            _guard_local._in_guard = False
            return None

        try:
            # 3. Identify the calling extension via stack frames
            caller_ext = self._identify_caller()
            if caller_ext is None:
                # Import from non-extension code -> allow
                return None

            # 4. VIOLATION:* is always blocked
            if required_perm.startswith("VIOLATION:"):
                self._record_denial(caller_ext)
                raise ImportError(
                    f"[Sandbox] Extension '{caller_ext}' は "
                    f"'{fullname}' の import が禁止されています "
                    f"(violation: {required_perm})"
                )

            # 5. Permission check
            granted = self._ext_permissions.get(caller_ext, set())
            if required_perm not in granted:
                self._record_denial(caller_ext)
                raise ImportError(
                    f"[Sandbox] Extension '{caller_ext}' は "
                    f"'{fullname}' の import に '{required_perm}' "
                    f"権限が必要ですが付与されていません"
                )

            # Permission granted -> return None to delegate to normal import
            return None
        finally:
            _guard_local._in_guard = False

    def _match_permission(
        self, fullname: str, permission_map: dict[str, str]
    ) -> str | None:
        """Check if a module name matches an entry in IMPORT_PERMISSION_MAP."""
        # Exact match
        if fullname in permission_map:
            return permission_map[fullname]
        # Prefix match (e.g. urllib.request -> urllib.request)
        for pattern, perm in permission_map.items():
            if fullname.startswith(pattern + "."):
                return perm
        return None

    def _identify_caller(self) -> str | None:
        """Identify the calling extension by inspecting stack frames.

        Detection is based on ext_* module name prefixes.
        Stops inspection when a core.* frame is reached (prevents false positives via core_shim).
        """
        frame = sys._getframe(2)  # find_module → _identify_caller → skip 2

        while frame is not None:
            module_name = frame.f_globals.get("__name__", "")

            # Reached core.* frame -> not an import from an extension
            if module_name.startswith("core."):
                return None

            # Detect import from ext_* module
            if module_name.startswith("ext_"):
                # Exact match or submodule match
                for ext_name, ext_mod in self._ext_modules.items():
                    if module_name == ext_mod or module_name.startswith(ext_mod + "."):
                        return ext_name

            frame = frame.f_back

        return None

    def _record_denial(self, ext_name: str) -> None:
        """Record a denial. Coordinates with RevocationTracker."""
        count = self._denial_counts.get(ext_name, 0) + 1
        self._denial_counts[ext_name] = count
        logger.warning(
            "ImportGuard: import denied for '%s' (total denials: %d)",
            ext_name,
            count,
        )

        # Notify RevocationTracker
        try:
            from core.extensions_core.token_mgmt.token_revocation import (
                get_revocation_tracker,
            )
            tracker = get_revocation_tracker()
            should_revoke, reason = tracker.record_denial(ext_name)
            if should_revoke:
                from core.extensions_core.token_mgmt.capability_token import (
                    get_enforcer,
                )
                enforcer = get_enforcer()
                enforcer.revoke_tokens(ext_name)
                logger.warning(
                    "ImportGuard: Token revoked for '%s' (%s)",
                    ext_name,
                    reason,
                )
        except Exception as exc:
            logger.debug("ImportGuard: revocation check failed: %s", exc)

    def get_denial_count(self, ext_name: str) -> int:
        """Return the denial count for an extension."""
        return self._denial_counts.get(ext_name, 0)

    def install(self) -> None:
        """Register self on sys.meta_path."""
        if self._installed:
            return
        sys.meta_path.insert(0, self)
        self._installed = True
        logger.info("ImportGuard: installed on sys.meta_path")

    def uninstall(self) -> None:
        """Remove self from sys.meta_path."""
        if not self._installed:
            return
        with contextlib.suppress(ValueError):
            sys.meta_path.remove(self)
        self._installed = False
        logger.info("ImportGuard: uninstalled from sys.meta_path")


# --- Singleton ---

_guard: ExtensionImportGuard | None = None


def get_import_guard() -> ExtensionImportGuard:
    """Return the singleton ExtensionImportGuard instance."""
    global _guard
    if _guard is None:
        _guard = ExtensionImportGuard()
    return _guard


def reset_import_guard() -> None:
    """For testing: reset the singleton."""
    global _guard
    if _guard is not None:
        _guard.uninstall()
    _guard = None
