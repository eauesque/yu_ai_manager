"""WebM metadata extraction -- EBML/Matroska tag parsing."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_webm_metadata(path: Path) -> dict[str, str]:
    """Extract metadata from WebM files (Automatic1111 embeds data as comments).
    
    WebM files may contain:
      - Comment tags with A1111 parameters
      - Title tags
      - Other Matroska tags
    
    Uses subprocess to call ffprobe if available, otherwise tries basic parsing.
    """
    import subprocess
    
    out: dict[str, str] = {}
    
    # Try ffprobe first (most reliable method)
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_entries", "format_tags",
                str(path)
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10
        )
        
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                tags = data.get("format", {}).get("tags", {})
                
                # Look for common metadata fields
                for key in ["comment", "COMMENT", "Comment", "description", "DESCRIPTION"]:
                    if key in tags:
                        text = tags[key]
                        if isinstance(text, str) and text.strip():
                            out["comment"] = text
                            # Check if it's A1111 format
                            if ("Steps:" in text) and ("Negative prompt:" in text or "Sampler:" in text):
                                out["parameters"] = text
                                out["Parameters"] = text
                            break
                
                # Also check for prompt/workflow (ComfyUI style)
                for key in ["prompt", "workflow", "PROMPT", "WORKFLOW"]:
                    if key in tags:
                        text = tags[key]
                        if isinstance(text, str) and text.strip():
                            out[key.lower()] = text
                
            except json.JSONDecodeError:
                pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # ffprobe not available or timed out
        pass
    
    # Fallback: Try basic Matroska tag parsing
    if not out:
        try:
            with path.open("rb") as f:
                # Read first 64KB to look for tags
                header = f.read(65536)
                
                # Look for common text patterns (very basic heuristic)
                # Matroska uses EBML format, which is complex, so this is best-effort
                text = header.decode("utf-8", errors="ignore")
                
                # Look for A1111-style parameters
                if "Steps:" in text and "Sampler:" in text:
                    # Try to extract the parameters section
                    import re
                    # Look for pattern starting with tags and ending before binary data
                    match = re.search(r'([^\x00]*Steps:[^\x00]+Sampler:[^\x00]+)', text)
                    if match:
                        params = match.group(1).strip()
                        if params:
                            out["parameters"] = params
                            out["Parameters"] = params
        except Exception as exc:
            logger.debug("WebM metadata extraction failed: %s", exc)
    
    return out


