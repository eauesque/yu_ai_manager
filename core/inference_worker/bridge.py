"""Quart <-> Worker bridge.

Manages worker process start/stop/task submission from the Quart web process.
A monitor thread reflects progress to the JobManager.
Supports LLM streaming via per-task asyncio queues and auto-restart on crash.
"""

import asyncio
import contextlib
import logging
import multiprocessing
import threading
import time
from multiprocessing.process import BaseProcess
from typing import Any

from .task_queue import TaskQueue
from .task_types import (
    ControlResponse,
    InferenceResult,
    InferenceTask,
    ProgressUpdate,
    StreamingToken,
    TaskStatus,
)

logger = logging.getLogger(__name__)

class BridgeStoppedError(RuntimeError):
    """Raised when bridge is stopped while control request is pending."""
    pass



class InferenceWorkerBridge:
    """Communication bridge with the inference worker."""

    def __init__(self) -> None:
        self._queue: TaskQueue | None = None
        self._process: BaseProcess | None = None
        self._monitor_thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        # Per-task streaming queues for LLM output
        self._streaming_queues: dict[str, asyncio.Queue] = {}
        # Track tasks that have overflow termination sentinel
        self._overflow_terminated: set[str] = set()
        # Event loop bound at startup via before_serving hook
        self._main_loop: asyncio.AbstractEventLoop | None = None
        # Auto-restart state
        self._restart_count = 0
        self._max_restarts = 3
        self._restart_backoff = 1.0
        # Store config for client access and auto-restart
        self._config: dict | None = None
        self._db_path: str = ""
        # Control RPC: per-request_id futures resolved when the worker
        # responds via _control_response_queue. The pumper thread runs
        # alongside the result monitor thread.
        self._control_futures: dict[str, asyncio.Future] = {}
        self._control_response_thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._running and self._process is not None and self._process.is_alive()

    def bind_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the main event loop for streaming token dispatching."""
        self._main_loop = loop
        logger.debug("Event loop bound to bridge")

    def start(self, db_path: str, config: dict) -> None:
        """Start/launch the worker process."""
        with self._lock:
            if self.is_running:
                logger.warning("Worker already running")
                return

            ctx = multiprocessing.get_context("spawn")
            self._queue = TaskQueue(ctx=ctx)
            self._running = True
            self._restart_count = 0
            self._config = config
            self._db_path = db_path  # remember for auto-restart

            from .worker_process import worker_main

            self._process = ctx.Process(
                target=worker_main,
                args=(self._queue, db_path, config),
                daemon=False,
                name="inference-worker",
            )
            if self._process is not None:
                self._process.start()
                logger.info("Inference worker started (pid=%d)", self._process.pid)

            # Progress monitor thread
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="inference-monitor",
            )
            self._monitor_thread.start()

            # Control response pumper (separate queue from results)
            self._control_response_thread = threading.Thread(
                target=self._control_response_loop,
                daemon=True,
                name="inference-control-resp",
            )
            self._control_response_thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the worker process."""
        with self._lock:
            self._running = False
            if self._queue:
                self._queue.send_shutdown()
            if self._process and self._process.is_alive():
                self._process.join(timeout=timeout)
                if self._process.is_alive():
                    logger.warning("Worker did not stop gracefully, terminating")
                    self._process.terminate()
            if self._queue:
                self._queue.close()
            self._queue = None
            self._process = None
            # Clean up streaming queues
            self._streaming_queues.clear()
            self._overflow_terminated.clear()
            logger.info("Inference worker stopped")

    def submit_task(self, task: InferenceTask) -> bool:
        """Submit a task to the worker."""
        if not self.is_running or not self._queue:
            return False
        self._queue.put_task(task)
        return True

    def register_stream(self, task_id: str) -> asyncio.Queue:
        """Register a streaming task and return its output queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=4)
        self._streaming_queues[task_id] = q
        return q

    def unregister_stream(self, task_id: str) -> None:
        """Unregister a streaming task."""
        self._streaming_queues.pop(task_id, None)
        self._overflow_terminated.discard(task_id)

    async def iter_stream(
        self,
        task_id: str,
        first_token_timeout: float = 120.0,
        inter_token_timeout: float = 30.0,
    ):
        """Async generator to iterate over streaming tokens for a task.

        Uses a long timeout for the first token to accommodate cold_load
        (HailoRT LLM init holds GIL ~71s on Pi 5), then a shorter timeout
        between subsequent tokens.
        """
        q = self._streaming_queues.get(task_id)
        if not q:
            return
        timeout = first_token_timeout
        try:
            while True:
                try:
                    token = await asyncio.wait_for(q.get(), timeout=timeout)
                    timeout = inter_token_timeout
                    yield token
                    if token.terminal:
                        break
                except TimeoutError:
                    logger.warning("Stream timeout for task %s", task_id)
                    break
        finally:
            self.unregister_stream(task_id)

    def send_control(self, msg: Any) -> None:
        """Send a control message to the worker (fire-and-forget)."""
        if self._queue:
            self._queue.put_control(msg)

    async def send_control_and_wait(self, msg: Any, timeout: float = 10.0) -> ControlResponse:
        """Send a control message and await the worker's response.

        Uses ``msg.task_id`` as the correlation ID. The caller must ensure
        each in-flight request has a unique task_id (a uuid is fine for
        non-streaming control messages such as close_llm / clear_context /
        unload / status_query).
        """
        if not self._queue or not self._main_loop:
            raise RuntimeError("inference bridge not started or event loop not bound")

        loop = self._main_loop
        future: asyncio.Future = loop.create_future()
        self._control_futures[msg.task_id] = future
        try:
            self._queue.put_control(msg)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.CancelledError as err:
            raise BridgeStoppedError("Bridge stopped while waiting for control response") from err
        finally:
            self._control_futures.pop(msg.task_id, None)

    def _control_response_loop(self) -> None:
        """Pump the control_response queue and resolve pending futures."""
        while self._running:
            if not self._queue:
                break
            resp = self._queue.get_control_response(timeout=0.5)
            if resp is None:
                continue
            self._on_control_response(resp)
        
        # On exit, cancel all pending futures (if event loop still running)
        if self._main_loop and not self._main_loop.is_closed():
            def _cancel_all():
                """Cancel all pending control futures (event loop thread)."""
                for _task_id, future in list(self._control_futures.items()):
                    if not future.done():
                        future.set_exception(BridgeStoppedError("Bridge stopped with pending request"))
                self._control_futures.clear()
            
            try:
                self._main_loop.call_soon_threadsafe(_cancel_all)
            except RuntimeError:
                # Event loop already closed, clear futures locally
                for future in self._control_futures.values():
                    if not future.done():
                        future.set_exception(BridgeStoppedError("Bridge stopped"))
                self._control_futures.clear()

    def _monitor_loop(self) -> None:
        """Receive progress/results/tokens from the worker and reflect to JobManager."""
        while self._running:
            if not self._queue:
                break

            # Check if process crashed; auto-restart if enabled
            if not self._process or not self._process.is_alive():
                if self._running and self._restart_count < self._max_restarts:
                    logger.info(
                        "Worker crashed (count=%d), auto-restarting in %.1fs",
                        self._restart_count,
                        self._restart_backoff,
                    )
                    time.sleep(self._restart_backoff)
                    self._restart_count += 1
                    try:
                        # Stop and restart control response thread
                        self._running = False
                        if self._control_response_thread and self._control_response_thread.is_alive():
                            self._control_response_thread.join(timeout=2.0)
                        self._running = True
                        
                        # Create new queue to avoid stale multiprocessing primitives
                        if self._queue:
                            try:
                                # Drain pending items
                                while True:
                                    msg = self._queue.get_result(timeout=0.1)
                                    if msg is None:
                                        break
                            except Exception:
                                logger.warning("inference worker step failed", exc_info=True)
                            self._queue.close()
                        
                        ctx = multiprocessing.get_context("spawn")
                        self._queue = TaskQueue(ctx=ctx)
                        
                        from .worker_process import worker_main
                        self._process = ctx.Process(
                            target=worker_main,
                            args=(self._queue, self._db_path, self._config or {}),
                            daemon=False,
                            name="inference-worker",
                        )
                        if self._process is not None:
                            self._process.start()
                            logger.info("Worker restarted (pid=%d)", self._process.pid)
                            self._restart_backoff = 1.0  # Reset on successful restart
                            self._restart_count = 0
                            
                            # Restart control response thread
                            self._control_response_thread = threading.Thread(
                                target=self._control_response_loop,
                                daemon=True,
                                name="inference-control-resp",
                            )
                            self._control_response_thread.start()
                    except Exception as exc:
                        logger.error("Failed to restart worker: %s", exc)
                        self._restart_backoff = min(self._restart_backoff * 2, 30.0)
                        break
                else:
                    logger.error("Worker crashed and max restarts exhausted")
                    break

            msg = self._queue.get_result(timeout=0.5)
            if msg is None:
                continue

            if isinstance(msg, StreamingToken):
                self._on_streaming_token(msg)
            elif isinstance(msg, ControlResponse):
                self._on_control_response(msg)
            elif isinstance(msg, ProgressUpdate):
                self._on_progress(msg)
            elif isinstance(msg, InferenceResult):
                self._on_result(msg)

    def _on_streaming_token(self, token: StreamingToken) -> None:
        """Dispatch a streaming token to the per-task queue."""
        if not self._main_loop:
            logger.warning(
                "Stream output received but event loop not bound (task_id=%s)",
                token.task_id,
            )
            return

        q = self._streaming_queues.get(token.task_id)
        if not q:
            logger.debug(
                "No queue registered for task %s, ignoring output", token.task_id
            )
            return

        try:
            # If queue is full, drain and insert overflow sentinel
            if q.full():
                def _drain_and_put():
                    """Drain queue and put overflow token (event loop thread)."""
                    try:
                        while not q.empty():
                            try:
                                q.get_nowait()
                            except Exception:
                                break
                    except Exception:
                        logger.warning("inference worker step failed", exc_info=True)
                    # Insert overflow sentinel
                    overflow_token = StreamingToken(
                        task_id=token.task_id,
                        token="<OVERFLOW>",
                        seq=token.seq,
                        terminal=True,
                    )
                    with contextlib.suppress(Exception):
                        q.put_nowait(overflow_token)
                    self._overflow_terminated.add(token.task_id)
                    logger.warning("Queue overflow for task %s, inserting sentinel", token.task_id)
                
                self._main_loop.call_soon_threadsafe(_drain_and_put)
            else:
                self._main_loop.call_soon_threadsafe(q.put_nowait, token)

            # Clean up after terminal token
            if token.terminal:
                self._main_loop.call_soon_threadsafe(
                    self._streaming_queues.pop, token.task_id, None
                )
                self._overflow_terminated.discard(token.task_id)
        except Exception as exc:
            logger.error("Failed to dispatch output for task %s: %s", token.task_id, exc)

    def _on_control_response(self, resp: ControlResponse) -> None:
        """Resolve the pending future associated with this response."""
        logger.debug("Control response: task=%s op=%s ok=%s", resp.task_id, resp.op, resp.ok)
        if not self._main_loop:
            return
        
        def _resolve():
            """Resolve future in event loop thread (thread-safe)."""
            future = self._control_futures.pop(resp.task_id, None)
            if future and not future.done():
                try:
                    future.set_result(resp)
                except Exception as exc:
                    logger.debug("Failed to set control response: %s", exc)
        
        try:
            self._main_loop.call_soon_threadsafe(_resolve)
        except RuntimeError:
            self._control_futures.pop(resp.task_id, None)

    def _on_progress(self, update: ProgressUpdate) -> None:
        """Reflect progress to JobManager."""
        try:
            from core.jobs_core.jobs import job_manager

            job = job_manager.get_raw_job(update.task_id)
            if job:
                if update.phase:
                    job.update(phase=update.phase)
                if update.message:
                    job.update(message=update.message)
                if update.total > 0:
                    job.progress(update.current, update.total)
        except Exception as exc:
            logger.debug("Progress update failed: %s", exc)

    def _on_result(self, result: InferenceResult) -> None:
        """Reflect completion to JobManager."""
        try:
            from core.jobs_core.jobs import job_manager

            job = job_manager.get_raw_job(result.task_id)
            if job:
                msg = ""
                if result.result and isinstance(result.result, dict):
                    msg = result.result.get("message", "")
                if result.status == TaskStatus.COMPLETE:
                    job.complete(msg)
                elif result.status == TaskStatus.ERROR:
                    job.fail(result.error or "Unknown error")
                elif result.status == TaskStatus.CANCELLED:
                    job.complete_cancelled(msg)
        except Exception as exc:
            logger.debug("Result handling failed: %s", exc)


# Singleton instance
inference_bridge = InferenceWorkerBridge()
