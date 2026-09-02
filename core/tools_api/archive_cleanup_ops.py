"""Payload builders for archive cleanup APIs."""

from __future__ import annotations

import os
from typing import Any

from core.tools.archive_cleanup_execute import execute_archive_cleanup
from core.tools.archive_cleanup_scan import scan_archive_pairs


def _validate_path(path: str) -> str | None:
    """Return error message if *path* contains unsafe patterns, else None."""
    if not path:
        return "path is required"
    # Prevent expanduser(): reject leading ~ only (allow ~ in Windows short names)
    if path.startswith("~"):
        return "Path must not start with '~'"
    normalized = os.path.normpath(path)
    if ".." in normalized.split(os.sep):
        return "Path must not contain '..'"
    return None


def scan_archive_pairs_payload(
    data: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Validate and execute archive pair scan."""
    path = str(data.get("path", "")).strip()
    err = _validate_path(path)
    if err:
        return {"error": err}, 400

    recursive = bool(data.get("recursive", False))

    result = scan_archive_pairs(path, recursive=recursive)

    if "error" in result:
        return result, 400
    return result, 200


def execute_archive_cleanup_payload(
    data: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Validate and execute archive cleanup actions."""
    actions: list[dict[str, str]] = data.get("actions", [])
    if not isinstance(actions, list) or not actions:
        return {"error": "actions array is required"}, 400

    valid_actions = {"delete_archive", "delete_folder", "skip"}
    for i, item in enumerate(actions):
        if not isinstance(item, dict):
            return {"error": f"actions[{i}] must be an object"}, 400
        action = item.get("action", "")
        if action not in valid_actions:
            return {"error": f"actions[{i}].action invalid: {action}"}, 400
        if action == "delete_archive":
            p = str(item.get("archive_path", "")).strip()
            err = _validate_path(p)
            if err:
                return {"error": f"actions[{i}].archive_path: {err}"}, 400
        elif action == "delete_folder":
            p = str(item.get("folder_path", "")).strip()
            err = _validate_path(p)
            if err:
                return {"error": f"actions[{i}].folder_path: {err}"}, 400

    result = execute_archive_cleanup(actions)

    return result, 200


# ── LLM Verify ────────────────────────────────────────────────────

def llm_verify_payload(
    data: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Validate and execute LLM verification for a single pair."""
    archive_path = str(data.get("archive_path", "")).strip()
    folder_path = str(data.get("folder_path", "")).strip()
    err = _validate_path(archive_path)
    if err:
        return {"error": f"archive_path: {err}"}, 400
    err = _validate_path(folder_path)
    if err:
        return {"error": f"folder_path: {err}"}, 400

    pair_info = data.get("pair_info", {})
    if not isinstance(pair_info, dict):
        return {"error": "pair_info must be an object"}, 400

    from core.tools.archive_cleanup_llm import verify_pair_with_llm
    return verify_pair_with_llm(archive_path, folder_path, pair_info, None)


def llm_verify_batch_payload(
    data: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Validate and execute LLM verification for multiple pairs."""
    pairs: list[dict[str, Any]] = data.get("pairs", [])
    if not isinstance(pairs, list) or not pairs:
        return {"error": "pairs array is required"}, 400
    if len(pairs) > 50:
        return {"error": "Maximum 50 pairs per batch"}, 400

    from core.tools.archive_cleanup_llm import verify_pair_with_llm

    results: list[dict[str, Any]] = []
    for item in pairs:
        archive_path = str(item.get("archive_path", "")).strip()
        folder_path = str(item.get("folder_path", "")).strip()
        pair_info = item.get("pair_info", {})

        err = _validate_path(archive_path) or _validate_path(folder_path)
        if err:
            results.append({"error": err})
            continue

        result, _status = verify_pair_with_llm(
            archive_path, folder_path, pair_info, None)
        if "error" in result:
            results.append({"error": result["error"]})
        else:
            results.append({"result": result})

    return {"results": results}, 200


# ── LLM Config ────────────────────────────────────────────────────

def get_ac_llm_config_payload() -> tuple[dict[str, Any], int]:
    """Return archive cleanup LLM configuration."""
    from core.tools.archive_cleanup_llm_config import get_ac_llm_config
    return get_ac_llm_config(), 200


def save_ac_llm_config_payload(
    data: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Save archive cleanup LLM configuration."""
    from core.tools.archive_cleanup_llm_config import save_ac_llm_config
    return save_ac_llm_config(data)


# ── List Models ────────────────────────────────────────────────

def _list_ollama_models_payload(base_url: str) -> tuple[dict[str, Any], int]:
    from core.analysis.ollama_utils import list_ollama_models
    # allow_local=False: base_url here is an untrusted per-request field
    # (matches Rust's tools_ops.rs::archive_cleanup_list_models, which
    # rejects loopback/private for this endpoint). list_ollama_models
    # resolves, validates, and pins the connection to that single resolution
    # (see ollama_utils.py::_pinned_dns) so a DNS-rebinding answer can't
    # bypass the check between validation and the actual HTTP request.
    try:
        models = list_ollama_models(base_url, allow_local=False)
    except ValueError as e:
        return {"error": str(e)}, 400
    except Exception as e:
        return {"error": f"Connection failed: {e}"}, 200
    return {"models": [m["name"] for m in models]}, 200


def _list_openai_compat_models_payload(base_url: str, api_key: str) -> tuple[dict[str, Any], int]:
    from core.analysis.openai_compat_utils import list_openai_compat_models
    try:
        models = list_openai_compat_models(base_url, api_key, allow_local=False)
    except ValueError as e:
        return {"error": str(e)}, 400
    except Exception as e:
        return {"error": f"Connection failed: {e}"}, 200
    return {"models": [m["id"] for m in models]}, 200


def list_models_payload(
    data: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Fetch model list for the specified engine."""
    engine = str(data.get("engine", "")).strip()
    base_url = str(data.get("base_url", "")).strip()

    if engine == "ollama":
        if not base_url:
            return {"error": "base_url is required"}, 400
        return _list_ollama_models_payload(base_url)

    if engine == "openai_compat":
        if not base_url:
            return {"error": "base_url is required"}, 400
        api_key = str(data.get("api_key", "")).strip()
        return _list_openai_compat_models_payload(base_url, api_key)

    return {"error": f"Unsupported engine: {engine}"}, 400
