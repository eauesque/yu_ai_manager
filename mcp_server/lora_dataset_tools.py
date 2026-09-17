"""MCP tools for LoRA Dataset Manager."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .lora_dataset_tools_presets import register_lora_dataset_preset_tools
from .lora_dataset_tools_projects import register_lora_dataset_project_tools
from .lora_dataset_tools_training import register_lora_dataset_training_tools


def register_lora_dataset_tools(mcp: FastMCP, client: YuManagerClient):
    """Register LoRA Dataset Manager tools."""
    register_lora_dataset_project_tools(mcp, client)
    register_lora_dataset_training_tools(mcp, client)
    register_lora_dataset_preset_tools(mcp, client)
