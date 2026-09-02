"""Scan worker — CLI commands (start, scan-all, stop, status)."""

import argparse
import logging
import os
import sys
import time

from core.scan.scan_worker_job import (
    FileBasedJob,
    run_scan_with_lifecycle,
    setup_signal_handler,
    start_parent_monitor,
)
from core.scan.worker_ipc import (
    clear_pid,
    is_worker_running,
    read_pid,
    read_progress,
    signal_stop,
    write_pid,
)
from core.worker_runtime import bootstrap_worker_runtime, configure_worker_logging

logger = logging.getLogger(__name__)


def cmd_start(args):
    if is_worker_running():
        print("Scan worker is already running", file=sys.stderr)
        sys.exit(1)

    bootstrap_worker_runtime(db_path=args.db, config_path=args.config)

    # Register PID
    write_pid(os.getpid())
    logger.info("Scan worker started (PID %d)", os.getpid())

    # Create job
    job = FileBasedJob()
    setup_signal_handler(job)

    # Parent process monitoring
    if args.parent_pid:
        start_parent_monitor(job, args.parent_pid)

    # Execute scan
    try:
        run_scan_with_lifecycle(
            job,
            root_path=args.root,
            recursive=args.recursive,
            force=args.force,
            scan_zips=args.scan_zips,
            resume=args.resume,
        )
    finally:
        clear_pid()
        # Keep progress file so web_ui can read the final state
        logger.info("Scan worker finished (phase=%s)", job.phase)


def cmd_scan_all(args):
    """Run scan-all-roots as a worker process."""
    if is_worker_running():
        print("Scan worker is already running", file=sys.stderr)
        sys.exit(1)

    from core.configuration.api import load_config_json

    bootstrap_worker_runtime(db_path=args.db, config_path=args.config)

    # Get enabled scan roots
    cfg = load_config_json()
    roots = cfg.get("scan_roots", [])
    enabled_roots = [r for r in roots if r.get("enabled", True) and r.get("path")]
    if not enabled_roots:
        print("No enabled scan roots found", file=sys.stderr)
        sys.exit(1)

    # Register PID
    write_pid(os.getpid())
    logger.info("Scan-all worker started (PID %d, %d roots)", os.getpid(), len(enabled_roots))

    # Create job
    job = FileBasedJob(label="scan-all")
    setup_signal_handler(job)

    # Parent process monitoring
    if args.parent_pid:
        start_parent_monitor(job, args.parent_pid)

    # Scan all roots sequentially
    force = args.force
    try:
        _run_scan_all_with_lifecycle(job, enabled_roots, force)
    finally:
        clear_pid()
        logger.info("Scan-all worker finished (phase=%s)", job.phase)


def _run_scan_all_with_lifecycle(job: FileBasedJob, enabled_roots: list, force: bool):
    """Execute scan-all-roots inside the worker process."""
    from core.scan.runtime import run_scan_background
    from core.scan.runtime_post import purge_orphan_files

    try:
        for idx, root_cfg in enumerate(enabled_roots):
            if job.cancelled:
                job.complete_cancelled()
                return

            root_path = root_cfg.get("path", "")
            recursive = root_cfg.get("recursive", True)
            if not root_path:
                continue

            job.update(
                message=f"Scanning root {idx + 1}/{len(enabled_roots)}: {root_path}",
            )
            run_scan_background(root_path, recursive, force, scan_zips=True, job=job)

        if not job.cancelled:
            job.update(phase="cleanup", message="Detecting orphan files...")
            orphan_count = purge_orphan_files()
            if orphan_count > 0:
                job.update(message=f"Removed {orphan_count} orphan entries")

        if job.running:
            job.complete(f"Scan complete for {len(enabled_roots)} roots")
    except Exception as exc:
        if job.running:
            job.fail(str(exc))


def cmd_stop(_args):
    if not is_worker_running():
        print("Scan worker is not running")
        return

    pid = read_pid()
    if signal_stop():
        print(f"Stop signal sent (PID {pid})")
        for _ in range(20):
            time.sleep(0.5)
            if not is_worker_running():
                print("Scan worker stopped")
                return
        print("Worker is still shutting down")
    else:
        print("Failed to send stop signal")


def cmd_status(_args):
    if is_worker_running():
        progress = read_progress()
        if progress:
            phase = progress.get("phase", "?")
            cur = progress.get("current", 0)
            tot = progress.get("total", 0)
            pct = progress.get("percent", 0)
            msg = progress.get("message", "")
            print(f"Running: {phase} - {cur}/{tot} ({pct}%) {msg}")
        else:
            print("Running (no progress data)")
    else:
        print("Stopped")


def main():
    parser = argparse.ArgumentParser(description="YU AI Manager scan worker")
    sub = parser.add_subparsers(dest="command")

    start_p = sub.add_parser("start", help="Start scan worker")
    start_p.add_argument("--db", required=True, help="DB file path")
    start_p.add_argument("--root", required=True, help="Scan target directory")
    start_p.add_argument("--config", default=None, help="Config file path")
    start_p.add_argument("--recursive", action="store_true", default=True)
    start_p.add_argument("--no-recursive", dest="recursive", action="store_false")
    start_p.add_argument("--force", action="store_true", default=False)
    start_p.add_argument("--scan-zips", action="store_true", default=False)
    start_p.add_argument("--resume", action="store_true", default=False)
    start_p.add_argument("--parent-pid", type=int, default=None,
                         help="Parent PID (for auto-stop)")

    scan_all_p = sub.add_parser("scan-all", help="Scan all roots as worker")
    scan_all_p.add_argument("--db", required=True, help="DB file path")
    scan_all_p.add_argument("--config", default=None, help="Config file path")
    scan_all_p.add_argument("--force", action="store_true", default=False)
    scan_all_p.add_argument("--parent-pid", type=int, default=None,
                            help="Parent PID (for auto-stop)")

    sub.add_parser("stop", help="Stop scan worker")
    sub.add_parser("status", help="Show scan worker status")

    args = parser.parse_args()

    if args.command in ("start", "scan-all"):
        configure_worker_logging("scan-worker")
        if args.command == "start":
            cmd_start(args)
        else:
            cmd_scan_all(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()
