"""@validate_request decorator -- automatic request validation with Pydantic models.

Usage::

    from core.infra_core.api_validate import validate_request

    class SetRatingRequest(ApiModel):
        file_id: FileId
        rating: Rating

    @bp.route("/api/ratings/set", methods=["POST"])
    @validate_request(SetRatingRequest)
    async def api_set_rating(*, data: SetRatingRequest):
        result = set_rating(data.file_id, data.rating)
        return api_result(result, 200)
"""

from __future__ import annotations

import contextlib
from functools import wraps

from pydantic import BaseModel, ValidationError
from quart import request

from core.infra_core.api_errors import api_error


def validate_request(model_cls: type[BaseModel]):
    """Decorator that adds Pydantic validation to Quart routes.

    GET: Builds a dict from request.args for validation.
    POST/PUT/DELETE: Validates via await request.get_json().
    On validation success, injects the model instance into kwargs["data"].
    Returns a 400 error on ValidationError.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if request.method == "GET":
                raw = dict(request.args)
                # Convert numeric strings to int/float (query params are always str)
                for key, val in raw.items():
                    if isinstance(val, str):
                        try:
                            raw[key] = int(val)
                        except ValueError:
                            with contextlib.suppress(ValueError):
                                raw[key] = float(val)
            else:
                raw = await request.get_json(silent=True)
                if raw is None:
                    return api_error(
                        "JSON body required",
                        400,
                        code="invalid_json",
                    )

            try:
                validated = model_cls.model_validate(raw)
            except ValidationError as exc:
                details = []
                for err in exc.errors():
                    loc = ".".join(str(x) for x in err["loc"])
                    details.append(f"{loc}: {err['msg']}")
                return api_error(
                    "; ".join(details),
                    400,
                    code="validation_error",
                    detail=str(exc.error_count()) + " validation error(s)",
                )

            kwargs["data"] = validated
            return await fn(*args, **kwargs)

        return wrapper

    return decorator
