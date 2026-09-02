"""Audit Bureau query operations -- report generation, search, and status.

Split from audit_bureau.py to keep file sizes manageable.
Contains: generate_report, search_log, acknowledge, status methods.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Import shared constants and helpers
from core.agent_safety.audit_bureau_constants import (
    EVENT_REPORT,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    _emit_sse,
    _get_db,
    _now_iso,
)


class AuditBureauQueriesMixin:
    """Mixin providing query/report methods for AuditBureau.

    Expects the host class to have:
      - _report_interval: int (seconds)
      - _last_report_time: float
      - _enabled: bool
      - record(): method for writing audit entries
    """

    def generate_report(self, hours: int = 24) -> dict:
        """Generate a periodic summary report."""
        try:
            db = _get_db()
            # Use SQLite's datetime('now', ...) so the window is computed entirely
            # inside the DB engine, avoiding Python ISO string formatting issues
            # (e.g. +00:00 timezone suffix confusion with older SQLite builds).
            window = f"-{hours} hours"

            # Count by severity
            rows = db.execute(
                """SELECT severity, COUNT(*) FROM audit_log
                   WHERE timestamp > datetime('now', ?)
                   GROUP BY severity""",
                (window,),
            )
            by_severity = {row[0]: row[1] for row in rows}

            # Count by event_type
            rows = db.execute(
                """SELECT event_type, COUNT(*) FROM audit_log
                   WHERE timestamp > datetime('now', ?)
                   GROUP BY event_type""",
                (window,),
            )
            by_type = {row[0]: row[1] for row in rows}

            total = sum(by_severity.values())
            unacknowledged = db.execute(
                """SELECT COUNT(*) FROM audit_log
                   WHERE user_acknowledged = 0
                   AND timestamp > datetime('now', ?)""",
                (window,),
            ).fetchone()[0]

            report = {
                "period_hours": hours,
                "total_events": total,
                "unacknowledged": unacknowledged,
                "by_severity": by_severity,
                "by_type": by_type,
                "generated_at": _now_iso(),
            }

            # Record the report generation itself
            self.record(
                event_type=EVENT_REPORT,
                source="audit_bureau",
                severity=SEVERITY_INFO,
                reported_to="user",
                detail=report,
            )

            _emit_sse("audit.report_ready", {
                "period": hours,
                "anomaly_count": by_severity.get(SEVERITY_CRITICAL, 0)
                    + by_severity.get(SEVERITY_WARNING, 0),
                "summary": f"{total} events, {unacknowledged} unacknowledged",
            })

            self._last_report_time = time.time()
            return report
        except Exception as exc:
            logger.warning("Audit Bureau: report generation failed: %s", exc)
            return {"error": str(exc)}

    def search_log(
        self,
        event_type: str = "",
        severity: str = "",
        source: str = "",
        unacknowledged_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Search audit log entries."""
        db = _get_db()
        conditions: list[str] = []
        params: list[Any] = []

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if unacknowledged_only:
            conditions.append("user_acknowledged = 0")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        total = db.execute(
            f"SELECT COUNT(*) FROM audit_log {where}", params
        ).fetchone()[0]

        rows = db.execute(
            f"""SELECT id, timestamp, event_type, source, target,
                       severity, reported_to, detail_json,
                       user_acknowledged, acknowledged_at
                FROM audit_log {where}
                ORDER BY id DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        )

        items = []
        for row in rows:
            items.append({
                "id": row[0],
                "timestamp": row[1],
                "event_type": row[2],
                "source": row[3],
                "target": row[4],
                "severity": row[5],
                "reported_to": row[6],
                "detail": row[7],
                "user_acknowledged": bool(row[8]),
                "acknowledged_at": row[9],
            })

        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def acknowledge(self, audit_id: int) -> bool:
        """Mark an audit log entry as acknowledged by the user."""
        try:
            db = _get_db()
            cursor = db.execute(
                """UPDATE audit_log
                   SET user_acknowledged = 1, acknowledged_at = ?
                   WHERE id = ? AND user_acknowledged = 0""",
                (_now_iso(), audit_id),
            )
            db.commit()
            return cursor.rowcount > 0
        except Exception as exc:
            logger.warning("Audit Bureau: acknowledge failed: %s", exc)
            return False

    def status(self) -> dict:
        """Return current Audit Bureau status."""
        try:
            db = _get_db()
            row = db.execute(
                "SELECT COUNT(*), "
                "SUM(CASE WHEN user_acknowledged = 0 THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) "
                "FROM audit_log"
            ).fetchone()
            total = row[0] or 0
            unacked = row[1] or 0
            critical = row[2] or 0
            return {
                "enabled": self._enabled,
                "total_entries": total,
                "unacknowledged": unacked,
                "critical_count": critical,
                "report_interval_hours": self._report_interval / 3600,
            }
        except Exception:
            return {"enabled": self._enabled, "total_entries": 0}
