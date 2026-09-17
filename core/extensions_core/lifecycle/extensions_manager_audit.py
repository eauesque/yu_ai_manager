"""Extension load-time audit checks.

After loading, verifies structural integrity of manifest + module,
and issues warnings or rejections for any problems found.
"""

import logging

logger = logging.getLogger(__name__)

from core.extensions_core.extensions_defs import HOOK_DEFINITIONS, ExtensionManifest
from core.extensions_core.extensions_defs_constants import VALID_CAPABILITIES

# (level, message)  level: "reject" | "warn"
AuditResult = list[tuple[str, str]]


def audit_extension(manifest: ExtensionManifest, module) -> AuditResult:
    """Execute integrity audit on manifest + module."""
    results: AuditResult = []

    # 1. on_scan_file should pair with on_build_sections (warn, not reject —
    # rev2 §4.4 D2: external transformer extensions may legitimately omit it)
    if "on_scan_file" in manifest.hooks and "on_build_sections" not in manifest.hooks:
        results.append((
            "warn",
            "on_scan_file declared without on_build_sections — "
            "scan results will not produce UI sections",
        ))

    # 1b. on_inspect was removed in v4.171 — reject any leftover declaration
    if "on_inspect" in manifest.hooks:
        results.append((
            "reject",
            "on_inspect hook was removed; migrate to on_build_sections "
            "(see EXTENSION_HOOKS_SPEC.md)",
        ))

    # 2. Check if declared hooks have corresponding callables in module
    for hook_name in manifest.hooks:
        if hook_name not in HOOK_DEFINITIONS:
            results.append(("warn", f"unknown hook '{hook_name}' — ignored"))
            continue
        cb = getattr(module, hook_name, None)
        if cb is None or not callable(cb):
            results.append((
                "reject",
                f"hook '{hook_name}' declared but no callable in module",
            ))

    # 3. type=importer but no hooks declared
    if manifest.type == "importer" and not manifest.hooks:
        results.append((
            "warn",
            "type=importer but no hooks declared — extension does nothing at scan time",
        ))

    # 4. type=importer but on_scan_file not declared
    if manifest.type == "importer" and manifest.hooks and "on_scan_file" not in manifest.hooks:
        results.append((
            "warn",
            "type=importer but on_scan_file not declared — cannot parse files",
        ))

    # 5. Blueprint is required
    if not manifest.has_blueprint:
        results.append((
            "reject",
            "has_blueprint is required — all extensions must provide a blueprint",
        ))

    # 6. has_blueprint=true but no get_blueprint() function
    if manifest.has_blueprint:
        get_bp = getattr(module, "get_blueprint", None)
        if get_bp is None or not callable(get_bp):
            results.append((
                "reject",
                "has_blueprint=true but no get_blueprint() function",
            ))

    # 7. blueprint_prefix does not start with /
    if manifest.has_blueprint and manifest.blueprint_prefix and not manifest.blueprint_prefix.startswith("/"):
        results.append((
            "warn",
            f"blueprint_prefix '{manifest.blueprint_prefix}' should start with '/'",
        ))

    # 8. Validate capabilities (unknown capabilities are warned)
    caps = getattr(manifest, "capabilities", None)
    if caps and isinstance(caps, list):
        for cap in caps:
            if cap not in VALID_CAPABILITIES:
                results.append((
                    "warn",
                    f"unknown capability '{cap}' -- "
                    f"valid: {', '.join(sorted(VALID_CAPABILITIES))}",
                ))

    return results


def apply_audit_results(
    manifest: ExtensionManifest, results: AuditResult
) -> bool:
    """Log audit results and update manifest.status if rejected.

    Returns:
        True: can proceed (warnings only or no issues)
        False: rejected (one or more reject findings)
    """
    rejected = False
    for level, message in results:
        if level == "reject":
            logger.error(f"{manifest.name}: rejected -- {message}")
            rejected = True
        else:
            logger.warning(f"{manifest.name}: {message}")

    if rejected:
        # Use first reject message as status_message
        first_reject = next(msg for lvl, msg in results if lvl == "reject")
        manifest.status = "rejected"
        manifest.status_message = first_reject

    return not rejected
