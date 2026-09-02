"""Synchronous helpers for agent governance audit routes."""

from __future__ import annotations

import hashlib


def verify_audit_log_chain() -> dict:
    """Verify the hash chain integrity of the audit_log table."""
    from core.agent_safety.audit_bureau_constants import _get_db

    db = _get_db()
    rows = db.execute(
        """SELECT id, timestamp, event_type, source, target,
                  severity, detail_json, prev_hash, entry_hash
           FROM audit_log ORDER BY id ASC"""
    )
    errors = []
    prev_hash = ""
    checked = 0
    for row in rows:
        checked += 1
        rid, ts, ev, src, tgt, sev, dj, ph, eh = row
        if not ph and not eh:
            continue
        raw = f"{ph}{ts}{ev}{src or ''}{tgt or ''}{sev}{dj or ''}"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        if eh != expected:
            errors.append({"id": rid, "reason": "hash_mismatch"})
        if ph != prev_hash:
            errors.append({"id": rid, "reason": "chain_break"})
        prev_hash = eh
    return {"ok": len(errors) == 0, "checked": checked, "errors": errors}
