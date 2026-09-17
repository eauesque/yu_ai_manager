"""Handlers for scan roots config routes."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

from quart import request

from core.scan_roots_api.checkpoints import fetch_checkpoints_payload
from core.scan_roots_api.ops import (
    add_scan_root,
    batch_toggle_scan_roots,
    edit_scan_root,
    get_scan_roots_with_exists,
    recovery_apply,
    recovery_check,
    recovery_dismiss,
    remove_scan_root,
    reorder_scan_roots,
    toggle_scan_root,
)


def _safe(action: Callable[[], tuple[dict[str, Any], int]]) -> tuple[dict[str, Any], int]:
    try:
        return action()
    except Exception:
        logger.exception("Scan roots config operation failed")
        return {"error": "Scan roots config operation failed", "code": "scan_roots_config_failed"}, 500


def handle_checkpoints() -> tuple[dict[str, Any], int]:
    return _safe(lambda: (fetch_checkpoints_payload(), 200))


def handle_get_scan_roots() -> tuple[dict[str, Any], int]:
    return _safe(lambda: ({"roots": get_scan_roots_with_exists()}, 200))


async def handle_add_scan_root() -> tuple[dict[str, Any], int]:
    try:
        if not request.is_json:
            return {"error": "JSON body is required", "code": "invalid_content_type"}, 400
        payload = await request.get_json(silent=True)
        if payload is None or not isinstance(payload, dict):
            return {"error": "Invalid JSON body", "code": "invalid_json"}, 400
        new_root, err = add_scan_root(payload)
        if err:
            return err
        return {"success": True, "root": new_root}, 200
    except Exception:
        logger.exception("Scan roots config operation failed")
        return {"error": "Scan roots config operation failed", "code": "scan_roots_config_failed"}, 500


def handle_remove_scan_root(index: int) -> tuple[dict[str, Any], int]:
    return _safe(lambda: _remove(index))


def _remove(index: int) -> tuple[dict[str, Any], int]:
    removed, err = remove_scan_root(index)
    if err:
        return err
    return {"success": True, "removed": removed}, 200


def handle_toggle_scan_root(index: int) -> tuple[dict[str, Any], int]:
    return _safe(lambda: _toggle(index))


def _toggle(index: int) -> tuple[dict[str, Any], int]:
    root, err = toggle_scan_root(index)
    if err:
        return err
    return {"success": True, "root": root}, 200


async def handle_edit_scan_root(index: int) -> tuple[dict[str, Any], int]:
    try:
        if not request.is_json:
            return {"error": "JSON body is required", "code": "invalid_content_type"}, 400
        payload = await request.get_json(silent=True)
        if payload is None or not isinstance(payload, dict):
            return {"error": "Invalid JSON body", "code": "invalid_json"}, 400
        root, err = edit_scan_root(index, payload)
        if err:
            return err
        return {"success": True, "root": root}, 200
    except Exception:
        logger.exception("Scan roots config operation failed")
        return {"error": "Scan roots config operation failed", "code": "scan_roots_config_failed"}, 500


async def handle_batch_toggle_scan_roots() -> tuple[dict[str, Any], int]:
    try:
        if not request.is_json:
            return {"error": "JSON body is required", "code": "invalid_content_type"}, 400
        payload = await request.get_json(silent=True)
        if payload is None or not isinstance(payload, dict):
            return {"error": "Invalid JSON body", "code": "invalid_json"}, 400
        enabled = payload.get("enabled", True)
        result, err = batch_toggle_scan_roots(bool(enabled))
        if err:
            return err
        return {"success": True, **result}, 200
    except Exception:
        logger.exception("Batch toggle scan roots failed")
        return {"error": "Batch toggle failed", "code": "batch_toggle_failed"}, 500


async def handle_reorder_scan_roots() -> tuple[dict[str, Any], int]:
    try:
        if not request.is_json:
            return {"error": "JSON body is required", "code": "invalid_content_type"}, 400
        payload = await request.get_json(silent=True)
        if payload is None or not isinstance(payload, dict):
            return {"error": "Invalid JSON body", "code": "invalid_json"}, 400
        roots, err = reorder_scan_roots(payload)
        if err:
            return err
        return {"success": True, "roots": roots}, 200
    except Exception:
        logger.exception("Scan roots config operation failed")
        return {"error": "Scan roots config operation failed", "code": "scan_roots_config_failed"}, 500


def handle_recovery_check() -> tuple[dict[str, Any], int]:
    return _safe(recovery_check)


async def handle_recovery_apply() -> tuple[dict[str, Any], int]:
    try:
        payload = await request.get_json(silent=True) if request.is_json else None
        return recovery_apply(payload if isinstance(payload, dict) else {})
    except Exception:
        logger.exception("Scan roots recovery apply failed")
        return {"error": "Recovery apply failed", "code": "recovery_apply_failed"}, 500


def handle_recovery_dismiss() -> tuple[dict[str, Any], int]:
    return _safe(recovery_dismiss)
