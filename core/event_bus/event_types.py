"""Event type definitions for the in-process event bus."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    """A single event emitted through the event bus."""

    type: str
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "data": self.data,
            "source": self.source,
        }


# -- Scan events --
SCAN_START = "scan.start"
SCAN_PROGRESS = "scan.progress"
SCAN_COMPLETE = "scan.complete"
SCAN_ERROR = "scan.error"
SCAN_DB_BUSY = "scan.db_busy"  # DB busy notification during scan
SCAN_QUEUED = "scan.queued"  # Scan added to queue
SCAN_QUEUE_NEXT = "scan.queue_next"  # Next scan started from queue
SCAN_QUEUE_CLEARED = "scan.queue_cleared"  # Queue fully cleared

# -- Favorite events --
FAV_ADD = "favorite.add"
FAV_REMOVE = "favorite.remove"

# -- Collection events --
COLL_CREATE = "collection.create"
COLL_DELETE = "collection.delete"

# -- Generation events --
GEN_SUBMIT = "generation.submit"
GEN_PROGRESS = "generation.progress"
GEN_COMPLETE = "generation.complete"
GEN_ERROR = "generation.error"
GEN_CANCEL = "generation.cancel"

# -- Rating events --
RATING_SET = "rating.set"
RATING_CLEAR = "rating.clear"

# -- Annotation events --
ANNOTATION_SET = "annotation.set"
ANNOTATION_DELETE = "annotation.delete"

# -- Config events --
SCAN_ROOTS_CHANGED = "config.scan_roots_changed"

# -- Watcher events --
WATCHER_STARTED = "watcher.started"
WATCHER_STOPPED = "watcher.stopped"
WATCHER_SYNC = "watcher.sync"

# -- Backup events --
BACKUP_COMPLETE = "backup.complete"
BACKUP_ERROR = "backup.error"

# -- Semantic index events --
SEMANTIC_INDEX_START = "semantic_index.start"
SEMANTIC_INDEX_PROGRESS = "semantic_index.progress"
SEMANTIC_INDEX_COMPLETE = "semantic_index.complete"

# -- YOLO detection events --
YOLO_DETECT_START = "yolo_detect.start"
YOLO_DETECT_PROGRESS = "yolo_detect.progress"
YOLO_DETECT_COMPLETE = "yolo_detect.complete"

# -- Hash backfill events --
HASH_BACKFILL_PROGRESS = "hash_backfill.progress"
HASH_BACKFILL_COMPLETE = "hash_backfill.complete"

# -- Freeze & Pull-back events --
FPB_START = "fpb.start"
FPB_PROGRESS = "fpb.progress"
FPB_COMPLETE = "fpb.complete"
FPB_ERROR = "fpb.error"

# -- Chatlog reprocess events --
CHATLOG_REPROCESS_START = "chatlog_reprocess.start"
CHATLOG_REPROCESS_PROGRESS = "chatlog_reprocess.progress"
CHATLOG_REPROCESS_COMPLETE = "chatlog_reprocess.complete"
CHATLOG_REPROCESS_ERROR = "chatlog_reprocess.error"

# -- Agent Safety events --
AGENT_KILLED = "agent.killed"
AGENT_RESUMED = "agent.resumed"
AGENT_CIRCUIT_OPEN = "agent.circuit_open"
AGENT_CIRCUIT_CLOSED = "agent.circuit_closed"
AGENT_CIRCUIT_HALF_OPEN = "agent.circuit_half_open"
AGENT_BUDGET_WARNING = "agent.budget_warning"
AGENT_BUDGET_EXHAUSTED = "agent.budget_exhausted"

# -- Scheduler events --
SCHEDULER_JOB_EXECUTED = "scheduler.job_executed"
SCHEDULER_JOB_ERROR = "scheduler.job_error"

# -- GitHub issue queue events --
GITHUB_QUEUE_NEW = "github_queue.new_issues"
GITHUB_QUEUE_TRIAGE = "github_queue.triage_complete"
GITHUB_QUEUE_DISMISSED = "github_queue.dismissed"

# -- Bluesky notification queue events --
BSKY_QUEUE_NEW = "bsky_queue.new_notifications"
BSKY_QUEUE_TRIAGE = "bsky_queue.triage_complete"
BSKY_QUEUE_RESPONDED = "bsky_queue.auto_responded"

# -- Peer / LAN Cowork events --
PEER_DISCOVERED = "peer.discovered"
PEER_ONLINE = "peer.online"
PEER_OFFLINE = "peer.offline"
PEER_STATUS_UPDATE = "peer.status_update"
PEER_AUTH_LOST = "peer.auth_lost"  # 401 received — token expired/revoked, re-pair needed
SYNC_FILE_CHANGED = "sync.file_changed"
SYNC_FILE_RECEIVED = "sync.file_received"
SYNC_MANIFEST_EXCHANGED = "sync.manifest_exchanged"
SYNC_CONFLICT = "sync.conflict"

# -- Tag events --
TAG_ADD = "tag.add"
TAG_REMOVE = "tag.remove"

# -- Analysis events --
ANALYSIS_COMPLETE = "analysis.complete"
BATCH_ANALYSIS_COMPLETE = "batch_analysis.complete"

# -- Processor completion events --
WD_TAGGER_COMPLETE = "wd_tagger.complete"
OCR_COMPLETE = "ocr.complete"

# -- Inbound webhook events --
WEBHOOK_RECEIVED = "webhook.received"

ALL_EVENT_TYPES = (
    SCAN_START, SCAN_PROGRESS, SCAN_COMPLETE, SCAN_ERROR, SCAN_DB_BUSY,
    SCAN_QUEUED, SCAN_QUEUE_NEXT, SCAN_QUEUE_CLEARED,
    FAV_ADD, FAV_REMOVE,
    COLL_CREATE, COLL_DELETE,
    RATING_SET, RATING_CLEAR,
    ANNOTATION_SET, ANNOTATION_DELETE,
    GEN_SUBMIT, GEN_PROGRESS, GEN_COMPLETE, GEN_ERROR, GEN_CANCEL,
    SCAN_ROOTS_CHANGED,
    WATCHER_STARTED, WATCHER_STOPPED, WATCHER_SYNC,
    BACKUP_COMPLETE, BACKUP_ERROR,
    SEMANTIC_INDEX_START, SEMANTIC_INDEX_PROGRESS, SEMANTIC_INDEX_COMPLETE,
    YOLO_DETECT_START, YOLO_DETECT_PROGRESS, YOLO_DETECT_COMPLETE,
    HASH_BACKFILL_PROGRESS, HASH_BACKFILL_COMPLETE,
    FPB_START, FPB_PROGRESS, FPB_COMPLETE, FPB_ERROR,
    CHATLOG_REPROCESS_START, CHATLOG_REPROCESS_PROGRESS,
    CHATLOG_REPROCESS_COMPLETE, CHATLOG_REPROCESS_ERROR,
    AGENT_KILLED, AGENT_RESUMED,
    AGENT_CIRCUIT_OPEN, AGENT_CIRCUIT_CLOSED, AGENT_CIRCUIT_HALF_OPEN,
    AGENT_BUDGET_WARNING, AGENT_BUDGET_EXHAUSTED,
    SCHEDULER_JOB_EXECUTED, SCHEDULER_JOB_ERROR,
    GITHUB_QUEUE_NEW, GITHUB_QUEUE_TRIAGE, GITHUB_QUEUE_DISMISSED,
    BSKY_QUEUE_NEW, BSKY_QUEUE_TRIAGE, BSKY_QUEUE_RESPONDED,
    PEER_DISCOVERED, PEER_ONLINE, PEER_OFFLINE, PEER_STATUS_UPDATE, PEER_AUTH_LOST,
    SYNC_FILE_CHANGED, SYNC_FILE_RECEIVED, SYNC_MANIFEST_EXCHANGED, SYNC_CONFLICT,
    TAG_ADD, TAG_REMOVE,
    ANALYSIS_COMPLETE, BATCH_ANALYSIS_COMPLETE,
    WD_TAGGER_COMPLETE, OCR_COMPLETE,
    WEBHOOK_RECEIVED,
)
