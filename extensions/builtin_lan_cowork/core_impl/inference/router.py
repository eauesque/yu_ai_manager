"""InferenceRouter — distribute batch inference across mesh peers.

Uses asyncio.Queue work-stealing: each peer pulls batches from a shared
queue, so faster peers naturally process more items.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from ..models import PeerInfo
from ..registry import PeerRegistry

logger = logging.getLogger(__name__)


class BatchInferenceStrategy:
    """Select peers capable of a given inference type.

    In ``single`` mode, the first eligible peer is selected. The router passes
    the local peer first, so capable local execution is preferred.
    """

    def _eligible_peers(
        self,
        inference_type: str,
        peers: list[PeerInfo],
    ) -> list[PeerInfo]:
        """Return online peers that have *inference_type* in their inference_types."""
        return [
            p
            for p in peers
            if p.status == "online" and inference_type in p.inference_types
        ]

    def _apply_mode(
        self,
        peers: list[PeerInfo],
        mode: str,
    ) -> list[PeerInfo]:
        """Apply dispatch mode to eligible peers."""
        if mode == "single":
            return peers[:1]
        return list(peers)

    def select_peers(
        self,
        inference_type: str,
        peers: list[PeerInfo],
        mode: str = "parallel",
    ) -> list[PeerInfo]:
        """Return eligible peers after applying dispatch mode."""
        return self._apply_mode(self._eligible_peers(inference_type, peers), mode)


class InferenceRouter:
    """Distribute batch inference work across mesh peers."""

    def __init__(
        self,
        local_peer: PeerInfo,
        registry: PeerRegistry,
        strategy: BatchInferenceStrategy | None = None,
    ) -> None:
        self._local_peer = local_peer
        self._registry = registry
        self._strategy = strategy or BatchInferenceStrategy()

    # ------------------------------------------------------------------
    # Public accessors (for core/mesh_inference bridge layer)
    # ------------------------------------------------------------------

    @property
    def strategy(self) -> BatchInferenceStrategy:
        """Current dispatch strategy."""
        return self._strategy

    @strategy.setter
    def strategy(self, value: BatchInferenceStrategy) -> None:
        self._strategy = value

    def get_available_peers(
        self,
        inference_type: str,
        mode: str = "parallel",
    ) -> list[PeerInfo]:
        """Get capable peers including the local peer."""
        remote = self._registry.list_online()
        all_peers = [self._local_peer] + remote
        return self._strategy.select_peers(inference_type, all_peers, mode)

    # Backward-compatible aliases (deprecated)
    def _get_available_peers(
        self,
        inference_type: str,
        mode: str = "parallel",
    ) -> list[PeerInfo]:
        return self.get_available_peers(inference_type, mode)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch_inference(
        self,
        inference_type: str,
        items: list[Any],
        batch_size: int = 32,
        mode: str = "parallel",
        worker_fn: Callable[[PeerInfo, list[Any]], Coroutine[Any, Any, list[Any]]] | None = None,
        result_fn: Callable[[list[Any]], None] | None = None,
        progress_fn: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Distribute *items* across peers using asyncio.Queue work-stealing.

        Args:
            inference_type: e.g. "clip", "yolo".
            items: list of work items (file paths, etc.).
            batch_size: items per worker call.
            mode: "parallel" (default, all eligible peers) or "single"
                (first eligible peer only; local is preferred since the
                router lists it first).
            worker_fn: async (peer, batch) -> list[(id, result)] | None.
                A list item of None is treated as a failed/skipped item.
            result_fn: optional sync callback receiving each batch result.
                New callbacks may accept (results, batch); legacy callbacks
                accepting only (results) are still supported.
            progress_fn: optional sync callback (processed, total).

        Returns:
            {"status": "ok", "processed": N, "errors": N}
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")

        total = len(items)
        if total == 0:
            return {"status": "ok", "processed": 0, "errors": 0}

        peers = self.get_available_peers(inference_type, mode)
        if not peers:
            logger.warning(
                "No peers available for inference_type=%s", inference_type,
            )
            return {"status": "ok", "processed": 0, "errors": total}

        # Shared queue of items
        queue: asyncio.Queue[Any] = asyncio.Queue()
        for item in items:
            queue.put_nowait(item)

        processed = 0
        errors = 0
        stats_lock = asyncio.Lock()

        async def _worker(peer: PeerInfo) -> None:
            nonlocal processed, errors
            while True:
                batch: list[Any] = []
                try:
                    for _ in range(batch_size):
                        batch.append(queue.get_nowait())
                except asyncio.QueueEmpty:
                    pass

                if not batch:
                    return

                try:
                    if worker_fn is not None:
                        results = await worker_fn(peer, batch)
                    else:
                        results = batch  # no-op passthrough

                    if result_fn is not None:
                        _call_result_fn(result_fn, results, batch)

                    succeeded = _count_successful_results(results, len(batch))
                    async with stats_lock:
                        processed += succeeded
                        errors += len(batch) - succeeded
                        if progress_fn is not None:
                            progress_fn(processed, total)
                except Exception as exc:
                    logger.error(
                        "Worker error on peer %s: %s", peer.name, exc,
                    )
                    async with stats_lock:
                        errors += len(batch)

        # Launch one worker per peer
        tasks = [asyncio.create_task(_worker(p)) for p in peers]
        await asyncio.gather(*tasks, return_exceptions=True)

        return {"status": "ok", "processed": processed, "errors": errors}


def _count_successful_results(results: Any, batch_len: int) -> int:
    """Count router-progress successes for worker_fn result contracts.

    worker_fn must return list[(id, result)] | None. List entries of None are
    failed/skipped items. Unexpected result types are treated as zero successes
    and logged, rather than silently assuming the whole batch succeeded.
    """
    if isinstance(results, (list, tuple)):
        successful = sum(1 for item in results if item is not None)
        return min(successful, batch_len)
    if results is None:
        return 0
    logger.warning(
        "Unexpected worker_fn result type %s; counting batch_len=%d as errors",
        type(results).__name__,
        batch_len,
    )
    return 0


def _call_result_fn(result_fn: Callable[..., None], results: Any, batch: list[Any]) -> None:
    try:
        signature = inspect.signature(result_fn)
    except (TypeError, ValueError):
        result_fn(results, batch)
        return

    parameters = list(signature.parameters.values())
    accepts_varargs = any(param.kind == inspect.Parameter.VAR_POSITIONAL for param in parameters)
    positional = [
        param
        for param in parameters
        if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if accepts_varargs or len(positional) >= 2:
        result_fn(results, batch)
    else:
        result_fn(results)
