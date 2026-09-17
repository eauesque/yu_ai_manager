"""Re-exports from builtin_lan_cowork worker_client with lazy path setup.

Provides stable import names for remote inference functions. Each wrapper
ensures the extension is on sys.path before delegating to the real
implementation in core_impl.inference.worker_client.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Absolute path to the builtin_lan_cowork package directory
_EXT_ROOT = Path(__file__).resolve().parent.parent.parent / "extensions" / "builtin_lan_cowork"


def _ensure_ext_path() -> None:
    """Add the extension root to sys.path if not already present."""
    ext_str = str(_EXT_ROOT)
    if ext_str not in sys.path:
        sys.path.insert(0, ext_str)


async def clip_encode_remote(peer: Any, image_paths: list[str], **kw: Any) -> Any:
    """Encode images via CLIP on a remote peer.

    Delegates to core_impl.inference.worker_client.clip_encode_remote.
    """
    _ensure_ext_path()
    from core_impl.inference.worker_client import clip_encode_remote as _fn
    return await _fn(peer, image_paths, **kw)


async def yolo_detect_remote(peer: Any, image_paths: list[str], **kw: Any) -> Any:
    """Run YOLO object detection on images via a remote peer.

    Delegates to core_impl.inference.worker_client.yolo_detect_remote.
    """
    _ensure_ext_path()
    from core_impl.inference.worker_client import yolo_detect_remote as _fn
    return await _fn(peer, image_paths, **kw)


async def whisper_transcribe_remote(peer: Any, wav_path: str, **kw: Any) -> Any:
    """Transcribe audio via Whisper on a remote peer.

    Delegates to core_impl.inference.worker_client.whisper_transcribe_remote.
    """
    _ensure_ext_path()
    from core_impl.inference.worker_client import whisper_transcribe_remote as _fn
    return await _fn(peer, wav_path, **kw)


async def tagger_tag_remote(peer: Any, image_path: str, **kw: Any) -> Any:
    """Tag a single image via WD-Tagger on a remote peer.

    Delegates to core_impl.inference.worker_client.tagger_tag_remote.
    """
    _ensure_ext_path()
    from core_impl.inference.worker_client import tagger_tag_remote as _fn
    return await _fn(peer, image_path, **kw)


async def llm_chat_remote(peer: Any, messages: list[Any], **kw: Any) -> Any:
    """Send LLM chat request to remote peer via mesh.

    Delegates to core_impl.inference.worker_client.llm_chat_remote.
    Returns a response dict or None.
    """
    _ensure_ext_path()
    from core_impl.inference.worker_client import llm_chat_remote as _fn
    return await _fn(peer, messages, **kw)
