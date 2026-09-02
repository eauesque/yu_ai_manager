"""multiprocessing.Queue wrapper (bidirectional).

Quart process -> Worker: task submission
Worker -> Quart process: progress/result return
Quart <-> Worker: control messages and responses
"""

import contextlib
import multiprocessing
from multiprocessing.context import BaseContext

from .task_types import ControlMessage, ControlResponse, InferenceTask, ShutdownSentinel


class TaskQueue:
    """Bidirectional queue: task submission + result/progress reception + control messaging."""

    def __init__(self, ctx: BaseContext | None = None) -> None:
        if ctx is None:
            ctx = multiprocessing.get_context("spawn")
        
        self._task_queue: multiprocessing.Queue = ctx.Queue()
        self._result_queue: multiprocessing.Queue = ctx.Queue()
        self._control_queue: multiprocessing.Queue = ctx.Queue()
        self._control_response_queue: multiprocessing.Queue = ctx.Queue()

    def put_task(self, task: InferenceTask) -> None:
        """Send a task to the worker."""
        self._task_queue.put(task)

    def get_task(self, timeout: float = 1.0) -> InferenceTask | None:
        """Get a task on the worker side."""
        try:
            return self._task_queue.get(timeout=timeout)
        except Exception:
            return None

    def put_result(self, result) -> None:
        """Return result/progress to the Quart web process."""
        self._result_queue.put(result)

    def get_result(self, timeout: float = 0.1):
        """Get result/progress on the Quart web process side."""
        try:
            return self._result_queue.get(timeout=timeout)
        except Exception:
            return None

    def put_control(self, msg: ControlMessage) -> None:
        """Send a control message to the worker."""
        self._control_queue.put(msg)

    def get_control(self, timeout: float = 0.5) -> ControlMessage | None:
        """Get a control message on the worker side."""
        try:
            return self._control_queue.get(timeout=timeout)
        except Exception:
            return None

    def put_control_response(self, resp: ControlResponse) -> None:
        """Send a control response back to Quart."""
        self._control_response_queue.put(resp)

    def get_control_response(self, timeout: float = 1.0) -> ControlResponse | None:
        """Get a control response on the Quart side."""
        try:
            return self._control_response_queue.get(timeout=timeout)
        except Exception:
            return None

    def send_shutdown(self) -> None:
        """Send a shutdown signal to the worker.
        
        Accepts both ShutdownSentinel (new) and None (legacy) for compatibility.
        Worker checks isinstance(task, ShutdownSentinel) or task is None.
        """
        self._task_queue.put(ShutdownSentinel())

    def close(self) -> None:
        """Close all queues."""
        with contextlib.suppress(Exception):
            self._task_queue.close()
        with contextlib.suppress(Exception):
            self._result_queue.close()
        with contextlib.suppress(Exception):
            self._control_queue.close()
        with contextlib.suppress(Exception):
            self._control_response_queue.close()
