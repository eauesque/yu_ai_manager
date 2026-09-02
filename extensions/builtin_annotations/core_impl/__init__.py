"""File annotations core logic (AI/agent annotation storage).

Provides batch set, get, search, and delete operations for the
file_annotations table. Follows BATCH_API_STANDARD for batch endpoints.
"""

import re

from core.event_bus import emit
from core.event_bus.event_types import ANNOTATION_DELETE, ANNOTATION_SET
from core.services_core.store_utils import validate_file_ids

from .store import (
    delete_annotations_rows,
    get_annotations_rows,
    get_user_notes,
    search_annotations_rows,
    upsert_annotations_batch_commit,
)

_MAX_VALUE_LEN = 65536  # 64 KB max for value field
_SOURCE_RE = re.compile(r"^[a-z0-9_.:-]{1,64}$")
_KEY_RE = re.compile(r"^[a-z0-9_.:-]{1,128}$")


def set_annotations_batch(items: list) -> dict:
    """Upsert annotations for multiple files in one transaction."""
    candidate_ids = [
        item.get("file_id") for item in items
        if isinstance(item.get("file_id"), int) and item.get("file_id") > 0
    ]
    existing_file_ids = validate_file_ids(candidate_ids)

    valid_items: list = []
    errors: list = []
    for item in items:
        file_id = item.get("file_id")
        source = item.get("source")
        key = item.get("key")
        value = item.get("value")
        confidence = item.get("confidence")

        if not isinstance(file_id, int) or file_id <= 0:
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": "file_id must be a positive integer"})
            continue
        if not isinstance(source, str) or not source.strip():
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": "source is required"})
            continue
        if not _SOURCE_RE.match(source.strip()):
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": "source must match ^[a-z0-9_.:-]{1,64}$"})
            continue
        if not isinstance(key, str) or not key.strip():
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": "key is required"})
            continue
        if not _KEY_RE.match(key.strip()):
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": "key must match ^[a-z0-9_.:-]{1,128}$"})
            continue
        if not isinstance(value, str):
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": "value must be a string"})
            continue
        if len(value) > _MAX_VALUE_LEN:
            errors.append({"file_id": file_id, "code": "invalid_value",
                           "error": f"value exceeds {_MAX_VALUE_LEN} characters"})
            continue
        if confidence is not None:
            if not isinstance(confidence, (int, float)):
                errors.append({"file_id": file_id, "code": "invalid_value",
                               "error": "confidence must be a number or null"})
                continue
            confidence = float(confidence)
            if confidence < 0.0 or confidence > 1.0:
                errors.append({"file_id": file_id, "code": "invalid_value",
                               "error": "confidence must be 0.0-1.0"})
                continue
        if file_id not in existing_file_ids:
            errors.append({"file_id": file_id, "code": "not_found",
                           "error": "File not found"})
            continue

        valid_items.append({
            "file_id": file_id,
            "source": source.strip(),
            "key": key.strip(),
            "value": value,
            "confidence": confidence,
        })

    succeeded = upsert_annotations_batch_commit(valid_items) if valid_items else 0

    if succeeded > 0:
        emit(ANNOTATION_SET, {"count": succeeded}, source="annotations")

    return {
        "total": len(items),
        "succeeded": succeeded,
        "failed": len(errors),
        "errors": errors,
    }


def get_annotations_for_file(
    file_id: int,
    source: str | None = None,
    key: str | None = None,
) -> list[dict]:
    """Get all annotations for a file, optionally filtered by source/key."""
    return get_annotations_rows(file_id, source=source, key=key)


def search_annotations(
    source: str | None = None,
    key: str | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Search annotations by source, key, confidence range."""
    annotations, total = search_annotations_rows(
        source=source,
        key=key,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        limit=limit,
        offset=offset,
    )
    return {
        "annotations": annotations,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def delete_annotations_batch(
    source: str,
    file_ids: list[int] | None = None,
    key: str | None = None,
) -> dict:
    """Delete annotations by source, optionally for specific files/keys."""
    if not source or not isinstance(source, str):
        return {"deleted": 0}

    deleted = delete_annotations_rows(source, file_ids=file_ids, key=key)

    if deleted > 0:
        emit(ANNOTATION_DELETE, {"source": source, "count": deleted},
             source="annotations")

    return {"deleted": deleted}
