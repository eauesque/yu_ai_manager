"""Shared result, executor, and tool definitions for agent loops."""

from __future__ import annotations

from typing import Any


class AgentResult:
    """Result of an agent loop execution."""

    __slots__ = ("content", "model", "steps", "rounds")

    def __init__(self, content: str, model: str, steps: list[dict], rounds: int):
        self.content = content
        self.model = model
        self.steps = steps
        self.rounds = rounds

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "model": self.model,
            "steps": self.steps,
            "rounds": self.rounds,
        }


class ToolExecutor:
    """Base class for tool execution."""

    async def execute(self, name: str, arguments: dict) -> Any:
        raise NotImplementedError


class LocalAPIExecutor(ToolExecutor):
    """Execute tools by calling the local REST API."""

    def __init__(self, base_url: str = "http://127.0.0.1:5000", auth_headers: dict[str, str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.auth_headers = auth_headers or {}

    async def execute(self, name: str, arguments: dict) -> Any:
        import re as _re

        import httpx

        endpoint = TOOL_API_MAP.get(name)
        if not endpoint:
            return {"error": f"Unknown tool: {name}"}

        method, path_template = endpoint
        path_params = set(_re.findall(r"\{(\w+)\}", path_template))
        path = path_template.format(
            **{key: arguments[key] for key in path_params if key in arguments}
        )
        body = {key: value for key, value in arguments.items() if key not in path_params}
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        headers.update(self.auth_headers)

        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                if method == "GET":
                    params = {key: str(value) for key, value in body.items()}
                    response = await http.get(url, params=params, headers=headers)
                else:
                    response = await http.request(method, url, json=body, headers=headers)
                return response.json()
        except Exception as exc:
            return {"error": str(exc)}


TOOL_API_MAP: dict[str, tuple[str, str]] = {
    "search_files": ("GET", "/api/search"),
    "get_file_info": ("GET", "/api/files/{file_id}"),
    "get_file_tags": ("GET", "/api/files/{file_id}/tags"),
    "list_scan_roots": ("GET", "/api/scan-roots"),
    "get_stats": ("GET", "/api/stats"),
    "get_server_info": ("GET", "/api/server-info"),
    "list_collections": ("GET", "/api/collections"),
    "list_llm_endpoints": ("GET", "/api/settings/llm-endpoints"),
    "get_server_mode": ("GET", "/api/server/mode"),
    "set_tags": ("POST", "/api/tags/batch-set"),
    "add_to_collection": ("POST", "/api/collections/{collection_id}/batch-add"),
    "remove_from_collection": ("POST", "/api/collections/{collection_id}/batch-remove"),
    "create_collection": ("POST", "/api/collections"),
    "rate_image": ("POST", "/api/ratings/set"),
    "toggle_favorite": ("POST", "/api/favorites/toggle"),
}


def _tool(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        },
    }


_READ_TOOLS: list[dict] = [
    _tool("search_files", "Search files by tag query", {
        "q": {"type": "string", "description": "Tag search query"},
        "limit": {"type": "integer", "description": "Max results (default 20)"},
    }, ["q"]),
    _tool("get_file_info", "Get detailed info about a file by ID", {
        "file_id": {"type": "integer", "description": "File ID"},
    }, ["file_id"]),
    _tool("get_file_tags", "Get all tags for a file", {
        "file_id": {"type": "integer", "description": "File ID"},
    }, ["file_id"]),
    _tool("list_scan_roots", "List registered scan root directories", {}, []),
    _tool("get_stats", "Get database statistics (file count, tag count, etc.)", {}, []),
    _tool("get_server_info", "Get server status (uptime, version, mode)", {}, []),
    _tool("list_collections", "List all collections", {}, []),
    _tool("list_llm_endpoints", "List configured LLM endpoints", {}, []),
    _tool("get_server_mode", "Get current server mode", {}, []),
]


_WRITE_TOOLS: list[dict] = [
    _tool("set_tags", "Add or remove tags on files", {
        "items": {
            "type": "array",
            "description": "Array of {file_id, add: [tags], remove: [tags]}",
            "items": {"type": "object"},
        },
    }, ["items"]),
    _tool("add_to_collection", "Add files to a collection", {
        "collection_id": {"type": "integer", "description": "Collection ID"},
        "file_ids": {"type": "array", "description": "Array of file IDs to add", "items": {"type": "integer"}},
    }, ["collection_id", "file_ids"]),
    _tool("remove_from_collection", "Remove files from a collection", {
        "collection_id": {"type": "integer", "description": "Collection ID"},
        "file_ids": {"type": "array", "description": "Array of file IDs to remove", "items": {"type": "integer"}},
    }, ["collection_id", "file_ids"]),
    _tool("create_collection", "Create a new collection", {
        "name": {"type": "string", "description": "Collection name"},
    }, ["name"]),
    _tool("rate_image", "Set rating for a file (0=clear, 1-5=rating)", {
        "file_id": {"type": "integer", "description": "File ID"},
        "rating": {"type": "integer", "description": "Rating 0-5"},
    }, ["file_id", "rating"]),
    _tool("toggle_favorite", "Toggle a file as favorite", {
        "file_id": {"type": "integer", "description": "File ID"},
    }, ["file_id"]),
]


def get_default_tools() -> list[dict]:
    return _READ_TOOLS[:]


def get_all_tools() -> list[dict]:
    return _READ_TOOLS + _WRITE_TOOLS
