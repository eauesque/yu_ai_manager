"""ZIP path/text helpers for media file routes."""

from pathlib import Path


def zip_error_text(summary: str, zip_path: Path | None = None, internal_path: str | None = None, hint: str | None = None) -> str:
    parts = [summary]
    if zip_path:
        parts.append(f"zip={zip_path}")
    if internal_path:
        parts.append(f"entry={internal_path}")
    if hint:
        parts.append(f"hint={hint}")
    return " | ".join(parts)


def resolve_zip_target(zip_files: list[str], inner_path: str) -> str | None:
    inner_path_normalized = inner_path.replace("\\", "/")
    if inner_path_normalized in zip_files:
        return inner_path_normalized
    if inner_path in zip_files:
        return inner_path

    filename = Path(inner_path).name
    matches = [f for f in zip_files if Path(f).name == filename]
    if matches:
        return matches[0]
    return None
