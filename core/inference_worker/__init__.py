"""Inference worker isolation package.

Runs GPU inference in a separate process so the Quart web process is not blocked by Python's GIL during inference.
Toggled by the "inference_worker.enabled" config flag (disabled by default).
"""

from .bridge import InferenceWorkerBridge, inference_bridge
from .task_types import InferenceResult, InferenceTask, ProgressUpdate, TaskStatus, TaskType

__all__ = [
    "InferenceResult",
    "InferenceTask",
    "InferenceWorkerBridge",
    "ProgressUpdate",
    "TaskStatus",
    "TaskType",
    "inference_bridge",
]
