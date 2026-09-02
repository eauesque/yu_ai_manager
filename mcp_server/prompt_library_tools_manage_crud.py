"""Prompt CRUD tools for Prompt Library."""


from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .prompt_library_tools_common import _PFX, as_json
from .validators import validate_prompt_id, validate_prompt_title


def _collect_prompt_fields(fields: list[tuple[str, str | None]], include_none: bool = False) -> dict:
    body = {}
    for key, value in fields:
        if include_none:
            if value is not None:
                body[key] = value
        elif value:
            body[key] = value
    return body


def register_prompt_library_crud_tools(mcp: FastMCP, client: YuManagerClient):
    """Register prompt CRUD tools."""

    @mcp.tool()
    def create_prompt(
        title: str,
        positive: str = "",
        negative: str = "",
        memo: str = "",
        seed: str = "",
        steps: str = "",
        sampler: str = "",
        cfg_scale: str = "",
        model_name: str = "",
    ) -> str:
        """Create a new prompt in the Prompt Library.

        Args:
            title: Prompt title (required)
            positive: Positive prompt text
            negative: Negative prompt text
            memo: Personal notes or memo
            seed: Generation seed value
            steps: Number of sampling steps
            sampler: Sampler name
            cfg_scale: CFG scale value
            model_name: Model/checkpoint name
        """
        err = validate_prompt_title(title)
        if err:
            return err
        body = {"title": title}
        body.update(_collect_prompt_fields([
            ("positive", positive), ("negative", negative), ("memo", memo), ("seed", seed),
            ("steps", steps), ("sampler", sampler), ("cfg_scale", cfg_scale), ("model_name", model_name),
        ]))
        return as_json(client.post(f"{_PFX}/api/prompts", body))

    @mcp.tool()
    def update_prompt(
        prompt_id: int,
        title: str | None = None,
        positive: str | None = None,
        negative: str | None = None,
        memo: str | None = None,
        seed: str | None = None,
        steps: str | None = None,
        sampler: str | None = None,
        cfg_scale: str | None = None,
        model_name: str | None = None,
    ) -> str:
        """Update an existing prompt (partial update, only provided fields change).

        Args:
            prompt_id: The prompt ID to update
            title: New title
            positive: New positive prompt
            negative: New negative prompt
            memo: New memo
            seed: New seed
            steps: New steps
            sampler: New sampler
            cfg_scale: New CFG scale
            model_name: New model name
        """
        err = validate_prompt_id(prompt_id)
        if err:
            return err
        if title is not None:
            err = validate_prompt_title(title)
            if err:
                return err
        body = _collect_prompt_fields([
            ("title", title), ("positive", positive), ("negative", negative), ("memo", memo),
            ("seed", seed), ("steps", steps), ("sampler", sampler), ("cfg_scale", cfg_scale), ("model_name", model_name),
        ], include_none=True)
        if not body:
            return as_json({"ok": False, "error": "No fields to update"})
        return as_json(client.put(f"{_PFX}/api/prompts/{prompt_id}", body))

    @mcp.tool()
    def delete_prompt(prompt_id: int) -> str:
        """Delete a prompt from the Prompt Library.

        Args:
            prompt_id: The prompt ID to delete
        """
        err = validate_prompt_id(prompt_id)
        if err:
            return err
        return as_json(client.delete(f"{_PFX}/api/prompts/{prompt_id}"))
