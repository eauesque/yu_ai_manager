"""File operations for custom extension authoring."""

import json
import logging

from .authoring_rules import (
    FILE_TYPES,
    ext_dir,
    resolve_file_path,
    validate_file_type,
    validate_filename,
    validate_name,
)

logger = logging.getLogger(__name__)
_UNTRUSTED_LEVEL = "untrusted"


def create_extension(name: str, description: str = "") -> dict:
    """Create a new custom extension with scaffold files."""
    name_err = validate_name(name)
    if name_err:
        return {"ok": False, "error": name_err}

    extension_path = ext_dir(name)
    if extension_path.exists():
        return {"ok": False, "error": f"Extension 'custom-{name}' already exists"}

    extension_path.mkdir(parents=True, exist_ok=True)
    (extension_path / "templates" / name.replace("-", "_")).mkdir(parents=True, exist_ok=True)
    (extension_path / "static").mkdir(parents=True, exist_ok=True)

    entrypoint = f"{name.replace('-', '_')}_ext.py"
    manifest = {
        "name": f"custom-{name}",
        "version": "0.1.0",
        "description": description or f"Custom extension: {name}",
        "entry": entrypoint,
        "author": "user",
        "trust_level": _UNTRUSTED_LEVEL,
        "has_blueprint": True,
        "blueprint_prefix": f"/ext/custom-{name}",
        "permissions": {"required": [], "optional": []},
    }
    manifest_path = extension_path / "extension.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    py_name = name.replace("-", "_")
    entrypoint_path = extension_path / entrypoint
    entrypoint_path.write_text(
        f'''"""Custom extension: {name}."""\n\nfrom quart import Blueprint\n\nbp = Blueprint("custom_{py_name}", __name__,\n               template_folder="templates",\n               static_folder="static")\n\n\ndef get_blueprint():\n    """Return the Blueprint for this extension."""\n    return bp\n''',
        encoding="utf-8",
    )

    logger.info("[authoring] Created extension scaffold: custom-%s", name)
    return {
        "ok": True,
        "name": f"custom-{name}",
        "path": str(extension_path),
        "files": [
            str(manifest_path.relative_to(extension_path)),
            str(entrypoint_path.relative_to(extension_path)),
        ],
    }


def write_extension_file(extension_name: str, file_type: str, filename: str, content: str) -> dict:
    """Write a validated text file into a custom extension."""
    name_err = validate_name(extension_name)
    if name_err:
        return {"ok": False, "error": name_err}
    file_type_err = validate_file_type(file_type)
    if file_type_err:
        return {"ok": False, "error": file_type_err}
    filename_err = validate_filename(filename, file_type)
    if filename_err:
        return {"ok": False, "error": filename_err}

    extension_path = ext_dir(extension_name)
    if not extension_path.exists():
        return {"ok": False, "error": f"Extension 'custom-{extension_name}' does not exist. Create it first."}

    _, _, max_size = FILE_TYPES[file_type]
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > max_size:
        return {"ok": False, "error": f"Content too large ({len(content_bytes)} bytes, max {max_size})"}
    if "\x00" in content:
        return {"ok": False, "error": "Binary content is not allowed"}

    file_path = resolve_file_path(extension_name, file_type, filename)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    logger.info("[authoring] Wrote %s/%s (%d bytes)", extension_name, file_path.name, len(content_bytes))
    return {
        "ok": True,
        "file": str(file_path.relative_to(extension_path)),
        "size": len(content_bytes),
    }


def read_extension_file(extension_name: str, file_type: str, filename: str) -> dict:
    """Read a file from a custom extension."""
    name_err = validate_name(extension_name)
    if name_err:
        return {"ok": False, "error": name_err}
    file_type_err = validate_file_type(file_type)
    if file_type_err:
        return {"ok": False, "error": file_type_err}
    filename_err = validate_filename(filename, file_type)
    if filename_err:
        return {"ok": False, "error": filename_err}

    extension_path = ext_dir(extension_name)
    if not extension_path.exists():
        return {"ok": False, "error": f"Extension 'custom-{extension_name}' does not exist"}

    file_path = resolve_file_path(extension_name, file_type, filename)
    if not file_path.exists():
        return {"ok": False, "error": f"File not found: {file_path.name}"}

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"ok": False, "error": "File contains binary data and cannot be read as text"}

    return {
        "ok": True,
        "file": str(file_path.relative_to(extension_path)),
        "content": content,
        "size": len(content.encode("utf-8")),
    }


def list_extension_files(extension_name: str) -> dict:
    """List all files in a custom extension."""
    name_err = validate_name(extension_name)
    if name_err:
        return {"ok": False, "error": name_err}

    extension_path = ext_dir(extension_name)
    if not extension_path.exists():
        return {"ok": False, "error": f"Extension 'custom-{extension_name}' does not exist"}

    files: list[dict] = []
    for file_path in sorted(extension_path.rglob("*")):
        if file_path.is_file():
            files.append(
                {
                    "path": str(file_path.relative_to(extension_path)).replace("\\", "/"),
                    "size": file_path.stat().st_size,
                }
            )

    return {
        "ok": True,
        "name": f"custom-{extension_name}",
        "files": files,
        "total_size": sum(file["size"] for file in files),
    }


def validate_extension(extension_name: str) -> dict:
    """Validate extension.json and run CodeVerifier without registering."""
    name_err = validate_name(extension_name)
    if name_err:
        return {"ok": False, "error": name_err}

    extension_path = ext_dir(extension_name)
    if not extension_path.exists():
        return {"ok": False, "error": f"Extension 'custom-{extension_name}' does not exist"}

    manifest_path = extension_path / "extension.json"
    if not manifest_path.exists():
        return {"ok": False, "error": "extension.json not found"}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"ok": False, "error": f"Invalid extension.json: {exc}"}

    issues = _collect_manifest_issues(extension_path, manifest)
    code_findings = _run_code_verifier(extension_path, issues)
    return {
        "ok": len(issues) == 0,
        "name": f"custom-{extension_name}",
        "issues": issues,
        "code_findings": code_findings,
        "manifest": manifest,
    }


def _collect_manifest_issues(extension_path, manifest: dict) -> list[str]:
    issues: list[str] = []
    for field in ("name", "version", "entry"):
        if field not in manifest:
            issues.append(f"Missing required field: {field}")
    if "entry" in manifest:
        entrypoint_path = extension_path / manifest["entry"]
        if not entrypoint_path.exists():
            issues.append(f"Entrypoint file not found: {manifest['entry']}")
    return issues


def _run_code_verifier(extension_path, issues: list[str]) -> list[dict]:
    code_findings: list[dict] = []
    try:
        from core.extensions_core.validation.code_verifier import CodeVerifier

        verifier = CodeVerifier()
        verdict = verifier.verify(
            extension_path,
            trust_level=_UNTRUSTED_LEVEL,
            granted_permissions=set(),
        )
        for finding in verdict.findings:
            code_findings.append(
                {
                    "severity": finding.severity,
                    "message": finding.message,
                    "file": getattr(finding, "file", ""),
                    "line": getattr(finding, "line", 0),
                }
            )
        if not verdict.approved:
            issues.append("CodeVerifier rejected: dangerous patterns detected")
    except Exception as exc:
        issues.append(f"CodeVerifier failed: {exc}")
    return code_findings
