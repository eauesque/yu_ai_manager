"""Hailo-specific indexer wrapper.

Thin wrapper that injects the Hailo encoder and Hailo preprocessing
into the generic ``core.clip_core.indexer``.

Also re-exports status/stop functions for backward compatibility.
"""


from core.clip_core.indexer import get_index_status, stop_indexing  # noqa: F401


def start_indexing(batch_size: int = 32, hef_dir: str | None = None) -> dict:
    """Start background indexing with the Hailo encoder.

    Args:
        batch_size: Number of images per batch.
        hef_dir: Directory containing HEF files. Defaults to ~/hailo_models.
    """
    from core.clip_core.indexer import start_indexing as _start

    from .hailo_inference import get_encoder
    from .image_preprocess import preprocess_image

    def _hailo_factory():
        return get_encoder(hef_dir)

    return _start(
        batch_size=batch_size,
        encoder_factory=_hailo_factory,
        preprocess_fn=preprocess_image,
    )
