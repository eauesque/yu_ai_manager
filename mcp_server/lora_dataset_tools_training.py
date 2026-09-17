"""Training tools for LoRA dataset MCP integration."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .lora_dataset_tools_common import as_json


def register_lora_dataset_training_tools(mcp: FastMCP, client: YuManagerClient):
    """Register LoRA dataset training tools."""

    @mcp.tool()
    def list_lora_checkpoints() -> str:
        """List available base model checkpoint files (.safetensors, .ckpt, etc.)
        in the configured checkpoint directory."""
        return as_json(client.get("/ext/lora-dataset/checkpoints"))

    @mcp.tool()
    def preview_lora_train_command(
        project_id: int,
        checkpoint: str,
        extra_args: list | None = None,
        resume: bool = False,
        resume_from: str = "",
    ) -> str:
        """Preview the kohya_ss training command without executing it (dry run).

        Args:
            project_id: Project ID
            checkpoint: Full path to the base model checkpoint file
            extra_args: Additional CLI args (e.g. ["--optimizer_type=AdamW8bit"])
            resume: If True, auto-detect and resume from the latest saved state
            resume_from: Explicit path to a saved state directory to resume from
        """
        payload = {"checkpoint": checkpoint, "dry_run": True}
        if extra_args:
            payload["extra_args"] = extra_args
        if resume:
            payload["resume"] = True
        if resume_from:
            payload["resume_from"] = resume_from
        return as_json(client.post(f"/ext/lora-dataset/projects/{project_id}/train", payload))

    @mcp.tool()
    def start_lora_training(
        project_id: int,
        checkpoint: str,
        extra_args: list | None = None,
        resume: bool = False,
        resume_from: str = "",
    ) -> str:
        """Start LoRA training with kohya_ss. This launches a long-running
        background process. Use get_lora_train_status to monitor progress.

        Args:
            project_id: Project ID
            checkpoint: Full path to the base model checkpoint file
            extra_args: Additional CLI args (e.g. ["--optimizer_type=AdamW8bit"])
            resume: If True, auto-detect and resume from the latest saved state
            resume_from: Explicit path to a saved state directory to resume from
        """
        payload = {"checkpoint": checkpoint}
        if extra_args:
            payload["extra_args"] = extra_args
        if resume:
            payload["resume"] = True
        if resume_from:
            payload["resume_from"] = resume_from
        return as_json(client.post(f"/ext/lora-dataset/projects/{project_id}/train", payload))

    @mcp.tool()
    def get_lora_train_status(project_id: int, tail: int = 50) -> str:
        """Get training job status and recent log output.

        Args:
            project_id: Project ID
            tail: Number of recent log lines to return (default: 50)
        """
        return as_json(client.get(f"/ext/lora-dataset/projects/{project_id}/train/status", {"tail": str(tail)}))
