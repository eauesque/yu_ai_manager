"""Compatibility facade for ZIP route operations."""

from core.zip_api.container_ops import get_container_members_payload
from core.zip_api.extract_ops import extract_from_zip
from core.zip_api.info_ops import get_file_info_payload, open_folder_for_file

__all__ = ["extract_from_zip", "get_container_members_payload", "get_file_info_payload", "open_folder_for_file"]
