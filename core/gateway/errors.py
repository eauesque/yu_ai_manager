from __future__ import annotations

import json

from quart import Response


class BodyTooLargeError(Exception):
    def __init__(self, limit_bytes: int) -> None:
        self.limit_bytes = limit_bytes
        super().__init__(f"body exceeds {limit_bytes} bytes")


def openai_error(
    message: str,
    code: str,
    http_status: int,
    error_type: str = "invalid_request_error",
    param: str | None = None,
) -> tuple[Response, int]:
    body: dict = {"error": {"message": message, "type": error_type, "code": code}}
    if param is not None:
        body["error"]["param"] = param
    return (
        Response(json.dumps(body, ensure_ascii=False), content_type="application/json"),
        http_status,
    )
