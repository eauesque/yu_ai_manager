"""Project and export tools for LoRA dataset MCP integration."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .lora_dataset_tools_common import as_json


def register_lora_dataset_project_tools(mcp: FastMCP, client: YuManagerClient):
    """Register LoRA dataset project and export tools."""

    @mcp.tool()
    def list_lora_projects() -> str:
        """List all LoRA dataset projects with file counts."""
        return as_json(client.get("/ext/lora-dataset/projects"))

    @mcp.tool()
    def get_lora_project(project_id: int) -> str:
        """Get details of a LoRA dataset project.

        Args:
            project_id: Project ID
        """
        return as_json(client.get(f"/ext/lora-dataset/projects/{project_id}"))

    @mcp.tool()
    def create_lora_project(
        name: str,
        concept: str,
        base_model: str = "sdxl",
        repeat: int = 10,
        model_scope: str = "active",
    ) -> str:
        """Create a new LoRA dataset project.

        Args:
            name: Project name (e.g. 'my_character_lora')
            concept: Concept name used as kohya_ss folder name (e.g. '1girl white_hair')
            base_model: 'sd15' or 'sdxl' (default: sdxl)
            repeat: Repeat count for kohya_ss folder prefix (default: 10)
            model_scope: 'active' | 'all' | '<model_id>' (default: active)
        """
        return as_json(
            client.post(
                "/ext/lora-dataset/projects",
                {
                    "name": name,
                    "concept": concept,
                    "base_model": base_model,
                    "repeat": repeat,
                    "model_scope": model_scope,
                },
            )
        )

    @mcp.tool()
    def update_lora_project(
        project_id: int,
        file_ids: list | None = None,
        tag_exclude: list | None = None,
        model_scope: str = "",
        tag_preset: str = "",
        search_query: str = "",
        repeat: int = 0,
        name: str = "",
        concept: str = "",
    ) -> str:
        """Update a LoRA dataset project.

        Only non-empty / non-zero values are sent to the server.

        Args:
            project_id: Project ID
            file_ids: List of file IDs to include in the dataset
            tag_exclude: List of tag names to exclude from captions
            model_scope: 'active' | 'all' | '<model_id>'
            tag_preset: Name of an existing tag preset to apply
            search_query: Search query used to populate the project file list
            repeat: Repeat count for kohya_ss folder prefix (1-999; 0 = unchanged)
            name: New project name
            concept: New concept string (kohya_ss folder name)
        """
        payload: dict = {}
        if file_ids is not None:
            payload["file_ids"] = file_ids
        if tag_exclude is not None:
            payload["tag_exclude"] = tag_exclude
        if model_scope:
            payload["model_scope"] = model_scope
        if tag_preset:
            payload["tag_preset"] = tag_preset
        if search_query:
            payload["search_query"] = search_query
        if repeat:
            payload["repeat"] = repeat
        if name:
            payload["name"] = name
        if concept:
            payload["concept"] = concept
        return as_json(client.put(f"/ext/lora-dataset/projects/{project_id}", payload))

    @mcp.tool()
    def delete_lora_project(project_id: int) -> str:
        """Delete a LoRA dataset project.

        Args:
            project_id: Project ID
        """
        return as_json(client.delete(f"/ext/lora-dataset/projects/{project_id}"))

    @mcp.tool()
    def get_lora_project_tags(project_id: int, limit: int = 200) -> str:
        """Get aggregated tag summary for a project's files.

        Returns tags sorted by frequency with count and average confidence.

        Args:
            project_id: Project ID
            limit: Max number of tags to return (default: 200)
        """
        return as_json(
            client.get(f"/ext/lora-dataset/projects/{project_id}/tags", {"limit": str(limit)})
        )

    @mcp.tool()
    def preview_lora_caption(project_id: int, file_id: int | None = None) -> str:
        """Preview the caption that would be generated for a file.

        Args:
            project_id: Project ID
            file_id: File ID to preview (default: first file in project)
        """
        params = {}
        if file_id is not None:
            params["file_id"] = str(file_id)
        return as_json(client.get(f"/ext/lora-dataset/projects/{project_id}/caption-preview", params))

    @mcp.tool()
    def export_lora_dataset(project_id: int, output_dir: str = "") -> str:
        """Export dataset to kohya_ss folder structure with images and captions.

        Creates: {output_dir}/{project_name}/{repeat}_{concept}/ with .png/.jpg + .txt pairs.

        Args:
            project_id: Project ID
            output_dir: Output directory (uses config default if empty)
        """
        payload = {}
        if output_dir:
            payload["output_dir"] = output_dir
        return as_json(client.post(f"/ext/lora-dataset/projects/{project_id}/export", payload))

    @mcp.tool()
    def get_lora_export_status(project_id: int) -> str:
        """Get export progress/result for a project.

        Args:
            project_id: Project ID
        """
        return as_json(client.get(f"/ext/lora-dataset/projects/{project_id}/export/status"))
