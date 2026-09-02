"""Cross Search scan worker -- runs in a separate process from web_ui.

Usage:
    python -m extensions.builtin_cross_search.core_impl.scan_worker \
        start --db PATH --roots PATH1,PATH2 [--parent-pid PID]
    python -m extensions.builtin_cross_search.core_impl.scan_worker stop
    python -m extensions.builtin_cross_search.core_impl.scan_worker status
"""

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

# Add project root to sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.worker_runtime import (
    bootstrap_worker_runtime,
    configure_worker_logging,
    install_cancel_signal_handlers,
)
from core.worker_runtime import (
    start_parent_monitor as _shared_start_parent_monitor,
)
from extensions.builtin_cross_search.core_impl.worker_ipc import (
    clear_pid,
    is_process_alive,
    is_worker_running,
    read_pid,
    read_progress,
    signal_stop,
    write_pid,
    write_progress,
)

logger = logging.getLogger(__name__)

_PARENT_CHECK_INTERVAL = 60


class FileBasedJob:
    """FileBasedJob -- a Job that writes progress to a JSON file.

    core.scan.scan_worker.FileBasedJob と同パターン。
    scanner.py が受け取る Job インターフェースを満たす。
    """

    def __init__(self, job_id: str = "cross_search_scan", label: str = "Cross Search スキャン"):
        self.job_id = job_id
        self.label = label
        self.running = True
        self.phase = "starting"
        self.current = 0
        self.total = 0
        self.percent = 0
        self.message = ""
        self.detail = ""
        self.error = None
        self.started_at = time.time()
        self.finished_at = None
        self.stop_event = threading.Event()
        self._last_write = 0.0
        self._write_interval = 1.0

    @property
    def cancelled(self) -> bool:
        return self.stop_event.is_set()

    def cancel(self):
        self.stop_event.set()

    def update(self, phase: str = "", message: str = ""):
        if phase:
            self.phase = phase
        if message:
            self.message = message
        self._write_progress()

    def progress(self, current: int, total: int, detail: str = ""):
        self.current = current
        self.total = total
        self.percent = int((current / total) * 100) if total > 0 else 0
        self.detail = detail
        self._write_progress(throttled=True)

    def complete(self, message: str = ""):
        self.running = False
        self.phase = "complete"
        self.percent = 100
        if self.total > 0:
            self.current = self.total
        if message:
            self.message = message
        self.finished_at = time.time()
        self._write_progress()

    def complete_cancelled(self, message: str = ""):
        self.running = False
        self.phase = "cancelled"
        self.message = message or f"中断: {self.current}件処理済み / {self.total}件中"
        self.finished_at = time.time()
        self._write_progress()

    def fail(self, error: str):
        self.running = False
        self.phase = "error"
        self.error = error
        self.message = error
        self.finished_at = time.time()
        self._write_progress()

    def to_dict(self):
        elapsed = (self.finished_at or time.time()) - self.started_at
        return {
            "job_id": self.job_id,
            "label": self.label,
            "running": self.running,
            "phase": self.phase,
            "current": self.current,
            "total": self.total,
            "percent": self.percent,
            "message": self.message,
            "detail": self.detail,
            "error": self.error,
            "elapsed_seconds": round(elapsed, 1),
        }

    def _write_progress(self, throttled: bool = False):
        now = time.time()
        if throttled and (now - self._last_write) < self._write_interval:
            return
        self._last_write = now
        write_progress(self.to_dict())


# -- Signal / Parent monitoring -----------------------------------------------

def _setup_signal_handler(job: FileBasedJob):
    install_cancel_signal_handlers(
        job.cancel,
        logger=logger,
        message="cancelling cross-search scan...",
    )


def _start_parent_monitor(job: FileBasedJob, parent_pid: int):
    _shared_start_parent_monitor(
        parent_pid=parent_pid,
        is_running=lambda: job.running,
        is_process_alive=is_process_alive,
        cancel=job.cancel,
        logger=logger,
        message="Parent PID %d is gone, cancelling scan...",
        interval=_PARENT_CHECK_INTERVAL,
    )


# -- CLI commands --------------------------------------------------------------

def cmd_start(args):
    if is_worker_running():
        print("Cross Search ワーカーは既に実行中です", file=sys.stderr)
        sys.exit(1)

    bootstrap_worker_runtime(db_path=args.db, config_path=args.config)

    # Register PID
    write_pid(os.getpid())
    logger.info("Cross Search worker started (PID %d)", os.getpid())

    # Create Job
    job = FileBasedJob()
    _setup_signal_handler(job)

    if args.parent_pid:
        _start_parent_monitor(job, args.parent_pid)

    # Execute scan
    roots = [r.strip() for r in args.roots.split(",") if r.strip()]
    try:
        from extensions.builtin_cross_search.core_impl.scanner import scan_text_files
        scan_text_files(roots, job=job)
    except Exception as e:
        if job.running:
            job.fail(str(e))
    finally:
        if job.running:
            if job.cancelled:
                job.complete_cancelled()
            else:
                job.complete(job.message or "完了")
        clear_pid()
        logger.info("Cross Search worker finished (phase=%s)", job.phase)


def cmd_stop(_args):
    if not is_worker_running():
        print("Cross Search ワーカーは実行されていません")
        return
    pid = read_pid()
    if signal_stop():
        print(f"停止シグナル送信 (PID {pid})")
        for _ in range(20):
            time.sleep(0.5)
            if not is_worker_running():
                print("ワーカー停止完了")
                return
        print("ワーカーはまだ停止処理中です")
    else:
        print("停止シグナルの送信に失敗しました")


def cmd_status(_args):
    if is_worker_running():
        progress = read_progress()
        if progress:
            phase = progress.get("phase", "?")
            cur = progress.get("current", 0)
            tot = progress.get("total", 0)
            pct = progress.get("percent", 0)
            msg = progress.get("message", "")
            print(f"実行中: {phase} - {cur}/{tot} ({pct}%) {msg}")
        else:
            print("実行中 (進捗データなし)")
    else:
        print("停止中")


def main():
    parser = argparse.ArgumentParser(description="Cross Search scan worker")
    sub = parser.add_subparsers(dest="command")

    start_p = sub.add_parser("start", help="ワーカーを起動")
    start_p.add_argument("--db", required=True, help="DB ファイルパス")
    start_p.add_argument("--roots", required=True, help="スキャンディレクトリ (カンマ区切り)")
    start_p.add_argument("--config", default=None, help="設定ファイルパス")
    start_p.add_argument("--parent-pid", type=int, default=None,
                         help="親プロセス PID (自動停止用)")

    sub.add_parser("stop", help="ワーカーを停止")
    sub.add_parser("status", help="ワーカーの状態を表示")

    args = parser.parse_args()

    if args.command == "start":
        configure_worker_logging("cross-scan-worker")
        cmd_start(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
