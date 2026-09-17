"""Pydantic-based API model foundation.

Used for type-safe API request/response definitions.
Each route module imports base classes and common types from here.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Base class for all API models.

    - extra="forbid" rejects unknown fields
    - populate_by_name=True accepts both alias and Python field names
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


# --- Common type aliases ---

FileId = Annotated[int, Field(gt=0, description="ファイル ID (正の整数)")]
Rating = Annotated[int, Field(ge=0, le=5, description="レーティング (0=クリア, 1-5)")]
PageLimit = Annotated[int, Field(ge=1, le=1000, default=100, description="ページサイズ")]
PageOffset = Annotated[int, Field(ge=0, default=0, description="オフセット")]
Confidence = Annotated[float, Field(ge=0.0, le=1.0, description="信頼度 (0.0-1.0)")]


# --- Common request models ---


class FileIdParam(ApiModel):
    """Request that accepts only file_id."""

    file_id: FileId


class FileIdsParam(ApiModel):
    """Request that accepts a list of file_ids."""

    file_ids: list[FileId]


class PaginationParam(ApiModel):
    """Pagination parameters."""

    limit: PageLimit = 100
    offset: PageOffset = 0


# --- Common response models ---


class BatchResult(BaseModel):
    """Result of a batch operation."""

    total: int
    succeeded: int
    failed: int
    errors: list[dict[str, Any]] = []


# --- Utilities ---


def model_to_dict(model: BaseModel) -> dict:
    """Convert a Pydantic model to a serializable dict."""
    return model.model_dump(exclude_none=True)
