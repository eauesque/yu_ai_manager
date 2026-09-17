import logging

from .s2t_batch_local import save_transcript, transcribe_single, unlink_if_exists

logger = logging.getLogger(__name__)


def has_remote_workers() -> bool:
    from core.mesh_inference import get_router

    router = get_router()
    if router is None:
        return False
    peers = router._get_available_peers("whisper")
    local_id = router._local_peer.peer_id
    return any(p.peer_id != local_id for p in peers)


def run_distributed_batch(file_ids, paths_map, backend, language, extract_audio_wav, save_fn, started_at, emit_progress):
    """Transcribe files using mesh InferenceRouter with per-file (batch_size=1) dispatch."""
    from core.mesh_inference import get_router
    from core.mesh_inference.dispatch_sync import dispatch_inference_sync

    router = get_router()
    if router is None:
        return None

    processed = 0
    errors = 0
    total = len(file_ids)
    local_peer_id = router._local_peer.peer_id

    # Items are plain file_ids; worker_fn resolves path and wav extraction inline.
    async def worker_fn(peer, batch):
        results = []
        drop_counts: dict[str, int] = {}
        for file_id in batch:
            path = paths_map.get(file_id)
            if not path:
                drop_counts["missing_path"] = drop_counts.get("missing_path", 0) + 1
                results.append((file_id, None))
                continue
            if peer.peer_id == local_peer_id:
                # Local transcription — synchronous helper, run directly.
                done, failed = transcribe_single(file_id, paths_map, backend, language, extract_audio_wav, save_fn)
                results.append((file_id, "ok" if done else None))
            else:
                from core.mesh_inference._imports import whisper_transcribe_remote
                wav_path = extract_audio_wav(path)
                if wav_path is None:
                    drop_counts["extract_failed"] = drop_counts.get("extract_failed", 0) + 1
                    results.append((file_id, None))
                    continue
                try:
                    result = await whisper_transcribe_remote(peer, wav_path, language)
                    transcript = _remote_transcript_from_result(result)
                    if transcript is not None:
                        text, segments, backend_name = transcript
                        save_transcript(file_id, text, segments, backend_name, save_fn)
                        results.append((file_id, "ok"))
                    else:
                        reason = _remote_drop_reason(result)
                        drop_counts[reason] = drop_counts.get(reason, 0) + 1
                        results.append((file_id, None))
                except Exception as exc:
                    drop_counts["worker_exception"] = drop_counts.get("worker_exception", 0) + 1
                    logger.exception("Remote S2T peer=%s failed fid=%d: %s", peer.peer_id, file_id, exc)
                    results.append((file_id, None))
                finally:
                    unlink_if_exists(wav_path)
        _log_remote_dropped("Distributed S2T result", drop_counts, peer.peer_id)
        return results

    def result_fn(results):
        nonlocal processed, errors
        for _file_id, status in results:
            if status == "ok":
                processed += 1
            else:
                errors += 1
        emit_progress(processed, errors, total, started_at)

    dispatch_inference_sync(
        router, "whisper", file_ids,
        batch_size=1, mode="parallel",
        worker_fn=worker_fn, result_fn=result_fn,
    )
    return {"processed": processed, "errors": errors}


def _remote_transcript_from_result(result):
    if not isinstance(result, dict):
        return None
    ok_value = result.get("ok")
    if ok_value is False:
        return None
    if ok_value is not True and result.get("status") != "ok":
        return None

    text = result.get("text")
    segments = result.get("segments")
    if not isinstance(text, str) or not isinstance(segments, list):
        return None

    backend_name = result.get("backend") or result.get("model") or "remote"
    if not isinstance(backend_name, str):
        backend_name = "remote"
    return text, segments, backend_name


def _remote_drop_reason(result) -> str:
    if not isinstance(result, dict):
        return "none_or_non_dict"
    if result.get("ok") is False:
        return "ok_false"
    if result.get("ok") is not True and result.get("status") != "ok":
        return "not_success"
    if not isinstance(result.get("text"), str):
        return f"invalid_text_{type(result.get('text')).__name__}"
    if not isinstance(result.get("segments"), list):
        return f"invalid_segments_{type(result.get('segments')).__name__}"
    return "invalid_result"


def _log_remote_dropped(context: str, counts: dict[str, int], peer_id: str) -> None:
    counts = {reason: count for reason, count in counts.items() if count}
    if not counts:
        return
    total = sum(counts.values())
    breakdown = ", ".join(f"{reason}={count}" for reason, count in sorted(counts.items()))
    logger.warning("%s dropped %d items peer=%s: %s", context, total, peer_id, breakdown)
