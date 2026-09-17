"""WebM metadata extractors for legacy media parsing."""

import json
import logging

logger = logging.getLogger(__name__)


def extract_webm_metadata(path) -> dict[str, str]:
    import subprocess

    out: dict[str, str] = {}

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_entries",
                "format_tags",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )

        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                tags = data.get("format", {}).get("tags", {})

                for key in ["comment", "COMMENT", "Comment", "description", "DESCRIPTION"]:
                    if key in tags:
                        text = tags[key]
                        if isinstance(text, str) and text.strip():
                            out["comment"] = text
                            if ("Steps:" in text) and ("Negative prompt:" in text or "Sampler:" in text):
                                out["parameters"] = text
                                out["Parameters"] = text
                            break

                for key in ["prompt", "workflow", "PROMPT", "WORKFLOW"]:
                    if key in tags:
                        text = tags[key]
                        if isinstance(text, str) and text.strip():
                            out[key.lower()] = text

            except json.JSONDecodeError:
                pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    if not out:
        try:
            with path.open("rb") as f:
                header = f.read(65536)
                text = header.decode("utf-8", errors="ignore")

                if "Steps:" in text and "Sampler:" in text:
                    import re

                    match = re.search(r"([^\x00]*Steps:[^\x00]+Sampler:[^\x00]+)", text)
                    if match:
                        params = match.group(1).strip()
                        if params:
                            out["parameters"] = params
                            out["Parameters"] = params
        except Exception as exc:
            logger.debug("WebM legacy metadata extraction failed: %s", exc)

    return out
