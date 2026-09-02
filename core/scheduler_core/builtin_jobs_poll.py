"""Built-in scheduled jobs -- external service polling.

Contains github_issue_poll and bsky_notification_poll which fetch
data from external APIs and enqueue results locally.
"""

import contextlib
import logging
import os
from datetime import UTC

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
def github_issue_poll() -> str:
    """Poll GitHub API for new issues and enqueue them."""
    from core.configuration.api import load_config_json
    from core.settings_core.secret_store import decrypt, is_encrypted

    cfg = load_config_json()
    gh_cfg = cfg.get("github_integration", {})
    accounts = gh_cfg.get("accounts", [])

    if not accounts:
        return "No GitHub accounts configured"

    tokens = gh_cfg.get("tokens", {})

    total_new = 0
    for acc in accounts:
        if not acc.get("enabled", True):
            continue
        label = acc.get("label", "")
        # New: tokens stored in flat dict; fallback to legacy accounts[].token
        token = tokens.get(label, "") or acc.get("token", "")
        if is_encrypted(token):
            token = decrypt(token)
        if not token:
            continue
        repos = acc.get("repos", [])
        for repo in repos:
            try:
                new_count = _poll_repo_issues(token, repo)
                total_new += new_count
            except Exception as exc:
                logger.warning(
                    "[SCHEDULER] github_issue_poll error for %s: %s",
                    repo, exc,
                )

    if total_new > 0:
        try:
            from core.event_bus import emit
            emit("github_queue.new_issues", {
                "count": total_new,
            }, source="scheduler")
        except Exception:
            logger.warning("step failed", exc_info=True)

    logger.info(
        "[SCHEDULER] github_issue_poll: %d new issues queued", total_new
    )
    return f"Polled: {total_new} new issues queued"


def _poll_repo_issues(token: str, repo: str) -> int:
    """Fetch open issues for a repo and enqueue new ones. Returns count added."""
    import importlib
    # Load github_client directly from the extension package directory.
    spec_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "extensions", "builtin_github_integration",
        "core_impl", "github_client.py",
    )
    spec = importlib.util.spec_from_file_location(
        "github_client_poll", spec_path,
    )
    gh_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gh_mod)

    code, data = gh_mod.fetch_issues(token, repo, state="open", per_page=50)
    if code != 200 or not isinstance(data, list):
        return 0

    from datetime import datetime

    rows = []
    now = datetime.now(UTC).isoformat()
    for raw in data:
        if "pull_request" in raw:
            continue
        issue = gh_mod.normalize_issue(raw)
        rows.append((
            repo,
            issue["number"],
            issue["title"],
            issue["body"][:3000],
            issue["created_at"],
            now,
        ))

    if not rows:
        return 0

    from core.services_core.db_write import submit_db_write
    return submit_db_write(_poll_repo_issues_write, rows)


def _poll_repo_issues_write(rows: list[tuple]) -> int:
    from core.services_core.db_state import get_db
    db = get_db()
    inserted = 0
    for row in rows:
        try:
            cur = db.execute(
                "INSERT OR IGNORE INTO github_issue_queue "
                "(repo, issue_number, title, body, created_at, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                row,
            )
            if cur.rowcount > 0:
                inserted += 1
        except Exception as exc:
            logger.warning("Failed to enqueue %s#%s: %s", row[0], row[1], exc)
    db.commit()
    return inserted


@_with_db_cleanup
def bsky_notification_poll() -> str:
    """Poll Bluesky for new notifications and enqueue them."""
    with contextlib.suppress(ImportError):
        from extensions.builtin_sns_share_shim import poll_notifications  # noqa: F401  # availability probe

    # Use importlib to load the monitor directly from the extension package.
    import importlib
    spec_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "extensions", "builtin_sns_share",
        "core_impl", "bsky_monitor.py",
    )
    spec = importlib.util.spec_from_file_location(
        "bsky_monitor_poll", spec_path,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    counts = mod.poll_notifications()
    total = sum(counts.values())

    if total > 0:
        try:
            from core.event_bus import emit
            emit("bsky_queue.new_notifications", {
                "counts": counts, "total": total,
            }, source="scheduler")
        except Exception:
            logger.warning("step failed", exc_info=True)

    logger.info(
        "[SCHEDULER] bsky_notification_poll: %d new notifications", total
    )
    return f"Polled: {total} new notifications ({counts})"
