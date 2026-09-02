import json
import logging
import os

logger = logging.getLogger(__name__)


def transcribe_single(fid, paths_map, backend, language, extract_fn, save_fn):
    import wave

    import numpy as np

    video_path = paths_map.get(fid)
    if not video_path:
        return 0, 1
    wav_path = extract_fn(video_path)
    if wav_path is None:
        return 0, 1
    try:
        with wave.open(wav_path, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        audio_data = np.frombuffer(raw, dtype=np.int16)
        segments = backend.transcribe(audio_data, language=language)
        full_text = " ".join(seg["text"] for seg in segments).strip()
        save_transcript(fid, full_text, segments, backend.name, save_fn)
        return 1, 0
    except Exception:
        logger.exception("Batch S2T failed for file_id=%d", fid)
        return 0, 1
    finally:
        unlink_if_exists(wav_path)


def save_transcript(fid, full_text, segments, backend_name, save_fn):
    save_fn(
        [
            {"file_id": fid, "source": "s2t", "key": "transcript", "value": full_text, "confidence": None},
            {"file_id": fid, "source": "s2t", "key": "transcript_segments", "value": json.dumps(segments, ensure_ascii=False), "confidence": None},
            {"file_id": fid, "source": "s2t", "key": "transcript_backend", "value": backend_name, "confidence": None},
        ]
    )


def unlink_if_exists(path: str | None) -> None:
    try:
        if path:
            os.unlink(path)
    except OSError:
        pass
