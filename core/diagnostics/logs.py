"""Recent log collection for diagnostics bundles."""

from __future__ import annotations

from pathlib import Path

from core.diagnostics.redaction import merge_counts, redact_text

_MAX_LOG_BYTES = 1024 * 1024


def _log_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_root / "logs"
    try:
        from core.paths import get_log_dir  # noqa: PLC0415
        return get_log_dir()
    except Exception:
        return Path("logs")


def collect_recent_logs(project_root: Path | None = None) -> tuple[str, dict[str, int]]:
    root = _log_root(project_root)
    if not root.exists():
        return "", {}
    files = sorted(root.glob("*.log"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    chunks: list[str] = []
    counts: dict[str, int] = {}
    remaining = _MAX_LOG_BYTES
    for path in files:
        if remaining <= 0:
            break
        try:
            with path.open("rb") as fh:
                size = path.stat().st_size
                if size > remaining:
                    fh.seek(max(0, size - remaining))
                data = fh.read(remaining)
        except OSError:
            continue
        remaining -= len(data)
        text = data.decode("utf-8", errors="replace")
        redacted, local_counts = redact_text(text)
        merge_counts(counts, local_counts)
        chunks.append(f"===== {path.name} =====\n{redacted}")
    return "\n".join(chunks), counts
