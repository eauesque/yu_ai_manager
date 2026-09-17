"""Archive cleanup LLM verification -- use LLM to verify archive/folder pairs.

Send file list comparison as text to LLM and obtain duplicate determination.
Images are not needed so text-only engines are used (Hailo VLM excluded).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def verify_pair_with_llm(
    archive_path: str,
    folder_path: str,
    pair_info: dict[str, Any],
    llm_config: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Validate an archive/folder pair using LLM.

    Returns (result_dict, status_code).
    """
    from core.tools.archive_cleanup_llm_config import resolve_ac_llm_engine

    engine_type, engine_kwargs, err = resolve_ac_llm_engine(llm_config)
    if err:
        return {"error": err}, 400

    prompt = build_verification_prompt(pair_info)

    try:
        raw = _call_engine(engine_type, engine_kwargs, prompt)
    except Exception as exc:
        logger.warning("LLM verification failed: %s", exc)
        return {"error": "LLM verification failed"}, 500

    result = _parse_llm_response(raw)
    return result, 200


def build_verification_prompt(pair_info: dict[str, Any]) -> str:
    """Build a file list comparison prompt."""
    arc_name = pair_info.get("archive_name", "?")
    arc_count = pair_info.get("archive_file_count", 0)
    fld_name = pair_info.get("folder_name", "?")
    fld_count = pair_info.get("folder_file_count", 0)
    match_rate = pair_info.get("match_rate", 0)
    diagnosis = pair_info.get("diagnosis")
    adj_rate = pair_info.get("adjusted_match_rate")
    adj_reason = pair_info.get("adjustment_reason", "")

    diag_text = ""
    if diagnosis:
        diag_text = f"\n- Diagnosis: {diagnosis}"
        if adj_rate is not None:
            diag_text += f" (adjusted match rate: {adj_rate}%)"
        if adj_reason:
            diag_text += f"\n- Reason: {adj_reason}"

    return f"""You are an archive management assistant. Analyze the following archive/folder pair and determine if they are duplicates.

## Pair Information
- Archive: {arc_name} ({arc_count} files)
- Folder: {fld_name} ({fld_count} files)
- Match rate (name+size): {match_rate}%{diag_text}

## Task
Determine if the folder is an extracted copy of the archive. Consider:
1. File count differences
2. Match rate and what might cause mismatches
3. Whether it's safe to delete one side

## Response Format (JSON only)
{{
  "is_duplicate": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation in Japanese",
  "recommendation": "delete_archive / delete_folder / keep_both",
  "warnings": ["Any concerns (Japanese)"]
}}"""


def _call_engine(
    engine_type: str,
    engine_kwargs: dict[str, Any],
    prompt: str,
) -> str:
    """Directly call each engine's _call_api(messages)."""
    from core.analysis.engines_factory import get_engine

    engine = get_engine(engine_type, **engine_kwargs)
    messages: list[dict[str, Any]]

    if engine_type == "ollama":
        messages = [{"role": "user", "content": prompt}]
        return engine._call_api(messages, format_json=True)  # type: ignore[attr-defined]

    # Claude / OpenAI / OpenAI-compat: text-only messages
    messages = [{"role": "user", "content": prompt}]
    return engine._call_api(messages)  # type: ignore[attr-defined]


def _parse_llm_response(raw: str) -> dict[str, Any]:
    """Extract and parse JSON from LLM response."""
    # Look for JSON block
    text = raw.strip()

    # Extract ```json ... ```
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    # Extract { ... }
    if "{" in text:
        brace_start = text.index("{")
        brace_end = text.rindex("}") + 1
        text = text[brace_start:brace_end]

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {
            "is_duplicate": False,
            "confidence": 0.0,
            "reasoning": raw[:500],
            "recommendation": "keep_both",
            "warnings": ["LLM response could not be parsed as JSON"],
        }

    return {
        "is_duplicate": bool(data.get("is_duplicate", False)),
        "confidence": float(data.get("confidence", 0.0)),
        "reasoning": str(data.get("reasoning", "")),
        "recommendation": str(data.get("recommendation", "keep_both")),
        "warnings": list(data.get("warnings", [])),
    }
