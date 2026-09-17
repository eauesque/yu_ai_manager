"""Built-in scheduled jobs -- extension audit operations.

Implements the three-tier audit model from MCP_EXTENSION_AUTHORING_SPEC.md:
- Type II: Periodic audit (scheduled, systematic)
- Type III: Surprise inspection (random, unpredictable)
"""

import logging
import secrets

logger = logging.getLogger(__name__)


def _with_db_cleanup(func):
    """Decorator: ensure thread-local DB connections are closed after job."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            from core.services_core.db_state import close_thread_connections
            close_thread_connections()
    wrapper.__name__ = func.__name__
    wrapper.__qualname__ = func.__qualname__
    return wrapper


@_with_db_cleanup
def extension_audit_periodic():
    """Type II: Periodic audit — systematic check of all custom extensions.

    Runs all audit checks:
    - Approval snapshot comparison (cumulative distance)
    - CodeVerifier re-scan with latest rules
    - File integrity verification
    - Audit log chain hash validation

    Results recorded to AuditBureau + SSE notification.
    """
    try:
        from core.extensions_core.audit.extension_audit import audit_all_extensions
        result = audit_all_extensions(audit_type="periodic")
        if result.get("ok"):
            logger.info(
                "[ext-audit] Periodic audit complete: %d audited, %d issues, %d revocations",
                result.get("audited", 0),
                result.get("issues_found", 0),
                result.get("revocations", 0),
            )
        else:
            logger.warning("[ext-audit] Periodic audit failed: %s", result.get("error"))
    except Exception as exc:
        logger.error("[ext-audit] Periodic audit error: %s", exc)


@_with_db_cleanup
def extension_audit_surprise():
    """Type III: Surprise inspection — random, unpredictable deep audit.

    Randomly selects ONE custom extension and runs a full audit.
    The randomness makes it impossible to predict which extension
    will be inspected and when, creating structural deterrence.

    Scheduling: runs at random intervals via APScheduler interval trigger.
    Each execution picks a random extension, so over time all extensions
    are covered with unpredictable timing.
    """
    try:
        from core.extensions_core.lifecycle.runtime import get_extension_manager
        mgr = get_extension_manager()
        if mgr is None:
            return

        # Collect non-builtin extensions
        candidates = []
        for entry in mgr.extensions_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith("builtin-"):
                candidates.append(entry.name)

        if not candidates:
            return

        # `secrets`, not `random`: this is the "surprise inspection" target, and
        # this project's own governance rule is that inspection timing must not
        # be announced. A predictable PRNG lets whoever can observe enough of
        # its output work out which extension is next -- which is the same
        # thing as announcing it. The cost of the stronger generator here is
        # one draw per audit run.
        target = secrets.choice(candidates)
        logger.info("[ext-audit] Surprise inspection target: %s", target)

        from core.extensions_core.audit.extension_audit import audit_extension
        result = audit_extension(target, audit_type="surprise")

        if result.get("ok"):
            sev = result.get("severity", "info")
            if sev in ("warning", "critical"):
                logger.warning(
                    "[ext-audit] Surprise inspection found issues in %s: %s",
                    target, result.get("findings"),
                )
            else:
                # No issues found — record only, don't notify extension
                logger.info("[ext-audit] Surprise inspection: %s — no issues", target)
    except Exception as exc:
        logger.error("[ext-audit] Surprise inspection error: %s", exc)
