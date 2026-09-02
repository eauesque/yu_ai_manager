"""Runtime audit logic for cumulative extension reviews."""

from __future__ import annotations

import json
import logging

from .extension_audit_snapshot import compute_distance, compute_snapshot, load_approval_snapshot, save_approval_snapshot

logger = logging.getLogger(__name__)

CHANGE_RATE_THRESHOLD = 50.0
NEW_IMPORT_THRESHOLD = 3
FILE_COUNT_MULTIPLIER = 2.0
PERIODIC_AUDIT_DAYS = 30
PERIODIC_AUDIT_DAYS_STATIC = 90


def audit_extension(ext_name: str, audit_type: str = "periodic") -> dict:
    """Run a full audit on an extension."""
    from core.extensions_core.lifecycle.runtime import get_extension_manager

    mgr = get_extension_manager()
    if mgr is None:
        return {"ok": False, "error": "Extension manager not available"}

    ext_dir = mgr.extensions_dir / ext_name
    if not ext_dir.exists():
        ext_dir = mgr.extensions_dir / f"custom-{ext_name}"
        if not ext_dir.exists():
            return {"ok": False, "error": f"Extension '{ext_name}' not found"}

    findings: list[dict] = []
    actions: list[str] = []
    severity = "info"
    baseline = load_approval_snapshot(ext_name)
    current = compute_snapshot(ext_dir)
    distance = compute_distance(baseline, current) if baseline else None

    severity = _check_baseline(ext_name, ext_dir, baseline, distance, current, findings, actions, severity)
    severity = _check_code_verifier(ext_dir, findings, actions, severity)
    severity = _check_integrity(ext_name, findings, actions, severity)
    _apply_actions(ext_name, audit_type, actions)
    _record_audit(ext_name, audit_type, severity, findings, actions, distance)
    _emit_audit(ext_name, audit_type, severity, findings, actions)

    return {
        "ok": True,
        "ext_name": ext_name,
        "audit_type": audit_type,
        "severity": severity,
        "findings": findings,
        "actions": actions,
        "distance": distance,
        "re_approval_required": "re_approval_required" in actions,
    }


def audit_all_extensions(audit_type: str = "periodic") -> dict:
    """Run audit on all custom extensions."""
    from core.extensions_core.lifecycle.runtime import get_extension_manager

    mgr = get_extension_manager()
    if mgr is None:
        return {"ok": False, "error": "Extension manager not available"}

    results = []
    for entry in sorted(mgr.extensions_dir.iterdir()):
        if entry.is_dir() and not entry.name.startswith("builtin-"):
            result = audit_extension(entry.name, audit_type=audit_type)
            if result.get("ok"):
                results.append(result)

    return {
        "ok": True,
        "audit_type": audit_type,
        "audited": len(results),
        "issues_found": sum(1 for result in results if result.get("findings")),
        "revocations": sum(1 for result in results if "token_revocation" in result.get("actions", [])),
        "re_approvals": sum(1 for result in results if result.get("re_approval_required")),
        "results": results,
    }


def _check_baseline(ext_name, ext_dir, baseline, distance, current, findings, actions, severity: str) -> str:
    if distance:
        if distance["change_rate"] >= CHANGE_RATE_THRESHOLD:
            findings.append({"type": "cumulative_change", "severity": "warning", "message": f"Code changed {distance['change_rate']}% from approval baseline", "detail": distance})
            actions.append("re_approval_required")
            severity = "warning"
        if len(distance.get("new_imports", [])) >= NEW_IMPORT_THRESHOLD:
            findings.append({"type": "new_imports", "severity": "warning", "message": f"New imports since approval: {', '.join(distance['new_imports'])}"})
            actions.append("re_approval_required")
            severity = "warning"
        if baseline.get("file_count", 1) > 0 and current.get("file_count", 0) / baseline["file_count"] >= FILE_COUNT_MULTIPLIER:
            findings.append({"type": "file_proliferation", "severity": "warning", "message": f"File count grew from {baseline['file_count']} to {current['file_count']}"})
            actions.append("re_approval_required")
            severity = "warning"
    else:
        findings.append({"type": "no_baseline", "severity": "info", "message": "No approval snapshot found. Creating one now."})
        save_approval_snapshot(ext_name, ext_dir)
    return severity


def _check_code_verifier(ext_dir, findings, actions, severity: str) -> str:
    try:
        from core.extensions_core.validation.code_verifier import CodeVerifier

        verdict = CodeVerifier().verify(ext_dir, trust_level="L2", granted_permissions=set())
        if not verdict.approved:
            for finding in verdict.findings:
                if finding.severity == "block":
                    findings.append({"type": "code_violation", "severity": "critical", "message": finding.message, "file": getattr(finding, "file", "")})
            actions.append("token_revocation")
            return "critical"
    except Exception as exc:
        findings.append({"type": "verification_error", "severity": "info", "message": f"CodeVerifier could not run: {exc}"})
    return severity


def _check_integrity(ext_name: str, findings, actions, severity: str) -> str:
    try:
        from core.extensions_core.sandbox.integrity_monitor import get_integrity_monitor

        tampered = get_integrity_monitor().check_integrity(ext_name)
        if tampered:
            findings.append({"type": "file_tampering", "severity": "critical", "message": f"Tampered files detected: {', '.join(tampered)}"})
            actions.append("token_revocation")
            return "critical"
    except Exception:
        # A failing tamper check must not read as "clean" without a word.
        logger.warning("integrity check for %s did not complete", ext_name, exc_info=True)
    return severity


def _apply_actions(ext_name: str, audit_type: str, actions: list[str]) -> None:
    if "token_revocation" not in actions:
        return
    try:
        from core.extensions_core.token_mgmt.capability_token import get_enforcer

        get_enforcer().revoke_tokens(ext_name, reason=f"audit_{audit_type}")
        logger.warning("[ext-audit] access revoked for %s (audit: %s)", ext_name, audit_type)
    except Exception:
        # The audit decided to revoke. If this threw, the extension still holds
        # its tokens and nothing above here will say so.
        logger.error(
            "[ext-audit] revocation FAILED for %s (audit: %s) -- access is still granted",
            ext_name, audit_type, exc_info=True,
        )


def _record_audit(ext_name: str, audit_type: str, severity: str, findings, actions, distance) -> None:
    try:
        from core.agent_safety.audit_bureau import get_audit_bureau

        get_audit_bureau().record(
            event_type="extension_audit",
            source=f"audit_{audit_type}",
            severity=severity,
            target=ext_name,
            reported_to="all",
            detail=json.dumps({"audit_type": audit_type, "findings_count": len(findings), "actions": actions, "distance": distance}, ensure_ascii=False),
        )
    except Exception:
        logger.warning("[ext-audit] audit result for %s was not recorded", ext_name, exc_info=True)


def _emit_audit(ext_name: str, audit_type: str, severity: str, findings, actions) -> None:
    try:
        from core.event_bus import emit

        emit("audit.extension_audit", {"ext_name": ext_name, "audit_type": audit_type, "severity": severity, "findings_count": len(findings), "actions": actions}, source="audit")
    except Exception:
        logger.warning("[ext-audit] audit event for %s was not emitted", ext_name, exc_info=True)
