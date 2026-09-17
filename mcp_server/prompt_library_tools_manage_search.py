"""Search and read tools for Prompt Library."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .prompt_library_tools_common import _PFX, as_json
from .validators import validate_prompt_id, validate_prompt_sort, validate_search_limit


def register_prompt_library_search_tools(mcp: FastMCP, client: YuManagerClient):
    """Register search and read tools."""

    @mcp.tool()
    def search_prompts(
        query: str = "",
        folder_id: int = 0,
        tag_id: int = 0,
        sort: str = "updated_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """Search saved prompts in the Prompt Library.

        Args:
            query: Full-text search across title, positive, negative, memo
            folder_id: Filter by folder (0 = all folders)
            tag_id: Filter by library tag (0 = all tags)
            sort: Sort field (updated_at|created_at|title)
            order: Sort direction (asc|desc)
            limit: Max results per page (1-200, default 50)
            offset: Skip first N results
        """
        err = validate_prompt_sort(sort)
        if err:
            return err
        limit, _ = validate_search_limit(limit)
        params = {"sort": sort, "order": order, "limit": str(limit), "offset": str(offset)}
        if query:
            params["q"] = query
        if folder_id > 0:
            params["folder_id"] = str(folder_id)
        if tag_id > 0:
            params["tag_id"] = str(tag_id)
        return as_json(client.get(f"{_PFX}/api/prompts", params))

    @mcp.tool()
    def get_prompt(prompt_id: int) -> str:
        """Get a single prompt by ID with its folders and tags.

        Args:
            prompt_id: The prompt ID to retrieve
        """
        err = validate_prompt_id(prompt_id)
        if err:
            return err
        return as_json(client.get(f"{_PFX}/api/prompts/{prompt_id}"))
