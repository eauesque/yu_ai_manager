"""Extension authoring MCP tool registration."""

from __future__ import annotations

import json


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(msg: str) -> str:
    return _json({"ok": False, "error": msg})


def register_extension_authoring_tools(mcp, client) -> None:
    @mcp.tool()
    def create_extension(name: str, description: str = "") -> str:
        """Create a new custom extension with scaffold files.

        Creates extensions/custom-{name}/ with extension.json, entrypoint, and directory structure.
        The extension starts as L2 (Untrusted) and requires user approval before activation.

        Args:
            name: Extension name. Lowercase letters, numbers, and hyphens only (e.g. "my-watermark").
                  Must not start with "builtin-".
            description: Short description of what the extension does.
        """
        name = name.strip()
        if not name:
            return _err("name must not be empty")
        return _json(client.post("/api/extensions/author/create", {"name": name, "description": description}))

    @mcp.tool()
    def write_extension_file(extension_name: str, file_type: str, filename: str, content: str) -> str:
        """Write a file to a custom extension.

        Only text files are allowed. Binary content is prohibited.
        The extension must have been created with create_extension() first.

        Args:
            extension_name: Extension name (without "custom-" prefix, e.g. "my-watermark")
            file_type: File type - one of:
                - "entrypoint": Python entry point (.py, max 50KB)
                - "template": HTML template (.html, max 50KB, placed in templates/{name}/)
                - "static_css": CSS file (.css, max 50KB, placed in static/)
                - "static_js": JavaScript file (.js, max 50KB, placed in static/)
                - "config": extension.json manifest (.json, max 10KB)
                - "readme": README file (.md, max 20KB)
            filename: File name without extension (e.g. "index" for index.html).
                      For config type, must be "extension". For readme, must be "README".
            content: File content as text string.
        """
        extension_name = extension_name.strip()
        if not extension_name:
            return _err("extension_name must not be empty")
        return _json(
            client.post(
                f"/api/extensions/author/{extension_name}/write",
                {"file_type": file_type, "filename": filename, "content": content},
            )
        )

    @mcp.tool()
    def read_extension_file(extension_name: str, file_type: str, filename: str) -> str:
        """Read a file from a custom extension.

        Can only read files within the specified custom extension.
        Core, builtin, and other custom extensions are not accessible.

        Args:
            extension_name: Extension name (without "custom-" prefix)
            file_type: File type (entrypoint, template, static_css, static_js, config, readme)
            filename: File name without extension
        """
        extension_name = extension_name.strip()
        if not extension_name:
            return _err("extension_name must not be empty")
        return _json(
            client.get(
                f"/api/extensions/author/{extension_name}/read",
                {"file_type": file_type, "filename": filename},
            )
        )

    @mcp.tool()
    def list_extension_files(extension_name: str) -> str:
        """List all files in a custom extension directory.

        Args:
            extension_name: Extension name (without "custom-" prefix)
        """
        extension_name = extension_name.strip()
        if not extension_name:
            return _err("extension_name must not be empty")
        return _json(client.get(f"/api/extensions/author/{extension_name}/files"))

    @mcp.tool()
    def validate_extension(extension_name: str) -> str:
        """Validate a custom extension's manifest and code without registering it.

        Runs CodeVerifier static analysis and checks extension.json structure.
        Use this before registering to catch issues early.

        Args:
            extension_name: Extension name (without "custom-" prefix)
        """
        extension_name = extension_name.strip()
        if not extension_name:
            return _err("extension_name must not be empty")
        return _json(client.post(f"/api/extensions/author/{extension_name}/validate", {}))
