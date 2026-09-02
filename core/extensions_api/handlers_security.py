"""Security-related handlers: permissions, code scan, tokens, integrity, isolation."""

import logging

from quart import request

from core.extensions_core.lifecycle.runtime import get_extension_manager
from core.infra_core.api_errors import api_error, api_result
from core.infra_core.api_request import require_json_dict


def get_extension_permissions(name):
    """Return permission info and approval state for an extension."""
    mgr = get_extension_manager()
    manifest = mgr.manifests.get(name)
    if manifest is None:
        return api_error(f"Extension '{name}' not found", 404)

    from core.extensions_core.validation.extension_permissions import (
        has_user_approval,
        load_extension_permissions,
    )

    try:
        from core.services_core.db_api import get_config
        config = get_config()
    except Exception:
        config = {}

    trust_level = str(manifest.trust_level) if manifest.trust_level else "trusted"
    approved = has_user_approval(config, name)

    perms_data = {"required": [], "optional": []}
    if manifest.permissions:
        perms_data["required"] = [
            {"name": d.name, "reason": d.reason} for d in manifest.permissions.required
        ]
        perms_data["optional"] = [
            {"name": d.name, "reason": d.reason} for d in manifest.permissions.optional
        ]

    all_perms = load_extension_permissions(config)
    granted_info = None
    if name in all_perms:
        gp = all_perms[name]
        granted_info = {
            "granted": gp.granted,
            "denied": gp.denied,
            "granted_at": gp.granted_at,
            "auto_approved": gp.auto_approved,
        }

    return api_result({
        "name": name,
        "trust_level": trust_level,
        "approved": approved,
        "permissions": perms_data,
        "granted": granted_info,
    }, 200)


async def approve_extension_permissions(name):
    """Approve or revoke extension permissions."""
    mgr = get_extension_manager()
    manifest = mgr.manifests.get(name)
    if manifest is None:
        return api_error(f"Extension '{name}' not found", 404)

    from core.extensions_core.validation.extension_permissions import (
        approve_permissions,
        revoke_permissions,
    )

    try:
        from core.services_core.db_api import get_config
        config = get_config()
    except Exception:
        config = {}

    data, err = await require_json_dict(request)
    if err:
        return api_result(err[0], err[1])

    action = data.get("action", "approve")
    if action not in ("approve", "revoke"):
        return api_error(f"invalid action: {action!r}", 400)

    trust_level = str(manifest.trust_level) if manifest.trust_level else "trusted"

    if action == "revoke":
        revoke_permissions(config, name)
        if not _save_config(config):
            return api_error("設定の保存に失敗しました", 500)
        return api_result({"name": name, "action": "revoked"}, 200)

    # approve
    granted_perms = data.get("granted", [])
    denied_perms = data.get("denied", [])

    if not isinstance(granted_perms, list):
        return api_error("granted must be a list", 400)
    if not isinstance(denied_perms, list):
        return api_error("denied must be a list", 400)

    approve_permissions(config, name, trust_level, granted_perms, denied_perms)
    if not _save_config(config):
        return api_error("設定の保存に失敗しました", 500)

    return api_result({
        "name": name,
        "action": "approved",
        "granted": granted_perms,
        "denied": denied_perms,
    }, 200)


def scan_extension_code(name):
    """Return static analysis results for extension code."""
    mgr = get_extension_manager()
    manifest = mgr.manifests.get(name)
    if manifest is None:
        return api_error(f"Extension '{name}' not found", 404)

    from core.extensions_core.validation.code_verifier import CodeVerifier
    from core.extensions_core.validation.extension_permissions import get_granted_permission_set
    from core.extensions_core.validation.manifest_authority import ManifestAuthority

    try:
        from core.services_core.db_api import get_config
        config = get_config()
    except Exception:
        config = {}

    trust_level = str(manifest.trust_level) if manifest.trust_level else "trusted"

    # ManifestAuthority review
    authority = ManifestAuthority()
    m_verdict = authority.review(manifest)

    # CodeVerifier analysis
    c_verdict = None
    if manifest.directory:
        granted = get_granted_permission_set(config, name)
        if manifest.permissions:
            for d in manifest.permissions.required:
                granted.add(d.name)
            for d in manifest.permissions.optional:
                granted.add(d.name)
        verifier = CodeVerifier()
        c_verdict = verifier.verify(manifest.directory, trust_level, granted)

    return api_result({
        "name": name,
        "trust_level": trust_level,
        "manifest_review": {
            "approved": m_verdict.approved,
            "issues": [{"severity": s, "message": m} for s, m in m_verdict.issues],
        },
        "code_scan": {
            "approved": c_verdict.approved if c_verdict else True,
            "findings": [
                {
                    "file": f.file,
                    "line": f.line,
                    "severity": f.severity,
                    "message": f.message,
                }
                for f in (c_verdict.findings if c_verdict else [])
            ],
        } if c_verdict else None,
    }, 200)


def rescan_extension(name):
    """Re-scan extension code (delegates to scan_extension_code)."""
    return scan_extension_code(name)


def get_extension_tokens(name):
    """Return capability token issuance status for an extension."""
    mgr = get_extension_manager()
    manifest = mgr.manifests.get(name)
    if manifest is None:
        return api_error(f"Extension '{name}' not found", 404)

    from core.extensions_core.token_mgmt.capability_token import get_enforcer
    enforcer = get_enforcer()
    summary = enforcer.token_summary(name)

    return api_result({
        "name": name,
        "token_count": len(summary),
        "tokens": summary,
    }, 200)


def get_extension_integrity(name):
    """Return file integrity status for an extension."""
    mgr = get_extension_manager()
    manifest = mgr.manifests.get(name)
    if manifest is None:
        return api_error(f"Extension '{name}' not found", 404)

    from core.extensions_core.sandbox.integrity_monitor import get_integrity_monitor
    monitor = get_integrity_monitor()
    status = monitor.get_status(name)

    # Also include RevocationTracker info
    revocation_info = {}
    try:
        from core.extensions_core.token_mgmt.token_revocation import get_revocation_tracker
        tracker = get_revocation_tracker()
        revocation_info = {
            "denial_count": tracker.get_denial_count(name),
            "last_access": tracker.get_last_access(name),
        }
    except Exception:
        logging.getLogger(__name__).warning(
            "extension security handler step failed", exc_info=True
        )

    # ImportGuard denial count
    import_guard_info = {}
    try:
        from core.extensions_core.sandbox.import_guard import get_import_guard
        guard = get_import_guard()
        import_guard_info = {
            "import_denial_count": guard.get_denial_count(name),
        }
    except Exception:
        logging.getLogger(__name__).warning(
            "extension security handler step failed", exc_info=True
        )

    return api_result({
        "name": name,
        "integrity": status,
        "revocation": revocation_info,
        "import_guard": import_guard_info,
    }, 200)


def get_isolation_status():
    """Return process isolation status."""
    from core.extensions_core.sandbox.process_isolation import (
        get_isolation_status as _get_status,
    )
    from core.extensions_core.sandbox.process_isolation import (
        is_isolation_available,
    )

    return api_result({
        "available": is_isolation_available(),
        "processes": _get_status(),
    }, 200)


def get_os_isolation_status():
    """Return OS-level isolation status (Phase D)."""
    from core.extensions_core.sandbox.os_isolation import (
        get_os_isolation_info,
        load_os_isolation_config,
    )
    from core.extensions_core.sandbox.process_isolation import (
        get_isolation_status as _get_process_status,
    )
    from core.services_core.db_api import get_config

    config = get_config()
    os_config = load_os_isolation_config(config)

    return api_result({
        "os_isolation": get_os_isolation_info(),
        "config": {
            "enabled": os_config.enabled,
            "apparmor": os_config.apparmor,
            "macos_sandbox_exec": os_config.macos_sandbox_exec,
            "macos_user_isolation": os_config.macos_user_isolation,
            "windows_restricted_token": os_config.windows_restricted_token,
            "windows_job_object": os_config.windows_job_object,
        },
        "processes": _get_process_status(),
    }, 200)


def _save_config(config: dict) -> bool:
    """Persist config dict to file. Returns False on failure."""
    try:
        from core.configuration.api import save_config_json
        save_config_json(config)
        return True
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("設定の保存に失敗しました: %s", exc)
        return False
