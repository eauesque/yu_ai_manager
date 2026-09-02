"""Request models for AI server CRUD routes and services."""

from __future__ import annotations

from typing import Any

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator

from core.infra_core.api_models import ApiModel

from .server_model_data import VALID_TYPES


class AnalysisServerCreateRequest(ApiModel):
    id: StrictStr | None = None
    name: StrictStr = Field(min_length=1)
    type: StrictStr
    priority: StrictInt | None = None
    enabled: StrictBool = True
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Server name is required")
        return value

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        if value not in VALID_TYPES:
            raise ValueError(f"Invalid type: {value}")
        return value


class AnalysisServerUpdateRequest(ApiModel):
    name: StrictStr | None = None
    type: StrictStr | None = None
    priority: StrictInt | None = None
    enabled: StrictBool | None = None
    config: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Server name is required")
        return value

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in VALID_TYPES:
            raise ValueError(f"Invalid type: {value}")
        return value


class AnalysisServerReorderRequest(ApiModel):
    server_ids: list[str]
