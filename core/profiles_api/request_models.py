"""Request models for profiles CRUD routes."""

from __future__ import annotations

from pydantic import Field, StrictBool, StrictStr, field_validator

from core.infra_core.api_models import ApiModel


class ProfileCreateRequest(ApiModel):
    name: StrictStr = Field(min_length=1)
    label: StrictStr | None = None
    description: StrictStr = ""
    base_config: dict | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value

class ProfileUpdateRequest(ApiModel):
    label: StrictStr | None = None
    description: StrictStr | None = None
    favorite: StrictBool | None = None

    @field_validator("favorite")
    @classmethod
    def _validate_favorite(cls, value: bool | None) -> bool | None:
        if value is None:
            raise ValueError("favorite must be a boolean")
        return value


class ProfileDuplicateRequest(ApiModel):
    new_name: StrictStr = Field(min_length=1)
    new_label: StrictStr | None = None

    @field_validator("new_name")
    @classmethod
    def _validate_new_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("new_name must not be empty")
        return value

class ProfileRenameRequest(ApiModel):
    new_name: StrictStr = Field(min_length=1)

    @field_validator("new_name")
    @classmethod
    def _validate_new_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("new_name must not be empty")
        return value
