"""Compatibility facade for file detail/conversion helpers."""

from core.file_api.convert_ops import convert_prompt_payload
from core.file_api.detail_payload import build_file_detail_payload

__all__ = ["build_file_detail_payload", "convert_prompt_payload"]
