"""OpenAPI 3.1 schema auto-generation.

Generates an OpenAPI schema from models registered via @validate_request
and serves it at GET /api/openapi.json.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from quart import Blueprint, jsonify

logger = logging.getLogger(__name__)

bp = Blueprint("openapi", __name__)

_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "VERSION"
_cached_version: str | None = None


def _get_version() -> str:
    global _cached_version
    if _cached_version is not None:
        return _cached_version
    try:
        _cached_version = _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        _cached_version = "unknown"
    return _cached_version

# Registered endpoint information
_endpoints: list[dict[str, Any]] = []


def register_endpoint(
    path: str,
    method: str,
    request_model: type[BaseModel] | None = None,
    response_model: type[BaseModel] | None = None,
    summary: str = "",
    tags: list[str] | None = None,
) -> None:
    """Register an endpoint in the OpenAPI document."""
    _endpoints.append({
        "path": path,
        "method": method.lower(),
        "request_model": request_model,
        "response_model": response_model,
        "summary": summary,
        "tags": tags or [],
    })


def _model_to_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """Generate JSON Schema from a Pydantic model."""
    return model_cls.model_json_schema(mode="serialization")


def generate_openapi_spec() -> dict[str, Any]:
    """Generate an OpenAPI 3.1 specification from registered endpoints."""
    paths: dict[str, Any] = {}
    components_schemas: dict[str, Any] = {}

    for ep in _endpoints:
        path = ep["path"]
        method = ep["method"]

        operation: dict[str, Any] = {}
        if ep["summary"]:
            operation["summary"] = ep["summary"]
        if ep["tags"]:
            operation["tags"] = ep["tags"]

        # Request body
        req_model = ep.get("request_model")
        if req_model and method in ("post", "put", "patch", "delete"):
            schema_name = req_model.__name__
            components_schemas[schema_name] = _model_to_schema(req_model)
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{schema_name}"}
                    }
                },
            }
        elif req_model and method == "get":
            # Expand as GET query parameters
            schema = _model_to_schema(req_model)
            params = []
            for prop_name, prop_schema in schema.get("properties", {}).items():
                required = prop_name in schema.get("required", [])
                params.append({
                    "name": prop_name,
                    "in": "query",
                    "required": required,
                    "schema": prop_schema,
                })
            if params:
                operation["parameters"] = params

        # Response
        resp_model = ep.get("response_model")
        if resp_model:
            schema_name = resp_model.__name__
            components_schemas[schema_name] = _model_to_schema(resp_model)
            operation["responses"] = {
                "200": {
                    "description": "Success",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{schema_name}"}
                        }
                    },
                }
            }
        else:
            operation["responses"] = {
                "200": {"description": "Success"},
            }

        if path not in paths:
            paths[path] = {}
        paths[path][method] = operation

    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "YU AI Manager API",
            "version": _get_version(),
            "description": "AI 画像メタデータ管理 API",
        },
        "paths": paths,
    }

    if components_schemas:
        spec["components"] = {"schemas": components_schemas}

    return spec


@bp.route("/api/openapi.json")
async def api_openapi_spec():
    """Return the OpenAPI 3.1 specification as JSON."""
    return jsonify(generate_openapi_spec())
