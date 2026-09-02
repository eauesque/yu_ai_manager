"""Sandbox gate and isolation helpers for extension lifecycle.

Contains the sandbox verification pipeline (ManifestAuthority,
CodeVerifier, permission approval), capability token issuance,
process isolation checks, and integrity baseline recording.
"""

import logging

from core.extensions_core.extensions_defs import ExtensionManifest, TrustLevel

from ..sandbox.import_guard import get_import_guard
from ..sandbox.integrity_monitor import get_integrity_monitor
from ..sandbox.isolation_hooks import load_isolated_extension
from ..sandbox.process_isolation import should_isolate as should_process_isolate
from ..token_mgmt.capability_token import get_enforcer
from ..validation.code_verifier import CodeVerifier
from ..validation.extension_permissions import (
    get_granted_permission_set,
    has_user_approval,
)
from ..validation.manifest_authority import ManifestAuthority
from .extensions_core_shim import register_core_shim

logger = logging.getLogger(__name__)


def sandbox_gate(manifest: ExtensionManifest) -> bool:
    """Sandbox gate for non-builtin extensions.

    Runs ManifestAuthority -> CodeVerifier -> permission approval checks.
    Updates manifest.status and returns False if any check fails.
    """
    try:
        from core.services_core.db_api import get_config
        config = get_config()
    except Exception:
        config = {}

    # 1. Manifest Authority
    authority = ManifestAuthority()
    m_verdict = authority.review(manifest)
    if not m_verdict.approved:
        first_issue = m_verdict.issues[0][1] if m_verdict.issues else "Manifest review failed"
        manifest.status = "rejected"
        manifest.status_message = first_issue
        logger.warning(f"{manifest.name}: ManifestAuthority rejected -- {first_issue}")
        return False

    # Log warn-level issues
    for severity, msg in m_verdict.issues:
        if severity == "warn":
            logger.warning(f"{manifest.name}: ManifestAuthority -- {msg}")

    # 2. Code Verifier
    if manifest.directory:
        from core.extensions_core.entry_path import resolve_extension_entry
        try:
            resolve_extension_entry(manifest.directory, manifest.entry)
        except (OSError, ValueError):
            manifest.status = "rejected"
            manifest.status_message = "Unsafe extension entry path"
            return False
        granted = get_granted_permission_set(config, manifest.name)
        # Also treat manifest-declared permissions as granted (for pre-approval analysis)
        if manifest.permissions:
            for decl in manifest.permissions.required:
                granted.add(decl.name)
            for decl in manifest.permissions.optional:
                granted.add(decl.name)

        verifier = CodeVerifier()
        c_verdict = verifier.verify(manifest.directory, manifest.trust_level, granted)
        if not c_verdict.approved:
            first_finding = c_verdict.findings[0] if c_verdict.findings else None
            msg = first_finding.message if first_finding else "Code verification failed"
            manifest.status = "rejected"
            manifest.status_message = msg
            logger.warning(f"{manifest.name}: CodeVerifier rejected -- {msg}")
            return False

        # Log warn/info-level findings
        for finding in c_verdict.findings:
            if finding.severity in ("warn", "info"):
                logger.info(
                    f"{manifest.name}: CodeVerifier {finding.severity} "
                    f"at {finding.file}:{finding.line} -- {finding.message}"
                )

    # 3. Permission check (pending_approval if not approved)
    if not has_user_approval(config, manifest.name):
        manifest.status = "pending_approval"
        manifest.status_message = "Permission approval required"
        logger.info(f"{manifest.name}: pending permission approval (pending_approval)")
        return False

    # All 3 branches approved -> issue Capability Token
    _issue_capability_tokens(manifest, config)

    # Record approval snapshot for cumulative anomaly detection
    _record_approval_snapshot(manifest)

    return True


def _issue_capability_tokens(manifest: ExtensionManifest, config: dict) -> None:
    """Issue capability tokens based on granted permissions."""
    granted = get_granted_permission_set(config, manifest.name)
    if not granted:
        return

    enforcer = get_enforcer()
    tokens = enforcer.issue_tokens(manifest.name, list(granted))
    logger.info(
        f"{manifest.name}: {len(tokens)} Capability Token(s) issued"
    )


def _record_approval_snapshot(manifest: ExtensionManifest) -> None:
    """Record approval-time snapshot for cumulative anomaly detection."""
    if not manifest.directory:
        return
    try:
        from core.extensions_core.audit.extension_audit import save_approval_snapshot
        save_approval_snapshot(manifest.name, manifest.directory)
    except Exception as exc:
        logger.debug("Approval snapshot skipped for %s: %s", manifest.name, exc)


def should_isolate(manifest: ExtensionManifest) -> bool:
    """Determine whether an extension should be process-isolated (Phase 4)."""
    try:
        from core.services_core.db_api import get_config
        config = get_config()
    except Exception:
        return manifest.trust_level != TrustLevel.TRUSTED
    if manifest.trust_level != TrustLevel.TRUSTED:
        return True
    return should_process_isolate(manifest.name, config)


def load_isolated(manifest: ExtensionManifest, registry, blueprints) -> bool:
    """Load an extension as an isolated process (Phase 4)."""
    try:
        from core.services_core.db_api import get_config
        config = get_config()
        return load_isolated_extension(manifest, config, registry, blueprints)
    except Exception as exc:
        logger.error(f"{manifest.name}: Isolated load failed: {exc}")
        manifest.status = "error"
        manifest.status_message = f"Isolated load failed: {exc}"
        return False


def record_integrity_baseline(manifest: ExtensionManifest) -> None:
    """Record file integrity baseline for L1/L2 extensions."""
    try:
        monitor = get_integrity_monitor()
        monitor.record_baseline(manifest.name, manifest.directory)
    except Exception as exc:
        logger.debug(f"{manifest.name}: integrity baseline skipped: {exc}")


def start_runtime_guards() -> None:
    """Install ImportGuard and start IntegrityMonitor periodic checks."""
    try:
        guard = get_import_guard()
        guard.install()
    except Exception as exc:
        logger.warning(f"ImportGuard install failed: {exc}")

    try:
        monitor = get_integrity_monitor()
        monitor.start_periodic_check()
    except Exception as exc:
        logger.warning(f"IntegrityMonitor start failed: {exc}")


def register_core_shim_for(manifest: ExtensionManifest) -> None:
    """Register a virtual package in sys.modules for backward-compatible imports."""
    if manifest.core_shim and manifest.directory:
        register_core_shim(manifest.core_shim, manifest.directory / "core_impl")
