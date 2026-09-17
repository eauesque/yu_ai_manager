"""Structured error bundle generation for QR-based bug reports."""

from core.web.error_bundle_capture import build_error_bundle, enrich_error_bundle
from core.web.error_bundle_pack import (
    build_bug_report_url,
    encode_error_bundle_gzip_base64,
    pack_error_bundle,
)

__all__ = [
    "build_bug_report_url",
    "build_error_bundle",
    "encode_error_bundle_gzip_base64",
    "enrich_error_bundle",
    "pack_error_bundle",
]
