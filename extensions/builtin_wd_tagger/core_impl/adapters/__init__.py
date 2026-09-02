"""Tagger adapter family modules.

Each adapter family (wd / camie / generic_onnx / vlm) implements the
TaggerAdapter ABC defined in base.py. The FAMILY_REGISTRY maps the
``adapter_family`` string from a TaggerProfile JSON to the concrete
adapter class.

engine_factory uses ``get_adapter_class(profile.adapter_family)`` to
build the right adapter for a given profile.
"""
from __future__ import annotations

from .base import TaggerAdapter
from .camie_adapter import CamieAdapter
from .generic_onnx_adapter import GenericOnnxAdapter
from .wd_adapter import WdAdapter

# Family name → adapter class. Note: VLM is dispatched separately by
# engine_factory (engine_type=vlm path) and not registered here.
FAMILY_REGISTRY: dict[str, type[TaggerAdapter]] = {
    "wd": WdAdapter,
    "camie": CamieAdapter,
    "generic_onnx": GenericOnnxAdapter,
}


def get_adapter_class(family: str) -> type[TaggerAdapter]:
    """Look up the adapter class for an adapter_family string.

    Raises LookupError if the family is not registered.
    """
    try:
        return FAMILY_REGISTRY[family]
    except KeyError as exc:
        raise LookupError(
            f"unknown adapter_family={family!r}. "
            f"Known: {sorted(FAMILY_REGISTRY)}"
        ) from exc


__all__ = ["FAMILY_REGISTRY", "TaggerAdapter", "get_adapter_class"]
