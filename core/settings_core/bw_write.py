"""Bitwarden write operations: push secrets to vault."""

from __future__ import annotations

import base64
import logging
import subprocess
from typing import Any

from .bw_cli import (
    BW_TIMEOUT,
    is_available,
    key_to_field_name,
    parse_bw_error,
    run_bw,
    validate_name,
)

logger = logging.getLogger(__name__)


def push_secrets_to_bw(
    folder_id: str | None,
    item_name: str,
    secrets: dict[str, str],
) -> dict[str, Any]:
    """Write secrets to Bitwarden in batch.

    Updates an existing item if found, otherwise creates a new secure note.
    Fields are created with type=1 (Hidden).

    Args:
        folder_id: Folder ID (None for no folder).
        item_name: Item name.
        secrets: {"server.pin": "1234", ...} key -> plaintext map.

    Returns:
        {"success": bool, "message": str,
         "mappings": {"server.pin": {"item": "<id>", "field": "server_pin"}, ...}}
    """
    import json as _json

    # Validation
    err = validate_name(item_name, "アイテム名")
    if err:
        return {"success": False, "message": err, "mappings": {}}

    if not secrets:
        return {"success": False, "message": "書き込むシークレットがありません", "mappings": {}}

    if not is_available():
        return {"success": False, "message": "bw CLI が見つかりません", "mappings": {}}

    # Build fields
    key_to_field: dict[str, str] = {}
    new_fields = []
    for key, value in secrets.items():
        field_name = key_to_field_name(key)
        key_to_field[key] = field_name
        new_fields.append({
            "name": field_name,
            "value": value,
            "type": 1,  # Hidden
        })

    # Search for existing item
    existing_item = None
    try:
        r = run_bw(["list", "items", "--search", item_name])
        if r.returncode == 0:
            items = _json.loads(r.stdout)
            # Find exact name match
            for item in items:
                if item.get("name") == item_name:
                    existing_item = item
                    break
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "bw list items タイムアウト", "mappings": {}}
    except Exception as e:
        logger.debug("bw list items check error (proceeding with create): %s", e)

    try:
        if existing_item:
            # Update existing item: merge with existing fields
            item_id = existing_item["id"]
            existing_fields = existing_item.get("fields") or []

            # Exclude existing fields whose names overlap with current write targets
            new_field_names = {f["name"] for f in new_fields}
            merged_fields = [
                f for f in existing_fields
                if f.get("name") not in new_field_names
            ]
            merged_fields.extend(new_fields)
            existing_item["fields"] = merged_fields

            # Base64 encode and pass to bw edit item
            item_json = _json.dumps(existing_item, ensure_ascii=False)
            encoded = base64.b64encode(item_json.encode("utf-8")).decode("ascii")

            r = run_bw(["edit", "item", item_id], stdin_data=encoded)

            logger.info(
                "Bitwarden item updated: name=%s, id=%s, fields=%d",
                item_name, item_id, len(secrets),
            )
        else:
            # Create new secure note
            new_item = {
                "type": 2,  # SecureNote
                "name": item_name,
                "notes": "",
                "folderId": folder_id,
                "fields": new_fields,
                "secureNote": {"type": 0},
            }

            item_json = _json.dumps(new_item, ensure_ascii=False)
            encoded = base64.b64encode(item_json.encode("utf-8")).decode("ascii")

            r = run_bw(["create", "item"], stdin_data=encoded)

            logger.info(
                "Bitwarden item created: name=%s, folder=%s, fields=%d",
                item_name, folder_id, len(secrets),
            )

        if r.returncode != 0:
            msg = parse_bw_error(r.stderr)
            return {"success": False, "message": msg, "mappings": {}}

        # Success: get item ID from response
        try:
            created = _json.loads(r.stdout)
            result_id = created.get("id", existing_item["id"] if existing_item else "")
        except (_json.JSONDecodeError, Exception):
            result_id = existing_item["id"] if existing_item else ""

        # Build mappings
        mappings = {}
        for key, field_name in key_to_field.items():
            mappings[key] = {"item": result_id, "field": field_name}

        action = "更新" if existing_item else "作成"
        return {
            "success": True,
            "message": f"{len(secrets)} 件のシークレットを Bitwarden に{action}しました",
            "mappings": mappings,
        }

    except subprocess.TimeoutExpired:
        action = "edit" if existing_item else "create"
        return {
            "success": False,
            "message": f"bw {action} item タイムアウト ({BW_TIMEOUT}秒)",
            "mappings": {},
        }
    except Exception as e:
        return {"success": False, "message": f"予期しないエラー: {e}", "mappings": {}}
