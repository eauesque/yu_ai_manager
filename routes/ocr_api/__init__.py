"""OCR API routes package.

Defines the Blueprint and registers routes from each feature module.
The pure-service implementations live in ``core/ocr_api/``; this file
just owns the Blueprint and wires the per-domain ``register(bp)``
callables onto it.
"""

from quart import Blueprint

bp = Blueprint("ocr", __name__)

from core.ocr_api import (
    benchmark_ops,
    export_ops,
    media_ops,
    single_ops,
    translate_ops,
)

single_ops.register(bp)
export_ops.register(bp)
translate_ops.register(bp)
benchmark_ops.register(bp)
media_ops.register(bp)
