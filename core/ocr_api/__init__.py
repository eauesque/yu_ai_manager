"""OCR API service layer.

Pure-service modules (route registration callables, helpers) used by
``routes/ocr_api/`` Blueprint host. Each ``*_ops`` module exposes a
``register(bp)`` callable that attaches its handlers to the parent
Blueprint owned by routes/.
"""

from core.ocr_api import (
    benchmark_ops,
    export_batch,
    export_ops,
    helpers,
    media_ops,
    single_ops,
    translate_ops,
)

__all__ = [
    "benchmark_ops",
    "export_batch",
    "export_ops",
    "helpers",
    "media_ops",
    "single_ops",
    "translate_ops",
]
