"""Coordinator for mesh-based tagger batch dispatch."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_IN_CHUNK_SIZE = 500


def _tagger_batch_coordinator(job, file_ids, limit, force, threshold):
    try:
        from core.mesh_inference import dispatch_sync as facade
        from core.mesh_inference.tagger_store import save_tagger_tags_batch
        from core.services_core.db_state import get_readonly_db

        targets = list(file_ids) if file_ids else facade.get_untagged_file_ids(limit=limit)

        if not targets:
            job.complete("No files to tag")
            return

        if not force:
            targets = facade._filter_untagged(targets)
            if not targets:
                job.complete("All files already tagged")
                return

        items: list[tuple[int, str]] = []
        for fid, fp in _iter_active_paths(get_readonly_db(), targets):
            if not Path(fp).exists():
                continue
            items.append((fid, fp))

        if not items:
            job.complete("No accessible files to tag")
            return

        total = len(items)
        job.update(phase="tagger_mesh", message=f"Tagger mesh: 0/{total} (tagged=0, empty=0, errors=0)")
        job.progress(0, total)

        router = facade.get_router()
        if router is None:
            job.fail("Mesh router not available")
            return

        try:
            available = router.get_available_peers("tagger")
        except Exception as exc:
            logger.error("get_available_peers failed: %s", exc)
            available = []
        if not available:
            job.fail("no_enabled_peers: all tagger peers are disabled")
            return

        stats = {"tagged": 0, "empty": 0, "errors": 0, "done": 0}
        stats_lock = asyncio.Lock()

        local_peer_id: str = ""
        try:
            import sys

            ext_path = str(Path(__file__).resolve().parent.parent.parent / "extensions" / "builtin_lan_cowork")
            if ext_path not in sys.path:
                sys.path.insert(0, ext_path)
            from lan_cowork_ext import _get_manager  # type: ignore[import]

            mgr = _get_manager()
            if mgr is not None:
                local_peer_id = mgr.local_peer.peer_id
        except Exception as exc:
            logger.debug("Could not resolve local_peer_id: %s", exc)

        async def _worker_fn(peer: Any, batch: list[tuple[int, str]]) -> list[Any]:
            results = []
            write_batch: list[tuple[int, list[dict], str]] = []
            drop_counts: dict[str, int] = {}

            async def _add_stats(**increments: int) -> tuple[int, int, int, int]:
                async with stats_lock:
                    for key, value in increments.items():
                        stats[key] += value
                    if stats["tagged"] + stats["empty"] + stats["errors"] != stats["done"]:
                        raise RuntimeError("Tagger mesh accounting invariant violated")
                    done = stats["done"]
                    tagged = stats["tagged"]
                    empty = stats["empty"]
                    errors = stats["errors"]
                return done, tagged, empty, errors

            def _emit_progress(done: int, tagged: int, empty: int, errors: int) -> None:
                job.progress(done, total)
                job.update(message=f"Tagger mesh: {done}/{total} (tagged={tagged}, empty={empty}, errors={errors})")

            for fid, fp in batch:
                try:
                    if peer.peer_id == local_peer_id:
                        raw_tags = await asyncio.get_event_loop().run_in_executor(
                            None, facade._tag_local, fp, threshold
                        )
                    else:
                        from core.mesh_inference._imports import tagger_tag_remote

                        raw_tags = await tagger_tag_remote(peer, fp)

                    filtered, drop_reason = _filter_valid_tagger_tags(raw_tags, threshold)
                    if drop_reason is not None:
                        drop_counts[drop_reason] = drop_counts.get(drop_reason, 0) + 1
                        done, tagged, empty, errors = await _add_stats(errors=1, done=1)
                        _emit_progress(done, tagged, empty, errors)
                    elif filtered:
                        write_batch.append((fid, filtered, f"mesh:{peer.name}"))
                    else:
                        done, tagged, empty, errors = await _add_stats(empty=1, done=1)
                        _emit_progress(done, tagged, empty, errors)
                except Exception as exc:
                    logger.error("Tagger mesh error peer=%s file_id=%d: %s", peer.name, fid, exc)
                    drop_counts["worker_exception"] = drop_counts.get("worker_exception", 0) + 1
                    done, tagged, empty, errors = await _add_stats(errors=1, done=1)
                    _emit_progress(done, tagged, empty, errors)
                results.append(fid)
            if write_batch:
                try:
                    saved = save_tagger_tags_batch(write_batch)
                    if saved is False:
                        raise RuntimeError("save_tagger_tags_batch returned False")
                except Exception as exc:
                    failed = len(write_batch)
                    drop_counts["save_fail"] = drop_counts.get("save_fail", 0) + failed
                    logger.error("Tagger mesh batch write failed peer=%s items=%d: %s", peer.name, failed, exc)
                    done, tagged, empty, errors = await _add_stats(errors=failed, done=failed)
                    _emit_progress(done, tagged, empty, errors)
                else:
                    saved_count = len(write_batch)
                    done, tagged, empty, errors = await _add_stats(tagged=saved_count, done=saved_count)
                    _emit_progress(done, tagged, empty, errors)
            _log_tagger_dropped("Distributed Tagger result", drop_counts)
            async with stats_lock:
                done = stats["done"]
                tagged = stats["tagged"]
                empty = stats["empty"]
                errors = stats["errors"]
            job.update(message=f"Tagger mesh: {done}/{total} (tagged={tagged}, empty={empty}, errors={errors})")
            return results

        def _progress_fn(processed: int, _total: int) -> None:
            return None

        asyncio.run(
            router.dispatch_inference(
                "tagger",
                items,
                batch_size=8,
                worker_fn=_worker_fn,
                progress_fn=_progress_fn,
            )
        )

        s = stats
        job.complete(f"Tagger mesh complete: {s['tagged']} tagged, {s['empty']} empty, {s['errors']} errors")
    except Exception as exc:
        logger.error("Tagger mesh coordinator error: %s", exc)
        job.fail(str(exc))


def _iter_active_paths(con, file_ids):
    for index in range(0, len(file_ids), _IN_CHUNK_SIZE):
        chunk = file_ids[index : index + _IN_CHUNK_SIZE]
        if not chunk:
            continue
        placeholders = ",".join("?" for _ in chunk)
        cursor = con.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders}) AND is_deleted = 0",
            chunk,
        )
        by_id = {int(row["id"]): row["path"] for row in cursor}
        for fid in chunk:
            path = by_id.get(int(fid))
            if path:
                yield int(fid), path


def _filter_valid_tagger_tags(raw_tags: Any, threshold: float) -> tuple[list[dict], str | None]:
    if raw_tags is None:
        return [], "none"
    if not isinstance(raw_tags, list):
        return [], "not_list"

    filtered: list[dict] = []
    for index, item in enumerate(raw_tags):
        if not isinstance(item, dict):
            return [], f"invalid_item_{index}"
        tag = item.get("tag")
        confidence = item.get("confidence")
        if not isinstance(tag, str) or not tag:
            return [], f"invalid_tag_{index}"
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return [], f"invalid_confidence_{index}"
        if confidence >= threshold:
            filtered.append({"tag": tag, "confidence": float(confidence)})
    return filtered, None


def _log_tagger_dropped(context: str, counts: dict[str, int]) -> None:
    counts = {reason: count for reason, count in counts.items() if count}
    if not counts:
        return
    total = sum(counts.values())
    breakdown = ", ".join(f"{reason}={count}" for reason, count in sorted(counts.items()))
    logger.warning("%s dropped %d items: %s", context, total, breakdown)
