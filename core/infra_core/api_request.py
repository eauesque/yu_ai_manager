"""Request parsing helpers for API endpoints."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError


async def require_json_dict(request: Any) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], int] | None]:
    """Require a valid JSON object body, otherwise return error payload and status."""
    if not getattr(request, "is_json", False):
        return None, ({"error": "JSON body is required", "code": "invalid_content_type"}, 400)
    data = await request.get_json(silent=True)
    if data is None:
        return None, ({"error": "Invalid JSON body", "code": "invalid_json"}, 400)
    if not isinstance(data, dict):
        return None, ({"error": "JSON object body is required", "code": "invalid_json_object"}, 400)
    return data, None


T = TypeVar("T", bound=BaseModel)


def validate_json_model(model_cls: type[T], raw: dict[str, Any]) -> tuple[T | None, tuple[dict[str, Any], int] | None]:
    """Validate a JSON object against a Pydantic model."""
    try:
        return model_cls.model_validate(raw), None
    except ValidationError as exc:
        details = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err["loc"])
            details.append(f"{loc}: {err['msg']}")
        return None, ({
            "error": "; ".join(details),
            "code": "validation_error",
            "detail": f"{exc.error_count()} validation error(s)",
        }, 400)


async def require_json_model(request: Any, model_cls: type[T]) -> tuple[T | None, tuple[dict[str, Any], int] | None]:
    """Require a JSON object body and validate it against a Pydantic model."""
    data, err = await require_json_dict(request)
    if err:
        return None, err
    assert data is not None
    return validate_json_model(model_cls, data)
