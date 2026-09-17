"""Built-in scheduled jobs -- re-export facade.

Split into:
  - builtin_jobs_db: database and maintenance jobs
  - builtin_jobs_poll: external service polling jobs
"""

# Re-export all public symbols for backward compatibility
from core.scheduler_core.builtin_jobs_audit import (  # noqa: F401
    extension_audit_periodic,
    extension_audit_surprise,
)
from core.scheduler_core.builtin_jobs_db import (  # noqa: F401
    db_analyze,
    db_backup,
    db_compress_old_raw_responses,
    db_integrity_check,
    db_prune_old_webhook_deliveries,
    db_vacuum,
    prune_unused_tags,
    rebuild_groups_index,
    refresh_monthly_stats,
    thumbnail_cleanup,
    thumbnail_cleanup_pressure,
    thumbnail_integrity_check,
)
from core.scheduler_core.builtin_jobs_poll import (  # noqa: F401
    bsky_notification_poll,
    github_issue_poll,
)

# Registry: job_id -> callable
BUILTIN_JOBS = {
    "db_analyze": db_analyze,
    "db_vacuum": db_vacuum,
    "db_integrity_check": db_integrity_check,
    "thumbnail_cleanup": thumbnail_cleanup,
    "thumbnail_cleanup_pressure": thumbnail_cleanup_pressure,
    "thumbnail_integrity_check": thumbnail_integrity_check,
    "github_issue_poll": github_issue_poll,
    "bsky_notification_poll": bsky_notification_poll,
    "prune_unused_tags": prune_unused_tags,
    "refresh_monthly_stats": refresh_monthly_stats,
    "rebuild_groups_index": rebuild_groups_index,
    "db_backup": db_backup,
    "db_compress_old_raw_responses": db_compress_old_raw_responses,
    "db_prune_old_webhook_deliveries": db_prune_old_webhook_deliveries,
    "extension_audit_periodic": extension_audit_periodic,
    "extension_audit_surprise": extension_audit_surprise,
}
