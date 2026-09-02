"""Async HTTP client facade for remote mesh inference workers."""

from __future__ import annotations

from .worker_client_clip import clip_encode_remote
from .worker_client_llm import llm_chat_remote
from .worker_client_tagger import tagger_tag_remote
from .worker_client_transport import (
    DEFAULT_BOUNDARY as _DEFAULT_BOUNDARY,
)
from .worker_client_transport import (
    IMAGE_EXTS,
    build_multipart_images,
)
from .worker_client_transport import (
    MIME_MAP as _MIME_MAP,
)
from .worker_client_transport import (
    USER_AGENT as _USER_AGENT,
)
from .worker_client_transport import (
    YOLO_REMOTE_CHUNK as _YOLO_REMOTE_CHUNK,
)
from .worker_client_whisper import whisper_transcribe_remote
from .worker_client_yolo import yolo_detect_remote

__all__ = [
    "IMAGE_EXTS",
    "_DEFAULT_BOUNDARY",
    "_MIME_MAP",
    "_USER_AGENT",
    "_YOLO_REMOTE_CHUNK",
    "build_multipart_images",
    "clip_encode_remote",
    "llm_chat_remote",
    "tagger_tag_remote",
    "whisper_transcribe_remote",
    "yolo_detect_remote",
]
