"""Inference task type definitions.

Dataclasses used for IPC with the worker process.
Must maintain pickle compatibility (for Windows spawn method).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class TaskType(Enum):
    """Types of inference tasks."""
    WD_TAGGER_BATCH = "wd_tagger_batch"
    WD_TAGGER_SINGLE = "wd_tagger_single"
    AI_ANALYSIS_BATCH = "ai_analysis_batch"
    AI_ANALYSIS_SINGLE = "ai_analysis_single"
    LLM_CHAT_STREAM = "llm_chat_stream"


class TaskStatus(Enum):
    """Task status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class InferenceTask:
    """Inference task sent to the worker."""
    task_id: str
    task_type: TaskType
    file_ids: list[int] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    # For single file processing
    file_path: str | None = None
    # Flag to indicate streaming task (LLM_CHAT_STREAM mode)
    streaming: bool = False


@dataclass
class ProgressUpdate:
    """Progress notification from the worker."""
    task_id: str
    current: int = 0
    total: int = 0
    phase: str = ""
    message: str = ""


@dataclass
class InferenceResult:
    """Completion notification from the worker."""
    task_id: str
    status: TaskStatus = TaskStatus.COMPLETE
    result: Any = None
    error: str | None = None


@dataclass
class StreamingToken:
    """Individual token from LLM stream."""
    task_id: str
    token: str
    seq: int
    terminal: bool = False
    error: str | None = None


@dataclass
class ControlMessage:
    """Control message sent to the worker process."""
    task_id: str
    op: Literal["cancel", "status_query", "close_llm", "close_vlm", "clear_context", "unload"]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ControlResponse:
    """Response to a control message from the worker."""
    task_id: str
    op: str
    ok: bool
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ShutdownSentinel:
    """Sentinel value to signal worker shutdown.
    
    Uses a dataclass (serialization-safe) instead of a bare object()
    because spawn context pickles and unpickles values, losing identity.
    """
    reason: str = "shutdown"
